"""Sub-band Multi-resolution STFT Loss for MB-iSTFT-VITS2.

Training-only loss module. Not included in the ONNX inference graph.
"""

import torch
import torch.nn.functional as F
from torch import nn


class SpectralConvergenceLoss(nn.Module):
    """Spectral convergence loss.

    Measures the Frobenius norm of the difference between predicted and
    target magnitude spectrograms, normalized by the target norm.
    """

    def forward(self, x_mag: torch.Tensor, y_mag: torch.Tensor) -> torch.Tensor:
        """Compute spectral convergence loss.

        Args:
            x_mag: Predicted magnitude spectrogram.
            y_mag: Target magnitude spectrogram.

        Returns:
            Scalar loss value: ||y_mag - x_mag||_F / ||y_mag||_F
        """
        return torch.norm(y_mag - x_mag, p="fro") / torch.norm(y_mag, p="fro").clamp(
            min=1e-7
        )


class LogSTFTMagnitudeLoss(nn.Module):
    """Log STFT magnitude loss.

    Computes L1 distance in the log-magnitude domain.
    """

    def forward(self, x_mag: torch.Tensor, y_mag: torch.Tensor) -> torch.Tensor:
        """Compute log STFT magnitude loss.

        Args:
            x_mag: Predicted magnitude spectrogram.
            y_mag: Target magnitude spectrogram.

        Returns:
            Scalar loss value: L1(log(x_mag), log(y_mag))
        """
        return F.l1_loss(torch.log(x_mag + 1e-7), torch.log(y_mag + 1e-7))


class STFTLoss(nn.Module):
    """Single-resolution STFT loss.

    Combines spectral convergence and log STFT magnitude losses
    for one (fft_size, hop_size, win_size) configuration.
    """

    def __init__(self, fft_size: int, hop_size: int, win_size: int) -> None:
        super().__init__()
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.win_size = win_size
        self.register_buffer("window", torch.hann_window(win_size))
        self.sc_loss = SpectralConvergenceLoss()
        self.mag_loss = LogSTFTMagnitudeLoss()

    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """Compute STFT loss for a single resolution.

        Args:
            x: Predicted waveform (B, T) or (B, 1, T).
            y: Target waveform (B, T) or (B, 1, T).

        Returns:
            Scalar loss value (spectral convergence + log magnitude).
        """
        x_mag = self._stft(x)
        y_mag = self._stft(y)
        sc = self.sc_loss(x_mag, y_mag)
        mag = self.mag_loss(x_mag, y_mag)
        return sc + mag

    def _stft(self, x: torch.Tensor) -> torch.Tensor:
        """Compute STFT magnitude spectrogram.

        Args:
            x: Waveform tensor (B, T) or (B, 1, T).

        Returns:
            Magnitude spectrogram (B, freq_bins, frames).
        """
        if x.dim() == 3:
            x = x.squeeze(1)
        stft = torch.stft(
            x,
            self.fft_size,
            self.hop_size,
            self.win_size,
            self.window,
            return_complex=True,
        )
        return torch.abs(stft)


class MultiResolutionSTFTLoss(nn.Module):
    """Multi-resolution STFT loss for sub-band signals.

    Computes STFT losses at multiple resolutions and averages them.
    Default parameters follow the MB-iSTFT-VITS2 paper for sub-band
    analysis (high / medium / low resolution).
    """

    def __init__(
        self,
        fft_sizes: tuple[int, ...] = (171, 384, 683),
        hop_sizes: tuple[int, ...] = (10, 30, 60),
        win_sizes: tuple[int, ...] = (60, 150, 300),
    ) -> None:
        super().__init__()
        self.stft_losses = nn.ModuleList()
        for fs, hs, ws in zip(fft_sizes, hop_sizes, win_sizes, strict=False):
            self.stft_losses.append(STFTLoss(fs, hs, ws))

    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """Compute multi-resolution STFT loss.

        Args:
            x: Predicted sub-band signals (B, subbands, T) or (B*subbands, T).
            y: Target sub-band signals (B, subbands, T) or (B*subbands, T).

        Returns:
            Scalar loss value averaged over all resolutions.
        """
        if x.dim() == 3:
            B, S, T = x.shape
            x = x.reshape(B * S, T)
            y = y.reshape(B * S, T)

        loss = 0.0
        for stft_loss in self.stft_losses:
            loss += stft_loss(x, y)
        return loss / len(self.stft_losses)


