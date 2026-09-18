#!/usr/bin/env python3
"""SRT millisecond rounding must stay half-away-from-zero in all 6 runtimes.

Issue #681: `docs/spec/phoneme-timing-contract.toml` specified the SRT
timestamp FORMAT but not its ROUNDING, and the language default differs.
Python's `round()` and .NET's `Math.Round(double)` round half to EVEN, while
Rust `f64::round`, Go `math.Round`, JS `Math.round` and the C++
`(long long)(ms + 0.5)` idiom all round half away from zero. Python and C#
reached for the default and emitted a timestamp 1 ms earlier than the other
four runtimes on every `.5` boundary -- Python's own doctest pinned the wrong
value as expected output.

Nothing caught it: there is no SRT parity fixture (the golden matrix carries
millisecond numbers, not formatted output), and every runtime's own SRT tests
used values whose fractional part was not `.5`.

This gate reads `[output_formats.srt].rounding_impl` and, per runtime,
asserts the formatter file:

  1. exists,
  2. contains the declared idiom (so the correct rounding is still there),
  3. contains none of the runtime's forbidden idioms (the language defaults
     that round half to even).

Why an idiom check and not a value check: five of the six formatters are
private to their module, and the C++ one takes seconds as `float`, where no
value multiplies to exactly 1234.5 ms. Value-level pinning belongs to each
runtime's own test suite, driven by the contract's `rounding_cases`; this gate
exists to catch the one regression that produced #681 -- someone replacing the
explicit idiom with the language default.

Exit codes: 0 = every runtime keeps the canonical idiom, 1 = drift.
"""

from __future__ import annotations

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
        case
        for case in cases
        if float(case.get("ms", 0)) % 1 == 0.5 and int(float(case["ms"])) % 2 == 0
    ]
    if not discriminating:
        print(
            "ERROR: [output_formats.srt].rounding_cases has no case with a .5 "
            "fraction over an even integer, so the per-runtime test suites it "
            "drives cannot tell half-to-even from half-away-from-zero",
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

    forbidden = impl.get("forbidden_idioms", {})
    declared = {name for name in impl if name != "forbidden_idioms"}
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

        source = path.read_text(encoding="utf-8")
        if idiom not in source:
            failures.append(
                f"{runtime}: {entry['file']} no longer contains the canonical "
                f"rounding idiom {idiom!r}. If the implementation moved, update "
                "the contract's rounding_impl entry; if the rounding changed, "
                "that is issue #681 reappearing."
            )

        for bad in forbidden.get(runtime, []):
            if bad in source:
                failures.append(
                    f"{runtime}: {entry['file']} contains {bad!r}, which rounds "
                    "half to EVEN in this language and puts the SRT output 1 ms "
                    "behind the other runtimes on .5 boundaries (issue #681)"
                )

        if not any(f.startswith(f"{runtime}:") for f in failures):
            print(f"  OK: {runtime} -- {entry['file']} keeps {idiom!r}")

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
