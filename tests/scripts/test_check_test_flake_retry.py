"""Unit tests for scripts/check_test_flake_retry.py (M2 T-008)."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_test_flake_retry.py"


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_test_flake_retry",
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


def _spec_toml(
    python_status: str = "proposed",
    retry_max: int = 2,
) -> str:
    return textwrap.dedent(f"""
        [meta]
        spec_version = 1
        applies_to = ["python", "rust", "go", "csharp"]
        forward_compat_policy = "strict"
        direction = "pre-impl"
        retry_count_max = {retry_max}

        [python]
        status = "{python_status}"
        package = "pytest-rerunfailures"
        ci_flag = "--reruns 1"

        [rust]
        status = "proposed"
        package = "cargo-nextest"
        ci_flag = "--retries 2"

        [go]
        status = "proposed"
        package = "gotestsum"
        ci_flag = "--rerun-fails=2"

        [csharp]
        status = "proposed"
        package = "Xunit.RetryAttribute"
        ci_flag = "[Retry(2)]"

        [[invariants]]
        name = "no-blanket-retry"
        description = "x"

        [[invariants]]
        name = "retry-count-max-2"
        description = "x"

        [[invariants]]
        name = "ci-only-retry"
        description = "x"
    """)


def test_real_spec_aligned(mod, capsys: pytest.CaptureFixture):
    """Committed spec + real repository config must align."""
    rc = mod.main([])
    captured = capsys.readouterr()
    assert rc == 0, f"Real repo failed unexpectedly:\n{captured.err}"
    # 8 runtimes after the WASM/C++/Kotlin/Swift extension; python is the
    # only `phase-1` entry so enforced=1.
    assert "Collected retry policies (runtimes=8" in captured.err


def test_check_python_proposed_phase_skips_impl_check(
    mod,
    tmp_path: Path,
):
    """status=proposed only validates shape; no pyproject/workflow check."""
    spec_text = _spec_toml(python_status="proposed")
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(spec_text)
    spec = mod.load_spec(spec_path)
    errors = mod.check_python(
        spec["python"],
        retry_max=2,
        pyproject_path=tmp_path / "nonexistent.toml",
        workflow_path=tmp_path / "nonexistent.yml",
    )
    assert errors == []


def test_check_python_phase1_requires_dep(mod, tmp_path: Path):
    """status=phase-1 with missing pyproject dep yields an error."""
    spec_text = _spec_toml(python_status="phase-1")
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(spec_text)
    spec = mod.load_spec(spec_path)
    py = tmp_path / "pyproject.toml"
    py.write_text("[project]\nname = 'x'\n")  # no rerunfailures
    wf = tmp_path / "wf.yml"
    wf.write_text("pytest --reruns 1\n")
    errors = mod.check_python(
        spec["python"],
        retry_max=2,
        pyproject_path=py,
        workflow_path=wf,
    )
    assert any("pytest-rerunfailures" in e for e in errors)


def test_check_python_phase1_requires_workflow_flag(mod, tmp_path: Path):
    spec_text = _spec_toml(python_status="phase-1")
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(spec_text)
    spec = mod.load_spec(spec_path)
    py = tmp_path / "pyproject.toml"
    py.write_text("'pytest-rerunfailures>=14.0'\n")
    wf = tmp_path / "wf.yml"
    wf.write_text("pytest tests/\n")  # no --reruns
    errors = mod.check_python(
        spec["python"],
        retry_max=2,
        pyproject_path=py,
        workflow_path=wf,
    )
    assert any("--reruns" in e for e in errors)


def test_check_python_rejects_excess_reruns(mod, tmp_path: Path):
    """invariant retry-count-max-2: --reruns 3 must fail even at proposed."""
    spec_text = _spec_toml(python_status="phase-1")
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(spec_text)
    spec = mod.load_spec(spec_path)
    py = tmp_path / "pyproject.toml"
    py.write_text("'pytest-rerunfailures>=14.0'")
    wf = tmp_path / "wf.yml"
    wf.write_text("pytest --reruns 5\n")
    errors = mod.check_python(
        spec["python"],
        retry_max=2,
        pyproject_path=py,
        workflow_path=wf,
    )
    assert any("retry-count-max-2" in e for e in errors)


def test_check_python_accepts_reruns_within_limit(mod, tmp_path: Path):
    spec_text = _spec_toml(python_status="phase-1")
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(spec_text)
    spec = mod.load_spec(spec_path)
    py = tmp_path / "pyproject.toml"
    py.write_text("'pytest-rerunfailures>=14.0'")
    wf = tmp_path / "wf.yml"
    wf.write_text("pytest --reruns 1 --reruns 2\n")
    errors = mod.check_python(
        spec["python"],
        retry_max=2,
        pyproject_path=py,
        workflow_path=wf,
    )
    assert errors == []


def test_check_proposed_runtime_validates_shape(mod):
    errors = mod.check_proposed_runtime(
        "rust",
        {"status": "proposed"},  # missing package + ci_flag
    )
    assert any("package" in e for e in errors)
    assert any("ci_flag" in e for e in errors)


def test_full_check_passes_for_well_formed_spec(mod, tmp_path: Path):
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(_spec_toml())
    spec = mod.load_spec(spec_path)
    errors, seen, enforced = mod.check(spec)
    assert seen == 4
    assert enforced == 0  # all proposed
    # The python branch will probe the REAL repo paths via module-level
    # PYTHON_PYPROJECT — but status=proposed skips those checks, so
    # the only error candidate is invariants.
    assert errors == [], f"Unexpected errors: {errors}"


def test_full_check_flags_missing_runtime_section(mod, tmp_path: Path):
    body = _spec_toml().replace(
        '[rust]\nstatus = "proposed"\npackage = "cargo-nextest"\nci_flag = "--retries 2"\n',
        "",
    )
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(body)
    spec = mod.load_spec(spec_path)
    errors, _, _ = mod.check(spec)
    assert any("[rust] section missing" in e for e in errors), (
        f"Expected [rust] section error, got: {errors}"
    )


def test_full_check_flags_missing_invariant(mod, tmp_path: Path):
    body = _spec_toml().replace(
        '[[invariants]]\nname = "ci-only-retry"\ndescription = "x"\n',
        "",
    )
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(body)
    spec = mod.load_spec(spec_path)
    errors, _, _ = mod.check(spec)
    assert any("ci-only-retry" in e for e in errors), (
        f"Expected ci-only-retry error, got: {errors}"
    )


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


def test_silent_zero_warning_when_applies_to_empty(
    mod,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    body = textwrap.dedent("""
        [meta]
        spec_version = 1
        applies_to = []
        forward_compat_policy = "strict"
        direction = "pre-impl"
        retry_count_max = 2

        [[invariants]]
        name = "no-blanket-retry"
        description = ""

        [[invariants]]
        name = "retry-count-max-2"
        description = ""

        [[invariants]]
        name = "ci-only-retry"
        description = ""
    """)
    spec_path = tmp_path / "spec.toml"
    spec_path.write_text(body)
    rc = mod.main(["--spec", str(spec_path)])
    captured = capsys.readouterr()
    # empty applies_to is not itself a violation (invariants still pass),
    # but the silent-zero defensive log MUST fire.
    assert rc == 0
    assert "Collected retry policies (runtimes=0" in captured.err
    assert "::warning::" in captured.err
