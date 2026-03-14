"""
Tests for VITS2 Speaker-Conditioned TextEncoder (Phase 3 M5).

Verifies that:
- speaker_conditioned_encoder=True adds cond_proj to encoder
- speaker_conditioned_encoder=False (default) has no cond_proj
- Forward/infer work with speaker conditioning
- Single-speaker (gin_channels=0) correctly skips conditioning
"""

import pytest

try:
    import torch
except ImportError:
    torch = None

pytestmark = pytest.mark.skipif(torch is None, reason="torch not installed")

if torch is not None:
    from piper_train.vits.models import SynthesizerTrn, TextEncoder
    from piper_train.vits.attentions import Encoder


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


class TestEncoderSpeakerConditioning:
    """Tests for Encoder-level speaker conditioning."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_encoder_cond_proj_exists(self):
        """Encoder with gin_channels>0 should have cond_proj."""
        enc = Encoder(
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            gin_channels=256,
        )
        assert hasattr(enc, 'cond_proj'), "cond_proj should exist when gin_channels>0"

    @pytest.mark.unit
    @pytest.mark.training
    def test_encoder_no_cond_proj_default(self):
        """Encoder with gin_channels=0 should NOT have cond_proj."""
        enc = Encoder(
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
        )
        assert not hasattr(enc, 'cond_proj'), "cond_proj should not exist when gin_channels=0"

    @pytest.mark.unit
    @pytest.mark.training
    def test_encoder_cond_layer_idx(self):
        """cond_layer_idx should be n_layers//2 - 1 (3rd layer for 6 layers)."""
        enc = Encoder(
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            gin_channels=256,
        )
        assert enc.cond_layer_idx == 2, f"Expected cond_layer_idx=2, got {enc.cond_layer_idx}"

    @pytest.mark.unit
    @pytest.mark.training
    def test_encoder_forward_with_g(self):
        """Encoder forward should work with speaker conditioning."""
        enc = Encoder(
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            gin_channels=256,
        )
        enc.eval()

        batch_size = 2
        seq_len = 10
        x = torch.randn(batch_size, 192, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)
        g = torch.randn(batch_size, 256, 1)

        with torch.no_grad():
            output = enc(x, x_mask, g=g)

        assert output.shape == (batch_size, 192, seq_len)

    @pytest.mark.unit
    @pytest.mark.training
    def test_encoder_forward_without_g(self):
        """Encoder forward should work without g (backward compat)."""
        enc = Encoder(
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            gin_channels=256,
        )
        enc.eval()

        batch_size = 2
        seq_len = 10
        x = torch.randn(batch_size, 192, seq_len)
        x_mask = torch.ones(batch_size, 1, seq_len)

        with torch.no_grad():
            output = enc(x, x_mask)

        assert output.shape == (batch_size, 192, seq_len)


class TestTextEncoderSpeakerConditioning:
    """Tests for TextEncoder-level speaker conditioning."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_text_encoder_passes_gin_channels(self):
        """TextEncoder should pass gin_channels to its Encoder."""
        te = TextEncoder(
            n_vocab=100,
            out_channels=192,
            hidden_channels=192,
            filter_channels=768,
            n_heads=2,
            n_layers=6,
            kernel_size=3,
            p_dropout=0.1,
            gin_channels=256,
        )
        assert hasattr(te.encoder, 'cond_proj')


class TestSynthesizerTrnSpeakerCondEncoder:
    """Tests for SynthesizerTrn with speaker_conditioned_encoder."""

    @pytest.mark.unit
    @pytest.mark.training
    def test_speaker_cond_encoder_enabled(self):
        """When enabled, enc_p's encoder should have cond_proj."""
        model = _make_synthesizer(
            n_speakers=5,
            gin_channels=256,
            speaker_conditioned_encoder=True,
        )
        assert hasattr(model.enc_p.encoder, 'cond_proj')

    @pytest.mark.unit
    @pytest.mark.training
    def test_speaker_cond_encoder_disabled_default(self):
        """When disabled (default), enc_p's encoder should NOT have cond_proj."""
        model = _make_synthesizer(
            n_speakers=5,
            gin_channels=256,
            speaker_conditioned_encoder=False,
        )
        assert not hasattr(model.enc_p.encoder, 'cond_proj')

    @pytest.mark.unit
    @pytest.mark.training
    def test_speaker_cond_encoder_single_speaker(self):
        """Single speaker + speaker_conditioned_encoder should not add cond_proj."""
        model = _make_synthesizer(
            n_speakers=1,
            gin_channels=0,
            speaker_conditioned_encoder=True,
        )
        assert not hasattr(model.enc_p.encoder, 'cond_proj')

    @pytest.mark.unit
    @pytest.mark.training
    def test_forward_with_speaker_cond_encoder(self):
        """Forward pass should work with speaker_conditioned_encoder=True."""
        model = _make_synthesizer(
            n_speakers=5,
            gin_channels=256,
            speaker_conditioned_encoder=True,
            use_sdp=False,
        )
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

        assert len(result) == 8

    @pytest.mark.unit
    @pytest.mark.training
    def test_infer_with_speaker_cond_encoder(self):
        """Inference should work with speaker_conditioned_encoder=True."""
        model = _make_synthesizer(
            n_speakers=5,
            gin_channels=256,
            speaker_conditioned_encoder=True,
            use_sdp=False,
        )
        model.eval()

        x = torch.randint(0, 100, (1, 5))
        x_lengths = torch.tensor([5])
        sid = torch.tensor([0])

        with torch.no_grad():
            result = model.infer(x, x_lengths, sid=sid)

        assert len(result) == 4
