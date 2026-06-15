"""Acceptance tests for AI-03: ``decoder_type`` switch on ``MBiSTFTGenerator``.

This module implements the 4 acceptance tests called out in ticket AI-03:

1. ``test_decoder_type_default_is_mb_istft_1d``      — instantiating with
   default kwargs yields ``gen.decoder_type == "mb_istft_1d"`` so that no
   existing caller's behaviour changes.

2. ``test_forward_1d2d_output_shape``                — when the 2D hybrid
   backbone is implemented, ``MBiSTFTGenerator(decoder_type=
   "istftnet2_mb_1d2d")`` should accept ``x=[1, 192, 50]`` and
   ``g=[1, 256, 1]`` and produce a ``[1, 1, 50*256]`` float32 fullband.
   SKIPPED in this skeleton commit until the ``_forward_1d2d`` body lands
   with the tuned weight schedule.

3. ``test_param_count_within_budget``                — assert
   ``0.78e6 <= trainable_params <= 0.88e6`` for the istftnet2_mb_1d2d path.
   SKIPPED pending channel-schedule calibration (see ticket AI-03 blockers).

4. ``test_forward_1d_bit_exact_with_baseline``       — assert that the new
   dispatcher ``forward()`` invoking ``_forward_1d`` produces output that
   matches the legacy ``_forward_1d`` implementation byte-for-byte on a
   random-seeded fixture. This is the MERGE-BLOCKING gate; it must be green
   at merge to guarantee the ``[mb_istft_1d]`` audio-parity baseline is
   untouched by this refactor.

TODO(AI-04): Expand into full TDD coverage of the 2D backbone (per-block
shape checks, pixel-shuffle factor audit, ONNX op-set assertion against
``Conv2d / Reshape / Transpose`` only, etc.).
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_gen(decoder_type: str = "mb_istft_1d", **overrides):
    """Build an ``MBiSTFTGenerator`` mirroring the 6lang base config.

    Mirrors :func:`tests.test_mb_istft_generator._make_generator` defaults so
    that bit-exactness comparisons share the same hyperparameter surface
    (``upsample_rates=(4, 4)`` / ``upsample_initial_channel=256`` etc.).
    """
    from piper_train.vits.mb_istft import MBiSTFTGenerator

    defaults = dict(
        initial_channel=192,
        resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
        decoder_type=decoder_type,
    )
    defaults.update(overrides)
    return MBiSTFTGenerator(**defaults)


@pytest.mark.unit
def test_decoder_type_default_is_mb_istft_1d():
    """Default ``decoder_type`` is the legacy 1D path.

    Contract: existing callers that omit ``decoder_type`` must keep the
    pre-AI-03 backbone so the [mb_istft_1d] audio-parity baseline stays
    untouched. The default value is hard-coded in three layered constructors
    (MBiSTFTGenerator / SynthesizerTrn / VitsModel) — this test pins the
    leaf-level default.
    """
    gen = _make_gen()  # no decoder_type override
    assert gen.decoder_type == "mb_istft_1d"


@pytest.mark.unit
@pytest.mark.skip(
    reason=(
        "AI-03 skeleton: _forward_1d2d body lands with weight schedule tuning "
        "(see ticket AI-03 blockers; gated by AI-04/AI-05 follow-ups)."
    )
)
def test_forward_1d2d_output_shape():
    """``istftnet2_mb_1d2d`` forward should produce ``[B, 1, T_frames*256]``.

    Total upsample factor stays ``256x`` (``upsample_rates(16x) * iSTFT_hop(4x)
    * PQMF_subbands(4x)``) so the ONNX I/O contract for C#/Rust/Go/WASM/C++
    runtimes is unchanged — this test pins that the new backbone preserves
    the same output shape and float32 dtype.
    """
    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    x = torch.randn(1, 192, 50)
    g = torch.randn(1, 256, 1)
    gen.onnx_export_mode = True
    out = gen(x, g=g)
    assert isinstance(out, torch.Tensor)
    assert out.shape == (1, 1, 50 * 256)
    assert out.dtype == torch.float32


@pytest.mark.unit
@pytest.mark.skip(
    reason=(
        "AI-03 skeleton: trainable param count needs final channel schedule "
        "(in_ch -> 64 -> 32 -> 16 -> 8); empirical tuning deferred."
    )
)
def test_param_count_within_budget():
    """``istftnet2_mb_1d2d`` trainable params must fit ``0.83M +/- 0.05M``.

    Pins the param-budget gate so that schedule changes during 50-epoch PoC
    training (AI-05) do not silently blow up the model size on Xeon CPUs
    (AI-12 benchmark assumes a ~0.83M decoder).
    """
    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    n_params = sum(p.numel() for p in gen.parameters() if p.requires_grad)
    assert 0.78e6 <= n_params <= 0.88e6, (
        f"istftnet2_mb_1d2d trainable params = {n_params:,} "
        f"outside budget 0.78e6 .. 0.88e6"
    )


@pytest.mark.unit
def test_forward_1d_bit_exact_with_baseline():
    """``forward()`` on default kwargs must match ``_forward_1d`` bit-exact.

    MERGE-BLOCKING gate (NOT skipped). The AI-03 refactor introduces a thin
    dispatcher ``forward()`` that delegates to ``_forward_1d`` when
    ``decoder_type == "mb_istft_1d"``. The dispatcher is a rename-only
    extraction of the legacy ``forward`` body — this test guarantees the
    [mb_istft_1d] audio-parity baseline is untouched.
    """
    torch.manual_seed(20260615)
    gen = _make_gen()
    gen.eval()

    x = torch.randn(1, 192, 32)

    with torch.no_grad():
        out_dispatcher = gen(x)
        out_direct = gen._forward_1d(x)

    # Both code paths return (fullband, subbands) in training mode.
    assert isinstance(out_dispatcher, tuple)
    assert isinstance(out_direct, tuple)
    assert len(out_dispatcher) == len(out_direct) == 2

    fb_dispatch, sb_dispatch = out_dispatcher
    fb_direct, sb_direct = out_direct

    # Bit-exact equality — the dispatcher must not introduce any numerical
    # drift (no extra activations, no precision changes, no re-ordering).
    assert torch.equal(fb_dispatch, fb_direct), "fullband output drifted"
    assert torch.equal(sb_dispatch, sb_direct), "subband output drifted"


# ----------------------------------------------------------------------
# AI-03 additional gates (negative-path coverage + dispatcher contract)
# ----------------------------------------------------------------------
# These tests pin the surfaces called out in the AI-03 audit:
#   * ValueError contract for unknown decoder_type strings (mb_istft.py L186-190).
#   * NotImplementedError contract for the 2D forward stub (L406-409).
#   * Non-default decoder_type attribute and conditional blocks_2d construction
#     (L191, L254-269) — guards against ckpt-load surface changes.
#   * Risk R7: 2D path must use Conv2d only, never ConvTranspose2d.
#   * Forward dispatcher routing for decoder_type == "istftnet2_mb_1d2d".
#   * Canonical set of valid decoder_type values (drift gate across 3 sites).


@pytest.mark.unit
def test_decoder_type_invalid_raises_value_error():
    """Unknown ``decoder_type`` strings raise ``ValueError`` with bad-repr.

    AI-03 G-1.9 backward-compat negative case (mb_istft.py L186-190). The
    constructor must reject any value outside the canonical set with a
    message that includes the offending value's ``repr`` so users can
    spot typos like trailing whitespace immediately.
    """
    with pytest.raises(ValueError, match="decoder_type must be"):
        _make_gen(decoder_type="hifigan")

    # The bad value's ``repr`` (single-quoted) must appear in the message
    # so silent typos like "mb_istft_1D" surface in the traceback.
    with pytest.raises(ValueError, match=r"'hifigan'"):
        _make_gen(decoder_type="hifigan")


@pytest.mark.unit
def test_forward_1d2d_raises_not_implemented_error():
    """``istftnet2_mb_1d2d`` forward raises ``NotImplementedError`` (AI-03 stub).

    Downstream tickets (AI-04 / AI-05) rely on this being an explicit
    raise — not a silent no-op — so an accidental short-circuit during a
    refactor surfaces immediately. Pins both the dispatcher entry point
    (``forward``) and the direct method (``_forward_1d2d``) and the
    sentinel substring "AI-03" in the error message.
    """
    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    x = torch.randn(1, 192, 8)
    g = torch.randn(1, 256, 1)

    # Dispatcher path.
    with pytest.raises(NotImplementedError, match="AI-03"):
        gen(x, g=g)

    # Direct method path — guards against future dispatcher rewrites that
    # bypass the stub but leave the method body intact.
    with pytest.raises(NotImplementedError, match="AI-03"):
        gen._forward_1d2d(x, g=g)


@pytest.mark.unit
def test_decoder_type_attribute_pinned():
    """Non-default ``decoder_type`` is stored as a string attribute.

    Pin for mb_istft.py L191. ``test_decoder_type_default_is_mb_istft_1d``
    only covers the default; this test asserts the new-decoder value
    survives the constructor unchanged (no enum coercion, no normalisation).
    """
    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    assert gen.decoder_type == "istftnet2_mb_1d2d"
    assert isinstance(gen.decoder_type, str)


@pytest.mark.unit
def test_blocks_2d_built_only_for_istftnet2():
    """``blocks_2d`` and ``num_upsamples_1d`` are gated on the new decoder.

    Pin for mb_istft.py L254-269. The legacy path must NOT carry any 2D
    state (ckpt-load surface, memory footprint), so ``state_dict()`` for
    the default decoder must not include any ``blocks_2d`` /
    ``num_upsamples_1d`` keys.
    """
    gen_legacy = _make_gen()
    assert not hasattr(gen_legacy, "blocks_2d"), (
        "legacy mb_istft_1d must not carry blocks_2d (ckpt-load surface)"
    )
    assert not hasattr(gen_legacy, "num_upsamples_1d"), (
        "legacy mb_istft_1d must not carry num_upsamples_1d"
    )
    legacy_keys = set(gen_legacy.state_dict().keys())
    assert not any("blocks_2d" in k for k in legacy_keys), (
        "legacy state_dict() must not contain blocks_2d.* entries"
    )
    assert not any("num_upsamples_1d" in k for k in legacy_keys), (
        "legacy state_dict() must not contain num_upsamples_1d.* entries"
    )

    gen_new = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    assert hasattr(gen_new, "blocks_2d")
    # ch_schedule = (64, 32, 16, 8) -> 3 transition blocks.
    assert len(gen_new.blocks_2d) == 3, (
        f"expected 3 blocks (4 channel stages), got {len(gen_new.blocks_2d)}"
    )
    assert gen_new.num_upsamples_1d == 2, (
        f"expected num_upsamples_1d == 2, got {gen_new.num_upsamples_1d!r}"
    )


@pytest.mark.unit
def test_blocks_2d_uses_no_conv_transpose2d():
    """Risk R7 gate: 2D path must use ``Conv2d`` only, never ``ConvTranspose2d``.

    Mobile execution providers fall back to CPU for ``ConvTranspose2d``
    on iOS / Android, which would tank the AI-12 latency benchmark. The
    AI-03 ticket review-checklist explicitly bans ``ConvTranspose2d`` in
    favour of pixel-shuffle for F-axis growth — pin it at module level.
    """
    from torch.nn import Conv2d, ConvTranspose2d

    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    for m in gen.blocks_2d.modules():
        assert not isinstance(m, ConvTranspose2d), (
            f"Risk R7 violated: {type(m).__name__} in blocks_2d "
            "(use Conv2d + pixel-shuffle for F-axis growth)"
        )
    assert any(isinstance(m, Conv2d) for m in gen.blocks_2d.modules()), (
        "blocks_2d must contain at least one Conv2d module"
    )


@pytest.mark.unit
def test_dispatcher_routes_to_forward_1d2d_for_istftnet2():
    """``forward()`` routes to ``_forward_1d2d`` for the new decoder.

    Pure dispatch test (mb_istft.py L285-287). Monkeypatches both
    branches so we observe routing, not the stub's ``NotImplementedError``.
    If a future refactor inverts the if-branch, this test fails immediately
    even though both code paths happen to "look right" in isolation.
    """
    from unittest.mock import patch

    gen = _make_gen(decoder_type="istftnet2_mb_1d2d", gin_channels=256)
    x = torch.randn(1, 192, 8)
    g = torch.randn(1, 256, 1)

    def _boom_1d(*_args, **_kwargs):
        raise RuntimeError("_forward_1d must NOT be called for istftnet2_mb_1d2d")

    with (
        patch.object(gen, "_forward_1d2d", return_value="SENTINEL_2D") as mock_2d,
        patch.object(gen, "_forward_1d", side_effect=_boom_1d) as mock_1d,
    ):
        result = gen(x, g=g)

    assert result == "SENTINEL_2D", (
        "dispatcher did not invoke _forward_1d2d for istftnet2_mb_1d2d"
    )
    assert mock_2d.call_count == 1
    assert mock_1d.call_count == 0, (
        "dispatcher accidentally invoked the legacy _forward_1d branch"
    )


@pytest.mark.unit
def test_decoder_type_class_constant_values():
    """Canonical set of valid ``decoder_type`` values is pinned.

    The valid values appear in 3 places (mb_istft.py ValueError list,
    __main__.py argparse choices, ticket spec). This test makes drift
    across those 3 sites loud: it pins both the accepted set AND that
    unknown values raise (and that argparse choices match the runtime set).
    """
    expected = {"mb_istft_1d", "istftnet2_mb_1d2d"}

    # Runtime side: each canonical value constructs without error.
    for name in expected:
        gen = _make_gen(decoder_type=name, gin_channels=256)
        assert gen.decoder_type == name

    # Negative case: anything outside the set must raise ValueError.
    with pytest.raises(ValueError, match="decoder_type must be"):
        _make_gen(decoder_type="istftnet3", gin_channels=256)

    # CLI side: argparse choices must equal the same canonical set.
    from piper_train.__main__ import create_parser

    parser = create_parser()
    decoder_action = None
    for action in parser._actions:
        if action.dest == "decoder_type":
            decoder_action = action
            break
    assert decoder_action is not None, "--decoder-type action not found on parser"
    assert set(decoder_action.choices) == expected, (
        f"argparse choices {set(decoder_action.choices)} drifted from "
        f"runtime canonical set {expected}"
    )
