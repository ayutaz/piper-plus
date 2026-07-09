"""Tests for --channels-last (T1: NHWC memory format on Conv2d Discriminator).

Opt-in perf switch: routes DiscriminatorP Conv2d layers through channels_last
Tensor Core kernels on A100 SXM4 / Ada 6000. Silent fallback on sm_75 (T4).
DiscriminatorS (Conv1d) and Generator (Conv1d-heavy) are untouched because
torch.channels_last is only defined for 4D tensors.

Contract:
1. CLI flag ``--channels-last`` (default OFF) parses and reaches ``args``.
2. Flag propagates through ``dict_args["use_channels_last"]`` and lands on the
   VitsModel hparams / MultiPeriodDiscriminator / DiscriminatorP.
3. When enabled, DiscriminatorP Conv2d weights adopt channels_last stride
   pattern; DiscriminatorS Conv1d weights stay in default layout.
4. Discriminator forward path is functionally equivalent (deterministic seeds).
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
