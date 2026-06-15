#!/usr/bin/env python3
"""AI-15 regression-guard: expected_p50_ms tolerance gate.

Loads ``tools/benchmark/metrics.json`` (produced by AI-12) and compares
each variant's measured ``rtf_p50_ms`` against the canonical target in
``docs/spec/audio-parity-contract.toml``.

Tolerance policy:

* ``[mb_istft_1d]``  -> +/-10 % of expected_p50_ms (existing baseline).
* ``[istftnet2_mb_1d2d]``, ``[mswavehax]``, ``[fly_convnext6]``
  -> measured value must be <= target (strict).

Failure of any variant produces a non-zero exit with per-variant
pass / fail messages.

NOTE: This is a SKELETON for AI-15. The numeric comparison + json schema
load is intentionally stubbed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/audio-parity-contract.toml"
DEFAULT_METRICS_PATH = REPO_ROOT / "tools/benchmark/metrics.json"

# Variants whose target is bounded by a +/- ratio (the existing baseline).
TOLERANCE_VARIANTS: dict[str, float] = {
    "mb_istft_1d": 0.10,  # +/-10 %
}

# Variants whose measured value must be <= contract target (strict ceiling).
STRICT_VARIANTS: tuple[str, ...] = (
    "istftnet2_mb_1d2d",
    "mswavehax",
    "fly_convnext6",
)


def _load_metrics(path: Path) -> dict:
    """Load tools/benchmark/metrics.json.

    Expected schema (per AI-12):
      {variant: {"proxy_mos": float, "rtf_p50_ms": float, "params_m": float}}

    TODO(AI-15): implement json.load + schema validation.
    """
    # TODO(AI-15): implement json.load with helpful error if missing.
    raise NotImplementedError(f"TODO(AI-15): load metrics from {path}")


def _load_targets(path: Path) -> dict[str, float]:
    """Return {variant: expected_p50_ms} from the contract toml.

    TODO(AI-15): tomllib.load + iterate over the variant tables.
    """
    # TODO(AI-15): implement tomllib-based target lookup.
    raise NotImplementedError(f"TODO(AI-15): load targets from {path}")


def _check_tolerance(
    variant: str, measured: float, target: float, tolerance: float
) -> Optional[str]:
    """Return None if within +/-tolerance; otherwise a drift message.

    TODO(AI-15): real ratio compare; surface measured/target in message.
    """
    # TODO(AI-15): abs(measured - target) / target <= tolerance.
    raise NotImplementedError(
        f"TODO(AI-15): tolerance check for {variant} not implemented"
    )


def _check_strict(variant: str, measured: float, target: float) -> Optional[str]:
    """Return None if measured <= target; otherwise a drift message.

    TODO(AI-15): real <= compare for strict-ceiling variants.
    """
    # TODO(AI-15): measured <= target.
    raise NotImplementedError(
        f"TODO(AI-15): strict check for {variant} not implemented"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the expected_p50_ms tolerance gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare measured rtf_p50_ms per variant against the canonical "
            "audio-parity-contract.toml target. mb_istft_1d uses +/-10 %; "
            "the three new variants use a strict ceiling."
        )
    )
    parser.add_argument(
        "--from-metrics",
        type=Path,
        default=DEFAULT_METRICS_PATH,
        help="Path to metrics.json (default: %(default)s).",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=CONTRACT_PATH,
        help="Path to audio-parity-contract.toml (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    # TODO(AI-15): wire the pipeline:
    #   metrics = _load_metrics(args.from_metrics)
    #   targets = _load_targets(args.contract)
    #   for variant, ratio in TOLERANCE_VARIANTS.items():
    #       err = _check_tolerance(variant, ..., ..., ratio)
    #       if err: failures.append(err)
    #   for variant in STRICT_VARIANTS:
    #       err = _check_strict(variant, ..., ...)
    #       if err: failures.append(err)
    # TODO(AI-15): emit per-variant pass/fail summary.
    # TODO(AI-15): stub for AI-16 tolerance widening + bf16-mixed re-baseline.
    _ = args  # silence unused while skeleton
    print(
        "AI-15 skeleton: check_expected_p50_ms_gate.py not yet implemented",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
