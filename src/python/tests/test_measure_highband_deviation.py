"""High-band energy deviation from real recordings of the same voice (plan §7.9)."""

import numpy as np
import pytest


pytestmark = pytest.mark.unit

SR = 22050


def _voice(seed, seconds=2.0):
    """Harmonic tone with a little broadband noise, like a voiced recording."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * seconds)) / SR
    f0 = 180 + 10 * seed
    x = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 40) if f0 * k < 10000)
    return (x + 0.01 * rng.standard_normal(t.size)).astype(np.float32)


def _highpass_noise(seed, n, cutoff=3000):
    rng = np.random.default_rng(seed)
    spec = np.fft.rfft(rng.standard_normal(n))
    spec[: int(cutoff / (SR / 2) * spec.size)] = 0
    return np.fft.irfft(spec, n).astype(np.float32)


def _lowpass(x, cutoff=3000):
    spec = np.fft.rfft(x)
    spec[int(cutoff / (SR / 2) * spec.size) :] = 0
    return np.fft.irfft(spec, x.size).astype(np.float32)


def test_edges_run_from_2750_hz_to_10250_hz_in_500_hz_steps():
    from piper_train.tools.measure_highband_deviation import high_band_edges

    edges = high_band_edges(SR)
    assert edges[0] == 2750 and edges[1] == 3250
    assert edges[-1] == 10250  # the resampler's transition band is left out


def test_identical_audio_has_zero_deviation():
    from piper_train.tools.measure_highband_deviation import voice_deviation

    real = [_voice(1), _voice(2)]
    r = voice_deviation(real, real, SR)
    assert r["abs_mean_db"] == pytest.approx(0.0, abs=1e-9)
    assert r["signed_mean_db"] == pytest.approx(0.0, abs=1e-9)


def test_added_high_band_noise_is_positive_and_lowpass_is_negative():
    from piper_train.tools.measure_highband_deviation import voice_deviation

    real = [_voice(1), _voice(2)]
    noisy = [x + 0.3 * _highpass_noise(i, x.size) for i, x in enumerate(real)]
    muffled = [_lowpass(x) for x in real]
    up = voice_deviation(noisy, real, SR)
    down = voice_deviation(muffled, real, SR)
    assert up["signed_mean_db"] > 1.0 and up["abs_mean_db"] > 1.0
    # a muffled sound must not look clean: the absolute deviation catches it
    assert down["signed_mean_db"] < -1.0 and down["abs_mean_db"] > 1.0
    assert len(up["per_band_db"]) == 15


def test_directory_report_averages_groups(tmp_path):
    import soundfile as sf

    from piper_train.tools.measure_highband_deviation import directory_report

    for group, seed in (("a", 1), ("b", 3)):
        for kind, gain in (("real", 0.0), ("test", 0.3)):
            d = tmp_path / kind / group
            d.mkdir(parents=True)
            for i in range(2):
                x = _voice(seed + i)
                sf.write(d / f"{i}.wav", x + gain * _highpass_noise(i, x.size), SR)
    report = directory_report(tmp_path / "test", tmp_path / "real")
    assert set(report["groups"]) == {"a", "b"}
    means = [report["groups"][g]["abs_mean_db"] for g in ("a", "b")]
    assert report["abs_mean_db"] == pytest.approx(sum(means) / 2)
    assert report["groups"]["a"]["n_test"] == 2


def test_real_recordings_at_another_rate_are_resampled(tmp_path):
    import soundfile as sf
    import soxr

    from piper_train.tools.measure_highband_deviation import directory_report

    for i in range(2):
        x = _voice(i + 1)
        (tmp_path / "test" / "a").mkdir(parents=True, exist_ok=True)
        (tmp_path / "real" / "a").mkdir(parents=True, exist_ok=True)
        sf.write(tmp_path / "test" / "a" / f"{i}.wav", x, SR)
        sf.write(
            tmp_path / "real" / "a" / f"{i}.wav", soxr.resample(x, SR, 44100), 44100
        )
    report = directory_report(tmp_path / "test", tmp_path / "real")
    assert report["abs_mean_db"] < 0.5


def test_real_recordings_can_sit_in_a_subdirectory_of_each_group(tmp_path):
    import soundfile as sf

    from piper_train.tools.measure_highband_deviation import directory_report

    for i in range(2):
        x = _voice(i + 1)
        (tmp_path / "test" / "a").mkdir(parents=True, exist_ok=True)
        (tmp_path / "set" / "a" / "speaker").mkdir(parents=True, exist_ok=True)
        sf.write(tmp_path / "test" / "a" / f"{i}.wav", x, SR)
        sf.write(tmp_path / "set" / "a" / "speaker" / f"{i}.wav", x, SR)
    report = directory_report(tmp_path / "test", tmp_path / "set", "speaker")
    assert report["abs_mean_db"] == pytest.approx(0.0, abs=1e-9)
