"""High-level Speaker Encoder API.

Provides a unified interface for extracting speaker embeddings from audio
files using either a PyTorch checkpoint or an ONNX model.

Usage (ONNX -- recommended for inference):
    encoder = SpeakerEncoder.from_onnx("speaker_encoder.onnx")
    emb = encoder.encode("audio.wav")

Usage (PyTorch):
    encoder = SpeakerEncoder.from_pytorch("speaker_encoder.ckpt")
    emb = encoder.encode("audio.wav")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .audio_utils import (
    DEFAULT_FMAX,
    DEFAULT_FMIN,
    DEFAULT_HOP_LENGTH,
    DEFAULT_N_FFT,
    DEFAULT_N_MELS,
    DEFAULT_SR,
    compute_mel_spectrogram,
    load_audio,
    normalize_audio,
)


if TYPE_CHECKING:
    import onnxruntime
    import torch

_LOGGER = logging.getLogger(__name__)


def _infer_hparams(state_dict: dict) -> dict:
    """Infer ECAPA-TDNN hyperparameters from a state_dict.

    Examines key tensor shapes to determine input_dim, channels, emb_dim,
    and scale so that the model can be reconstructed without explicit
    configuration.

    Args:
        state_dict: Model state dictionary.

    Returns:
        Dict of keyword arguments for :class:`ECAPATDNN`.
    """
    # layer1.0.weight has shape (channels, input_dim, kernel_size)
    layer1_weight = state_dict.get("layer1.0.weight")
    if layer1_weight is None:
        raise ValueError(
            "Cannot infer hparams: 'layer1.0.weight' not found in state_dict"
        )

    channels = layer1_weight.shape[0]
    input_dim = layer1_weight.shape[1]

    # fc.weight has shape (emb_dim, channels * 2)
    fc_weight = state_dict.get("fc.weight")
    if fc_weight is None:
        raise ValueError("Cannot infer hparams: 'fc.weight' not found in state_dict")
    emb_dim = fc_weight.shape[0]

    # Infer Res2Net scale from the number of conv modules in layer2.res2net.convs
    # convs has (scale - 1) entries: convs.0, convs.1, ..., convs.(scale-2)
    scale_minus_1 = 0
    for key in state_dict:
        if key.startswith("layer2.res2net.convs.") and key.endswith(".weight"):
            scale_minus_1 += 1
    scale = scale_minus_1 + 1 if scale_minus_1 > 0 else 8

    # Infer SE bottleneck from layer2.se.se.1.weight shape (bottleneck, channels, 1)
    se_weight = state_dict.get("layer2.se.se.1.weight")
    se_bottleneck = se_weight.shape[0] if se_weight is not None else 128

    return {
        "input_dim": input_dim,
        "channels": channels,
        "emb_dim": emb_dim,
        "scale": scale,
        "se_bottleneck": se_bottleneck,
    }


class SpeakerEncoder:
    """Speaker Encoder high-level API.

    Loads a PyTorch or ONNX speaker encoder model and provides methods
    to extract 256-dimensional speaker embeddings from audio files.

    Do not instantiate directly; use :meth:`from_pytorch` or :meth:`from_onnx`.
    """

    def __init__(self) -> None:
        self._mode: str = "none"  # "pytorch" or "onnx"
        self._pytorch_model: torch.nn.Module | None = None
        self._pytorch_device: str = "cpu"
        self._onnx_session: onnxruntime.InferenceSession | None = None

    @classmethod
    def from_pytorch(
        cls,
        checkpoint_path: str | Path,
        device: str = "cpu",
    ) -> SpeakerEncoder:
        """Load a speaker encoder from a PyTorch checkpoint.

        The checkpoint should contain either:
          - A raw state_dict (keys like ``layer1.0.weight``), or
          - A dict with a ``"model_state_dict"`` key.

        Args:
            checkpoint_path: Path to the ``.ckpt`` or ``.pt`` file.
            device: Torch device string (default: ``"cpu"``).

        Returns:
            Configured :class:`SpeakerEncoder` instance.
        """
        import torch  # noqa: PLC0415

        from .ecapa_tdnn import ECAPATDNN  # noqa: PLC0415

        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        ckpt = torch.load(str(checkpoint_path), map_location=device, weights_only=True)

        if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
            state_dict = ckpt["model_state_dict"]
        elif isinstance(ckpt, dict) and all(isinstance(k, str) for k in ckpt.keys()):
            state_dict = ckpt
        else:
            raise ValueError(
                "Checkpoint format not recognised. Expected a state_dict or a "
                "dict with 'model_state_dict' key."
            )

        # Infer model hyperparameters from the state_dict shapes
        hparams = _infer_hparams(state_dict)
        model = ECAPATDNN(**hparams)
        model.load_state_dict(state_dict)
        model.eval()
        model.to(device)

        encoder = cls()
        encoder._mode = "pytorch"
        encoder._pytorch_model = model
        encoder._pytorch_device = device
        _LOGGER.info(
            "Loaded PyTorch speaker encoder from %s (device=%s)",
            checkpoint_path,
            device,
        )
        return encoder

    @classmethod
    def from_onnx(cls, onnx_path: str | Path) -> SpeakerEncoder:
        """Load a speaker encoder from an ONNX model.

        Uses the project's shared ORT session utilities for optimised
        session creation with caching support.

        Args:
            onnx_path: Path to the ``.onnx`` file.

        Returns:
            Configured :class:`SpeakerEncoder` instance.
        """
        onnx_path = Path(onnx_path)
        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

        from ..ort_utils import create_session_with_cache  # noqa: PLC0415

        session = create_session_with_cache(onnx_path, device="cpu")

        encoder = cls()
        encoder._mode = "onnx"
        encoder._onnx_session = session
        _LOGGER.info("Loaded ONNX speaker encoder from %s", onnx_path)
        return encoder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, audio_path: str | Path) -> np.ndarray:
        """Extract a 256-dimensional speaker embedding from an audio file.

        The audio is loaded, peak-normalized, converted to a log-mel
        spectrogram, and passed through the encoder model.

        Args:
            audio_path: Path to an audio file (WAV, FLAC, OGG, etc.).

        Returns:
            1-D float32 array of shape ``(256,)``, L2-normalized.
        """
        mel = self._audio_to_mel(audio_path)
        return self._infer(mel)

    def encode_batch(self, audio_paths: list[str | Path]) -> np.ndarray:
        """Extract speaker embeddings for multiple audio files.

        All mel spectrograms are zero-padded to the longest in the batch
        so they can be processed in a single forward pass.

        Args:
            audio_paths: List of audio file paths.

        Returns:
            2-D float32 array of shape ``(len(audio_paths), 256)``.
        """
        if not audio_paths:
            return np.empty((0, 256), dtype=np.float32)

        mels = [self._audio_to_mel(p) for p in audio_paths]

        # Pad to uniform time length
        max_time = max(m.shape[1] for m in mels)
        padded = np.zeros((len(mels), mels[0].shape[0], max_time), dtype=np.float32)
        for i, m in enumerate(mels):
            padded[i, :, : m.shape[1]] = m

        return self._infer_batch(padded)

    @staticmethod
    def similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings.

        Both embeddings should already be L2-normalized (as returned by
        :meth:`encode`), but this method re-normalizes for safety.

        Args:
            emb1: 1-D float32 array of shape ``(emb_dim,)``.
            emb2: 1-D float32 array of shape ``(emb_dim,)``.

        Returns:
            Cosine similarity in [-1, 1].
        """
        emb1 = emb1.flatten().astype(np.float64)
        emb2 = emb2.flatten().astype(np.float64)

        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 < 1e-12 or norm2 < 1e-12:
            return 0.0

        return float(np.dot(emb1, emb2) / (norm1 * norm2))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _audio_to_mel(self, audio_path: str | Path) -> np.ndarray:
        """Load audio and compute mel spectrogram.

        Returns:
            (n_mels, time) float32 array.
        """
        audio = load_audio(audio_path, sr=DEFAULT_SR)
        audio = normalize_audio(audio)
        mel = compute_mel_spectrogram(
            audio,
            sr=DEFAULT_SR,
            n_fft=DEFAULT_N_FFT,
            hop_length=DEFAULT_HOP_LENGTH,
            n_mels=DEFAULT_N_MELS,
            fmin=DEFAULT_FMIN,
            fmax=DEFAULT_FMAX,
        )
        return mel

    def _infer(self, mel: np.ndarray) -> np.ndarray:
        """Run inference on a single mel spectrogram.

        Args:
            mel: (n_mels, time) float32 array.

        Returns:
            1-D float32 array of shape ``(emb_dim,)``.
        """
        # Add batch dimension: (1, n_mels, time)
        mel_batch = mel[np.newaxis, :, :]
        return self._infer_batch(mel_batch)[0]

    def _infer_batch(self, mel_batch: np.ndarray) -> np.ndarray:
        """Run inference on a batch of mel spectrograms.

        Args:
            mel_batch: (batch, n_mels, time) float32 array.

        Returns:
            (batch, emb_dim) float32 array.
        """
        if self._mode == "pytorch":
            return self._infer_pytorch(mel_batch)
        elif self._mode == "onnx":
            return self._infer_onnx(mel_batch)
        else:
            raise RuntimeError(
                "SpeakerEncoder not initialised. Use from_pytorch() or from_onnx()."
            )

    def _infer_pytorch(self, mel_batch: np.ndarray) -> np.ndarray:
        """Run inference with the PyTorch model."""
        import torch  # noqa: PLC0415

        assert self._pytorch_model is not None

        tensor = torch.from_numpy(mel_batch).to(self._pytorch_device)
        with torch.no_grad():
            embedding = self._pytorch_model(tensor)

        return embedding.cpu().numpy()

    def _infer_onnx(self, mel_batch: np.ndarray) -> np.ndarray:
        """Run inference with the ONNX model."""
        assert self._onnx_session is not None

        input_name = self._onnx_session.get_inputs()[0].name
        output_name = self._onnx_session.get_outputs()[0].name

        result = self._onnx_session.run(
            [output_name],
            {input_name: mel_batch.astype(np.float32)},
        )
        return result[0]
