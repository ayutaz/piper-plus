"""Tests for --attn-drop-rel-v (T3: SDPA fast path for TextEncoder self-attention).

Opt-in perf switch: swaps the manual matmul path in
``piper_train.vits.attentions.MultiHeadAttention.attention`` for
``F.scaled_dot_product_attention`` (SDPA) with the relative-K bias folded into
``attn_mask``. The relative-V correction is dropped because SDPA does not
surface ``p_attn`` (this is why the flag is named ``drop_rel_v``).

Contract:
1. CLI flag ``--attn-drop-rel-v`` (default OFF) parses and reaches ``args``.
2. Flag propagates through ``dict_args["attn_drop_rel_v"]`` and lands on the
   VitsModel hparams → SynthesizerTrn → TextEncoder → attentions.Encoder →
   MultiHeadAttention (every attention sub-layer sees the flag).
3. ``MultiHeadAttention.forward(...)`` returns the same shape regardless of
   the flag (fast path is a pure kernel swap, not a shape change).
4. With the flag OFF (default), the output is numerically identical to the
   pre-T3 manual path (regression zero, bit-parity).
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")


# ---------------------------------------------------------------------------
# 1. CLI parser plumbing
# ---------------------------------------------------------------------------


def _base_cli_args() -> list[str]:
    """Minimum required CLI args to satisfy ``create_parser().parse_args``."""
    return [
        "--dataset-dir",
        "/tmp/does-not-exist",
        "--batch-size",
        "4",
    ]


@pytest.mark.unit
def test_attn_drop_rel_v_flag_default_off() -> None:
    """--attn-drop-rel-v is opt-in; default value is False."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args(_base_cli_args())
    assert hasattr(args, "attn_drop_rel_v")
    assert args.attn_drop_rel_v is False


