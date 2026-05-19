"""Unit tests for scripts/check_readme_heading_tree.py.

`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #2 由来の multilingual
README heading tree parity validator のテスト。 既存 README が bootstrap
baseline で pass することと、 代表的な drift パターン (H2 count diff /
H2 section の H3 count 大幅乖離 / order divergence) が warning として
検出されることを確認する。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_readme_heading_tree.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_readme_heading_tree", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def test_repo_readmes_pass_with_default_tolerance(mod):
    """既存 README*.md は default ``--h3-tolerance 5`` で pass する (bootstrap baseline)。"""
    warnings = mod.check(
        REPO_ROOT / "README.md",
        [REPO_ROOT / f"README_{lang}.md" for lang in ("DE", "EN", "ES", "FR", "KO", "PT", "ZH")],
        h3_tolerance=5,
        strict_order=False,
    )
    assert warnings == [], f"existing READMEs must be clean; got: {warnings}"


def test_h2_count_mismatch_is_warning(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text("# Title\n\n## A\n\n## B\n", encoding="utf-8")
    translation = tmp_path / "README_EN.md"
    translation.write_text("# Title\n\n## A\n", encoding="utf-8")
    warnings = mod.check(canonical, [translation], h3_tolerance=5, strict_order=False)
    assert any("H2 count" in w for w in warnings)


def test_h3_drift_within_tolerance_no_warning(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text(
        "# Title\n\n## A\n\n### a1\n\n### a2\n\n## B\n", encoding="utf-8"
    )
    translation = tmp_path / "README_EN.md"
    # ±2 within tolerance=2
    translation.write_text(
        "# Title\n\n## A\n\n### a1\n\n### a2\n\n### a3\n\n### a4\n\n## B\n",
        encoding="utf-8",
    )
    warnings = mod.check(canonical, [translation], h3_tolerance=2, strict_order=False)
    assert warnings == []


def test_h3_drift_exceeding_tolerance_is_warning(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text("# Title\n\n## A\n\n## B\n", encoding="utf-8")
    translation = tmp_path / "README_EN.md"
    # H2 A has +5 H3
    translation.write_text(
        "# Title\n\n## A\n\n### a1\n\n### a2\n\n### a3\n\n### a4\n\n### a5\n\n## B\n",
        encoding="utf-8",
    )
    warnings = mod.check(canonical, [translation], h3_tolerance=2, strict_order=False)
    assert any("H2 section #1" in w for w in warnings)


def test_strict_order_divergence_is_warning(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text(
        "# Title\n\n## A\n\n### a1\n\n## B\n\n### b1\n", encoding="utf-8"
    )
    translation = tmp_path / "README_EN.md"
    # swap order of H3 between sections (a1 missing, b1 under A)
    translation.write_text(
        "# Title\n\n## A\n\n## B\n\n### b1\n", encoding="utf-8"
    )
    warnings = mod.check(canonical, [translation], h3_tolerance=2, strict_order=True)
    assert any("heading order differs" in w for w in warnings)


def test_code_fence_headings_ignored(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text(
        "# Title\n\n## Real\n\n```\n## not a heading\n```\n", encoding="utf-8"
    )
    translation = tmp_path / "README_EN.md"
    translation.write_text(
        "# Title\n\n## Real\n\n```\n### also not\n```\n", encoding="utf-8"
    )
    warnings = mod.check(canonical, [translation], h3_tolerance=0, strict_order=True)
    assert warnings == []


def test_missing_translation_is_warning(mod, tmp_path: Path):
    canonical = tmp_path / "README.md"
    canonical.write_text("# Title\n\n## A\n", encoding="utf-8")
    missing = tmp_path / "README_XX.md"  # does not exist
    warnings = mod.check(canonical, [missing], h3_tolerance=5, strict_order=False)
    assert any("translation missing" in w for w in warnings)


def test_extract_heading_pattern_basic(mod, tmp_path: Path):
    p = tmp_path / "x.md"
    p.write_text(
        "# H1 ignored\n\n## h2\n\n### h3\n\n#### h4\n\n##### h5 ignored\n",
        encoding="utf-8",
    )
    assert mod.extract_heading_pattern(p) == [2, 3, 4]


def test_h3_counts_per_h2(mod):
    # [2, 3, 3, 2, 3, 2] → [2, 1, 0]
    assert mod.h3_counts_per_h2([2, 3, 3, 2, 3, 2]) == [2, 1, 0]
