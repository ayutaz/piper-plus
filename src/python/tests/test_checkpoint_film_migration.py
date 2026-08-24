"""Regression tests for the pre-FiLM decoder checkpoint migration (issue #616).

PR #579 widened `MBiSTFTGenerator.cond` from `upsample_initial_channel` to
`upsample_initial_channel * 2` outputs and added per-stage `cond_layers`, which
made every previously published or trained checkpoint unloadable:

    size mismatch for model_g.dec.cond.weight: copying a param with shape
    torch.Size([256, 512, 1]) ... the shape in current model is
    torch.Size([512, 512, 1])

`strict=False` does not help — it tolerates missing and unexpected keys, never
mismatched shapes.

The migration must be **exact**, not merely loadable. `_apply_film` computes
`x * (sigmoid(scale_raw) + 0.5) + shift`, so stacking zeros on top of the old
weights gives a gain of exactly 1.0 and reproduces the old `x + cond(g)`.
`test_migrated_decoder_output_is_bit_identical_to_additive_conditioning` is the
test that actually pins that claim; the shape assertions alone would pass for a
migration that silently changed the audio.
"""

from __future__ import annotations

import pytest


pytest.importorskip("torch", reason="torch required for checkpoint migration")

import torch  # noqa: E402
from torch import nn  # noqa: E402

from piper_train.vits.commons import (  # noqa: E402
    is_legacy_hifigan_checkpoint,
    migrate_prefilm_decoder_cond,
    migrate_prefilm_optimizer_states,
    normalize_checkpoint_state_dict,
    optimizer_states_need_migration,
)
from piper_train.vits.mb_istft import MBiSTFTGenerator  # noqa: E402


GIN_CHANNELS = 64
UPSAMPLE_INITIAL_CHANNEL = 32
INITIAL_CHANNEL = 16


def _make_generator() -> MBiSTFTGenerator:
    """A small MB-iSTFT generator with the current (FiLM) conditioning."""
    return MBiSTFTGenerator(
        initial_channel=INITIAL_CHANNEL,
        resblock="2",
        resblock_kernel_sizes=(3,),
        resblock_dilation_sizes=((1, 2),),
        upsample_rates=(4, 4),
        upsample_initial_channel=UPSAMPLE_INITIAL_CHANNEL,
        upsample_kernel_sizes=(16, 16),
        gin_channels=GIN_CHANNELS,
    )