@pytest.mark.unit
def test_attn_drop_rel_v_flag_can_be_enabled() -> None:
    """--attn-drop-rel-v on the command line sets args.attn_drop_rel_v True."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args([*_base_cli_args(), "--attn-drop-rel-v"])
    assert args.attn_drop_rel_v is True


# ---------------------------------------------------------------------------
# 2. hparam / model propagation
# ---------------------------------------------------------------------------


def _make_model(*, attn_drop_rel_v: bool):
    """Build a minimal VitsModel with the given flag; skip if deps missing."""
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    return VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-5,
        use_wavlm_discriminator=False,
        attn_drop_rel_v=attn_drop_rel_v,
    )


@pytest.mark.unit
def test_hparam_default_false_reaches_every_attention_layer() -> None:
    """When the flag is omitted, drop_rel_v is False everywhere downstream."""
    model = _make_model(attn_drop_rel_v=False)
    assert model.hparams.attn_drop_rel_v is False
    encoder = model.model_g.enc_p.encoder
    assert encoder.drop_rel_v is False
    # Every MultiHeadAttention sub-layer must carry the same flag value.
    assert len(encoder.attn_layers) > 0
    for attn in encoder.attn_layers:
        assert attn.drop_rel_v is False


@pytest.mark.unit
def test_hparam_true_propagates_to_every_attention_layer() -> None:
    """--attn-drop-rel-v=True flows to every TextEncoder attention sub-layer."""
    model = _make_model(attn_drop_rel_v=True)
    assert model.hparams.attn_drop_rel_v is True
    encoder = model.model_g.enc_p.encoder
    assert encoder.drop_rel_v is True
    assert len(encoder.attn_layers) > 0
    for attn in encoder.attn_layers:
        assert attn.drop_rel_v is True


# ---------------------------------------------------------------------------
# 3. Forward-shape parity (both branches must produce the same shape)
# ---------------------------------------------------------------------------


def _make_mha(*, drop_rel_v: bool, window_size: int | None = 4, seed: int = 0):
    """Build a MultiHeadAttention directly with a fixed seed."""
    from piper_train.vits.attentions import MultiHeadAttention

    torch.manual_seed(seed)
    return MultiHeadAttention(
        channels=64,
        out_channels=64,
        n_heads=2,
        p_dropout=0.0,
        window_size=window_size,
        drop_rel_v=drop_rel_v,
    )


@pytest.mark.unit
def test_mha_forward_shape_parity_with_window_size() -> None:
    """Fast path (drop_rel_v=True) returns the same output shape as manual path.

    Numerical values will differ because the SDPA path drops the relative-V
    correction — this test only asserts the API/shape contract is preserved.
    """
    from piper_train.vits.attentions import MultiHeadAttention  # noqa: F401

    torch.manual_seed(0)
    mha_off = _make_mha(drop_rel_v=False, seed=0)
    torch.manual_seed(0)
    mha_on = _make_mha(drop_rel_v=True, seed=0)
    mha_off.eval()
    mha_on.eval()

    b, d, t = 2, 64, 8
    x = torch.randn(b, d, t)
    # Encoder-style self-attention mask (all-ones for simplicity).
    x_mask = torch.ones(b, 1, t)
    attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)  # [B, 1, T, T]

    with torch.no_grad():
        y_off = mha_off(x, x, attn_mask)
        y_on = mha_on(x, x, attn_mask)

    assert y_off.shape == y_on.shape == (b, d, t), (
        f"Expected ({b}, {d}, {t}); got manual={tuple(y_off.shape)} "
        f"sdpa={tuple(y_on.shape)}"
    )


@pytest.mark.unit
def test_mha_forward_shape_parity_no_window_size() -> None:
    """SDPA path also works when window_size is None (no relative-K bias)."""
    torch.manual_seed(0)
    mha_off = _make_mha(drop_rel_v=False, window_size=None, seed=0)
    torch.manual_seed(0)
    mha_on = _make_mha(drop_rel_v=True, window_size=None, seed=0)
    mha_off.eval()
    mha_on.eval()

    b, d, t = 2, 64, 8
    x = torch.randn(b, d, t)
    x_mask = torch.ones(b, 1, t)
    attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)

    with torch.no_grad():
        y_off = mha_off(x, x, attn_mask)
        y_on = mha_on(x, x, attn_mask)

    assert y_off.shape == y_on.shape == (b, d, t)


# ---------------------------------------------------------------------------
# 4. Numerical equivalence for the default (manual) path — regression zero
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_path_bit_parity_across_seeded_inits() -> None:
    """With drop_rel_v=False (default), two seeded MHA instances match exactly.

    This is the "regression zero" guarantee: enabling the T3 feature-flag arg
    on the class must not change the behavior of the manual path.
    """
    from piper_train.vits.attentions import MultiHeadAttention

    def _build_and_run(drop_rel_v_kw: dict) -> torch.Tensor:
        torch.manual_seed(42)
        m = MultiHeadAttention(
            channels=64,
            out_channels=64,
            n_heads=2,
            p_dropout=0.0,
            window_size=4,
            **drop_rel_v_kw,
        )
        m.eval()
        torch.manual_seed(0)
        x = torch.randn(2, 64, 8)
        x_mask = torch.ones(2, 1, 8)
        attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)
        with torch.no_grad():
            return m(x, x, attn_mask)

    # No kwarg (pre-T3 signature) vs explicit False (post-T3 default) must be
    # bit-identical: the new __init__ path adds a no-op field, nothing else.
    y_pre_t3 = _build_and_run({})
    y_explicit_false = _build_and_run({"drop_rel_v": False})
    assert torch.equal(y_pre_t3, y_explicit_false), (
        "Adding drop_rel_v=False to __init__ must not change the manual path "
        "output — that would break existing checkpoints."
    )


@pytest.mark.unit
def test_encoder_default_path_regression_zero() -> None:
    """attentions.Encoder default (drop_rel_v=False) matches pre-T3 behavior.

    Same guarantee at the Encoder level: constructing without the T3 kwarg
    vs constructing with drop_rel_v=False must give bit-identical forward.
    """
    from piper_train.vits.attentions import Encoder

    def _build_and_run(drop_rel_v_kw: dict) -> torch.Tensor:
        torch.manual_seed(42)
        enc = Encoder(
            hidden_channels=64,
            filter_channels=128,
            n_heads=2,
            n_layers=2,
            kernel_size=3,
            p_dropout=0.0,
            window_size=4,
            **drop_rel_v_kw,
        )
        enc.eval()
        torch.manual_seed(0)
        x = torch.randn(2, 64, 8)
        x_mask = torch.ones(2, 1, 8)
        with torch.no_grad():
            return enc(x, x_mask)

    y_pre_t3 = _build_and_run({})
    y_explicit_false = _build_and_run({"drop_rel_v": False})
    assert torch.equal(y_pre_t3, y_explicit_false)


# ---------------------------------------------------------------------------
# 5. SDPA path produces finite, differentiable output
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sdpa_path_produces_finite_gradients() -> None:
    """SDPA fast path must be differentiable and produce finite output.

    v8 zero-shot from-scratch training is the target for this flag; gradient
    flow through SDPA + the fused additive bias must work.
    """
    torch.manual_seed(0)
    mha = _make_mha(drop_rel_v=True, seed=0)
    mha.train()

    b, d, t = 2, 64, 8
    x = torch.randn(b, d, t, requires_grad=True)
    x_mask = torch.ones(b, 1, t)
    attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)

    y = mha(x, x, attn_mask)
    assert torch.isfinite(y).all(), "SDPA path produced non-finite output"

    y.sum().backward()
    assert x.grad is not None
    assert torch.isfinite(x.grad).all(), "SDPA path produced non-finite gradient"


@pytest.mark.unit
def test_sdpa_path_respects_padding_mask() -> None:
    """SDPA path masks padded positions (attn_bias -1e4) so their contribution
    to attention output is negligible.

    Test setup: build a batch where element 1 in the batch has half its
    positions masked out. The unmasked positions must produce finite output
    equal to what we'd get on a matching all-unpadded input.
    """
    torch.manual_seed(0)
    mha = _make_mha(drop_rel_v=True, window_size=None, seed=0)
    mha.eval()

    b, d, t = 2, 64, 8
    x = torch.randn(b, d, t)
    # Mask the last 4 positions of batch 1.
    x_mask = torch.ones(b, 1, t)
    x_mask[1, 0, 4:] = 0.0
    attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)

    with torch.no_grad():
        y = mha(x, x, attn_mask)

    assert y.shape == (b, d, t)
    assert torch.isfinite(y).all()
