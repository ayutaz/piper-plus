#!/usr/bin/env python3
"""Validate a PE-A style bank ``.npz`` file for schema and numerical sanity.

Validation rules (see ``docs/features/style-bank.md``)::

    1. The archive contains the three required keys:
         emotion_names, emotion_centroids, global_centroid
    2. ``emotion_names`` is a 1-D object array of non-empty, unique strings.
    3. ``emotion_centroids`` is ``float32`` with shape ``[N, D]``.
    4. ``global_centroid``    is ``float32`` with shape ``[D]``.
    5. ``N == len(emotion_names)`` and the two centroid arrays share ``D``.
    6. Each row of ``emotion_centroids`` has an L2 norm of ``1.0 ± 1e-3``.
    7. No ``NaN`` / ``Inf`` values anywhere.
    8. ``global_centroid`` is close to ``mean(emotion_centroids)`` in cosine
       similarity (>= 0.99). This is a *warning* by default because the
       fork's build pipeline keeps the raw (non-normalised) mean here, which
       can yield lower similarity when the per-emotion means differ in
       magnitude before normalisation; ``--strict`` upgrades it to an error.

Exit codes::

    0 — PASS (plus possible non-strict warnings)
    1 — FAIL (at least one validation rule broken)

CLI example::

    uv run python -m piper_train.tools.validate_style_bank \\
        --style-bank /data/piper/style_bank_crema_d.npz \\
        --expected-emotions angry disgusted fearful happy neutral sad \\
        --expected-dim 512
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

_LOGGER = logging.getLogger("validate_style_bank")

REQUIRED_KEYS = ("emotion_names", "emotion_centroids", "global_centroid")
L2_NORM_TOLERANCE = 1e-3
GLOBAL_CENTROID_COSSIM_THRESHOLD = 0.99


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------


def load_style_bank(path: Path) -> dict[str, Any]:
    archive = np.load(str(path), allow_pickle=True)
    return {key: archive[key] for key in archive.files}


def check_schema(bank: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in bank:
            errors.append(f"Missing key: {key}")
    if errors:
        return errors  # Can't check further without the arrays

    names = bank["emotion_names"]
    centroids = bank["emotion_centroids"]
    global_c = bank["global_centroid"]

    if names.dtype != object:
        errors.append(
            f"emotion_names dtype must be object (str), got {names.dtype}"
        )
    if names.ndim != 1:
        errors.append(f"emotion_names must be 1-D, got {names.ndim}-D")

    if centroids.dtype != np.float32:
        errors.append(
            f"emotion_centroids dtype must be float32, got {centroids.dtype}"
        )
    if centroids.ndim != 2:
        errors.append(
            f"emotion_centroids must be 2-D [N, D], got {centroids.ndim}-D"
        )

    if global_c.dtype != np.float32:
        errors.append(
            f"global_centroid dtype must be float32, got {global_c.dtype}"
        )
    if global_c.ndim != 1:
        errors.append(f"global_centroid must be 1-D, got {global_c.ndim}-D")

    if centroids.ndim == 2 and names.ndim == 1:
        if centroids.shape[0] != names.shape[0]:
            errors.append(
                "Mismatch: emotion_centroids.shape[0]={} vs len(emotion_names)={}".format(
                    centroids.shape[0], names.shape[0]
                )
            )
    if centroids.ndim == 2 and global_c.ndim == 1:
        if centroids.shape[1] != global_c.shape[0]:
            errors.append(
                "Embedding dim mismatch: emotion_centroids={} vs global_centroid={}".format(
                    centroids.shape[1], global_c.shape[0]
                )
            )
    return errors


def check_nan_inf(bank: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("emotion_centroids", "global_centroid"):
        arr = bank.get(key)
        if arr is None:
            continue
        if not np.isfinite(arr).all():
            errors.append(f"{key} contains NaN or Inf values")
    return errors


def check_l2_norm(
    centroids: np.ndarray, tolerance: float = L2_NORM_TOLERANCE
) -> list[str]:
    errors: list[str] = []
    if centroids.size == 0:
        return errors
    norms = np.linalg.norm(centroids, axis=-1)
    for i, norm in enumerate(norms):
        if not np.isfinite(norm):
            errors.append(f"emotion_centroids row {i} has non-finite norm: {norm}")
            continue
        if abs(float(norm) - 1.0) > tolerance:
            errors.append(
                f"emotion_centroids row {i} L2 norm = {norm:.6f} "
                f"(expected 1.0 ± {tolerance})"
            )
    return errors


def check_global_centroid_consistency(
    centroids: np.ndarray,
    global_centroid: np.ndarray,
) -> list[str]:
    """Compare ``global_centroid`` against ``mean(emotion_centroids)``.

    Returns a *warning list* (strings). Caller decides whether to treat them
    as fatal.
    """
    if centroids.size == 0:
        return []
    mean_vec = centroids.mean(axis=0)
    mean_norm = float(np.linalg.norm(mean_vec))
    gc_norm = float(np.linalg.norm(global_centroid))
    if mean_norm == 0 or gc_norm == 0:
        return ["global_centroid consistency not computable: zero-norm vector"]
    cos_sim = float(np.dot(mean_vec, global_centroid) / (mean_norm * gc_norm))
    warnings: list[str] = []
    if cos_sim < GLOBAL_CENTROID_COSSIM_THRESHOLD:
        warnings.append(
            "global_centroid vs mean(emotion_centroids) cos_sim = "
            f"{cos_sim:.4f} (< {GLOBAL_CENTROID_COSSIM_THRESHOLD}). "
            "This is expected if global_centroid was computed from raw "
            "embeddings (not L2-normalised)."
        )
    return warnings


def check_emotion_names(names: np.ndarray) -> list[str]:
    errors: list[str] = []
    str_names = [str(n) for n in names.tolist()]
    if len(set(str_names)) != len(str_names):
        errors.append(
            "Duplicate emotion names found: " + ", ".join(sorted(set(str_names)))
        )
    for i, name in enumerate(str_names):
        stripped = name.strip()
        if not stripped:
            errors.append(f"emotion_names[{i}] is empty or whitespace")
        if any(ord(c) > 127 and not c.isalnum() for c in name):
            # Non-fatal; just log at info.
            _LOGGER.info("emotion_names[%d] contains non-ASCII chars: %r", i, name)
    return errors


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate(
    style_bank_path: Path,
    *,
    strict: bool = False,
    expected_emotions: Optional[list[str]] = None,
    expected_dim: Optional[int] = None,
) -> int:
    _LOGGER.info("Validating: %s", style_bank_path)
    bank = load_style_bank(style_bank_path)

    schema_errors = check_schema(bank)
    if schema_errors:
        for err in schema_errors:
            _LOGGER.error(err)
        return 1

    names = bank["emotion_names"]
    centroids = bank["emotion_centroids"]
    global_c = bank["global_centroid"]

    str_names = [str(n) for n in names.tolist()]
    _LOGGER.info("  emotion_names: %s", str_names)
    _LOGGER.info("  emotion_centroids.shape: %s", centroids.shape)
    _LOGGER.info("  global_centroid.shape: %s", global_c.shape)

    name_errors = check_emotion_names(names)
    for err in name_errors:
        _LOGGER.error(err)
    if name_errors:
        return 1

    finite_errors = check_nan_inf(bank)
    for err in finite_errors:
        _LOGGER.error(err)
    if finite_errors:
        return 1

    norm_errors = check_l2_norm(centroids)
    for err in norm_errors:
        _LOGGER.error(err)
    if norm_errors:
        return 1

    consistency_warnings = check_global_centroid_consistency(centroids, global_c)
    for warn in consistency_warnings:
        if strict:
            _LOGGER.error(warn)
        else:
            _LOGGER.warning(warn)
    if strict and consistency_warnings:
        return 1

    if expected_emotions:
        missing = set(expected_emotions) - set(str_names)
        if missing:
            _LOGGER.error("Missing expected emotions: %s", sorted(missing))
            return 1

    if expected_dim is not None and centroids.shape[1] != expected_dim:
        _LOGGER.error(
            "Embedding dim %d != expected %d", centroids.shape[1], expected_dim
        )
        return 1

    _LOGGER.info("Validation PASSED")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_argv(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a PE-A style bank .npz for schema and numerical correctness",
    )
    parser.add_argument("--style-bank", type=Path, required=True)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat non-fatal warnings as errors (affects global_centroid consistency)",
    )
    parser.add_argument(
        "--expected-emotions",
        nargs="+",
        default=None,
        help="Assert the presence of these emotion labels",
    )
    parser.add_argument(
        "--expected-dim",
        type=int,
        default=None,
        help="Assert the embedding dimension matches this value",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_argv(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return validate(
        args.style_bank,
        strict=args.strict,
        expected_emotions=args.expected_emotions,
        expected_dim=args.expected_dim,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
