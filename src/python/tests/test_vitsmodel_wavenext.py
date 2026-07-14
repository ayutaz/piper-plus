"""Tests for VitsModel WaveNeXt decoder integration (Stage 1).

Verifies the decoder-arch gating added in lightning.py:

- ``decoder_arch='wavenext'`` skips PQMF / sub-band STFT loss and
  instantiates the fullband MultiResolutionDiscriminator (MRD)
- the pqmf-injection gate is a correctness requirement: WaveNeXt
  checkpoints must contain no ``model_g.dec.pqmf.*`` keys so the
  tri-state classifier keeps returning ``wavenext``
  (docs/design/wavenext-decoder-ablation/04-pre-stage0-verification.md §3-7)
- ``decoder_arch='mb_istft'`` (default) keeps the original PQMF sharing
  and gets no MRD (regression guard)
- MRD parameters go into the D optimizer only
- MRD forward keeps the MultiPeriodDiscriminator return contract so
  losses.py LSGAN helpers apply unchanged
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_vitsmodel(**overrides):
    """Create a minimal VitsModel; default overrides select WaveNeXt."""
    from piper_train.vits.lightning import VitsModel

    kwargs = {
        "num_symbols": 97,
        "num_speakers": 1,
        "num_languages": 2,
        "dataset": None,
        "batch_size": 4,
        "learning_rate": 2e-4,
        "use_wavlm_discriminator": False,
        "decoder_arch": "wavenext",
    }
    kwargs.update(overrides)
    return VitsModel(**kwargs)


@pytest.mark.unit
def test_wavenext_skips_pqmf_and_substft_instantiates_mrd():
    """WaveNeXt: no PQMF / sub-band loss; MRD is created; fullband STFT off."""
    model = _make_vitsmodel()
    assert model.pqmf is None
    assert model.sub_stft_loss is None
    assert model.model_mrd is not None
    # c_mrstft defaults to 0.0 → fullband MR-STFT loss disabled
    assert model.fullband_stft_loss is None


@pytest.mark.unit
def test_wavenext_state_dict_has_no_pqmf_keys():
    """Correctness requirement: pqmf buffers must not contaminate the ckpt.

    lightning.py の PQMF 注入 gate が外れると model_g.dec.pqmf.* が混入し、
    tri-state 分類器 (mb_istft マーカー優先) が誤分類する。
    """
    from piper_train.__main__ import _detect_decoder_arch

    model = _make_vitsmodel()
    state_dict = model.state_dict()
    assert not any(k.startswith("model_g.dec.pqmf.") for k in state_dict)
    assert any(k.startswith("model_g.dec.convnext.") for k in state_dict)

    # Round-trip through the checkpoint-level detector (tag + markers agree)
    checkpoint = {
        "state_dict": state_dict,
        "hyper_parameters": dict(model.hparams),
    }
    assert _detect_decoder_arch(checkpoint) == "wavenext"


@pytest.mark.unit
def test_mb_istft_default_keeps_pqmf_sharing_and_no_mrd():
    """Regression: default mb_istft path is unchanged by the gating."""
    model = _make_vitsmodel(
        decoder_arch="mb_istft",
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
    )
    assert model.pqmf is not None
    assert model.model_g.dec.pqmf is model.pqmf  # shared instance
    assert model.sub_stft_loss is not None
    assert model.model_mrd is None
    assert model.fullband_stft_loss is None


@pytest.mark.unit
def test_c_mrstft_enables_fullband_stft_loss():
    """c_mrstft > 0 instantiates the fullband MultiResolutionSTFTLoss."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    model = _make_vitsmodel(c_mrstft=1.0)
    assert isinstance(model.fullband_stft_loss, MultiResolutionSTFTLoss)


@pytest.mark.unit
def test_hop_length_guard():
    """hop_length != 256 with wavenext raises (hop != 256 is Stage 3 scope)."""
    with pytest.raises(ValueError, match="256") as excinfo:
        _make_vitsmodel(hop_length=512)
    assert "Stage 3" in str(excinfo.value)


