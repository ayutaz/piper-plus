"""Unit tests for scripts/check_test_threshold_relaxation.py.

docs/design/zero-shot-noise-root-cause-pqmf.md §4 の再発防止 gate: テストの
数値閾値を「実測に合わせて」緩める変更 (goalpost moving) を staged diff から
検出する。PQMF の受け入れ基準が -90dB → 5dB に緩和されて 15 ヶ月バグが制度化
された事故 (PR #320) を仕組みで遮断するのが目的。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_test_threshold_relaxation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_test_threshold_relaxation", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = _load_module()


def _diff(path: str, old: str, new: str, context: str = "") -> str:
    """Build a minimal unified diff for one changed line."""
    ctx = f" {context}\n" if context else ""
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -10,3 +10,3 @@ def test_x():\n"
        f"{ctx}"
        f"-{old}\n"
        f"+{new}\n"
    )


class TestRelaxationDetected:
    def test_lower_floor_flagged(self):
        """`> 50` → `> 5` (PQMF 事故の再現) は検出される。"""
        d = _diff(
            "src/python/tests/test_pqmf.py",
            "    assert snr_db > 50, f'SNR {snr_db}'",
            "    assert snr_db > 5, f'SNR {snr_db}'",
        )
        v = MOD.check_diff(d)
        assert len(v) == 1
        assert "test_pqmf.py" in v[0]

    def test_higher_ceiling_flagged(self):
        d = _diff(
            "src/python/tests/test_x.py",
            "    assert error < 1e-6",
            "    assert error < 1e-3",
        )
        assert len(MOD.check_diff(d)) == 1

    def test_wider_tolerance_flagged(self):
        d = _diff(
            "tests/scripts/test_y.py",
            "    assert x == pytest.approx(1.0, abs=1e-6)",
            "    assert x == pytest.approx(1.0, abs=1e-2)",
        )
        assert len(MOD.check_diff(d)) == 1

    def test_fewer_places_flagged(self):
        d = _diff(
            "src/python_run/tests/test_z.py",
            "        self.assertAlmostEqual(a, b, places=7)",
            "        self.assertAlmostEqual(a, b, places=3)",
        )
        assert len(MOD.check_diff(d)) == 1


class TestNotFlagged:
    def test_tightening_ok(self):
        """基準を厳しくする方向は通す。"""
        d = _diff(
            "src/python/tests/test_pqmf.py",
            "    assert snr_db > 5",
            "    assert snr_db > 55",
        )
        assert MOD.check_diff(d) == []

    def test_non_test_file_ignored(self):
        d = _diff(
            "src/python/piper_train/vits/models.py",
            "    assert snr_db > 50",
            "    assert snr_db > 5",
        )
        assert MOD.check_diff(d) == []

    def test_justified_relaxation_passes(self):
        d = _diff(
            "src/python/tests/test_pqmf.py",
            "    assert snr_db > 50",
            "    assert snr_db > 30  # threshold-relaxed: canonical kan-bayashi impl also gives 32dB for taps=16",
        )
        assert MOD.check_diff(d) == []

    def test_justification_on_line_above_passes(self):
        path = "src/python/tests/test_pqmf.py"
        d = (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -10,4 +10,5 @@ def test_x():\n"
            "+    # threshold-relaxed: reference impl comparison in PR #999 shows 30dB is correct\n"
            "-    assert snr_db > 50\n"
            "+    assert snr_db > 30\n"
        )
        assert MOD.check_diff(d) == []

    def test_empty_justification_rejected(self):
        d = _diff(
            "src/python/tests/test_pqmf.py",
            "    assert snr_db > 50",
            "    assert snr_db > 5  # threshold-relaxed:",
        )
        assert len(MOD.check_diff(d)) == 1

    def test_unrelated_assert_change_ok(self):
        """構造が変わった assert (数値の対応が取れない) は誤検出しない。"""
        d = _diff(
            "src/python/tests/test_x.py",
            "    assert len(items) > 3",
            "    assert result.status == 'ok'",
        )
        assert MOD.check_diff(d) == []

    def test_new_assert_without_removal_ok(self):
        path = "src/python/tests/test_new.py"
        d = (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            "@@ -0,0 +1,2 @@\n"
            "+def test_new():\n"
            "+    assert snr > 5\n"
        )
        assert MOD.check_diff(d) == []

    def test_operator_direction_change_not_paired(self):
        d = _diff(
            "src/python/tests/test_x.py",
            "    assert x > 10",
            "    assert x < 10",
        )
        assert MOD.check_diff(d) == []


class TestMultiFileDiff:
    def test_violation_attributed_to_correct_file(self):
        """複数ファイル diff で前ファイルの hunk が次ファイルへ漏れない。

        回帰 pin: file 境界 (+++ b/) で hunk を flush しないバグにより、
        2 番目のファイルの緩和が 1 番目のファイル名で報告されていた。
        """
        d = (
            "diff --git a/tests/scripts/test_first.py b/tests/scripts/test_first.py\n"
            "--- a/tests/scripts/test_first.py\n"
            "+++ b/tests/scripts/test_first.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+def helper():\n"
            "+    return 1\n"
            " def test_a():\n"
            "diff --git a/src/python/tests/test_second.py b/src/python/tests/test_second.py\n"
            "--- a/src/python/tests/test_second.py\n"
            "+++ b/src/python/tests/test_second.py\n"
            "@@ -5,3 +5,3 @@ def test_b():\n"
            "-    assert loss < 1e-5\n"
            "+    assert loss < 1e-2\n"
        )
        v = MOD.check_diff(d)
        assert len(v) == 1
        assert "test_second.py" in v[0]
        assert "test_first.py" not in v[0]
