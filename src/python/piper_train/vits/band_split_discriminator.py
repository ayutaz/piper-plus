"""Band-split multi-resolution spectrogram discriminator (DAC-style MRD).

P1 decoder design (docs/design/zero-shot-decoder-p1-design-2026-10-29.md §2 H2,
§5.1): the existing MRD (``DiscriminatorR``) runs one conv stack over the whole
magnitude spectrogram, so the loud low band dominates what it learns and the
quiet bands above 2.8 kHz — where the audible roughness lives (plan §7.9) —
get little adversarial pressure. Following DAC (Kumar et al. 2023), each
resolution splits the complex STFT into frequency bands and gives every band
its own conv stack; the band outputs are joined only at the final layer.

Interface matches ``MultiPeriodDiscriminator``:
``forward(y, y_hat) -> (y_d_rs, y_d_gs, fmap_rs, fmap_gs)``.

Training-only; nothing here is exported.
"""

from __future__ import annotations

import itertools

import torch
from torch import nn
from torch.amp import autocast
from torch.nn import functional as F
from torch.nn.utils import weight_norm


# DAC's band split, as fractions of the Nyquist bin. At 22.05 kHz the edges are
# 1.1 / 2.76 / 5.5 / 8.3 kHz; 0.25 / 0.5 / 0.75 coincide with the MB-iSTFT
# decoder's 4-band edges.
DEFAULT_BAND_FRACTIONS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
LRELU_SLOPE = 0.1


def band_bin_ranges(
    n_bins: int, band_fractions: tuple[float, ...] = DEFAULT_BAND_FRACTIONS
) -> list[tuple[int, int]]:
    """``[start, stop)`` STFT bin ranges that tile ``n_bins`` without overlap."""
    edges = [round(f * (n_bins - 1)) for f in band_fractions]
    edges[-1] = n_bins
    return list(itertools.pairwise(edges))


class BandSplitDiscriminatorR(nn.Module):
    """One STFT resolution; real and imaginary parts as 2 input channels."""

    def __init__(
        self,
        n_fft: int,
        band_fractions: tuple[float, ...] = DEFAULT_BAND_FRACTIONS,
        channels: int = 32,
    ):
        super().__init__()
        self.n_fft = n_fft
        self.hop = n_fft // 4
        self.bands = band_bin_ranges(n_fft // 2 + 1, band_fractions)
        self.register_buffer("window", torch.hann_window(n_fft), persistent=False)

        def stack() -> nn.ModuleList:
            c = channels
            return nn.ModuleList(
                [
                    weight_norm(nn.Conv2d(2, c, (3, 9), padding=(1, 4))),
                    weight_norm(nn.Conv2d(c, c, (3, 9), stride=(1, 2), padding=(1, 4))),
                    weight_norm(nn.Conv2d(c, c, (3, 9), stride=(1, 2), padding=(1, 4))),
                    weight_norm(nn.Conv2d(c, c, (3, 9), stride=(1, 2), padding=(1, 4))),
                    weight_norm(nn.Conv2d(c, c, (3, 3), padding=(1, 1))),
                ]
            )

        self.band_convs = nn.ModuleList([stack() for _ in self.bands])
        self.conv_post = weight_norm(nn.Conv2d(channels, 1, (3, 3), padding=(1, 1)))

    def spectrogram(self, x: torch.Tensor) -> torch.Tensor:
        """[B, 1, T] -> [B, 2, frames, bins]; fp32 regardless of autocast (cuFFT)."""
        with autocast(x.device.type, enabled=False):
            spec = torch.stft(
                x.float().squeeze(1),
                n_fft=self.n_fft,
                hop_length=self.hop,
                window=self.window.float(),
                center=True,
                return_complex=True,
            )
        return torch.view_as_real(spec).permute(0, 3, 2, 1)

    def _run(self, x: torch.Tensor):
        spec = self.spectrogram(x)
        fmap, outs = [], []
        for (start, stop), convs in zip(self.bands, self.band_convs, strict=True):
            h = spec[..., start:stop]
            for conv in convs:
                h = F.leaky_relu(conv(h), LRELU_SLOPE)
                fmap.append(h)
            outs.append(h)
        return outs, fmap

    def band_features(self, x: torch.Tensor) -> list[torch.Tensor]:
        """Per-band outputs of the band stacks, before they are joined."""
        return self._run(x)[0]

    def forward(self, x: torch.Tensor):
        outs, fmap = self._run(x)
        h = self.conv_post(torch.cat(outs, dim=-1))
        fmap.append(h)
        return torch.flatten(h, 1, -1), fmap


class BandSplitSpectrogramDiscriminator(nn.Module):
    def __init__(
        self,
        fft_sizes: tuple[int, ...] = (2048, 1024, 512),
        band_fractions: tuple[float, ...] = DEFAULT_BAND_FRACTIONS,
        channels: int = 32,
    ):
        super().__init__()
        self.discriminators = nn.ModuleList(
            [BandSplitDiscriminatorR(n, band_fractions, channels) for n in fft_sizes]
        )

    def forward(self, y: torch.Tensor, y_hat: torch.Tensor):
        y_d_rs, y_d_gs, fmap_rs, fmap_gs = [], [], [], []
        b = y.shape[0]
        x = torch.cat([y, y_hat], dim=0)
        for d in self.discriminators:
            score, fmap = d(x)
            y_d_rs.append(score[:b])
            y_d_gs.append(score[b:])
            fmap_rs.append([f[:b] for f in fmap])
            fmap_gs.append([f[b:] for f in fmap])
        return y_d_rs, y_d_gs, fmap_rs, fmap_gs
