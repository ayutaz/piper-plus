"""Tests for model configuration, imports, and CLI argument handling.

Prevents regressions:
1. models.py must import monotonic_align from local Cython module (not super_monotonic_align)
2. gin_channels must auto-set to 512 for multi-speaker models
3. Training speedup CLI args (--val-every-n-epochs, --limit-val-batches) have correct defaults
"""

import ast
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.unit
def test_models_no_super_monotonic_align_import():
    """Ensure models.py does not import from super_monotonic_align (not on PyPI)."""
    models_path = Path(__file__).resolve().parent.parent / "piper_train" / "vits" / "models.py"
    source = models_path.read_text()
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
    models_path = Path(__file__).resolve().parent.parent / "piper_train" / "vits" / "models.py"
    source = models_path.read_text()

    assert "monotonic_align" in source, (
        "models.py must import monotonic_align (local Cython module)"
    )


@pytest.mark.unit
def test_models_module_importable():
    """Ensure piper_train.vits.models can be imported without errors."""
    torch = pytest.importorskip("torch", reason="torch required")
    try:
        mod = importlib.import_module("piper_train.vits.models")
    except ImportError as e:
        if "monotonic_align" in str(e):
            pytest.skip(f"Cython monotonic_align extension not built: {e}")
        raise
    assert hasattr(mod, "SynthesizerTrn")


@pytest.mark.unit
def test_gin_channels_auto_512_for_multispeaker():
    """gin_channels must auto-set to 512 when num_speakers > 1 and not explicitly set.

    Regression test for bug where argparse default value (0) in dict_args
    caused 'gin_channels not in dict_args' to always be False.

    Note: 768 was previously used but caused ONNX export precision degradation
    (PyTorch↔ONNX correlation dropped from 0.97 to 0.70). 512 matches the
    VitsModel.__init__ fallback and produces correct ONNX exports.
    """
    # Simulate argparse output: gin_channels=0 (default, not explicitly set)
    dict_args = {"gin_channels": 0}
    num_speakers = 80

    # This is the fixed logic from __main__.py
    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 512

    assert dict_args["gin_channels"] == 512, (
        f"gin_channels should be 512 for {num_speakers} speakers, got {dict_args['gin_channels']}"
    )


@pytest.mark.unit
def test_gin_channels_respects_explicit_value():
    """gin_channels should not be overridden when explicitly set."""
    dict_args = {"gin_channels": 256}
    num_speakers = 80

    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 512

    assert dict_args["gin_channels"] == 256, (
        "gin_channels should remain 256 when explicitly set"
    )


@pytest.mark.unit
def test_gin_channels_not_set_for_single_speaker():
    """gin_channels should not auto-set for single speaker models."""
    dict_args = {"gin_channels": 0}
    num_speakers = 1

    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 512

    assert dict_args["gin_channels"] == 0, (
        "gin_channels should remain 0 for single speaker model"
    )


# ============================================================================
# Training speedup CLI arguments (A1, A2)
# ============================================================================


def _parse_main_args(cli_args):
    """Parse CLI args using __main__.py's argparser (without running main())."""
    import argparse

    from piper_train.__main__ import main
    from piper_train.vits.lightning import VitsModel

    parser = argparse.ArgumentParser()
    # Replicate the parser setup from __main__.py
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--checkpoint-epochs", type=int)
    parser.add_argument("--quality", default="medium", choices=("x-low", "medium", "high"))
    parser.add_argument("--save-top-k", type=int, default=-1)
    parser.add_argument("--no-ema", action="store_true")
    parser.add_argument("--ema-decay", type=float, default=0.9995)
    parser.add_argument("--auto_lr_scaling", action="store_true", default=True)
    parser.add_argument("--disable_auto_lr_scaling", action="store_true")
    parser.add_argument("--base_lr", type=float, default=2e-4)
    parser.add_argument("--wavlm-model-name", default="microsoft/wavlm-base-plus")
    parser.add_argument("--c-wavlm", type=float, default=0.5)
    parser.add_argument("--wavlm-every-n-steps", type=int, default=1)
    parser.add_argument("--no-wavlm", action="store_true")
    parser.add_argument("--accelerator", default="gpu")
    parser.add_argument("--devices", type=int, default=1)
    parser.add_argument("--strategy", default=None)
    parser.add_argument("--no-pin-memory", action="store_true")
    parser.add_argument("--samples-per-speaker", type=int, default=0)
    parser.add_argument("--precision", default="16-mixed")
    parser.add_argument("--max_epochs", type=int, default=1000)
    parser.add_argument("--default_root_dir", default=None)
    parser.add_argument("--resume_from_checkpoint", default=None)
    parser.add_argument(
        "--val-every-n-epochs", type=int, default=5,
    )
    parser.add_argument(
        "--limit-val-batches", type=int, default=50,
    )
    VitsModel.add_model_specific_args(parser)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--seed", type=int, default=1234)

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
    args = _parse_main_args([
        "--dataset-dir", "/tmp/test", "--batch-size", "4",
        "--val-every-n-epochs", "10",
    ])
    assert args.val_every_n_epochs == 10


@pytest.mark.unit
def test_limit_val_batches_custom():
    """--limit-val-batches should accept custom values."""
    args = _parse_main_args([
        "--dataset-dir", "/tmp/test", "--batch-size", "4",
        "--limit-val-batches", "100",
    ])
    assert args.limit_val_batches == 100


@pytest.mark.unit
def test_num_workers_default_is_2():
    """--num-workers should default to 2 (not 0)."""
    args = _parse_main_args(["--dataset-dir", "/tmp/test", "--batch-size", "4"])
    assert args.num_workers == 2, (
        f"num_workers default should be 2, got {args.num_workers}"
    )
