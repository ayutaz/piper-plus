"""Tests for piper_train.tools.measure_comb_hnr (comb-HNR@1-3kHz、A3 直接測定).

背景 (docs/design/zero-shot-v10b-residual-noise-diagnosis.md §1/§8):
がびがきの主犯 A3 (調波間ノイズ充填) は「調波 bin vs 中間 bin の voiced
パワー比」(comb-HNR) で直接測る。v11 harmonic head 設計 §5.3 の実測で
「GT/予測 F0 格子で測ると ±20 cent の系統誤差で崩壊する」罠が確定したため、
**出力自身の F0 トラック (pyin) で測る**プロトコルをテストで pin する
(罠の再発防止 = test_self_track_invariant_under_f0_cent_error)。
"""

from __future__ import annotations

import numpy as np
import pytest

from piper_train.tools import measure_comb_hnr
from piper_train.tools.measure_comb_hnr import (
    DEFAULT_BAND_HZ,
    comb_hnr,
    comb_hnr_at_reference,
    comb_hnr_frames,
    detect_octave_down,
)


SR = measure_comb_hnr.SR_ANALYSIS  # 22050 固定 (診断 doc の全アンカーと同一)


def _harmonic_signal(
    f0: float,
    duration: float = 1.2,
    noise_rms: float = 1e-4,
    seed: int = 0,
    odd_gain: float = 1.0,
) -> np.ndarray:
    """調波信号 + 白色ノイズ床。odd_gain < 1 で period-doubling 型 (奇数倍音弱)。"""
    t = np.arange(int(SR * duration)) / SR
    wav = np.zeros_like(t)
    for k in range(1, 60):
        f = k * f0
        if f >= SR / 2:
            break
        gain = 1.0 / k
        if k % 2 == 1:
            gain *= odd_gain
        wav += gain * np.sin(2 * np.pi * f * t)
    rng = np.random.default_rng(seed)
    wav = wav / (np.sqrt(np.mean(wav**2)) + 1e-12) * 0.1
    return wav + noise_rms * rng.standard_normal(len(t))


@pytest.mark.unit
class TestFirstPrinciples:
    """合成信号での第一原理一致 (dB スケールの絶対保証)。"""

    def test_harmonic_signal_first_principles(self):
        """ノイズパワー ×10 で comb-HNR がちょうど -10dB 動く (比の定義の検証)。

        調波 bin のパワーは調波が支配し、中間 bin は白色ノイズが支配する。
        ノイズ振幅を √10 倍するとノイズパワーは 10 倍 → 比は -10dB。
        """
        base = comb_hnr(_harmonic_signal(220.0, noise_rms=3e-4, seed=1), SR)
        noisy = comb_hnr(
            _harmonic_signal(220.0, noise_rms=3e-4 * np.sqrt(10.0), seed=1), SR
        )
        assert base is not None and noisy is not None
        assert base - noisy == pytest.approx(10.0, abs=1.5)
        # ノイズ床が薄いほど高い (単調性)
        assert base > noisy

    def test_white_noise_near_zero_db(self):
        """白色雑音は調波 bin と中間 bin のパワーが同じ → ~0dB (ゼロ点校正)。

        pyin は白色雑音を voiced と判定しないため、純関数 comb_hnr_frames に
        F0/voiced を注入して測る。
        """
        import librosa

        rng = np.random.default_rng(7)
        y = rng.standard_normal(int(SR * 1.0))
        power = (
            np.abs(
                librosa.stft(
                    y,
                    n_fft=measure_comb_hnr.N_FFT,
                    hop_length=measure_comb_hnr.HOP,
                )
            )
            ** 2
        )
        n = power.shape[1]
        f0 = np.full(n, 220.0)
        voiced = np.ones(n, dtype=bool)
        ratios = comb_hnr_frames(power, f0, voiced, SR)
        assert len(ratios) > 0
        assert abs(float(np.median(ratios))) < 1.0

    def test_too_short_returns_none(self):
        y = _harmonic_signal(220.0, duration=0.2)
        assert comb_hnr(y, SR) is None

    def test_sr_mismatch_raises(self):
        y = _harmonic_signal(220.0)
        with pytest.raises(ValueError):
            comb_hnr(y, 16000)


