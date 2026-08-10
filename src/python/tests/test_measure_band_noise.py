"""Tests for piper_train.tools.measure_band_noise (voiced high-band excess).

背景 (docs/design/zero-shot-noise-root-cause-pqmf.md 症状 7): 既製指標が全て
zero-shot 合成の 5-9kHz ノイズに盲目だったため、v9 の smoke/eval 用に新設した
専用指標。実データ検証 (2026-08-10、同一テキスト・同一話者):
FT (がびがび無し) -15.5dB vs v8/v8.1 (がびがび有り) -9dB 台で 6dB 分離。

合成信号でその分離能力の機序 (有声フレームの高域過多を検出する) を pin する。
"""

from __future__ import annotations

import numpy as np
import pytest

from piper_train.tools.measure_band_noise import (
    _yin_f0_track,
    voiced_high_band_excess,
)


SR = 22050


def _harmonic_voice(
    duration: float = 1.0,
    f0: float = 150.0,
    n_harmonics: int = 60,
    rolloff_db_per_octave: float = 12.0,
) -> np.ndarray:
    """F0 の倍音列で「クリーンな有声音」を合成 (高域は自然減衰)。"""
    t = np.arange(int(SR * duration)) / SR
    wav = np.zeros_like(t)
    for k in range(1, n_harmonics + 1):
        f = k * f0
        if f >= SR / 2:
            break
        gain = 10 ** (-rolloff_db_per_octave * np.log2(f / f0) / 20)
        wav += gain * np.sin(2 * np.pi * f * t)
    return (wav / np.abs(wav).max() * 0.5).astype(np.float32)


def _band_noise(n: int, lo: float, hi: float, level: float, seed: int = 0) -> np.ndarray:
    """lo-hi Hz の帯域ノイズ (FFT 整形)。がびがびの模擬。"""
    rng = np.random.default_rng(seed)
    spec = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    freqs = np.fft.rfftfreq(n, 1.0 / SR)
    spec[(freqs < lo) | (freqs >= hi)] = 0
    noise = np.fft.irfft(spec, n=n)
    return (noise / np.abs(noise).max() * level).astype(np.float32)


@pytest.mark.unit
class TestVoicedHighBandExcess:
    def test_garbled_scores_higher_than_clean(self):
        """5-9kHz ノイズを足した「がびがび」版はクリーン版より高い値を返す。

        これが指標の存在意義そのもの (がびがび検出)。実データでは
        FT vs zero-shot で ~6dB の分離を確認済み — 合成信号では機序を pin。
        """
        clean = _harmonic_voice()
        garbled = clean + _band_noise(len(clean), 5000, 9000, level=0.05)
        v_clean = voiced_high_band_excess(clean, SR)
        v_garbled = voiced_high_band_excess(garbled, SR)
        assert v_clean is not None and v_garbled is not None
        assert v_garbled > v_clean + 3.0, (
            f"garbled ({v_garbled:.1f} dB) must exceed clean ({v_clean:.1f} dB) "
            f"by a clear margin"
        )

    def test_silence_returns_none(self):
        assert voiced_high_band_excess(np.zeros(SR, dtype=np.float32), SR) is None

    def test_unvoiced_noise_returns_none(self):
        """F0 のない純ノイズは voiced フレームが無く None (無声部を除外する設計)。"""
        rng = np.random.default_rng(1)
        noise = (rng.standard_normal(SR) * 0.3).astype(np.float32)
        assert voiced_high_band_excess(noise, SR) is None

    def test_stereo_input_accepted(self):
        clean = _harmonic_voice()
        stereo = np.stack([clean, clean], axis=1)
        v = voiced_high_band_excess(stereo, SR)
        assert v is not None

    def test_noise_level_monotonicity(self):
        """ノイズが強いほど値が上がる (単調性)。"""
        clean = _harmonic_voice()
        values = []
        for level in (0.0, 0.02, 0.08):
            wav = clean + _band_noise(len(clean), 5000, 9000, level=level, seed=2)
            values.append(voiced_high_band_excess(wav, SR))
        assert values[0] < values[1] < values[2]


@pytest.mark.unit
class TestYinTracker:
    def test_detects_f0_on_harmonic_voice(self):
        wav = _harmonic_voice(f0=150.0)
        f0 = _yin_f0_track(wav, SR)
        voiced = f0[f0 > 0]
        assert len(voiced) > 0.5 * len(f0), "most frames should be voiced"
        assert abs(np.median(voiced) - 150.0) < 10.0

    def test_silence_all_unvoiced(self):
        f0 = _yin_f0_track(np.zeros(SR, dtype=np.float32), SR)
        assert (f0 == 0).all()


@pytest.mark.unit
def test_cli_single_wav(tmp_path):
    import subprocess
    import sys

    import soundfile as sf

    wav_path = tmp_path / "test.wav"
    sf.write(str(wav_path), _harmonic_voice(), SR)
    proc = subprocess.run(
        [sys.executable, "-m", "piper_train.tools.measure_band_noise", "--wav", str(wav_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert "test.wav" in proc.stdout
