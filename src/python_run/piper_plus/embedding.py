"""Speaker embedding validation shared by Python inference and training."""

from collections.abc import Iterable

import numpy as np


def embedding_dimension(inputs: Iterable, default: int = 192) -> int:
    """Read the graph's fixed feature dimension, preserving legacy 256 graphs."""
    for item in inputs:
        if item.name == "speaker_embedding":
            shape = item.shape
            if isinstance(shape, (list, tuple)) and len(shape) == 2:
                if isinstance(shape[1], int) and shape[1] > 0:
                    return shape[1]
            return default
    return default


def validate_embedding(values, dimension: int = 192) -> np.ndarray:
    """Return one finite, nonzero L2-normalized float32 speaker vector.

    Accept [D] or [1,D], never flatten an arbitrary tensor. A missing speaker
    condition is handled by the caller; an explicit zero vector is invalid.
    """
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("speaker_embedding must contain numeric values") from exc
    if vector.shape == (1, dimension):
        vector = vector[0]
    if vector.shape != (dimension,):
        raise ValueError(
            f"speaker_embedding must have shape ({dimension},) or (1, {dimension}), "
            f"got {vector.shape}"
        )
    if not np.isfinite(vector).all():
        raise ValueError("speaker_embedding must contain only finite values")
    # Scale before norm to avoid overflow even for finite float64 callers.
    peak = float(np.abs(vector).max())
    if peak == 0:
        raise ValueError("speaker_embedding must have nonzero norm")
    scaled = vector / peak
    scaled_norm = float(np.linalg.norm(scaled))
    if peak <= 1e-8 / scaled_norm:
        raise ValueError("speaker_embedding norm must exceed 1e-8")
    return np.ascontiguousarray(scaled / scaled_norm, dtype=np.float32)
