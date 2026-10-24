"""Tests for scripts/check_dependency_floors.py (Issue #709)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_dependency_floors.py"


@pytest.fixture(scope="module")
def floors():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("check_dependency_floors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


NLTK = {
    "package": "nltk",
    "minimum": "3.10.4",
    "fixed_advisories": ["GHSA-8mgp-746c-j5xp"],
    "issue": 709,
}


def test_floor_below_minimum_fails(floors):
    files = {"pyproject.toml": 'dependencies = [\n    "nltk>=3.10.0",\n]\n'}
    errors = floors.check(files, [NLTK])
    assert any("pyproject.toml:2" in e and "3.10.0" in e for e in errors)


def test_floor_at_minimum_passes(floors):
    files = {"pyproject.toml": 'dependencies = ["nltk>=3.10.4"]\n'}
    assert floors.check(files, [NLTK]) == []


def test_workflow_pip_install_floor_is_checked(floors):
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        ".github/workflows/x.yml": 'run: pip install inflect "nltk>=3.10.0"\n',
    }
    errors = floors.check(files, [NLTK])
    assert any(".github/workflows/x.yml:1" in e for e in errors)


def test_lock_version_below_minimum_fails(floors):
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        "uv.lock": '[[package]]\nname = "nltk"\nversion = "3.10.3"\n',
    }
    errors = floors.check(files, [NLTK])
    assert any("uv.lock" in e and "3.10.3" in e for e in errors)


def test_lock_version_at_minimum_passes(floors):
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        "uv.lock": '[[package]]\nname = "nltk"\nversion = "3.10.4"\n',
    }
    assert floors.check(files, [NLTK]) == []


def test_lock_recorded_specifier_below_minimum_fails(floors):
    """uv.lock records each member's requirements. A stale record means the
    lock was not regenerated after the floor moved (PR #852: uv 0.12 kept
    `specifier = ">=3.10.0"` for a requirements.txt-driven member, and
    `uv lock --check` on uv 0.13 failed in CI)."""
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        "uv.lock": (
            "[package.metadata]\nrequires-dist = [\n"
            '    { name = "nltk", specifier = ">=3.10.0" },\n'
            '    { name = "nltk", marker = "extra == \'en\'", specifier = ">=3.10.4" },\n'
            "]\n"
        ),
    }
    errors = floors.check(files, [NLTK])
    assert len(errors) == 1
    assert "uv.lock:3" in errors[0] and "3.10.0" in errors[0]


def test_no_floor_site_fails(floors):
    """A gate that finds nothing to check must not pass silently."""
    errors = floors.check({"pyproject.toml": '"numpy>=1.26"\n'}, [NLTK])
    assert any("no floor" in e for e in errors)


def test_floor_in_comment_is_not_a_declaration(floors):
    """History comments name old floors (`旧 floor nltk>=3.9.4`)."""
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        ".github/workflows/x.yml": "        #   旧 floor `nltk>=3.9.4` は範囲の内側\n",
        "src/requirements.txt": "#   nltk>=3.9.4 was the old floor\nnltk>=3.10.4\n",
    }
    assert floors.check(files, [NLTK]) == []


def test_similar_package_name_is_not_matched(floors):
    files = {"pyproject.toml": '"nltk>=3.10.4"\n"nltk-extras>=0.1"\n'}
    assert floors.check(files, [NLTK]) == []


@pytest.mark.parametrize(
    "line",
    [
        "            --ignore-vuln GHSA-8mgp-746c-j5xp",
        "          allow-ghsas: GHSA-8mgp-746c-j5xp",
        "          allow-ghsas: GHSA-aaaa-bbbb-cccc, GHSA-8mgp-746c-j5xp",
    ],
)
def test_suppression_of_fixed_advisory_fails(floors, line: str):
    """Once the floor is above the affected range, keeping the suppression
    only hides a regression to a vulnerable version (Issue #709, #588)."""
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        ".github/workflows/security-audit.yml": line + "\n",
    }
    errors = floors.check(files, [NLTK])
    assert any("GHSA-8mgp-746c-j5xp" in e and "suppress" in e for e in errors)


def test_advisory_mentioned_in_comment_is_allowed(floors):
    files = {
        "pyproject.toml": '"nltk>=3.10.4"\n',
        ".github/workflows/security-audit.yml": (
            "        #   - GHSA-8mgp-746c-j5xp (nltk <= 3.10.3) — 3.10.4 で解除\n"
        ),
    }
    assert floors.check(files, [NLTK]) == []


def test_repository_satisfies_spec(floors):
    """The committed tree must pass the committed spec."""
    spec = floors.load_floors(REPO_ROOT / "docs" / "spec" / "dependency-floors.toml")
    assert {f["package"] for f in spec} >= {"nltk", "joblib"}
    errors = floors.check(floors.collect_files(REPO_ROOT), spec)
    assert errors == []