@pytest.mark.unit
def test_configure_optimizers_puts_mrd_in_d_optimizer_only():
    """MRD parameters belong to opt_d and never to opt_g."""
    model = _make_vitsmodel()
    optimizers, _schedulers = model.configure_optimizers()
    opt_g, opt_d = optimizers

    g_ids = {id(p) for group in opt_g.param_groups for p in group["params"]}
    d_ids = {id(p) for group in opt_d.param_groups for p in group["params"]}
    mrd_ids = {id(p) for p in model.model_mrd.parameters()}

    assert mrd_ids, "MRD has no parameters"
    assert mrd_ids <= d_ids, "MRD parameters missing from the D optimizer"
    assert not (mrd_ids & g_ids), "MRD parameters leaked into the G optimizer"


@pytest.mark.unit
def test_wavenext_hparams_persisted():
    """WaveNeXt hparams survive save_hyperparameters (hparams.yaml 永続化)."""
    model = _make_vitsmodel()
    assert model.hparams.c_mrd == 0.1
    assert model.hparams.c_mrstft == 0.0
    assert model.hparams.pretrain_mel_steps == 0
    assert model.hparams.wavenext_dim == 512
    assert model.hparams.wavenext_intermediate_dim == 1536
    assert model.hparams.wavenext_num_blocks == 8
    assert model.hparams.decoder_arch == "wavenext"


# ---------------------------------------------------------------------------
# MultiResolutionDiscriminator (wavenext_losses.py) unit contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMultiResolutionDiscriminator:
    def test_forward_matches_mpd_return_contract(self):
        """(y_d_rs, y_d_gs, fmap_rs, fmap_gs), one entry per resolution."""
        from piper_train.vits.wavenext_losses import MultiResolutionDiscriminator

        torch.manual_seed(1234)
        mrd = MultiResolutionDiscriminator()
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192)

        y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(y, y_hat)
        assert len(y_d_rs) == 3  # fft_sizes (2048, 1024, 512)
        assert len(y_d_gs) == 3
        assert len(fmap_rs) == 3
        assert len(fmap_gs) == 3
        for fmap in (*fmap_rs, *fmap_gs):
            assert isinstance(fmap, list)
            assert len(fmap) > 0

    def test_lsgan_losses_apply_unchanged(self):
        """losses.py LSGAN helpers consume the MRD outputs and stay finite."""
        from piper_train.vits.losses import (
            discriminator_loss,
            feature_loss,
            generator_loss,
        )
        from piper_train.vits.wavenext_losses import MultiResolutionDiscriminator

        torch.manual_seed(1234)
        mrd = MultiResolutionDiscriminator()
        y = torch.randn(2, 1, 8192)
        y_hat = torch.randn(2, 1, 8192)
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(y, y_hat)

        loss_disc, r_losses, g_losses = discriminator_loss(y_d_rs, y_d_gs)
        loss_gen, _gen_losses = generator_loss(y_d_gs)
        loss_fm = feature_loss(fmap_rs, fmap_gs)

        assert len(r_losses) == len(g_losses) == 3
        for loss in (loss_disc, loss_gen, loss_fm):
            assert loss.dim() == 0
            assert torch.isfinite(loss)

    def test_bf16_input_is_cast_to_float32(self):
        """bf16-mixed 下でも spectrogram 内の float32 cast で成功する。"""
        from piper_train.vits.wavenext_losses import MultiResolutionDiscriminator

        torch.manual_seed(1234)
        mrd = MultiResolutionDiscriminator()
        y = torch.randn(2, 1, 8192, dtype=torch.bfloat16)
        y_hat = torch.randn(2, 1, 8192, dtype=torch.bfloat16)

        y_d_rs, _y_d_gs, _fmap_rs, _fmap_gs = mrd(y, y_hat)
        assert all(torch.isfinite(out).all() for out in y_d_rs)

    def test_gradient_flows_to_generator_input(self):
        """G-side MRD loss backpropagates into y_hat (generator output)."""
        from piper_train.vits.losses import feature_loss, generator_loss
        from piper_train.vits.wavenext_losses import MultiResolutionDiscriminator

        torch.manual_seed(1234)
        mrd = MultiResolutionDiscriminator(fft_sizes=(512,))
        y = torch.randn(1, 1, 4096)
        y_hat = torch.randn(1, 1, 4096, requires_grad=True)

        _y_d_rs, y_d_gs, fmap_rs, fmap_gs = mrd(y, y_hat)
        loss_gen, _ = generator_loss(y_d_gs)
        loss_fm = feature_loss(fmap_rs, fmap_gs)
        (loss_gen + loss_fm).backward()

        assert y_hat.grad is not None
        assert torch.isfinite(y_hat.grad).all()
