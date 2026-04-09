"""ECAPA-TDNN Speaker Encoder.

Reference:
    Desplanques, B., Thienpondt, J., & Demuynck, K. (2020).
    "ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation
    in TDNN Based Speaker Verification." Proc. Interspeech 2020.

Architecture summary:
    1. Initial TDNN layer (Conv1d, k=5)
    2. 3x SE-Res2Net blocks (k=3, dilation=2,3,4, scale=8)
    3. Multi-layer feature aggregation (MFA) via concatenation + Conv1d
    4. Attentive Statistics Pooling (ASP)
    5. Fully-connected layer -> 256-dim L2-normalized embedding
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class SEModule(nn.Module):
    """Squeeze-and-Excitation module.

    Adaptively recalibrates channel-wise feature responses by modelling
    inter-channel dependencies through a bottleneck FC structure.

    Args:
        channels: Number of input/output channels.
        bottleneck: Bottleneck dimension (default: 128).
    """

    def __init__(self, channels: int, bottleneck: int = 128) -> None:
        super().__init__()
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Conv1d(channels, bottleneck, kernel_size=1, bias=True),
            nn.ReLU(inplace=True),
            nn.Conv1d(bottleneck, channels, kernel_size=1, bias=True),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply channel-wise squeeze-and-excitation.

        Args:
            x: (batch, channels, time)
        Returns:
            Recalibrated tensor of same shape.
        """
        return x * self.se(x)


