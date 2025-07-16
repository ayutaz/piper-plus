"""Multi-Resolution STFT Discriminator for improved perceptual quality."""

import torch
from torch import nn
from torch.nn.utils import spectral_norm, weight_norm


class Conv2DBlock(nn.Module):
    """2D Convolutional block with normalization and activation."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: tuple[int, int],
        stride: tuple[int, int] = (1, 1),
        padding: tuple[int, int] = (0, 0),
        norm_type: str = "spectral",
    ):
        super().__init__()

        # Choose normalization
        if norm_type == "spectral":
            self.conv = spectral_norm(
                nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding),
            )
        elif norm_type == "weight":
            self.conv = weight_norm(
                nn.Conv2d(in_channels, out_channels, kernel_size, stride, padding),
            )
        else:
            self.conv = nn.Conv2d(
                in_channels, out_channels, kernel_size, stride, padding
            )

        self.activation = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.activation(self.conv(x))


class STFTDiscriminator(nn.Module):
    """Single resolution STFT discriminator."""

    def __init__(
        self,
        fft_size: int = 1024,
        hop_size: int = 256,
        win_size: int = 1024,
        norm_type: str = "spectral",
        channels: list[int] | None = None,
    ):
        super().__init__()
        if channels is None:
            channels = [32, 64, 128, 256, 512]
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.win_size = win_size
        self.register_buffer("window", torch.hann_window(win_size))

        # Build convolutional layers
        self.convs = nn.ModuleList()
        in_channels = 2  # Real and imaginary parts

        for i, out_channels in enumerate(channels):
            kernel_size = (3, 3) if i < len(channels) - 1 else (3, 1)
            stride = (2, 2) if i < len(channels) - 1 else (1, 1)
            padding = (1, 1) if i < len(channels) - 1 else (1, 0)

            self.convs.append(
                Conv2DBlock(
                    in_channels,
                    out_channels,
                    kernel_size,
                    stride,
                    padding,
                    norm_type,
                ),
            )
            in_channels = out_channels

        # Final conv to single channel output
        if norm_type == "spectral":
            self.conv_post = spectral_norm(
                nn.Conv2d(channels[-1], 1, (3, 1), (1, 1), (1, 0))
            )
        else:
            self.conv_post = weight_norm(
                nn.Conv2d(channels[-1], 1, (3, 1), (1, 1), (1, 0))
            )

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, list[torch.Tensor]]:
        """Forward pass of STFT discriminator.

        Args:
            x: Input audio [B, 1, T] or [B, T]

        Returns:
            output: Discriminator output
            feature_maps: List of intermediate feature maps
        """
        # Handle different input shapes
        if x.dim() == 3:
            x = x.squeeze(1)

        # Compute STFT
        x_stft = torch.stft(
            x,
            n_fft=self.fft_size,
            hop_length=self.hop_size,
            win_length=self.win_size,
            window=self.window,
            return_complex=True,
        )  # [B, F, T]

        # Stack real and imaginary parts
        x_real = x_stft.real.unsqueeze(1)  # [B, 1, F, T]
        x_imag = x_stft.imag.unsqueeze(1)  # [B, 1, F, T]
        x = torch.cat([x_real, x_imag], dim=1)  # [B, 2, F, T]

        # Pass through conv layers
        feature_maps = []
        for conv in self.convs:
            x = conv(x)
            feature_maps.append(x)

        # Final output
        x = self.conv_post(x)
        feature_maps.append(x)
        x = x.squeeze(1)  # [B, F', T']

        return x, feature_maps


class MultiResolutionSTFTDiscriminator(nn.Module):
    """Multi-Resolution STFT Discriminator.

    Uses multiple STFT resolutions to capture different time-frequency characteristics.
    """

    def __init__(
        self,
        fft_sizes: list[int] | None = None,
        hop_sizes: list[int] | None = None,
        win_sizes: list[int] | None = None,
        norm_type: str = "spectral",
        channels: list[list[int]] | None = None,
    ):
        super().__init__()
        if fft_sizes is None:
            fft_sizes = [512, 1024, 2048]
        if hop_sizes is None:
            hop_sizes = [120, 240, 480]
        if win_sizes is None:
            win_sizes = [480, 960, 1920]
        assert len(fft_sizes) == len(hop_sizes) == len(win_sizes)

        # Default channel configurations for each resolution
        if channels is None:
            channels = [
                [32, 64, 128, 256, 512],  # High resolution
                [32, 64, 128, 256, 512],  # Mid resolution
                [32, 64, 128, 256, 512],  # Low resolution
            ]

        self.discriminators = nn.ModuleList()
        for fft_size, hop_size, win_size, ch in zip(
            fft_sizes,
            hop_sizes,
            win_sizes,
            channels,
            strict=False,
        ):
            self.discriminators.append(
                STFTDiscriminator(fft_size, hop_size, win_size, norm_type, ch),
            )

    def forward(
        self,
        y: torch.Tensor,
        y_hat: torch.Tensor,
    ) -> tuple[
        list[torch.Tensor],
        list[torch.Tensor],
        list[list[torch.Tensor]],
        list[list[torch.Tensor]],
    ]:
        """Forward pass of multi-resolution STFT discriminator.

        Args:
            y: Real audio [B, 1, T]
            y_hat: Generated audio [B, 1, T]

        Returns:
            y_d_rs: List of real audio discriminator outputs
            y_d_gs: List of generated audio discriminator outputs
            fmap_rs: List of real audio feature maps
            fmap_gs: List of generated audio feature maps
        """
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []

        for discriminator in self.discriminators:
            y_d_r, fmap_r = discriminator(y)
            y_d_g, fmap_g = discriminator(y_hat)

            y_d_rs.append(y_d_r)
            y_d_gs.append(y_d_g)
            fmap_rs.append(fmap_r)
            fmap_gs.append(fmap_g)

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class CombinedMultiDiscriminator(nn.Module):
    """Combined discriminator using both Multi-Period and Multi-Resolution STFT."""

    def __init__(
        self,
        use_spectral_norm: bool = False,
        # Multi-Resolution STFT params
        fft_sizes: list[int] | None = None,
        hop_sizes: list[int] | None = None,
        win_sizes: list[int] | None = None,
    ):
        super().__init__()
        if fft_sizes is None:
            fft_sizes = [512, 1024, 2048]
        if hop_sizes is None:
            hop_sizes = [120, 240, 480]
        if win_sizes is None:
            win_sizes = [480, 960, 1920]

        # Import existing MultiPeriodDiscriminator
        from .models import MultiPeriodDiscriminator

        self.mpd = MultiPeriodDiscriminator(use_spectral_norm)
        self.mrd = MultiResolutionSTFTDiscriminator(
            fft_sizes,
            hop_sizes,
            win_sizes,
            norm_type="spectral" if use_spectral_norm else "weight",
        )

    def forward(
        self,
        y: torch.Tensor,
        y_hat: torch.Tensor,
    ) -> tuple[
        list[torch.Tensor],
        list[torch.Tensor],
        list[list[torch.Tensor]],
        list[list[torch.Tensor]],
    ]:
        """Forward pass combining both discriminators.

        Args:
            y: Real audio [B, 1, T]
            y_hat: Generated audio [B, 1, T]

        Returns:
            y_d_rs: Combined list of real audio discriminator outputs
            y_d_gs: Combined list of generated audio discriminator outputs
            fmap_rs: Combined list of real audio feature maps
            fmap_gs: Combined list of generated audio feature maps
        """
        # Multi-Period Discriminator
        mpd_y_d_rs, mpd_y_d_gs, mpd_fmap_rs, mpd_fmap_gs = self.mpd(y, y_hat)

        # Multi-Resolution STFT Discriminator
        mrd_y_d_rs, mrd_y_d_gs, mrd_fmap_rs, mrd_fmap_gs = self.mrd(y, y_hat)

        # Combine outputs
        y_d_rs = mpd_y_d_rs + mrd_y_d_rs
        y_d_gs = mpd_y_d_gs + mrd_y_d_gs
        fmap_rs = mpd_fmap_rs + mrd_fmap_rs
        fmap_gs = mpd_fmap_gs + mrd_fmap_gs

        return y_d_rs, y_d_gs, fmap_rs, fmap_gs
