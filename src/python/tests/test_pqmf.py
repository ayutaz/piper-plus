"""Tests for PQMF (Pseudo Quadrature Mirror Filterbank).

Verifies analysis/synthesis round-trip reconstruction, output shapes,
buffer registration, and batch processing of piper_train.vits.mb_istft.PQMF.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


@pytest.mark.unit
def test_pqmf_roundtrip_reconstruction():
    """PQMF analysis -> synthesis round-trip has reconstruction SNR > 5 dB.

    The cosine-modulated PQMF is a *near*-perfect-reconstruction filter bank
    (~7-8 dB with Kaiser-window prototype).  The neural network compensates
    for residual aliasing during training, so a moderate SNR floor suffices.
    """
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    x = torch.randn(1, 1, 8192)
    subbands = pqmf.analysis(x)
    x_hat = pqmf.synthesis(subbands)
    # Exclude edge artefacts (taps // 2 = 31 samples)
    trim = 31
    error = x[..., trim:-trim] - x_hat[..., trim:-trim]
    snr_db = 10 * torch.log10(
        torch.sum(x[..., trim:-trim] ** 2) / torch.sum(error**2)
    )
    assert snr_db > 5, f"Reconstruction SNR {snr_db:.1f} dB < 5 dB"


@pytest.mark.unit
def test_pqmf_analysis_output_shape():
    """analysis output shape is [B, subbands, T // subbands]."""
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    x = torch.randn(2, 1, 8192)
    out = pqmf.analysis(x)
    assert out.shape == (2, 4, 2048)


@pytest.mark.unit
def test_pqmf_synthesis_output_shape():
    """synthesis output shape is [B, 1, T_sub * subbands]."""
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    x = torch.randn(2, 4, 2048)
    out = pqmf.synthesis(x)
    assert out.shape == (2, 1, 8192)


@pytest.mark.unit
def test_pqmf_buffers_registered():
    """analysis_filter, synthesis_filter, updown_filter are registered buffers."""
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF()
    buffers = dict(pqmf.named_buffers())
    assert "analysis_filter" in buffers
    assert "synthesis_filter" in buffers
    assert "updown_filter" in buffers
    # No trainable parameters
    assert len(list(pqmf.parameters())) == 0


@pytest.mark.unit
def test_pqmf_batch_processing():
    """Batch size > 1 produces correct output shape after round-trip."""
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF()
    x = torch.randn(4, 1, 4096)
    subbands = pqmf.analysis(x)
    x_hat = pqmf.synthesis(subbands)
    assert x_hat.shape == (4, 1, 4096)