class Res2NetBlock(nn.Module):
    """Res2Net split-transform-merge block with scale=8.

    Splits the input channels into ``scale`` groups and applies hierarchical
    residual-like connections across them.  Each group (except the first) is
    convolved and added to the previous group's output, enabling multi-scale
    feature extraction within a single block.

    Args:
        channels: Number of input/output channels (must be divisible by ``scale``).
        kernel_size: Convolution kernel size.
        dilation: Convolution dilation factor.
        scale: Number of parallel branches (default: 8).
    """

    def __init__(
        self,
        channels: int,
        kernel_size: int,
        dilation: int,
        scale: int = 8,
    ) -> None:
        super().__init__()
        assert channels % scale == 0, (
            f"channels ({channels}) must be divisible by scale ({scale})"
        )
        self.scale = scale
        self.width = channels // scale

        self.convs = nn.ModuleList(
            [
                nn.Conv1d(
                    self.width,
                    self.width,
                    kernel_size=kernel_size,
                    dilation=dilation,
                    padding=dilation * (kernel_size - 1) // 2,
                )
                for _ in range(scale - 1)
            ]
        )
        self.bns = nn.ModuleList([nn.BatchNorm1d(self.width) for _ in range(scale - 1)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Split, hierarchically convolve, and merge.

        Args:
            x: (batch, channels, time)
        Returns:
            Multi-scale features of same shape.
        """
        splits = torch.split(x, self.width, dim=1)
        outputs: list[torch.Tensor] = [splits[0]]

        for i in range(self.scale - 1):
            sp = splits[i + 1]
            if i > 0:
                sp = sp + outputs[-1]
            sp = F.relu(self.bns[i](self.convs[i](sp)), inplace=True)
            outputs.append(sp)

        return torch.cat(outputs, dim=1)


class SERes2NetBlock(nn.Module):
    """SE-Res2Net block for ECAPA-TDNN.

    Combines a 1x1 expansion, Res2Net multi-scale convolution, another 1x1
    projection, and Squeeze-and-Excitation recalibration, all wrapped in a
    residual connection.

    Args:
        channels: Number of input/output channels.
        kernel_size: Res2Net convolution kernel size (default: 3).
        dilation: Dilation factor (default: 2).
        scale: Res2Net scale parameter (default: 8).
        se_bottleneck: SE module bottleneck dimension (default: 128).
    """

    def __init__(
        self,
        channels: int,
        kernel_size: int = 3,
        dilation: int = 2,
        scale: int = 8,
        se_bottleneck: int = 128,
    ) -> None:
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, kernel_size=1, bias=True)
        self.bn1 = nn.BatchNorm1d(channels)

        self.res2net = Res2NetBlock(channels, kernel_size, dilation, scale)

        self.conv2 = nn.Conv1d(channels, channels, kernel_size=1, bias=True)
        self.bn2 = nn.BatchNorm1d(channels)

        self.se = SEModule(channels, bottleneck=se_bottleneck)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """SE-Res2Net forward with residual connection.

        Args:
            x: (batch, channels, time)
        Returns:
            Tensor of same shape.
        """
        residual = x
        out = F.relu(self.bn1(self.conv1(x)), inplace=True)
        out = self.res2net(out)
        out = F.relu(self.bn2(self.conv2(out)), inplace=True)
        out = self.se(out)
        return out + residual


class AttentiveStatisticsPooling(nn.Module):
    """Attentive Statistics Pooling (ASP).

    Computes attention-weighted mean and standard deviation across the time
    axis, producing a fixed-length representation from variable-length input.

    Args:
        channels: Number of input channels.
        attention_channels: Hidden dimension of the attention network (default: 128).
    """

    def __init__(self, channels: int, attention_channels: int = 128) -> None:
        super().__init__()
        self.attention = nn.Sequential(
            nn.Conv1d(channels, attention_channels, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.Conv1d(attention_channels, channels, kernel_size=1),
            nn.Softmax(dim=2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Compute attention-weighted statistics.

        Args:
            x: (batch, channels, time)
        Returns:
            (batch, channels * 2) -- concatenation of weighted mean and std.
        """
        alpha = self.attention(x)  # (B, C, T)

        # Weighted mean
        mean = torch.sum(alpha * x, dim=2)  # (B, C)

        # Weighted standard deviation
        var = torch.sum(alpha * (x**2), dim=2) - mean**2
        std = torch.sqrt(var.clamp(min=1e-8))

        return torch.cat([mean, std], dim=1)  # (B, 2C)


class ECAPATDNN(nn.Module):
    """ECAPA-TDNN Speaker Encoder.

    Produces L2-normalized speaker embeddings from mel spectrograms.

    Args:
        input_dim: Number of mel frequency bins (default: 80).
        channels: Main channel dimension C (default: 1024).
        emb_dim: Output embedding dimension (default: 256).
        scale: Res2Net scale parameter (default: 8).
        se_bottleneck: SE module bottleneck dimension (default: 128).
        attention_channels: ASP attention hidden dim (default: 128).
    """

    def __init__(
        self,
        input_dim: int = 80,
        channels: int = 1024,
        emb_dim: int = 256,
        scale: int = 8,
        se_bottleneck: int = 128,
        attention_channels: int = 128,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.channels = channels
        self.emb_dim = emb_dim

        # Initial TDNN layer: (input_dim, T) -> (C, T)
        self.layer1 = nn.Sequential(
            nn.Conv1d(input_dim, channels, kernel_size=5, padding=2),
            nn.BatchNorm1d(channels),
            nn.ReLU(inplace=True),
        )

        # 3 SE-Res2Net blocks with increasing dilation
        self.layer2 = SERes2NetBlock(
            channels,
            kernel_size=3,
            dilation=2,
            scale=scale,
            se_bottleneck=se_bottleneck,
        )
        self.layer3 = SERes2NetBlock(
            channels,
            kernel_size=3,
            dilation=3,
            scale=scale,
            se_bottleneck=se_bottleneck,
        )
        self.layer4 = SERes2NetBlock(
            channels,
            kernel_size=3,
            dilation=4,
            scale=scale,
            se_bottleneck=se_bottleneck,
        )

        # Multi-layer Feature Aggregation (MFA):
        # Concatenate outputs from all SE-Res2Net blocks -> 1x1 conv
        self.mfa = nn.Conv1d(channels * 3, channels, kernel_size=1)

        # Attentive Statistics Pooling
        self.asp = AttentiveStatisticsPooling(
            channels, attention_channels=attention_channels
        )

        # Batch normalisation after pooling
        self.asp_bn = nn.BatchNorm1d(channels * 2)

        # Final fully-connected layer -> emb_dim
        self.fc = nn.Linear(channels * 2, emb_dim)
        self.fc_bn = nn.BatchNorm1d(emb_dim)

    def forward(self, mel: torch.Tensor) -> torch.Tensor:
        """Extract L2-normalized speaker embedding.

        Args:
            mel: (batch, n_mels, time) mel spectrogram.
        Returns:
            (batch, emb_dim) L2-normalized speaker embedding.
        """
        # Initial TDNN
        x1 = self.layer1(mel)  # (B, C, T)

        # SE-Res2Net blocks
        x2 = self.layer2(x1)  # (B, C, T)
        x3 = self.layer3(x2)  # (B, C, T)
        x4 = self.layer4(x3)  # (B, C, T)

        # Multi-layer Feature Aggregation
        x = torch.cat([x2, x3, x4], dim=1)  # (B, 3C, T)
        x = self.mfa(x)  # (B, C, T)

        # Attentive Statistics Pooling
        x = self.asp(x)  # (B, 2C)
        x = self.asp_bn(x)

        # Embedding projection
        x = self.fc(x)  # (B, emb_dim)
        x = self.fc_bn(x)

        # L2 normalisation
        x = F.normalize(x, p=2, dim=1)

        return x
