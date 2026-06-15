"""TDD unit-test stub for the FLY-TTS ConvNeXt6 decoder (AI-06).

These tests pin the acceptance criteria from ticket AI-06:

* shape / param-count contract on ``ConvNeXtBlock1d`` and ``FlyDecoder``;
* iSTFT upsampling ratio ``hop_length=256`` so ``T_audio == T_input * 256``;
* op-audit: no ``nn.Conv2d`` / ``nn.ConvTranspose2d`` / PQMF modules;
* determinism under ``torch.manual_seed(0)``;
* gradient flow through ``conv_pre``.

Each test is currently ``@pytest.mark.skip`` so the suite stays green
while AI-06 implementation lands; the skip markers are removed in the
follow-up PR that wires up ``FlyDecoder.forward`` (red -> green TDD).
"""

from __future__ import annotations

import pytest


torch = pytest.importorskip("torch")

from piper_train.vits.fly_decoder import (  # noqa: E402 (import after skip)
    ConvNeXtBlock1d,
    FlyDecoder,
)


# --------------------------------------------------------------------------- #
# ConvNeXtBlock1d                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_convnext_block_residual_shape() -> None:
    """ConvNeXtBlock1d preserves ``[B, C, T]`` shape via residual path."""
    block = ConvNeXtBlock1d(channels=256, kernel_size=7)
    x = torch.randn(2, 256, 50)
    y = block(x)
    assert y.shape == x.shape


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_convnext_block_residual_finite() -> None:
    """Residual output is finite (no NaN / Inf) for unit-variance input."""
    block = ConvNeXtBlock1d(channels=256, kernel_size=7)
    x = torch.randn(2, 256, 50)
    y = block(x)
    assert torch.isfinite(y).all()


# --------------------------------------------------------------------------- #
# FlyDecoder                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_output_shape() -> None:
    """``FlyDecoder`` emits ``[B, 1, T_input * hop_length]`` audio."""
    decoder = FlyDecoder(
        in_channels=192,
        hidden_channels=256,
        num_blocks=6,
        n_fft=1024,
        hop_length=256,
    )
    x = torch.randn(1, 192, 50)
    audio = decoder(x)
    assert audio.shape[0] == 1
    assert audio.shape[1] == 1
    assert audio.shape[2] == 50 * 256, (
        f"expected T_audio == T_input * hop_length, got {audio.shape[2]}"
    )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_params_count() -> None:
    """Parameter count sits in the FLY-TTS-paper range ``0.58e6 .. 0.68e6``."""
    decoder = FlyDecoder(
        in_channels=192,
        hidden_channels=256,
        num_blocks=6,
        n_fft=1024,
        hop_length=256,
    )
    n_params = sum(p.numel() for p in decoder.parameters() if p.requires_grad)
    assert 0.58e6 <= n_params <= 0.68e6, (
        f"FlyDecoder param count {n_params} outside [0.58e6, 0.68e6]"
    )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_no_2d_op() -> None:
    """Op-audit: no 2D Conv / ConvTranspose anywhere in the module tree."""
    decoder = FlyDecoder()
    for module in decoder.modules():
        assert not isinstance(module, torch.nn.Conv2d), (
            f"unexpected Conv2d module: {module}"
        )
        assert not isinstance(module, torch.nn.ConvTranspose2d), (
            f"unexpected ConvTranspose2d module: {module}"
        )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_no_pqmf() -> None:
    """Op-audit: PQMF must not appear (single-band iSTFT only)."""
    decoder = FlyDecoder()
    for module in decoder.modules():
        assert "PQMF" not in type(module).__name__, (
            f"unexpected PQMF module: {type(module).__name__}"
        )


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_forward_deterministic() -> None:
    """Same seed + same input -> bit-for-bit equal output (eval mode)."""
    torch.manual_seed(0)
    decoder_a = FlyDecoder().eval()
    torch.manual_seed(0)
    decoder_b = FlyDecoder().eval()
    x = torch.randn(1, 192, 50)
    with torch.no_grad():
        y_a = decoder_a(x)
        y_b = decoder_b(x)
    assert torch.allclose(y_a, y_b, atol=0.0)


@pytest.mark.skip(reason="awaiting AI-06 implementation")
def test_fly_decoder_gradient_flow() -> None:
    """Backward pass reaches ``conv_pre.weight`` with finite gradients."""
    decoder = FlyDecoder()
    x = torch.randn(1, 192, 50, requires_grad=False)
    audio = decoder(x)
    loss = audio.pow(2).mean()
    loss.backward()
    grad = decoder.conv_pre.weight.grad
    assert grad is not None, "conv_pre.weight.grad missing"
    assert torch.isfinite(grad).all(), "conv_pre.weight.grad contains NaN/Inf"
