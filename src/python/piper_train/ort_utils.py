"""ONNX Runtime session utilities.

Provides optimized SessionOptions aligned with the C# (SessionFactory.cs)
and Rust (engine.rs) engine implementations.
"""

import logging
import os
import time
from pathlib import Path

import numpy as np
import onnxruntime


_LOGGER = logging.getLogger(__name__)


# VITS is a small model (15-75MB); more than 4 intra-op threads
# adds synchronization overhead that exceeds the parallelism benefit.
MAX_INTRA_THREADS = 4


def _get_logical_core_count() -> int:
    """Return logical core count, respecting Docker/cgroup CPU limits.

    On Linux, ``os.sched_getaffinity(0)`` reflects cgroup constraints
    (e.g. ``docker run --cpus=2``).  On Windows/macOS or when the
    syscall is unavailable, falls back to ``os.cpu_count()``.
    """
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 2


def create_session_options(
    *,
    intra_op_threads: int | None = None,
    inter_op_threads: int = 1,
) -> onnxruntime.SessionOptions:
    """Create an optimized SessionOptions for VITS inference.

    Settings are aligned with the C# (SessionFactory.cs) and
    Rust (engine.rs) implementations:

      - Graph optimization: ORT_ENABLE_ALL
      - Execution mode: SEQUENTIAL (VITS has a linear graph)
      - intra_op threads: min(logical_cores / 2, 4)
      - inter_op threads: 1
      - Memory arena/pattern/reuse: enabled

    Args:
        intra_op_threads: Override for intra-op thread count.  When *None*
            (the default), computed as ``min(logical_cores // 2, 4)``.
            The environment variable ``PIPER_INTRA_THREADS`` takes
            precedence over both this argument and the auto-detection.
        inter_op_threads: Inter-op thread count (default 1).  VITS has
            a linear graph with no parallel sub-graphs, so 1 is optimal.
    """
    opts = onnxruntime.SessionOptions()

    # Graph optimization: constant folding, operator fusion, layout optimization
    opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

    # VITS has a linear graph with few parallel sub-graphs
    opts.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    # Thread settings (matching C#/Rust engines)
    # Priority: PIPER_INTRA_THREADS env > intra_op_threads arg > auto-detect
    env_threads = os.environ.get("PIPER_INTRA_THREADS")
    if env_threads is not None:
        try:
            opts.intra_op_num_threads = max(1, min(int(env_threads), MAX_INTRA_THREADS))
        except ValueError:
            _LOGGER.warning(
                "Ignoring invalid PIPER_INTRA_THREADS=%r; using auto-detected thread count",
                env_threads,
            )
            env_threads = None  # fall through to auto-detect

    if env_threads is None and intra_op_threads is not None:
        opts.intra_op_num_threads = max(1, intra_op_threads)
    elif env_threads is None:
        # os.cpu_count() returns logical cores (incl. HyperThreading).
        # Dividing by 2 approximates physical core count.
        logical_cores = _get_logical_core_count()
        opts.intra_op_num_threads = min(logical_cores // 2 or 1, MAX_INTRA_THREADS)

    opts.inter_op_num_threads = inter_op_threads

    # Memory optimization: pre-allocate and reuse buffers
    opts.enable_cpu_mem_arena = True
    opts.enable_mem_pattern = True
    opts.enable_mem_reuse = True

    # Dynamic block sizing: split intra-op thread work into finer blocks
    # to reduce latency variance across runs.
    opts.add_session_config_entry("session.dynamic_block_base", "4")

    return opts


def get_providers(device: str = "cpu") -> list[str]:
    """Return ONNX Runtime execution providers for the given device.

    Args:
        device: ``"cpu"``, ``"gpu"``, or ``"auto"``.
    """
    if device == "cpu":
        return ["CPUExecutionProvider"]
    # "auto" or "gpu": prefer CUDA when available, otherwise fall back to CPU
    available = onnxruntime.get_available_providers()
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


# ---------------------------------------------------------------------------
# Optimized model cache
# ---------------------------------------------------------------------------


def _get_device_label(device: str) -> str:
    """Return effective device label for cache path (e.g., 'cpu', 'cuda0')."""
    if device in ("gpu", "auto"):
        available = onnxruntime.get_available_providers()
        if "CUDAExecutionProvider" in available:
            return "cuda0"
    return "cpu"


def _build_cache_paths(model_path: str | Path, device_label: str) -> tuple[Path, Path]:
    """Return (cache_path, sentinel_path) for the optimized model cache."""
    model_p = Path(model_path)
    cache_path = model_p.with_suffix(f".{device_label}.opt.onnx")
    sentinel_path = Path(str(cache_path) + ".ok")
    return cache_path, sentinel_path


# NOTE: voice.py (python_run) にインライン複製あり。変更時は両方更新すること
def create_session_with_cache(
    model_path: str | Path,
    *,
    device: str = "cpu",
    intra_op_threads: int | None = None,
    inter_op_threads: int = 1,
) -> onnxruntime.InferenceSession:
    """Create an InferenceSession with optimized model caching.

    On first load, ORT graph optimizations are saved to a ``.opt.onnx`` file.
    Subsequent loads skip optimization by loading the cached model directly
    with ``ORT_DISABLE_ALL``.  A sentinel file (``.ok``) guards against
    incomplete caches from interrupted processes.

    Set ``PIPER_DISABLE_CACHE=1`` to bypass caching entirely.
    """
    opts = create_session_options(
        intra_op_threads=intra_op_threads,
        inter_op_threads=inter_op_threads,
    )
    providers = get_providers(device)

    # Cache disabled via env var
    if os.environ.get("PIPER_DISABLE_CACHE", "").lower() in ("1", "true", "yes"):
        _LOGGER.info("Model cache disabled via PIPER_DISABLE_CACHE")
        return onnxruntime.InferenceSession(
            str(model_path), sess_options=opts, providers=providers
        )

    device_label = _get_device_label(device)
    cache_path, sentinel_path = _build_cache_paths(model_path, device_label)

    # Cache hit: both .opt.onnx and .ok exist
    if cache_path.exists() and sentinel_path.exists():
        _LOGGER.info("Loading pre-optimized model from %s", cache_path)
        opts.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
        )
        try:
            return onnxruntime.InferenceSession(
                str(cache_path), sess_options=opts, providers=providers
            )
        except Exception as e:
            _LOGGER.warning(
                "Failed to load cached model %s: %s — rebuilding cache",
                cache_path,
                e,
            )
            # Fall through to re-optimize
            try:
                cache_path.unlink(missing_ok=True)
                sentinel_path.unlink(missing_ok=True)
            except OSError:
                pass
            # Reset optimization level for re-optimization
            opts.graph_optimization_level = (
                onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
            )

    # Incomplete cache: .opt.onnx exists but .ok missing
    if cache_path.exists() and not sentinel_path.exists():
        _LOGGER.warning("Removing incomplete cache %s (missing sentinel)", cache_path)
        try:
            cache_path.unlink()
        except OSError:
            pass

    # First run or cache rebuild
    _cache_requested = False
    cache_dir = cache_path.parent
    if os.access(cache_dir, os.W_OK):
        try:
            opts.optimized_model_filepath = str(cache_path)
            _cache_requested = True
        except Exception as exc:
            _LOGGER.warning(
                "Could not set optimized model path %s: %s (continuing without cache)",
                cache_path,
                exc,
            )
    else:
        _LOGGER.info(
            "Model directory %s is not writable, skipping ORT cache", cache_dir
        )

    session = onnxruntime.InferenceSession(
        str(model_path), sess_options=opts, providers=providers
    )

    # Write sentinel only if we actually requested cache generation
    if _cache_requested and cache_path.exists():
        try:
            sentinel_path.write_text("ok")
            _LOGGER.info("Cache sentinel written: %s", sentinel_path)
        except OSError as exc:
            _LOGGER.warning("Failed to write sentinel %s: %s", sentinel_path, exc)

    return session


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

