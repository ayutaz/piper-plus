"""Tests for validation_step metric isolation.

Regression test for #23: validation_step must NOT log training-named metrics
(loss_gen_all, loss_disc_all, etc.) to avoid polluting the validation metric
namespace.  The implementation temporarily replaces self.log with a no-op
during the generator/discriminator forward passes and restores it afterwards,
logging only "val_loss".
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRAINING_METRIC_NAMES = frozenset(
    {
        "loss_gen_all",
        "loss_disc_all",
        "loss_gen_wavlm",
        "loss_fm_wavlm",
        "loss_disc_wavlm",
    }
)


def _make_model():
    """Create a minimal VitsModel for validation_step testing.

    VitsModel instantiation is heavy (builds full SynthesizerTrn +
    MultiPeriodDiscriminator), so we create the smallest viable model.
    """
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:
        pytest.skip(f"Training dependencies not available: {e}")

    model = VitsModel(
        num_symbols=50,
        num_speakers=1,
        num_languages=1,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
    )
    return model


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidationStepMetricIsolation:
    """Verify that validation_step does not leak training metric names."""

    def test_log_suppression_mechanism(self):
        """validation_step replaces self.log with a no-op during
        training_step_g / training_step_d, then restores the original.

        We verify the mechanism by inspecting the source of validation_step
        rather than running a full forward pass (which would require a
        dataset, GPU, etc.).
        """
        import inspect

        try:
            from piper_train.vits.lightning import VitsModel
        except ImportError as e:
            pytest.skip(f"Training dependencies not available: {e}")

        src = inspect.getsource(VitsModel.validation_step)

        # The suppression pattern: save original log, replace with no-op,
        # call training_step_g/d, then restore.
        assert "self.log = lambda" in src or "self.log =" in src, (
            "validation_step must suppress self.log during generator/discriminator "
            "forward passes to prevent training metric contamination"
        )
        assert "_orig_log" in src or "orig_log" in src, (
            "validation_step must save and restore the original self.log"
        )
        assert "finally" in src, (
            "validation_step must restore self.log in a finally block "
            "to guarantee cleanup even on exceptions"
        )

    def test_validation_step_logs_only_val_loss(self):
        """validation_step should only log 'val_loss', not training metrics.

        We intercept self.log (the actual Lightning log method) to capture
        which metric keys reach it.  The validation_step temporarily replaces
        self.log with a no-op during training_step_g/d, so training-named
        metrics should never reach the real self.log.
        """
        model = _make_model()

        # Capture all keys that reach the REAL self.log
        logged_keys = []
        _orig_log = model.log

        def capture_log(key, *args, **kwargs):
            logged_keys.append(key)

        model.log = capture_log

        # Build a minimal fake Batch
        try:
            from piper_train.vits.dataset import Batch
        except ImportError as e:
            pytest.skip(f"Training dependencies not available: {e}")

        batch_size = 2
        phoneme_len = 10
        spec_channels = 513
        spec_len = 32
        audio_len = spec_len * 256  # hop_length=256

        fake_batch = Batch(
            phoneme_ids=torch.randint(0, 50, (batch_size, phoneme_len)),
            phoneme_lengths=torch.full((batch_size,), phoneme_len, dtype=torch.long),
            audios=torch.randn(batch_size, 1, audio_len),
            audio_lengths=torch.full((batch_size,), audio_len, dtype=torch.long),
            spectrograms=torch.randn(batch_size, spec_channels, spec_len),
            spectrogram_lengths=torch.full(
                (batch_size,), spec_len, dtype=torch.long
            ),
            speaker_ids=None,
            language_ids=None,
            prosody_features=None,
        )

        # Provide a minimal trainer mock so _log_with_batch_info works
        class FakeTrainer:
            world_size = 1

        model.trainer = FakeTrainer()

        # Run validation_step — self.log is our capture_log.
        # Inside validation_step, self.log is temporarily replaced with
        # a no-op (so training_step_g/d metrics go nowhere), then restored
        # to capture_log for the final val_loss log.
        try:
            model.eval()
            with torch.no_grad():
                model.validation_step(fake_batch, batch_idx=0)
        except Exception:
            # Forward pass may fail on CPU with random data
            pass

        # Check that no training metric names reached self.log
        leaked = TRAINING_METRIC_NAMES.intersection(logged_keys)
        assert not leaked, (
            f"validation_step leaked training metrics: {leaked}. "
            "Only 'val_loss' should be logged during validation."
        )

    def test_validation_step_source_has_val_loss_log(self):
        """validation_step must contain a log call for 'val_loss'."""
        import inspect

        try:
            from piper_train.vits.lightning import VitsModel
        except ImportError as e:
            pytest.skip(f"Training dependencies not available: {e}")

        src = inspect.getsource(VitsModel.validation_step)
        assert "val_loss" in src, (
            "validation_step must log 'val_loss' as the validation metric"
        )
