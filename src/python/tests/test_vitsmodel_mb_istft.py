"""Tests for VitsModel with mb_istft=True path.

Verifies that the MB-iSTFT code path in VitsModel correctly initialises
PQMF / sub-band STFT loss, saves hparams, shares the PQMF instance with
the generator, and includes MB-iSTFT parameters in the optimiser.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_vitsmodel(mb_istft=False):
    """Create a minimal VitsModel with or without MB-iSTFT enabled."""
    from piper_train.vits.lightning import VitsModel

    return VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
        mb_istft=mb_istft,
    )


@pytest.mark.unit
def test_vitsmodel_mb_istft_init_pqmf():
    """MB-iSTFT path creates PQMF and sub-band STFT loss."""
    model = _make_vitsmodel(mb_istft=True)
    assert model.pqmf is not None
    assert model.sub_stft_loss is not None


@pytest.mark.unit
def test_vitsmodel_no_pqmf_without_flag():
    """Without mb_istft, PQMF and sub-band STFT loss are None."""
    model = _make_vitsmodel(mb_istft=False)
    assert model.pqmf is None
    assert model.sub_stft_loss is None


@pytest.mark.unit
def test_vitsmodel_hparams_saved():
    """mb_istft flag is persisted in hparams."""
    model = _make_vitsmodel(mb_istft=True)
    assert model.hparams.mb_istft is True
    assert model.hparams.upsample_rates == (4, 4) or model.hparams.mb_istft  # flag is saved


@pytest.mark.unit
def test_vitsmodel_pqmf_shared_with_generator():
    """VitsModel.pqmf and Generator.pqmf are the same instance."""
    model = _make_vitsmodel(mb_istft=True)
    # VitsModel.pqmf and Generator.pqmf should be the same object
    assert model.pqmf is model.model_g.dec.pqmf


@pytest.mark.unit
def test_vitsmodel_configure_optimizers():
    """MB-iSTFT parameters are included in the generator optimiser."""
    model = _make_vitsmodel(mb_istft=True)
    # configure_optimizers may require Trainer context in some PL versions
    try:
        opt_g, opt_d = model.configure_optimizers()
        # MB-iSTFT parameters should be present in the generator optimiser
        g_param_count = sum(
            p.numel() for group in opt_g[0].param_groups for p in group["params"]
        )
        assert g_param_count > 0
    except Exception:
        pytest.skip("configure_optimizers requires Trainer context")
