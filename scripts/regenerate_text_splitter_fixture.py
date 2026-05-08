#!/usr/bin/env python3
"""Regenerate the text-splitter contract JSON fixture used by per-runtime parity tests.

Source of truth: ``docs/spec/text-splitter-contract.toml``
Output:          ``tests/fixtures/text_splitter/contract.json``

Each runtime (Python, Rust, Go, C#, C++) loads this JSON in its test suite and
asserts its own constants match the per-runtime expected codepoint set.
Using JSON avoids a toml dependency in five different languages.

The contract toml documents both a *canonical* set (the union across all 8
supported languages) and a *per-runtime divergence* (e.g. Go uses 8/14 closing
punct + depth-tracking; Rust/C# omit U+FF0E from terminators). The JSON fixture
projects both: ``canonical.*`` for the design-time spec, ``runtimes.<name>.*``
for current per-implementation reality.

Usage:
    python scripts/regenerate_text_splitter_fixture.py            # regenerate
    python scripts/regenerate_text_splitter_fixture.py --check    # CI mode
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "docs/spec/text-splitter-contract.toml"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/text_splitter/contract.json"

# ---------------------------------------------------------------------------
# Per-runtime current divergences. Mirrors the comments in the toml header.
# Each value is the set of codepoints actually accepted by that runtime's
# isClosingPunctuation()/isSentenceTerminator() (or equivalent).
#
# Update both this table AND the toml comment when a runtime is realigned.
# ---------------------------------------------------------------------------

# Canonical sets (from the toml [[closing_punctuation]] / [[sentence_terminators]] tables).
# Computed below from the toml itself.

# Codepoints that each runtime currently OMITS from the canonical close set.
RUNTIME_CLOSING_OMITS: dict[str, list[int]] = {
    "python": [],  # 14/14
    "rust": [],  # 14/14 after Issue #346
    "csharp": [],  # 14/14 after Issue #346
    "cpp": [],  # 14/14 after Issue #346
    "go": [0x0022, 0x0027, 0xFF3D, 0xFF63, 0x2019, 0x00BB],  # 8/14
}

# Codepoints that each runtime currently OMITS from the canonical terminator set.
RUNTIME_TERMINATOR_OMITS: dict[str, list[int]] = {
    "python": [],  # 7/7
    "rust": [0xFF0E],  # 6/7 (missing fullwidth full stop)
    "csharp": [0xFF0E],  # 6/7
    "cpp": [],  # 7/7
    "go": [],  # 7/7
}

# Per-runtime split strategy. The toml [behavior].strategy is canonical = post-consume.
RUNTIME_STRATEGY: dict[str, str] = {
    "python": "post-consume",
    "rust": "post-consume",
    "csharp": "post-consume",
    "cpp": "post-consume",
    "go": "depth-tracking",
}


def _parse_codepoint(token: str) -> int:
    """Parse 'U+0029' -> 0x29."""
    if not token.startswith("U+"):
        raise ValueError(f"unexpected codepoint format: {token!r}")
    return int(token[2:], 16)


def build_fixture() -> dict:
    contract = tomllib.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    canonical_close = sorted(
        _parse_codepoint(e["codepoint"]) for e in contract["closing_punctuation"]
    )
    canonical_term = sorted(
        _parse_codepoint(e["codepoint"]) for e in contract["sentence_terminators"]
    )
    canonical_strategy = contract["behavior"]["strategy"]

    runtimes: dict[str, dict] = {}
    for name in ("python", "rust", "csharp", "cpp", "go"):
        omits_close = set(RUNTIME_CLOSING_OMITS[name])
        omits_term = set(RUNTIME_TERMINATOR_OMITS[name])
        runtimes[name] = {
            "closing_punctuation": [c for c in canonical_close if c not in omits_close],
            "sentence_terminators": [c for c in canonical_term if c not in omits_term],
            "strategy": RUNTIME_STRATEGY[name],
        }

    return {
        "schema_version": 1,
        "comment": (
            "Text-splitter contract fixture. Regenerate via "
            "`python scripts/regenerate_text_splitter_fixture.py`. "
            "Source: docs/spec/text-splitter-contract.toml. "
            "Each runtime asserts its actual closing-punct + terminator sets "
            "match `runtimes.<name>.*` here."
        ),
        "canonical": {
            "closing_punctuation": canonical_close,
            "sentence_terminators": canonical_term,
            "strategy": canonical_strategy,
        },
        "runtimes": runtimes,
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
        help="CI mode: verify the in-tree fixture is up-to-date with the toml",
    )
    args = parser.parse_args()

    fixture = build_fixture()
    serialized = _serialize(fixture)
    rel = FIXTURE_PATH.relative_to(REPO_ROOT)

    if args.check:
        if not FIXTURE_PATH.exists():
            print(
                f"ERROR: {rel} does not exist. Run "
                f"`python scripts/regenerate_text_splitter_fixture.py`.",
                file=sys.stderr,
            )
            return 1
        existing = FIXTURE_PATH.read_text(encoding="utf-8")
        if existing != serialized:
            print(
                f"ERROR: {rel} is out of sync with "
                f"{CONTRACT_PATH.relative_to(REPO_ROOT)}.",
                file=sys.stderr,
            )
            print(
                "Run `python scripts/regenerate_text_splitter_fixture.py` to regenerate.",
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
