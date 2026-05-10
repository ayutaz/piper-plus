#!/usr/bin/env python3
"""Cross-runtime phoneme timing golden fixture (re)generator.

Source of truth: ``src/python_run/piper/timing.py:durations_to_timing``
Output:          ``tests/fixtures/phoneme_timing/golden_matrix.json``

Each runtime (Python, Rust, Go, C++, C#, WASM/JS) has its own ``timing``
implementation that must produce byte-equivalent output for the same inputs.
This fixture pins canonical input → expected pairs so that any runtime can
load it in tests and assert parity.

Usage:
    python scripts/regenerate_timing_fixture.py            # regenerate
    python scripts/regenerate_timing_fixture.py --check    # CI mode: drift check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# Make the runtime package importable without installation.
sys.path.insert(0, str(REPO_ROOT / "src/python_run"))

from piper.timing import durations_to_timing  # noqa: E402


FIXTURE_PATH = REPO_ROOT / "tests/fixtures/phoneme_timing/golden_matrix.json"

# Each case is intentionally small so it can be reproduced by other runtimes
# without needing to load an ONNX model. Inputs are integer frame counts and
# string phoneme tokens; outputs are computed using the canonical Python
# implementation.
CASES: list[dict] = [
    {
        "name": "basic_konnichiwa",
        "description": "Japanese greeting at 22050Hz / hop=256",
        "inputs": {
            "durations": [3, 5, 8, 4, 4, 5, 3, 6, 4, 5, 3],
            "phoneme_tokens": ["^", "k", "o", "n", "n", "i", "ch", "i", "w", "a", "$"],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
    {
        "name": "single_phoneme",
        "description": "Single phoneme — minimum non-empty case",
        "inputs": {
            "durations": [10],
            "phoneme_tokens": ["a"],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
    {
        "name": "negative_clamped",
        "description": "Negative durations are clamped to 0 (graceful degradation)",
        "inputs": {
            "durations": [3, -2, 5],
            "phoneme_tokens": ["a", "b", "c"],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
    {
        "name": "high_sample_rate",
        "description": "44100Hz / hop=512 — alternative model config",
        "inputs": {
            "durations": [10, 10],
            "phoneme_tokens": ["x", "y"],
            "sample_rate": 44100,
            "hop_length": 512,
        },
    },
    {
        "name": "pua_phoneme",
        "description": "PUA phoneme token (multi-char) is preserved verbatim",
        "inputs": {
            "durations": [5, 8, 3],
            "phoneme_tokens": ["a", "U+E019", "b"],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
    {
        "name": "empty",
        "description": "Empty input → empty result, total_duration_ms=0",
        "inputs": {
            "durations": [],
            "phoneme_tokens": [],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
    {
        "name": "all_zero_durations",
        "description": "All-zero durations → contiguous zero-length boundaries",
        "inputs": {
            "durations": [0, 0, 0],
            "phoneme_tokens": ["a", "b", "c"],
            "sample_rate": 22050,
            "hop_length": 256,
        },
    },
]


def _compute_expected(case: dict) -> dict:
    inputs = case["inputs"]
    result = durations_to_timing(
        durations=inputs["durations"],
        phoneme_tokens=inputs["phoneme_tokens"],
        sample_rate=inputs["sample_rate"],
        hop_length=inputs["hop_length"],
    )
    return {
        "phonemes": [asdict(p) for p in result.phonemes],
        "total_duration_ms": result.total_duration_ms,
        "sample_rate": result.sample_rate,
    }


def build_fixture() -> dict:
    return {
        "schema_version": 1,
        "comment": (
            "Cross-runtime phoneme timing golden fixture. "
            "Regenerate via `python scripts/regenerate_timing_fixture.py`. "
            "Source: src/python_run/piper/timing.py:durations_to_timing. "
            "Spec: docs/spec/phoneme-timing-contract.toml. Do not edit by hand."
        ),
        "calculation_formula": "frame_time_ms = (hop_length / sample_rate) * 1000",
        "cases": [{**case, "expected": _compute_expected(case)} for case in CASES],
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
        help="CI mode: verify that the in-tree fixture matches canonical generation",
    )
    args = parser.parse_args()

    serialized = _serialize(build_fixture())
    rel = FIXTURE_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not FIXTURE_PATH.exists():
            print(
                f"ERROR: {rel} does not exist. Run `python scripts/regenerate_timing_fixture.py`.",
                file=sys.stderr,
            )
            return 1
        existing = FIXTURE_PATH.read_text(encoding="utf-8")
        if existing != serialized:
            print(
                f"ERROR: {rel} is out of sync with canonical Python implementation.",
                file=sys.stderr,
            )
            print(
                "Run `python scripts/regenerate_timing_fixture.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {rel} is up-to-date with src/python_run/piper/timing.py.")
        return 0

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(serialized, encoding="utf-8")
    print(f"Wrote {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
