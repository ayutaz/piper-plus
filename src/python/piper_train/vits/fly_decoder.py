"""FLY-TTS ConvNeXt6 decoder skeleton (AI-06).

This module is the **skeleton scaffold** for ticket AI-06 (FLY-TTS
ConvNeXt6 decoder + single-band iSTFT). It is intentionally isolated
from ``mb_istft.py``, ``models.py`` and ``lightning.py`` to avoid
conflicts with in-flight PR #222 / PR #537 (see ticket description).

Implementation plan (per AI-06):

* ``ConvNeXtBlock1d``: 1D ConvNeXt residual block consisting of
  depthwise Conv1d, channel-last LayerNorm and a 4x expand-then-project
  MLP (pwconv1 / pwconv2).
* ``FlyDecoder``: stack of 6 ``ConvNeXtBlock1d`` operating on 256
  channels, sandwiched between Conv1d ``conv_pre`` (192 -> 256) and
  ``conv_post`` (256 -> ``(n_fft // 2 + 1) * 2``). The conv_post output
  is split into magnitude / phase and fed into a fresh
  :class:`~piper_train.vits.stft_onnx.OnnxISTFT` (n_fft=1024, hop=256)
  to produce ``[B, 1, T_audio]`` audio.

Numerical / training behaviour is **out of scope** for this skeleton.
Full training, MOS validation against the FLY-TTS paper, and 7-runtime
ONNX export parity belong to AI-07 / AI-13. The accompanying unit test
stub (``test_fly_decoder.py``) and ONNX smoke script
(``scripts/smoke_fly_decoder_onnx.py``) drive TDD red -> green.

Notes
-----
* No import of ``mb_istft`` / ``models`` / ``lightning`` to preserve
  isolation from PR #222 (mb_istft refactor) and PR #537.
* Multi-speaker conditioning (``g``) is left as a TODO no-op for the
  proof-of-concept. The signature exposes ``g`` so downstream callers
  can wire it without breaking the contract once AI-07 lands.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from .stft_onnx import OnnxISTFT


__all__ = ["ConvNeXtBlock1d", "FlyDecoder"]


class ConvNeXtBlock1d(nn.Module):
    """1D ConvNeXt residual block.

    Topology (per FLY-TTS / ConvNeXt-V1)::

        x -> dwconv(Conv1d, depthwise, k=7) -> transpose(B,T,C)
          -> LayerNorm(C) -> pwconv1(Linear C->4C) -> GELU
          -> pwconv2(Linear 4C->C) -> transpose(B,C,T)
          -> residual add with input x

    Parameters
    ----------
    channels:
        Number of input / output channels. Depthwise conv preserves
        channel count.
    kernel_size:
        Depthwise Conv1d kernel size. Default ``7`` per FLY-TTS.
    expand:
        Channel expansion factor of the inverted bottleneck MLP.
        Default ``4``.
    """

    def __init__(
        self,
        channels: int,
        kernel_size: int = 7,
        expand: int = 4,
    ) -> None:
        super().__init__()
        # TODO(AI-06): construct dwconv (Conv1d groups=channels, padding=k//2)
        self.dwconv: nn.Conv1d = nn.Conv1d(
            channels,
            channels,
            kernel_size=kernel_size,
            padding=kernel_size // 2,
            groups=channels,
        )
        # TODO(AI-06): construct channel-last LayerNorm(channels)
        self.norm: nn.LayerNorm = nn.LayerNorm(channels)
        # TODO(AI-06): construct pwconv1 / pwconv2 (Linear) with expand factor
        self.pwconv1: nn.Linear = nn.Linear(channels, expand * channels)
        self.pwconv2: nn.Linear = nn.Linear(expand * channels, channels)
        self.act: nn.GELU = nn.GELU()
        self.channels: int = channels

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Apply the ConvNeXt block.

        Parameters
        ----------
        x:
            Input tensor of shape ``[B, C, T]``.

        Returns
        -------
        Tensor of identical shape ``[B, C, T]`` (residual preserved).
        """
        # TODO(AI-06): implement residual + transpose-LN-MLP-transpose
        raise NotImplementedError(
            "TODO(AI-06): ConvNeXtBlock1d.forward residual MLP path"
        )


