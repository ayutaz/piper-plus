"""Tests for VITS2 adversarial Duration Predictor (--vits2 flag).

Verifies:
- DurationDiscriminator forward pass shapes
- VITS2 training step smoke test (generator + discriminator + dur_disc)
- VITS1 checkpoint loading into VITS2 model (strict=False)
- freeze-dp also freezes dur_disc
- VITS1 backward compatibility (vits2=False default)
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


class TestDurationDiscriminator:
    """Unit tests for the DurationDiscriminator module."""

    @pytest.mark.unit
    def test_forward_shape(self):
        """DurationDiscriminator forward produces correct output shapes."""
        from piper_train.vits.models import DurationDiscriminator

        batch, hidden, time = 2, 192, 20
        dur_disc = DurationDiscriminator(hidden_channels=hidden)

        x = torch.randn(batch, hidden, time)
        x_mask = torch.ones(batch, 1, time)
        dur_r = torch.randn(batch, 1, time)
        dur_g = torch.randn(batch, 1, time)

        disc_real, disc_fake = dur_disc(x, x_mask, dur_r, dur_g)

        assert disc_real.shape == (batch, 1, time)
        assert disc_fake.shape == (batch, 1, time)

    @pytest.mark.unit
    def test_forward_masked(self):
        """Masked positions produce zero output."""
        from piper_train.vits.models import DurationDiscriminator

        batch, hidden, time = 1, 192, 10
        dur_disc = DurationDiscriminator(hidden_channels=hidden)

        x = torch.randn(batch, hidden, time)
        # Mask out last 5 positions
        x_mask = torch.ones(batch, 1, time)
        x_mask[:, :, 5:] = 0.0
        dur_r = torch.randn(batch, 1, time)
        dur_g = torch.randn(batch, 1, time)

        disc_real, disc_fake = dur_disc(x, x_mask, dur_r, dur_g)

        # Masked positions should be zero
        assert (disc_real[:, :, 5:] == 0.0).all()
        assert (disc_fake[:, :, 5:] == 0.0).all()

    @pytest.mark.unit
    def test_forward_with_prosody_dim(self):
        """DurationDiscriminator works with prosody-augmented hidden channels."""
        from piper_train.vits.models import DurationDiscriminator

        # With prosody_dim=16, dp_in_channels = 192 + 16 = 208
        dp_in_channels = 208
        batch, time = 2, 15
        dur_disc = DurationDiscriminator(hidden_channels=dp_in_channels)

        x = torch.randn(batch, dp_in_channels, time)
        x_mask = torch.ones(batch, 1, time)
        dur_r = torch.randn(batch, 1, time)
        dur_g = torch.randn(batch, 1, time)

        disc_real, disc_fake = dur_disc(x, x_mask, dur_r, dur_g)
        assert disc_real.shape == (batch, 1, time)
        assert disc_fake.shape == (batch, 1, time)

    @pytest.mark.unit
    def test_gradients_flow(self):
        """Gradients flow through DurationDiscriminator."""
        from piper_train.vits.models import DurationDiscriminator

        dur_disc = DurationDiscriminator(hidden_channels=192)
        x = torch.randn(1, 192, 10)
        x_mask = torch.ones(1, 1, 10)
        dur_r = torch.randn(1, 1, 10, requires_grad=True)
        dur_g = torch.randn(1, 1, 10, requires_grad=True)

        disc_real, disc_fake = dur_disc(x, x_mask, dur_r, dur_g)
        loss = disc_real.mean() + disc_fake.mean()
        loss.backward()

        # Check that dur_disc parameters received gradients
        for name, p in dur_disc.named_parameters():
            assert p.grad is not None, f"No gradient for {name}"


class TestVits2Model:
    """Integration tests for VITS2 mode in VitsModel."""

    @pytest.mark.unit
    def test_when_vits2_disabled_model_has_no_duration_discriminator(self, make_vits_model):
        """vits2 defaults to False."""
        model = make_vits_model(vits2=False)
        assert model.hparams.vits2 is False
        assert model.model_g.dur_disc is None

    @pytest.mark.unit
    def test_when_vits2_enabled_model_has_duration_discriminator(self, make_vits_model):
        """vits2=True creates DurationDiscriminator on model_g."""
        model = make_vits_model(vits2=True)
        assert model.hparams.vits2 is True
        assert model.model_g.dur_disc is not None
        assert model.model_g.vits2 is True

    @pytest.mark.unit
    def test_when_vits2_enabled_creates_three_optimizers(self, make_vits_model):
        """VITS2 creates 3 optimizers (gen, disc, dur_disc)."""
        model = make_vits_model(vits2=True)
        optimizers, schedulers = model.configure_optimizers()
        assert len(optimizers) == 3, "VITS2 should have 3 optimizers"
        assert len(schedulers) == 3, "VITS2 should have 3 schedulers"

    @pytest.mark.unit
    def test_when_vits1_creates_two_optimizers(self, make_vits_model):
        """VITS1 (default) creates 2 optimizers."""
        model = make_vits_model(vits2=False)
        optimizers, schedulers = model.configure_optimizers()
        assert len(optimizers) == 2, "VITS1 should have 2 optimizers"
        assert len(schedulers) == 2, "VITS1 should have 2 schedulers"

    @pytest.mark.unit
    def test_when_vits2_dur_disc_excluded_from_generator_optimizer(self, make_vits_model):
        """dur_disc parameters are NOT in the generator optimizer."""
        model = make_vits_model(vits2=True)
        optimizers, _ = model.configure_optimizers()
        opt_g = optimizers[0]

        dur_disc_param_ids = {
            id(p) for p in model.model_g.dur_disc.parameters()
        }

        for group in opt_g.param_groups:
            for param in group["params"]:
                assert id(param) not in dur_disc_param_ids, (
                    "Generator optimizer should not contain dur_disc parameters"
                )

    @pytest.mark.unit
    def test_when_vits2_dur_disc_in_third_optimizer(self, make_vits_model):
        """dur_disc parameters are in the 3rd optimizer."""
        model = make_vits_model(vits2=True)
        optimizers, _ = model.configure_optimizers()
        opt_dur = optimizers[2]

        dur_disc_param_ids = {
            id(p) for p in model.model_g.dur_disc.parameters()
        }

        opt_param_ids = set()
        for group in opt_dur.param_groups:
            for param in group["params"]:
                opt_param_ids.add(id(param))

        assert dur_disc_param_ids == opt_param_ids, (
            "3rd optimizer should contain exactly the dur_disc parameters"
        )


class TestVits2FreezeDp:
    """Tests for freeze-dp interaction with VITS2."""

    @pytest.mark.unit
    def test_when_freeze_dp_then_dur_disc_is_frozen(self, make_vits_model):
        """--freeze-dp also freezes DurationDiscriminator in VITS2 mode."""
        model = make_vits_model(vits2=True, freeze_dp=True)
        model.configure_optimizers()

        for name, param in model.model_g.dur_disc.named_parameters():
            assert not param.requires_grad, (
                f"dur_disc param {name} should be frozen when freeze_dp=True"
            )

    @pytest.mark.unit
    def test_when_freeze_dp_still_has_three_optimizers(self, make_vits_model):
        """When freeze-dp, VITS2 still has 3 optimizers (3rd is dummy)."""
        model = make_vits_model(vits2=True, freeze_dp=True)
        optimizers, schedulers = model.configure_optimizers()
        assert len(optimizers) == 3
        assert len(schedulers) == 3

    @pytest.mark.unit
    def test_when_no_freeze_dp_then_dur_disc_is_trainable(self, make_vits_model):
        """Without freeze-dp, dur_disc params are trainable."""
        model = make_vits_model(vits2=True, freeze_dp=False)
        model.configure_optimizers()

        for name, param in model.model_g.dur_disc.named_parameters():
            assert param.requires_grad, (
                f"dur_disc param {name} should be trainable when freeze_dp=False"
            )


class TestVits1Compatibility:
    """Ensure VITS1 path is untouched when vits2=False."""

    @pytest.mark.unit
    def test_when_vits1_forward_returns_none_dur_info(self, make_vits_model):
        """SynthesizerTrn.forward returns dur_info=None when vits2=False."""
        model = make_vits_model(vits2=False)
        model_g = model.model_g

        # Create minimal inputs
        batch_size = 1
        text_len = 10
        spec_len = 50
        x = torch.randint(0, 97, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.LongTensor([spec_len])

        with torch.no_grad():
            result = model_g(x, x_lengths, spec, spec_lengths)

        # Result should have 8 elements with dur_info as the last one
        assert len(result) == 8, f"Expected 8 return values, got {len(result)}"
        dur_info = result[7]
        assert dur_info is None, "dur_info should be None when vits2=False"

    @pytest.mark.unit
    def test_when_vits2_forward_returns_dur_info_tuple(self, make_vits_model):
        """SynthesizerTrn.forward returns dur_info tuple when vits2=True (use_sdp=False)."""
        model = make_vits_model(vits2=True)
        model_g = model.model_g

        batch_size = 1
        text_len = 10
        spec_len = 50
        x = torch.randint(0, 97, (batch_size, text_len))
        x_lengths = torch.LongTensor([text_len])
        spec = torch.randn(batch_size, 513, spec_len)
        spec_lengths = torch.LongTensor([spec_len])

        with torch.no_grad():
            result = model_g(x, x_lengths, spec, spec_lengths)

        assert len(result) == 8
        dur_info = result[7]
        assert dur_info is not None, "dur_info should be a tuple when vits2=True"
        assert len(dur_info) == 4, "dur_info should be (x_dp_det, x_mask, logw_r, logw_g)"

    @pytest.mark.unit
    def test_when_loading_vits1_checkpoint_into_vits2(self, make_vits_model):
        """A VITS1 state dict can be loaded into a VITS2 model with strict=False."""
        model_v1 = make_vits_model(vits2=False)
        state_dict_v1 = model_v1.state_dict()

        model_v2 = make_vits_model(vits2=True)
        missing, unexpected = model_v2.load_state_dict(state_dict_v1, strict=False)

        # dur_disc keys should be in "missing" since VITS1 doesn't have them
        dur_disc_missing = [k for k in missing if "dur_disc" in k]
        assert len(dur_disc_missing) > 0, (
            "dur_disc keys should be missing when loading VITS1 into VITS2"
        )

        # No unexpected keys (VITS1 is a subset of VITS2)
        assert len(unexpected) == 0, (
            f"Should have no unexpected keys, got: {unexpected}"
        )

    @pytest.mark.unit
    def test_infer_works_regardless_of_vits2_flag(self, make_vits_model):
        """infer() method works identically regardless of vits2 flag."""
        # Both models should be able to run inference
        for vits2_flag in [False, True]:
            model = make_vits_model(vits2=vits2_flag)
            model_g = model.model_g
            model_g.eval()

            x = torch.randint(0, 97, (1, 10))
            x_lengths = torch.LongTensor([10])

            with torch.no_grad():
                o, attn, y_mask, _ = model_g.infer(x, x_lengths)

            assert o.dim() == 3, f"Output should be 3D, got {o.dim()}"
            assert o.shape[0] == 1, "Batch size should be 1"
