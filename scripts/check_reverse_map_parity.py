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

A second section checks the Rust/Go CLI WIRING. Having the map is not enough:
the CLI has to decide whether the id list actually lines up with the durations,
and fall back to placeholders when it does not. That decision first landed
inline in each CLI's main(), where no test and no CI step executed either
branch -- exactly the blind spot that let the original bug ship. So the gate
requires the decision to live in the shared, unit-tested helper
(`resolve_timing_tokens` / `ResolveTimingTokens`), requires the CLI to call it,
forbids the CLI from rebuilding the reverse map itself, and requires the named
tests for both branches to exist.

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

# The token-resolution decision must live in the shared helper, not inline in
# the CLI. `forbidden_in_cli` is what inlining looks like: if the CLI builds the
# reverse map itself, it is making the alignment decision again in untested
# code. `tests` are required by name so deleting them fails the gate rather
# than silently reducing coverage to zero.
CLI_WIRING: dict[str, dict[str, object]] = {
    "rust": {
        "helper_file": "src/rust/piper-core/src/timing.rs",
        "helper_decl": "pub fn resolve_timing_tokens(",
        "guard": "duration_count > 0",
        "placeholder": 'format!("ph_{}", i)',
        "cli_file": "src/rust/piper-cli/src/main.rs",
        "cli_call": "timing::resolve_timing_tokens(",
        "forbidden_in_cli": ["build_phoneme_id_reverse_map("],
        "test_file": "src/rust/piper-core/src/timing.rs",
        "tests": [
            "resolve_timing_tokens_uses_real_phonemes_when_aligned",
            "resolve_timing_tokens_falls_back_when_counts_differ",
            "resolve_timing_tokens_treats_zero_durations_as_unresolved",
        ],
    },
    "go": {
        "helper_file": "src/go/piperplus/timing.go",
        "helper_decl": "func ResolveTimingTokens(",
        "guard": "durationCount > 0",
        "placeholder": 'fmt.Sprintf("ph_%d", i)',
        "cli_file": "src/go/cmd/piper-plus/main.go",
        "cli_call": "piperplus.ResolveTimingTokens(",
        "forbidden_in_cli": ["BuildPhonemeIDReverseMap("],
        "test_file": "src/go/piperplus/timing_test.go",
        "tests": [
            "TestResolveTimingTokens_UsesRealPhonemesWhenAligned",
            "TestResolveTimingTokens_FallsBackWhenCountsDiffer",
            "TestResolveTimingTokens_TreatsZeroDurationsAsUnresolved",
        ],
    },
}


def read(rel: str) -> str | None:
    path = REPO_ROOT / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def check_cli_wiring() -> list[str]:
    """Rust/Go: the alignment decision must be shared and unit-tested."""
    failures: list[str] = []

    for runtime, spec in sorted(CLI_WIRING.items()):
        helper_rel = str(spec["helper_file"])
        cli_rel = str(spec["cli_file"])
        test_rel = str(spec["test_file"])

        helper = read(helper_rel)
        cli = read(cli_rel)
        tests = read(test_rel)
        for rel, source in ((helper_rel, helper), (cli_rel, cli), (test_rel, tests)):
            if source is None:
                failures.append(f"{runtime}: file not found: {rel}")
        if helper is None or cli is None or tests is None:
            continue

        problems: list[str] = []

        decl = str(spec["helper_decl"])
        if decl not in helper:
            problems.append(
                f"{helper_rel}: no shared helper (expected {decl!r}); the "
                "alignment decision would be inline in the CLI, where no test "
                "reaches either branch"
            )
        guard = str(spec["guard"])
        if guard not in helper:
            problems.append(
                f"{helper_rel}: no zero-duration guard (expected {guard!r}); an "
                "empty id list trivially matches a duration count of 0, so the "
                "helper would report a broken result as resolved"
            )
        placeholder = str(spec["placeholder"])
        if placeholder not in helper:
            problems.append(
                f"{helper_rel}: no {placeholder!r} fallback label; Rust and Go "
                "must agree on the placeholder spelling"
            )

        call = str(spec["cli_call"])
        if call not in cli:
            problems.append(
                f"{cli_rel}: does not call {call!r}; the CLI must delegate the "
                "decision to the tested helper"
            )
        for forbidden in spec["forbidden_in_cli"]:  # type: ignore[union-attr]
            if str(forbidden) in cli:
                problems.append(
                    f"{cli_rel}: contains {forbidden!r}; resolving ids in the "
                    "CLI re-introduces the untested inline decision"
                )

        for test_name in spec["tests"]:  # type: ignore[union-attr]
            if str(test_name) not in tests:
                problems.append(
                    f"{test_rel}: missing test {test_name!r}; the branch it "
                    "covers would go unexercised"
                )

        if problems:
            failures.extend(f"{runtime} {problem}" for problem in problems)
        else:
            print(f"  OK: {runtime} CLI wiring -- {cli_rel} -> {helper_rel}")

    return failures



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

    failures.extend(check_cli_wiring())

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

    print(
        f"OK: all {len(RUNTIMES)} runtimes implement the phoneme-ID reverse map, "
        f"and {len(CLI_WIRING)} CLI(s) delegate token resolution to a tested helper"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
