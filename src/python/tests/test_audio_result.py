"""Tests for AudioResult -- container for synthesized audio data.

Verifies duration calculation, WAV encoding, file output, and edge cases.
Follows t-wada TDD principles: behaviour-driven test names, Arrange-Act-Assert,
triangulation with multiple data points.
"""

from __future__ import annotations

import struct
import wave
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

from piper_plus.audio import AudioResult


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioResultDuration:
    """AudioResult.duration returns audio length in seconds."""

    def test_duration_returns_zero_for_empty_audio(self):
        # Arrange
        result = AudioResult(audio=np.array([], dtype=np.int16), sample_rate=22050)

        # Act
        duration = result.duration

        # Assert
        assert duration == 0.0

    def test_duration_returns_one_second_for_22050_samples(self):
        # Arrange
        result = AudioResult(
            audio=np.zeros(22050, dtype=np.int16), sample_rate=22050
        )

        # Act / Assert
        assert result.duration == pytest.approx(1.0)

    def test_duration_returns_half_second_for_11025_samples(self):
        result = AudioResult(
            audio=np.zeros(11025, dtype=np.int16), sample_rate=22050
        )
        assert result.duration == pytest.approx(0.5)

    def test_duration_scales_with_sample_rate(self):
        """Same number of samples at different rates yields different durations."""
        samples = np.zeros(44100, dtype=np.int16)
        at_22050 = AudioResult(audio=samples, sample_rate=22050)
        at_44100 = AudioResult(audio=samples, sample_rate=44100)

        assert at_22050.duration == pytest.approx(2.0)
        assert at_44100.duration == pytest.approx(1.0)

    def test_duration_uses_default_sample_rate_22050(self):
        result = AudioResult(audio=np.zeros(22050, dtype=np.int16))
        assert result.sample_rate == 22050
        assert result.duration == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# to_wav_bytes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioResultToWavBytes:
    """AudioResult.to_wav_bytes() produces valid WAV data."""

    def test_to_wav_bytes_returns_bytes(self):
        result = AudioResult(audio=np.zeros(100, dtype=np.int16), sample_rate=22050)

        wav_data = result.to_wav_bytes()

        assert isinstance(wav_data, bytes)

    def test_to_wav_bytes_starts_with_riff_header(self):
        result = AudioResult(audio=np.zeros(100, dtype=np.int16), sample_rate=22050)

        wav_data = result.to_wav_bytes()

        assert wav_data[:4] == b"RIFF"

    def test_to_wav_bytes_has_correct_channels_and_sample_width(self):
        result = AudioResult(audio=np.zeros(100, dtype=np.int16), sample_rate=22050)

        wav_data = result.to_wav_bytes()
        with wave.open(BytesIO(wav_data), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2

    def test_to_wav_bytes_preserves_sample_rate(self):
        result = AudioResult(audio=np.zeros(100, dtype=np.int16), sample_rate=44100)

        wav_data = result.to_wav_bytes()
        with wave.open(BytesIO(wav_data), "rb") as wf:
            assert wf.getframerate() == 44100

    def test_to_wav_bytes_preserves_frame_count(self):
        audio = np.arange(256, dtype=np.int16)
        result = AudioResult(audio=audio, sample_rate=22050)

        wav_data = result.to_wav_bytes()
        with wave.open(BytesIO(wav_data), "rb") as wf:
            assert wf.getnframes() == 256

    def test_to_wav_bytes_round_trip_preserves_pcm_data(self):
        """PCM samples survive encode -> decode round-trip."""
        original = np.array([0, 1000, -1000, 32767, -32768], dtype=np.int16)
        result = AudioResult(audio=original, sample_rate=22050)

        wav_data = result.to_wav_bytes()
        with wave.open(BytesIO(wav_data), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        decoded = np.frombuffer(raw, dtype=np.int16)

        np.testing.assert_array_equal(decoded, original)

    def test_to_wav_bytes_for_empty_audio(self):
        result = AudioResult(audio=np.array([], dtype=np.int16), sample_rate=22050)

        wav_data = result.to_wav_bytes()
        with wave.open(BytesIO(wav_data), "rb") as wf:
            assert wf.getnframes() == 0


# ---------------------------------------------------------------------------
# save
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAudioResultSave:
    """AudioResult.save() writes a valid WAV file to disk."""

    def test_save_creates_file(self, tmp_path):
        audio = np.zeros(100, dtype=np.int16)
        result = AudioResult(audio=audio, sample_rate=22050)

        out = tmp_path / "output.wav"
        returned_path = result.save(out)

        assert out.exists()
        assert returned_path == out

    def test_save_creates_parent_directories(self, tmp_path):
        audio = np.zeros(100, dtype=np.int16)
        result = AudioResult(audio=audio, sample_rate=22050)

        nested = tmp_path / "a" / "b" / "c" / "output.wav"
        result.save(nested)

        assert nested.exists()

    def test_save_file_content_is_valid_wav(self, tmp_path):
        audio = np.array([100, -100, 32767], dtype=np.int16)
        result = AudioResult(audio=audio, sample_rate=16000)

        out = tmp_path / "test.wav"
        result.save(out)

        with wave.open(str(out), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 3
            assert wf.getnchannels() == 1

    def test_save_accepts_string_path(self, tmp_path):
        result = AudioResult(audio=np.zeros(50, dtype=np.int16), sample_rate=22050)

        out = str(tmp_path / "string_path.wav")
        returned = result.save(out)

        assert Path(out).exists()
        assert isinstance(returned, Path)

    def test_save_empty_audio_creates_valid_wav(self, tmp_path):
        result = AudioResult(audio=np.array([], dtype=np.int16), sample_rate=22050)

        out = tmp_path / "empty.wav"
        result.save(out)

        with wave.open(str(out), "rb") as wf:
            assert wf.getnframes() == 0
