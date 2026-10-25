#!/usr/bin/env python3
"""Fail CI when a test is skipped without a reason in the allowlist.

A skipped test is reported as a pass by most runners, so a test whose
fixture, dictionary or dependency is missing in CI checks nothing while the
job stays green. Every skip seen in CI must match an entry of
docs/spec/test-skip-allowlist.toml; ``tracked`` entries (tests that should
run in CI) also carry an expiry date.

Usage:
    check_test_skips.py check --runtime RUNTIME --platform PLATFORM FILE...
    check_test_skips.py list --runtime RUNTIME FILE...
    check_test_skips.py validate

RUNTIME selects how FILE is read:
    python  JSON lines written by scripts/pytest_plugins/piper_plus_skip_log.py
    go      ``go test -v`` output (``--- SKIP: TestName``)
    cpp     ctest / GoogleTest output (``[  SKIPPED ] Suite.Test (0 ms)``)
    csharp  TRX files from ``dotnet test --logger trx``
    rust    ``cargo test`` output (``test name ... ignored``)

PLATFORM is ``linux``, ``macos`` or ``windows`` (``runner.os`` lowercased);
an entry with ``platforms`` only applies there.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import glob
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = REPO_ROOT / "docs" / "spec" / "test-skip-allowlist.toml"

RUNTIMES = ("python", "go", "cpp", "csharp", "rust")
PLATFORMS = ("linux", "macos", "windows")
KINDS = ("harmless", "tracked")
FIELDS = {"runtime", "test", "kind", "reason", "expires", "platforms"}


@dataclass(frozen=True)
class Skip:
    test: str
    reason: str


# --- parsers ------------------------------------------------------------------


def parse_python(text: str) -> list[Skip]:
    skips = []
    for line in text.splitlines():
        if line.strip():
            record = json.loads(line)
            skips.append(Skip(record["test"], record.get("reason", "")))
    return skips


_GO_SKIP = re.compile(r"^\s*--- SKIP: (\S+) \(")
_GO_RESULT = re.compile(r"^\s*--- (?:PASS|FAIL|SKIP): ")
_GO_MESSAGE = re.compile(r"^\s+\S+\.go:\d+: (.*)$")


def parse_go(text: str) -> list[Skip]:
    # `go test -v` prints the t.Skip message before the `--- SKIP` line; for
    # a subtest the parent's `--- PASS` line can sit in between.
    lines = text.splitlines()
    skips = []
    for i, line in enumerate(lines):
        m = _GO_SKIP.match(line)
        if m:
            reason = ""
            j = i - 1
            while j >= 0 and _GO_RESULT.match(lines[j]):
                j -= 1
            if j >= 0 and (msg := _GO_MESSAGE.match(lines[j])):
                reason = msg[1]
            skips.append(Skip(m[1], reason))
    return skips


# ctest -V prefixes each line with "<test number>: ". The gtest summary at the
# end lists the same tests again without a duration, so it is not matched.
_GTEST_SKIP = re.compile(r"\[  SKIPPED \] (\S+\.\S+) \(\d+ ms\)")
# A whole ctest test skipped (SKIP_RETURN_CODE / SKIP_REGULAR_EXPRESSION).
_CTEST_SKIP = re.compile(r"Test\s+#\d+: (\S+) \.+\s*\*+Skipped")


def parse_cpp(text: str) -> list[Skip]:
    return [Skip(m[1], "") for m in _GTEST_SKIP.finditer(text)] + [
        Skip(m[1], "ctest") for m in _CTEST_SKIP.finditer(text)
    ]


def parse_csharp(text: str) -> list[Skip]:
    root = ET.fromstring(text)
    skips = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "UnitTestResult" and el.get("outcome") == "NotExecuted":
            reason = " ".join(
                (sub.text or "").strip()
                for sub in el.iter()
                if sub.tag.rsplit("}", 1)[-1] in ("Message", "StdOut") and (sub.text or "").strip()
            )
            skips.append(Skip(el.get("testName", ""), reason))
    return skips


_RUST_IGNORED = re.compile(r"^test (.+?) \.\.\. ignored(?:, (.*))?$")


def parse_rust(text: str) -> list[Skip]:
    skips = []
    for line in text.splitlines():
        m = _RUST_IGNORED.match(line.strip())
        if m:
            skips.append(Skip(m[1], m[2] or ""))
    return skips


PARSERS = {
    "python": parse_python,
    "go": parse_go,
    "cpp": parse_cpp,
    "csharp": parse_csharp,
    "rust": parse_rust,
}


def expand(patterns: list[str]) -> list[Path]:
    """Expand glob patterns; a pattern matching nothing is an error.

    The tests may not have run at all, and an absent log must not read as
    "nothing was skipped".
    """
    files = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern, recursive=True)) if glob.has_magic(pattern) else [pattern]
        matches = [m for m in matches if Path(m).is_file()]
        if not matches:
            raise SystemExit(f"error: no test output at {pattern} (did the tests run?)")
        files.extend(Path(m) for m in matches)
    return files


def read_skips(runtime: str, files: list[Path]) -> list[Skip]:
    skips = []
    for path in files:
        skips.extend(PARSERS[runtime](path.read_text(encoding="utf-8", errors="replace")))
    return skips


# --- allowlist ----------------------------------------------------------------


def load_entries(spec: Path) -> list[dict]:
    return tomllib.loads(spec.read_text(encoding="utf-8")).get("entry", [])


def validate(entries: list[dict]) -> list[str]:
    problems = []
    seen = set()
    for i, e in enumerate(entries, 1):
        where = f"entry {i} ({e.get('runtime')} / {e.get('test')})"
        if unknown := set(e) - FIELDS:
            problems.append(f"{where}: unknown field(s) {sorted(unknown)}")
        if e.get("runtime") not in RUNTIMES:
            problems.append(f"{where}: runtime must be one of {RUNTIMES}")
        if not e.get("test"):
            problems.append(f"{where}: test is empty")
        if not str(e.get("reason", "")).strip():
            problems.append(f"{where}: reason is empty")
        kind = e.get("kind")
        if kind not in KINDS:
            problems.append(f"{where}: kind must be one of {KINDS}")
        if kind == "tracked" and not isinstance(e.get("expires"), str):
            problems.append(f"{where}: a tracked entry needs expires = \"YYYY-MM-DD\"")
        if kind == "harmless" and "expires" in e:
            problems.append(f"{where}: a harmless entry has no expires")
        if "expires" in e:
            try:
                dt.date.fromisoformat(str(e["expires"]))
            except ValueError:
                problems.append(f"{where}: expires is not YYYY-MM-DD")
        for p in e.get("platforms", []):
            if p not in PLATFORMS:
                problems.append(f"{where}: platform {p!r} is not one of {PLATFORMS}")
        key = (e.get("runtime"), e.get("test"), tuple(e.get("platforms", [])))
        if key in seen:
            problems.append(f"{where}: duplicate entry")
        seen.add(key)
    return problems


def _applies(entry: dict, runtime: str, platform: str) -> bool:
    return entry.get("runtime") == runtime and (not entry.get("platforms") or platform in entry["platforms"])


def check(
    runtime: str,
    platform: str,
    skips: list[Skip],
    entries: list[dict],
    today: dt.date,
) -> list[str]:
    problems = validate(entries)
    if problems:
        return problems
    applicable = [e for e in entries if _applies(e, runtime, platform)]
    for e in applicable:
        if e["kind"] == "tracked" and dt.date.fromisoformat(e["expires"]) < today:
            problems.append(
                f"allowlist entry for {e['test']!r} expired on {e['expires']}: make the test run, "
                "or extend the date with a new reason"
            )
    for skip in sorted(set(skips), key=lambda s: s.test):
        if not any(skip.test == e["test"] or fnmatch.fnmatchcase(skip.test, e["test"]) for e in applicable):
            detail = f" ({skip.reason})" if skip.reason else ""
            problems.append(f"skipped without an allowlist entry: {skip.test}{detail}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, default=SPEC)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "list"):
        p = sub.add_parser(name)
        p.add_argument("--runtime", choices=RUNTIMES, required=True)
        p.add_argument("files", nargs="+", help="test output files or glob patterns")
        if name == "check":
            # type=str.lower takes $RUNNER_OS (Linux, macOS, Windows) as is.
            p.add_argument("--platform", type=str.lower, choices=PLATFORMS, required=True)
            p.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    sub.add_parser("validate")
    args = parser.parse_args(argv)

    if args.command == "list":
        for skip in sorted(set(read_skips(args.runtime, expand(args.files))), key=lambda s: s.test):
            print(f"{skip.test}\t{skip.reason}")
        return 0
    entries = load_entries(args.spec)
    if args.command == "validate":
        problems = validate(entries)
    else:
        skips = read_skips(args.runtime, expand(args.files))
        problems = check(args.runtime, args.platform, skips, entries, args.today)
        print(f"{len(skips)} skipped test result(s), {len(set(skips))} distinct")
    for problem in problems:
        print(f"::error::{problem}")
    if problems:
        print(f"Add an entry to {SPEC.relative_to(REPO_ROOT).as_posix()} or make the test run.", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
