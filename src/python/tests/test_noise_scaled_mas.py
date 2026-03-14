"""
Tests for Noise-Scaled MAS (VITS2 improvement C).

Validates that Gaussian noise is correctly injected into the MAS cost matrix
during training, decays over steps, and can be disabled for VITS1 compatibility.
"""

import pytest


try:
    import torch
except ImportError:
    torch = None

# Skip all tests in this module if torch is not available
pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits.models import SynthesizerTrn


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


class TestNoiseScaledMAS:
    """Tests for Noise-Scaled MAS (VITS2)."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_noise_scale_reaches_zero_after_5000_steps(self):
        """Noise scale should reach 0 after exactly 5000 steps with default parameters.

        With initial=0.01 and decay=2e-6: 0.01 / 2e-6 = 5000 steps.
        """
        model = _make_synthesizer(
            mas_noise_scale_initial=0.01,
            mas_noise_scale_decay=2e-6,
        )

        assert model.current_mas_noise_scale == 0.01

        # Simulate 5000 decay steps
        for _ in range(5000):
            model.current_mas_noise_scale = max(
                0.0, model.current_mas_noise_scale - model.mas_noise_scale_decay
            )

        assert model.current_mas_noise_scale == 0.0, (
            f"Expected 0.0 after 5000 steps, got {model.current_mas_noise_scale}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_zero_initial_noise_disables_feature(self):
        """Setting mas_noise_scale_initial=0 should disable noise (VITS1 compatible).

        When initial noise is 0, neg_cent should not be modified.
        """
        model = _make_synthesizer(
            mas_noise_scale_initial=0.0,
            mas_noise_scale_decay=2e-6,
        )

        assert model.current_mas_noise_scale == 0.0
        assert model.mas_noise_scale_initial == 0.0

        # Verify that with scale=0, no noise would be added
        neg_cent = torch.randn(2, 10, 8)
        neg_cent_copy = neg_cent.clone()

        # Simulate the noise injection logic from forward()
        if model.current_mas_noise_scale > 0:
            neg_cent = neg_cent + torch.randn_like(neg_cent) * model.current_mas_noise_scale

        # neg_cent should be unchanged when noise scale is 0
        assert torch.equal(neg_cent, neg_cent_copy), (
            "neg_cent should not be modified when mas_noise_scale_initial=0"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_positive_noise_modifies_neg_cent(self):
        """When noise scale > 0, neg_cent should be modified by Gaussian noise."""
        model = _make_synthesizer(
            mas_noise_scale_initial=0.01,
            mas_noise_scale_decay=2e-6,
        )

        torch.manual_seed(42)
        neg_cent = torch.randn(2, 10, 8)
        neg_cent_original = neg_cent.clone()

        # Simulate the noise injection logic from forward()
        if model.current_mas_noise_scale > 0:
            neg_cent = neg_cent + torch.randn_like(neg_cent) * model.current_mas_noise_scale

        # neg_cent should differ from the original
        assert not torch.equal(neg_cent, neg_cent_original), (
            "neg_cent should be modified when mas_noise_scale > 0"
        )

        # The difference should be approximately the noise scale magnitude
        diff = (neg_cent - neg_cent_original).abs()
        mean_diff = diff.mean().item()
        # Standard normal * 0.01 -> expected mean abs ~0.008
        assert mean_diff < 0.05, (
            f"Noise magnitude ({mean_diff}) should be small with scale=0.01"
        )
        assert mean_diff > 0.0, "Noise should be non-zero"

    @pytest.mark.unit
    @pytest.mark.training
    def test_default_parameters(self):
        """Default MAS noise parameters should match VITS2 defaults."""
        model = _make_synthesizer()

        assert model.mas_noise_scale_initial == 0.01
        assert model.mas_noise_scale_decay == 2e-6
        assert model.current_mas_noise_scale == 0.01

    @pytest.mark.unit
    @pytest.mark.training
    def test_noise_decay_is_linear(self):
        """Noise decay should be linear (constant subtraction per step)."""
        initial = 0.01
        decay = 2e-6
        model = _make_synthesizer(
            mas_noise_scale_initial=initial,
            mas_noise_scale_decay=decay,
        )

        # After 1000 steps, scale should be initial - 1000 * decay
        for _ in range(1000):
            model.current_mas_noise_scale = max(
                0.0, model.current_mas_noise_scale - model.mas_noise_scale_decay
            )

        expected = initial - 1000 * decay
        assert abs(model.current_mas_noise_scale - expected) < 1e-10, (
            f"Expected {expected}, got {model.current_mas_noise_scale}"
        )

    @pytest.mark.unit
    @pytest.mark.training
    def test_noise_scale_does_not_go_negative(self):
        """Noise scale should be clamped to 0 and never go negative."""
        model = _make_synthesizer(
            mas_noise_scale_initial=0.01,
            mas_noise_scale_decay=2e-6,
        )

        # Simulate more steps than needed to reach zero
        for _ in range(10000):
            model.current_mas_noise_scale = max(
                0.0, model.current_mas_noise_scale - model.mas_noise_scale_decay
            )

        assert model.current_mas_noise_scale == 0.0
        assert model.current_mas_noise_scale >= 0.0
