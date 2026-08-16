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


# ---------------------------------------------------------------------------
# Phase A (E-1/E-2/E-5(iv)): band_profile / band_vector_db / DEFAULT_HI_BAND
# canonical 数式の出典: scripts/zs-quality-anatomy/anatomy.py (a)/(e)。
# 数値閾値は canonical 再現実装に同一の合成信号を通した実測で事前検証済み。
# ---------------------------------------------------------------------------

N_FFT = 2048


def _white_noise(duration: float = 3.0, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(int(SR * duration))


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


@pytest.mark.unit
class TestBandProfile:
    def test_band_vector_db_flat_spectrum_exact(self):
        """純関数 band_vector_db: 平坦スペクトル → 各 1kHz band ≈ -3.01dB。

        導出: ref=1-3kHz は 2kHz 幅で band の 2 倍 → 10·log10(1/2) = -3.010dB。
        bin 端数 (band あたり 92-93 bins / ref 186 bins) による誤差は最大
        -3.057dB (8-9kHz band)。閾値 ±0.2dB は端数誤差 0.047dB の 4 倍。
        """
        from piper_train.tools.measure_band_noise import band_vector_db

        freqs = np.fft.rfftfreq(N_FFT, 1.0 / SR)
        flat = np.ones(len(freqs))
        edges = tuple(range(0, 11001, 1000))
        vec = np.asarray(
            band_vector_db(flat, freqs, edges, (1000.0, 3000.0)), dtype=float
        )
        assert vec.shape == (11,)
        np.testing.assert_allclose(vec, -3.010, atol=0.2)
        # ref 正規化の pin: 任意ゲインで出力不変 (比率指標)。
        vec_gain = np.asarray(
            band_vector_db(flat * 123.4, freqs, edges, (1000.0, 3000.0)), dtype=float
        )
        np.testing.assert_allclose(vec_gain, vec, atol=1e-9)

    def test_band_profile_detects_injected_band_only(self):
        """6.1-6.9kHz だけ持ち上げた合成信号 → 1kHz ベクトルの band 6 のみ検出。

        注入は band 6 ([6,7) kHz) 内側 (6100-6900Hz) — STFT 窓の端漏れが隣接
        band に染みない配置。共通の微小白色床 (0.002) は倍音が尽きる 9kHz 以上
        の空 band を窓漏れの数値床から実体のある床に置き換え、Δ を安定させる
        (床なしだと 10-11kHz の Δ が -4dB 台に暴れる実測)。canonical 再現での
        実測: Δ[6]=+24.5dB / 他 band |Δ|≤0.06dB。閾値 >3.0 / <1.0 (仕様 §6.3)。
        """
        from piper_train.tools.acoustic_frames import analyze_frames
        from piper_train.tools.measure_band_noise import (
            band_delta_vs_real,
            band_group_summary,
            band_profile,
        )

        n = int(1.5 * SR)
        floor = 0.002 * _white_noise(duration=1.5, seed=13)
        clean = _harmonic_voice(duration=1.5).astype(np.float64) + floor
        noisy = clean + _band_noise(n, 6100, 6900, level=0.05, seed=7)

        fa_clean = analyze_frames(clean, SR)
        fa_noisy = analyze_frames(noisy, SR)
        assert fa_clean is not None and fa_noisy is not None
        prof_clean = band_profile(fa_clean)
        prof_noisy = band_profile(fa_noisy)
        assert prof_clean is not None and prof_noisy is not None

        delta = band_delta_vs_real(
            band_group_summary([prof_noisy]), band_group_summary([prof_clean])
        )
        vec = np.asarray(delta["band_delta_vs_real_1khz"], dtype=float)
        assert vec.shape == (11,)
        assert vec[6] > 3.0, f"injected band not detected: {vec[6]:.2f} dB"
        others = np.delete(vec, 6)
        assert np.all(np.abs(others) < 1.0), f"false detection: {np.round(vec, 2)}"

    def test_voiced_unvoiced_shelf_separation(self):
        """無声部にのみ 5.5-8.5kHz 過剰 → unvoiced shelf だけが検出する。

        有声部 (クリーン倍音 1.2s) + 無音ギャップ 0.3s + 無声バースト 0.5s。
        ギャップは voice/burst 境界フレーム (STFT 窓 ±1024 samples が両者を跨ぐ)
        の voiced 平均への混入を防ぐ (ギャップなしだと voiced shelf が +21dB
        汚染される実測)。test = 5.5-8.5kHz バースト / ctrl = 0.5-4kHz バースト。
        canonical 再現での実測: voiced Δ=0.00dB / unvoiced Δ≈+52dB
        (n_unvoiced=46 ≥ 5)。閾値: voiced |Δ|<1.5 / unvoiced Δ>3.0 (仕様 §6.3、
        §4.3 の無声別枠 gate ≤+3.0dB と同じ物差し)。
        """
        from piper_train.tools.acoustic_frames import analyze_frames
        from piper_train.tools.measure_band_noise import (
            band_delta_vs_real,
            band_group_summary,
            band_profile,
        )

        voice = _harmonic_voice(duration=1.2).astype(np.float64)
        gap = np.zeros(int(0.3 * SR))
        burst_hi = _band_noise(int(0.5 * SR), 5500, 8500, level=0.3, seed=11)
        burst_lo = _band_noise(int(0.5 * SR), 500, 4000, level=0.3, seed=11)
        test_clip = np.concatenate([voice, gap, burst_hi.astype(np.float64)])
        ctrl_clip = np.concatenate([voice, gap, burst_lo.astype(np.float64)])

        profiles = {}
        for name, clip in (("test", test_clip), ("ctrl", ctrl_clip)):
            fa = analyze_frames(clip, SR)
            assert fa is not None
            prof = band_profile(fa)
            assert prof is not None
            profiles[name] = prof

        delta = band_delta_vs_real(
            band_group_summary([profiles["test"]]),
            band_group_summary([profiles["ctrl"]]),
        )
        assert abs(delta["shelf_voiced_max_delta_db"]) < 1.5, (
            "voiced shelf must be unaffected by unvoiced-only noise: "
            f"{delta['shelf_voiced_max_delta_db']:.2f} dB"
        )
        assert delta["shelf_unvoiced_max_delta_db"] is not None
        assert delta["shelf_unvoiced_max_delta_db"] > 3.0

    def test_voiced_high_band_excess_backward_compat(self):
        """既存 voiced_high_band_excess の regression pin (Phase A 拡張で不変)。

        pin 値は Phase A 拡張前の実装 (2026-08-16、numpy 経路のみで決定論的)
        での採取値。hi_band を明示指定するのは、E-5(iv) の DEFAULT_HI_BAND 変更
        (5-9k → 4-9k) 後もこの値が不変であるべきため (関数本体は無変更が契約 —
        仕様 §2.3、歴史的 TSV との A/B 継続性)。atol=1e-4dB は プラットフォーム
        FP 揺らぎ (〜1e-7dB) の 1000 倍マージンで、実装変更 (>0.01dB) は検出する。
        """
        clean = _harmonic_voice()
        garbled = clean + _band_noise(len(clean), 5000, 9000, level=0.05, seed=0)
        v_clean = voiced_high_band_excess(clean, SR, hi_band=(5000.0, 9000.0))
        v_garbled = voiced_high_band_excess(garbled, SR, hi_band=(5000.0, 9000.0))
        assert v_clean == pytest.approx(-21.917684877889933, abs=1e-4)
        assert v_garbled == pytest.approx(-0.7192264022755911, abs=1e-4)

    def test_default_hi_band_unified_to_4k9k(self):
        """E-5(iv): DEFAULT_HI_BAND は (4000, 9000) — 契約 §1 / 本走 harness と統一。

        v9 期の旧値 (5000, 9000) に戻すと fail する pin (仕様 D8)。旧 TSV と
        直接比較する場合は CLI で --hi-lo 5000 を明示する運用。
        """
        from piper_train.tools.measure_band_noise import DEFAULT_HI_BAND

        assert tuple(DEFAULT_HI_BAND) == (4000.0, 9000.0)

    def test_band_profile_deterministic(self):
        """同一入力 2 回 → 同一出力 (manifest への数値 pin の前提条件)。"""
        from piper_train.tools.acoustic_frames import analyze_frames
        from piper_train.tools.measure_band_noise import band_profile

        wav = _harmonic_voice(duration=1.2).astype(np.float64)
        wav = wav + 0.01 * _white_noise(duration=1.2, seed=17)
        fa1 = analyze_frames(wav, SR)
        fa2 = analyze_frames(wav.copy(), SR)
        assert fa1 is not None and fa2 is not None
        p1 = band_profile(fa1)
        p2 = band_profile(fa2)
        assert p1 is not None and p2 is not None
        _assert_tree_equal(p1, p2)
