"""Tests for piper_train.tools.measure_comb_artifacts (E-4 コム/残差 autocorr).

canonical 数式の出典: ``scripts/zs-quality-anatomy/comb_check.py``。本ファイルの
数値閾値はすべて canonical 数式の再現実装に同一の合成信号を通した実測で事前検証
済み (各 assert の導出コメント参照)。

実測 baseline (comb_check.py): r2 合成 +4.1〜4.7dB / GT 0.65-0.76dB、
autocorr r2 0.10-0.24 / GT 0.006-0.13。合成信号でこの分離の機序を pin する。

教訓① (絶対): 対象モジュールの全指標は評価専用 (EVAL-ONLY)。学習 loss /
reward / 動的サンプル選別への流用は docs/spec/zs-eval-contract.md §2 禁止事項 4
で恒久禁止。本テストは「測る数学」を pin するだけで、pass/fail 判定 (事前登録
閾値) はツールに実装しない (測定と判定の分離)。

ヘルパは test_measure_band_noise.py / test_measure_prosody.py と共有ヘルパへ
昇格せず各テストファイルに複製する方針 (テスト間の暗黙結合を避ける)。
SR=22050、seed 固定。
"""

from __future__ import annotations

import numpy as np
import pytest

from piper_train.tools.measure_comb_artifacts import comb_metrics


SR = 22050
N_FFT = 2048
BIN_HZ = SR / N_FFT  # 10.7666015625 Hz/bin
# 測定格子: bin index 16k (= 172.265625 Hz = SR/128 の整数倍) のうち 4-8.5kHz。
# comb_check.py L42-45 の `372 <= g <= 790` (16 の倍数) と同一の 26 bins。
GRID_BINS = tuple(range(384, 785, 16))


# ---------------------------------------------------------------------------
# 合成信号ヘルパ
# ---------------------------------------------------------------------------


def _white_noise(duration: float = 3.0, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(SR * duration))


def _grid_tones(
    duration: float = 3.0,
    amp: float = 0.5,
    shift_bins: int = 0,
    seed: int = 0,
) -> np.ndarray:
    """白色雑音 + 測定格子上の純音列 (フレーム格子コムアーティファクトの模擬)。

    amp=0.5 で per-bin トーン SNR ≈ +19dB (hann 窓 n_fft=2048: トーン bin パワー
    (amp·N/4)² vs 雑音 bin パワー σ²·(3/8)·N → 341·amp²)。shift_bins=8 は半格子
    (+86.13Hz) シフト = peak 窓 (中心±1bin=±10.8Hz) の完全に外。
    """
    t = np.arange(int(SR * duration)) / SR
    wav = _white_noise(duration, seed)
    for g in GRID_BINS:
        f = (g + shift_bins) * BIN_HZ
        wav = wav + amp * np.sin(2 * np.pi * f * t + 0.1 * g)
    return wav


def _tiled_noise(period: int, duration: float = 3.0, seed: int = 3) -> np.ndarray:
    """period サンプルの雑音ブロックをタイル (完全周期信号、>4kHz 成分を含む)。

    hop=256 のフレーム格子アーティファクト (がびがびの機序) の理想化モデル。
    LTI highpass を通しても周期性は保存されるため ac[period] → 1 に漸近する。
    """
    block = np.random.default_rng(seed).standard_normal(period)
    reps = int(np.ceil(SR * duration / period))
    return np.tile(block, reps)[: int(SR * duration)]


def _harmonic_voice(
    duration: float = 1.0,
    f0: float = 150.0,
    n_harmonics: int = 60,
    rolloff_db_per_octave: float = 12.0,
) -> np.ndarray:
    """F0 の倍音列で「クリーンな有声音」を合成 (高域は自然減衰)。

    test_measure_band_noise.py の同名ヘルパの複製 (byte 同等のロジック)。
    """
    t = np.arange(int(SR * duration)) / SR
    wav = np.zeros_like(t)
    for k in range(1, n_harmonics + 1):
        f = k * f0
        if f >= SR / 2:
            break
        gain = 10 ** (-rolloff_db_per_octave * np.log2(f / f0) / 20)
        wav += gain * np.sin(2 * np.pi * f * t)
    return (wav / np.abs(wav).max() * 0.5).astype(np.float32)


