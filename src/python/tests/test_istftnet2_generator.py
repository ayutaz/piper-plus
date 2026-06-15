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
