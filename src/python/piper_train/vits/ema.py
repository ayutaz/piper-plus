import torch
from pytorch_lightning.callbacks import Callback
from torch import nn


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
    """PyTorch Lightning callback for EMA during training."""

    def __init__(
        self,
        decay: float = 0.999,
        apply_ema_every_n_steps: int = 1,
        start_step: int = 0,
        save_ema_weights_in_callback_state: bool = True,
    ):
        self.decay = decay
        self.apply_ema_every_n_steps = apply_ema_every_n_steps
        self.start_step = start_step
        self.save_ema_weights_in_callback_state = save_ema_weights_in_callback_state

        self.ema_generator = None
        self.ema_spk_proj = None
        self.ema_discriminator = None
        self._needs_device_sync = False

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

    def on_train_batch_end(self, trainer, model, outputs, batch, batch_idx):
        """Update EMA after each training step."""
        # Bug 1 fix: sync shadow params to correct device after checkpoint resume
        if self._needs_device_sync:
            device = next(model.parameters()).device
            if self.ema_generator is not None:
                self.ema_generator.to(device)
            if self.ema_spk_proj is not None:
                self.ema_spk_proj.to(device)
            if self.ema_discriminator is not None:
                self.ema_discriminator.to(device)
            self._needs_device_sync = False

        step = trainer.global_step

        if step >= self.start_step and step % self.apply_ema_every_n_steps == 0:
            if self.ema_generator is not None:
                self.ema_generator.update()
            if self.ema_spk_proj is not None:
                self.ema_spk_proj.update()
            if self.ema_discriminator is not None:
                self.ema_discriminator.update()

    def on_validation_epoch_start(self, trainer, model):
        """Apply EMA weights for validation."""
        if self.ema_generator is not None:
            self.ema_generator.apply_shadow()
        if self.ema_spk_proj is not None:
            self.ema_spk_proj.apply_shadow()
        if self.ema_discriminator is not None:
            self.ema_discriminator.apply_shadow()

    def on_validation_epoch_end(self, trainer, model):
        """Restore original weights after validation."""
        if self.ema_generator is not None:
            self.ema_generator.restore()
        if self.ema_spk_proj is not None:
            self.ema_spk_proj.restore()
        if self.ema_discriminator is not None:
            self.ema_discriminator.restore()

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

    def on_load_checkpoint(self, trainer, model, checkpoint):
        """Load EMA state from checkpoint."""
        if checkpoint.get("ema_generator_state"):
            if self.ema_generator is None:
                self.ema_generator = ExponentialMovingAverage(
                    model.model_g.dec, decay=self.decay
                )
            self.ema_generator.load_state_dict(checkpoint["ema_generator_state"])

        if checkpoint.get("ema_spk_proj_state"):
            if self.ema_spk_proj is None and hasattr(model.model_g, "spk_proj"):
                self.ema_spk_proj = ExponentialMovingAverage(
                    model.model_g.spk_proj, decay=self.decay
                )
            if self.ema_spk_proj is not None:
                self.ema_spk_proj.load_state_dict(checkpoint["ema_spk_proj_state"])

        if (
            checkpoint.get("ema_discriminator_state")
        ):
            if self.ema_discriminator is None:
                self.ema_discriminator = ExponentialMovingAverage(
                    model.model_d, decay=self.decay
                )
            self.ema_discriminator.load_state_dict(
                checkpoint["ema_discriminator_state"]
            )

        # Mark that shadow params may be on CPU and need to be moved to GPU
        self._needs_device_sync = True