def _assert_tree_equal(a, b, path: str = "$") -> None:
    """dict / list / ndarray / scalar / None を再帰的に厳密比較 (NaN==NaN 扱い)。"""
    if isinstance(a, dict):
        assert isinstance(b, dict), f"{path}: type mismatch {type(b)}"
        assert set(a) == set(b), f"{path}: key mismatch {set(a) ^ set(b)}"
        for k in a:
            _assert_tree_equal(a[k], b[k], f"{path}.{k}")
    elif a is None:
        assert b is None, f"{path}: {b!r} != None"
    elif isinstance(a, str):
        assert a == b, f"{path}: {a!r} != {b!r}"
    else:
        np.testing.assert_array_equal(np.asarray(a), np.asarray(b), err_msg=path)


# ---------------------------------------------------------------------------
# E-4: コムメトリクス
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCombMetrics:
    """SR/128 格子コム超過 + >4kHz 残差 autocorr (がびがびのゲーム不能量)。"""

    def test_comb_excess_on_grid_tones_detected(self):
        """格子周波数上の純音列 → 大きな正のコム超過 (検出能力の pin)。

        導出: per-bin トーン SNR ≈ +19dB (_grid_tones docstring) → peak はトーン
        支配 / neighbor median は雑音床 → 超過はトーン SNR に漸近。canonical 再現
        での実測 19.4dB。閾値 6.0dB は仕様 §6.1 の登録値 (v10b 事前登録 gate
        1.5dB の 4 倍マージン)。
        """
        m_tones = comb_metrics(_grid_tones(), SR)
        m_noise = comb_metrics(_white_noise(), SR)
        assert m_tones is not None and m_noise is not None
        assert m_tones["comb_excess_db"] > 6.0
        # noise-only に対し +5dB 以上の分離 (仕様 §6.1)。実測 19.4 vs 0.4 dB。
        assert m_tones["comb_excess_db"] > m_noise["comb_excess_db"] + 5.0

    def test_white_noise_excess_near_zero(self):
        """白色雑音 → ~0dB (dB スケールのゼロ点校正)。

        導出: Pm は ~258 フレーム平均で per-bin 分散が小さく、max-of-3 /
        median-of-10 の推定バイアスは +0.2〜0.4dB 程度 (χ² 統計)。canonical
        再現での実測 0.41dB、GT 実波形も 0.65-0.76dB。閾値 1.0dB。
        """
        m = comb_metrics(_white_noise(), SR)
        assert m is not None
        assert abs(m["comb_excess_db"]) < 1.0

    def test_off_grid_tones_do_not_trip(self):
        """半格子 (+8 bins = +86.13Hz) シフトした同一トーン列 → 超過なし。

        格子選択性の証明 (無関係なトーンで偽陽性にならない)。トーンは peak 窓
        (中心±1bin=±10.8Hz) の外、neighbor 窓 (±4〜8bin) に落ちるが median は
        雑音床のまま。canonical 再現での実測 -0.07dB。閾値 1.5dB (仕様 §6.1)。
        """
        m = comb_metrics(_grid_tones(shift_bins=8), SR)
        assert m is not None
        assert abs(m["comb_excess_db"]) < 1.5

    def test_comb_excess_harmonic_voice_low(self):
        """非格子 F0 の調波のみの合成音声 → 低い (格子と調波の混同がない)。

        f0=260Hz: 4-8.6kHz 内の全倍音 260n と格子 172.266k の最小距離 25.6Hz
        (2.4 bins) で peak 窓 (±1bin) の外 (f0 候補走査で事前検証。150/200/210/
        220/240/250Hz は最小距離 <5Hz で不適)。微小白色床 (-34dB) は neighbor
        median を安定させる breathiness 模擬。canonical 再現での実測 0.49dB。
        """
        wav = _harmonic_voice(duration=3.0, f0=260.0).astype(np.float64)
        wav = wav + 0.01 * _white_noise(seed=9)
        m = comb_metrics(wav, SR)
        assert m is not None
        assert abs(m["comb_excess_db"]) < 1.5

    def test_frame_tiled_noise_high_autocorr(self):
        """128 サンプル周期の雑音タイル → lag128 で高い autocorr (検出能力)。

        周期 128 の完全周期信号は highpass (LTI) 後も周期を保ち ac[128]→1。
        canonical 再現での実測 lag128=0.998。ついでに comb_excess も巨大になる
        (線スペクトルが格子と一致、実測 +40dB) — 同一アーティファクトを両指標
        が捉える機序の pin。閾値 0.5 は仕様 §6.1。
        """
        m = comb_metrics(_tiled_noise(128), SR)
        assert m is not None
        assert m["hf_autocorr_lag128"] > 0.5
        assert m["comb_excess_db"] > 6.0

    def test_hf_autocorr_tiled_256_hits_lag256_not_128(self):
        """256 サンプル周期のタイル → lag256 で高く lag128 は低い (lag 特異性)。

        周期 256 の雑音は半周期 (128) では非相関。canonical 再現での実測
        lag256=0.996 / lag128=0.013。
        """
        m = comb_metrics(_tiled_noise(256), SR)
        assert m is not None
        assert m["hf_autocorr_lag256"] > 0.5
        assert m["hf_autocorr_lag128"] < 0.1

    def test_hf_autocorr_white_noise_near_zero(self):
        """白色雑音 → autocorr ~0 (ゼロ点校正)。

        導出: n=66150 で |ac| の 3σ ≈ 3/√n ≈ 0.012 → 閾値 0.03 は 2.5 倍の
        マージン (仕様 §6.1)。canonical 再現での実測 0.0045 / 0.0032。
        """
        m = comb_metrics(_white_noise(), SR)
        assert m is not None
        assert m["hf_autocorr_lag128"] < 0.03
        assert m["hf_autocorr_lag256"] < 0.03


