"""Unit tests for the KsponSpeech-style headerless PCM reader.

KsponSpeech ships as raw 16 kHz mono s16le PCM with no RIFF header. The v8 KO
enablement adds ``norm_audio._read_pcm16_mono`` + ``_read_audio_any`` so the
preprocess pipeline can enumerate ``.pcm`` files directly, skipping the ~3-4h
PCM→WAV pre-pass that the previous handoff required.

These tests pin the reader contract:

1. Round-trip: int16 samples divided by 32768 land in ``[-1, 1]`` float32.
2. Normalisation matches the PCM spec exactly (``-32768 / 32768 == -1.0``,
   ``32767 / 32768 ≈ 0.99997``).
3. ``_read_audio_any`` dispatches on the ``.pcm`` suffix (case-insensitive)
   and returns the pinned 16 kHz sample rate.
4. Non-``.pcm`` paths fall through to soundfile so existing WAV/FLAC callers
   keep the same behaviour.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


torch = pytest.importorskip("torch")
soundfile = pytest.importorskip("soundfile")

from piper_train.norm_audio import (  # noqa: E402
    _PCM16_MONO_SAMPLE_RATE,
    _read_audio_any,
    _read_pcm16_mono,
)


def _write_pcm16(path: Path, samples: np.ndarray) -> None:
    """Write an int16 numpy array as headerless little-endian PCM."""
    assert samples.dtype == np.int16, f"expected int16, got {samples.dtype}"
    # numpy int16 uses native byte order — force little-endian to mimic the
    # KsponSpeech distribution regardless of host endianness.
    samples.astype("<i2").tofile(str(path))


# ---------------------------------------------------------------------------
# _read_pcm16_mono normalisation contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_read_pcm16_mono_returns_float32_in_unit_range(tmp_path: Path) -> None:
    rng = np.random.default_rng(seed=42)
    samples = rng.integers(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        size=16000,  # 1 second of "audio"
        dtype=np.int16,
    )
    pcm_path = tmp_path / "clip.pcm"
    _write_pcm16(pcm_path, samples)

    audio = _read_pcm16_mono(pcm_path)

    assert audio.dtype == np.float32
    assert audio.ndim == 1  # mono → 1-D, matches sf.read(always_2d=False)
    assert audio.shape == (16000,)
    # Normalisation must land inside [-1, 1] (inclusive lower bound for
    # int16.min / 32768).
    assert audio.min() >= -1.0
    assert audio.max() <= 1.0


@pytest.mark.unit
def test_read_pcm16_mono_normalisation_matches_spec(tmp_path: Path) -> None:
    """Divisor is 32768 per the s16 PCM convention (not 32767)."""
    samples = np.array(
        [np.iinfo(np.int16).min, 0, np.iinfo(np.int16).max], dtype=np.int16
    )
    pcm_path = tmp_path / "extremes.pcm"
    _write_pcm16(pcm_path, samples)

    audio = _read_pcm16_mono(pcm_path)

    # Exact-value assertions — any regression to /32767.0 would flip these.
    assert audio[0] == pytest.approx(-1.0, abs=1e-7)
    assert audio[1] == pytest.approx(0.0, abs=1e-7)
    assert audio[2] == pytest.approx(32767.0 / 32768.0, abs=1e-7)


@pytest.mark.unit
def test_read_pcm16_mono_handles_empty_file(tmp_path: Path) -> None:
    pcm_path = tmp_path / "empty.pcm"
    pcm_path.write_bytes(b"")

    audio = _read_pcm16_mono(pcm_path)

    assert audio.dtype == np.float32
    assert audio.shape == (0,)


# ---------------------------------------------------------------------------
# _read_audio_any dispatcher (.pcm vs soundfile passthrough)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_read_audio_any_dispatches_pcm(tmp_path: Path) -> None:
    samples = np.array([0, 16384, -16384, 32767], dtype=np.int16)
    pcm_path = tmp_path / "clip.pcm"
    _write_pcm16(pcm_path, samples)

    audio, sr = _read_audio_any(pcm_path)

    assert sr == _PCM16_MONO_SAMPLE_RATE == 16000
    assert audio.dtype == np.float32
    assert audio.shape == (4,)
    np.testing.assert_allclose(
        audio,
        np.array(
            [0.0, 16384 / 32768.0, -16384 / 32768.0, 32767 / 32768.0],
            dtype=np.float32,
        ),
        atol=1e-7,
    )


@pytest.mark.unit
def test_read_audio_any_pcm_dispatch_is_case_insensitive(tmp_path: Path) -> None:
    """KsponSpeech ships lowercase but future exporters may not."""
    samples = np.zeros(8, dtype=np.int16)
    pcm_path = tmp_path / "clip.PCM"
    _write_pcm16(pcm_path, samples)

    audio, sr = _read_audio_any(pcm_path)

    assert sr == 16000
    assert audio.shape == (8,)


@pytest.mark.unit
def test_read_audio_any_falls_through_to_soundfile_for_wav(
    tmp_path: Path,
) -> None:
    """Non-.pcm paths must keep going through soundfile at native sample rate."""
    sr_native = 22050
    t = np.linspace(0.0, 1.0, sr_native, endpoint=False, dtype=np.float32)
    audio_in = (0.25 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    wav_path = tmp_path / "clip.wav"
    soundfile.write(str(wav_path), audio_in, sr_native)

    audio_out, sr_out = _read_audio_any(wav_path)

    # soundfile returned the WAV's own sample rate — dispatcher did NOT force
    # the PCM 16 kHz shortcut.
    assert sr_out == sr_native
    assert audio_out.dtype == np.float32
    assert audio_out.shape == (sr_native,)
