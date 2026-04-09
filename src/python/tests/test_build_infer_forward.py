"""Unit tests for build_infer_forward() extracted from export_onnx.py.

Tests verify:
- The factory returns a callable
- Deterministic mode produces stable output
- Stochastic mode produces varying output
- Output shapes are correct
- Single-speaker (sid=None, lid=None) works
- Multi-speaker with sid/lid works
"""

import pytest
import torch


@pytest.mark.unit
class TestBuildInferForward:
    """Tests for the build_infer_forward factory function."""

    def test_returns_callable(self, mock_vits_model):
        """build_infer_forward returns a callable."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)
        assert callable(fn)

    def test_deterministic_output_stable(self, mock_vits_model):
        """Deterministic mode: same input produces identical output twice.

        Note: onnx_export_mode must be set to ensure the StochasticDurationPredictor
        produces deterministic durations (it uses internal randomness otherwise).
        """
        from piper_train.export_onnx import build_infer_forward

        # Enable ONNX export mode so SDP is fully deterministic
        mock_vits_model.onnx_export_mode = True
        if hasattr(mock_vits_model, "dp"):
            mock_vits_model.dp.onnx_export_mode = True

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio1, dur1 = fn(text, text_lengths, scales, prosody_features=prosody)
            audio2, dur2 = fn(text, text_lengths, scales, prosody_features=prosody)

        torch.testing.assert_close(audio1, audio2)
        torch.testing.assert_close(dur1, dur2)

    def test_stochastic_output_varies(self, mock_vits_model):
        """Stochastic mode: same input produces different output across runs."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=True)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio1, _ = fn(text, text_lengths, scales, prosody_features=prosody)
            audio2, _ = fn(text, text_lengths, scales, prosody_features=prosody)

        # With noise_scale=0.667, outputs should differ
        assert not torch.equal(audio1, audio2), (
            "Stochastic mode should produce different outputs across runs"
        )

    def test_output_shape_audio(self, mock_vits_model):
        """Audio output has 3 dimensions: (batch, channels, time)."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, _ = fn(text, text_lengths, scales, prosody_features=prosody)

        assert audio.ndim == 3, f"Expected audio.ndim == 3, got {audio.ndim}"
        assert audio.shape[0] == 1, "Batch dimension should be 1"

    def test_output_shape_durations(self, mock_vits_model):
        """Durations shape is (batch, phoneme_length)."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        phoneme_length = 10
        text = torch.randint(0, 50, (1, phoneme_length), dtype=torch.long)
        text_lengths = torch.LongTensor([phoneme_length])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        prosody = torch.zeros(1, phoneme_length, 3, dtype=torch.long)

        with torch.no_grad():
            _, durations = fn(text, text_lengths, scales, prosody_features=prosody)

        assert durations.shape == (1, phoneme_length), (
            f"Expected durations shape (1, {phoneme_length}), got {durations.shape}"
        )

    def test_single_speaker_sid_none(self, mock_vits_model):
        """Single-speaker model works with sid=None, lid=None."""
        from piper_train.export_onnx import build_infer_forward

        fn = build_infer_forward(mock_vits_model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, durations = fn(
                text, text_lengths, scales,
                sid=None, lid=None, prosody_features=prosody,
            )

        assert audio.shape[0] == 1
        assert durations.shape[0] == 1

    def test_multi_speaker_with_sid_lid(self, mock_vits_model_multilingual):
        """Multi-speaker/multilingual model works with explicit sid and lid."""
        from piper_train.export_onnx import build_infer_forward

        model = mock_vits_model_multilingual
        fn = build_infer_forward(model, stochastic=False)

        text = torch.randint(0, 50, (1, 10), dtype=torch.long)
        text_lengths = torch.LongTensor([10])
        scales = torch.FloatTensor([0.667, 1.0, 0.8])
        sid = torch.LongTensor([0])
        lid = torch.LongTensor([0])
        prosody = torch.zeros(1, 10, 3, dtype=torch.long)

        with torch.no_grad():
            audio, durations = fn(
                text, text_lengths, scales,
                sid=sid, lid=lid, prosody_features=prosody,
            )

        assert audio.ndim == 3, f"Expected audio.ndim == 3, got {audio.ndim}"
        assert durations.shape == (1, 10)
