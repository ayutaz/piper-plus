"""
Tests for DurationDiscriminatorV2 (VITS2 Phase 2).

Validates the duration discriminator architecture, forward pass shapes,
speaker conditioning, and SynthesizerTrn forward() dur_info integration.
"""

import pytest


try:
    import torch
except ImportError:
    torch = None

# Skip all tests in this module if torch is not available
pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits.models import DurationDiscriminatorV2, SynthesizerTrn


def _make_synthesizer(**kwargs):
    """Create a minimal SynthesizerTrn for testing."""
    defaults = dict(
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
        n_speakers=1,
        gin_channels=0,
        use_sdp=True,
        prosody_dim=0,
    )
    defaults.update(kwargs)
    return SynthesizerTrn(**defaults)


class TestDurationDiscriminatorV2:
    """Tests for DurationDiscriminatorV2 class."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_shape_single_speaker(self):
        """DurationDiscriminatorV2 forward should return correct shapes (gin_channels=0)."""
        batch_size = 2
        in_channels = 192
        filter_channels = 256
        seq_len = 10

        disc = DurationDiscriminatorV2(
            in_channels=in_channels,
            filter_channels=filter_channels,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=0,
        )

        x = torch.randn(batch_size, in_channels, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        dur_r = torch.randn(batch_size, 1, seq_len)
        dur_hat = torch.randn(batch_size, 1, seq_len)

        output_probs = disc(x, x_mask, dur_r, dur_hat, g=None)

        assert len(output_probs) == 2, "Should return [prob_real, prob_fake]"
        assert output_probs[0].shape == (batch_size, seq_len, 1), (
            f"prob_real shape should be (B, T, 1), got {output_probs[0].shape}"
        )
        assert output_probs[1].shape == (batch_size, seq_len, 1), (
            f"prob_fake shape should be (B, T, 1), got {output_probs[1].shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_shape_multi_speaker(self):
        """DurationDiscriminatorV2 forward should work with speaker conditioning (gin_channels>0)."""
        batch_size = 2
        in_channels = 192
        filter_channels = 256
        gin_channels = 256
        seq_len = 10

        disc = DurationDiscriminatorV2(
            in_channels=in_channels,
            filter_channels=filter_channels,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=gin_channels,
        )

        x = torch.randn(batch_size, in_channels, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        dur_r = torch.randn(batch_size, 1, seq_len)
        dur_hat = torch.randn(batch_size, 1, seq_len)
        g = torch.randn(batch_size, gin_channels, 1)

        output_probs = disc(x, x_mask, dur_r, dur_hat, g=g)

        assert len(output_probs) == 2, "Should return [prob_real, prob_fake]"
        assert output_probs[0].shape == (batch_size, seq_len, 1), (
            f"prob_real shape should be (B, T, 1), got {output_probs[0].shape}"
        )
        assert output_probs[1].shape == (batch_size, seq_len, 1), (
            f"prob_fake shape should be (B, T, 1), got {output_probs[1].shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_probability_shape(self):
        """forward_probability should return correct shape for a single duration."""
        batch_size = 2
        filter_channels = 256
        seq_len = 10

        disc = DurationDiscriminatorV2(
            in_channels=192,
            filter_channels=filter_channels,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=0,
        )

        # Pre-processed text features (after conv_1/conv_2)
        x = torch.randn(batch_size, filter_channels, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        dur = torch.randn(batch_size, 1, seq_len)

        output_prob = disc.forward_probability(x, x_mask, dur)

        assert output_prob.shape == (batch_size, seq_len, 1), (
            f"forward_probability shape should be (B, T, 1), got {output_prob.shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_output_range_sigmoid(self):
        """Output probabilities should be in [0, 1] range due to Sigmoid."""
        disc = DurationDiscriminatorV2(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.0,  # No dropout for deterministic test
            gin_channels=0,
        )
        disc.eval()

        x = torch.randn(4, 192, 15)
        x_mask = torch.ones(4, 1, 15)
        dur_r = torch.randn(4, 1, 15)
        dur_hat = torch.randn(4, 1, 15)

        with torch.no_grad():
            output_probs = disc(x, x_mask, dur_r, dur_hat)

        for prob in output_probs:
            assert prob.min() >= 0.0, f"Probability minimum {prob.min()} should be >= 0"
            assert prob.max() <= 1.0, f"Probability maximum {prob.max()} should be <= 1"

    @pytest.mark.unit
    @pytest.mark.training
    def test_mask_applied(self):
        """Masked positions should produce zero output."""
        disc = DurationDiscriminatorV2(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.0,
            gin_channels=0,
        )
        disc.eval()

        batch_size = 2
        seq_len = 10

        x = torch.randn(batch_size, 192, seq_len)
        # Mask: first 5 positions valid, last 5 masked
        x_mask = torch.zeros(batch_size, 1, seq_len)
        x_mask[:, :, :5] = 1.0
        dur_r = torch.randn(batch_size, 1, seq_len)
        dur_hat = torch.randn(batch_size, 1, seq_len)

        with torch.no_grad():
            output_probs = disc(x, x_mask, dur_r, dur_hat)

        # The output at masked positions should be approximately 0.5 (sigmoid(0))
        # since the input to sigmoid is zeroed by the mask.
        # Note: Linear layer bias causes slight deviation from exactly 0.5.
        for prob in output_probs:
            masked_values = prob[:, 5:, :]
            assert torch.allclose(masked_values, torch.full_like(masked_values, 0.5), atol=0.1), (
                f"Masked positions should output ~sigmoid(0)=0.5, got {masked_values.mean()}"
            )

    @pytest.mark.unit
    @pytest.mark.training
    def test_no_cond_attribute_without_gin_channels(self):
        """When gin_channels=0, the cond layer should not exist."""
        disc = DurationDiscriminatorV2(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=0,
        )

        assert not hasattr(disc, 'cond'), (
            "cond layer should not exist when gin_channels=0"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_cond_attribute_with_gin_channels(self):
        """When gin_channels>0, the cond layer should exist."""
        disc = DurationDiscriminatorV2(
            in_channels=192,
            filter_channels=256,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=256,
        )

        assert hasattr(disc, 'cond'), (
            "cond layer should exist when gin_channels>0"
        )


class TestSynthesizerTrnDurInfo:
    """Tests for SynthesizerTrn forward() dur_info return value."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_returns_dur_info_dp_mode(self):
        """SynthesizerTrn forward() should return dur_info when use_sdp=False."""
        model = _make_synthesizer(use_sdp=False, prosody_dim=0)
        model.eval()

        batch_size = 2
        seq_len = 5
        spec_len = 32

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len, seq_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.tensor([spec_len, spec_len])

        with torch.no_grad():
            result = model(x, x_lengths, spec, spec_lengths)

        assert len(result) == 8, (
            f"forward() should return 8 elements, got {len(result)}"
        )

        dur_info = result[7]
        assert dur_info is not None, (
            "dur_info should not be None when use_sdp=False"
        )

        x_dp, logw, logw_hat = dur_info
        assert x_dp.shape[0] == batch_size, "x_dp batch size mismatch"
        assert x_dp.shape[2] == seq_len, "x_dp seq_len mismatch"
        assert logw.shape == (batch_size, 1, seq_len), (
            f"logw shape should be (B, 1, T), got {logw.shape}"
        )
        assert logw_hat.shape == (batch_size, 1, seq_len), (
            f"logw_hat shape should be (B, 1, T), got {logw_hat.shape}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_returns_none_dur_info_sdp_mode(self):
        """SynthesizerTrn forward() should return dur_info=None when use_sdp=True."""
        model = _make_synthesizer(use_sdp=True, prosody_dim=0)
        model.eval()

        batch_size = 2
        seq_len = 5
        spec_len = 32

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len, seq_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.tensor([spec_len, spec_len])

        with torch.no_grad():
            result = model(x, x_lengths, spec, spec_lengths)

        assert len(result) == 8, (
            f"forward() should return 8 elements, got {len(result)}"
        )

        dur_info = result[7]
        assert dur_info is None, (
            "dur_info should be None when use_sdp=True"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_dur_info_x_has_hidden_channels_only(self):
        """x in dur_info should have hidden_channels only (not prosody_dim).

        Duration Discriminator expects in_channels=hidden_channels, so dur_info
        returns x (text encoder output) rather than x_dp (which includes prosody).
        """
        prosody_dim = 16
        hidden_channels = 192
        model = _make_synthesizer(
            use_sdp=False,
            prosody_dim=prosody_dim,
            hidden_channels=hidden_channels,
        )
        model.eval()

        batch_size = 2
        seq_len = 5
        spec_len = 32

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len, seq_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.tensor([spec_len, spec_len])
        prosody_features = torch.randn(batch_size, seq_len, 3)

        with torch.no_grad():
            result = model(
                x, x_lengths, spec, spec_lengths,
                prosody_features=prosody_features,
            )

        dur_info = result[7]
        assert dur_info is not None
        x_hidden = dur_info[0]
        # x should have hidden_channels only (not hidden_channels + prosody_dim)
        # because DurationDiscriminatorV2 expects in_channels=hidden_channels
        assert x_hidden.shape[1] == hidden_channels, (
            f"x channels should be {hidden_channels}, got {x_hidden.shape[1]}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_dur_info_tensors_not_detached(self):
        """dur_info tensors should retain gradients (not detached) for generator training."""
        model = _make_synthesizer(use_sdp=False, prosody_dim=0)
        model.train()

        batch_size = 2
        seq_len = 5
        spec_len = 32

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len, seq_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.tensor([spec_len, spec_len])

        result = model(x, x_lengths, spec, spec_lengths)
        dur_info = result[7]

        assert dur_info is not None
        _x_dp, _logw, logw_hat = dur_info
        # logw_hat comes from the Duration Predictor and should require grad
        assert logw_hat.requires_grad, (
            "logw_hat should require grad for generator training"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_infer_returns_unchanged(self):
        """SynthesizerTrn.infer() return value should remain 4 elements (unchanged)."""
        model = _make_synthesizer(use_sdp=False, prosody_dim=0)
        model.eval()

        batch_size = 1
        seq_len = 5

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len])

        with torch.no_grad():
            result = model.infer(x, x_lengths)

        assert len(result) == 4, (
            f"infer() should still return 4 elements, got {len(result)}"
        )