class FlyDecoder(nn.Module):
    """FLY-TTS ConvNeXt6 decoder with single-band iSTFT head.

    Replaces HiFi-GAN / MB-iSTFT decoders with a stack of 6 ConvNeXt
    blocks operating on 256 channels, followed by a single-band iSTFT
    (n_fft=1024, hop=256). The decoder consumes posterior latents of
    shape ``[B, 192, T]`` and emits ``[B, 1, T * hop_length]`` audio.

    Parameters
    ----------
    in_channels:
        Posterior channel count. Default ``192`` (matches VITS flow).
    hidden_channels:
        ConvNeXt working channel count. Default ``256``.
    num_blocks:
        Number of ``ConvNeXtBlock1d`` stages. Default ``6``.
    kernel_size:
        Depthwise kernel size in each ConvNeXt block. Default ``7``.
    n_fft:
        FFT size for the iSTFT head. Default ``1024``.
    hop_length:
        Hop length for the iSTFT head. Default ``256``.
    """

    def __init__(
        self,
        in_channels: int = 192,
        hidden_channels: int = 256,
        num_blocks: int = 6,
        kernel_size: int = 7,
        n_fft: int = 1024,
        hop_length: int = 256,
    ) -> None:
        super().__init__()
        self.in_channels: int = in_channels
        self.hidden_channels: int = hidden_channels
        self.num_blocks: int = num_blocks
        self.n_fft: int = n_fft
        self.hop_length: int = hop_length

        # TODO(AI-06): construct conv_pre Conv1d(in_channels -> hidden_channels, k=7, pad=3)
        self.conv_pre: nn.Conv1d = nn.Conv1d(
            in_channels,
            hidden_channels,
            kernel_size=kernel_size,
            padding=kernel_size // 2,
        )

        # TODO(AI-06): build ModuleList of ConvNeXtBlock1d x num_blocks
        self.blocks: nn.ModuleList = nn.ModuleList(
            [
                ConvNeXtBlock1d(hidden_channels, kernel_size=kernel_size)
                for _ in range(num_blocks)
            ]
        )

        # conv_post emits (n_fft//2+1) magnitude + (n_fft//2+1) phase channels
        out_channels = (n_fft // 2 + 1) * 2
        # TODO(AI-06): construct conv_post Conv1d(hidden -> 2*(n_fft//2+1), k=7, pad=3)
        self.conv_post: nn.Conv1d = nn.Conv1d(
            hidden_channels,
            out_channels,
            kernel_size=kernel_size,
            padding=kernel_size // 2,
        )

        # Fresh OnnxISTFT instance (NOT shared with mb_istft.py).
        # TODO(AI-06): wire single-band iSTFT (n_fft=1024, hop=256)
        self.istft: OnnxISTFT = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)

        # TODO(AI-06): multi-speaker conditioning placeholder. AI-07 wires
        # in a Linear(gin_channels, hidden_channels) projection added to
        # conv_pre output. For PoC we keep this as a no-op.
        self._g_proj: nn.Module | None = None

    def forward(
        self,
        x: torch.Tensor,
        g: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Run the FLY-TTS decoder.

        Parameters
        ----------
        x:
            Latent tensor of shape ``[B, in_channels, T]``.
        g:
            Optional global conditioning of shape ``[B, gin_channels, 1]``.
            Currently a no-op (see ``_g_proj`` TODO).

        Returns
        -------
        Tensor of shape ``[B, 1, T * hop_length]`` audio waveform.
        """
        # TODO(AI-06): conv_pre -> (optional g) -> blocks -> conv_post
        # TODO(AI-06): split into magnitude / phase, apply exp(clamp(max=10)) / sin
        # TODO(AI-06): feed through self.istft -> [B,1,T_audio]
        raise NotImplementedError(
            "TODO(AI-06): FlyDecoder.forward conv_pre/blocks/conv_post/iSTFT chain"
        )

    # ------------------------------------------------------------------
    # Static helpers (op-audit aids for tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _split_mag_phase(
        spec: torch.Tensor, cutoff: int
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Split conv_post output into magnitude / phase halves.

        Helper exposed for AI-06 unit tests; uses :func:`torch.split`
        so the operator graph stays ONNX-friendly (no Conv2d / STFT).

        Parameters
        ----------
        spec:
            Tensor of shape ``[B, 2*cutoff, T]``.
        cutoff:
            ``n_fft // 2 + 1``.

        Returns
        -------
        Tuple of ``(magnitude, phase)``, each ``[B, cutoff, T]``.
        """
        # TODO(AI-06): implement split helper (kept here so tests can
        # exercise the op-audit contract without instantiating the full
        # decoder).
        del spec, cutoff  # silence ARG004 until the body lands
        _ = F  # keep torch.nn.functional import live for AI-07 wiring
        raise NotImplementedError("TODO(AI-06): _split_mag_phase helper for op-audit")
