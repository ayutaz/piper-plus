"""ONNX-compatible iSTFT using conv_transpose1d.

ONNX lacks a native iSTFT operator, so we pre-compute the DFT inverse basis
and perform the inverse transform via ``F.conv_transpose1d``.  All operations
are expressible with Conv1d / ConvTranspose1d (ONNX opset 15).

The inverse basis absorbs the Hann window and OLA normalisation so that no
post-processing is needed (center=False, no trimming).
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn


class OnnxISTFT(nn.Module):
    """Inverse Short-Time Fourier Transform implemented with ``conv_transpose1d``.

    Parameters
    ----------
    n_fft : int
        FFT size (default ``16``).
    hop_length : int
        Hop size between frames (default ``4``).
    """

    def __init__(self, n_fft: int = 16, hop_length: int = 4) -> None:
        super().__init__()
        inverse_basis = self._build_inverse_basis(n_fft, hop_length)
        # shape: (n_fft + 2, 1, n_fft) e.g. (18, 1, 16)
        self.register_buffer("inverse_basis", inverse_basis)
        self.hop_length = hop_length
        self.n_fft = n_fft

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, magnitude: torch.Tensor, phase: torch.Tensor) -> torch.Tensor:
        """Reconstruct a waveform from magnitude and phase spectrograms.

        Parameters
        ----------
        magnitude : Tensor
            ``(B, n_fft//2+1, T)`` magnitude spectrogram.
        phase : Tensor
            ``(B, n_fft//2+1, T)`` phase spectrogram.

        Returns
        -------
        Tensor
            ``(B, 1, T_out)`` reconstructed waveform.
        """
        real = magnitude * torch.cos(phase)  # (B, n_fft//2+1, T)
        imag = magnitude * torch.sin(phase)  # (B, n_fft//2+1, T)
        combined = torch.cat([real, imag], dim=1)  # (B, n_fft+2, T)
        waveform = F.conv_transpose1d(
            combined, self.inverse_basis, stride=self.hop_length
        )  # (B, 1, T_out)
        return waveform

    # ------------------------------------------------------------------
    # Basis construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_inverse_basis(n_fft: int, hop_length: int) -> torch.Tensor:
        """Build the inverse DFT basis with Hann window and OLA normalisation.

        The returned tensor has shape ``(n_fft + 2, 1, n_fft)`` and is ready
        for use as a ``conv_transpose1d`` weight.

        Construction
        ------------
        1. Build the one-sided iDFT synthesis matrix *S* of shape
           ``(n_fft, 2 * cutoff)`` that maps ``[Re(X); Im(X)]`` back to a
           time-domain frame.
        2. Multiply each row by the periodic Hann window (synthesis window).
        3. Divide by the window-sum-of-squares (WSS) so that overlap-add
           recovers the original signal without further normalisation.
        4. Transpose to ``(2 * cutoff, n_fft)`` and insert a unit
           ``out_channels`` dimension for ``conv_transpose1d``.
        """
        cutoff = n_fft // 2 + 1  # number of one-sided frequency bins

        # -- 1. One-sided iDFT synthesis matrix --
        # x[n] = (1/N) * sum_{k=0}^{N-1} X[k] * exp(j*2*pi*k*n/N)
        # Expanded for real signal using one-sided spectrum [Re(X); Im(X)]:
        #   DC  (k=0)          : coefficient 1/N on Re, 0 on Im
        #   Nyquist (k=N/2)    : coefficient cos(pi*n)/N on Re, -sin(pi*n)/N on Im
        #   Interior (1<=k<N/2): coefficient 2*cos(..)/N on Re, -2*sin(..)/N on Im
        n_idx = np.arange(n_fft)
        k_idx = np.arange(cutoff)
        angle = 2.0 * np.pi * np.outer(n_idx, k_idx) / n_fft  # (n_fft, cutoff)
        cos_table = np.cos(angle)
        sin_table = np.sin(angle)

        S_re = np.zeros((n_fft, cutoff))
        S_im = np.zeros((n_fft, cutoff))

        # DC bin (k=0)
        S_re[:, 0] = 1.0 / n_fft

        # Nyquist bin (k=N/2)
        S_re[:, cutoff - 1] = cos_table[:, cutoff - 1] / n_fft
        S_im[:, cutoff - 1] = -sin_table[:, cutoff - 1] / n_fft

        # Interior bins (1 <= k < N/2) -- factor of 2 for hermitian symmetry
        for ki in range(1, cutoff - 1):
            S_re[:, ki] = 2.0 * cos_table[:, ki] / n_fft
            S_im[:, ki] = -2.0 * sin_table[:, ki] / n_fft

        # S maps [Re(X_0..cutoff); Im(X_0..cutoff)] -> x[0..n_fft]
        S = np.hstack([S_re, S_im])  # (n_fft, 2*cutoff)

        # -- 2. Periodic Hann window --
        # np.hanning(N+1)[:N] == torch.hann_window(N, periodic=True)
        window = np.hanning(n_fft + 1)[:n_fft]

        # -- 3. Window-sum-of-squares (WSS) for OLA normalisation --
        # At steady state every sample receives n_fft/hop_length overlapping
        # frames each weighted by window^2.  The constant WSS value lets us
        # absorb the normalisation as a scalar divisor.
        wss = np.sum(window**2) * hop_length / n_fft

        # Apply synthesis window and WSS normalisation row-wise
        inverse_basis = S * (window[:, np.newaxis] / wss)  # (n_fft, 2*cutoff)

        # -- 4. Reshape for conv_transpose1d --
        # conv_transpose1d weight: (in_channels, out_channels/groups, kernel_size)
        # input: (B, 2*cutoff, T)  ->  output: (B, 1, T_out)
        # weight[c, 0, n] reconstructs sample n from channel c
        inverse_basis = inverse_basis.T[:, np.newaxis, :]  # (2*cutoff, 1, n_fft)

        return torch.FloatTensor(inverse_basis)
