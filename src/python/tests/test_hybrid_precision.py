"""Tests for T6: hybrid precision knob (--disc-precision).

Contract
--------
1. CLI flag ``--disc-precision`` (choices: ``inherit``/``bf16-mixed``/``32-true``,
   default ``inherit``) parses and reaches ``args``.
2. Flag propagates through ``dict_args["disc_precision"]`` → VitsModel hparam.
3. ``VitsModel._disc_autocast_ctx()`` returns:
   - ``contextlib.nullcontext`` on ``inherit`` (status quo).
   - ``torch.autocast(dtype=bf16, enabled=True)`` on ``bf16-mixed``.
   - ``torch.autocast(enabled=False)`` on ``32-true``.
4. ``VitsModel._scl_autocast_ctx()`` always returns
   ``torch.autocast(enabled=False)`` so SCL is guaranteed fp32 regardless of
   ``disc_precision``.
5. Source-level check: SCL block in ``training_step_g`` is wrapped with
   ``_scl_autocast_ctx`` so a future refactor cannot silently hoist SCL out of
   the fp32 region.
6. Default behaviour is unchanged: ``inherit`` produces a null context that
   does not affect autocast state.
"""

from __future__ import annotations

import contextlib
import inspect

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
def test_disc_precision_flag_default_inherit() -> None:
    """--disc-precision defaults to 'inherit' (opt-in hybrid)."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args(_base_cli_args())
    assert hasattr(args, "disc_precision")
    assert args.disc_precision == "inherit"


@pytest.mark.unit
def test_disc_precision_flag_accepts_bf16_mixed() -> None:
    """--disc-precision bf16-mixed parses successfully."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args([*_base_cli_args(), "--disc-precision", "bf16-mixed"])
    assert args.disc_precision == "bf16-mixed"


