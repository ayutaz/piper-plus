"""AudioResult -- container for synthesized audio data."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AudioResult:
    """Container for synthesized audio data.

    Attributes:
        audio: Raw PCM audio samples (int16).
        sample_rate: Audio sample rate in Hz (default: 22050).
    """

    audio: np.ndarray
    sample_rate: int = 22050

    @property
    def duration(self) -> float:
        """Audio duration in seconds."""
        return len(self.audio) / self.sample_rate

    def to_wav_bytes(self) -> bytes:
        """Convert to WAV format bytes."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.audio.tobytes())
        return buf.getvalue()

    def save(self, path: str | Path) -> Path:
        """Save audio to WAV file.

        Args:
            path: Output file path. Parent directories are created
                automatically if they do not exist.

        Returns:
            The resolved :class:`Path` that was written.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_wav_bytes())
        return path

    def play(self) -> None:
        """Play audio using sounddevice (requires ``sounddevice`` package)."""
        if len(self.audio) == 0:
            return
        try:
            import sounddevice as sd  # noqa: PLC0415
        except ImportError:
            raise ImportError(
                "sounddevice is required for playback. "
                "Install with: pip install sounddevice"
            ) from None
        sd.play(self.audio.astype(np.float32) / 32768.0, self.sample_rate)
        sd.wait()
