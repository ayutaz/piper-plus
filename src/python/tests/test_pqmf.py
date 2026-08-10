"""Tests for PQMF (Pseudo Quadrature Mirror Filterbank).

Verifies analysis/synthesis round-trip reconstruction, output shapes,
buffer registration, and batch processing of piper_train.vits.mb_istft.PQMF.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _roundtrip_snr_db(pqmf, x: "torch.Tensor") -> float:
    """Analysis->synthesis round-trip SNR, excluding filter edge artefacts."""
    subbands = pqmf.analysis(x)
    x_hat = pqmf.synthesis(subbands)
    trim = 31  # taps // 2
    error = x[..., trim:-trim] - x_hat[..., trim:-trim]
    snr = 10 * torch.log10(torch.sum(x[..., trim:-trim] ** 2) / torch.sum(error**2))
    return float(snr)


@pytest.mark.unit
def test_pqmf_roundtrip_reconstruction():
    """PQMF round-trip SNR floor — CURRENTLY PINNED TO A KNOWN-BUGGY VALUE.

    HISTORICAL WARNING (do not repeat): this test originally claimed that
    "~7-8 dB is the theoretical limit of a near-perfect-reconstruction
    filter bank and the neural network compensates the residual aliasing".
    Both claims were false. The implementation is missing the ``(-1)^k·π/4``
    phase term of the canonical cosine modulation, so alias cancellation
    does not work; a correct PQMF with the same Kaiser prototype measures
    ~60 dB (band-edge tones ~59 dB vs -1.6 dB here). The learned "NN
    compensation" only generalises for single-speaker fine-tunes and is the
    root cause of the audible zero-shot aliasing noise. Full analysis:
    docs/design/zero-shot-noise-root-cause-pqmf.md.

    The 5 dB floor is kept ONLY because every shipped MB-iSTFT checkpoint
    is trained against the buggy bank (fixing the bank breaks them). When
    the bank is fixed (v9), delete this test and promote
    ``test_pqmf_reconstruction_matches_canonical`` below to the gate.
    """
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    x = torch.randn(1, 1, 8192)
    snr_db = _roundtrip_snr_db(pqmf, x)
    assert snr_db > 5, f"Reconstruction SNR {snr_db:.1f} dB < 5 dB"


@pytest.mark.unit
@pytest.mark.xfail(
    strict=True,
    reason="Known PQMF aliasing bug: missing (-1)^k*pi/4 modulation phase term "
    "(docs/design/zero-shot-noise-root-cause-pqmf.md). A canonical "
    "cosine-modulated PQMF reaches ~60 dB round-trip SNR with this prototype. "
    "strict=True: when the bank is fixed this test XPASSes as FAILURE, forcing "
    "removal of the xfail marker and promotion to the real gate.",
)
def test_pqmf_reconstruction_matches_canonical():
    """Near-perfect reconstruction: round-trip SNR must be >= 55 dB.

    This is the criterion the original requirements specified (residual
    aliasing at -90 dB, later relaxed — see root-cause doc §4). Band-edge
    tones are the sharpest probe: harmonics crossing 2756/5512/8268 Hz are
    exactly where the missing phase term leaks mirror images.
    """
    import math

    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    sr = 22050
    t = torch.arange(8192, dtype=torch.float32) / sr

    x = torch.randn(1, 1, 8192)
    assert _roundtrip_snr_db(pqmf, x) >= 55, "white-noise round-trip below 55 dB"

    for freq in (2756.25, 5512.5, 8268.75):  # PQMF band edges @ 22.05 kHz
        tone = torch.sin(2 * math.pi * freq * t).reshape(1, 1, -1)
        snr = _roundtrip_snr_db(pqmf, tone)
        assert snr >= 50, f"band-edge tone {freq:.0f} Hz round-trip {snr:.1f} dB < 50 dB"


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