def _prefilm_state_dict(generator: MBiSTFTGenerator) -> dict:
    """Take a current state_dict back to the pre-FiLM layout.

    Halves `cond` (keeping the *shift* half, which is what the old additive
    layer produced) and drops `cond_layers` entirely, exactly as a checkpoint
    written before PR #579 looks.
    """
    out = {}
    for key, value in generator.state_dict().items():
        if key.startswith("cond_layers."):
            continue
        if key in ("cond.weight", "cond.bias"):
            out[key] = value[value.shape[0] // 2 :].clone()
            continue
        out[key] = value.clone()
    return out


@pytest.mark.unit
class TestMigratePrefilmDecoderCond:
    def test_widens_cond_and_backfills_cond_layers(self) -> None:
        generator = _make_generator()
        model_sd = generator.state_dict()
        saved = _prefilm_state_dict(generator)

        migrated, n = migrate_prefilm_decoder_cond(saved, model_sd)

        assert n == 2, "expected cond.weight and cond.bias to migrate"
        assert migrated["cond.weight"].shape == model_sd["cond.weight"].shape
        assert migrated["cond.bias"].shape == model_sd["cond.bias"].shape
        for key in model_sd:
            if key.startswith("cond_layers."):
                assert key in migrated, f"cond_layers key not back-filled: {key}"

    def test_scale_half_is_zero_and_shift_half_is_preserved(self) -> None:
        """The zeros must land on the scale half, not the shift half.

        Swapping the two halves would still load and still produce the right
        shapes, but `sigmoid(w) + 0.5` of the old weights is not 1.0, so the
        decoder would be silently mis-conditioned.
        """
        generator = _make_generator()
        saved = _prefilm_state_dict(generator)
        original = saved["cond.weight"].clone()

        migrated, _ = migrate_prefilm_decoder_cond(saved, generator.state_dict())
        half = original.shape[0]

        assert torch.equal(migrated["cond.weight"][:half], torch.zeros_like(original))
        assert torch.equal(migrated["cond.weight"][half:], original)

    def test_backfilled_cond_layers_are_zero(self) -> None:
        generator = _make_generator()
        saved = _prefilm_state_dict(generator)

        migrated, _ = migrate_prefilm_decoder_cond(saved, generator.state_dict())

        for key, value in migrated.items():
            if key.startswith("cond_layers."):
                assert torch.count_nonzero(value) == 0, (
                    f"{key} must be zero so FiLM starts as the identity"
                )

    def test_is_idempotent(self) -> None:
        generator = _make_generator()
        model_sd = generator.state_dict()
        once, _ = migrate_prefilm_decoder_cond(_prefilm_state_dict(generator), model_sd)

        twice, n = migrate_prefilm_decoder_cond(once, model_sd)

        assert n == 0
        assert all(torch.equal(twice[k], once[k]) for k in once)

    def test_current_format_checkpoint_is_untouched(self) -> None:
        generator = _make_generator()
        model_sd = generator.state_dict()

        migrated, n = migrate_prefilm_decoder_cond(dict(model_sd), model_sd)

        assert n == 0
        assert all(torch.equal(migrated[k], model_sd[k]) for k in model_sd)

    def test_unrelated_half_width_tensors_are_not_migrated(self) -> None:
        """Only `dec.cond` may be widened, however suggestive other shapes are.

        A blanket "half the rows? double it" rule would corrupt any layer that
        legitimately changed size between versions.
        """
        generator = _make_generator()
        model_sd = generator.state_dict()
        saved = _prefilm_state_dict(generator)
        saved["conv_pre.bias"] = model_sd["conv_pre.bias"][
            : model_sd["conv_pre.bias"].shape[0] // 2
        ].clone()

        migrated, _ = migrate_prefilm_decoder_cond(saved, model_sd)

        assert migrated["conv_pre.bias"].shape != model_sd["conv_pre.bias"].shape

    def test_migrated_decoder_output_is_bit_identical_to_additive_conditioning(
        self,
    ) -> None:
        """The whole point: migrating must not change a single sample.

        Compares the migrated FiLM decoder against the same weights driven by
        the original `x = x + cond(g)` rule. `_apply_film` is patched to that
        rule rather than the forward pass being re-implemented here, so the
        reference cannot drift away from the real decoder.
        """
        torch.manual_seed(0)
        generator = _make_generator()
        saved = _prefilm_state_dict(generator)

        migrated_gen = _make_generator()
        migrated_sd, _ = migrate_prefilm_decoder_cond(saved, migrated_gen.state_dict())
        migrated_gen.load_state_dict(migrated_sd, strict=True)
        migrated_gen.eval()

        legacy_gen = _make_generator()
        legacy_gen.cond = nn.Conv1d(GIN_CHANNELS, UPSAMPLE_INITIAL_CHANNEL, 1)
        legacy_gen.load_state_dict(saved, strict=False)
        legacy_gen.eval()

        class _ZeroCond(nn.Module):
            def __init__(self, channels: int) -> None:
                super().__init__()
                self.channels = channels

            def forward(self, g: torch.Tensor) -> torch.Tensor:
                return torch.zeros(g.shape[0], self.channels, g.shape[2])

        legacy_gen.cond_layers = nn.ModuleList(
            [
                _ZeroCond(UPSAMPLE_INITIAL_CHANNEL // (2 ** (i + 1)))
                for i in range(legacy_gen.num_upsamples)
            ]
        )

        x = torch.randn(2, INITIAL_CHANNEL, 12)
        g = torch.randn(2, GIN_CHANNELS, 1)

        with torch.no_grad():
            migrated_out = migrated_gen(x, g)

        original_film = MBiSTFTGenerator.__dict__["_apply_film"]
        MBiSTFTGenerator._apply_film = staticmethod(
            lambda t, cond, free_scale=False: t + cond
        )
        try:
            with torch.no_grad():
                legacy_out = legacy_gen(x, g)
        finally:
            MBiSTFTGenerator._apply_film = original_film

        migrated_wave = (
            migrated_out[0] if isinstance(migrated_out, tuple) else migrated_out
        )
        legacy_wave = legacy_out[0] if isinstance(legacy_out, tuple) else legacy_out

        assert torch.equal(migrated_wave, legacy_wave), (
            "migrated decoder output differs from the additive-conditioning "
            f"reference (max abs diff "
            f"{(migrated_wave - legacy_wave).abs().max().item()})"
        )


@pytest.mark.unit
class TestNormalizeCheckpointStateDict:
    def test_strict_load_succeeds_after_normalisation(self) -> None:
        generator = _make_generator()
        saved = {
            f"model_g.dec.{k}": v for k, v in _prefilm_state_dict(generator).items()
        }
        model_sd = {f"model_g.dec.{k}": v for k, v in generator.state_dict().items()}
        # Marker key so the HiFi-GAN guard recognises this as MB-iSTFT.
        assert any("subband_conv_post" in k for k in saved)

        normalized, stats = normalize_checkpoint_state_dict(saved, model_sd)

        assert stats["cond_migrated"] == 2
        assert set(normalized) == set(model_sd)
        for key in model_sd:
            assert normalized[key].shape == model_sd[key].shape

    def test_migration_runs_after_orig_mod_strip(self) -> None:
        """`torch.compile` keys must be canonicalised before the reshape.

        The migration looks target shapes up by key, so a stale
        `_orig_mod` segment makes it silently skip and the load then fails
        with the original size mismatch — a regression that would be invisible
        without this ordering check.
        """
        generator = _make_generator()
        saved = {
            f"model_g.dec._orig_mod.{k}": v
            for k, v in _prefilm_state_dict(generator).items()
        }
        model_sd = {f"model_g.dec.{k}": v for k, v in generator.state_dict().items()}

        normalized, stats = normalize_checkpoint_state_dict(saved, model_sd)

        assert stats["stripped"] > 0
        assert stats["cond_migrated"] == 2, (
            "cond migration must run after _orig_mod stripping"
        )

    def test_hifigan_checkpoint_is_rejected_before_migration(self) -> None:
        """HiFi-GAN must still raise, not be silently "migrated".

        Its `Generator.cond` had the same `(upsample_initial_channel, gin, 1)`
        shape, so the shape rule alone cannot tell the two apart — only the
        absence of the MB-iSTFT marker keys can.
        """
        hifigan_sd = {
            "model_g.dec.conv_pre.weight": torch.zeros(32, 16, 7),
            "model_g.dec.cond.weight": torch.zeros(32, GIN_CHANNELS, 1),
            "model_g.dec.conv_post.weight": torch.zeros(1, 4, 7),
        }
        assert is_legacy_hifigan_checkpoint(hifigan_sd)

        with pytest.raises(RuntimeError, match="HiFi-GAN"):
            normalize_checkpoint_state_dict(hifigan_sd, dict(hifigan_sd))


@pytest.mark.unit
class TestOptimizerStateMigration:
    """`optimizer.load_state_dict` does not validate shapes.

    A pre-FiLM moment tensor loads happily into a widened parameter and only
    raises at the first `step()`, where `piper_train`'s resume fallback catches
    it and restarts from epoch 0. That silent loss of progress is what these
    tests guard.
    """

    @staticmethod
    def _checkpoint(moment_shape: tuple[int, ...]) -> dict:
        return {
            "optimizer_states": [
                {
                    "state": {
                        0: {
                            "exp_avg": torch.zeros(*moment_shape),
                            "exp_avg_sq": torch.zeros(*moment_shape),
                        }
                    },
                    "param_groups": [{"params": [0]}],
                }
            ]
        }

    def test_detects_prefilm_optimizer_state(self) -> None:
        model_sd = {"model_g.dec.cond.weight": torch.zeros(64, GIN_CHANNELS, 1)}
        checkpoint = self._checkpoint((32, GIN_CHANNELS, 1))

        assert optimizer_states_need_migration(checkpoint, model_sd) is True

    def test_current_format_needs_no_migration(self) -> None:
        model_sd = {"model_g.dec.cond.weight": torch.zeros(64, GIN_CHANNELS, 1)}
        checkpoint = self._checkpoint((64, GIN_CHANNELS, 1))

        assert optimizer_states_need_migration(checkpoint, model_sd) is False

    def test_widens_moments_when_mapping_validates(self) -> None:
        param = torch.zeros(64, GIN_CHANNELS, 1)
        checkpoint = self._checkpoint((32, GIN_CHANNELS, 1))

        widened = migrate_prefilm_optimizer_states(
            checkpoint, [("model_g.dec.cond.weight", param)]
        )

        assert widened == 2
        state = checkpoint["optimizer_states"][0]["state"][0]
        assert state["exp_avg"].shape == param.shape
        assert state["exp_avg_sq"].shape == param.shape

    def test_refuses_to_widen_when_mapping_is_inconsistent(self) -> None:
        """An unexplained shape means the index->parameter mapping is wrong.

        Widening on a bad mapping would write moments onto the wrong tensors —
        corruption that no later check would notice. Returning 0 lets the
        caller drop the optimizer state loudly instead.
        """
        checkpoint = self._checkpoint((32, GIN_CHANNELS, 1))
        mismatched = torch.zeros(7, 3, 1)

        widened = migrate_prefilm_optimizer_states(
            checkpoint, [("model_g.enc_p.emb.weight", mismatched)]
        )

        assert widened == 0
        assert checkpoint["optimizer_states"][0]["state"][0]["exp_avg"].shape == (
            32,
            GIN_CHANNELS,
            1,
        )
