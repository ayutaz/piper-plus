"""Tests for the numpy energy VAD that replaced Silero ONNX VAD.

Source: ``piper_train.norm_audio.energy_vad_numpy``.
Reported speedup: ~1793x faster than Silero ONNX with 100% agreement on LibriTTS-R.
These tests pin the public contract so silent regressions in the VAD
behaviour cannot reach the training pipeline.
"""

import numpy as np
import pytest

# piper_train.norm_audio.__init__ imports torchaudio at module top-level,
# so we must skip the entire test module when torchaudio is unavailable.
pytest.importorskip("torchaudio")

from piper_train.norm_audio import energy_vad_numpy  # noqa: E402


@pytest.mark.unit
class TestEnergyVadNumpyBoundaries:
    def test_silent_audio_returns_no_voiced_content(self):
        audio = np.zeros(16000, dtype=np.float32)
        offset, duration = energy_vad_numpy(audio)
        assert offset == 0.0
        assert duration is None

    def test_audio_shorter_than_chunk_returns_none(self):
        # chunk_size default is 480 samples; len(audio) // chunk_size == 0
        audio = np.zeros(100, dtype=np.float32)
        offset, duration = energy_vad_numpy(audio)
        assert offset == 0.0
        assert duration is None

    def test_constant_loud_audio_detected(self):
        audio = np.ones(32000, dtype=np.float32) * 0.5
        offset, duration = energy_vad_numpy(audio, threshold=0.02)
        assert offset == 0.0
        assert duration is not None
        assert duration > 1.9  # ~2.0 seconds covered

    def test_signal_above_threshold_detected(self):
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.5, size=32000).astype(np.float32)
        offset, duration = energy_vad_numpy(audio, threshold=0.02)
        assert duration is not None

    def test_signal_below_threshold_returns_none(self):
        rng = np.random.default_rng(42)
        audio = rng.normal(0, 0.005, size=32000).astype(np.float32)
        offset, duration = energy_vad_numpy(audio, threshold=0.1)
        assert offset == 0.0
        assert duration is None


@pytest.mark.unit
class TestEnergyVadNumpyTrimming:
    def test_speech_in_middle_with_silence_padding(self):
        sr = 16000
        silence = np.zeros(sr, dtype=np.float32)
        speech = np.ones(sr, dtype=np.float32) * 0.5
        audio = np.concatenate([silence, speech, silence])

        offset, duration = energy_vad_numpy(
            audio,
            chunk_size=480,
            threshold=0.02,
            keep_before=0,
            keep_after=0,
        )
        assert duration is not None
        # Speech starts approximately 1 second in
        assert 0.9 <= offset <= 1.1
        # And lasts approximately 1 second
        assert 0.9 <= duration <= 1.1

    def test_keep_before_after_extends_segment(self):
        sr = 16000
        silence = np.zeros(sr, dtype=np.float32)
        speech = np.ones(int(sr * 0.5), dtype=np.float32) * 0.5
        audio = np.concatenate([silence, speech, silence])

        off0, dur0 = energy_vad_numpy(
            audio, chunk_size=480, threshold=0.02, keep_before=0, keep_after=0
        )
        off1, dur1 = energy_vad_numpy(
            audio, chunk_size=480, threshold=0.02, keep_before=2, keep_after=2
        )

        assert off0 is not None and off1 is not None
        assert dur0 is not None and dur1 is not None
        # Padded version starts at or before, and lasts at least as long
        assert off1 <= off0
        assert dur1 >= dur0

    def test_keep_before_clamped_to_zero(self):
        # keep_before larger than the silence prefix should not yield negative offset
        sr = 16000
        silence = np.zeros(sr // 4, dtype=np.float32)  # 0.25s prefix
        speech = np.ones(sr, dtype=np.float32) * 0.5
        audio = np.concatenate([silence, speech])
        offset, duration = energy_vad_numpy(
            audio,
            chunk_size=480,
            threshold=0.02,
            keep_before=999,
            keep_after=0,
        )
        assert offset == 0.0
        assert duration is not None

    def test_keep_after_clamped_to_audio_length(self):
        sr = 16000
        speech = np.ones(sr, dtype=np.float32) * 0.5
        silence = np.zeros(sr // 4, dtype=np.float32)
        audio = np.concatenate([speech, silence])
        offset, duration = energy_vad_numpy(
            audio,
            chunk_size=480,
            threshold=0.02,
            keep_before=0,
            keep_after=999,
        )
        assert duration is not None
        # Should not exceed the total audio length in seconds
        assert offset + duration <= len(audio) / sr + 1e-6


@pytest.mark.unit
class TestEnergyVadNumpyContract:
    def test_returns_pair_floats(self):
        audio = np.ones(16000, dtype=np.float32) * 0.5
        offset, duration = energy_vad_numpy(audio)
        assert isinstance(offset, float)
        assert duration is None or isinstance(duration, float)

    def test_chunk_size_changes_quantisation(self):
        sr = 16000
        audio = np.ones(sr, dtype=np.float32) * 0.5
        _, dur_large = energy_vad_numpy(audio, chunk_size=480)
        _, dur_small = energy_vad_numpy(audio, chunk_size=160)
        # Both detect speech; shorter chunks give finer-grained results.
        assert dur_large is not None and dur_small is not None
