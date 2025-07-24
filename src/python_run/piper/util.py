"""Utilities"""

import numpy as np


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0, volume: float = 1.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range"""
    # First normalize to avoid clipping
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))

    # Then apply volume adjustment
    audio_norm = audio_norm * volume

    # Clip to valid range and convert to int16
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    audio_norm = audio_norm.astype("int16")
    return audio_norm
