"""Parity fixture tests for zero-shot synthesis.

Validates that ``tests/fixtures/audio-corpus/parity/zero_shot_phoneme_ids.jsonl``
- parses cleanly with ``speaker_embedding`` field of shape (192,) float32, and
- when fed to the zero-shot test ONNX model, produces deterministic, distinguishable
  audio that downstream runtimes (Rust / Go / C# / WASM / C++) can use as the
  Python-side parity anchor.

Tests bypass G2P / ``PiperVoice`` and run raw ``onnxruntime.InferenceSession``
to avoid the espeak ``phoneme_type`` dependency of ``zero-shot-test.onnx.json``
(same approach as ``test_zero_shot_e2e.py``).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

try:
    import onnxruntime  # noqa: F401

    _ORT_AVAILABLE = True
except ImportError:
    _ORT_AVAILABLE = False

ort_skip = pytest.mark.skipif(
    not _ORT_AVAILABLE,
    reason="onnxruntime is not installed",
)

_REPO_ROOT = Path(__file__).parents[3]
_FIXTURE_PATH = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "audio-corpus"
    / "parity"
    / "zero_shot_phoneme_ids.jsonl"
)
_MODEL_DIR = _REPO_ROOT / "test" / "models"
_MODEL_PATH = _MODEL_DIR / "zero-shot-test.onnx"

fixture_skip = pytest.mark.skipif(
    not _FIXTURE_PATH.exists(),
    reason=f"zero-shot parity fixture missing at {_FIXTURE_PATH}",
)
model_skip = pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason=f"zero-shot test ONNX missing at {_MODEL_PATH}",
)


def _load_fixture_entries() -> list[dict]:
    """Read the JSONL fixture and return parsed entries."""
    entries: list[dict] = []
    with _FIXTURE_PATH.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _run_session(
    session: "onnxruntime.InferenceSession",
    phoneme_ids: list[int],
    embedding: np.ndarray,
) -> np.ndarray:
    """Run zero-shot inference and return float32 audio waveform [1, 1, T]."""
    ids = np.asarray(phoneme_ids, dtype=np.int64).reshape(1, -1)
    length = ids.shape[1]
    inputs = {
        "input": ids,
        "input_lengths": np.array([length], dtype=np.int64),
        "scales": np.array([0.4, 1.0, 0.5], dtype=np.float32),
        "prosody_features": np.zeros((1, length, 3), dtype=np.int64),
        "speaker_embedding": embedding.reshape(1, 192).astype(np.float32),
    }
    return session.run(None, inputs)[0]


class TestZeroShotParityFixture:
    """Python-side parity anchor for the zero-shot JSONL fixture."""

    @fixture_skip
    def test_reads_zero_shot_jsonl_fixture(self):
        """Each fixture line parses and yields a (192,) float32 embedding."""
        entries = _load_fixture_entries()

        assert entries, "fixture must contain at least one utterance"

        for idx, entry in enumerate(entries):
            assert "phoneme_ids" in entry, f"entry {idx} missing phoneme_ids"
            assert "speaker_embedding" in entry, (
                f"entry {idx} missing speaker_embedding"
            )

            emb = np.asarray(entry["speaker_embedding"], dtype=np.float32)
            assert emb.shape == (192,), (
                f"entry {idx} speaker_embedding shape {emb.shape}, expected (192,)"
            )
            assert emb.dtype == np.float32
            assert np.all(np.isfinite(emb)), (
                f"entry {idx} speaker_embedding contains non-finite values"
            )

            ids = entry["phoneme_ids"]
            assert isinstance(ids, list) and len(ids) >= 2, (
                f"entry {idx} phoneme_ids must be a non-empty list"
            )

    @ort_skip
    @fixture_skip
    @model_skip
    @pytest.mark.inference
    def test_python_synthesis_produces_reference_wav(self):
        """Python ORT inference on each fixture entry yields deterministic audio.

        We do not pin an exact golden sha256 here because the zero-shot test
        ONNX is rebuilt across CI environments; instead we assert that two
        independent runs on the same fixture entry produce byte-identical
        audio (the property the cross-runtime parity gate actually needs).
        """
        session = onnxruntime.InferenceSession(  # type: ignore[attr-defined]
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
        entries = _load_fixture_entries()

        for idx, entry in enumerate(entries):
            emb = np.asarray(entry["speaker_embedding"], dtype=np.float32)
            audio_a = _run_session(session, entry["phoneme_ids"], emb)
            audio_b = _run_session(session, entry["phoneme_ids"], emb)

            assert audio_a.shape == audio_b.shape
            assert audio_a.ndim == 3 and audio_a.shape[2] > 0, (
                f"entry {idx} produced empty audio"
            )
            assert np.all(np.isfinite(audio_a)), (
                f"entry {idx} produced non-finite audio"
            )

            # Determinism: identical inputs → byte-identical outputs.
            hash_a = hashlib.sha256(audio_a.tobytes()).hexdigest()
            hash_b = hashlib.sha256(audio_b.tobytes()).hexdigest()
            assert hash_a == hash_b, (
                f"entry {idx} synthesis is non-deterministic: {hash_a} vs {hash_b}"
            )

    @ort_skip
    @model_skip
    @pytest.mark.inference
    def test_different_embeddings_produce_different_audio(self):
        """Two distinct embeddings → distinguishable audio (RMS diff > threshold).

        Guards against silent-drop regressions of the ``speaker_embedding``
        input wiring (e.g. accidental zeroing in ``_synthesize_ids_core``).
        """
        session = onnxruntime.InferenceSession(  # type: ignore[attr-defined]
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )

        phoneme_ids = [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2]
        emb_a = np.zeros(192, dtype=np.float32)
        emb_b = np.ones(192, dtype=np.float32) / np.sqrt(192.0)

        audio_a = _run_session(session, phoneme_ids, emb_a).reshape(-1)
        audio_b = _run_session(session, phoneme_ids, emb_b).reshape(-1)

        assert audio_a.shape == audio_b.shape, (
            f"shape mismatch: {audio_a.shape} vs {audio_b.shape}"
        )

        rms_diff = float(np.sqrt(np.mean((audio_a - audio_b) ** 2)))
        assert rms_diff > 1e-4, (
            f"speaker_embedding appears to have no effect: rms_diff={rms_diff:.3e}"
        )
