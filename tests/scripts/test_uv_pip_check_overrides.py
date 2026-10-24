"""Tests for scripts/uv_pip_check_overrides.py.

`uv pip check` reports the Pillow override in environments/webui as an
incompatibility (gradio requires `pillow<13.0`). The wrapper accepts exactly
the incompatibilities that a declared override explains and fails on the rest.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "uv_pip_check_overrides.py"


@pytest.fixture(scope="module")
def mod():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("uv_pip_check_overrides", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


OVERRIDES = ["pillow>=13.0.0"]
HEADER = "Using Python 3.13.13 environment at: .venv\nChecked 77 packages in 110ms\n"


def test_clean_environment_passes(mod):
    out = HEADER + "All installed packages are compatible\n"
    assert mod.unexplained(out, OVERRIDES) == []


def test_override_explains_the_gradio_cap(mod):
    out = HEADER + (
        "Found 1 incompatibility\n"
        "The package `gradio` requires `pillow>=8.0,<13.0`, but `13.0.0` is installed\n"
    )
    assert mod.unexplained(out, OVERRIDES) == []


def test_other_incompatibility_fails(mod):
    out = HEADER + (
        "Found 2 incompatibilities\n"
        "The package `gradio` requires `pillow>=8.0,<13.0`, but `13.0.0` is installed\n"
        "The package `fastapi` requires `starlette<0.50`, but `0.51.0` is installed\n"
    )
    problems = mod.unexplained(out, OVERRIDES)
    assert len(problems) == 1 and "starlette" in problems[0]


def test_override_package_below_the_override_fails(mod):
    """The override must actually be in effect, not just declared."""
    out = HEADER + (
        "Found 1 incompatibility\n"
        "The package `foo` requires `pillow>=14`, but `12.3.0` is installed\n"
    )
    assert len(mod.unexplained(out, OVERRIDES)) == 1


def test_missing_dependency_fails(mod):
    out = HEADER + (
        "Found 1 incompatibility\n"
        "The package `gradio` requires `pillow`, but it's not installed\n"
    )
    assert len(mod.unexplained(out, OVERRIDES)) == 1


def test_unrecognised_report_line_fails(mod):
    """A format change in uv must not turn the check into a silent pass."""
    out = HEADER + "Found 1 incompatibility\nsomething new happened\n"
    assert len(mod.unexplained(out, OVERRIDES)) == 1


def test_reads_overrides_from_pyproject(mod):
    overrides = mod.load_overrides(REPO_ROOT / "environments" / "webui" / "pyproject.toml")
    assert overrides == ["pillow>=13.0.0"]
