#!/usr/bin/env python3
"""Mutation testing targets, CI matrix and score gate.

docs/spec/mutation-testing.toml lists every mutation target with the
tests that are run against it and the `break` score below which the
weekly run fails. This script

* prints the CI matrix for one runtime (``matrix python``), so the
  workflow and the spec cannot list different targets,
* checks one finished run against its target's ``break`` score
  (``score python <module> <.mutmut-cache>``, ``score rust <module>
  <outcomes.json>``, ``score csharp <module> <mutation-report.json>``).

Score = detected / (detected + undetected), where *detected* is killed or
timed out (an infinite loop is a failure the tests notice) and
*undetected* is survived, suspicious (mutmut: the tests passed, only
slower) or not covered (Stryker). Mutants that do not compile are left
out. A run that did not test every mutant fails: a crash must not read as
a good score.

Usage:
    uv run python scripts/check_mutation_score.py matrix python
    uv run python scripts/check_mutation_score.py score python text_splitter .mutmut-cache
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tomllib
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "docs" / "spec" / "mutation-testing.toml"
RUNTIMES = ("python", "rust", "csharp")


def load_targets(spec: Path = SPEC) -> dict[str, list[dict]]:
    data = tomllib.loads(spec.read_text(encoding="utf-8"))
    return {runtime: data.get(runtime, []) for runtime in RUNTIMES}


def find_target(runtime: str, module: str, spec: Path = SPEC) -> dict:
    for target in load_targets(spec)[runtime]:
        if target["module"] == module:
            return target
    raise SystemExit(f"ERROR: no {runtime} target named {module!r} in {spec.name}")


# --- counting -----------------------------------------------------------------


def count_mutmut(cache: Path) -> tuple[int, int, list[str]]:
    """mutmut 2.x stores one row per mutant in the SQLite `.mutmut-cache`."""
    con = sqlite3.connect(cache)
    try:
        statuses = Counter(dict(con.execute("select status, count(*) from Mutant group by status")))
    finally:
        con.close()
    problems = []
    if not statuses:
        problems.append("no mutants were generated")
    if statuses.get("untested"):
        problems.append(f"{statuses['untested']} mutants were never tested")
    detected = statuses["ok_killed"] + statuses["bad_timeout"]
    undetected = statuses["bad_survived"] + statuses["ok_suspicious"]
    # `skipped`: lines marked `# pragma: no mutate`, left out like a compile error.
    unknown = set(statuses) - {"ok_killed", "bad_timeout", "bad_survived", "ok_suspicious", "untested", "skipped"}
    if unknown:
        problems.append(f"unknown mutmut statuses {sorted(unknown)}")
    return detected, undetected, problems


def count_cargo_mutants(outcomes: Path) -> tuple[int, int, list[str]]:
    data = json.loads(outcomes.read_text(encoding="utf-8"))
    problems = []
    tested = data["caught"] + data["missed"] + data["timeout"] + data["unviable"]
    if data["total_mutants"] == 0:
        problems.append("no mutants were generated")
    if tested != data["total_mutants"]:
        problems.append(f"only {tested} of {data['total_mutants']} mutants were tested")
    return data["caught"] + data["timeout"], data["missed"], problems


STRYKER_DETECTED = {"Killed", "Timeout"}
STRYKER_UNDETECTED = {"Survived", "NoCoverage"}
STRYKER_EXCLUDED = {"CompileError", "Ignored"}


def count_stryker(report: Path) -> tuple[int, int, list[str]]:
    data = json.loads(report.read_text(encoding="utf-8"))
    statuses = Counter(m["status"] for f in data["files"].values() for m in f["mutants"])
    problems = []
    if not statuses:
        problems.append("no mutants were generated")
    unknown = set(statuses) - STRYKER_DETECTED - STRYKER_UNDETECTED - STRYKER_EXCLUDED
    if unknown:
        # Pending / RuntimeError: the run did not finish testing every mutant.
        problems.append(f"mutants with status {sorted(unknown)}: {sum(statuses[s] for s in unknown)}")
    detected = sum(statuses[s] for s in STRYKER_DETECTED)
    undetected = sum(statuses[s] for s in STRYKER_UNDETECTED)
    return detected, undetected, problems


COUNTERS = {"python": count_mutmut, "rust": count_cargo_mutants, "csharp": count_stryker}


def check_score(runtime: str, module: str, result: Path, spec: Path = SPEC) -> list[str]:
    target = find_target(runtime, module, spec)
    detected, undetected, problems = COUNTERS[runtime](result)
    total = detected + undetected
    score = 100.0 * detected / total if total else 0.0
    print(f"{runtime} {module}: {detected}/{total} detected = {score:.1f}% (break {target['break']})")
    if total == 0 and not problems:
        problems.append("no mutant was tested")
    if score < target["break"]:
        problems.append(
            f"score {score:.1f}% is below break {target['break']}; add or strengthen tests for the "
            "survived mutants (see the report artifact)"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", type=Path, default=SPEC)
    sub = ap.add_subparsers(dest="command", required=True)
    m = sub.add_parser("matrix", help="print the CI matrix (JSON) for one runtime")
    m.add_argument("runtime", choices=RUNTIMES)
    s = sub.add_parser("score", help="check a finished run against its break score")
    s.add_argument("runtime", choices=RUNTIMES)
    s.add_argument("module")
    s.add_argument("result", type=Path, help=".mutmut-cache / outcomes.json / mutation-report.json")
    args = ap.parse_args(argv)

    if args.command == "matrix":
        print(json.dumps({"include": load_targets(args.spec)[args.runtime]}))
        return 0
    problems = check_score(args.runtime, args.module, args.result, args.spec)
    for problem in problems:
        print(f"::error::{args.runtime} {args.module}: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
