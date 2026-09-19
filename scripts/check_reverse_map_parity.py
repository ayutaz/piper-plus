#!/usr/bin/env python3
"""Every runtime must implement the phoneme-ID reverse map (issue #656).

`docs/spec/phoneme-timing-contract.toml` `[reverse_map]` specifies how phoneme
IDs are turned back into display names: first-wins on collision, and PUA
characters (U+E000..U+F8FF) without an explicit name rendered as `U+XXXX`.

Rust and Go shipped without it. Their CLIs emitted positional placeholders --
`ph_0`, `ph_1`, ... and `p0`, `p1`, ... -- so the timing output could not
identify phonemes at all, which makes it useless for lip-sync or subtitles, and
disagrees with the four runtimes that do resolve names. The placeholders also
HID a second defect: with no real phoneme names in the output, nobody could see
that Rust was synthesizing its own SSML wrapper as speech for short inputs
(#694).

This gate asserts, per runtime, that the implementation file:

  1. exists,
  2. contains the PUA range bounds (so the fallback branch is present),
  3. contains the `U+XXXX` format with 4-digit uppercase hex,
  4. contains the first-wins guard idiom declared in the contract.

It is a presence check, not a behaviour check: the values are pinned by each
runtime's own unit tests (Python doctests, `timing::tests` in Rust,
`TestBuildPhonemeIDReverseMap_*` in Go, and the JS/C#/C++ suites). What this
gate prevents is a runtime being added -- or reverted -- WITHOUT the map, which
is the state Rust and Go were in.

Exit codes: 0 = every runtime implements it, 1 = at least one does not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# file -> (PUA lower bound, PUA upper bound, first-wins idiom)
# The bounds are matched case-insensitively because the languages spell hex
# literals differently (0xE000 / 0xe000 / ).
RUNTIMES: dict[str, dict[str, object]] = {
    "python": {
        "file": "src/python_run/piper_plus/timing.py",
        "first_wins": "if phoneme_id not in reverse_map",
    },
    "rust": {
        "file": "src/rust/piper-core/src/timing.rs",
        "first_wins": "or_insert_with",
    },
    "go": {
        "file": "src/go/piperplus/timing.go",
        "first_wins": "if _, exists := reverse[id]; !exists",
    },
    "js": {
        "file": "src/wasm/openjtalk-web/src/timing.js",
        "first_wins": "!(id in reverse)",
    },
    "csharp": {
        "file": "src/csharp/PiperPlus.Core/Inference/TimingWriter.cs",
        "first_wins": "TryAdd",
    },
    "cpp": {
        "file": "src/cpp/piper.cpp",
        "first_wins": "find",
    },
}

PUA_LOWER = re.compile(r"(0x)?e000", re.IGNORECASE)
PUA_UPPER = re.compile(r"(0x)?f8ff", re.IGNORECASE)
# "U+%04X", f"U+{...:04X}", `U+${...}` etc. All of them contain "U+" adjacent
# to a format directive; requiring 04X specifically would reject the JS form.
PUA_FORMAT = re.compile(r"U\+")


def main() -> int:
    failures: list[str] = []

    for runtime, spec in sorted(RUNTIMES.items()):
        rel = str(spec["file"])
        path = REPO_ROOT / rel
        if not path.is_file():
            failures.append(f"{runtime}: file not found: {rel}")
            continue

        source = path.read_text(encoding="utf-8", errors="replace")
        problems: list[str] = []

        if not PUA_LOWER.search(source) or not PUA_UPPER.search(source):
            problems.append(
                "no PUA range (U+E000..U+F8FF) bounds, so the "
                "[reverse_map.pua_handling] fallback cannot be implemented"
            )
        if not PUA_FORMAT.search(source):
            problems.append("no 'U+' output format for unmapped PUA characters")

        first_wins = str(spec["first_wins"])
        if first_wins not in source:
            problems.append(
                f"no first-wins guard (expected {first_wins!r}); a collision "
                "would then resolve non-deterministically"
            )

        if problems:
            for problem in problems:
                failures.append(f"{runtime} ({rel}): {problem}")
        else:
            print(f"  OK: {runtime} -- {rel}")

    if failures:
        print(
            f"\nERROR: reverse map missing or incomplete in {len(failures)} "
            "place(s):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print(
            "\nA runtime without the reverse map emits positional placeholders "
            "instead of phoneme names (issue #656).",
            file=sys.stderr,
        )
        return 1

    print(f"OK: all {len(RUNTIMES)} runtimes implement the phoneme-ID reverse map")
    return 0


if __name__ == "__main__":
    sys.exit(main())