@pytest.mark.unit
class TestCombContract:
    """API 契約 (仕様 §1.2-§1.3): canonical 集合 pin / スケール不変 / 縮退。"""

    def test_grid_bins_match_comb_check(self):
        """測定格子 = comb_check.py の canonical 集合 (26 bins) の pin。"""
        from piper_train.tools.measure_comb_artifacts import GRID_BINS as MODULE_BINS

        assert tuple(MODULE_BINS) == tuple(range(384, 785, 16))
        assert len(MODULE_BINS) == 26

    def test_scale_invariance(self):
        """同一信号 ×0.1 / ×10 → 全 field 一致 (RMS 正規化の pin)。"""
        wav = _grid_tones(duration=2.0)
        base = comb_metrics(wav, SR)
        assert base is not None
        for gain in (0.1, 10.0):
            m = comb_metrics(wav * gain, SR)
            assert m is not None
            for key, value in base.items():
                assert m[key] == pytest.approx(value, abs=1e-9), key

    def test_too_short_returns_none(self):
        """0.5 秒未満 → None (仕様 §1.2 の最短長)。"""
        assert comb_metrics(_white_noise(duration=0.3), SR) is None

    def test_sr_mismatch_raises(self):
        """sr != 22050 は ValueError (silent 二重 resample 防止)。"""
        with pytest.raises(ValueError, match="22050"):
            comb_metrics(_white_noise(duration=1.0), 16000)

    def test_comb_metrics_deterministic(self):
        """同一入力 2 回 → 同一出力 (manifest への数値 pin の前提条件)。"""
        wav = _grid_tones(duration=2.0)
        m1 = comb_metrics(wav, SR)
        m2 = comb_metrics(wav.copy(), SR)
        assert m1 is not None and m2 is not None
        _assert_tree_equal(m1, m2)
