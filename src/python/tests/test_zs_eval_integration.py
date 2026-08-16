"""Phase A 契約ゲート統合テスト (再発防止面の登録・配線の存在検証).

zs-prevention gate (scripts/check_zs_prevention_tests.py) の EXPECTED に
Phase A の新指標 (コム / 韻律 / 帯域プロファイル + isolation gate) が登録され、
契約 (docs/spec/zs-eval-contract.md) と pre-commit 配線が揃っていることを pin
する (docs/design/zero-shot-v10b-quality-plan.md §2 E-7/E-8 /
phase_a_spec.md §5.1 §5.3 §5.4)。

教訓① (評価メトリクスの学習流用禁止) の三重固定:
(i) モジュール docstring の EVAL-ONLY マーカー / (ii) 契約 §2 禁止事項 4 /
(iii) pre-commit gate — の (ii)(iii) 側の登録をここで検証する。
((i) と gate 本体の挙動は test_zs_metric_isolation_gate.py が担当。)
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PREVENTION_PATH = REPO_ROOT / "scripts" / "check_zs_prevention_tests.py"
CONTRACT_PATH = REPO_ROOT / "docs" / "spec" / "zs-eval-contract.md"
PRECOMMIT_PATH = REPO_ROOT / ".pre-commit-config.yaml"


@pytest.fixture(scope="module")
def prevention():
    """prevention gate script を module として load する (非汎用 module 名)。"""
    spec = importlib.util.spec_from_file_location(
        "zs_prevention_gate_module", PREVENTION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {PREVENTION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
class TestPreventionGateExpected:
    """§5.4: EXPECTED への新指標シンボル登録 (黙った弱体化の検出面を先に固定)。"""

    def test_new_metric_modules_registered(self, prevention):
        exp = prevention.EXPECTED

        comb = exp["src/python/piper_train/tools/measure_comb_artifacts.py"]
        assert "def comb_metrics" in comb
        assert "EVAL-ONLY" in comb

        pros = exp["src/python/piper_train/tools/measure_prosody.py"]
        assert "def prosody_stats" in pros
        assert "def prosody_delta" in pros
        assert "EVAL-ONLY" in pros

        band = exp["src/python/piper_train/tools/measure_band_noise.py"]
        assert "def voiced_high_band_excess" in band  # 旧指標の互換維持
        assert "def band_profile" in band  # E-1 帯域ベクトル
        assert "EVAL-ONLY" in band

    def test_isolation_gate_registered(self, prevention):
        gate = prevention.EXPECTED["scripts/check_zs_metric_isolation.py"]
        assert "piper_train.vits" in gate  # 隔離 gate 本体の存在ガード

    def test_new_prevention_tests_registered(self, prevention):
        exp = prevention.EXPECTED

        comb_t = exp["src/python/tests/test_measure_comb_artifacts.py"]
        for sym in (
            "def test_off_grid_tones_do_not_trip",  # 格子選択性 (偽陽性防止)
            "def test_white_noise_excess_near_zero",  # ゼロ点校正
            "def test_frame_tiled_noise_high_autocorr",  # フレーム格子検出能力
        ):
            assert sym in comb_t, sym

        pros_t = exp["src/python/tests/test_measure_prosody.py"]
        for sym in (
            "def test_vibrato_f0_std_matches_first_principles",
            "def test_flat_f0_near_zero_std",
        ):
            assert sym in pros_t, sym

    def test_eval_and_contract_symbols_extended(self, prevention):
        exp = prevention.EXPECTED

        ev = exp["src/python/piper_train/tools/eval_zs_secs.py"]
        assert "above_ceiling" in ev  # E-7(iii)
        assert "manifest" in ev  # E-5(i)
        # 既存ガード面が残っていること (置換ではなく追加)
        for legacy in (
            "goodhart_flag",
            "require-encoder2",
            "gap_same_minus_cross",
            "cross_utt_secs",
        ):
            assert legacy in ev, legacy

        doc = exp["docs/spec/zs-eval-contract.md"]
        assert "恒久禁止" in doc  # §2 禁止事項 4 (学習流用の恒久禁止)
        assert "above_ceiling_flag" in doc
        assert "same-utt" in doc  # 既存条項の維持


@pytest.mark.unit
class TestContractText:
    """§5.1: 契約本文への Phase A 追記 (禁止事項 4-5 / v3 schema / 音響指標)。"""

    def test_contract_bans_metric_reuse_in_training(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        # 禁止事項 4: 評価メトリクスの学習流用の恒久禁止 + 機械的強制の参照
        assert "学習流用" in text
        assert "check_zs_metric_isolation" in text
        # 禁止事項 5: 素の出力 wav で測る (gate 回避目的の後処理禁止)
        assert "後処理" in text

    def test_contract_defines_v3_schema_and_flags(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "zs-eval-v3" in text
        assert "above_ceiling_flag" in text
        # E-7(ii): SECS↔人間類似の相関上限の注記 (±0.03 未満は判定材料にしない)
        assert "0.03" in text

    def test_contract_registers_acoustic_metrics(self):
        text = CONTRACT_PATH.read_text(encoding="utf-8")
        assert "comb_excess_db" in text  # E-4 コム超過
        assert "prosody_delta" in text  # E-3 韻律記述統計差
        assert "band_profile" in text  # E-1 帯域プロファイル


@pytest.mark.unit
class TestPreCommitWiring:
    """§5.3 / §5.4: gate の pre-commit 配線 (登録漏れ = gate は存在しても走らない)。"""

    def test_isolation_gate_wired(self):
        text = PRECOMMIT_PATH.read_text(encoding="utf-8")
        assert "zs-metric-isolation-gate" in text
        assert "check_zs_metric_isolation.py" in text

    def test_prevention_gate_files_regex_extended(self):
        text = PRECOMMIT_PATH.read_text(encoding="utf-8")
        # 新モジュール / 新テストの変更でも zs-prevention-gate が発火すること
        assert "measure_comb_artifacts" in text
        assert "measure_prosody" in text


@pytest.mark.unit
def test_prevention_gate_full_run_passes():
    """prevention gate 自体が現 repo で green であること。

    EXPECTED 追記 (red) → モジュール/契約の実装 (green) の順序を強制する:
    EXPECTED だけ先に更新した状態では本テストが red になり、シンボル実装まで
    commit できない (実装完了時点で green に戻る)。
    """
    proc = subprocess.run(
        [sys.executable, str(PREVENTION_PATH)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
