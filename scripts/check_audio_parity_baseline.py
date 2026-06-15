#!/usr/bin/env python3
"""AI-15 regression-guard: [mb_istft_1d] audio-parity baseline drift check.

This script is part of the AI-15 implementation plan (CI regression-guard
gate for A-1 / A-2 / FLY-TTS decoder variants). It enforces that the
canonical baseline values for the existing `[mb_istft_1d]` decoder
variant remain immutable unless a maintainer explicitly opts in via a
commit-message trailer.

Baseline source-of-truth: docs/spec/audio-parity-contract.toml
Pin file:                 scripts/audio_parity_baseline.lock.json

Behaviour:

* Load both files, diff-compare the `[mb_istft_1d]` fields
  (expected_p50_ms, expected_proxy_mos_mean, expected_params_m,
  expected_snr_floor_db, sample_rate).
* On drift -> exit 1 with a descriptive stderr message.
* On drift + ``--update-baseline`` + a commit message bearing the
  trailer ``audio-parity-baseline-bump:`` -> rewrite the lock.json and
  exit 0.

NOTE: This is a SKELETON for AI-15. Real comparison + trailer-detection
logic is intentionally stubbed; see the AI-15 ticket for the full DoD.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/audio-parity-contract.toml"
LOCK_PATH = REPO_ROOT / "scripts/audio_parity_baseline.lock.json"

# Canonical [mb_istft_1d] fields the lock pins; see CLAUDE.md / README.
PINNED_FIELDS = (
    "expected_p50_ms",
    "expected_proxy_mos_mean",
    "expected_params_m",
    "expected_snr_floor_db",
    "sample_rate",
)

# Commit-message trailer required to authorise a baseline bump.
BUMP_TRAILER = "audio-parity-baseline-bump:"


def _load_contract(path: Path) -> dict:
    """Parse the audio-parity TOML contract and return the [mb_istft_1d] table.

    TODO(AI-15): replace placeholder with tomllib.load + section lookup.
    """
    # TODO(AI-15): implement tomllib-based load and surface a friendly
    # error when the [mb_istft_1d] section is missing.
    raise NotImplementedError(
        f"TODO(AI-15): load [mb_istft_1d] section from {path}"
    )


def _load_lock(path: Path) -> dict:
    """Load the JSON pin file and return the [mb_istft_1d] dict.

    TODO(AI-15): implement json.load + schema sanity check.
    """
    # TODO(AI-15): implement JSON load with helpful error if file missing.
    raise NotImplementedError(f"TODO(AI-15): load lock file {path}")


def _diff_fields(contract_section: dict, lock_section: dict) -> list[str]:
    """Return a list of human-readable drift descriptions; empty on match.

    TODO(AI-15): per-field compare with float tolerance for ms / mos fields.
    """
    # TODO(AI-15): walk PINNED_FIELDS and accumulate drift messages.
    raise NotImplementedError("TODO(AI-15): diff_fields not implemented")


def _commit_message_has_trailer(trailer: str = BUMP_TRAILER) -> bool:
    """Return True if HEAD's commit message contains the bump trailer.

    TODO(AI-15): subprocess.run(['git', 'log', '-1', '--format=%B']) and
    case-insensitive line search. Also hook into CODEOWNERS approval.
    """
    # TODO(AI-15): integrate with git log + CODEOWNERS approval check.
    raise NotImplementedError(
        f"TODO(AI-15): trailer detection for {trailer!r} not implemented"
    )


def _rewrite_lock(path: Path, new_section: dict) -> None:
    """Persist a refreshed [mb_istft_1d] block to the lock file.

    TODO(AI-15): implement atomic write with stable key ordering.
    """
    # TODO(AI-15): json.dump with sort_keys=True, indent=2, trailing newline.
    raise NotImplementedError(f"TODO(AI-15): rewrite {path}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the AI-15 baseline-drift gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Check [mb_istft_1d] audio-parity baseline against the pinned "
            "lock file. Pass --update-baseline (with the required trailer) "
            "to refresh the lock during an intentional bump."
        )
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Rewrite the lock file from the contract toml. Requires HEAD "
            f"commit message to include the {BUMP_TRAILER!r} trailer."
        ),
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=CONTRACT_PATH,
        help="Override the contract TOML path (default: %(default)s).",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=LOCK_PATH,
        help="Override the lock JSON path (default: %(default)s).",
    )
    args = parser.parse_args(argv)

    # TODO(AI-15): wire up the pipeline:
    #   contract = _load_contract(args.contract)
    #   lock     = _load_lock(args.lock)
    #   drift    = _diff_fields(contract, lock)
    #   if drift and not args.update_baseline:
    #       print to stderr, return 1
    #   elif drift and args.update_baseline and _commit_message_has_trailer():
    #       _rewrite_lock(args.lock, contract)
    #       return 0
    print(
        "AI-15 skeleton: check_audio_parity_baseline.py not yet implemented",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
