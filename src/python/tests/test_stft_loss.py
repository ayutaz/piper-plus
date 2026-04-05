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
    assert loss.item() < 0.1  # spectral convergence ~ 0, log mag ~ 0


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
