"""帯域分割 MRD を全体の学習 (``VitsModel``) に入れる配線のテスト。

P1 (docs/design/zero-shot-decoder-p1-design-2026-10-29.md) では帯域分割 MRD を
decoder だけの学習 (``tools/train_decoder_only.py``) で使い、D0 が合格した。
P2 (plan §6、2026-10-30 改定) の K1 は from scratch の全体の学習でこれを使う
ので、``--use-band-split-mrd`` (既定 off) で ``VitsModel`` に足す。

配線の漏れ (識別器は作ったが G/D の損失に入っていない、D の optimizer や
勾配クリップに入っていない) は単体テストでは見えないため、実 batch で
``training_step_g`` / ``training_step_d`` を回して確かめる。
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch", reason="torch required")
pytest.importorskip("pytorch_lightning")

from torch.nn import functional as F  # noqa: E402


B, T_TEXT, T_FRAMES = 2, 20, 48
HOP = 256
BMRD_KEYS = ("loss_gen_bmrd", "loss_fm_bmrd", "loss_disc_bmrd")


def _vits_model(**overrides):
    try:
        from piper_train.vits.lightning import VitsModel
    except ImportError as e:  # pragma: no cover
        pytest.skip(f"Training dependencies not available: {e}")
    kwargs = {
        "num_symbols": 97,
        "num_speakers": 4,
        "num_languages": 2,
        "dataset": None,
        "batch_size": B,
        "learning_rate": 2e-5,
        "use_wavlm_discriminator": False,
        "upsample_rates": (4, 4),
        "upsample_kernel_sizes": (16, 16),
        "segment_size": 8192,
    }
    kwargs.update(overrides)
    torch.manual_seed(0)
    return VitsModel(**kwargs)


def _batch():
    from piper_train.vits.dataset import Batch

    torch.manual_seed(1)
    return Batch(
        phoneme_ids=torch.randint(1, 97, (B, T_TEXT)),
        phoneme_lengths=torch.full((B,), T_TEXT),
        spectrograms=torch.randn(B, 513, T_FRAMES).abs(),
        spectrogram_lengths=torch.full((B,), T_FRAMES),
        audios=torch.randn(B, 1, T_FRAMES * HOP) * 0.1,
        audio_lengths=torch.full((B,), T_FRAMES * HOP),
        speaker_ids=torch.tensor([0, 1]),
        language_ids=torch.tensor([0, 0]),
        prosody_features=torch.zeros(B, T_TEXT, 3, dtype=torch.long),
        speaker_embeddings=F.normalize(torch.randn(B, 192), dim=-1),
    )


def _capture_logs(model):
    logged: dict[str, float] = {}

    def _stub(key, value, batch=None, batch_size=None):
        logged[key] = float(value.detach()) if torch.is_tensor(value) else float(value)

    model._log_with_batch_info = _stub
    return logged


def _steps(model):
    model.train()
    logged = _capture_logs(model)
    batch = _batch()
    torch.manual_seed(2)
    loss_g = model.training_step_g(batch)
    loss_d = model.training_step_d(batch)
    return loss_g, loss_d, logged


def _parse_train_args(extra=()):
    from piper_train.__main__ import create_parser

    parser = create_parser()
    return parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1", *extra])


@pytest.mark.unit
class TestBandSplitMrdWiring:
    def test_off_by_default(self):
        model = _vits_model(use_mrd=True)
        assert model.model_d_bmrd is None
        _, _, logged = _steps(model)
        assert not set(BMRD_KEYS) & set(logged)

    def test_enabled_builds_the_p1_discriminator(self):
        from piper_train.vits.band_split_discriminator import (
            BandSplitSpectrogramDiscriminator,
        )

        model = _vits_model(use_mrd=True, use_band_split_mrd=True)
        assert isinstance(model.model_d_bmrd, BandSplitSpectrogramDiscriminator)
        # P1 の D0 と同じ解像度 (train_decoder_only.TrainConfig.band_disc_ffts)
        assert [d.n_fft for d in model.model_d_bmrd.discriminators] == [2048, 1024, 512]

    def test_generator_and_discriminator_steps_use_it(self):
        model = _vits_model(use_mrd=True, use_band_split_mrd=True)
        loss_g, loss_d, logged = _steps(model)
        assert torch.isfinite(loss_g)
        assert torch.isfinite(loss_d)
        for key in BMRD_KEYS:
            assert key in logged, f"{key} が training_step から記録されていない"

    def test_weight_scales_the_generator_term(self):
        """G の損失に ``c_band_split_mrd × (adv + fm)`` だけ入る。"""
        losses = {}
        for c in (1.0, 3.0):
            model = _vits_model(
                use_mrd=True, use_band_split_mrd=True, c_band_split_mrd=c
            )
            model.train()
            logged = _capture_logs(model)
            torch.manual_seed(2)
            losses[c] = (float(model.training_step_g(_batch()).detach()), logged)
        (g1, log1), (g3, _) = losses[1.0], losses[3.0]
        term = log1["loss_gen_bmrd"] + log1["loss_fm_bmrd"]
        assert g3 - g1 == pytest.approx(2.0 * term, rel=1e-4, abs=1e-4)

    def test_discriminator_weight_scales_the_discriminator_term(self):
        totals = {}
        for c in (1.0, 3.0):
            model = _vits_model(
                use_mrd=True, use_band_split_mrd=True, c_band_split_mrd=c
            )
            _, loss_d, logged = _steps(model)
            totals[c] = (float(loss_d.detach()), logged["loss_disc_bmrd"])
        (d1, term), (d3, _) = totals[1.0], totals[3.0]
        assert d3 - d1 == pytest.approx(2.0 * term, rel=1e-4, abs=1e-4)

    def test_discriminator_parameters_include_it(self):
        model = _vits_model(use_mrd=True, use_band_split_mrd=True)
        ids = {id(p) for p in model.discriminator_parameters()}
        assert all(id(p) in ids for p in model.model_d_bmrd.parameters())
        assert all(id(p) in ids for p in model.model_d_mrd.parameters())

    def test_discriminator_optimizer_updates_it(self):
        model = _vits_model(use_mrd=True, use_band_split_mrd=True)
        optimizers, _ = model.configure_optimizers()
        opt_d = optimizers[1]
        ids = {id(p) for group in opt_d.param_groups for p in group["params"]}
        assert all(id(p) in ids for p in model.model_d_bmrd.parameters())

    def test_generator_optimizer_does_not_update_it(self):
        model = _vits_model(use_mrd=True, use_band_split_mrd=True)
        optimizers, _ = model.configure_optimizers()
        ids = {id(p) for group in optimizers[0].param_groups for p in group["params"]}
        assert not any(id(p) in ids for p in model.model_d_bmrd.parameters())


@pytest.mark.unit
class TestBandSplitMrdCli:
    def test_default_off(self):
        args = _parse_train_args()
        assert args.use_band_split_mrd is False
        assert args.c_band_split_mrd == 1.0

    def test_flags(self):
        args = _parse_train_args(
            ("--use-band-split-mrd", "--c-band-split-mrd", "0.5")
        )
        assert args.use_band_split_mrd is True
        assert args.c_band_split_mrd == 0.5
