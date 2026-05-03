"""Tests for OnnxISTFT.

Verifies STFT/iSTFT round-trip accuracy, inverse_basis shape,
output shape, and buffer registration of piper_train.vits.stft_onnx.OnnxISTFT.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


@pytest.mark.unit
def test_onnx_istft_roundtrip():
    """STFT -> OnnxISTFT round-trip matches the original signal."""
    from piper_train.vits.stft_onnx import OnnxISTFT

    n_fft = 16
    hop_length = 4
    istft = OnnxISTFT(n_fft=n_fft, hop_length=hop_length)

    # Test signal
    x = torch.randn(1, 1, 256)  # short signal
    x_2d = x.squeeze(0)  # [1, 256]

    # Forward STFT (PyTorch, center=False to match OnnxISTFT)
    window = torch.hann_window(n_fft, periodic=True)
    stft_out = torch.stft(
        x_2d.squeeze(0),
        n_fft,
        hop_length,
        n_fft,
        window,
        center=False,
        return_complex=True,
    )
    mag = torch.abs(stft_out).unsqueeze(0)  # [1, 9, T]
    phase = torch.angle(stft_out).unsqueeze(0)

    # iSTFT
    x_hat = istft(mag, phase)  # [1, 1, T_out]

    # Compare in steady-state region (exclude edges)
    trim = n_fft
    x_trimmed = x[..., trim:-trim]
    x_hat_trimmed = x_hat[..., trim : trim + x_trimmed.shape[-1]]
    error = torch.max(torch.abs(x_trimmed - x_hat_trimmed))
    assert error < 1e-4, f"Round-trip error {error:.2e} > 1e-4"


@pytest.mark.unit
def test_onnx_istft_inverse_basis_shape():
    """inverse_basis shape is (n_fft+2, 1, n_fft) = (18, 1, 16)."""
    from piper_train.vits.stft_onnx import OnnxISTFT

    istft = OnnxISTFT(n_fft=16, hop_length=4)
    assert istft.inverse_basis.shape == (18, 1, 16)


@pytest.mark.unit
def test_onnx_istft_output_shape():
    """Output shape matches expected T_out = (T_frames - 1) * hop + n_fft."""
    from piper_train.vits.stft_onnx import OnnxISTFT

    istft = OnnxISTFT(n_fft=16, hop_length=4)
    mag = torch.randn(2, 9, 512).abs()  # [B, n_fft//2+1, T_frames]
    phase = torch.randn(2, 9, 512)
    out = istft(mag, phase)
    assert out.shape[0] == 2
    assert out.shape[1] == 1
    # T_out = (T_frames - 1) * hop_length + n_fft = 511 * 4 + 16 = 2060
    assert out.shape[2] == 2060


@pytest.mark.unit
def test_onnx_istft_buffer_registered():
    """inverse_basis is a registered buffer with no trainable parameters."""
    from piper_train.vits.stft_onnx import OnnxISTFT

    istft = OnnxISTFT()
    buffers = dict(istft.named_buffers())
    assert "inverse_basis" in buffers
    assert len(list(istft.parameters())) == 0
