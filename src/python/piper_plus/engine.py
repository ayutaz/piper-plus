"""piper-plus inference engine -- standalone ONNX inference without piper_train dependency.

This module provides the core ONNX inference pipeline used by both the
``PiperPlus`` high-level API and the Wyoming adapter.  It depends only on
``numpy``, ``onnxruntime``, and the Python standard library -- no
``piper_train`` imports.

Session settings follow ``docs/spec/ort-session-contract.toml``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


logger = logging.getLogger(__name__)

# VITS is a small model (15-75 MB); more than 4 intra-op threads adds
# synchronization overhead that exceeds the parallelism benefit.
MAX_INTRA_THREADS = 4


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Clip and convert float32 audio to int16 PCM."""
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * max_wav_value).astype(np.int16)


def load_config(config_path: str | Path) -> dict:
    """Load a model ``config.json`` file."""
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def get_sample_rate(config: dict) -> int:
    """Return the audio sample rate from a config dict (default 22050)."""
    return config.get("audio", {}).get("sample_rate", 22050)


def get_language_id_map(config: dict) -> dict[str, int]:
    """Return the language-to-ID mapping from a config dict."""
    return config.get("language_id_map", {})


def get_speaker_id_map(config: dict) -> dict[str, int]:
    """Return the speaker name-to-ID mapping from a config dict."""
    return config.get("speaker_id_map", {})


# ---------------------------------------------------------------------------
# ORT session creation
# ---------------------------------------------------------------------------


def _get_logical_core_count() -> int:
    """Return logical core count, respecting Docker/cgroup CPU limits."""
    try:
        return len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return os.cpu_count() or 2


def _get_providers(device: str = "cpu") -> list[str | tuple[str, dict]]:
    """Return ONNX Runtime execution providers for *device*.

    *device* may be ``"cpu"``, ``"gpu"``, ``"cuda"``, ``"cuda:N"``, or
    ``"auto"``.
    """
    if device == "cpu":
        return ["CPUExecutionProvider"]

    providers: list[str | tuple[str, dict]] = []

    if device.startswith("cuda"):
        device_id = "0"
        if ":" in device:
            device_id = device.split(":", 1)[1]
        providers.append(("CUDAExecutionProvider", {"device_id": device_id}))
    elif device in ("gpu", "auto"):
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")

    providers.append("CPUExecutionProvider")
    return providers


