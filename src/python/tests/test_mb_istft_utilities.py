"""Tests for MB-iSTFT-related utility functions.

This module tests:
1. set_export_mode — onnx_export_mode bulk toggle on SynthesizerTrn + submodules
2. _check_decoder_architecture_compatibility — checkpoint decoder mismatch detection
"""

import logging
import tempfile

import pytest

torch = pytest.importorskip("torch", reason="torch required")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthesizer(mb_istft=False, n_speakers=1, n_languages=2, gin_channels=512):
    """Build a minimal SynthesizerTrn for testing."""
    from piper_train.vits.models import SynthesizerTrn

    return SynthesizerTrn(
        n_vocab=97,
        spec_channels=513,
        segment_size=32,
        inter_channels=192,
        hidden_channels=192,
        filter_channels=768,
        n_heads=2,
        n_layers=6,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4) if mb_istft else (8, 8, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16) if mb_istft else (16, 16, 8),
        n_speakers=n_speakers,
        n_languages=n_languages,
        gin_channels=gin_channels,
        mb_istft=mb_istft,
    )


# ---------------------------------------------------------------------------
# set_export_mode tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_set_export_mode_enables_all_modules():
    """set_export_mode(model, True) sets onnx_export_mode on SynthesizerTrn and MBiSTFTGenerator."""
    from piper_train.export_onnx import set_export_mode

    model = _make_synthesizer(mb_istft=True)

    set_export_mode(model, True)
    # SynthesizerTrn itself
    assert model.onnx_export_mode is True
    # MBiSTFTGenerator (dec)
    assert model.dec.onnx_export_mode is True

    set_export_mode(model, False)
    assert model.onnx_export_mode is False
    assert model.dec.onnx_export_mode is False


@pytest.mark.unit
def test_set_export_mode_hifigan_no_error():
    """HiFi-GAN Generator (no onnx_export_mode attr) does not raise on set_export_mode."""
    from piper_train.export_onnx import set_export_mode

    model = _make_synthesizer(mb_istft=False)

    # Must not raise
    set_export_mode(model, True)
    # SynthesizerTrn itself should still have the attribute set
    assert model.onnx_export_mode is True


# ---------------------------------------------------------------------------
# _check_decoder_architecture_compatibility tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ckpt_compat_mismatch_warns(caplog):
    """Mismatched decoder architecture emits a WARNING containing 'mismatch'."""
    from piper_train.__main__ import _check_decoder_architecture_compatibility

    ckpt = {"hyper_parameters": {"mb_istft": False}}
    with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
        torch.save(ckpt, f.name)
        with caplog.at_level(logging.WARNING):
            _check_decoder_architecture_compatibility(f.name, model_mb_istft=True)
        assert "mismatch" in caplog.text.lower() or "Decoder architecture" in caplog.text


@pytest.mark.unit
def test_ckpt_compat_match_no_warning(caplog):
    """Matching decoder architecture produces no WARNING about mismatch."""
    from piper_train.__main__ import _check_decoder_architecture_compatibility

    ckpt = {"hyper_parameters": {"mb_istft": True}}
    with tempfile.NamedTemporaryFile(suffix=".ckpt", delete=False) as f:
        torch.save(ckpt, f.name)
        with caplog.at_level(logging.WARNING):
            _check_decoder_architecture_compatibility(f.name, model_mb_istft=True)
        assert "mismatch" not in caplog.text.lower()


@pytest.mark.unit
def test_ckpt_compat_invalid_path_no_error():
    """Non-existent checkpoint path does not raise (handled gracefully)."""
    from piper_train.__main__ import _check_decoder_architecture_compatibility

    # Must not raise any exception
    _check_decoder_architecture_compatibility("/nonexistent/path.ckpt", model_mb_istft=True)
