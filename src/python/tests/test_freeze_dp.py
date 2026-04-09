"""Tests for --freeze-dp (Duration Predictor freezing) functionality.

Prevents Duration Predictor catastrophic forgetting during fine-tuning
by freezing DP parameters and excluding them from the optimizer.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_model(freeze_dp=False, num_speakers=1, num_languages=2):
    """Create a minimal VitsModel with freeze_dp setting."""
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
        learning_rate=2e-5,
        freeze_dp=freeze_dp,
        use_wavlm_discriminator=False,
    )
    return model


@pytest.mark.unit
def test_freeze_dp_flag_default():
    """--freeze-dp defaults to False."""
    model = _make_model(freeze_dp=False)
    assert getattr(model.hparams, "freeze_dp", False) is False


@pytest.mark.unit
def test_freeze_dp_parameters_frozen():
    """DP params have requires_grad=False when --freeze-dp is set."""
    model = _make_model(freeze_dp=True)
    # Trigger configure_optimizers to apply freezing
    model.configure_optimizers()

    for name, param in model.model_g.named_parameters():
        if name.startswith("dp."):
            assert not param.requires_grad, (
                f"DP parameter {name} should be frozen (requires_grad=False)"
            )


@pytest.mark.unit
def test_freeze_dp_other_params_trainable():
    """Non-DP generator params remain trainable when --freeze-dp is set."""
    model = _make_model(freeze_dp=True)
    model.configure_optimizers()

    trainable_non_dp = [
        name
        for name, param in model.model_g.named_parameters()
        if not name.startswith("dp.") and param.requires_grad
    ]
    assert len(trainable_non_dp) > 0, (
        "Non-DP parameters should remain trainable"
    )


@pytest.mark.unit
def test_freeze_dp_optimizer_excludes_dp():
    """Optimizer only contains trainable (non-DP) parameters."""
    model = _make_model(freeze_dp=True)
    optimizers, _ = model.configure_optimizers()
    opt_g = optimizers[0]

    # Count DP parameters in generator
    dp_param_ids = {
        id(p)
        for name, p in model.model_g.named_parameters()
        if name.startswith("dp.")
    }

    # Check optimizer param groups don't include DP params
    for group in opt_g.param_groups:
        for param in group["params"]:
            assert id(param) not in dp_param_ids, (
                "Optimizer should not contain frozen DP parameters"
            )


@pytest.mark.unit
def test_no_freeze_dp_all_params_trainable():
    """Without --freeze-dp, all generator params are trainable."""
    model = _make_model(freeze_dp=False)
    model.configure_optimizers()

    frozen = [
        name
        for name, param in model.model_g.named_parameters()
        if not param.requires_grad
    ]
    assert len(frozen) == 0, (
        f"Without --freeze-dp, no params should be frozen, but found: {frozen}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw_value, expected_shape, expected_dtype, expected_item",
    [
        pytest.param(3, (1,), torch.long, 3, id="int"),
        pytest.param(torch.LongTensor([5]), (1,), torch.long, 5, id="1d-tensor"),
        pytest.param(
            torch.tensor(7, dtype=torch.long), (1,), torch.long, 7, id="0d-tensor"
        ),
        pytest.param(None, None, None, None, id="none"),
    ],
)
def test_speaker_id_tensor_handling(
    raw_value, expected_shape, expected_dtype, expected_item
):
    """normalize_id_tensor converts int/Tensor/None to shape-[1] LongTensor or None.

    Regression test: on_validation_epoch_end の audio logging で
    speaker_id が int (test_utterances.jsonl 経由) の場合と
    Tensor (random_split Subset 経由) の場合の両方を正しく処理できること。
    """
    from piper_train.vits.lightning import normalize_id_tensor

    result = normalize_id_tensor(raw_value)

    if expected_shape is None:
        assert result is None
    else:
        assert result.shape == expected_shape
        assert result.dtype == expected_dtype
        assert result.item() == expected_item