WARMUP_PHONEME_LENGTH = 100
DEFAULT_WARMUP_RUNS = 2


def warmup_onnx_session(
    session: onnxruntime.InferenceSession,
    *,
    runs: int = DEFAULT_WARMUP_RUNS,
    phoneme_length: int = WARMUP_PHONEME_LENGTH,
) -> None:
    """Run dummy inference to trigger ORT graph optimisation and memory allocation.

    The first inference through an ONNX Runtime session is significantly
    slower because lazy optimisations and arena allocation happen at that
    point.  Running a small dummy input before real traffic eliminates
    that cold-start penalty.

    Set the environment variable ``PIPER_DISABLE_WARMUP=1`` to skip.
    """
    if os.environ.get("PIPER_DISABLE_WARMUP", "").lower() in ("1", "true", "yes"):
        return
    if runs <= 0:
        return
    try:
        # Dummy input: fill with phoneme ID 8, bookend with BOS=1 / EOS=2
        phoneme_ids = np.full((1, phoneme_length), 8, dtype=np.int64)
        phoneme_ids[0, 0] = 1  # BOS
        phoneme_ids[0, -1] = 2  # EOS
        input_lengths = np.array([phoneme_length], dtype=np.int64)
        scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

        # Detect optional inputs dynamically
        input_names = {inp.name for inp in session.get_inputs()}
        inputs: dict[str, np.ndarray] = {
            "input": phoneme_ids,
            "input_lengths": input_lengths,
            "scales": scales,
        }
        if "sid" in input_names:
            inputs["sid"] = np.array([0], dtype=np.int64)
        if "lid" in input_names:
            inputs["lid"] = np.array([0], dtype=np.int64)
        if "prosody_features" in input_names:
            inputs["prosody_features"] = np.zeros(
                (1, phoneme_length, 3), dtype=np.int64
            )
        if "speaker_embedding" in input_names:
            emb_dim = 256
            for inp in session.get_inputs():
                if inp.name == "speaker_embedding":
                    if len(inp.shape) >= 2 and isinstance(inp.shape[1], int):
                        emb_dim = inp.shape[1]
                    break
            inputs["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
            inputs["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)

        output_names = [o.name for o in session.get_outputs()]
        t0 = time.perf_counter()
        for _i in range(runs):
            session.run(output_names, inputs)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _LOGGER.info("Warmup completed (%d runs in %.0fms)", runs, elapsed_ms)
    except Exception as e:
        _LOGGER.warning("Warmup failed (non-fatal): %s", e)
