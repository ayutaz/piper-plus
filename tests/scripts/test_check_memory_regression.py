"""The per-language memory gate must fail on growth and on missing data.

Regression focus: memory-regression.yml compared inline, never failed,
and every baseline was ``null``, so it reported SKIP for all six
languages on every run.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_memory_regression.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "memory-regression.yml"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_memory_regression", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _write(tmp_path, gate, base_mb=200.0, observed=None):
    baseline = {
        "threshold_pct": 0.15,
        "languages": {lang: {"peak_memory_mb": base_mb} for lang in gate.LANGUAGES},
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    results = tmp_path / "results"
    results.mkdir()
    for lang in gate.LANGUAGES:
        value = (observed or {}).get(lang, base_mb)
        if value is not None:
            # benchmark.py --format json writes a single object.
            (results / f"{lang}.json").write_text(
                json.dumps({"peak_memory_mb": value}), encoding="utf-8"
            )
    return path, results


def _run(gate, path, results, *extra):
    return gate.main(["--baseline", str(path), "--results-dir", str(results), *extra])


def test_committed_baseline_has_a_value_for_every_language(gate):
    baseline = json.loads(gate.DEFAULT_BASELINE.read_text(encoding="utf-8"))
    for lang in gate.LANGUAGES:
        value = baseline["languages"][lang]["peak_memory_mb"]
        assert isinstance(value, (int, float)) and value > 0, lang
    assert baseline["policy"] == "fail"


def test_within_threshold_passes(gate, tmp_path):
    path, results = _write(tmp_path, gate, observed={"ja": 229.0})
    assert _run(gate, path, results) == 0


def test_growth_beyond_threshold_fails(gate, tmp_path):
    path, results = _write(tmp_path, gate, observed={"zh": 231.0})
    rows = {r["lang"]: r for r in gate.compare(json.loads(path.read_text()), results)}
    assert rows["zh"]["status"] == "FAIL"
    assert _run(gate, path, results) == 1


def test_shrinking_passes(gate, tmp_path):
    path, results = _write(tmp_path, gate, observed={"en": 100.0})
    assert _run(gate, path, results) == 0


def test_missing_result_fails(gate, tmp_path):
    path, results = _write(tmp_path, gate, observed={"fr": None})
    rows = {r["lang"]: r for r in gate.compare(json.loads(path.read_text()), results)}
    assert rows["fr"]["status"] == "MISSING"
    assert _run(gate, path, results) == 1


def test_null_baseline_fails(gate, tmp_path):
    path, results = _write(tmp_path, gate, base_mb=None, observed=dict.fromkeys(gate.LANGUAGES, 200.0))
    assert _run(gate, path, results) == 1


def test_list_shaped_result_is_read(gate, tmp_path):
    path, results = _write(tmp_path, gate)
    (results / "pt.json").write_text(json.dumps([{"peak_memory_mb": 200.0}]), encoding="utf-8")
    assert _run(gate, path, results) == 0


def test_update_baseline_writes_rounded_values_and_refuses_gaps(gate, tmp_path):
    path, results = _write(tmp_path, gate, observed={"es": 212.34})
    assert _run(gate, path, results, "--update-baseline") == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["languages"]["es"]["peak_memory_mb"] == 212.3

    (results / "ja.json").unlink()
    assert _run(gate, path, results, "--update-baseline") == 1
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_workflow_runs_the_gate_without_swallowing_its_exit_code():
    wf = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = wf["jobs"]["memory"]
    assert job["permissions"]["contents"] == "read"
    step = next(s for s in job["steps"] if s.get("id") == "compare")
    assert "check_memory_regression.py" in step["run"]
    assert "||" not in step["run"]
    assert step.get("continue-on-error", "false") == "false"
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "initialize_baseline" not in text
    assert "git-auto-commit" not in text
