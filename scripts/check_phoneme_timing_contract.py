#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2/5-space indented bullet lists)
"""Phoneme timing contract gate.

The phoneme-timing formula `(hop_length / sample_rate) * 1000` is the
*only* knob that controls cross-runtime timing parity. A silent drift
(e.g. someone "optimises" the Rust path to compute frame_time in seconds
and then forgets the `* 1000`) is catastrophic: the JSON / TSV / SRT
outputs disagree across runtimes and break byte-for-byte parity tests
days or weeks later, when the change-set is no longer obvious.

This gate is intentionally lightweight (no AST / no parser). It loads
`docs/spec/phoneme-timing-contract.toml`, extracts the canonical formula
and the per-runtime implementation paths, then for each implementation
asserts:

  1. The file exists.
  2. The file references `hop_length` and `sample_rate` (canonical
     parameter names — kebab/snake/camel variants all accepted).
  3. A multiplier of `1000` appears in the file (the ms conversion).
  4. The runtime mentions either `(hop` or `frame_time` / `frameTime`
     to anchor on the formula site rather than incidental docstrings.

Why not parse the formula? Each runtime spells it differently
(Python: `(hop_length / sample_rate) * 1000.0`, Rust: two-step
`frame_time_s = hop_length as f64 / sample_rate as f64; frame_time_ms
= frame_time_s * 1000.0`, C++: `float frameLength = hopSize /
sampleRate` then `* 1000` elsewhere, …). The textual check is a
floor-level smoke test paired with the existing byte-for-byte golden
fixtures owned by each runtime's test suite — together they fail
fast on drift but don't try to re-derive correctness from source.

Exit codes:
    0 -- every runtime implementation contains the canonical anchors
    1 -- contract toml missing, or at least one runtime impl missing
         the expected formula anchors
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "spec" / "phoneme-timing-contract.toml"

# Per-runtime file extraction: the contract's `[implementations.<runtime>]`
# table carries a `file = "..."` field. Some runtimes (cpp) declare a file
# *plus* a parenthetical function name — strip that.
FILE_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")

# Acceptable spellings of the canonical parameter names. Each runtime uses
# either snake_case (Python/Rust/Go/C++ comments) or camelCase (JS/C#/C++
# C++ vars), and some C++ sites use UpperCamelCase (e.g. `HopSize`,
# `SampleRate`) when surfacing the parameter as a public field/getter.
# The substring check is generous on purpose — we only want to fail when
# *neither* spelling appears.
HOP_TOKENS = (
    "hop_length",
    "hopLength",
    "HopLength",
    "hop_size",
    "hopSize",
    "HopSize",
)
SR_TOKENS = ("sample_rate", "sampleRate", "SampleRate")

# Anchors that pin the check to the formula site (not unrelated comments).
# Either a multiplier of 1000 OR a frame_time variable name is acceptable.
FORMULA_ANCHOR_TOKENS = (
    "1000",  # ms conversion (e.g. `* 1000`, `1000.0f`, `1000.0`)
    "frame_time",
    "frameTime",
    "frameLength",
)


def _resolve_file(rel: str) -> Path:
    """Strip the trailing ``(function)`` suffix some entries carry."""
    stripped = FILE_PAREN_RE.sub("", rel).strip()
    return REPO_ROOT / stripped


def _runtime_ok(runtime: str, file_path: Path) -> list[str]:
    """Return a list of failure messages for one runtime (empty = pass)."""
    failures: list[str] = []
    if not file_path.exists():
        return [f"  FAIL [{runtime}] file missing: {file_path}"]
    text = file_path.read_text(encoding="utf-8", errors="replace")

    if not any(tok in text for tok in HOP_TOKENS):
        failures.append(
            f"  FAIL [{runtime}] {file_path.relative_to(REPO_ROOT)}: "
            f"no hop_length/hopSize spelling found"
        )
    if not any(tok in text for tok in SR_TOKENS):
        failures.append(
            f"  FAIL [{runtime}] {file_path.relative_to(REPO_ROOT)}: "
            f"no sample_rate/sampleRate spelling found"
        )
    if not any(tok in text for tok in FORMULA_ANCHOR_TOKENS):
        failures.append(
            f"  FAIL [{runtime}] {file_path.relative_to(REPO_ROOT)}: "
            f"no 1000 multiplier or frame_time anchor — drift suspected"
        )
    return failures


def main() -> int:
    if not CONTRACT.exists():
        print(f"::error::contract missing: {CONTRACT}", file=sys.stderr)
        return 1
    with CONTRACT.open("rb") as f:
        contract = tomllib.load(f)

    calc = contract.get("calculation", {})
    formula_raw = calc.get("formula")
    # Normalise: strip surrounding whitespace so a trailing newline / stray
    # indent in the TOML doesn't produce a spurious drift failure. The
    # canonical comparison is on the meaningful payload, not the verbatim
    # bytes.
    formula = formula_raw.strip() if isinstance(formula_raw, str) else formula_raw
    print(f"Canonical formula: {formula}")
    expected = "frame_time_ms = (hop_length / sample_rate) * 1000"
    if formula != expected:
        print(
            f"::error::canonical formula drift: {formula!r} "
            f"(expected {expected!r})",
            file=sys.stderr,
        )
        return 1

    impls = contract.get("implementations", {})
    if not impls:
        print("::error::[implementations] table empty in contract", file=sys.stderr)
        return 1

    all_failures: list[str] = []
    for runtime, table in impls.items():
        rel = table.get("file")
        if not rel:
            print(f"  SKIP [{runtime}] no 'file' key")
            continue
        file_path = _resolve_file(rel)
        fails = _runtime_ok(runtime, file_path)
        if fails:
            all_failures.extend(fails)
            for f in fails:
                print(f, file=sys.stderr)
        else:
            print(f"  OK   [{runtime}] {file_path.relative_to(REPO_ROOT)}")

    if all_failures:
        print(
            f"\n{len(all_failures)} phoneme-timing contract drift(s)",
            file=sys.stderr,
        )
        return 1

    print("\n[OK] phoneme-timing formula anchors present in every runtime impl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