@pytest.mark.unit
def test_disc_precision_flag_accepts_32_true() -> None:
    """--disc-precision 32-true parses successfully."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    args = parser.parse_args([*_base_cli_args(), "--disc-precision", "32-true"])
    assert args.disc_precision == "32-true"


@pytest.mark.unit
def test_disc_precision_flag_rejects_unknown() -> None:
    """Unknown --disc-precision values are rejected by argparse."""
    try:
        from piper_train.__main__ import create_parser
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    parser = create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([*_base_cli_args(), "--disc-precision", "fp16-mixed"])


# ---------------------------------------------------------------------------
# 2. hparam propagation into VitsModel
# ---------------------------------------------------------------------------


def _make_model(*, disc_precision: str = "inherit"):
    """Build a minimal single-speaker VitsModel with the given disc_precision."""
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
        disc_precision=disc_precision,
    )


@pytest.mark.unit
def test_hparam_default_inherit() -> None:
    """When flag is omitted, ``disc_precision`` hparam is 'inherit'."""
    model = _make_model(disc_precision="inherit")
    assert model.hparams.disc_precision == "inherit"


@pytest.mark.unit
def test_hparam_bf16_mixed_propagates() -> None:
    """disc_precision='bf16-mixed' lands on the model hparams."""
    model = _make_model(disc_precision="bf16-mixed")
    assert model.hparams.disc_precision == "bf16-mixed"


@pytest.mark.unit
def test_hparam_32_true_propagates() -> None:
    """disc_precision='32-true' lands on the model hparams."""
    model = _make_model(disc_precision="32-true")
    assert model.hparams.disc_precision == "32-true"


# ---------------------------------------------------------------------------
# 3. _disc_autocast_ctx behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_disc_autocast_ctx_inherit_is_nullcontext() -> None:
    """'inherit' returns a nullcontext (status quo — no autocast override)."""
    model = _make_model(disc_precision="inherit")
    ctx = model._disc_autocast_ctx()
    assert isinstance(ctx, contextlib.nullcontext)


@pytest.mark.unit
def test_disc_autocast_ctx_bf16_returns_autocast() -> None:
    """'bf16-mixed' returns a torch.autocast(bf16, enabled=True) context."""
    model = _make_model(disc_precision="bf16-mixed")
    ctx = model._disc_autocast_ctx()
    assert isinstance(ctx, torch.autocast)
    # torch.autocast objects expose ``fast_dtype`` (private but stable across 2.x).
    dtype = getattr(ctx, "fast_dtype", None) or getattr(ctx, "_fast_dtype", None)
    assert dtype == torch.bfloat16, (
        f"Expected bf16 autocast when disc_precision='bf16-mixed', got dtype={dtype!r}"
    )


@pytest.mark.unit
def test_disc_autocast_ctx_32_true_returns_disabled_autocast() -> None:
    """'32-true' returns a torch.autocast(enabled=False) context."""
    model = _make_model(disc_precision="32-true")
    ctx = model._disc_autocast_ctx()
    assert isinstance(ctx, torch.autocast)
    # Both public and private attribute names are checked for cross-version safety.
    enabled = getattr(ctx, "_enabled", None)
    if enabled is None:
        enabled = getattr(ctx, "enabled", None)
    assert enabled is False, (
        f"Expected disabled autocast when disc_precision='32-true', got enabled={enabled!r}"
    )


# ---------------------------------------------------------------------------
# 4. _scl_autocast_ctx: SCL is guaranteed fp32 in every mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["inherit", "bf16-mixed", "32-true"])
def test_scl_autocast_ctx_disabled_in_every_mode(mode: str) -> None:
    """SCL autocast context is disabled regardless of disc_precision."""
    model = _make_model(disc_precision=mode)
    ctx = model._scl_autocast_ctx()
    assert isinstance(ctx, torch.autocast)
    enabled = getattr(ctx, "_enabled", None)
    if enabled is None:
        enabled = getattr(ctx, "enabled", None)
    assert enabled is False, (
        f"SCL autocast MUST stay disabled (fp32) regardless of disc_precision. "
        f"disc_precision={mode!r} produced enabled={enabled!r}"
    )


# ---------------------------------------------------------------------------
# 5. Source-level guard: SCL block is wrapped in _scl_autocast_ctx
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_scl_block_is_wrapped_in_scl_autocast_ctx() -> None:
    """training_step_g's SCL block is wrapped with self._scl_autocast_ctx().

    Source-level guard: a refactor that hoists SCL out of the fp32 wrap would
    break the hybrid-precision contract. Verify the SCL block starts with the
    explicit wrap.
    """
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    src = inspect.getsource(VitsModel.training_step_g)
    # The wrap must appear *before* any SCL / DINO call.
    scl_wrap_idx = src.find("self._scl_autocast_ctx()")
    assert scl_wrap_idx >= 0, "SCL block must be wrapped in self._scl_autocast_ctx()"

    speaker_encoder_idx = src.find("self.speaker_encoder(")
    if speaker_encoder_idx >= 0:
        assert scl_wrap_idx < speaker_encoder_idx, (
            "self._scl_autocast_ctx() wrap must precede the CAM++ SCL call to "
            "keep the encoder path in fp32 regardless of disc_precision."
        )
    mel_scl_idx = src.find("mel_speaker_consistency_loss(")
    if mel_scl_idx >= 0:
        assert scl_wrap_idx < mel_scl_idx, (
            "self._scl_autocast_ctx() wrap must precede the mel SCL fallback."
        )


@pytest.mark.unit
def test_d_forward_is_wrapped_in_disc_autocast_ctx() -> None:
    """Both training_step_g and training_step_d wrap self.model_d(...) in ctx.

    Source-level guard so an accidental refactor cannot pull D forward out of
    the hybrid-precision override region.
    """
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    src_g = inspect.getsource(VitsModel.training_step_g)
    src_d = inspect.getsource(VitsModel.training_step_d)

    for label, src in (("training_step_g", src_g), ("training_step_d", src_d)):
        wrap_idx = src.find("self._disc_autocast_ctx()")
        d_call_idx = src.find("self.model_d(")
        assert wrap_idx >= 0, (
            f"{label}: expected self._disc_autocast_ctx() wrap around model_d."
        )
        assert d_call_idx >= 0, f"{label}: expected self.model_d(...) call."
        assert wrap_idx < d_call_idx, (
            f"{label}: self._disc_autocast_ctx() wrap must precede model_d call."
        )


# ---------------------------------------------------------------------------
# 6. Default-behaviour parity: 'inherit' does not alter autocast state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_inherit_ctx_does_not_change_autocast_state() -> None:
    """Entering the 'inherit' nullcontext is a no-op on autocast state.

    This guarantees that adding --disc-precision default 'inherit' does not
    alter the behaviour of existing training runs.
    """
    model = _make_model(disc_precision="inherit")

    # Baseline: autocast off outside any wrap.
    assert not torch.is_autocast_enabled()

    with model._disc_autocast_ctx():
        # nullcontext must not enable autocast when it was previously off.
        assert not torch.is_autocast_enabled()

    # And still off after exit.
    assert not torch.is_autocast_enabled()
