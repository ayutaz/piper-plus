"""Tests for Style Vector Conditioning (Phase 1).

Covers TextEncoder / SynthesizerTrn style_vector integration:
- Backwards compatibility (style_vector_dim=0)
- Zero initialisation of the global-mode style_proj
- None-style fallback (treated as zeros)
- Dropout behaviour in train vs eval
- Mode validation (global/text/invalid)
- gin_channels requirement for global mode
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="torch required")


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_text_encoder(**overrides):
    """Create a minimal TextEncoder for unit tests.

    Uses deliberately small dims so CPU tests stay fast.
    """
    from piper_train.vits.models import TextEncoder

    kwargs = dict(
        n_vocab=100,
        out_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.1,
    )
    kwargs.update(overrides)
    return TextEncoder(**kwargs)


def _make_synthesizer(**overrides):
    """Create a minimal SynthesizerTrn for unit tests."""
    from piper_train.vits.models import SynthesizerTrn

    kwargs = dict(
        n_vocab=100,
        spec_channels=33,
        segment_size=32,
        inter_channels=64,
        hidden_channels=64,
        filter_channels=128,
        n_heads=2,
        n_layers=2,
        kernel_size=3,
        p_dropout=0.1,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(8, 8, 4),
        upsample_initial_channel=128,
        upsample_kernel_sizes=(16, 16, 8),
        n_speakers=4,
        n_languages=2,
        gin_channels=128,
        use_sdp=True,
        prosody_dim=0,
    )
    kwargs.update(overrides)
    return SynthesizerTrn(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStyleVectorConditioning:
    """Phase 1 style_vector unit tests (8 cases)."""

    @pytest.mark.unit
    def test_backwards_compatible_dim_0(self):
        """style_vector_dim=0 で既存挙動と完全に等価であることを確認."""
        torch.manual_seed(42)
        enc_default = _make_text_encoder()
        torch.manual_seed(42)
        enc_explicit_0 = _make_text_encoder(style_vector_dim=0)

        assert enc_default.style_proj is None
        assert enc_explicit_0.style_proj is None

        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        enc_default.eval()
        enc_explicit_0.eval()
        with torch.no_grad():
            out1 = enc_default(x, x_lengths)
            out2 = enc_explicit_0(x, x_lengths)
        for o1, o2 in zip(out1, out2, strict=True):
            assert torch.equal(o1, o2)

    @pytest.mark.unit
    def test_global_mode_projection_zero_init(self):
        """Global mode の style_proj がゼロ初期化されていること (最終層)."""
        model = _make_synthesizer(
            style_vector_dim=16,
            style_condition_mode="global",
        )
        assert model.style_proj is not None

        # Final Linear's weight/bias are zero-initialised so the Sequential
        # output is the zero tensor for any input.
        final_linear = model.style_proj[-1]
        assert torch.all(final_linear.weight == 0)
        assert torch.all(final_linear.bias == 0)

        style_vector = torch.randn(3, 16)
        with torch.no_grad():
            out = model.style_proj(style_vector)
        assert torch.allclose(out, torch.zeros_like(out))

    @pytest.mark.unit
    def test_style_vector_none_fallback(self):
        """style_vector=None で zeros fallback (style_proj がゼロ初期化のため None 同等)."""
        torch.manual_seed(123)
        model = _make_text_encoder(style_vector_dim=16)
        model.eval()

        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        with torch.no_grad():
            out_none = model(x, x_lengths, style_vector=None)
            out_zeros = model(x, x_lengths, style_vector=torch.zeros(2, 16))

        for a, b in zip(out_none, out_zeros, strict=True):
            assert torch.equal(a, b)

    @pytest.mark.unit
    def test_dropout_training_mode(self):
        """Training mode で dropout が効く (ランダム性あり)."""
        model = _make_text_encoder(
            style_vector_dim=16,
            style_condition_dropout=0.5,
        )
        # Replace the zero-initialised projection with random weights so that
        # the style contribution is non-zero and dropout is observable.
        with torch.no_grad():
            torch.nn.init.normal_(model.style_proj.weight)
            torch.nn.init.normal_(model.style_proj.bias)

        # Also zero out the attention encoder's internal dropout so the only
        # stochastic element is style_condition_dropout.
        model.encoder.drop.p = 0.0

        model.train()
        x = torch.randint(0, 100, (4, 6))
        x_lengths = torch.tensor([6, 6, 6, 6])
        style_vector = torch.randn(4, 16)

        torch.manual_seed(1)
        outputs = []
        for _ in range(8):
            out, *_ = model(x, x_lengths, style_vector=style_vector)
            outputs.append(out)

        # Not all eight outputs should be identical — dropout should flip some.
        any_different = any(
            not torch.equal(outputs[0], outputs[i]) for i in range(1, len(outputs))
        )
        assert any_different

    @pytest.mark.unit
    def test_dropout_eval_mode(self):
        """Eval mode で dropout が効かない (決定的)."""
        model = _make_text_encoder(
            style_vector_dim=16,
            style_condition_dropout=0.5,
        )
        with torch.no_grad():
            torch.nn.init.normal_(model.style_proj.weight)
            torch.nn.init.normal_(model.style_proj.bias)
        model.eval()

        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 10])
        style_vector = torch.randn(2, 16)
        with torch.no_grad():
            out1, *_ = model(x, x_lengths, style_vector=style_vector)
            out2, *_ = model(x, x_lengths, style_vector=style_vector)
        assert torch.equal(out1, out2)

    @pytest.mark.unit
    def test_text_mode_works_with_dim_0(self):
        """text mode + dim=0 で style_proj=None (SynthesizerTrn)."""
        model = _make_synthesizer(
            style_vector_dim=0,
            style_condition_mode="text",
        )
        assert model.style_proj is None
        assert model.enc_p.style_proj is None

    @pytest.mark.unit
    def test_global_mode_requires_gin_channels(self):
        """Global mode で gin_channels<=0 なら ValueError."""
        with pytest.raises(ValueError, match="gin_channels"):
            _make_synthesizer(
                style_vector_dim=16,
                style_condition_mode="global",
                gin_channels=0,
                n_speakers=1,
                n_languages=1,
            )

    @pytest.mark.unit
    def test_invalid_mode_raises(self):
        """未知の mode で ValueError."""
        with pytest.raises(ValueError, match="style_condition_mode"):
            _make_synthesizer(style_condition_mode="invalid")
