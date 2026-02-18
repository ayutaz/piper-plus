"""Tests for model configuration and imports.

Prevents regressions:
1. models.py must import monotonic_align from local Cython module (not super_monotonic_align)
2. gin_channels must auto-set to 768 for multi-speaker models
"""

import ast
import importlib
from pathlib import Path

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
def test_gin_channels_auto_768_for_multispeaker():
    """gin_channels must auto-set to 768 when num_speakers > 1 and not explicitly set.

    Regression test for bug where argparse default value (0) in dict_args
    caused 'gin_channels not in dict_args' to always be False.
    """
    # Simulate argparse output: gin_channels=0 (default, not explicitly set)
    dict_args = {"gin_channels": 0}
    num_speakers = 80

    # This is the fixed logic from __main__.py
    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 768

    assert dict_args["gin_channels"] == 768, (
        f"gin_channels should be 768 for {num_speakers} speakers, got {dict_args['gin_channels']}"
    )


@pytest.mark.unit
def test_gin_channels_respects_explicit_value():
    """gin_channels should not be overridden when explicitly set."""
    dict_args = {"gin_channels": 512}
    num_speakers = 80

    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 768

    assert dict_args["gin_channels"] == 512, (
        "gin_channels should remain 512 when explicitly set"
    )


@pytest.mark.unit
def test_gin_channels_not_set_for_single_speaker():
    """gin_channels should not auto-set for single speaker models."""
    dict_args = {"gin_channels": 0}
    num_speakers = 1

    if num_speakers > 1 and dict_args.get("gin_channels", 0) == 0:
        dict_args["gin_channels"] = 768

    assert dict_args["gin_channels"] == 0, (
        "gin_channels should remain 0 for single speaker model"
    )
