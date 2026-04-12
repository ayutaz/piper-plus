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
