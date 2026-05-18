"""Unit tests for scripts/check_changelog_format.py.

`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #1 由来の keep-a-changelog
形式 validator のテスト。 既存 CHANGELOG.md が pass することと、 代表的な
violation パターン (H1 欠落 / Unreleased 欠落 / version 順序逆転 / date 形式
不正 / section 重複) が error として検出されることを確認する。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_changelog_format.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_changelog_format", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def test_repo_changelog_passes(mod):
    """piper-plus 自身の CHANGELOG.md は error 0 でなければならない (bootstrap baseline)。"""
    errors, _warnings = mod.check(REPO_ROOT / "CHANGELOG.md")
    assert errors == [], f"existing CHANGELOG.md must be clean; errors: {errors}"


def test_missing_h1_is_error(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("Not a changelog header\n\n## [Unreleased]\n", encoding="utf-8")
    errors, _ = mod.check(cl)
    assert any("expected '# Changelog'" in e for e in errors)


def test_missing_unreleased_is_error(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n- foo\n", encoding="utf-8"
    )
    errors, _ = mod.check(cl)
    assert any("missing '## [Unreleased]'" in e for e in errors)


def test_unreleased_after_release_is_error(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n- foo\n\n## [Unreleased]\n",
        encoding="utf-8",
    )
    errors, _ = mod.check(cl)
    assert any("must precede the first versioned release" in e for e in errors)


def test_bad_date_format_is_error(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026/01/01\n\n### Added\n- foo\n",
        encoding="utf-8",
    )
    errors, _ = mod.check(cl)
    assert any("does not match" in e for e in errors)


def test_version_order_descending_required(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n- foo\n\n"
        "## [2.0.0] - 2026-02-01\n\n### Added\n- bar\n",
        encoding="utf-8",
    )
    errors, _ = mod.check(cl)
    assert any("descending order" in e for e in errors)


def test_unknown_section_is_warning_not_error(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Wibble\n- foo\n",
        encoding="utf-8",
    )
    errors, warnings = mod.check(cl)
    assert errors == []
    assert any("not in the allowed list" in w for w in warnings)


def test_duplicate_section_within_release_is_warning(mod, tmp_path: Path):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- foo\n\n### Added\n- bar\n",
        encoding="utf-8",
    )
    errors, warnings = mod.check(cl)
    assert errors == []
    assert any("repeated within release" in w for w in warnings)


def test_terminator_section_skips_version_check(mod, tmp_path: Path):
    """``## Older Releases`` 以降の構造は version check 範囲外。"""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n- foo\n\n"
        "## Older Releases\n\n"
        "Free-form prose with [arbitrary] formatting that should NOT trip the H2 check.\n",
        encoding="utf-8",
    )
    errors, _ = mod.check(cl)
    assert errors == []


def test_extended_section_with_suffix_allowed(mod, tmp_path: Path):
    """``### Limitations (...)`` のような suffix 付きセクションは許容。"""
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Limitations (v1.13.0 iOS xcframework)\n- foo\n",
        encoding="utf-8",
    )
    errors, warnings = mod.check(cl)
    assert errors == []
    assert not any("not in the allowed list" in w for w in warnings)
