"""Unit tests for `piper_train.vits.ema.EMACallback` lifecycle.

Covers the gap from the audit:
- `on_train_batch_end`: shadow params updated when step >= start_step and
  step % apply_ema_every_n_steps == 0
- `on_validation_epoch_start`: shadow params applied to model
- `on_validation_epoch_end`: original params restored
- `on_save_checkpoint`: ema state stored in checkpoint dict
- `on_load_checkpoint`: ema state restored from checkpoint dict
- adaptive decay rate (use_num_updates=True) progresses with num_updates
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("pytorch_lightning")

from torch import nn  # noqa: E402

from piper_train.vits.ema import EMACallback, ExponentialMovingAverage  # noqa: E402

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Test fixtures: minimal mock model that mimics piper's `model_g.dec` shape
# ---------------------------------------------------------------------------


class _DummyDecoder(nn.Module):
    """Minimal HiFi-GAN-like decoder for EMA tests (a single Linear layer)."""

    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(4, 4)
        # Initialize to a known state so we can verify shadow updates.
        with torch.no_grad():
            self.linear.weight.fill_(1.0)
            self.linear.bias.fill_(0.0)


class _DummyGenerator(nn.Module):
    """Mimics `model.model_g` with a `.dec` attribute."""

    def __init__(self):
        super().__init__()
        self.dec = _DummyDecoder()


class _DummyLightningModule:
    """Mimics the LightningModule attribute shape EMACallback inspects."""

    def __init__(self):
        self.model_g = _DummyGenerator()


class _DummyTrainer:
    def __init__(self, global_step: int = 0):
        self.global_step = global_step


# ---------------------------------------------------------------------------
# ExponentialMovingAverage — core update / apply / restore
# ---------------------------------------------------------------------------


class TestExponentialMovingAverageCore:
    def test_init_shadow_params_clones_current(self):
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=0.9)
        assert "linear.weight" in ema.shadow_params
        assert "linear.bias" in ema.shadow_params
        # Shadow starts equal to current params
        assert torch.allclose(
            ema.shadow_params["linear.weight"], model.linear.weight.data
        )

    def test_update_advances_shadow_toward_current(self):
        model = _DummyDecoder()
        # decay=0.5 with use_num_updates=False: shadow = 0.5*shadow + 0.5*current
        ema = ExponentialMovingAverage(model, decay=0.5, use_num_updates=False)
        # Mutate model weights to 2.0 — shadow should move halfway (to 1.5)
        with torch.no_grad():
            model.linear.weight.fill_(2.0)
        ema.update()
        expected = torch.full_like(model.linear.weight, 1.5)
        assert torch.allclose(ema.shadow_params["linear.weight"], expected)

    def test_update_with_adaptive_decay_progresses(self):
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=0.9995, use_num_updates=True)
        # First update: num_updates=1, decay=min(0.9995, (1+1)/(10+1))=2/11
        # Second update: num_updates=2, decay=min(0.9995, (1+2)/(10+2))=3/12
        ema.update()
        assert ema.num_updates == 1
        ema.update()
        assert ema.num_updates == 2

    def test_apply_shadow_then_restore_round_trip(self):
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=0.5, use_num_updates=False)
        # Set shadow = 7.0 and current = 1.0
        with torch.no_grad():
            ema.shadow_params["linear.weight"].fill_(7.0)
            model.linear.weight.fill_(1.0)
        ema.apply_shadow()
        # Now model holds shadow values
        assert torch.allclose(
            model.linear.weight, torch.full_like(model.linear.weight, 7.0)
        )
        # Backup retains the original 1.0
        assert torch.allclose(
            ema.backup_params["linear.weight"],
            torch.full_like(model.linear.weight, 1.0),
        )
        ema.restore()
        assert torch.allclose(
            model.linear.weight, torch.full_like(model.linear.weight, 1.0)
        )
        # Backup is cleared after restore
        assert ema.backup_params == {}

    def test_state_dict_round_trip(self):
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=0.999)
        ema.update()
        ema.update()
        sd = ema.state_dict()
        assert sd["decay"] == 0.999
        assert sd["num_updates"] == 2
        assert "linear.weight" in sd["shadow_params"]
        # Reload into a fresh EMA instance
        ema2 = ExponentialMovingAverage(_DummyDecoder(), decay=0.5)
        ema2.load_state_dict(sd)
        assert ema2.decay == 0.999
        assert ema2.num_updates == 2


# ---------------------------------------------------------------------------
# EMACallback — Lightning lifecycle hooks
# ---------------------------------------------------------------------------


class TestEMACallbackLifecycle:
    def test_on_fit_start_initializes_ema(self):
        callback = EMACallback(decay=0.999)
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)
        assert callback.ema_generator is not None
        assert callback.ema_discriminator is None  # disabled by default

    def test_on_train_batch_end_updates_ema_on_qualifying_steps(self):
        callback = EMACallback(decay=0.5, apply_ema_every_n_steps=1, start_step=0)
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)

        # Mutate model weights so update has effect
        with torch.no_grad():
            model.model_g.dec.linear.weight.fill_(3.0)

        trainer = _DummyTrainer(global_step=0)
        callback.on_train_batch_end(trainer, model, None, None, 0)
        # After update, shadow has moved from initial 1.0 toward 3.0
        # With adaptive decay (use_num_updates=True default): num_updates=1,
        # decay = min(0.5, (1+1)/(10+1)) = 2/11. shadow = (2/11)*1.0 + (9/11)*3.0
        expected_decay = 2 / 11
        expected_shadow = expected_decay * 1.0 + (1 - expected_decay) * 3.0
        actual = callback.ema_generator.shadow_params["linear.weight"][0, 0].item()
        assert actual == pytest.approx(expected_shadow, rel=1e-5)

    def test_on_train_batch_end_skips_before_start_step(self):
        callback = EMACallback(decay=0.5, apply_ema_every_n_steps=1, start_step=10)
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)
        # Step 5 < start_step=10, should not update
        with torch.no_grad():
            model.model_g.dec.linear.weight.fill_(3.0)
        trainer = _DummyTrainer(global_step=5)
        callback.on_train_batch_end(trainer, model, None, None, 0)
        # Shadow should remain at initial value 1.0
        assert callback.ema_generator.shadow_params["linear.weight"][0, 0].item() == 1.0
        assert callback.ema_generator.num_updates == 0

    def test_on_train_batch_end_respects_apply_every_n_steps(self):
        callback = EMACallback(
            decay=0.5, apply_ema_every_n_steps=5, start_step=0
        )
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)
        # Step 1: 1 % 5 != 0 → skip
        callback.on_train_batch_end(_DummyTrainer(global_step=1), model, None, None, 0)
        assert callback.ema_generator.num_updates == 0
        # Step 5: 5 % 5 == 0 → update
        callback.on_train_batch_end(_DummyTrainer(global_step=5), model, None, None, 0)
        assert callback.ema_generator.num_updates == 1
        # Step 10: 10 % 5 == 0 → update
        callback.on_train_batch_end(_DummyTrainer(global_step=10), model, None, None, 0)
        assert callback.ema_generator.num_updates == 2

    def test_validation_epoch_swaps_to_shadow_then_restores(self):
        callback = EMACallback(decay=0.5)
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)

        # Mutate: model=1.0 (initial), shadow=7.0 (synthetic)
        with torch.no_grad():
            callback.ema_generator.shadow_params["linear.weight"].fill_(7.0)

        original = model.model_g.dec.linear.weight.clone()
        callback.on_validation_epoch_start(_DummyTrainer(), model)
        # During validation: model holds shadow values
        assert torch.allclose(
            model.model_g.dec.linear.weight,
            torch.full_like(model.model_g.dec.linear.weight, 7.0),
        )
        callback.on_validation_epoch_end(_DummyTrainer(), model)
        # After validation: model restored to original
        assert torch.allclose(model.model_g.dec.linear.weight, original)

    def test_on_save_checkpoint_serializes_ema_state(self):
        callback = EMACallback(decay=0.999)
        model = _DummyLightningModule()
        callback.on_fit_start(_DummyTrainer(), model)
        callback.on_train_batch_end(_DummyTrainer(global_step=0), model, None, None, 0)

        checkpoint: dict = {}
        callback.on_save_checkpoint(_DummyTrainer(), model, checkpoint)
        assert "ema_generator_state" in checkpoint
        gen_state = checkpoint["ema_generator_state"]
        assert gen_state["decay"] == 0.999
        assert gen_state["num_updates"] == 1
        assert "linear.weight" in gen_state["shadow_params"]
        # Discriminator EMA disabled → state is None
        assert checkpoint["ema_discriminator_state"] is None

    def test_on_load_checkpoint_restores_ema_state(self):
        # Build a checkpoint from one callback, load into another
        callback_a = EMACallback(decay=0.999)
        model_a = _DummyLightningModule()
        callback_a.on_fit_start(_DummyTrainer(), model_a)
        for step in range(3):
            callback_a.on_train_batch_end(
                _DummyTrainer(global_step=step), model_a, None, None, 0
            )
        checkpoint: dict = {}
        callback_a.on_save_checkpoint(_DummyTrainer(), model_a, checkpoint)

        callback_b = EMACallback(decay=0.999)
        model_b = _DummyLightningModule()
        # No on_fit_start → ema_generator is None initially
        assert callback_b.ema_generator is None
        callback_b.on_load_checkpoint(_DummyTrainer(), model_b, checkpoint)
        assert callback_b.ema_generator is not None
        assert callback_b.ema_generator.num_updates == callback_a.ema_generator.num_updates


# ---------------------------------------------------------------------------
# Edge case: decay validation (audit gap #2)
# ---------------------------------------------------------------------------


class TestEMADecayValidation:
    """Pin behaviour for boundary / pathological decay values.

    The current implementation does NOT validate decay (no ValueError).
    These tests pin observable behaviour so future stricter validation
    will signal an intentional change.
    """

    def test_decay_zero_immediate_follow(self):
        """decay=0.0, use_num_updates=False -> shadow tracks current immediately.

        Update rule: shadow = decay*shadow + (1-decay)*current. With
        decay=0, shadow becomes current after a single update.
        """
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=0.0, use_num_updates=False)
        with torch.no_grad():
            model.linear.weight.fill_(5.0)
        ema.update()
        assert torch.allclose(
            ema.shadow_params["linear.weight"],
            torch.full_like(model.linear.weight, 5.0),
        )

    def test_decay_one_freeze_shadow(self):
        """decay=1.0, use_num_updates=False -> shadow frozen at init.

        Update rule with decay=1: shadow = 1*shadow + 0*current = shadow.
        Shadow stays at the initial value regardless of model param drift.
        """
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(model, decay=1.0, use_num_updates=False)
        # Drive model away from init (1.0 -> 9.0)
        with torch.no_grad():
            model.linear.weight.fill_(9.0)
        for _ in range(10):
            ema.update()
        assert torch.allclose(
            ema.shadow_params["linear.weight"],
            torch.full_like(model.linear.weight, 1.0),
        )

    def test_decay_negative_diverges_pin(self):
        """decay=-1.0 (use_num_updates=False) -> no error, divergent behaviour pinned.

        With decay=-1: shadow = -1*shadow + 2*current = 2*current - shadow.
        Starting shadow=1, current=2 (constant): step1=2*2-1=3, step2=2*2-3=1,
        oscillates between 3 and 1. We just pin "no exception is raised".
        """
        model = _DummyDecoder()
        # Should not raise (no validation in current code)
        ema = ExponentialMovingAverage(model, decay=-1.0, use_num_updates=False)
        with torch.no_grad():
            model.linear.weight.fill_(2.0)
        # Multiple updates — should not raise
        for _ in range(5):
            ema.update()
        # Shadow values are still tensors (no NaN guard expected here)
        assert "linear.weight" in ema.shadow_params

    def test_decay_nan_handling(self):
        """decay=NaN -> no exception, shadow becomes NaN. Pin current behaviour."""
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(
            model, decay=float("nan"), use_num_updates=False
        )
        with torch.no_grad():
            model.linear.weight.fill_(2.0)
        ema.update()
        # Pin: NaN propagates into shadow without raising
        assert torch.isnan(ema.shadow_params["linear.weight"]).any()

    def test_decay_inf_handling(self):
        """decay=+inf -> no exception, shadow may become inf/NaN. Pin behaviour."""
        model = _DummyDecoder()
        ema = ExponentialMovingAverage(
            model, decay=float("inf"), use_num_updates=False
        )
        with torch.no_grad():
            model.linear.weight.fill_(2.0)
        ema.update()
        # Pin: no exception. shadow = inf*1 + (1-inf)*2 -> inf or nan.
        shadow = ema.shadow_params["linear.weight"]
        assert (
            torch.isinf(shadow).any() or torch.isnan(shadow).any()
        ), f"decay=inf should produce inf or NaN values, got {shadow}"


# ---------------------------------------------------------------------------
# Edge case: apply_ema_weights vs remove_weight_norm() ordering (audit gap #4)
# ---------------------------------------------------------------------------


class TestEMAWithRemoveWeightNorm:
    """Regression test for export_onnx.py L428-L431 critical comment.

    EMA shadow params reference ``weight_g``/``weight_v`` keys created by
    ``torch.nn.utils.weight_norm``.  ``remove_weight_norm()`` fuses them
    into a single ``weight`` tensor, after which ``apply_ema_shadow_params``
    cannot find any matching key.
    """

    def _make_decoder_with_weight_norm(self):
        """Build a small Conv1d wrapped in weight_norm (mimics HiFi-GAN ResBlock)."""
        from torch.nn.utils import weight_norm

        decoder = nn.Sequential(weight_norm(nn.Conv1d(4, 4, kernel_size=3, padding=1)))
        return decoder

    def _make_shadow_params(self, decoder):
        """Build shadow params from current decoder state (matches weight_g/v)."""
        return {
            name: param.data.clone() + 0.1
            for name, param in decoder.named_parameters()
        }

    def test_apply_ema_before_remove_weight_norm_succeeds(self):
        """正常 path: EMA を weight_norm 解除 *前* に適用すれば weight_g/v が一致."""
        from piper_train.export_onnx import apply_ema_shadow_params

        decoder = self._make_decoder_with_weight_norm()
        shadow_params = self._make_shadow_params(decoder)
        # Sanity: weight_norm produces weight_g and weight_v
        names = set(dict(decoder.named_parameters()).keys())
        assert any("weight_g" in n for n in names), (
            f"weight_norm should expose weight_g, got {names}"
        )

        applied, skipped = apply_ema_shadow_params(decoder, shadow_params)
        assert applied == len(shadow_params), (
            f"All shadow params should match weight_g/weight_v keys "
            f"(applied={applied}, expected={len(shadow_params)})"
        )
        assert skipped == 0

    def test_apply_ema_after_remove_weight_norm_fails(self):
        """remove_weight_norm 後に EMA shadow を適用すると全てが skipped になる.

        Pin the regression: weight_g/weight_v keys vanish after
        remove_weight_norm(), and ``applied`` becomes 0 with all
        shadow keys reported as skipped.
        """
        from piper_train.export_onnx import apply_ema_shadow_params

        decoder = self._make_decoder_with_weight_norm()
        # Capture shadow params BEFORE remove_weight_norm (these have weight_g/v keys)
        shadow_params = self._make_shadow_params(decoder)

        # Now remove weight norm — fuses weight_g + weight_v into single "weight"
        # Find the wrapped Conv1d module and unwrap it
        from torch.nn.utils import remove_weight_norm

        for module in decoder.modules():
            if isinstance(module, nn.Conv1d):
                remove_weight_norm(module)

        # Verify weight_g/v are gone
        post_names = set(dict(decoder.named_parameters()).keys())
        assert not any("weight_g" in n for n in post_names), (
            f"weight_g should be removed, got {post_names}"
        )

        # Now apply_ema_shadow_params: all shadow keys are unmatched
        applied, skipped = apply_ema_shadow_params(decoder, shadow_params)
        assert applied == 0, (
            f"After remove_weight_norm(), no weight_g/v keys remain to apply "
            f"(applied={applied}, expected=0)"
        )
        assert skipped == len(shadow_params), (
            f"All {len(shadow_params)} shadow keys should be skipped, got {skipped}"
        )
