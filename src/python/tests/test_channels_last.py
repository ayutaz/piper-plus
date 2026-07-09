"""Tests for --channels-last (T1: NHWC memory format on Conv2d Discriminator).

Opt-in perf switch: routes DiscriminatorP Conv2d layers through channels_last
Tensor Core kernels on A100 SXM4 / Ada 6000. Silent fallback on sm_75 (T4).
DiscriminatorS (Conv1d) is untouched because torch.channels_last is only
defined for 4D tensors.

T1 拡張: MBiSTFTGenerator (SynthesizerTrn.dec) にも同一 flag を propagate。
現状 Generator は Conv1d のみで構成されるため PyTorch の
``Module.to(memory_format=torch.channels_last)`` が 3D weight を skip し
silent no-op。 (a) D 側との対称性、 (b) 将来 Generator に Conv2d を追加した
時の future-proofing、 の 2 目的で通す。

Contract:
1. CLI flag ``--channels-last`` (default OFF) parses and reaches ``args``.
2. Flag propagates through ``dict_args["use_channels_last"]`` and lands on the
   VitsModel hparams / MultiPeriodDiscriminator / DiscriminatorP AND on
   SynthesizerTrn (→ MBiSTFTGenerator).
3. When enabled, DiscriminatorP Conv2d weights adopt channels_last stride
   pattern; DiscriminatorS Conv1d and MBiSTFTGenerator Conv1d weights stay
   in default layout (PyTorch's Module.to() skips 3D tensors).
4. Discriminator forward path is functionally equivalent (deterministic seeds).
5. MBiSTFTGenerator forward path with flag ON does not crash (Conv1d only,
   silent no-op).
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
def test_channels_last_flag_default_off() -> None:
    """--channels-last is opt-in; default value is False."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args(_base_cli_args())
    assert hasattr(args, "channels_last")
    assert args.channels_last is False


