"""ONNX Runtime session utilities.

Provides optimized SessionOptions aligned with the C# (SessionFactory.cs)
and Rust (engine.rs) engine implementations.
"""

import os

import onnxruntime

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
    opts.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    )

    # VITS has a linear graph with few parallel sub-graphs
    opts.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    # Thread settings (matching C#/Rust engines)
    # Priority: PIPER_INTRA_THREADS env > intra_op_threads arg > auto-detect
    env_threads = os.environ.get("PIPER_INTRA_THREADS")
    if env_threads is not None:
        opts.intra_op_num_threads = int(env_threads)
    elif intra_op_threads is not None:
        opts.intra_op_num_threads = intra_op_threads
    else:
        # os.cpu_count() returns logical cores (incl. HyperThreading).
        # Dividing by 2 approximates physical core count.
        logical_cores = _get_logical_core_count()
        opts.intra_op_num_threads = min(
            logical_cores // 2 or 1, MAX_INTRA_THREADS
        )

    opts.inter_op_num_threads = inter_op_threads

    # Memory optimization: pre-allocate and reuse buffers
    opts.enable_cpu_mem_arena = True
    opts.enable_mem_pattern = True
    opts.enable_mem_reuse = True

    return opts


def get_providers(device: str = "cpu") -> list[str]:
    """Return ONNX Runtime execution providers for the given device.

    Args:
        device: ``"cpu"``, ``"gpu"``, or ``"auto"``.
    """
    if device == "cpu":
        return ["CPUExecutionProvider"]
    # "auto" or "gpu": prefer CUDA, fall back to CPU
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]
