#!/usr/bin/env python3
"""AI-03 SKELETON: param-budget audit for the istftnet2_mb_1d2d decoder.

Invoke as ``uv run python scripts/check_istftnet2_params.py``.

Builds an :class:`MBiSTFTGenerator` configured with
``decoder_type="istftnet2_mb_1d2d"`` plus the same hyperparameters as the
6lang base config, prints the trainable parameter count, and asserts the
``0.83M +/- 0.05M`` budget. Also runs a single ``forward(x, g)`` with
``x=torch.randn(1, 192, 50)`` / ``g=torch.randn(1, 256, 1)`` and prints
the output shape so reviewers can sanity-check the [B, 1, 50*256] contract.

Exit codes:
  0 - within budget AND forward succeeded
  1 - budget miss OR forward raised (including NotImplementedError while the
      2D body is still a skeleton; this is expected during AI-03 review)

# TODO(AI-03): ONNX export dry-run with op-set audit (Conv2d/Reshape/Transpose
# only, NO ConvTranspose2d per Risk R7) lives in
# scripts/check_istftnet2_onnx_ops.py (future, owned by AI-08).
"""

from __future__ import annotations

import sys

# 6lang base config hyperparameters (mirrors training command Template A).
# Inline dict instead of loading from tests/fixtures/ to keep this script
# zero-dep and runnable without the full pytest setup.
_BASE_CFG: dict = {
    "initial_channel": 192,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 256,
    "upsample_kernel_sizes": (16, 16),
    "gin_channels": 256,
    "decoder_type": "istftnet2_mb_1d2d",
}

_BUDGET_MIN = 0.78e6
_BUDGET_MAX = 0.88e6


def main() -> int:
    """Build the generator, count params, run forward, return exit code."""
    try:
        import torch

        from piper_train.vits.mb_istft import MBiSTFTGenerator
    except ImportError as e:
        print(f"[AI-03 check_istftnet2_params] import failed: {e}", file=sys.stderr)
        return 1

    gen = MBiSTFTGenerator(**_BASE_CFG)

    n_params = sum(p.numel() for p in gen.parameters() if p.requires_grad)
    print(f"[AI-03] trainable params = {n_params:,}  ({n_params / 1e6:.3f}M)")
    print(f"[AI-03] budget           = {_BUDGET_MIN:,.0f} .. {_BUDGET_MAX:,.0f}")

    if not (_BUDGET_MIN <= n_params <= _BUDGET_MAX):
        print(
            f"[AI-03] BUDGET MISS: {n_params:,} outside "
            f"[{_BUDGET_MIN:,.0f}, {_BUDGET_MAX:,.0f}]",
            file=sys.stderr,
        )
        return 1

    # Smoke-test forward. Currently raises NotImplementedError in the
    # skeleton; AI-04 follow-up wires up the 2D body and this branch turns
    # green.
    x = torch.randn(1, 192, 50)
    g = torch.randn(1, 256, 1)
    try:
        out = gen(x, g=g)
    except NotImplementedError as e:
        print(f"[AI-03] forward not yet implemented (expected): {e}")
        # In the skeleton phase we treat NotImplementedError as a soft fail
        # so reviewers see the budget+shape contract clearly. Flip to soft-pass
        # by uncommenting the next line once AI-04 lands.
        # return 0
        return 1

    if isinstance(out, tuple):
        fullband = out[0]
    else:
        fullband = out
    print(f"[AI-03] forward output shape = {tuple(fullband.shape)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
