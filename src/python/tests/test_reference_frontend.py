"""参照音声trim (学習時と同じenergy VAD) のテスト。"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from piper_train.extract_speaker_embedding import preprocess_audio
from piper_train.reference_frontend import trim_reference_audio


def tone(n: int, amp: float, sr: int = 22050, freq: float = 220.0) -> np.ndarray:
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture
def wav_with_silence(tmp_path):
    sr = 22050
    audio = np.concatenate([np.zeros(sr), tone(sr, 0.3, sr), np.zeros(sr)])
    path = tmp_path / "ref.wav"
    sf.write(str(path), audio.astype(np.float32), sr)
    return path


def test_trim_matches_training_vad_bounds():
    audio = np.concatenate([np.zeros(22050), tone(22050, 0.3), np.zeros(22050)])
    out, info = trim_reference_audio(audio, 22050)
    assert 0.9 < info["offset_sec"] < 1.0
    assert len(out) < len(audio)
    assert info["method"] == "energy_vad_numpy@16k"
    assert info["duration_sec"] > 0


def test_trim_rejects_all_silence():
    with pytest.raises(ValueError, match="no voiced"):
        trim_reference_audio(np.zeros(44100, dtype=np.float32), 22050)


def test_preprocess_audio_trim_default_off_is_unchanged(wav_with_silence):
    assert np.array_equal(
        preprocess_audio(wav_with_silence),
        preprocess_audio(wav_with_silence, trim=False),
    )


def test_preprocess_audio_trim_shortens_features(wav_with_silence):
    untrimmed = preprocess_audio(wav_with_silence)
    trimmed = preprocess_audio(wav_with_silence, trim=True)
    assert trimmed.shape[0] < untrimmed.shape[0]
    assert trimmed.shape[1] == 80
