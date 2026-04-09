"""
Essential VITS utility tests
Only test critical functionality that affects inference
"""

import pytest


try:
    import torch
except ImportError:
    torch = None

# Skip all tests in this module if torch is not available
pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits import commons


class TestVITSUtils:
    """Test essential VITS utilities"""

    @pytest.mark.unit
    @pytest.mark.training
    def test_sequence_mask(self):
        """Test sequence mask generation for variable length inputs"""
        lengths = torch.tensor([10, 8, 12])
        max_len = 15

        mask = commons.sequence_mask(lengths, max_len)

        assert mask.shape == (3, max_len)
        # First sequence: True for first 10, False for rest
        assert torch.all(mask[0, :10])
        assert not torch.any(mask[0, 10:])

    @pytest.mark.unit
    @pytest.mark.training
    def test_get_padding(self):
        """Test padding calculation for convolutions"""
        # Standard cases
        assert commons.get_padding(kernel_size=1, dilation=1) == 0
        assert commons.get_padding(kernel_size=3, dilation=1) == 1
        assert commons.get_padding(kernel_size=5, dilation=1) == 2

        # With dilation
        assert commons.get_padding(kernel_size=3, dilation=2) == 2

    @pytest.mark.unit
    @pytest.mark.training
    def test_intersperse(self):
        """Test intersperse for adding blanks between phonemes"""
        lst = [1, 2, 3]
        result = commons.intersperse(lst, item=0)

        assert result == [
            0,
            1,
            0,
            2,
            0,
            3,
            0,
        ]  # Actual implementation adds item at start and end too
        assert commons.intersperse([], item=0) == [0]
        assert commons.intersperse([1], item=0) == [0, 1, 0]


class TestWavLMDiscriminator:
    """Test WavLM-based perceptual discriminator"""

    @pytest.mark.unit
    @pytest.mark.training
    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="WavLM tests require GPU for practical performance",
    )
    def test_wavlm_discriminator_forward(self):
        """Test WavLMDiscriminator forward pass"""
        from piper_train.vits.models import WavLMDiscriminator

        # Initialize discriminator
        disc = WavLMDiscriminator(
            model_name="microsoft/wavlm-base-plus",
            source_sample_rate=22050,
        )
        disc = disc.cuda()

        # Create test audio tensors (batch=2, 1 channel, ~0.5 sec at 22050Hz)
        batch_size = 2
        audio_length = 11025  # ~0.5 seconds at 22050Hz

        y = torch.randn(batch_size, 1, audio_length).cuda()
        y_hat = torch.randn(batch_size, 1, audio_length).cuda()

        # Forward pass
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = disc(y, y_hat)

        # Verify output shapes
        assert len(y_d_rs) == 1, "Should return 1 discriminator output for real"
        assert len(y_d_gs) == 1, "Should return 1 discriminator output for generated"
        assert len(fmap_rs) == 1, "Should return 1 feature map list for real"
        assert len(fmap_gs) == 1, "Should return 1 feature map list for generated"

        # Check discrimination scores shape
        assert y_d_rs[0].shape[0] == batch_size, "Batch size should match"
        assert y_d_gs[0].shape[0] == batch_size, "Batch size should match"

        # Check feature maps (should be from layers 6, 9, 12 by default)
        assert len(fmap_rs[0]) == 3, "Should have 3 feature maps (layers 6, 9, 12)"
        assert len(fmap_gs[0]) == 3, "Should have 3 feature maps (layers 6, 9, 12)"

    @pytest.mark.unit
    @pytest.mark.training
    def test_wavlm_discriminator_resample(self, mock_wavlm_discriminator):
        """Test audio resampling via WavLMDiscriminator._resample()"""
        source_sample_rate = 22050
        target_sample_rate = 16000

        disc = mock_wavlm_discriminator

        # Create test audio (batch=2, 1 channel, 1 second at 22050Hz)
        audio = torch.randn(2, 1, source_sample_rate)

        resampled = disc._resample(audio)

        # Expected length: 22050 * (16000 / 22050) = 16000
        expected_length = target_sample_rate
        assert resampled.shape == (2, expected_length), (
            f"Expected shape (2, {expected_length}), got {resampled.shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_wavlm_discriminator_resample_same_rate(self):
        """Test _resample() when source == target sample rate (no-op path)."""
        from unittest.mock import MagicMock, patch

        from piper_train.vits.models import WavLMDiscriminator

        sr = 16000

        # Same-rate path needs its own instance (source==target, no resampler)
        mock_wavlm = MagicMock()
        mock_wavlm.feature_extractor.parameters.return_value = []
        with patch("transformers.WavLMModel") as mock_wavlm_cls:
            mock_wavlm_cls.from_pretrained.return_value = mock_wavlm
            disc = WavLMDiscriminator(
                source_sample_rate=sr,
                target_sample_rate=sr,
            )

        audio = torch.randn(2, 1, sr)
        resampled = disc._resample(audio)

        # No resampling; just squeeze channel dim
        assert resampled.shape == (2, sr)

    @pytest.mark.unit
    @pytest.mark.training
    @pytest.mark.skipif(
        not torch.cuda.is_available(),
        reason="WavLM tests require GPU for practical performance",
    )
    def test_wavlm_discriminator_loss_compatibility(self):
        """Test that WavLMDiscriminator output is compatible with existing loss functions"""
        from piper_train.vits.losses import (
            discriminator_loss,
            feature_loss,
            generator_loss,
        )
        from piper_train.vits.models import WavLMDiscriminator

        disc = WavLMDiscriminator(
            model_name="microsoft/wavlm-base-plus",
            source_sample_rate=22050,
        )
        disc = disc.cuda()

        # Create test audio
        y = torch.randn(2, 1, 11025).cuda()
        y_hat = torch.randn(2, 1, 11025).cuda()

        # Forward pass
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = disc(y, y_hat)

        # Test discriminator loss
        loss_disc, r_losses, g_losses = discriminator_loss(y_d_rs, y_d_gs)
        assert loss_disc.item() >= 0, "Discriminator loss should be non-negative"

        # Test generator loss
        loss_gen, gen_losses = generator_loss(y_d_gs)
        assert loss_gen.item() >= 0, "Generator loss should be non-negative"

        # Test feature loss
        loss_fm = feature_loss(fmap_rs, fmap_gs)
        assert loss_fm.item() >= 0, "Feature loss should be non-negative"
