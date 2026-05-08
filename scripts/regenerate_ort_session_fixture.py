#!/usr/bin/env python3
"""Regenerate the ORT session contract JSON fixture used by per-runtime parity tests.

Source of truth: ``docs/spec/ort-session-contract.toml``
Output:          ``tests/fixtures/ort_session/contract.json``

Each runtime (Python / Rust / Go / C#) loads this JSON in its test suite
and asserts its own constants / behaviour match. JSON avoids requiring
a toml parser in five languages.

Usage:
    python scripts/regenerate_ort_session_fixture.py            # regenerate
    python scripts/regenerate_ort_session_fixture.py --check    # CI mode: drift check
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/ort-session-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/ort_session/contract.json"


def build_fixture() -> dict:
    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    return {
        "schema_version": 1,
        "comment": (
            "ORT session contract fixture. Regenerate via "
            "`python scripts/regenerate_ort_session_fixture.py`. "
            "Source: docs/spec/ort-session-contract.toml. "
            "Each runtime asserts its own session/warmup/cache/env_vars constants match."
        ),
        "session": {
            "graph_optimization_level": contract["session"]["graph_optimization_level"],
            "execution_mode": contract["session"]["execution_mode"],
            "max_intra_threads": contract["session"]["max_intra_threads"],
            "inter_op_threads": contract["session"]["inter_op_threads"],
            "enable_cpu_mem_arena": contract["session"]["enable_cpu_mem_arena"],
            "enable_memory_pattern": contract["session"]["enable_memory_pattern"],
            "dynamic_block_base": contract["session"]["dynamic_block_base"],
        },
        "warmup": {
            "phoneme_length": contract["warmup"]["phoneme_length"],
            "bos_token": contract["warmup"]["bos_token"],
            "eos_token": contract["warmup"]["eos_token"],
            "dummy_phoneme": contract["warmup"]["dummy_phoneme"],
            "default_runs": contract["warmup"]["default_runs"],
            "noise_scale": contract["warmup"]["noise_scale"],
            "length_scale": contract["warmup"]["length_scale"],
            "noise_w": contract["warmup"]["noise_w"],
        },
        "cache": {
            "optimized_extension": contract["cache"]["optimized_extension"],
            "sentinel_extension": contract["cache"]["sentinel_extension"],
            "sentinel_content": contract["cache"]["sentinel_content"],
            "device_label_cpu": contract["cache"]["device_label_cpu"],
            "device_label_cuda_format": contract["cache"]["device_label_cuda_format"],
        },
        "env_vars": {
            "disable_warmup": contract["env_vars"]["disable_warmup"],
            "disable_cache": contract["env_vars"]["disable_cache"],
            "intra_threads": contract["env_vars"]["intra_threads"],
        },
    }


def _serialize(fixture: dict) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
                f"ERROR: {rel} does not exist. Run `python scripts/regenerate_ort_session_fixture.py`.",
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
                "Run `python scripts/regenerate_ort_session_fixture.py` to regenerate.",
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
