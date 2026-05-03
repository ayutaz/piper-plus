"""Tests for MB-iSTFT-related utility functions.

This module tests ``set_export_mode`` — the ``onnx_export_mode`` bulk
toggle applied to ``SynthesizerTrn`` and its submodules before ONNX
export.
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_synthesizer(n_speakers=1, n_languages=2, gin_channels=512):
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
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        n_speakers=n_speakers,
        n_languages=n_languages,
        gin_channels=gin_channels,
    )


@pytest.mark.unit
def test_set_export_mode_enables_all_modules():
    """set_export_mode toggles onnx_export_mode on SynthesizerTrn and decoder."""
    from piper_train.export_onnx import set_export_mode

    model = _make_synthesizer()

    set_export_mode(model, True)
    assert model.onnx_export_mode is True
    assert model.dec.onnx_export_mode is True

    set_export_mode(model, False)
    assert model.onnx_export_mode is False
    assert model.dec.onnx_export_mode is False
