"""Tests for MultiResolutionSTFTLoss and STFTLoss.

Verifies scalar output, zero-loss on identical inputs, 2D input handling,
and buffer registration of piper_train.vits.stft_loss.
"""

import pytest

torch = pytest.importorskip("torch", reason="torch required")


@pytest.mark.unit
def test_multi_resolution_stft_loss_scalar():
    """Output is a scalar with positive value for different inputs."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    loss_fn = MultiResolutionSTFTLoss()
    x = torch.randn(2, 4, 2048)  # [B, subbands, T]
    y = torch.randn(2, 4, 2048)
    loss = loss_fn(x, y)
    assert loss.dim() == 0  # scalar
    assert loss.item() > 0


@pytest.mark.unit
def test_multi_resolution_stft_loss_zero():
    """Identical inputs produce near-zero loss."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    loss_fn = MultiResolutionSTFTLoss()
    x = torch.randn(2, 4, 2048)
    loss = loss_fn(x, x)
    assert loss.item() < 1e-5  # spectral convergence ~ 0, log mag ~ 0


@pytest.mark.unit
def test_multi_resolution_stft_loss_2d_input():
    """2D input (B*subbands, T) is handled correctly."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    loss_fn = MultiResolutionSTFTLoss()
    x = torch.randn(8, 2048)  # B*4 = 8
    y = torch.randn(8, 2048)
    loss = loss_fn(x, y)
    assert loss.dim() == 0


@pytest.mark.unit
def test_stft_loss_window_device():
    """Window tensor is managed as a registered buffer."""
    from piper_train.vits.stft_loss import STFTLoss

    loss = STFTLoss(171, 10, 60)
    buffers = dict(loss.named_buffers())
    assert "window" in buffers


@pytest.mark.unit
def test_multi_resolution_stft_loss_num_resolutions():
    """MultiResolutionSTFTLoss has exactly 3 resolution levels."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    loss_fn = MultiResolutionSTFTLoss()
    assert len(loss_fn.stft_losses) == 3


@pytest.mark.unit
def test_stft_loss_gradient_flow():
    """STFT loss supports backward pass."""
    from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

    loss_fn = MultiResolutionSTFTLoss()
    x = torch.randn(2, 4, 2048, requires_grad=True)
    y = torch.randn(2, 4, 2048)
    loss = loss_fn(x, y)
    loss.backward()
    assert x.grad is not None
    assert x.grad.shape == x.shape


@pytest.mark.unit
def test_spectral_convergence_loss_direct():
    """SpectralConvergenceLoss returns near-zero for identical inputs."""
    from piper_train.vits.stft_loss import SpectralConvergenceLoss

    loss_fn = SpectralConvergenceLoss()
    x = torch.randn(4, 100).abs()  # magnitude
    loss = loss_fn(x, x)
    assert loss.item() < 1e-6


@pytest.mark.unit
def test_spectral_convergence_loss_zero_target():
    """SpectralConvergenceLoss handles near-zero target without NaN."""
    from piper_train.vits.stft_loss import SpectralConvergenceLoss

    loss_fn = SpectralConvergenceLoss()
    x = torch.randn(4, 100).abs()
    y = torch.zeros(4, 100)
    loss = loss_fn(x, y)
    assert not torch.isnan(loss)
    assert not torch.isinf(loss)


@pytest.mark.unit
def test_log_stft_magnitude_loss_direct():
    """LogSTFTMagnitudeLoss returns near-zero for identical inputs."""
    from piper_train.vits.stft_loss import LogSTFTMagnitudeLoss

    loss_fn = LogSTFTMagnitudeLoss()
    x = torch.randn(4, 100).abs()
    loss = loss_fn(x, x)
    assert loss.item() < 1e-6


@pytest.mark.unit
def test_stft_loss_3d_input():
    """STFTLoss handles (B, 1, T) 3D input."""
    from piper_train.vits.stft_loss import STFTLoss

    loss_fn = STFTLoss(384, 30, 150)
    x = torch.randn(2, 1, 2048)
    y = torch.randn(2, 1, 2048)
    loss = loss_fn(x, y)
    assert loss.dim() == 0
    assert loss.item() > 0
