"""MB-iSTFT-VITS2 decoder components: PQMF and MBiSTFTGenerator.

Implements the Multi-Band inverse STFT decoder from:
  Kawamura et al., "Lightweight and High-Fidelity End-to-End Text-to-Speech
  with Multi-Band Generation and Inverse Short-Time Fourier Transform",
  ICASSP 2023 (arXiv:2210.15975)
"""

import math

import numpy as np
import torch
from torch import nn
from torch.nn import Conv1d, ConvTranspose1d, functional as F
from torch.nn.utils import remove_weight_norm, weight_norm

from .commons import init_weights
from .modules import ResBlock1, ResBlock2
from .stft_onnx import OnnxISTFT


LRELU_SLOPE = 0.1


class PQMF(nn.Module):
    """Pseudo Quadrature Mirror Filterbank.

    Decomposes a fullband signal into *subbands* equal-width sub-band signals
    (analysis) and reconstructs the fullband signal from sub-bands (synthesis).

    All filter tensors are registered as buffers so that they follow the
    module's device automatically (no ``.cuda()`` hard-coding).
    """

    def __init__(
        self,
        subbands: int = 4,
        taps: int = 62,
        cutoff_ratio: float = 0.15,
        beta: float = 9.0,
    ):
        super().__init__()
        self.subbands = subbands
        self.taps = taps

        # --- Prototype lowpass filter: Kaiser-windowed sinc ---
        filter_length = taps + 1  # 63
        omega_c = np.pi * cutoff_ratio
        t = np.arange(-(taps // 2), taps // 2 + 1, dtype=np.float64)

        # sinc(omega_c * t / pi) * omega_c / pi  (normalised cutoff)
        with np.errstate(divide="ignore", invalid="ignore"):
            sinc = np.where(t == 0, omega_c / np.pi, np.sin(omega_c * t) / (np.pi * t))
        window = np.kaiser(filter_length, beta)
        prototype = sinc * window

        # --- Cosine-modulated analysis filter bank ---
        # h_k[n] = 2 * prototype[n] * cos((2k+1)*pi/(2M) * (n - M/2))
        # where M = subbands, n in [0, filter_length-1]
        analysis_filter = np.zeros((subbands, 1, filter_length), dtype=np.float64)
        for k in range(subbands):
            for n in range(filter_length):
                analysis_filter[k, 0, n] = (
                    2.0
                    * prototype[n]
                    * np.cos((2 * k + 1) * np.pi / (2 * subbands) * (n - subbands / 2))
                )

        # Synthesis filter: time-reversed analysis filter
        synthesis_filter = analysis_filter[:, :, ::-1].copy()

        # Register as buffers (float32)
        self.register_buffer(
            "analysis_filter", torch.from_numpy(analysis_filter).float()
        )
        self.register_buffer(
            "synthesis_filter", torch.from_numpy(synthesis_filter).float()
        )

        # Up/down-sampling identity filter: eye(subbands) reshaped for conv1d
        updown = np.eye(subbands, dtype=np.float32).reshape(subbands, 1, subbands)
        self.register_buffer("updown_filter", torch.from_numpy(updown))

        # Padding
        self.pad = nn.ConstantPad1d(taps // 2, 0.0)

    def analysis(self, x: torch.Tensor) -> torch.Tensor:
        """Decompose fullband signal into sub-band signals.

        Args:
            x: Fullband waveform ``[B, 1, T]``.

        Returns:
            Sub-band signals ``[B, subbands, T // subbands]``.
        """
        x = self.pad(x)  # [B, 1, T + taps]
        x = F.conv1d(x, self.analysis_filter)  # [B, subbands, T]
        # Polyphase downsampling: stride-decimate each subband independently
        # updown_filter: [subbands, 1, subbands] -- groups=subbands
        # Input x: [B, subbands, T] -> output: [B, subbands, T // subbands]
        x = F.conv1d(
            x,
            self.updown_filter,
            stride=self.subbands,
            groups=self.subbands,
        )
        return x

    def synthesis(self, x: torch.Tensor) -> torch.Tensor:
        """Reconstruct fullband signal from sub-band signals.

        Args:
            x: Sub-band signals ``[B, subbands, T_sub]``.

        Returns:
            Fullband waveform ``[B, 1, T]`` where ``T = T_sub * subbands``.
        """
        # Upsample: insert zeros between samples
        # updown_filter: [subbands, 1, subbands] -- groups=subbands conv_transpose1d
        # Input x: [B, subbands, T_sub] -> output: [B, subbands, T_sub * subbands]
        x = F.conv_transpose1d(
            x,
            self.updown_filter * self.subbands,
            stride=self.subbands,
            groups=self.subbands,
        )
        x = self.pad(x)  # [B, subbands, T + taps]
        # Synthesis filter: (1, subbands, filter_length)
        x = F.conv1d(x, self.synthesis_filter.permute(1, 0, 2))  # [B, 1, T]
        return x


class MBiSTFTGenerator(nn.Module):
    """Multi-Band inverse STFT Generator.

    The sole VITS decoder. Generates fullband audio from latents via two
    transposed-convolution upsample stages followed by sub-band iSTFT and
    PQMF synthesis. Total upsample factor is
    ``upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x``.
    """

    def __init__(
        self,
        initial_channel: int,
        resblock: str | None,
        resblock_kernel_sizes: tuple[int, ...],
        resblock_dilation_sizes: tuple[tuple[int, ...], ...],
        upsample_rates: tuple[int, ...] = (4, 4),
        upsample_initial_channel: int = 256,
        upsample_kernel_sizes: tuple[int, ...] = (16, 16),
        gin_channels: int = 0,
        n_fft: int = 16,
        hop_length: int = 4,
        subbands: int = 4,
        pqmf: "PQMF | None" = None,
    ):
        super().__init__()
        self.num_kernels = len(resblock_kernel_sizes)
        self.num_upsamples = len(upsample_rates)
        self.subbands = subbands
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.onnx_export_mode = False

        # --- conv_pre ---
        self.conv_pre = weight_norm(
            Conv1d(initial_channel, upsample_initial_channel, 7, 1, padding=3)
        )

        # --- ResBlock selection ---
        resblock_module = ResBlock1 if resblock == "1" else ResBlock2

        # --- Upsampling layers (2 stages: 4x, 4x = 16x total) ---
        self.ups = nn.ModuleList()
        for i, (u, k) in enumerate(
            zip(upsample_rates, upsample_kernel_sizes, strict=False)
        ):
            self.ups.append(
                weight_norm(
                    ConvTranspose1d(
                        upsample_initial_channel // (2**i),
                        upsample_initial_channel // (2 ** (i + 1)),
                        k,
                        u,
                        padding=(k - u) // 2,
                    )
                )
            )

        # --- ResBlocks after each upsampling stage ---
        self.resblocks = nn.ModuleList()
        for i in range(len(self.ups)):
            ch = upsample_initial_channel // (2 ** (i + 1))
            for _j, (k, d) in enumerate(
                zip(resblock_kernel_sizes, resblock_dilation_sizes, strict=False)
            ):
                self.resblocks.append(resblock_module(ch, k, d))

        # --- Sub-band convolution (no weight_norm) ---
        post_in_channels = upsample_initial_channel // (2 ** len(upsample_rates))
        self.subband_conv_post = Conv1d(
            post_in_channels, subbands * (n_fft + 2), 7, padding=3
        )

        # --- iSTFT ---
        self.istft = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)

        # --- PQMF (shared instance or create new) ---
        self.pqmf = pqmf if pqmf is not None else PQMF(subbands=subbands)

        # --- Weight initialisation (ups only) ---
        self.ups.apply(init_weights)

        # --- Speaker conditioning ---
        if gin_channels != 0:
            self.cond = nn.Conv1d(gin_channels, upsample_initial_channel, 1)

    def forward(
        self, x: torch.Tensor, g: torch.Tensor | None = None
    ) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """Generate waveform from latent representation.

        Args:
            x: Latent ``[B, initial_channel, T_frames]``.
            g: Speaker embedding ``[B, gin_channels, 1]`` (optional).

        Returns:
            If ``onnx_export_mode`` is False (training):
                ``(fullband, subbands)`` where fullband is ``[B, 1, T]``
                and subbands is ``[B, subbands, T_sub]``.
            If ``onnx_export_mode`` is True (ONNX inference):
                ``fullband`` only ``[B, 1, T]``.
        """
        x = self.conv_pre(x)
        if g is not None:
            x = x + self.cond(g)

        for i, up in enumerate(self.ups):
            x = F.leaky_relu(x, LRELU_SLOPE)
            x = up(x)
            xs = None
            for j, resblock in enumerate(self.resblocks):
                index = j - (i * self.num_kernels)
                if index == 0:
                    xs = resblock(x)
                elif (index > 0) and (index < self.num_kernels):
                    xs = xs + resblock(x)
            x = xs / self.num_kernels

        x = F.leaky_relu(x, LRELU_SLOPE)
        x = self.subband_conv_post(x)  # [B, subbands * (n_fft + 2), T_frames]

        B = x.size(0)
        T_frames = x.size(-1)
        n_half = self.n_fft // 2 + 1  # 9

        # Reshape: [B, subbands, n_fft+2, T_frames]
        x = x.reshape(B, self.subbands, self.n_fft + 2, T_frames)

        # Magnitude (positive via exp) and phase (bounded to [-pi, pi] via sin)
        mag = torch.exp(x[:, :, :n_half, :])  # [B, subbands, 9, T_frames]
        phase = torch.sin(x[:, :, n_half:, :]) * math.pi  # [B, subbands, 9, T_frames]

        # Flatten subbands into batch for iSTFT (expects [B, n_fft//2+1, T])
        mag = mag.reshape(B * self.subbands, n_half, T_frames)
        phase = phase.reshape(B * self.subbands, n_half, T_frames)
        sub_wav = self.istft(mag, phase)  # [B*subbands, 1, T_sub_raw]
        subbands_signal = sub_wav.reshape(
            B, self.subbands, -1
        )  # [B, subbands, T_sub_raw]

        # Trim iSTFT output to expected length.
        # conv_transpose1d produces (T-1)*stride + kernel extra samples;
        # trim to T_frames * hop_length so PQMF synthesis yields exact segment_size.
        expected_sub_T = T_frames * self.hop_length
        subbands_signal = subbands_signal[..., :expected_sub_T]  # [B, subbands, T_sub]

        # PQMF synthesis: [B, subbands, T_sub] -> [B, 1, T]
        fullband = self.pqmf.synthesis(subbands_signal)

        if self.onnx_export_mode:
            return fullband
        return fullband, subbands_signal

    def remove_weight_norm(self):
        """Remove weight normalization from conv_pre and all upsampling layers.

        Called before ONNX export. ``subband_conv_post`` is excluded
        (no weight_norm was applied to it).
        """
        print("Removing weight norm...")
        remove_weight_norm(self.conv_pre)
        for l in self.ups:  # noqa: E741
            remove_weight_norm(l)
        for l in self.resblocks:  # noqa: E741
            l.remove_weight_norm()
