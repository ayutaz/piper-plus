"""Multi-Resolution STFT Loss for improved audio quality."""

import torch
import torch.nn.functional as F
from torch import nn


class STFTLoss(nn.Module):
    """STFT-based loss module."""

    def __init__(
        self,
        fft_size: int = 1024,
        hop_size: int = 256,
        win_size: int = 1024,
        window: str = "hann",
    ):
        super().__init__()
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.win_size = win_size
        self.register_buffer("window", self._get_window(window, win_size))

    def _get_window(self, window: str, win_size: int) -> torch.Tensor:
        """Get window function."""
        if window == "hann":
            return torch.hann_window(win_size)
        elif window == "hamming":
            return torch.hamming_window(win_size)
        else:
            raise ValueError(f"Unknown window type: {window}")

    def forward(self, y_hat: torch.Tensor, y: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute STFT magnitude and phase losses.

        Args:
            y_hat: Generated audio [B, 1, T]
            y: Ground truth audio [B, 1, T]

        Returns:
            mag_loss: Magnitude loss
            phase_loss: Phase loss
        """
        # Remove channel dimension
        y_hat = y_hat.squeeze(1)
        y = y.squeeze(1)

        # Compute STFT
        y_hat_stft = torch.stft(
            y_hat,
            n_fft=self.fft_size,
            hop_length=self.hop_size,
            win_length=self.win_size,
            window=self.window,
            return_complex=True,
        )
        y_stft = torch.stft(
            y,
            n_fft=self.fft_size,
            hop_length=self.hop_size,
            win_length=self.win_size,
            window=self.window,
            return_complex=True,
        )

        # Magnitude loss
        y_hat_mag = torch.abs(y_hat_stft)
        y_mag = torch.abs(y_stft)
        mag_loss = F.l1_loss(y_hat_mag, y_mag)

        # Phase loss (unwrapped)
        y_hat_phase = torch.angle(y_hat_stft)
        y_phase = torch.angle(y_stft)
        phase_loss = F.l1_loss(y_hat_phase, y_phase)

        return mag_loss, phase_loss


class MultiResolutionSTFTLoss(nn.Module):
    """Multi-Resolution STFT Loss.

    Computes STFT loss at multiple time-frequency resolutions for better
    perceptual quality.
    """

    def __init__(
        self,
        fft_sizes: list[int] = [512, 1024, 2048],
        hop_sizes: list[int] = [120, 240, 480],
        win_sizes: list[int] = [480, 960, 1920],
        window: str = "hann",
        mag_weight: float = 1.0,
        phase_weight: float = 0.1,
    ):
        super().__init__()
        assert len(fft_sizes) == len(hop_sizes) == len(win_sizes)

        self.stft_losses = nn.ModuleList()
        for fft_size, hop_size, win_size in zip(fft_sizes, hop_sizes, win_sizes):
            self.stft_losses.append(
                STFTLoss(fft_size, hop_size, win_size, window)
            )

        self.mag_weight = mag_weight
        self.phase_weight = phase_weight

    def forward(
        self, y_hat: torch.Tensor, y: torch.Tensor
    ) -> tuple[torch.Tensor, dict[str, float]]:
        """Compute multi-resolution STFT loss.

        Args:
            y_hat: Generated audio [B, 1, T]
            y: Ground truth audio [B, 1, T]

        Returns:
            total_loss: Weighted sum of all losses
            loss_dict: Dictionary of individual losses for logging
        """
        total_mag_loss = 0.0
        total_phase_loss = 0.0
        loss_dict = {}

        for i, stft_loss in enumerate(self.stft_losses):
            mag_loss, phase_loss = stft_loss(y_hat, y)
            total_mag_loss += mag_loss
            total_phase_loss += phase_loss

            loss_dict[f"stft_mag_{i}"] = mag_loss.item()
            loss_dict[f"stft_phase_{i}"] = phase_loss.item()

        # Average over resolutions
        total_mag_loss /= len(self.stft_losses)
        total_phase_loss /= len(self.stft_losses)

        # Weighted sum
        total_loss = (
            self.mag_weight * total_mag_loss + self.phase_weight * total_phase_loss
        )

        loss_dict["stft_mag"] = total_mag_loss.item()
        loss_dict["stft_phase"] = total_phase_loss.item()

        return total_loss, loss_dict


class SpectralConvergenceLoss(nn.Module):
    """Spectral Convergence Loss."""

    def __init__(self):
        super().__init__()

    def forward(self, y_hat_mag: torch.Tensor, y_mag: torch.Tensor) -> torch.Tensor:
        """Compute spectral convergence loss.

        Args:
            y_hat_mag: Predicted magnitude spectrogram
            y_mag: Ground truth magnitude spectrogram

        Returns:
            Spectral convergence loss
        """
        return torch.norm(y_mag - y_hat_mag, p="fro") / torch.norm(y_mag, p="fro")


class LogSTFTMagnitudeLoss(nn.Module):
    """Log STFT Magnitude Loss."""

    def __init__(self):
        super().__init__()

    def forward(self, y_hat_mag: torch.Tensor, y_mag: torch.Tensor) -> torch.Tensor:
        """Compute log STFT magnitude loss.

        Args:
            y_hat_mag: Predicted magnitude spectrogram
            y_mag: Ground truth magnitude spectrogram

        Returns:
            Log magnitude loss
        """
        # Add small epsilon to avoid log(0)
        eps = 1e-7
        return F.l1_loss(torch.log(y_hat_mag + eps), torch.log(y_mag + eps))