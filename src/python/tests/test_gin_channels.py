"""
Tests for gin_channels optimization (VITS2 Phase 3 M4).

Verifies that:
- gin_channels=256 produces valid model (forward + infer)
- gin_channels=0 still works for single-speaker
- Model parameter count decreases with lower gin_channels
"""

import pytest

try:
    import torch
except ImportError:
    torch = None

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


class TestGinChannelsOptimization:
    """Tests for gin_channels 768->256 optimization."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_gin_channels_256_model_creation(self):
        """Model should be constructible with gin_channels=256."""
        model = _make_synthesizer(n_speakers=20, gin_channels=256)
        assert model.emb_g is not None
        assert model.emb_g.embedding_dim == 256

    @pytest.mark.unit
    @pytest.mark.training
    def test_gin_channels_256_forward(self):
        """Forward pass should work with gin_channels=256."""
        model = _make_synthesizer(n_speakers=5, gin_channels=256, use_sdp=False)
        model.eval()

        batch_size = 2
        seq_len = 5
        spec_len = 32

        x = torch.randint(0, 100, (batch_size, seq_len))
        x_lengths = torch.tensor([seq_len, seq_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.tensor([spec_len, spec_len])
        sid = torch.tensor([0, 1])

        with torch.no_grad():
            result = model(x, x_lengths, spec, spec_lengths, sid=sid)

        assert len(result) == 8, f"forward() should return 8 elements, got {len(result)}"

    @pytest.mark.unit
    @pytest.mark.training
    def test_gin_channels_256_infer(self):
        """Inference should work with gin_channels=256."""
        model = _make_synthesizer(n_speakers=5, gin_channels=256, use_sdp=False)
        model.eval()

        x = torch.randint(0, 100, (1, 5))
        x_lengths = torch.tensor([5])
        sid = torch.tensor([0])

        with torch.no_grad():
            result = model.infer(x, x_lengths, sid=sid)

        assert len(result) == 4

    @pytest.mark.unit
    @pytest.mark.training
    def test_gin_channels_0_single_speaker(self):
        """gin_channels=0 should still work for single-speaker models."""
        model = _make_synthesizer(n_speakers=1, gin_channels=0)
        assert not hasattr(model, 'emb_g') or model.emb_g is None

    @pytest.mark.unit
    @pytest.mark.training
    def test_param_count_decreases(self):
        """Lower gin_channels should result in fewer parameters."""
        model_768 = _make_synthesizer(n_speakers=5, gin_channels=768)
        model_256 = _make_synthesizer(n_speakers=5, gin_channels=256)

        params_768 = sum(p.numel() for p in model_768.parameters())
        params_256 = sum(p.numel() for p in model_256.parameters())

        assert params_256 < params_768, (
            f"gin_channels=256 ({params_256:,}) should have fewer params than "
            f"gin_channels=768 ({params_768:,})"
        )
        # Expect at least 3M fewer parameters
        diff = params_768 - params_256
        assert diff > 3_000_000, (
            f"Expected >3M param reduction, got {diff:,}"
        )
