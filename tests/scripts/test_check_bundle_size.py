"""The bundle size gate must fail on anything it cannot compare.

Regression focus: a missing artifact and a ``size_bytes: null`` baseline
used to be a ``SKIP`` that never failed, the pack steps were
continue-on-error, and every baseline was ``null``. The gate stayed green
for its whole life without comparing a single size.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_bundle_size.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "bundle-size-gate.yml"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_bundle_size", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


@pytest.fixture
def built(gate, tmp_path, monkeypatch):
    """Lay out one fake artifact per entry under a temporary repo root."""
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    sizes = {}
    for i, art in enumerate(gate.ARTIFACTS):
        path = tmp_path / art.glob.replace("[0-9]*", "1.0.0")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * (1000 + i))
        sizes[gate._baseline_key(art)] = 1000 + i
    return sizes


def _baseline(tmp_path, gate, sizes):
    data = {
        "schema_version": gate.BASELINE_SCHEMA_VERSION,
        "version": 1,
        "artifacts": {
            key: {"size_bytes": size} for key, size in sizes.items()
        },
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_committed_baseline_has_a_size_for_every_artifact(gate):
    baseline = json.loads(gate.DEFAULT_BASELINE.read_text(encoding="utf-8"))
    for art in gate.ARTIFACTS:
        size = baseline["artifacts"][gate._baseline_key(art)]["size_bytes"]
        assert isinstance(size, int) and size > 0, art


def test_matching_sizes_pass(gate, built, tmp_path):
    assert gate.main(["--baseline", str(_baseline(tmp_path, gate, built))]) == 0


def test_size_beyond_tolerance_fails(gate, built, tmp_path):
    key = next(iter(built))
    grown = dict(built, **{key: int(built[key] / 1.2)})
    assert gate.main(["--baseline", str(_baseline(tmp_path, gate, grown))]) == 1


def test_missing_artifact_fails(gate, built, tmp_path):
    art = gate.ARTIFACTS[0]
    (tmp_path / art.glob.replace("[0-9]*", "1.0.0")).unlink()
    baseline = _baseline(tmp_path, gate, built)
    results = gate._compare(gate._load_baseline(baseline), gate._current_snapshot())
    assert results[0].status == "missing"
    assert gate.main(["--baseline", str(baseline)]) == 1


def test_null_baseline_fails(gate, built, tmp_path):
    key = gate._baseline_key(gate.ARTIFACTS[-1])
    baseline = _baseline(tmp_path, gate, dict(built, **{key: None}))
    results = gate._compare(gate._load_baseline(baseline), gate._current_snapshot())
    assert results[-1].status == "no-baseline"
    assert gate.main(["--baseline", str(baseline)]) == 1


def test_warn_only_never_fails(gate, built, tmp_path):
    key = gate._baseline_key(gate.ARTIFACTS[0])
    baseline = _baseline(tmp_path, gate, dict(built, **{key: None}))
    assert gate.main(["--baseline", str(baseline), "--warn-only"]) == 0


def test_update_baseline_refuses_partial_build_and_keeps_comment(
    gate, built, tmp_path
):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"_comment": "keep me", "artifacts": {}}), encoding="utf-8")
    assert gate.main(["--baseline", str(path), "--update-baseline"]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["_comment"] == "keep me"
    assert {k: v["size_bytes"] for k, v in data["artifacts"].items()} == built

    art = gate.ARTIFACTS[0]
    (tmp_path / art.glob.replace("[0-9]*", "1.0.0")).unlink()
    assert gate.main(["--baseline", str(path), "--update-baseline"]) == 1
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_workflow_lets_pack_failures_and_gate_fail_the_job():
    wf = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    for job in wf["jobs"].values():
        assert "continue-on-error" not in job
        for step in job["steps"]:
            assert step.get("continue-on-error", "false") == "false", step.get("name")
    steps = wf["jobs"]["bundle-size"]["steps"]
    gate_step = next(s for s in steps if s.get("id") == "gate")
    runs = [
        line
        for line in gate_step["run"].replace("\\\n", " ").splitlines()
        if "check_bundle_size.py" in line
    ]
    # The JSON report may be warn-only; the Markdown invocation is the gate.
    assert any("--warn-only" not in line for line in runs)
    assert 'exit "$status"' in gate_step["run"]
