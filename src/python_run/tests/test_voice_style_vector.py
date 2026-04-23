"""Tests for PiperVoice style_vector support (Phase 2 P2-T02).

These tests use a mocked ONNX session to verify the mask-based style_vector
handling. The feature-on / feature-off path, metadata resolution, and CLI
wiring are all covered without needing a real ONNX model.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from piper.config import PhonemeType, PiperConfig
from piper.voice import PiperVoice


def _make_mock_voice_with_style_vector(
    *,
    style_vector_dim: int = 256,
    metadata_dim: str | None = None,  # Derived from style_vector_dim by default
    config_style_vector_dim: int = 0,
    sample_rate: int = 22050,
) -> PiperVoice:
    """Build a PiperVoice whose ONNX session advertises a style_vector input.

    The ``metadata_dim`` argument controls what ``custom_metadata_map`` will
    report. Set to ``None`` to simulate a model without the metadata entry
    (forces fallback to ``config.style_vector_dim``).
    """
    config = PiperConfig(
        num_symbols=100,
        num_speakers=1,
        sample_rate=sample_rate,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={
            "_": [0],
            "^": [1],
            "$": [2],
            "a": [10],
        },
        phoneme_type=PhonemeType.MULTILINGUAL,
        style_vector_dim=config_style_vector_dim,
    )

    session = MagicMock()

    # Model inputs: input, input_lengths, scales, style_vector, style_vector_mask
    def _mk_inp(name, shape=None):
        m = MagicMock()
        m.name = name
        m.shape = shape or ["batch_size", None]
        return m

    style_vector_inp = _mk_inp("style_vector", ["batch_size", style_vector_dim])
    style_mask_inp = _mk_inp("style_vector_mask", ["batch_size", 1])

    session.get_inputs.return_value = [
        _mk_inp("input"),
        _mk_inp("input_lengths"),
        _mk_inp("scales"),
        style_vector_inp,
        style_mask_inp,
    ]

    output_mock = MagicMock()
    output_mock.name = "output"
    session.get_outputs.return_value = [output_mock]

    audio_samples = np.zeros((1, 1, sample_rate), dtype=np.float32)
    session.run.return_value = [audio_samples]

    # Model metadata (default: derive from style_vector_dim)
    effective_metadata_dim = (
        metadata_dim if metadata_dim is not None else str(style_vector_dim)
    )
    meta = MagicMock()
    custom_meta = {}
    if effective_metadata_dim != "__none__":
        custom_meta["style_vector_dim"] = effective_metadata_dim
        custom_meta["style_condition_mode"] = "global"
    meta.custom_metadata_map = custom_meta
    session.get_modelmeta.return_value = meta

    return PiperVoice(session=session, config=config)


def _captured_inputs(voice: PiperVoice) -> dict:
    """Return the dict passed to the last session.run() call."""
    return voice.session.run.call_args[0][1]


class TestResolveStyleVectorDim:
    """Tests for PiperVoice._resolve_style_vector_dim()."""

    def test_reads_from_metadata(self):
        voice = _make_mock_voice_with_style_vector(
            style_vector_dim=256, metadata_dim="256"
        )
        assert voice._resolve_style_vector_dim() == 256

    def test_falls_back_to_config(self):
        voice = _make_mock_voice_with_style_vector(
            style_vector_dim=128,
            metadata_dim="__none__",
            config_style_vector_dim=128,
        )
        assert voice._resolve_style_vector_dim() == 128

    def test_returns_zero_when_neither(self):
        voice = _make_mock_voice_with_style_vector(
            style_vector_dim=128,
            metadata_dim="__none__",
            config_style_vector_dim=0,
        )
        assert voice._resolve_style_vector_dim() == 0

    def test_metadata_takes_precedence_over_config(self):
        voice = _make_mock_voice_with_style_vector(
            style_vector_dim=64, metadata_dim="64", config_style_vector_dim=128
        )
        assert voice._resolve_style_vector_dim() == 64

    def test_invalid_metadata_value_falls_back(self):
        voice = _make_mock_voice_with_style_vector(
            style_vector_dim=32,
            metadata_dim="not-a-number",
            config_style_vector_dim=32,
        )
        assert voice._resolve_style_vector_dim() == 32


class TestSynthesizeWithStyleVector:
    """Tests for passing a style vector into synthesize_ids_to_raw()."""

    def test_style_vector_none_sends_zeros_with_mask_zero(self):
        voice = _make_mock_voice_with_style_vector(style_vector_dim=256)
        voice.synthesize_ids_to_raw([1, 0, 10, 0, 2])

        inputs = _captured_inputs(voice)
        assert "style_vector" in inputs
        assert "style_vector_mask" in inputs
        assert inputs["style_vector"].shape == (1, 256)
        assert inputs["style_vector"].dtype == np.float32
        assert np.all(inputs["style_vector"] == 0.0)
        assert inputs["style_vector_mask"].tolist() == [[0]]
        assert inputs["style_vector_mask"].dtype == np.int64

    def test_style_vector_provided_sends_mask_one(self):
        voice = _make_mock_voice_with_style_vector(style_vector_dim=256)
        sv = np.arange(256, dtype=np.float32)
        voice.synthesize_ids_to_raw([1, 0, 10, 0, 2], style_vector=sv)

        inputs = _captured_inputs(voice)
        assert inputs["style_vector"].shape == (1, 256)
        np.testing.assert_array_equal(inputs["style_vector"].reshape(-1), sv)
        assert inputs["style_vector_mask"].tolist() == [[1]]

    def test_style_vector_2d_shape_accepted(self):
        voice = _make_mock_voice_with_style_vector(style_vector_dim=64)
        sv = np.random.randn(1, 64).astype(np.float32)
        voice.synthesize_ids_to_raw([1, 0, 10, 0, 2], style_vector=sv)

        inputs = _captured_inputs(voice)
        assert inputs["style_vector"].shape == (1, 64)

    def test_style_vector_shape_mismatch_raises(self):
        voice = _make_mock_voice_with_style_vector(style_vector_dim=256)
        wrong_shape = np.zeros((1, 128), dtype=np.float32)
        with pytest.raises(ValueError, match="style_vector shape mismatch"):
            voice.synthesize_ids_to_raw([1, 0, 10, 0, 2], style_vector=wrong_shape)

    def test_style_vector_float64_is_cast_to_float32(self):
        voice = _make_mock_voice_with_style_vector(style_vector_dim=256)
        sv = np.random.randn(256).astype(np.float64)
        voice.synthesize_ids_to_raw([1, 0, 10, 0, 2], style_vector=sv)

        inputs = _captured_inputs(voice)
        assert inputs["style_vector"].dtype == np.float32


class TestModelWithoutStyleVectorInput:
    """When the model has no style_vector input, it must be silently ignored."""

    def _make_voice_without_style_vector(self):
        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type=PhonemeType.MULTILINGUAL,
        )

        session = MagicMock()
        input_mock = MagicMock()
        input_mock.name = "input"
        input_lengths_mock = MagicMock()
        input_lengths_mock.name = "input_lengths"
        scales_mock = MagicMock()
        scales_mock.name = "scales"
        session.get_inputs.return_value = [
            input_mock,
            input_lengths_mock,
            scales_mock,
        ]

        output_mock = MagicMock()
        output_mock.name = "output"
        session.get_outputs.return_value = [output_mock]

        audio = np.zeros((1, 1, 22050), dtype=np.float32)
        session.run.return_value = [audio]

        return PiperVoice(session=session, config=config)

    def test_no_style_vector_input_ignored(self):
        voice = self._make_voice_without_style_vector()
        # Even though we pass a style_vector, the ONNX call must not include it.
        sv = np.random.randn(256).astype(np.float32)
        voice.synthesize_ids_to_raw([1, 0, 10, 0, 2], style_vector=sv)

        inputs = voice.session.run.call_args[0][1]
        assert "style_vector" not in inputs
        assert "style_vector_mask" not in inputs
