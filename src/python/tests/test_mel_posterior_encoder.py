"""
Tests for VITS2 Mel Posterior Encoder (Improved Encoder E).

Verifies that:
- use_mel_posterior_encoder=True sets enc_q in_channels to 80 (Mel)
- use_mel_posterior_encoder=False keeps enc_q in_channels at spec_channels (backward compat)
- mel_spectrogram_torch output shape is (B, 80, T)
"""

import pytest

try:
    import torch
except ImportError:
    torch = None

pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")


class TestMelPosteriorEncoder:
    """Test VITS2 Mel Posterior Encoder integration."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_enc_q_in_channels_mel(self):
        """use_mel_posterior_encoder=True should set enc_q.in_channels to 80."""
        from piper_train.vits.models import SynthesizerTrn

        model = SynthesizerTrn(
            n_vocab=100,
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
            upsample_rates=(8, 8, 4),
            upsample_initial_channel=256,
            upsample_kernel_sizes=(16, 16, 8),
            use_mel_posterior_encoder=True,
        )
        assert model.enc_q.in_channels == 80, (
            f"Expected enc_q.in_channels=80, got {model.enc_q.in_channels}"
        )
        assert model.use_mel_posterior_encoder is True

    @pytest.mark.unit
    @pytest.mark.training
    def test_enc_q_in_channels_linear_default(self):
        """use_mel_posterior_encoder=False (default) should keep enc_q.in_channels at spec_channels."""
        from piper_train.vits.models import SynthesizerTrn

        spec_channels = 513
        model = SynthesizerTrn(
            n_vocab=100,
            spec_channels=spec_channels,
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
            upsample_rates=(8, 8, 4),
            upsample_initial_channel=256,
            upsample_kernel_sizes=(16, 16, 8),
        )
        assert model.enc_q.in_channels == spec_channels, (
            f"Expected enc_q.in_channels={spec_channels}, got {model.enc_q.in_channels}"
        )
        assert model.use_mel_posterior_encoder is False

    @pytest.mark.unit
    @pytest.mark.training
    def test_mel_spectrogram_output_shape(self):
        """mel_spectrogram_torch should produce output with shape (B, 80, T)."""
        from piper_train.vits.mel_processing import mel_spectrogram_torch

        batch_size = 2
        # Create a short audio signal (~0.25s at 22050 Hz)
        audio_length = 5520
        y = torch.randn(batch_size, audio_length)

        mel = mel_spectrogram_torch(
            y,
            n_fft=1024,
            num_mels=80,
            sampling_rate=22050,
            hop_size=256,
            win_size=1024,
            fmin=0,
            fmax=None,
        )

        assert mel.shape[0] == batch_size, (
            f"Expected batch dim={batch_size}, got {mel.shape[0]}"
        )
        assert mel.shape[1] == 80, (
            f"Expected 80 mel channels, got {mel.shape[1]}"
        )
        # Time dimension should be audio_length // hop_size + 1
        # (due to padding in mel_spectrogram_torch)
        assert mel.shape[2] > 0, "Time dimension should be > 0"

    @pytest.mark.unit
    @pytest.mark.training
    def test_spec_to_mel_output_shape(self):
        """spec_to_mel_torch should convert (B, 513, T) to (B, 80, T)."""
        from piper_train.vits.mel_processing import spec_to_mel_torch

        batch_size = 2
        spec_channels = 513
        time_steps = 20

        spec = torch.randn(batch_size, spec_channels, time_steps).abs() + 1e-5

        mel = spec_to_mel_torch(
            spec,
            n_fft=1024,
            num_mels=80,
            sampling_rate=22050,
            fmin=0,
            fmax=None,
        )

        assert mel.shape == (batch_size, 80, time_steps), (
            f"Expected shape ({batch_size}, 80, {time_steps}), got {mel.shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_backward_compat_no_mel_arg(self):
        """SynthesizerTrn should work without use_mel_posterior_encoder arg (defaults to False)."""
        from piper_train.vits.models import SynthesizerTrn

        # Construct without passing use_mel_posterior_encoder at all
        model = SynthesizerTrn(
            n_vocab=100,
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
            upsample_rates=(8, 8, 4),
            upsample_initial_channel=256,
            upsample_kernel_sizes=(16, 16, 8),
        )
        # Default behavior: enc_q should use full linear spec channels
        assert model.enc_q.in_channels == 513
        assert model.use_mel_posterior_encoder is False
