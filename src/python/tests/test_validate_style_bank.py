"""Unit tests for ``piper_train.tools.validate_style_bank`` (Phase 3 P3-T04)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from piper_train.tools import validate_style_bank as validator


def _make_good_bank(tmp_path: Path, dim: int = 8) -> Path:
    """Write a well-formed .npz file and return its path."""
    centroids = np.zeros((3, dim), dtype=np.float32)
    for i in range(3):
        v = np.random.default_rng(i).standard_normal(dim).astype(np.float32)
        centroids[i] = v / np.linalg.norm(v)
    global_c = centroids.mean(axis=0)
    global_c = global_c / max(np.linalg.norm(global_c), 1e-10)
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry", "happy", "sad"], dtype=object),
        emotion_centroids=centroids,
        global_centroid=global_c.astype(np.float32),
    )
    return path


# =============================================================================
# Schema checks
# =============================================================================


@pytest.mark.unit
def test_validate_full_pipeline_pass(tmp_path: Path):
    """Well-formed bank passes validation with exit code 0."""
    path = _make_good_bank(tmp_path)
    assert validator.validate(path) == 0


@pytest.mark.unit
def test_schema_missing_key(tmp_path: Path):
    """Missing required keys are fatal."""
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_centroids=np.zeros((2, 4), dtype=np.float32),
        global_centroid=np.zeros(4, dtype=np.float32),
    )
    assert validator.validate(path) == 1


@pytest.mark.unit
def test_schema_wrong_dtype(tmp_path: Path):
    """``emotion_centroids`` stored as float64 is fatal."""
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry"], dtype=object),
        emotion_centroids=np.ones((1, 4), dtype=np.float64),
        global_centroid=np.ones(4, dtype=np.float32),
    )
    assert validator.validate(path) == 1


@pytest.mark.unit
def test_schema_shape_mismatch(tmp_path: Path):
    """Mismatch between ``len(emotion_names)`` and ``emotion_centroids.shape[0]``."""
    centroids = np.zeros((3, 4), dtype=np.float32)
    for i in range(3):
        centroids[i, i] = 1.0
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry", "happy"], dtype=object),  # 2 vs 3
        emotion_centroids=centroids,
        global_centroid=np.ones(4, dtype=np.float32) / 2,
    )
    assert validator.validate(path) == 1


@pytest.mark.unit
def test_schema_embedding_dim_mismatch(tmp_path: Path):
    """emotion_centroids and global_centroid must share dimension."""
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["a", "b"], dtype=object),
        emotion_centroids=np.eye(2, dtype=np.float32),
        global_centroid=np.zeros(3, dtype=np.float32),  # different D
    )
    assert validator.validate(path) == 1


# =============================================================================
# L2 norm
# =============================================================================


@pytest.mark.unit
def test_l2_norm_pass():
    """Pure L2-normalised rows pass the L2 check."""
    centroids = np.eye(3, dtype=np.float32)
    assert validator.check_l2_norm(centroids) == []


@pytest.mark.unit
def test_l2_norm_fail():
    """Rows whose norm deviates from 1 are reported."""
    centroids = np.array([[2.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    errors = validator.check_l2_norm(centroids)
    assert len(errors) == 1
    assert "L2 norm = 2" in errors[0]


@pytest.mark.unit
def test_l2_norm_tolerance():
    """The tolerance parameter controls the acceptable deviation."""
    centroids = np.array([[1.01, 0.0]], dtype=np.float32)
    assert validator.check_l2_norm(centroids, tolerance=0.05) == []
    assert validator.check_l2_norm(centroids, tolerance=1e-4) != []


# =============================================================================
# NaN / Inf
# =============================================================================


@pytest.mark.unit
def test_rejects_nan(tmp_path: Path):
    """NaN values in centroids fail validation."""
    centroids = np.eye(2, dtype=np.float32)
    centroids[0, 0] = np.nan
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry", "happy"], dtype=object),
        emotion_centroids=centroids,
        global_centroid=np.ones(2, dtype=np.float32) / np.sqrt(2),
    )
    assert validator.validate(path) == 1


@pytest.mark.unit
def test_rejects_inf(tmp_path: Path):
    """Inf values in global_centroid fail validation."""
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry"], dtype=object),
        emotion_centroids=np.eye(1, 2, dtype=np.float32),
        global_centroid=np.array([np.inf, 0.0], dtype=np.float32),
    )
    assert validator.validate(path) == 1


# =============================================================================
# Global centroid consistency
# =============================================================================


@pytest.mark.unit
def test_global_centroid_consistency_pass():
    """Exactly-matching global vs mean(emotion) -> no warnings."""
    centroids = np.eye(2, dtype=np.float32)
    global_c = centroids.mean(axis=0)
    warnings = validator.check_global_centroid_consistency(centroids, global_c)
    assert warnings == []


@pytest.mark.unit
def test_global_centroid_consistency_raw_mean_warns():
    """When global_centroid diverges from the centroid mean, a warning is emitted."""
    centroids = np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32)
    global_c = np.array([0.0, 1.0], dtype=np.float32)
    warnings = validator.check_global_centroid_consistency(centroids, global_c)
    assert len(warnings) == 1
    assert "cos_sim" in warnings[0]


@pytest.mark.unit
def test_strict_upgrades_global_warning(tmp_path: Path):
    """``strict=True`` turns the global-consistency warning into a failure."""
    centroids = np.array([[1.0, 0.0], [0.99, 0.01]], dtype=np.float32)
    centroids[0] /= np.linalg.norm(centroids[0])
    centroids[1] /= np.linalg.norm(centroids[1])
    global_c = np.array([0.0, 1.0], dtype=np.float32)
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["a", "b"], dtype=object),
        emotion_centroids=centroids,
        global_centroid=global_c,
    )
    assert validator.validate(path) == 0  # non-strict: warning only
    assert validator.validate(path, strict=True) == 1


# =============================================================================
# Emotion names
# =============================================================================


@pytest.mark.unit
def test_emotion_names_duplicate(tmp_path: Path):
    """Duplicate emotion names are fatal."""
    centroids = np.eye(2, dtype=np.float32)
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry", "angry"], dtype=object),
        emotion_centroids=centroids,
        global_centroid=centroids.mean(axis=0).astype(np.float32),
    )
    assert validator.validate(path) == 1


@pytest.mark.unit
def test_emotion_names_empty(tmp_path: Path):
    """Empty / whitespace-only emotion labels are fatal."""
    centroids = np.eye(2, dtype=np.float32)
    path = tmp_path / "bank.npz"
    np.savez(
        str(path),
        emotion_names=np.array(["angry", "   "], dtype=object),
        emotion_centroids=centroids,
        global_centroid=centroids.mean(axis=0).astype(np.float32),
    )
    assert validator.validate(path) == 1


# =============================================================================
# CLI
# =============================================================================


@pytest.mark.unit
def test_expected_emotions_missing_fails(tmp_path: Path):
    """When ``--expected-emotions`` lists a missing label, validation fails."""
    path = _make_good_bank(tmp_path)  # angry / happy / sad
    assert (
        validator.validate(path, expected_emotions=["angry", "happy", "fearful"]) == 1
    )


@pytest.mark.unit
def test_expected_dim_mismatch_fails(tmp_path: Path):
    """``--expected-dim`` asserts the embedding dimension."""
    path = _make_good_bank(tmp_path, dim=8)
    assert validator.validate(path, expected_dim=16) == 1


@pytest.mark.unit
def test_expected_dim_match_passes(tmp_path: Path):
    """The matching ``--expected-dim`` does not fail."""
    path = _make_good_bank(tmp_path, dim=8)
    assert validator.validate(path, expected_dim=8) == 0


@pytest.mark.unit
def test_main_cli_exit_codes(tmp_path: Path):
    """``main()`` returns the numeric exit code so CI can gate PRs."""
    good = _make_good_bank(tmp_path)
    assert validator.main(["--style-bank", str(good)]) == 0

    bad = tmp_path / "bad.npz"
    np.savez(str(bad), emotion_centroids=np.ones((1, 4), dtype=np.float32))
    assert validator.main(["--style-bank", str(bad)]) == 1


@pytest.mark.unit
def test_main_cli_with_expected_emotions_and_dim(tmp_path: Path):
    """CLI plumbs through ``--expected-emotions`` and ``--expected-dim``."""
    path = _make_good_bank(tmp_path, dim=8)
    argv = [
        "--style-bank",
        str(path),
        "--expected-emotions",
        "angry",
        "happy",
        "sad",
        "--expected-dim",
        "8",
    ]
    assert validator.main(argv) == 0
