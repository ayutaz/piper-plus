"""``commons.slice_segments`` の一括切り出し。

旧実装は行ごとに ``max(0, ids_str[i])`` と ``x[i, :, a:b]`` を Python で回し、GPU の
``ids_str`` を行ごとに host へ読んでいた (1 batch に数十回の同期、RTX 5090 で
学習 thread の待ちの主因)。新実装は ``gather`` で全行を一度に切り出す。

固定する性質: 旧実装 (下の ``_reference``) と forward・backward が完全一致する
(負の開始位置は 0 に、末尾をはみ出す部分は 0 で埋める)。CUDA では host 同期なし。
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch", reason="needs torch")

from piper_train.vits.commons import rand_slice_segments, slice_segments  # noqa: E402

pytestmark = pytest.mark.unit


def _reference(x, ids_str, segment_size=4):
    """旧実装 (行ごとの Python ループ) をそのまま残した参照。"""
    ret = torch.zeros_like(x[:, :, :segment_size])
    for i in range(x.size(0)):
        idx_str = max(0, ids_str[i])
        idx_end = idx_str + segment_size
        seg = x[i, :, idx_str:idx_end]
        seg_len = seg.size(-1)
        if seg_len < segment_size:
            ret[i, :, :seg_len] = seg
        else:
            ret[i] = seg
    return ret


CASES = [
    # (T, segment, starts)  — 末尾ちょうど / はみ出し / 負 / 先頭
    (20, 5, [0, 15, 3, 7]),
    (20, 5, [16, 19, -2, 0]),
    (8, 8, [0, 0, 0, 0]),
    (8, 12, [0, 3, -1, 7]),
]


@pytest.mark.parametrize(("frames", "segment", "starts"), CASES)
@pytest.mark.parametrize("dtype", [torch.float32, torch.bfloat16])
def test_forward_and_backward_match_the_row_loop(frames, segment, starts, dtype):
    g = torch.Generator().manual_seed(0)
    base = torch.randn(len(starts), 3, frames, generator=g).to(dtype)
    ids = torch.tensor(starts, dtype=torch.long)
    # 区間長が系列長を超えると旧実装の出力幅は系列長になる (x[:, :, :segment])
    weight = torch.randn(len(starts), 3, min(segment, frames), generator=g).to(dtype)

    x_new = base.clone().requires_grad_(True)
    x_ref = base.clone().requires_grad_(True)
    out_new = slice_segments(x_new, ids, segment)
    out_ref = _reference(x_ref, ids, segment)
    assert out_new.dtype == out_ref.dtype and out_new.shape == out_ref.shape
    assert torch.equal(out_new, out_ref)
    (out_new * weight).sum().backward()
    (out_ref * weight).sum().backward()
    assert torch.equal(x_new.grad, x_ref.grad)


def test_rand_slice_segments_is_unchanged_for_the_same_rng():
    x = torch.randn(4, 3, 30)
    lengths = torch.tensor([30, 12, 25, 6])
    torch.manual_seed(5)
    out, ids = rand_slice_segments(x, lengths, 8)
    assert torch.equal(out, _reference(x, ids, 8))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_cuda_slice_does_not_synchronize():
    x = torch.randn(24, 192, 900, device="cuda", requires_grad=True)
    ids = torch.randint(0, 880, (24,), device="cuda")
    torch.cuda.synchronize()
    torch.cuda.set_sync_debug_mode("error")
    try:
        out = slice_segments(x, ids, 32)
        out.sum().backward()
    finally:
        torch.cuda.set_sync_debug_mode(0)
    torch.cuda.synchronize()
    assert torch.equal(out.detach().cpu(), _reference(x.detach().cpu(), ids.cpu(), 32))
