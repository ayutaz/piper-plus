"""Band-split spectrogram discriminator (DAC-style MRD), P1 decoder design §5.1."""

import itertools

import pytest
import torch


pytestmark = pytest.mark.unit


def _disc(**kw):
    from piper_train.vits.band_split_discriminator import (
        BandSplitSpectrogramDiscriminator,
    )

    torch.manual_seed(0)
    return BandSplitSpectrogramDiscriminator(fft_sizes=(512, 256), channels=8, **kw)


def test_band_bins_cover_every_frequency_bin_once():
    from piper_train.vits.band_split_discriminator import band_bin_ranges

    ranges = band_bin_ranges(
        n_bins=513, band_fractions=(0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
    )
    assert ranges[0][0] == 0 and ranges[-1][1] == 513
    for (a0, a1), (b0, _b1) in itertools.pairwise(ranges):
        assert a1 == b0 and a1 > a0
    # 0.25 of the Nyquist bin index lands on the 2.76 kHz decoder band edge at 22.05 kHz
    assert ranges[2][0] == 128


def test_forward_matches_mpd_interface():
    d = _disc()
    y = torch.randn(2, 1, 4096)
    y_hat = torch.randn(2, 1, 4096)
    y_d_rs, y_d_gs, fmap_rs, fmap_gs = d(y, y_hat)
    assert len(y_d_rs) == len(y_d_gs) == len(fmap_rs) == len(fmap_gs) == 2
    for r, g in zip(y_d_rs, y_d_gs, strict=True):
        assert r.shape == g.shape and r.shape[0] == 2
    for fr, fg in zip(fmap_rs, fmap_gs, strict=True):
        assert len(fr) == len(fg) > 0
        for a, b in zip(fr, fg, strict=True):
            assert a.shape == b.shape


def test_generator_gradient_flows_through_every_band():
    from piper_train.vits.losses import generator_loss

    d = _disc()
    y = torch.randn(1, 1, 4096)
    y_hat = torch.randn(1, 1, 4096, requires_grad=True)
    _r, y_d_gs, _fr, _fg = d(y, y_hat)
    loss, _ = generator_loss(y_d_gs)
    loss.backward()
    assert y_hat.grad is not None and y_hat.grad.abs().sum() > 0
    for stack in d.discriminators:
        for band in stack.band_convs:
            grads = [p.grad for p in band.parameters()]
            assert all(g is not None and g.abs().sum() > 0 for g in grads)


def test_high_band_change_moves_only_high_band_features():
    """A tone above 5.5 kHz must not change the features of the lowest band."""
    d = _disc().eval()
    sr = 22050
    t = torch.arange(4096) / sr
    low = torch.sin(2 * torch.pi * 300 * t)[None, None]
    high = low + 0.5 * torch.sin(2 * torch.pi * 8000 * t)[None, None]
    with torch.no_grad():
        f_low = d.discriminators[0].band_features(low)
        f_high = d.discriminators[0].band_features(high)
    # band 0 (0-1.1 kHz) only sees its own bins. The tone still reaches them
    # through spectral leakage at the clip edges (the reflect-padded frames are
    # not periodic), so compare against the band that holds the tone.
    moved_low = (f_low[0] - f_high[0]).abs().max()
    moved_tone = (f_low[3] - f_high[3]).abs().max()  # 5.5-8.3 kHz
    assert moved_low < 0.02 * moved_tone
