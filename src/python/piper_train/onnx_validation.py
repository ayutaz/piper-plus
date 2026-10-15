"""Validate the actual exported bytes and execute deterministic warmup feeds."""

import logging
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort


def validate_export(path: Path, feeds: dict[str, np.ndarray]) -> list[np.ndarray]:
    """Fail on an invalid graph, an unloadable session, or empty/nonfinite output."""
    onnx.checker.check_model(onnx.load(str(path)), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(path), options, providers=["CPUExecutionProvider"]
    )
    inputs = {meta.name: feeds[meta.name] for meta in session.get_inputs()}
    outputs = session.run(None, inputs)
    if not outputs or any(
        value.size == 0 or not np.isfinite(value).all() for value in outputs
    ):
        raise ValueError(f"Export produced empty or nonfinite outputs: {path}")
    return outputs


def check_fp16_parity(
    reference: list[np.ndarray], converted: list[np.ndarray], tolerance: float = 1e-2
) -> bool:
    """Record warn-only parity, as specified by the export contract."""
    matches = len(reference) == len(converted) and all(
        before.shape == after.shape
        and np.max(np.abs(before.astype(np.float32) - after.astype(np.float32)))
        <= tolerance
        for before, after in zip(reference, converted, strict=False)
    )
    if not matches:
        logging.getLogger(__name__).warning(
            "FP32/FP16 warmup parity exceeds tolerance %s", tolerance
        )
    return matches