def create_ort_session(
    model_path: str | Path,
    *,
    device: str = "cpu",
    intra_threads: int | None = None,
) -> ort.InferenceSession:
    """Create an optimized ORT inference session.

    Settings follow ``docs/spec/ort-session-contract.toml``:

    * ``graph_optimization_level``: ``ORT_ENABLE_ALL``
    * ``execution_mode``: ``ORT_SEQUENTIAL``
    * ``intra_op_num_threads``: ``min(logical_cores // 2, 4)``
    * ``inter_op_num_threads``: ``1``
    * Memory arena and pattern: enabled

    The environment variable ``PIPER_INTRA_THREADS`` overrides
    *intra_threads* and auto-detection.

    Args:
        model_path: Path to ``.onnx`` model file.
        device: ``"cpu"``, ``"gpu"``, ``"cuda"``, ``"cuda:N"``, or ``"auto"``.
        intra_threads: Override for intra-op thread count.
    """
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    # Thread settings -- priority: env > arg > auto-detect
    env_threads = os.environ.get("PIPER_INTRA_THREADS")
    resolved_threads: int | None = None
    if env_threads is not None:
        try:
            resolved_threads = max(1, min(int(env_threads), MAX_INTRA_THREADS))
        except ValueError:
            logger.warning(
                "Ignoring invalid PIPER_INTRA_THREADS=%r; using auto-detected value",
                env_threads,
            )

    if resolved_threads is None and intra_threads is not None:
        resolved_threads = max(1, intra_threads)

    if resolved_threads is None:
        logical_cores = _get_logical_core_count()
        resolved_threads = min(logical_cores // 2 or 1, MAX_INTRA_THREADS)

    opts.intra_op_num_threads = resolved_threads
    opts.inter_op_num_threads = 1

    opts.enable_cpu_mem_arena = True
    opts.enable_mem_pattern = True

    # Dynamic block sizing -- reduce latency variance across runs.
    opts.add_session_config_entry("session.dynamic_block_base", "4")

    providers = _get_providers(device)

    return ort.InferenceSession(str(model_path), opts, providers=providers)


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

WARMUP_PHONEME_LENGTH = 100
DEFAULT_WARMUP_RUNS = 2


def warmup_session(
    session: ort.InferenceSession,
    config: dict | None = None,
    *,
    runs: int = DEFAULT_WARMUP_RUNS,
) -> None:
    """Run *runs* dummy inferences to eliminate JIT cold-start latency.

    Set ``PIPER_DISABLE_WARMUP=1`` to skip.
    """
    if os.environ.get("PIPER_DISABLE_WARMUP", "").lower() in ("1", "true", "yes"):
        return
    if runs <= 0:
        return

    try:
        input_names = {inp.name for inp in session.get_inputs()}
        dummy_ids = np.full((1, WARMUP_PHONEME_LENGTH), 8, dtype=np.int64)
        dummy_ids[0, 0] = 1  # BOS
        dummy_ids[0, -1] = 2  # EOS
        dummy_lengths = np.array([WARMUP_PHONEME_LENGTH], dtype=np.int64)
        dummy_scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

        feed: dict[str, np.ndarray] = {
            "input": dummy_ids,
            "input_lengths": dummy_lengths,
            "scales": dummy_scales,
        }
        if "sid" in input_names:
            feed["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            feed["lid"] = np.array([0], dtype=np.int64)
        if "prosody_features" in input_names:
            feed["prosody_features"] = np.zeros(
                (1, WARMUP_PHONEME_LENGTH, 3), dtype=np.int64
            )

        output_names = [o.name for o in session.get_outputs()]
        t0 = time.perf_counter()
        for _ in range(runs):
            session.run(output_names, feed)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info("Warmup completed (%d runs in %.0f ms)", runs, elapsed_ms)
    except Exception as exc:
        logger.warning("Warmup failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def synthesize(
    session: ort.InferenceSession,
    phoneme_ids: list[int],
    *,
    config: dict | None = None,
    speaker_id: int = 0,
    language_id: int | None = None,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_w: float = 0.8,
    prosody_features: list[dict | None] | None = None,
) -> np.ndarray:
    """Run ONNX inference and return **int16** PCM audio samples.

    Args:
        session: ORT inference session created by :func:`create_ort_session`.
        phoneme_ids: List of phoneme IDs (including BOS/EOS).
        config: Model config dict -- currently unused but reserved for
            future extensions.
        speaker_id: Speaker ID for multi-speaker models.
        language_id: Language ID for multilingual models.
        noise_scale: Audio variation control.
        length_scale: Speaking speed (smaller = faster).
        noise_w: Phoneme duration variation.
        prosody_features: Per-phoneme ``{"a1": int, "a2": int, "a3": int}``
            dicts (or *None* entries).  Padded/truncated to match
            *phoneme_ids* length.

    Returns:
        1-D ``int16`` numpy array of PCM audio samples.
    """
    if not phoneme_ids:
        return np.array([], dtype=np.int16)

    input_names = {inp.name for inp in session.get_inputs()}

    ids = np.array([phoneme_ids], dtype=np.int64)
    lengths = np.array([len(phoneme_ids)], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_w], dtype=np.float32)

    feed: dict[str, np.ndarray] = {
        "input": ids,
        "input_lengths": lengths,
        "scales": scales,
    }

    if "sid" in input_names:
        feed["sid"] = np.array([speaker_id], dtype=np.int64)

    if "lid" in input_names and language_id is not None:
        feed["lid"] = np.array([language_id], dtype=np.int64)

    if "prosody_features" in input_names:
        seq_len = len(phoneme_ids)
        if prosody_features:
            rows: list[list[int]] = []
            for pf in prosody_features:
                if pf is None:
                    rows.append([0, 0, 0])
                else:
                    rows.append([pf.get("a1", 0), pf.get("a2", 0), pf.get("a3", 0)])
            prosody_array = np.array(rows, dtype=np.int64)
            # Pad or truncate to match sequence length
            if len(prosody_array) < seq_len:
                padding = np.zeros((seq_len - len(prosody_array), 3), dtype=np.int64)
                prosody_array = np.concatenate([prosody_array, padding])
            elif len(prosody_array) > seq_len:
                prosody_array = prosody_array[:seq_len]
            feed["prosody_features"] = prosody_array.reshape(1, seq_len, 3)
        else:
            feed["prosody_features"] = np.zeros((1, seq_len, 3), dtype=np.int64)

    # Run inference
    output = session.run(None, feed)[0]

    # Squeeze batch and channel dimensions
    audio_float = output.squeeze()

    return audio_float_to_int16(audio_float)


def synthesize_float(
    session: ort.InferenceSession,
    phoneme_ids: list[int],
    *,
    speaker_id: int = 0,
    language_id: int | None = None,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_w: float = 0.8,
    prosody_features: list[dict | None] | None = None,
) -> np.ndarray:
    """Like :func:`synthesize` but return **float32** audio in [-1, 1].

    Useful when the caller needs to do further DSP before final conversion.
    """
    if not phoneme_ids:
        return np.array([], dtype=np.float32)

    input_names = {inp.name for inp in session.get_inputs()}

    ids = np.array([phoneme_ids], dtype=np.int64)
    lengths = np.array([len(phoneme_ids)], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_w], dtype=np.float32)

    feed: dict[str, np.ndarray] = {
        "input": ids,
        "input_lengths": lengths,
        "scales": scales,
    }

    if "sid" in input_names:
        feed["sid"] = np.array([speaker_id], dtype=np.int64)

    if "lid" in input_names and language_id is not None:
        feed["lid"] = np.array([language_id], dtype=np.int64)

    if "prosody_features" in input_names:
        seq_len = len(phoneme_ids)
        if prosody_features:
            rows = []
            for pf in prosody_features:
                if pf is None:
                    rows.append([0, 0, 0])
                else:
                    rows.append([pf.get("a1", 0), pf.get("a2", 0), pf.get("a3", 0)])
            prosody_array = np.array(rows, dtype=np.int64)
            if len(prosody_array) < seq_len:
                padding = np.zeros((seq_len - len(prosody_array), 3), dtype=np.int64)
                prosody_array = np.concatenate([prosody_array, padding])
            elif len(prosody_array) > seq_len:
                prosody_array = prosody_array[:seq_len]
            feed["prosody_features"] = prosody_array.reshape(1, seq_len, 3)
        else:
            feed["prosody_features"] = np.zeros((1, seq_len, 3), dtype=np.int64)

    output = session.run(None, feed)[0]
    return np.clip(output.squeeze(), -1.0, 1.0).astype(np.float32)
