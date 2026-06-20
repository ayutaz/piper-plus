"""
E2E zero-shot inference tests using the real test ONNX model.

Tests run direct ONNX inference (bypassing PiperVoice) so that the
phoneme_type='espeak' config in zero-shot-test.onnx.json is not a concern.

Model files are expected at:
  <repo-root>/test/models/zero-shot-test.onnx
  <repo-root>/test/models/zero-shot-test.onnx.json
  <repo-root>/test/models/test_speaker.npy
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# onnxruntime availability guard
# ---------------------------------------------------------------------------
try:
    import onnxruntime  # noqa: F401

    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False

ort_skip = pytest.mark.skipif(
    not _ORT_AVAILABLE,
    reason="onnxruntime is not installed",
)

# ---------------------------------------------------------------------------
# Locate model files relative to the repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parents[3]  # .../piper-plus-zero-shot/
_MODEL_DIR = _REPO_ROOT / "test" / "models"
_MODEL_PATH = _MODEL_DIR / "zero-shot-test.onnx"
_SPEAKER_NPY = _MODEL_DIR / "test_speaker.npy"

_models_present = _MODEL_PATH.exists() and _SPEAKER_NPY.exists()
model_skip = pytest.mark.skipif(
    not _models_present,
    reason=f"Test model files not found under {_MODEL_DIR}",
)

# Note: These tests use raw onnxruntime.InferenceSession (not PiperVoice),
# so PIPER_DISABLE_WARMUP / PIPER_DISABLE_CACHE have no effect here. They
# are intentionally NOT set at module load to avoid polluting the environment
# for unrelated tests (e.g. test_config_fallback.TestVoiceInlineWarmup).


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_session() -> "onnxruntime.InferenceSession":
    """Load the zero-shot test ONNX model on CPU."""
    return onnxruntime.InferenceSession(
        str(_MODEL_PATH),
        providers=["CPUExecutionProvider"],
    )


def _base_inputs(phoneme_length: int = 40) -> dict:
    """Return the minimal dict of numpy arrays expected by zero-shot-test.onnx."""
    phoneme_ids = np.zeros((1, phoneme_length), dtype=np.int64)
    phoneme_ids[0, 0] = 1   # BOS
    phoneme_ids[0, -1] = 2  # EOS
    return {
        "input": phoneme_ids,
        "input_lengths": np.array([phoneme_length], dtype=np.int64),
        "scales": np.array([0.4, 1.0, 0.5], dtype=np.float32),
        "prosody_features": np.zeros((1, phoneme_length, 3), dtype=np.int64),
    }


def _run(session, embedding: np.ndarray, phoneme_length: int = 40) -> np.ndarray:
    """Run a single forward pass and return the audio tensor (float32)."""
    inputs = _base_inputs(phoneme_length)
    inputs["speaker_embedding"] = embedding.reshape(1, 192).astype(np.float32)
    return session.run(None, inputs)[0]  # shape [1, 1, T]


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

@ort_skip
@model_skip
class TestZeroShotE2E:
    """End-to-end inference tests against zero-shot-test.onnx."""

    @pytest.mark.inference
    def test_e2e_zero_shot_produces_audio(self):
        """Inference with a real speaker embedding produces non-empty, finite audio."""
        session = _load_session()
        embedding = np.load(str(_SPEAKER_NPY))  # shape (192,) float32

        audio = _run(session, embedding)

        # Shape: [batch=1, channels=1, time>0]
        assert audio.ndim == 3, f"Expected 3-D output, got shape {audio.shape}"
        assert audio.shape[0] == 1, "Batch dimension should be 1"
        assert audio.shape[2] > 0, "Audio time dimension must be non-zero"

        # All samples must be finite (no NaN / Inf)
        assert np.all(np.isfinite(audio)), "Audio output contains non-finite values"

        # At least some non-zero samples (not silent)
        assert np.any(audio != 0.0), "Audio output is all zeros"

    @pytest.mark.inference
    def test_e2e_zero_shot_embedding_affects_output(self):
        """Two different speaker embeddings produce different audio outputs."""
        session = _load_session()

        embedding1 = np.load(str(_SPEAKER_NPY)).astype(np.float32)

        # Construct a clearly different embedding (independent random vector)
        rng = np.random.default_rng(seed=12345)
        embedding2 = rng.standard_normal(192).astype(np.float32)

        # Normalise so both embeddings have the same L2 norm
        embedding2 /= np.linalg.norm(embedding2) + 1e-8

        audio1 = _run(session, embedding1)
        audio2 = _run(session, embedding2)

        assert audio1.shape == audio2.shape, (
            f"Shapes differ: {audio1.shape} vs {audio2.shape}"
        )

        # The outputs must differ by at least some margin
        assert not np.allclose(audio1, audio2, atol=1e-6), (
            "Two different speaker embeddings produced identical audio — "
            "speaker conditioning appears to have no effect"
        )

    @pytest.mark.inference
    def test_e2e_zero_shot_zero_embedding(self):
        """A zero-vector speaker embedding does not crash and returns finite audio."""
        session = _load_session()
        zero_embedding = np.zeros(192, dtype=np.float32)

        # Should not raise any exception
        audio = _run(session, zero_embedding)

        assert audio.ndim == 3, f"Expected 3-D output, got shape {audio.shape}"
        assert audio.shape[2] > 0, "Audio time dimension must be non-zero"
        assert np.all(np.isfinite(audio)), (
            "Audio output contains non-finite values when using zero embedding"
        )
