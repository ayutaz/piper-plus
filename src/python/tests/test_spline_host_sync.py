"""``unconstrained_rational_quadratic_spline`` を bool mask の添字なしで計算する。

旧実装は ``outputs[mask] = ...`` / ``inputs[mask]`` で区間内外を振り分けていた。
bool mask の添字は要素数を host で数える (``nonzero``) ため、forward と backward の
それぞれで GPU と同期する (確率的 duration predictor の flow で 1 batch に数十回)。
新実装は全要素を区間内として計算し (区間外の入力は 0 に置き換えて NaN を作らない)、
``torch.where`` で選ぶ。

固定する性質: 旧実装 (下の ``_reference``) と出力・logabsdet・各入力への勾配が一致する。
CUDA では forward・backward とも host 同期しない。
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="needs torch")
from torch.nn import functional as F  # noqa: E402

from piper_train.vits.transforms import (  # noqa: E402
    DEFAULT_MIN_BIN_HEIGHT,
    DEFAULT_MIN_BIN_WIDTH,
    DEFAULT_MIN_DERIVATIVE,
    rational_quadratic_spline,
    unconstrained_rational_quadratic_spline,
)

pytestmark = pytest.mark.unit


def _reference(
    inputs,
    unnormalized_widths,
    unnormalized_heights,
    unnormalized_derivatives,
    inverse=False,
    tails="linear",
    tail_bound=1.0,
    min_bin_width=DEFAULT_MIN_BIN_WIDTH,
    min_bin_height=DEFAULT_MIN_BIN_HEIGHT,
    min_derivative=DEFAULT_MIN_DERIVATIVE,
):
    """旧実装 (bool mask の添字) をそのまま残した参照。"""
    inside_interval_mask = (inputs >= -tail_bound) & (inputs <= tail_bound)
    outside_interval_mask = ~inside_interval_mask
    outputs = torch.zeros_like(inputs)
    logabsdet = torch.zeros_like(inputs)
    unnormalized_derivatives = F.pad(unnormalized_derivatives, pad=(1, 1))
    constant = np.log(np.exp(1 - min_derivative) - 1)
    unnormalized_derivatives[..., 0] = constant
    unnormalized_derivatives[..., unnormalized_derivatives.size(-1) - 1] = constant
    outputs[outside_interval_mask] = inputs[outside_interval_mask]
    logabsdet[outside_interval_mask] = 0
    (
        outputs[inside_interval_mask],
        logabsdet[inside_interval_mask],
    ) = rational_quadratic_spline(
        inputs=inputs[inside_interval_mask],
        unnormalized_widths=unnormalized_widths[inside_interval_mask, :],
        unnormalized_heights=unnormalized_heights[inside_interval_mask, :],
        unnormalized_derivatives=unnormalized_derivatives[inside_interval_mask, :],
        inverse=inverse,
        left=-tail_bound,
        right=tail_bound,
        bottom=-tail_bound,
        top=tail_bound,
        min_bin_width=min_bin_width,
        min_bin_height=min_bin_height,
        min_derivative=min_derivative,
    )
    return outputs, logabsdet


def _params(device, dtype, shape=(4, 2, 37), bins=10, seed=0):
    g = torch.Generator().manual_seed(seed)
    # 区間 [-5, 5] の内外が混ざるように広めに取る (境界ちょうども入れる)
    inputs = torch.randn(*shape, generator=g) * 4
    inputs[0, 0, :3] = torch.tensor([-5.0, 5.0, 0.0])
    w = torch.randn(*shape, bins, generator=g)
    h = torch.randn(*shape, bins, generator=g)
    d = torch.randn(*shape, bins - 1, generator=g)
    return [t.to(device=device, dtype=dtype) for t in (inputs, w, h, d)]


def _run(fn, params, inverse):
    leaves = [p.clone().requires_grad_(True) for p in params]
    out, lad = fn(*leaves, inverse=inverse, tails="linear", tail_bound=5.0)
    g = torch.Generator().manual_seed(1)
    wo = torch.randn(out.shape, generator=g).to(out)
    wl = torch.randn(lad.shape, generator=g).to(lad)
    ((out * wo).sum() + (lad * wl).sum()).backward()
    return out.detach(), lad.detach(), [leaf.grad for leaf in leaves]


DEVICES = ["cpu"] + (["cuda"] if torch.cuda.is_available() else [])


@pytest.mark.parametrize("device", DEVICES)
@pytest.mark.parametrize("inverse", [False, True])
def test_matches_masked_reference(device, inverse):
    params = _params(device, torch.float32)
    out, lad, grads = _run(unconstrained_rational_quadratic_spline, params, inverse)
    ref_out, ref_lad, ref_grads = _run(_reference, params, inverse)
    # 区間内の要素は同じ式を要素ごとに計算するので一致する。CUDA では softmax /
    # cumsum の kernel が行数で変わりうるため、float32 の数 ulp を許す。
    tol = {"rtol": 0, "atol": 0} if device == "cpu" else {"rtol": 1e-6, "atol": 1e-6}
    for new, old in zip([out, lad, *grads], [ref_out, ref_lad, *ref_grads], strict=True):
        torch.testing.assert_close(new, old, **tol)
    for grad in grads:
        assert torch.isfinite(grad).all()


def test_outside_inputs_pass_through_with_unit_gradient():
    params = _params("cpu", torch.float64)
    inputs = params[0]
    out, lad, grads = _run(unconstrained_rational_quadratic_spline, params, False)
    outside = (inputs < -5.0) | (inputs > 5.0)
    assert outside.any() and (~outside).any()
    assert torch.equal(out[outside], inputs[outside])
    assert torch.equal(lad[outside], torch.zeros_like(lad[outside]))
    # 区間外の要素は spline の母数に勾配を流さない
    assert torch.equal(grads[1][outside], torch.zeros_like(grads[1][outside]))


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")
def test_cuda_forward_backward_do_not_synchronize():
    leaves = [p.requires_grad_(True) for p in _params("cuda", torch.float32, shape=(24, 2, 300))]
    torch.cuda.synchronize()
    torch.cuda.set_sync_debug_mode("error")
    try:
        out, lad = unconstrained_rational_quadratic_spline(
            *leaves, inverse=False, tails="linear", tail_bound=5.0
        )
        (out.sum() + lad.sum()).backward()
    finally:
        torch.cuda.set_sync_debug_mode(0)
    torch.cuda.synchronize()
