#!/usr/bin/env python3
"""Decoder-only CPU latency / size benchmark for the v10b Phase B levers.

docs/design/zero-shot-v10b-quality-plan.md §4.3 registers a mandatory inference
cost gate — CPU p50 latency within +10% of the v10a-r2 ONNX and FP16 size
<= 40MB — because several v10b levers touch the inference graph (H-1
resize+conv, H-2b taps 62->126). This script gives the Phase B implementation a
fast, repeatable read on the decoder in isolation so a regression is caught
while the lever is still cheap to drop.

Scope and honesty about it: this measures ``MBiSTFTGenerator.forward`` in
PyTorch on CPU, not the exported ONNX graph end to end. It is the *screening*
measurement (does the arm blow the budget structurally?). The gate itself is
decided on the ONNX p50 numbers pinned in the Phase A baseline manifest.

Usage:
    python scripts/bench_decoder_cpu.py
    python scripts/bench_decoder_cpu.py --frames 172 --runs 30 --threads 1
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from platform_utils import force_utf8_output  # noqa: E402


# Real training/inference configuration (quality=medium, upsample_rates=(4, 4)).
_GEN_KWARGS = {
    "initial_channel": 192,
    "resblock": "2",
    "resblock_kernel_sizes": (3, 5, 7),
    "resblock_dilation_sizes": ((1, 2), (2, 6), (3, 12)),
    "upsample_rates": (4, 4),
    "upsample_initial_channel": 256,
    "upsample_kernel_sizes": (16, 16),
}

# (label, upsample_mode, pqmf_taps)
_ARMS = (
    ("baseline (transposed, taps=62)", "transposed", 62),
    ("H-1 resize (taps=62)", "resize", 62),
    ("H-2b taps=126 (transposed)", "transposed", 126),
    ("H-1 + H-2b (resize, taps=126)", "resize", 126),
)


def _build(mode: str, taps: int):
    import contextlib
    import io

    import torch

    from piper_train.vits.mb_istft import MBiSTFTGenerator

    torch.manual_seed(0)
    gen = MBiSTFTGenerator(**_GEN_KWARGS, upsample_mode=mode, pqmf_taps=taps)
    gen.eval()
    with contextlib.redirect_stdout(io.StringIO()):  # "Removing weight norm..."
        gen.remove_weight_norm()
    gen.onnx_export_mode = True
    return gen


def _time_all_interleaved(
    gens: list, frames: int, runs: int, warmup: int
) -> list[list[float]]:
    """Round-robin the arms so machine drift hits every arm equally.

    Measuring arms one after another lets thermal/scheduler drift masquerade as
    a per-arm cost difference, which is exactly the mistake to avoid when the
    verdict is a +/-10% gate.
    """
    import torch

    x = torch.randn(1, _GEN_KWARGS["initial_channel"], frames)
    samples: list[list[float]] = [[] for _ in gens]
    with torch.no_grad():
        for gen in gens:
            for _ in range(warmup):
                gen(x)
        for _ in range(runs):
            for i, gen in enumerate(gens):
                t0 = time.perf_counter()
                gen(x)
                samples[i].append((time.perf_counter() - t0) * 1000.0)
    return samples


def _param_bytes(gen) -> tuple[int, int]:
    """(total params, ups-only params) — FP16 size is params * 2 bytes."""
    total = sum(p.numel() for p in gen.parameters())
    ups = sum(p.numel() for p in gen.ups.parameters())
    return total, ups


def main() -> int:
    force_utf8_output()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--frames",
        type=int,
        default=172,
        help="latent frames (172 ~= 2.0 s at 22.05 kHz / hop 256)",
    )
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument(
        "--threads",
        type=int,
        default=0,
        help="torch CPU threads (0 = leave PyTorch default)",
    )
    args = ap.parse_args()

    import torch

    if args.threads:
        torch.set_num_threads(args.threads)

    print(
        f"decoder-only CPU bench | frames={args.frames} "
        f"({args.frames * 256 / 22050:.2f} s audio) runs={args.runs} "
        f"threads={torch.get_num_threads()} torch={torch.__version__}"
    )
    print(
        f"{'arm':<32} {'p50 ms':>9} {'p90 ms':>9} {'vs base':>9} "
        f"{'params':>10} {'FP16 MB':>9} {'ups params':>11}"
    )

    gens = [_build(mode, taps) for _, mode, taps in _ARMS]
    all_samples = _time_all_interleaved(gens, args.frames, args.runs, args.warmup)

    base_p50 = None
    for (label, _mode, _taps), gen, samples in zip(
        _ARMS, gens, all_samples, strict=True
    ):
        samples.sort()
        p50 = statistics.median(samples)
        p90 = samples[min(len(samples) - 1, int(0.9 * len(samples)))]
        total, ups = _param_bytes(gen)
        if base_p50 is None:
            base_p50 = p50
        delta = f"{(p50 / base_p50 - 1) * 100:+.1f}%"
        print(
            f"{label:<32} {p50:>9.2f} {p90:>9.2f} {delta:>9} "
            f"{total:>10,} {total * 2 / 1e6:>9.2f} {ups:>11,}"
        )

    print(
        "\nNote: the +10% gate in plan §4.3 is decided on exported-ONNX p50 "
        "against the Phase A baseline manifest; this table screens the decoder "
        "arms only."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