@pytest.mark.unit
def test_channels_last_flag_can_be_enabled() -> None:
    """--channels-last on the command line sets args.channels_last True."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args([*_base_cli_args(), "--channels-last"])
    assert args.channels_last is True


# ---------------------------------------------------------------------------
# 2. hparam propagation into VitsModel + Discriminator
# ---------------------------------------------------------------------------


def _make_model(*, use_channels_last: bool):
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
        use_channels_last=use_channels_last,
    )


@pytest.mark.unit
def test_hparam_default_false() -> None:
    """When flag is omitted, use_channels_last hparam is False (safe default)."""
    model = _make_model(use_channels_last=False)
    assert model.hparams.use_channels_last is False
    assert model.model_d.use_channels_last is False
    # All DiscriminatorP instances see the propagated flag.
    from piper_train.vits.models import DiscriminatorP

    period_discs = [
        d for d in model.model_d.discriminators if isinstance(d, DiscriminatorP)
    ]
    assert len(period_discs) == 5  # periods=[2,3,5,7,11]
    for d in period_discs:
        assert d.use_channels_last is False


@pytest.mark.unit
def test_hparam_true_propagates_to_disc() -> None:
    """--channels-last=True flows to MultiPeriodDiscriminator and all sub-P discs."""
    model = _make_model(use_channels_last=True)
    assert model.hparams.use_channels_last is True
    assert model.model_d.use_channels_last is True
    from piper_train.vits.models import DiscriminatorP

    period_discs = [
        d for d in model.model_d.discriminators if isinstance(d, DiscriminatorP)
    ]
    for d in period_discs:
        assert d.use_channels_last is True


# ---------------------------------------------------------------------------
# 3. Standalone MultiPeriodDiscriminator construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_conv2d_weights_channels_last_stride() -> None:
    """When enabled, DiscriminatorP Conv2d weights use NHWC stride pattern."""
    try:
        from piper_train.vits.models import DiscriminatorP, MultiPeriodDiscriminator
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    mpd = MultiPeriodDiscriminator(use_channels_last=True)
    # At least one DiscriminatorP.Conv2d weight should be tagged channels_last.
    saw_channels_last = False
    for sub in mpd.discriminators:
        if not isinstance(sub, DiscriminatorP):
            continue
        for conv in sub.convs:
            w = conv.weight
            # weight_norm wraps the conv, unwrap via the .weight tensor.
            if w.dim() == 4 and w.is_contiguous(memory_format=torch.channels_last):
                saw_channels_last = True
                break
        if saw_channels_last:
            break
    assert saw_channels_last, (
        "expected at least one DiscriminatorP.Conv2d weight to be tagged "
        "channels_last after MultiPeriodDiscriminator(use_channels_last=True)"
    )


@pytest.mark.unit
def test_conv1d_weights_untouched_by_flag() -> None:
    """DiscriminatorS Conv1d weights (3D tensor) stay in default layout.

    torch.channels_last is only defined for 4D tensors, so DiscriminatorS is a
    silent no-op — we assert its 1D convs stay contiguous.
    """
    try:
        from piper_train.vits.models import DiscriminatorS, MultiPeriodDiscriminator
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    mpd = MultiPeriodDiscriminator(use_channels_last=True)
    for sub in mpd.discriminators:
        if isinstance(sub, DiscriminatorS):
            for conv in sub.convs:
                w = conv.weight
                assert w.dim() == 3, "DiscriminatorS should use Conv1d (3D weight)"
                assert w.is_contiguous(), (
                    "Conv1d weights should stay in default (contiguous) layout"
                )
            break


# ---------------------------------------------------------------------------
# 4. Functional parity (CPU-only smoke; NHWC dispatch is transparent)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_discriminator_forward_functional_parity_cpu() -> None:
    """Same seed → same discriminator output regardless of channels_last flag.

    channels_last only reorders memory; kernel math is bit-equivalent on the
    same device. On CPU the change is a no-op (nchw fallback), so this is a
    tight bit-parity check.
    """
    try:
        from piper_train.vits.models import MultiPeriodDiscriminator
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    torch.manual_seed(0)
    mpd_off = MultiPeriodDiscriminator(use_channels_last=False)
    torch.manual_seed(0)
    mpd_on = MultiPeriodDiscriminator(use_channels_last=True)

    mpd_off.eval()
    mpd_on.eval()

    y = torch.randn(2, 1, 8192)
    y_hat = torch.randn(2, 1, 8192)
    with torch.no_grad():
        out_off = mpd_off(y, y_hat)
        out_on = mpd_on(y, y_hat)

    # (y_d_rs, y_d_gs, fmap_rs, fmap_gs) — compare y_d_rs (the score tensors).
    for a, b in zip(out_off[0], out_on[0], strict=True):
        assert torch.allclose(a, b, atol=1e-5), (
            "DiscriminatorP outputs should match between channels_last on/off "
            "when weights are initialized with the same seed."
        )


# ---------------------------------------------------------------------------
# 5. T1 拡張: MBiSTFTGenerator (Conv1d-only) silent no-op plumbing
# ---------------------------------------------------------------------------


def _make_generator(*, use_channels_last: bool, gin_channels: int = 0):
    """Build a minimal MBiSTFTGenerator; skip if training deps missing.

    Uses tiny channels to keep test fast (no CUDA, no PQMF batch grind).
    """
    try:
        from piper_train.vits.mb_istft import MBiSTFTGenerator
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    return MBiSTFTGenerator(
        initial_channel=8,
        resblock="1",
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 3, 5),),
        upsample_rates=(4, 4),
        upsample_initial_channel=16,
        upsample_kernel_sizes=(8, 8),
        gin_channels=gin_channels,
        use_channels_last=use_channels_last,
    )


@pytest.mark.unit
def test_generator_hparam_default_false() -> None:
    """MBiSTFTGenerator.use_channels_last defaults to False (opt-in)."""
    gen = _make_generator(use_channels_last=False)
    assert gen.use_channels_last is False


@pytest.mark.unit
def test_generator_hparam_true_stored() -> None:
    """When constructed with use_channels_last=True, the attribute persists.

    This is the plumbing check: even though the flag is a silent no-op for
    the current Conv1d-only Generator, the attribute must exist so that a
    future Conv2d addition (or an assertion in downstream code) can inspect it.
    """
    gen = _make_generator(use_channels_last=True)
    assert gen.use_channels_last is True


@pytest.mark.unit
def test_generator_conv1d_weights_untouched_by_flag() -> None:
    """Enabling channels_last MUST NOT change Conv1d weight layout.

    PyTorch's Module.to(memory_format=torch.channels_last) only converts 4D/5D
    tensors (source: torch/nn/modules/module.py::_apply → convert:
    ``t.dim() in (4, 5)`` guard). All Conv1d weights are 3D, so they must
    remain in default (contiguous) layout even when the flag is True. If this
    invariant breaks, PyTorch upstream changed behavior and we need to add
    an explicit dim guard here.
    """
    gen = _make_generator(use_channels_last=True, gin_channels=8)

    conv1d_seen = 0
    for name, param in gen.named_parameters():
        if param.dim() == 3:  # Conv1d / ConvTranspose1d weight
            conv1d_seen += 1
            assert param.is_contiguous(), (
                f"Conv1d parameter {name} should stay in default contiguous "
                f"layout when use_channels_last=True (PyTorch skips 3D tensors "
                f"in Module.to(memory_format=...)). stride={param.stride()}, "
                f"shape={tuple(param.shape)}"
            )
    assert conv1d_seen > 0, (
        "MBiSTFTGenerator should contain at least one Conv1d parameter "
        "(conv_pre / ups / resblocks / subband_conv_post)."
    )


@pytest.mark.unit
def test_generator_forward_functional_parity_cpu() -> None:
    """Same seed → same Generator output regardless of channels_last flag.

    Since Conv1d weights are unchanged by the flag (see previous test), the
    forward pass must produce bit-identical output. This is our safety net:
    if a future refactor accidentally introduces a memory_format-sensitive
    Conv1d path (or the .to(memory_format=...) call ever mutates 3D weights),
    this test flags the regression.
    """
    torch.manual_seed(0)
    gen_off = _make_generator(use_channels_last=False, gin_channels=8)
    torch.manual_seed(0)
    gen_on = _make_generator(use_channels_last=True, gin_channels=8)

    gen_off.eval()
    gen_on.eval()

    x = torch.randn(1, 8, 16)  # [B, initial_channel, T_frames]
    g = torch.randn(1, 8, 1)  # [B, gin_channels, 1]

    with torch.no_grad():
        out_off = gen_off(x, g)
        out_on = gen_on(x, g)

    # (fullband, subbands_signal) tuple in training mode
    fullband_off, sub_off = out_off
    fullband_on, sub_on = out_on

    assert torch.allclose(fullband_off, fullband_on, atol=1e-5), (
        "MBiSTFTGenerator fullband output should be bit-identical between "
        "use_channels_last on/off (Conv1d is a silent no-op)."
    )
    assert torch.allclose(sub_off, sub_on, atol=1e-5), (
        "MBiSTFTGenerator subbands output should be bit-identical between "
        "use_channels_last on/off (Conv1d is a silent no-op)."
    )


# ---------------------------------------------------------------------------
# 6. T1 拡張: VitsModel → SynthesizerTrn → MBiSTFTGenerator propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flag_propagates_to_synthesizer_generator() -> None:
    """--channels-last=True reaches model_g.dec (MBiSTFTGenerator) attribute.

    Guards the wiring: lightning.py → SynthesizerTrn(use_channels_last=...) →
    MBiSTFTGenerator(use_channels_last=...). If a future refactor drops the
    kwarg on any hop, model_g.dec.use_channels_last would silently stay False
    and the future Conv2d NHWC dispatch would break unnoticed.
    """
    model = _make_model(use_channels_last=True)
    assert model.model_g.dec.use_channels_last is True, (
        "use_channels_last should propagate from VitsModel through "
        "SynthesizerTrn to MBiSTFTGenerator (self.model_g.dec)."
    )


@pytest.mark.unit
def test_flag_off_leaves_generator_flag_off() -> None:
    """Default (flag omitted) keeps model_g.dec.use_channels_last False."""
    model = _make_model(use_channels_last=False)
    assert model.model_g.dec.use_channels_last is False
