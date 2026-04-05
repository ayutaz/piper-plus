"""ONNX Runtime session utilities.

Provides optimized SessionOptions matching the C#/Rust engine settings.
"""

import os

import onnxruntime

# VITS is a small model (15-75MB); more than 4 intra-op threads
# adds synchronization overhead that exceeds the parallelism benefit.
MAX_INTRA_THREADS = 4


def create_session_options() -> onnxruntime.SessionOptions:
    """Create an optimized SessionOptions for VITS inference.

    Settings are aligned with the C# (SessionFactory.cs) and
    Rust (engine.rs) implementations:
      - Graph optimization: ORT_ENABLE_ALL
      - Execution mode: SEQUENTIAL (VITS has a linear graph)
      - intra_op threads: min(physical_cores / 2, 4)
      - inter_op threads: 1
      - Memory arena/pattern/reuse: enabled
    """
    opts = onnxruntime.SessionOptions()

    # Graph optimization: constant folding, operator fusion, layout optimization
    opts.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    )

    # VITS has a linear graph with few parallel sub-graphs
    opts.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    # Thread settings matching C#/Rust engines
    physical_cores = os.cpu_count() or 2
    opts.intra_op_num_threads = min(physical_cores // 2 or 1, MAX_INTRA_THREADS)
    opts.inter_op_num_threads = 1

    # Memory optimization: pre-allocate and reuse buffers
    opts.enable_cpu_mem_arena = True
    opts.enable_mem_pattern = True
    opts.enable_mem_reuse = True

    return opts


def get_providers(device: str = "cpu") -> list[str]:
    """Return ONNX Runtime execution providers for the given device.

    Args:
        device: "cpu", "gpu", or "auto".
    """
    if device == "cpu":
        return ["CPUExecutionProvider"]
    # "auto" or "gpu": prefer CUDA, fall back to CPU
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]
