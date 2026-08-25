"""Unit tests for scripts/check_ruff_version_sync.py.

The regression these cover: a pin site listed in `sites` but yielding no
match used to be skipped silently. `.github/workflows/ci.yml` sat in the
list for three months after PR #462 (`36e40904`) deleted its ruff job, and
the gate printed "OK all sites pin ruff==X" while checking one site fewer
than it advertised — the gate would have gone green precisely when the pin
it guards disappeared.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_ruff_version_sync.py"

PRE_COMMIT = """\
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v{ver}
    hooks:
      - id: ruff
"""

PYTHON_LINT = """\
name: Python Linting
jobs:
  ruff:
    steps:
      - run: |
          pip install ruff=={ver}
"""

PYPROJECT = """\
[dependency-groups]
dev = ["ruff=={ver}"]
test = ["ruff=={ver}"]
quality = ["ruff=={ver}"]
"""


@pytest.fixture(scope="module")
def mod():
    # Ensure platform_utils is importable from scripts/
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("check_ruff_version_sync", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_repo(
    root: Path,
    *,
    pre_commit: str | None,
    python_lint: str | None,
    pyproject: str | None,
) -> None:
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    if pre_commit is not None:
        (root / ".pre-commit-config.yaml").write_text(pre_commit, encoding="utf-8")
    if python_lint is not None:
        (root / ".github/workflows/python-lint.yml").write_text(
            python_lint, encoding="utf-8"
        )
    if pyproject is not None:
        (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")


def _run(mod, root: Path) -> int:
    original = mod.REPO_ROOT
    mod.REPO_ROOT = root
    try:
        return mod.main()
    finally:
        mod.REPO_ROOT = original


def test_all_sites_agree_passes(mod, tmp_path, capsys):
    _write_repo(
        tmp_path,
        pre_commit=PRE_COMMIT.format(ver="0.15.15"),
        python_lint=PYTHON_LINT.format(ver="0.15.15"),
        pyproject=PYPROJECT.format(ver="0.15.15"),
    )
    assert _run(mod, tmp_path) == 0
    out = capsys.readouterr().out
    assert "Found 5 ruff pin site(s)" in out
    assert "OK all sites pin ruff==0.15.15" in out


def test_drift_between_sites_fails(mod, tmp_path, capsys):
    _write_repo(
        tmp_path,
        pre_commit=PRE_COMMIT.format(ver="0.15.15"),
        python_lint=PYTHON_LINT.format(ver="0.15.12"),  # drift
        pyproject=PYPROJECT.format(ver="0.15.15"),
    )
    assert _run(mod, tmp_path) == 1
    err = capsys.readouterr().err
    assert "DRIFT" in err
    assert "All 5 sites" in err


def test_vanished_pin_is_a_hard_failure(mod, tmp_path, capsys):
    """A site whose pin line disappears must fail, not silently drop out.

    Before EXPECTED_PIN_COUNT this returned 0 with "OK all sites pin ...".
    """
    _write_repo(
        tmp_path,
        pre_commit=PRE_COMMIT.format(ver="0.15.15"),
        # File exists (so the path.exists() guard does not fire) but the
        # `pip install ruff==` line is gone — exactly what happened to
        # ci.yml in PR #462.
        python_lint="name: Python Linting\njobs:\n  ruff:\n    steps:\n      - run: echo hi\n",
        pyproject=PYPROJECT.format(ver="0.15.15"),
    )
    assert _run(mod, tmp_path) == 1
    err = capsys.readouterr().err
    assert "pin site inventory mismatch" in err
    assert "python-lint.yml: expected 1 ruff pin(s), found 0" in err


def test_extra_pyproject_entry_is_a_hard_failure(mod, tmp_path, capsys):
    """A 4th pyproject entry means a dependency group was added unnoticed."""
    _write_repo(
        tmp_path,
        pre_commit=PRE_COMMIT.format(ver="0.15.15"),
        python_lint=PYTHON_LINT.format(ver="0.15.15"),
        pyproject=PYPROJECT.format(ver="0.15.15") + 'extra = ["ruff==0.15.15"]\n',
    )
    assert _run(mod, tmp_path) == 1
    err = capsys.readouterr().err
    assert "pyproject.toml: expected 3 ruff pin(s), found 4" in err


def test_missing_file_still_reported(mod, tmp_path, capsys):
    _write_repo(
        tmp_path,
        pre_commit=PRE_COMMIT.format(ver="0.15.15"),
        python_lint=None,  # file absent entirely
        pyproject=PYPROJECT.format(ver="0.15.15"),
    )
    assert _run(mod, tmp_path) == 1
    assert "python-lint.yml" in capsys.readouterr().err


def test_real_repo_is_in_sync(mod, capsys):
    """The checked-in repo must satisfy its own gate."""
    assert _run(mod, REPO_ROOT) == 0
    assert "OK all sites pin ruff==" in capsys.readouterr().out
