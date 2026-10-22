"""``discriminator_loss`` の各 scale の損失を GPU 上の tensor のまま返す。

旧実装は scale ごとに ``.item()`` で host へ読んでいた (MPD/MSD/WavLM/MRD で
1 batch 約 30 回の同期)。学習ループはこの内訳を使っていない。

固定する性質: 合計損失と各 scale の値は旧実装と同じ。内訳は勾配を持たない tensor。
CUDA では host 同期しない。
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="needs torch")

from piper_train.vits.losses import discriminator_loss  # noqa: E402

pytestmark = pytest.mark.unit


def _outputs(device="cpu"):
    g = torch.Generator().manual_seed(0)
    real = [torch.randn(4, 1, n, generator=g).to(device).requires_grad_(True) for n in (50, 33, 17)]
    fake = [torch.randn(4, 1, n, generator=g).to(device).requires_grad_(True) for n in (50, 33, 17)]
    return real, fake


def test_values_and_total_are_unchanged():
    real, fake = _outputs()
    loss, r_losses, g_losses = discriminator_loss(real, fake)
    expected_r = [torch.mean((1 - dr) ** 2) for dr in real]
    expected_g = [torch.mean(dg**2) for dg in fake]
    torch.testing.assert_close(loss, sum(r + g for r, g in zip(expected_r, expected_g, strict=True)))
    for got, want in zip(r_losses + g_losses, expected_r + expected_g, strict=True):
        assert isinstance(got, torch.Tensor) and not got.requires_grad
        assert float(got) == float(want)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_cuda_does_not_synchronize():
    real, fake = _outputs("cuda")
    torch.cuda.synchronize()
    torch.cuda.set_sync_debug_mode("error")
    try:
        loss, _, _ = discriminator_loss(real, fake)
        loss.backward()
    finally:
        torch.cuda.set_sync_debug_mode(0)
    torch.cuda.synchronize()
