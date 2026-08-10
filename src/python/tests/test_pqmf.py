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


def _legacy_buggy_coefficients(subbands=4, taps=62, cutoff_ratio=0.15, beta=9.0):
    """Reproduce the pre-2026-08 (buggy) PQMF coefficients.

    Kept as a test fixture ONLY: every MB-iSTFT checkpoint shipped before the
    v9 fix was trained against this bank and restores these values via
    state_dict. The bugs (missing ``(-1)^k·π/4`` phase, modulation centred at
    ``subbands/2``, grouped-eye updown skew) are documented in
    docs/design/zero-shot-noise-root-cause-pqmf.md. Do NOT use for new banks.
    """
    import numpy as np

    filter_length = taps + 1
    omega_c = np.pi * cutoff_ratio
    t = np.arange(-(taps // 2), taps // 2 + 1, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        sinc = np.where(t == 0, omega_c / np.pi, np.sin(omega_c * t) / (np.pi * t))
    prototype = sinc * np.kaiser(filter_length, beta)
    analysis = np.zeros((subbands, 1, filter_length))
    for k in range(subbands):
        for n in range(filter_length):
            analysis[k, 0, n] = (
                2.0 * prototype[n]
                * np.cos((2 * k + 1) * np.pi / (2 * subbands) * (n - subbands / 2))
            )
    synthesis = analysis[:, :, ::-1].copy()
    updown = np.eye(subbands, dtype=np.float32).reshape(subbands, 1, subbands)
    return (
        torch.from_numpy(analysis).float(),
        torch.from_numpy(synthesis).float(),
        torch.from_numpy(updown),
    )


@pytest.mark.unit
def test_pqmf_reconstruction_matches_canonical():
    """Near-perfect reconstruction: round-trip SNR must be >= 55 dB.

    This is the criterion the original requirements specified (residual
    aliasing at -90 dB — later wrongly relaxed to 5 dB by mistaking the buggy
    implementation's 7-8 dB for a "theoretical limit"; see root-cause doc §4
    and the ``test-threshold-relaxation`` pre-commit gate born from it).
    Band-edge tones are the sharpest probe: harmonics crossing
    2756/5512/8268 Hz are exactly where a broken phase term leaks mirror
    images.
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
def test_pqmf_legacy_checkpoint_coefficients_restore():
    """Legacy (pre-fix) checkpoints must keep their trained bank behaviour.

    Buffer shapes are intentionally unchanged by the v9 fix, so loading an
    old checkpoint's state_dict restores the old (buggy) coefficients and the
    model behaves exactly as trained. This pins that compatibility contract:
    (1) legacy buffers load without shape errors, (2) the restored bank
    reproduces the legacy round-trip characteristic (~7-8 dB — NOT the
    canonical ~60 dB), proving the coefficients came from the checkpoint
    rather than the new constructor.
    """
    from piper_train.vits.mb_istft import PQMF

    pqmf = PQMF(subbands=4)
    ana, syn, ud = _legacy_buggy_coefficients()
    pqmf.load_state_dict(
        {"analysis_filter": ana, "synthesis_filter": syn, "updown_filter": ud}
    )

    torch.manual_seed(0)
    x = torch.randn(1, 1, 8192)
    snr = _roundtrip_snr_db(pqmf, x)
    assert 4 < snr < 20, (
        f"legacy coefficients should reproduce the legacy ~7-8 dB round-trip, "
        f"got {snr:.1f} dB (restore from checkpoint is broken if this is ~60 dB)"
    )


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
