import logging

import torch
from pytorch_lightning.callbacks import Callback
from torch import nn

from .commons import migrate_prefilm_decoder_cond


_LOGGER = logging.getLogger(__name__)

# v10b S-5: ``--ema-scope extended`` で EMA 対象に加えるサブモジュール
# (``model_g`` の属性名)。存在しないものは黙って skip する
# (spk_proj_dp は --dp-spk-head 時のみ生える)。
#
# 背景: 現行 EMA は dec + spk_proj のみで、v10a の崩壊経路そのものだった
# flow (SNAC スケールの単調成長) が対象外だった (v10-design §10 所見 5)。
EXTENDED_EMA_MODULES: tuple[str, ...] = ("flow", "enc_p", "spk_proj_dp")

EMA_SCOPES: tuple[str, ...] = ("legacy", "extended")


class ExponentialMovingAverage:
    """Exponential Moving Average for model parameters.

    Improves training stability and quality for the neural vocoder generator
    (MB-iSTFT-VITS2 decoder in v1.12.0+; HiFi-GAN generator in legacy v1.11 ckpts).
    Particularly effective for preventing quality degradation during fine-tuning.
    """

    def __init__(
        self,
        model: nn.Module,
        decay: float = 0.999,
        use_num_updates: bool = True,
        power: float = 2 / 3,
    ):
        """
        Args:
            model: The model to track
            decay: Base decay rate (default: 0.999)
            use_num_updates: Whether to use adaptive decay based on update count
            power: Power for adaptive decay computation
        """
        self.model = model
        self.decay = decay
        self.use_num_updates = use_num_updates
        self.power = power
        self.num_updates = 0

        # Create shadow copy of model parameters
        self.shadow_params = {}
        self.backup_params = {}

        # Initialize shadow parameters
        self._init_shadow_params()

    def _init_shadow_params(self):
        """Initialize shadow parameters with current model values."""
        for name, param in self.model.named_parameters():
            if param.requires_grad:
                self.shadow_params[name] = param.data.clone().detach()

    def update(self):
        """Update shadow parameters with current model parameters."""
        if self.use_num_updates:
            self.num_updates += 1
            # Adaptive decay rate based on number of updates
            decay = min(self.decay, (1 + self.num_updates) / (10 + self.num_updates))
        else:
            decay = self.decay

        with torch.no_grad():
            for name, param in self.model.named_parameters():
                if param.requires_grad and name in self.shadow_params:
                    # EMA update: shadow = decay * shadow + (1 - decay) * current
                    self.shadow_params[name].mul_(decay).add_(
                        param.data, alpha=1 - decay
                    )

    def apply_shadow(self):
        """Apply shadow parameters to model (for evaluation)."""
        for name, param in self.model.named_parameters():
            if param.requires_grad and name in self.shadow_params:
                self.backup_params[name] = param.data.clone()
                param.data.copy_(self.shadow_params[name])

    def restore(self):
        """Restore original parameters after evaluation."""
        for name, param in self.model.named_parameters():
            if param.requires_grad and name in self.backup_params:
                param.data.copy_(self.backup_params[name])
        self.backup_params = {}

    def state_dict(self):
        """Get state dict for checkpointing."""
        return {
            "decay": self.decay,
            "num_updates": self.num_updates,
            "shadow_params": self.shadow_params,
        }

    def load_state_dict(self, state_dict):
        """Load from checkpoint."""
        self.decay = state_dict["decay"]
        self.num_updates = state_dict["num_updates"]
        self.shadow_params = state_dict["shadow_params"]

    def to(self, device):
        """Move shadow parameters to device."""
        for name in self.shadow_params:
            self.shadow_params[name] = self.shadow_params[name].to(device)


