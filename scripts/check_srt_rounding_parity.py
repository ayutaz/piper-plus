#!/usr/bin/env python3
"""SRT millisecond rounding must stay half-away-from-zero in all 6 runtimes.

Issue #681: `docs/spec/phoneme-timing-contract.toml` specified the SRT
timestamp FORMAT but not its ROUNDING, and the language default differs.
Python's `round()` and .NET's `Math.Round(double)` round half to EVEN, while
Rust `f64::round`, Go `math.Round` and JS `Math.round` round half away from
zero. Python and C# reached for the default and emitted a timestamp 1 ms
earlier than the other four runtimes on every `.5` boundary -- Python's own
doctest pinned the wrong value as expected output.

Nothing caught it: there is no SRT parity fixture (the golden matrix carries
millisecond numbers, not formatted output), and every runtime's own SRT tests
used values whose fractional part was not `.5`.

A second, subtler idiom is also forbidden. `floor(ms + 0.5)` looks like the
obvious replacement for a banker's `round`, but adding 0.5 can round up in
binary64: at `ms = 0.49999999999999994` the sum is exactly `1.0`, so the idiom
yields 1 where a true `round()` yields 0. That is the counterexample ECMA-262
cites for `Math.round`.

This gate reads `[output_formats.srt].rounding_impl` and, per runtime, asserts:

  1. the formatter file exists,
  2. it contains the declared idiom -- searched with COMMENTS STRIPPED, so
     leaving the idiom in a comment while changing the code does not pass,
  3. it contains none of the runtime's forbidden patterns (regexes, also
     comment-stripped, so `round(ms, 0)` cannot hide behind `round(ms)` not
     being a substring),
  4. it contains the declared clamp idiom, where one is declared (Rust relies
     on a saturating cast and is the documented exception),
  5. the runtime's own test file pins every DISCRIMINATING contract case, so a
     table quietly retuned to values both rounding rules agree on fails here
     instead of passing vacuously.

Why not compare values directly: five of the six formatters are private to
their module, and the C++ one takes seconds as `float`, where no value
multiplies to exactly 1234.5 ms. Value-level execution belongs to each
runtime's own test suite; this gate makes sure those suites keep their teeth.

Exit codes: 0 = every runtime keeps the canonical idiom, 1 = drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover - older interpreters
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "spec" / "phoneme-timing-contract.toml"

EXPECTED_RUNTIMES = {"python", "csharp", "rust", "go", "js", "cpp"}
EXPECTED_ROUNDING = "half_away_from_zero"

# Line-comment syntax per runtime. Block comments are not stripped: none of the
# six formatters uses one around the rounding site, and a half-stripped file
# would be worse than an unstripped one.
LINE_COMMENT = {
    "python": "#",
    "csharp": "//",
    "rust": "//",
    "go": "//",
    "js": "//",
    "cpp": "//",
}


def strip_prose(source: str, runtime: str) -> str:
    """Remove comments (and Python docstrings) so prose cannot satisfy the gate.

    Both directions matter. An idiom left in a comment while the code changed
    must NOT count as present, and a forbidden pattern merely DESCRIBED in
    prose must NOT count as used -- these files necessarily spell out the
    idioms they document, so an unstripped search reports the docstring.

    Deliberately naive about string literals in the comment pass: none of the
    six formatters contains a comment marker inside a string near the rounding
    site. Python triple-quoted blocks are stripped explicitly because that is
    where the explanation of the forbidden idiom lives.
    """
    if runtime == "python":
        # Drop docstrings: they name both the canonical and the forbidden
        # idiom, so leaving them in makes the forbidden-pattern search
        # report the explanation rather than the code.
        source = re.sub(r'["]{3}(?:.|\n)*?["]{3}', "", source)

    marker = LINE_COMMENT[runtime]
    kept = []
    for line in source.splitlines():
        index = line.find(marker)
        kept.append(line if index < 0 else line[:index])
    return "\n".join(kept)


def is_discriminating(ms: float) -> bool:
    """Would half-to-even and half-away-from-zero disagree on this value?

    True for a .5 fraction over an even integer part, and for the
    largest-double-below-.5 case that separates a true round() from
    floor(ms + 0.5).
    """
    if ms % 1 == 0.5 and int(ms) % 2 == 0:
        return True
    return 0.0 < ms % 1 < 0.5 and ms % 1 + 0.5 >= 1.0


def main() -> int:
    if not CONTRACT.is_file():
        print(f"ERROR: contract not found: {CONTRACT}", file=sys.stderr)
        return 1

    data = tomllib.loads(CONTRACT.read_text(encoding="utf-8"))
    try:
        srt = data["output_formats"]["srt"]
    except KeyError:
        print(
            "ERROR: [output_formats.srt] is missing from the contract",
            file=sys.stderr,
        )
        return 1

    rounding = srt.get("rounding")
    if rounding != EXPECTED_ROUNDING:
        print(
            f"ERROR: [output_formats.srt].rounding is {rounding!r}, expected "
            f"{EXPECTED_ROUNDING!r}. This gate and six runtime test suites were "
            "written against that rule; changing it is a spec_version-level "
            "decision, not a config tweak.",
            file=sys.stderr,
        )
        return 1

    cases = srt.get("rounding_cases") or []
    # Anti-vacuity: the table must contain a case where the two rounding rules
    # actually disagree, i.e. a .5 fraction over an EVEN integer part.
    discriminating = [
        case for case in cases if is_discriminating(float(case.get("ms", 0)))
    ]
    if not discriminating:
        print(
            "ERROR: [output_formats.srt].rounding_cases has no case with a .5 "
            "fraction over an even integer, so the per-runtime test suites it "
            "drives cannot tell half-to-even from half-away-from-zero",
            file=sys.stderr,
        )
        return 1

    negative_input = srt.get("negative_input")
    if negative_input != "clamp_to_zero_before_rounding":
        print(
            f"ERROR: [output_formats.srt].negative_input is {negative_input!r}, "
            "expected 'clamp_to_zero_before_rounding'. Without the clamp the two "
            "rounding idioms in use (half-up and half-away-from-zero) diverge on "
            "negative input, and JS leaked the sign into every timestamp field "
            "(issue #681).",
            file=sys.stderr,
        )
        return 1

    if not srt.get("negative_cases"):
        print(
            "ERROR: [output_formats.srt].negative_cases is missing or empty, so "
            "no runtime's clamp is pinned by the contract",
            file=sys.stderr,
        )
        return 1

    impl = srt.get("rounding_impl")
    if not impl:
        print(
            "ERROR: [output_formats.srt.rounding_impl] is missing",
            file=sys.stderr,
        )
        return 1

    forbidden = impl.get("forbidden_patterns", {})
    declared = {name for name in impl if name != "forbidden_patterns"}
    if declared != EXPECTED_RUNTIMES:
        missing = EXPECTED_RUNTIMES - declared
        extra = declared - EXPECTED_RUNTIMES
        print(
            "ERROR: rounding_impl does not cover exactly the 6 runtimes"
            + (f"; missing: {sorted(missing)}" if missing else "")
            + (f"; unexpected: {sorted(extra)}" if extra else ""),
            file=sys.stderr,
        )
        return 1

    failures: list[str] = []
    for runtime in sorted(declared):
        entry = impl[runtime]
        path = REPO_ROOT / entry["file"]
        idiom = entry["idiom"]

        if not path.is_file():
            failures.append(f"{runtime}: formatter file not found: {entry['file']}")
            continue

        raw = path.read_text(encoding="utf-8")
        source = strip_prose(raw, runtime)
        if idiom not in source:
            failures.append(
                f"{runtime}: {entry['file']} no longer contains the canonical "
                f"rounding idiom {idiom!r}. If the implementation moved, update "
                "the contract's rounding_impl entry; if the rounding changed, "
                "that is issue #681 reappearing."
            )

        clamp_idiom = entry.get("clamp_idiom")
        if clamp_idiom and clamp_idiom not in source:
            failures.append(
                f"{runtime}: {entry['file']} no longer contains the clamp "
                f"{clamp_idiom!r}. Without it a negative millisecond leaks its "
                "sign into every timestamp field -- JS emitted "
                '"-1:-1:-2,-500" before #681.'
            )

        for pattern in forbidden.get(runtime, []):
            if re.search(pattern, source):
                failures.append(
                    f"{runtime}: {entry['file']} matches the forbidden rounding "
                    f"pattern {pattern!r}. Either it rounds half to EVEN, or it "
                    "is the floor(ms + 0.5) idiom that disagrees with a true "
                    "round() at ms = 0.49999999999999994 (issue #681)"
                )

        test_rel = entry.get("test_file")
        if test_rel:
            test_path = REPO_ROOT / test_rel
            if not test_path.is_file():
                failures.append(
                    f"{runtime}: declared test_file not found: {test_rel}"
                )
            elif entry.get("test_reads_contract"):
                # This suite loads rounding_cases from the contract, so pinning
                # literals here would duplicate the fixture.
                if "rounding_cases" not in test_path.read_text(encoding="utf-8"):
                    failures.append(
                        f"{runtime}: {test_rel} is declared as reading the "
                        "contract but does not reference rounding_cases"
                    )
            elif entry.get("test_uses_float_seconds"):
                # PhonemeInfo stores float seconds; the contract's ms values are
                # unreachable, so require the guard that keeps ITS fixture on a
                # .5 boundary instead.
                test_source = test_path.read_text(encoding="utf-8")
                if "ASSERT_DOUBLE_EQ" not in test_source:
                    failures.append(
                        f"{runtime}: {test_rel} must keep the ASSERT_DOUBLE_EQ "
                        "guard proving its float fixture lands on a .5 ms "
                        "boundary, otherwise the cases stop discriminating"
                    )
            else:
                test_source = test_path.read_text(encoding="utf-8")
                # Match on the INPUT literal, not the expected timestamp: a
                # discriminating case can share its timestamp with a sanity case
                # (0.49999999999999994 and 0.0 both render 00:00:00,000), so the
                # timestamp alone would be satisfied without testing the value.
                applicable = [
                    case
                    for case in discriminating
                    if not (
                        case.get("requires_float64")
                        and entry.get("formatter_precision") == "float32"
                    )
                ]
                missing = [
                    repr(float(case["ms"]))
                    for case in applicable
                    if repr(float(case["ms"])) not in test_source
                ]
                if missing:
                    failures.append(
                        f"{runtime}: {test_rel} does not exercise the "
                        f"discriminating input(s) {missing}. Without them the "
                        "suite passes under either rounding rule"
                    )

        if not any(f.startswith(f"{runtime}: ") for f in failures):
            detail = f"keeps {idiom!r}"
            if clamp_idiom:
                detail += f" + clamp {clamp_idiom!r}"
            print(f"  OK: {runtime} -- {entry['file']} {detail}")

    if failures:
        print(
            f"\nERROR: SRT rounding drift in {len(failures)} place(s):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(
        f"OK: all {len(declared)} runtimes keep half-away-from-zero SRT rounding "
        f"({len(discriminating)} discriminating contract case(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
