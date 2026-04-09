"""Speaker Encoder (ECAPA-TDNN) for speaker embedding extraction.

Provides a PyTorch ECAPA-TDNN model, NumPy-based audio preprocessing,
and a high-level API for extracting 256-dimensional speaker embeddings
from audio files.

Usage (PyTorch):
    from piper_train.speaker_encoder import ECAPATDNN
    model = ECAPATDNN()
    embedding = model(mel_spectrogram)

Usage (high-level API):
    from piper_train.speaker_encoder import SpeakerEncoder
    encoder = SpeakerEncoder.from_onnx("speaker_encoder.onnx")
    embedding = encoder.encode("audio.wav")
"""

from .audio_utils import compute_mel_spectrogram, load_audio, normalize_audio
from .ecapa_tdnn import ECAPATDNN
from .encoder import SpeakerEncoder


__all__ = [
    "ECAPATDNN",
    "SpeakerEncoder",
    "compute_mel_spectrogram",
    "load_audio",
    "normalize_audio",
]