class BandWeightedSTFTLoss(STFTLoss):
    """Single-resolution *band-weighted* STFT magnitude loss (GT reference).

    Same spectral-convergence + log-magnitude structure as :class:`STFTLoss`
    but every rfft bin is multiplied by a **fixed** per-frequency weight
    before the norms are taken, so the loss only "sees" the configured
    bands. The weight is a buffer (never a parameter): making it trainable
    would hand the GAN yet another unconstrained degree of freedom, which is
    exactly the failure mode this loss exists to police (v10b trainable-PQMF
    drift, docs/design/zero-shot-v10b-residual-noise-diagnosis.md §3).
    """

    def __init__(
        self,
        fft_size: int,
        hop_size: int,
        win_size: int,
        sample_rate: int,
        band_weights: tuple[tuple[float, float, float], ...],
    ) -> None:
        super().__init__(fft_size, hop_size, win_size)
        n_bins = fft_size // 2 + 1
        freqs = torch.linspace(0.0, sample_rate / 2.0, n_bins)
        weight = torch.zeros(n_bins)
        for lo_hz, hi_hz, w in band_weights:
            weight[(freqs >= lo_hz) & (freqs < hi_hz)] = w
        self.register_buffer("band_weight", weight)

    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """Compute band-weighted STFT loss for one resolution.

        Args:
            x: Predicted waveform (B, T) or (B, 1, T).
            y: Target (ground-truth) waveform (B, T) or (B, 1, T).

        Returns:
            Scalar loss: weighted spectral convergence + weighted log-mag L1
            (the L1 mean is taken over the weight mass, not over all bins,
            so out-of-band bins neither contribute nor dilute).
        """
        x_mag = self._stft(x)
        y_mag = self._stft(y)
        w = self.band_weight.view(1, -1, 1)

        sc = torch.norm(w * (y_mag - x_mag), p="fro") / torch.norm(
            w * y_mag, p="fro"
        ).clamp(min=1e-7)

        log_diff = (torch.log(x_mag + 1e-7) - torch.log(y_mag + 1e-7)).abs()
        weighted = w * log_diff
        mag = weighted.sum() / w.expand_as(log_diff).sum().clamp(min=1e-7)
        return sc + mag


class HighBandSTFTLoss(nn.Module):
    """High-band (6-11kHz) band-weighted multi-resolution STFT loss (v11 柱2).

    GT-teacher magnitude regression against the ground-truth waveform for the
    band where mel L1 and the default STFT losses are effectively blind
    (coarse high-frequency mel bins). Motivated by the v10b A2' incident:
    the GAN parked a +6.9dB noise floor in band3 (8.3-11kHz) via the
    then-trainable PQMF synthesis filter, and no existing loss pushed back
    (docs/design/zero-shot-v10b-residual-noise-diagnosis.md §3).

    Contract note (docs/spec/zs-eval-contract.md §2): this is the *exception
    form* — a GT-teacher regression in the mel/STFT/MRD family — NOT a
    loss-ification of the E-4 comb metrics or of measure_band_noise;
    metric-module imports are structurally banned by
    ``scripts/check_zs_metric_isolation.py``.

    Default weighting: 6-9kHz weight 1.0, 9-11kHz (up to Nyquist) weight 2.0
    (band3 was the drift battleground, 9-11kHz the worst), <6kHz weight 0
    (that band belongs to mel L1 / sub-band STFT — pulling this loss down
    into it would upset the existing coefficient balance).
    """

    DEFAULT_BAND_WEIGHTS: tuple[tuple[float, float, float], ...] = (
        (6000.0, 9000.0, 1.0),
        (9000.0, 12000.0, 2.0),
    )

    def __init__(
        self,
        sample_rate: int = 22050,
        fft_sizes: tuple[int, ...] = (512, 1024, 2048),
        hop_sizes: tuple[int, ...] = (128, 256, 512),
        win_sizes: tuple[int, ...] = (512, 1024, 2048),
        band_weights: tuple[tuple[float, float, float], ...] = DEFAULT_BAND_WEIGHTS,
    ) -> None:
        super().__init__()
        self.stft_losses = nn.ModuleList()
        for fs, hs, ws in zip(fft_sizes, hop_sizes, win_sizes, strict=False):
            self.stft_losses.append(
                BandWeightedSTFTLoss(fs, hs, ws, sample_rate, band_weights)
            )

    def forward(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """Compute the multi-resolution band-weighted loss.

        Args:
            x: Predicted full-band waveform (B, T) or (B, 1, T).
            y: Target (ground-truth) full-band waveform, same shape.

        Returns:
            Scalar loss averaged over all resolutions.
        """
        if x.dim() == 3:
            x = x.squeeze(1)
        if y.dim() == 3:
            y = y.squeeze(1)
        loss = 0.0
        for stft_loss in self.stft_losses:
            loss += stft_loss(x, y)
        return loss / len(self.stft_losses)
