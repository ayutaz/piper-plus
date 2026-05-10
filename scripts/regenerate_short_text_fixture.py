#!/usr/bin/env python3
"""Regenerate the short-text contract JSON fixture used by per-runtime parity tests.

Source of truth: ``docs/spec/short-text-contract.toml``
Output:          ``tests/fixtures/short_text/contract.json``

Each non-Python runtime (Rust, Go, C++, C#, WASM/JS) loads this JSON in its
test suite and asserts its own constants match. Using JSON avoids a toml
dependency in five different languages.

Usage:
    python scripts/regenerate_short_text_fixture.py            # regenerate
    python scripts/regenerate_short_text_fixture.py --check    # CI mode: drift check
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/short-text-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/short_text/contract.json"


def build_fixture() -> dict:
    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    # Project a flat, language-neutral subset of the toml.
    return {
        "schema_version": 1,
        "comment": (
            "Short-text contract fixture. Regenerate via "
            "`python scripts/regenerate_short_text_fixture.py`. "
            "Source: docs/spec/short-text-contract.toml. "
            "Each runtime asserts its own constants match these values."
        ),
        "padding": {
            "min_phoneme_ids": contract["padding"]["min_phoneme_ids"],
            "min_body_for_strategy_a": contract["padding"]["min_body_for_strategy_a"],
            "pause_token_id": contract["padding"]["pause_token_id"],
            "split": contract["padding"]["split"],
            "prosody_fill": contract["padding"]["prosody_fill"],
        },
        "trim": {
            "threshold_rms": contract["trim"]["threshold_rms"],
            "min_samples": contract["trim"]["min_samples"],
            "window_size": contract["trim"]["window_size"],
            "sample_rate": contract["trim"]["sample_rate"],
        },
        "scales": {
            "noise_scale_min_ratio": contract["scales"]["noise_scale_min_ratio"],
            "noise_w_min_ratio": contract["scales"]["noise_w_min_ratio"],
        },
        "ssml_injection": {
            "short_text_chars": contract["ssml_injection"]["short_text_chars"],
            "silence_pad_ms": contract["ssml_injection"]["silence_pad_ms"],
            "skip_if_ssml": contract["ssml_injection"]["skip_if_ssml"],
        },
    }


def _serialize(fixture: dict) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="CI mode: verify that the in-tree fixture is up-to-date with the toml",
    )
    args = parser.parse_args()

    fixture = build_fixture()
    serialized = _serialize(fixture)
    rel = FIXTURE_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not FIXTURE_PATH.exists():
            print(
                f"ERROR: {rel} does not exist. Run `python scripts/regenerate_short_text_fixture.py`.",
                file=sys.stderr,
            )
            return 1
        existing = FIXTURE_PATH.read_text(encoding="utf-8")
        if existing != serialized:
            print(
                f"ERROR: {rel} is out of sync with {CONTRACT_PATH.relative_to(REPO_ROOT)}.",
                file=sys.stderr,
            )
            print(
                "Run `python scripts/regenerate_short_text_fixture.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel} is up-to-date.")
        return 0

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(serialized, encoding="utf-8")
    print(f"Wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