@pytest.mark.unit
class TestSelfTrackProtocol:
    """±20 cent 罠の再発防止 (v11 head 設計 §5.3 deviation 4)。"""

    def test_self_track_invariant_under_f0_cent_error(self):
        """モデルが +20 cent ずれて描画しても、出力自身の F0 トラックで測る
        comb-HNR は不変。同じ信号を GT 格子 (220Hz) で測ると崩壊する —
        「GT/予測 F0 格子で gate を測ってはいけない」罠の機械的 pin。
        """
        f0_true = 220.0
        f0_shifted = f0_true * 2 ** (20.0 / 1200.0)  # +20 cent
        y_ref = _harmonic_signal(f0_true, noise_rms=3e-4, seed=2)
        y_shift = _harmonic_signal(f0_shifted, noise_rms=3e-4, seed=2)

        self_ref = comb_hnr(y_ref, SR)
        self_shift = comb_hnr(y_shift, SR)
        assert self_ref is not None and self_shift is not None
        # 出力自身のトラックなら ±20 cent の系統誤差に不変 (spike E2: 18.69 vs 18.58)
        assert abs(self_ref - self_shift) < 1.5

        # GT 格子で測ると崩壊する (spike E2: 18.69 → 0.74)
        gt_grid = comb_hnr_at_reference(y_shift, SR, f0_true)
        assert gt_grid is not None
        assert gt_grid < self_shift - 5.0

    def test_reference_grid_matches_self_when_f0_exact(self):
        """F0 誤差ゼロなら外部格子と自トラックはほぼ一致 (格子計算の同一性)。"""
        y = _harmonic_signal(220.0, noise_rms=3e-4, seed=3)
        self_v = comb_hnr(y, SR)
        ref_v = comb_hnr_at_reference(y, SR, 220.0)
        assert self_v is not None and ref_v is not None
        assert abs(self_v - ref_v) < 1.5


@pytest.mark.unit
class TestOctaveDownDetection:
    """サブハーモニック挿入 (oct↓ エラー、period-doubling) の検出関数。"""

    def test_octave_down_flagged(self):
        """奇数倍音が弱い period-doubled 信号 (真の周期は 110Hz) を、意図 F0
        220Hz と照合すると octave_down_flag が立つ (f0 比 ≈ 0.5)。
        """
        y = _harmonic_signal(110.0, noise_rms=3e-4, seed=4, odd_gain=0.25)
        out = detect_octave_down(y, SR, f0_ref_hz=220.0)
        assert out["octave_down_flag"] is True
        assert out["f0_ratio_median"] == pytest.approx(0.5, abs=0.06)
        assert out["comb_hnr_self_db"] is not None

    def test_correct_octave_not_flagged(self):
        """意図どおりの F0 で描画された信号は flag が立たない (比 ≈ 1)。"""
        y = _harmonic_signal(220.0, noise_rms=3e-4, seed=5)
        out = detect_octave_down(y, SR, f0_ref_hz=220.0)
        assert out["octave_down_flag"] is False
        assert out["f0_ratio_median"] == pytest.approx(1.0, abs=0.06)

    def test_cent_error_is_not_octave_error(self):
        """±20 cent の系統誤差は oct↓ と誤判定しない (比 ≈ 1 のまま)。

        GT 格子 comb は cent 誤差でも崩壊するため、flag は f0 比を主根拠に
        することを pin する (格子崩壊単独での flag 化の禁止)。
        """
        y = _harmonic_signal(220.0 * 2 ** (20.0 / 1200.0), noise_rms=3e-4, seed=6)
        out = detect_octave_down(y, SR, f0_ref_hz=220.0)
        assert out["octave_down_flag"] is False


@pytest.mark.unit
class TestBandParams:
    def test_default_band_is_1_to_3_khz(self):
        """A3 の帯域 (診断 doc §1: 1-3kHz が聴感の主犯) を pin する。"""
        assert DEFAULT_BAND_HZ == (1000.0, 3000.0)

    def test_docstring_declares_anchors_and_eval_only(self):
        """既知アンカーと EVAL-ONLY マーカー、自 F0 トラック規約の存在。"""
        doc = measure_comb_hnr.__doc__
        assert "EVAL-ONLY" in doc
        assert "13.2" in doc  # GT アンカー
        assert "4.6" in doc  # v10b ns=0.667 アンカー
        assert "12.3" in doc  # v10b ns=0.0 アンカー
        assert "出力自身の F0" in doc
