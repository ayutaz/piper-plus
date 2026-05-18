"""Unit tests for scripts/check_migration_xref.py (M1.2)."""

from __future__ import annotations

import importlib.util
import sys
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_migration_xref.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "migration_xref"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_migration_xref", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def xref():
    return _load_module()


@pytest.fixture
def stage(tmp_path: Path):
    """Stage a CHANGELOG fixture + populate docs/migration/ from the fixture
    set so the script's path resolution treats ``tmp_path`` as the repo root."""
    def _stage(changelog_fixture: str, doc_fixtures: list[str] | None = None) -> Path:
        (tmp_path / "docs" / "migration").mkdir(parents=True, exist_ok=True)
        for d in doc_fixtures or []:
            target_name = d.removeprefix("doc_")
            shutil.copy(FIXTURES / d, tmp_path / "docs" / "migration" / target_name)
        cl = tmp_path / "CHANGELOG.md"
        shutil.copy(FIXTURES / changelog_fixture, cl)
        return cl
    return _stage


def _run(xref, changelog: Path, root: Path, *flags) -> int:
    args = xref.build_parser().parse_args(
        ["--changelog", str(changelog), "--root", str(root), *flags]
    )
    return xref.main([
        "--changelog", str(changelog),
        "--root", str(root),
        *flags,
    ])


def test_complete_pass(xref, stage, tmp_path, capsys):
    cl = stage("changelog_pass.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "OK" in captured.out


def test_missing_link_fails(xref, stage, tmp_path, capsys):
    cl = stage("changelog_missing_link.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "no docs/migration" in captured.err


def test_missing_file_fails(xref, stage, tmp_path, capsys):
    cl = stage("changelog_missing_file.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "migration doc not found" in captured.err


def test_anchor_mismatch_fails(xref, stage, tmp_path, capsys):
    cl = stage("changelog_anchor_mismatch.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "anchor not found" in captured.err
    assert "bar-removal" in captured.err


def test_no_anchor_passes_by_default(xref, stage, tmp_path, capsys):
    cl = stage("changelog_no_anchor.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0


def test_no_anchor_fails_in_strict_mode(xref, stage, tmp_path, capsys):
    cl = stage("changelog_no_anchor.md", ["doc_v1.12-to-v1.13.md"])
    rc = _run(xref, cl, tmp_path, "--strict-anchor")
    captured = capsys.readouterr()
    assert rc == 1
    assert "strict-anchor" in captured.err


def test_no_breaking_section_skips(xref, stage, tmp_path, capsys):
    cl = stage("changelog_no_breaking.md")
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "skip" in captured.out


def test_versioned_breaking_is_ignored(xref, stage, tmp_path, capsys):
    """Old release sections under ``## [1.x]`` must not be re-validated when
    the [Unreleased] section is empty of Breaking entries."""
    cl = stage("changelog_versioned_only.md")
    rc = _run(xref, cl, tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "skip" in captured.out


def test_slugify_handles_unicode(xref):
    assert xref.slugify("Foo Bar") == "foo-bar"
    assert xref.slugify("foo_bar") == "foo-bar"
    assert xref.slugify("`Generator` class removal") == "generator-class-removal"
    # The actual GitHub slug collapses runs of `-` differently per renderer;
    # this assertion pins our implementation's deterministic behaviour so
    # `\s+` runs (whether or not they used to contain `→`) collapse to a
    # single dash. Drift here is OK as long as the fixture-side migration doc
    # uses the matching anchor.
    assert xref.slugify("v1.12 → v1.13 migration guide") == "v112-v113-migration-guide"


def test_parse_extracts_continuation_lines(xref):
    text = (
        "## [Unreleased]\n"
        "\n"
        "### Breaking\n"
        "\n"
        "- first entry [a](docs/migration/v1.12-to-v1.13.md#x)\n"
        "  continuation line\n"
        "- second entry [b](docs/migration/v1.12-to-v1.13.md#y)\n"
    )
    entries = xref.parse_unreleased_breaking(text)
    assert len(entries) == 2
    assert "continuation line" in entries[0].body
