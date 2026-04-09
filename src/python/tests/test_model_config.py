"""Tests for model configuration, imports, and CLI argument handling.

Prevents regressions:
1. models.py must import monotonic_align from local Cython module (not super_monotonic_align)
2. Training speedup CLI args (--val-every-n-epochs, --limit-val-batches) have correct defaults

Note: gin_channels / apply_transfer_defaults tests are in test_multispeaker_transfer.py.
"""

import ast
import importlib
from pathlib import Path

import pytest


@pytest.mark.unit
def test_models_no_super_monotonic_align_import():
    """Ensure models.py does not import from super_monotonic_align (not on PyPI)."""
    models_path = (
        Path(__file__).resolve().parent.parent / "piper_train" / "vits" / "models.py"
    )
    source = models_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "super_monotonic_align", (
                f"models.py imports from 'super_monotonic_align' (line {node.lineno}). "
                "This package does not exist on PyPI. Use the local monotonic_align module instead: "
                "'from . import monotonic_align'"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "super_monotonic_align", (
                    f"models.py imports 'super_monotonic_align' (line {node.lineno}). "
                    "This package does not exist on PyPI."
                )


@pytest.mark.unit
def test_models_imports_local_monotonic_align():
    """Ensure models.py uses the local Cython monotonic_align module."""
    models_path = (
        Path(__file__).resolve().parent.parent / "piper_train" / "vits" / "models.py"
    )
    source = models_path.read_text(encoding="utf-8")

    assert "monotonic_align" in source, (
        "models.py must import monotonic_align (local Cython module)"
    )


@pytest.mark.unit
def test_models_module_importable():
    """Ensure piper_train.vits.models can be imported without errors."""
    pytest.importorskip("torch", reason="torch required")
    try:
        mod = importlib.import_module("piper_train.vits.models")
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise
    assert hasattr(mod, "SynthesizerTrn")


# gin_channels / apply_transfer_defaults tests live in test_multispeaker_transfer.py
# (canonical location for all apply_transfer_defaults coverage).


# ============================================================================
# Training speedup CLI arguments (A1, A2)
# ============================================================================


def _parse_main_args(cli_args):
    """Parse CLI args using the canonical parser from __main__.py."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    return parser.parse_args(cli_args)


@pytest.mark.unit
def test_val_every_n_epochs_default():
    """--val-every-n-epochs should default to 5."""
    args = _parse_main_args(["--dataset-dir", "/tmp/test", "--batch-size", "4"])
    assert args.val_every_n_epochs == 5


@pytest.mark.unit
def test_limit_val_batches_default():
    """--limit-val-batches should default to 50."""
    args = _parse_main_args(["--dataset-dir", "/tmp/test", "--batch-size", "4"])
    assert args.limit_val_batches == 50


@pytest.mark.unit
def test_val_every_n_epochs_custom():
    """--val-every-n-epochs should accept custom values."""
    args = _parse_main_args(
        [
            "--dataset-dir",
            "/tmp/test",
            "--batch-size",
            "4",
            "--val-every-n-epochs",
            "10",
        ]
    )
    assert args.val_every_n_epochs == 10


@pytest.mark.unit
def test_limit_val_batches_custom():
    """--limit-val-batches should accept custom values."""
    args = _parse_main_args(
        [
            "--dataset-dir",
            "/tmp/test",
            "--batch-size",
            "4",
            "--limit-val-batches",
            "100",
        ]
    )
    assert args.limit_val_batches == 100


@pytest.mark.unit
def test_num_workers_default_is_2():
    """--num-workers should default to 2 (not 0)."""
    args = _parse_main_args(["--dataset-dir", "/tmp/test", "--batch-size", "4"])
    assert args.num_workers == 2, (
        f"num_workers default should be 2, got {args.num_workers}"
    )
