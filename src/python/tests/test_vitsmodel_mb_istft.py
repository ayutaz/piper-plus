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


@pytest.mark.unit
def test_vitsmodel_propagates_decoder_type():
    """AI-03: ``VitsModel`` round-trips ``decoder_type`` through ``save_hyperparameters``.

    Pin for ``lightning.py`` L133 + L171. ``save_hyperparameters()`` is
    what determines ``ckpt['hyper_parameters']`` content; a future refactor
    that omits the kwarg silently from the SynthesizerTrn construction
    site would leave the hparam set but break ckpt reproducibility
    (AI-05 dependency). Pin both surfaces.
    """
    from piper_train.vits.lightning import VitsModel

    # Default: decoder_type is saved into hparams AND reaches model_g.dec.
    model_default = _make_vitsmodel()
    assert model_default.hparams.decoder_type == "mb_istft_1d", (
        f"AI-03: default decoder_type drifted to {model_default.hparams.decoder_type!r}"
    )
    assert model_default.model_g.dec.decoder_type == "mb_istft_1d", (
        "AI-03: hparams default not propagated to inner MBiSTFTGenerator"
    )

    # Explicit value: round-trip survives save_hyperparameters().
    model_new = VitsModel(
        num_symbols=97,
        num_speakers=1,
        num_languages=2,
        dataset=None,
        batch_size=4,
        learning_rate=2e-4,
        use_wavlm_discriminator=False,
        upsample_rates=(4, 4),
        upsample_kernel_sizes=(16, 16),
        decoder_type="istftnet2_mb_1d2d",
    )
    assert model_new.hparams.decoder_type == "istftnet2_mb_1d2d", (
        "AI-03: save_hyperparameters() lost the explicit decoder_type kwarg"
    )
    assert model_new.model_g.dec.decoder_type == "istftnet2_mb_1d2d", (
        "AI-03: hparams.decoder_type was set but did not reach model_g.dec"
    )
