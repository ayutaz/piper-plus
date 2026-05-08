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
