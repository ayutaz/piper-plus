#!/usr/bin/env python3
"""ONNX round-trip + op-audit smoke script for FLY-TTS decoder (AI-06).

Skeleton smoke for ticket AI-06. The script exports
``FlyDecoder`` to ONNX (opset 15) with dynamic time axes, walks the
graph to assert disallowed ops are absent, and verifies torch /
onnxruntime output parity within ``atol=1e-4``.

This is **not** a pytest target; it is invoked manually (or by AI-13's
7-runtime smoke matrix) once AI-06 implementation lands.

Usage
-----
    uv run python scripts/smoke_fly_decoder_onnx.py

Dependencies
------------
* torch (already in the training env)
* onnx, onnxruntime (install via ``uv sync --extra dev`` if absent)

Disallowed ONNX ops (op-audit set)
----------------------------------
* ``Conv`` with 2D kernels would surface as ``Conv`` nodes with 4D
  weight initializers; we forbid the higher-level ``Conv2d`` /
  ``ConvTranspose`` proxies that the PyTorch ONNX exporter would emit.
* ``STFT`` / ``DFT`` must not appear: the iSTFT head is implemented as
  ``conv_transpose1d`` (see :class:`OnnxISTFT`).

TODO(AI-13): reuse this smoke as the Python anchor of the 7-runtime
parity matrix (Rust / Go / C# / WASM / C++ / Swift / Kotlin all import
the same exported ``fly_decoder.onnx``).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Iterable


# Disallowed ONNX op_type set. ``Conv`` and ``ConvTranspose`` are flagged
# separately by inspecting weight rank since 1D variants share the op name.
DISALLOWED_OPS: frozenset[str] = frozenset({"STFT", "DFT"})


def _walk_disallowed_ops(model: onnx.ModelProto) -> list[str]:  # noqa: F821
    """Return a list of disallowed op_types found in ``model.graph``.

    TODO(AI-06): implement op-audit walk over ``model.graph.node``.
    """
    raise NotImplementedError(
        "TODO(AI-06): implement ONNX node walk for DISALLOWED_OPS audit"
    )


def _assert_no_2d_conv(model: onnx.ModelProto) -> Iterable[str]:  # noqa: F821
    """Yield names of Conv / ConvTranspose initializers with 4D weights.

    TODO(AI-06): walk model.graph.initializer and flag 4D weight tensors
    feeding Conv* nodes.
    """
    raise NotImplementedError("TODO(AI-06): implement 2D-conv weight-rank audit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("out/fly_decoder.onnx"),
        help="Output ONNX file path.",
    )
    parser.add_argument(
        "--opset",
        type=int,
        default=15,
        help="ONNX opset version (default 15).",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=1e-4,
        help="Absolute tolerance for torch / ORT parity (default 1e-4).",
    )
    args = parser.parse_args()

    # TODO(AI-06): import torch / numpy / onnx / onnxruntime lazily so
    # --help works without the heavy deps. Below imports are placeholders
    # showing the intended structure.
    try:
        import numpy as np  # noqa: F401
        import onnx  # noqa: F401
        import onnxruntime as ort  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:  # pragma: no cover - skeleton
        print(f"FAIL: missing dependency: {exc}", file=sys.stderr)
        print(
            "Hint: `uv sync --extra dev` to install torch / onnx / onnxruntime",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # TODO(AI-06): construct FlyDecoder().eval(), build dummy_x, run forward.
    # TODO(AI-06): torch.onnx.export with opset_version=args.opset and
    # dynamic_axes={"x": {2: "T"}, "audio": {2: "T_audio"}}.
    # TODO(AI-06): onnx.load and walk DISALLOWED_OPS / 2D Conv audit.
    # TODO(AI-06): ort.InferenceSession (CPUExecutionProvider) parity check
    # vs torch_out within args.atol.
    # TODO(AI-06): print PASS/FAIL summary including param count.
    print("TODO(AI-06): implement FLY-TTS decoder ONNX round-trip smoke")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