class EMACallback(Callback):
    """PyTorch Lightning callback for EMA during training.

    ``scope`` (v10b S-5):

    - ``"legacy"`` (default): ``dec`` + ``spk_proj`` のみ — 従来と bit 互換
    - ``"extended"``: 加えて :data:`EXTENDED_EMA_MODULES` (flow / enc_p /
      spk_proj_dp) を追跡する。SNAC flow (v10 M1) 導入後の必須整備で、
      ckpt に ``ema_scope`` を記録するため export 側が自動判別できる
    """

    def __init__(
        self,
        decay: float = 0.999,
        apply_ema_every_n_steps: int = 1,
        start_step: int = 0,
        save_ema_weights_in_callback_state: bool = True,
        scope: str = "legacy",
    ):
        if scope not in EMA_SCOPES:
            raise ValueError(
                f"unknown EMA scope: {scope!r} (expected one of {EMA_SCOPES})"
            )
        self.decay = decay
        self.apply_ema_every_n_steps = apply_ema_every_n_steps
        self.start_step = start_step
        self.save_ema_weights_in_callback_state = save_ema_weights_in_callback_state
        self.scope = scope

        self.ema_generator = None
        self.ema_spk_proj = None
        self.ema_discriminator = None
        # scope="extended" の追加対象。{属性名: ExponentialMovingAverage}
        self.ema_extended: dict[str, ExponentialMovingAverage] = {}
        self._needs_device_sync = False

    def _all_emas(self):
        """全 EMA インスタンスを列挙する (None は除く)。"""
        for ema in (self.ema_generator, self.ema_spk_proj, self.ema_discriminator):
            if ema is not None:
                yield ema
        yield from self.ema_extended.values()

    def _init_extended(self, model):
        """scope="extended" の対象サブモジュールに EMA を張る (存在するものだけ)。"""
        if self.scope != "extended":
            return
        for name in EXTENDED_EMA_MODULES:
            if name in self.ema_extended:
                continue
            module = getattr(model.model_g, name, None)
            if module is None:
                continue
            self.ema_extended[name] = ExponentialMovingAverage(module, decay=self.decay)
        if self.ema_extended:
            _LOGGER.info(
                "EMA scope=extended: tracking %s in addition to dec / spk_proj",
                ", ".join(sorted(self.ema_extended)),
            )

    def on_fit_start(self, trainer, model):
        """Initialize EMA for generator and discriminator."""
        # Only apply EMA to generator (MB-iSTFT-VITS2 decoder)
        # Only initialize if not already loaded from checkpoint
        if self.ema_generator is None:
            self.ema_generator = ExponentialMovingAverage(
                model.model_g.dec,  # MB-iSTFT decoder
                decay=self.decay,
            )

        # Also track spk_proj for zero-shot stability
        if self.ema_spk_proj is None and hasattr(model.model_g, "spk_proj"):
            self.ema_spk_proj = ExponentialMovingAverage(
                model.model_g.spk_proj,
                decay=self.decay,
            )

        self._init_extended(model)

    def on_train_batch_end(self, trainer, model, outputs, batch, batch_idx):
        """Update EMA after each training step."""
        # Bug 1 fix: sync shadow params to correct device after checkpoint resume
        if self._needs_device_sync:
            device = next(model.parameters()).device
            for ema in self._all_emas():
                ema.to(device)
            self._needs_device_sync = False

        step = trainer.global_step

        if step >= self.start_step and step % self.apply_ema_every_n_steps == 0:
            for ema in self._all_emas():
                ema.update()

    def on_validation_epoch_start(self, trainer, model):
        """Apply EMA weights for validation."""
        for ema in self._all_emas():
            ema.apply_shadow()

    def on_validation_epoch_end(self, trainer, model):
        """Restore original weights after validation."""
        for ema in self._all_emas():
            ema.restore()

    def on_save_checkpoint(self, trainer, model, checkpoint):
        """Save EMA state in checkpoint."""
        if self.save_ema_weights_in_callback_state:
            checkpoint["ema_generator_state"] = (
                self.ema_generator.state_dict() if self.ema_generator else None
            )
            checkpoint["ema_spk_proj_state"] = (
                self.ema_spk_proj.state_dict() if self.ema_spk_proj else None
            )
            checkpoint["ema_discriminator_state"] = (
                self.ema_discriminator.state_dict() if self.ema_discriminator else None
            )
            # v10b S-5: scope と拡張 shadow。export_onnx が ``ema_scope`` /
            # ``ema_extended_state`` の有無で適用先を自動判別する
            checkpoint["ema_scope"] = self.scope
            checkpoint["ema_extended_state"] = {
                name: ema.state_dict() for name, ema in self.ema_extended.items()
            }

    def on_load_checkpoint(self, trainer, model, checkpoint):
        """Load EMA state from checkpoint."""
        if checkpoint.get("ema_generator_state"):
            if self.ema_generator is None:
                self.ema_generator = ExponentialMovingAverage(
                    model.model_g.dec, decay=self.decay
                )
            # `VitsModel.on_load_checkpoint` normally migrates pre-FiLM shadow
            # params before this runs (Lightning restores the module before its
            # callbacks). Repeating it here keeps that ordering from being a
            # single point of failure — the migration is idempotent, so a
            # second pass is a no-op (issue #616).
            ema_state = checkpoint["ema_generator_state"]
            if isinstance(ema_state, dict) and ema_state.get("shadow_params"):
                ema_state["shadow_params"], _ = migrate_prefilm_decoder_cond(
                    ema_state["shadow_params"], model.model_g.dec.state_dict()
                )
            self.ema_generator.load_state_dict(ema_state)

        if checkpoint.get("ema_spk_proj_state"):
            if self.ema_spk_proj is None and hasattr(model.model_g, "spk_proj"):
                self.ema_spk_proj = ExponentialMovingAverage(
                    model.model_g.spk_proj, decay=self.decay
                )
            if self.ema_spk_proj is not None:
                self.ema_spk_proj.load_state_dict(checkpoint["ema_spk_proj_state"])

        if checkpoint.get("ema_discriminator_state"):
            if self.ema_discriminator is None:
                self.ema_discriminator = ExponentialMovingAverage(
                    model.model_d, decay=self.decay
                )
            self.ema_discriminator.load_state_dict(
                checkpoint["ema_discriminator_state"]
            )

        # v10b S-5: 拡張 shadow を持つ ckpt から legacy scope で resume すると、
        # shadow は validation で適用されるのに更新されず陳腐化する (静かに悪化)。
        # ckpt に記録された scope を採用して更新を継続させる。
        extended_state = checkpoint.get("ema_extended_state") or {}
        if extended_state:
            ckpt_scope = checkpoint.get("ema_scope", "extended")
            if ckpt_scope != self.scope:
                _LOGGER.warning(
                    "Checkpoint was trained with --ema-scope %s but this run "
                    "requested %s; adopting the checkpoint scope so the "
                    "extended shadows keep updating.",
                    ckpt_scope,
                    self.scope,
                )
                self.scope = ckpt_scope
            for name, state in extended_state.items():
                module = getattr(model.model_g, name, None)
                if module is None:
                    _LOGGER.warning(
                        "Checkpoint carries EMA shadows for model_g.%s but this "
                        "model has no such submodule — skipping.",
                        name,
                    )
                    continue
                if name not in self.ema_extended:
                    self.ema_extended[name] = ExponentialMovingAverage(
                        module, decay=self.decay
                    )
                self.ema_extended[name].load_state_dict(state)

        # Mark that shadow params may be on CPU and need to be moved to GPU
        self._needs_device_sync = True
