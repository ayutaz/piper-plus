"""Tests for --dp-lr (differential learning rate for Duration Predictor).

When --dp-lr is set, the generator optimizer uses two param groups:
one for Duration Predictor params at dp_lr, and one for all other
generator params at the base learning rate. This provides softer
regularization than --freeze-dp during fine-tuning.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_model(
    dp_lr=None,
    freeze_dp=False,
    num_speakers=1,
    num_languages=2,
    learning_rate=2e-5,
):
    """Create a minimal VitsModel with dp_lr setting."""
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    model = VitsModel(
        num_symbols=97,
        num_speakers=num_speakers,
        num_languages=num_languages,
        dataset=None,
        batch_size=4,
        learning_rate=learning_rate,
        freeze_dp=freeze_dp,
        dp_lr=dp_lr,
        use_wavlm_discriminator=False,
    )
    return model


@pytest.mark.unit
def test_dp_lr_creates_param_groups():
    """When dp_lr is set, generator optimizer should have 2 param groups with different LRs.

    Group 0: non-DP params at base learning_rate
    Group 1: DP params at dp_lr
    """
    base_lr = 2e-4
    dp_lr = 2e-5
    model = _make_model(dp_lr=dp_lr, learning_rate=base_lr)
    optimizers, _ = model.configure_optimizers()
    opt_g = optimizers[0]

    assert len(opt_g.param_groups) == 2, (
        f"Generator optimizer should have 2 param groups when dp_lr is set, "
        f"got {len(opt_g.param_groups)}"
    )

    # Group 0: non-DP params at base lr
    assert opt_g.param_groups[0]["lr"] == pytest.approx(base_lr), (
        f"Non-DP group lr should be {base_lr}, got {opt_g.param_groups[0]['lr']}"
    )
    # Group 1: DP params at dp_lr
    assert opt_g.param_groups[1]["lr"] == pytest.approx(dp_lr), (
        f"DP group lr should be {dp_lr}, got {opt_g.param_groups[1]['lr']}"
    )


@pytest.mark.unit
def test_dp_lr_none_uses_single_group():
    """When dp_lr is None (default), generator optimizer should have 1 param group.

    This ensures backward compatibility: without --dp-lr, all generator
    params are trained at a single learning rate.
    """
    model = _make_model(dp_lr=None)
    optimizers, _ = model.configure_optimizers()
    opt_g = optimizers[0]

    assert len(opt_g.param_groups) == 1, (
        f"Generator optimizer should have 1 param group when dp_lr is None, "
        f"got {len(opt_g.param_groups)}"
    )


@pytest.mark.unit
def test_dp_lr_with_freeze_dp():
    """When both dp_lr and freeze_dp are set, dp params should be empty (frozen).

    --freeze-dp takes precedence: DP params have requires_grad=False,
    so they are filtered out of both param groups. The dp_lr group
    should exist but contain no parameters (or the group is skipped).
    """
    model = _make_model(dp_lr=1e-5, freeze_dp=True)
    optimizers, _ = model.configure_optimizers()
    opt_g = optimizers[0]

    # When freeze_dp is active, DP params have requires_grad=False
    # The dp_lr branch still splits params, but dp group should be empty
    if len(opt_g.param_groups) == 2:
        dp_group = opt_g.param_groups[1]
        assert len(dp_group["params"]) == 0, (
            "DP param group should be empty when freeze_dp is True "
            "(all DP params are frozen)"
        )
    else:
        # If implementation collapses to single group when dp params are empty,
        # that is also acceptable
        assert len(opt_g.param_groups) == 1, (
            f"Expected 1 or 2 param groups, got {len(opt_g.param_groups)}"
        )


@pytest.mark.unit
def test_dp_lr_correct_param_split():
    """Verify dp.* params go to dp group, others go to the non-DP group.

    The parameter split should be based on the name prefix 'dp.'.
    """
    dp_lr = 5e-6
    model = _make_model(dp_lr=dp_lr)
    optimizers, _ = model.configure_optimizers()
    opt_g = optimizers[0]

    assert len(opt_g.param_groups) == 2, (
        "Expected 2 param groups for dp_lr split"
    )

    # Collect param ids for each group from the optimizer
    non_dp_param_ids = {id(p) for p in opt_g.param_groups[0]["params"]}
    dp_param_ids = {id(p) for p in opt_g.param_groups[1]["params"]}

    # Verify every trainable dp.* param is in the dp group
    for name, param in model.model_g.named_parameters():
        if not param.requires_grad:
            continue
        if name.startswith("dp."):
            assert id(param) in dp_param_ids, (
                f"DP parameter '{name}' should be in dp group (group 1)"
            )
            assert id(param) not in non_dp_param_ids, (
                f"DP parameter '{name}' should NOT be in non-DP group (group 0)"
            )
        else:
            assert id(param) in non_dp_param_ids, (
                f"Non-DP parameter '{name}' should be in non-DP group (group 0)"
            )
            assert id(param) not in dp_param_ids, (
                f"Non-DP parameter '{name}' should NOT be in dp group (group 1)"
            )
