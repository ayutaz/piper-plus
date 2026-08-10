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


@pytest.mark.unit
class TestFullBandSTFTLoss:
    """v9: full-band 線形周波数 MR-STFT loss の配線 (--c-full-stft)。

    mel L1 の高域粗さ (数百 Hz 幅 bin) を補う fullband 監督
    (docs/design/zero-shot-noise-root-cause-pqmf.md §3 副次要因 1)。
    """

    def test_fullband_config_finite_and_positive(self):
        """v9 デフォルト解像度 (512/1024/2048) で fullband [B,1,T] が通る。"""
        from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

        loss_fn = MultiResolutionSTFTLoss(
            fft_sizes=(512, 1024, 2048),
            hop_sizes=(128, 256, 512),
            win_sizes=(512, 1024, 2048),
        )
        x = torch.randn(2, 1, 16384)
        y = torch.randn(2, 1, 16384)
        loss = loss_fn(x, y)
        assert torch.isfinite(loss)
        assert loss.item() > 0

    def test_identical_inputs_near_zero(self):
        from piper_train.vits.stft_loss import MultiResolutionSTFTLoss

        loss_fn = MultiResolutionSTFTLoss(
            fft_sizes=(512, 1024, 2048),
            hop_sizes=(128, 256, 512),
            win_sizes=(512, 1024, 2048),
        )
        x = torch.randn(1, 1, 16384)
        assert loss_fn(x, x).item() < 1e-5

    def test_cli_advertises_c_full_stft(self):
        from piper_train.__main__ import create_parser

        parser = create_parser()
        args = parser.parse_args(
            ["--dataset-dir", "/tmp/x", "--batch-size", "1", "--c-full-stft", "0.5"]
        )
        assert args.c_full_stft == 0.5

    def test_c_full_stft_default_off(self):
        from piper_train.__main__ import create_parser

        parser = create_parser()
        args = parser.parse_args(["--dataset-dir", "/tmp/x", "--batch-size", "1"])
        assert args.c_full_stft == 0.0
