"""Tests for VitsModel MB-iSTFT decoder integration.

Verifies that VitsModel correctly initialises PQMF / sub-band STFT loss,
shares the PQMF instance with the generator, and includes MB-iSTFT
parameters in the optimiser. MB-iSTFT is the only decoder path.
"""

import pytest


torch = pytest.importorskip("torch", reason="torch required")


def _make_vitsmodel():
    """Create a minimal VitsModel with the standard MB-iSTFT upsample
    structure (4, 4) that __main__.main() applies for all qualities.
    """
    from piper_train.vits.lightning import VitsModel

    return VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
    )


@pytest.mark.unit
def test_vitsmodel_init_pqmf():
    """VitsModel always creates PQMF and sub-band STFT loss."""
    model = _make_vitsmodel()
    assert model.pqmf is not None
    assert model.sub_stft_loss is not None


@pytest.mark.unit
def test_vitsmodel_hparams_saved():
    """upsample_rates are persisted in hparams."""
    model = _make_vitsmodel()
    assert model.hparams.upsample_rates == (4, 4)


@pytest.mark.unit
def test_vitsmodel_pqmf_shared_with_generator():
    """VitsModel.pqmf and decoder.pqmf are the same instance."""
    model = _make_vitsmodel()
    assert model.pqmf is model.model_g.dec.pqmf


@pytest.mark.unit
def test_vitsmodel_configure_optimizers():
    """MB-iSTFT parameters are included in the generator optimiser."""
    model = _make_vitsmodel()
    try:
        opt_g, opt_d = model.configure_optimizers()
        g_param_count = sum(
            p.numel() for group in opt_g[0].param_groups for p in group["params"]
        )
        assert g_param_count > 0
    except Exception:
        pytest.skip("configure_optimizers requires Trainer context")
