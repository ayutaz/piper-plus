"""``modules.Flip`` の logdet を学習 device 上で直接作る。

旧実装は ``torch.zeros(B).type_as(x)`` で CPU に作ってから GPU へコピーしており、
flow の Flip ごとに host と同期していた (1 batch 12 回)。

固定する性質: 出力と logdet (値・dtype・device) は旧実装と同じ。CUDA では同期しない。
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="needs torch")

from piper_train.vits.modules import Flip  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
def test_output_and_logdet_match_the_old_form(dtype):
    x = torch.randn(3, 4, 7).to(dtype)
    y, logdet = Flip()(x)
    assert torch.equal(y, torch.flip(x, [1]))
    expected = torch.zeros(x.size(0)).type_as(x)
    assert logdet.dtype == expected.dtype and logdet.device == expected.device
    assert torch.equal(logdet, expected)
    assert torch.equal(Flip()(y, reverse=True), x)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_cuda_does_not_synchronize():
    x = torch.randn(24, 2, 300, device="cuda")
    torch.cuda.synchronize()
    torch.cuda.set_sync_debug_mode("error")
    try:
        _, logdet = Flip()(x)
    finally:
        torch.cuda.set_sync_debug_mode(0)
    assert logdet.device == x.device
