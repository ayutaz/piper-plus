"""Unit tests for scripts/check_artifact_retention.py (M2 T-006)."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_artifact_retention.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_artifact_retention",
        SCRIPT_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _spec_toml(mode: str = "warn") -> str:
    return textwrap.dedent(f"""
        [meta]
        spec_version = 1
        applies_to = ["github-actions"]
        canonical_reference = ".github/workflows/*.yml"
        forward_compat_policy = "strict"
        direction = "pre-impl"
        mode = "{mode}"

        [[categories]]
        name = "ephemeral"
        retention_days = 1

        [[categories]]
        name = "pr-debug"
        retention_days = 7

        [[categories]]
        name = "regression-baseline"
        retention_days = 30

        [[categories]]
        name = "release-publish"
        retention_days = 90
    """)


def _workflow_with_retention(value: int) -> str:
    return textwrap.dedent(f"""
        name: test
        on: push
        jobs:
          j:
            runs-on: ubuntu-24.04
            steps:
              - uses: actions/upload-artifact@v4
                with:
                  name: thing
                  path: out/
                  retention-days: {value}
    """)


def test_allowed_values(mod, tmp_path: Path):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    spec = mod.load_spec(spec_path)
    assert mod.allowed_values(spec) == {
        1: "ephemeral",
        7: "pr-debug",
        30: "regression-baseline",
        90: "release-publish",
    }


def test_scan_workflows_extracts_retention(mod, tmp_path: Path):
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "a.yml").write_text(_workflow_with_retention(7))
    (wf_dir / "b.yaml").write_text(_workflow_with_retention(30))
    findings = mod.scan_workflows(wf_dir)
    assert len(findings) == 2
    values = {f[2] for f in findings}
    assert values == {7, 30}


def test_scan_ignores_templated_value(mod, tmp_path: Path):
    """`retention-days: ${{ env.X }}` is out of scope — skip silently."""
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    body = _workflow_with_retention(7).replace(": 7", ": ${{ env.RETENTION }}")
    (wf_dir / "a.yml").write_text(body)
    assert mod.scan_workflows(wf_dir) == []


def test_evaluate_no_violations_for_aligned(mod, tmp_path: Path):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    spec = mod.load_spec(spec_path)
    findings = [(Path("a.yml"), 10, 7), (Path("b.yml"), 5, 30)]
    violations, workflows, steps = mod.evaluate(spec, findings)
    assert violations == []
    assert workflows == 2
    assert steps == 2


def test_evaluate_flags_14_days(mod, tmp_path: Path):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    spec = mod.load_spec(spec_path)
    findings = [(REPO_ROOT / "x.yml", 10, 14)]
    violations, *_ = mod.evaluate(spec, findings)
    assert len(violations) == 1
    assert "14" in violations[0]


def test_evaluate_flags_365_days(mod, tmp_path: Path):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    spec = mod.load_spec(spec_path)
    findings = [(REPO_ROOT / "x.yml", 10, 365)]
    violations, *_ = mod.evaluate(spec, findings)
    assert len(violations) == 1


def test_warn_mode_returns_zero_with_violations(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml(mode="warn"))
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "bad.yml").write_text(_workflow_with_retention(14))
    rc = mod.main(["--spec", str(spec_path), "--workflows-dir", str(wf_dir)])
    captured = capsys.readouterr()
    assert rc == 0  # warn mode does not fail
    assert "::warning::" in captured.err
    assert "mode=warn" in captured.err


def test_fail_mode_returns_one_with_violations(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml(mode="fail"))
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "bad.yml").write_text(_workflow_with_retention(14))
    rc = mod.main(["--spec", str(spec_path), "--workflows-dir", str(wf_dir)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "::error::" in captured.err


def test_strict_flag_overrides_warn_mode(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml(mode="warn"))
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "bad.yml").write_text(_workflow_with_retention(14))
    rc = mod.main(
        [
            "--spec",
            str(spec_path),
            "--workflows-dir",
            str(wf_dir),
            "--strict",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "::error::" in captured.err


def test_aligned_workflows_pass(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml(mode="fail"))
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    (wf_dir / "a.yml").write_text(_workflow_with_retention(7))
    (wf_dir / "b.yml").write_text(_workflow_with_retention(30))
    rc = mod.main(["--spec", str(spec_path), "--workflows-dir", str(wf_dir)])
    assert rc == 0
    assert "aligned" in capsys.readouterr().err


def test_silent_zero_warning_for_empty_dir(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    wf_dir = tmp_path / "workflows"
    wf_dir.mkdir()
    rc = mod.main(["--spec", str(spec_path), "--workflows-dir", str(wf_dir)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Collected upload steps (workflows=0, steps=0)" in captured.err
    assert "::warning::" in captured.err


def test_missing_spec_returns_two(mod, tmp_path: Path, capsys):
    rc = mod.main(["--spec", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert "spec missing" in capsys.readouterr().err


def test_malformed_spec_returns_two(mod, tmp_path: Path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("[meta\nnot toml")
    rc = mod.main(["--spec", str(bad)])
    assert rc == 2
    assert "spec malformed" in capsys.readouterr().err


def test_invalid_mode_returns_two(mod, tmp_path: Path, capsys):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml().replace('mode = "warn"', 'mode = "bogus"'))
    rc = mod.main(["--spec", str(spec_path)])
    assert rc == 2
    assert "mode must be" in capsys.readouterr().err


def test_real_workflows_baseline_runs(mod, capsys: pytest.CaptureFixture):
    """The committed spec + real workflows execute without crashing.

    Today's baseline contains 6 pre-existing violations (4× 14d, 1× 5d,
    1× 365d) that were captured before this gate existed. The spec sits
    at mode=warn so this MUST exit 0 even with those violations; the
    flip to mode=fail happens in a follow-up sweep PR.
    """
    rc = mod.main([])
    assert rc == 0, "warn mode must not fail; flip to mode=fail in a future PR"
    captured = capsys.readouterr()
    assert "Collected upload steps" in captured.err
