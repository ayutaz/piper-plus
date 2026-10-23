#!/usr/bin/env python3
"""Validate the shared lists of known G2P differences between runtimes.

``tests/fixtures/g2p/phoneme_test_cases_golden.json`` holds the phonemes
Python produces. Every runtime's golden parity test compares its own output
with it and reads ``tests/fixtures/g2p/known_divergences.json`` for the cases
that are known to differ: an unlisted difference fails the test, and so does a
listed case that starts to match. ``tests/fixtures/g2p/english_no_drop_words.json``
works the same way for English words that must never phonemize to nothing.

This gate checks the lists themselves, before any runtime reads them:

* every entry names a declared runtime, a GitHub issue and a reason;
* every divergence refers to a case that exists in the golden fixture;
* no runtime lists the same case or word twice;
* every declared runtime names its parity tests, and each of them exists and
  reads ``known_divergences.json`` -- a runtime whose test was deleted or
  stopped reading the list would otherwise pass silently.

Exit codes: 0 = valid, 1 = at least one problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = Path("tests/fixtures/g2p")
GOLDEN = FIXTURE_DIR / "phoneme_test_cases_golden.json"
DIVERGENCES = FIXTURE_DIR / "known_divergences.json"
NO_DROP = FIXTURE_DIR / "english_no_drop_words.json"

STATUSES = ("planned", "accepted")


def _check_common(entry: dict[str, Any], where: str, runtimes: set[str]) -> tuple[list[str], list[str]]:
    """Problems shared by both lists, plus the entry's valid runtimes."""
    problems: list[str] = []
    listed = entry.get("runtimes")
    if not isinstance(listed, list) or not listed:
        problems.append(f"{where}: no runtimes")
        listed = []
    for runtime in listed:
        if runtime not in runtimes:
            problems.append(f"{where}: unknown runtime '{runtime}'")
    issue = entry.get("issue")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
        problems.append(f"{where}: issue must be a GitHub issue number")
    reason = entry.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append(f"{where}: reason is empty")
    return problems, [r for r in listed if isinstance(r, str)]


def validate_divergences(registry: dict[str, Any], golden: list[dict[str, Any]], repo_root: Path) -> list[str]:
    problems: list[str] = []
    if registry.get("schema_version") != 1:
        problems.append("known_divergences.json: schema_version must be 1")

    runtimes = registry.get("runtimes") or {}
    for name, spec in runtimes.items():
        tests = spec.get("tests") if isinstance(spec, dict) else None
        if not tests:
            problems.append(f"runtime '{name}' lists no tests")
            continue
        for test in tests:
            path = repo_root / test
            if not path.is_file():
                problems.append(f"runtime '{name}': {test} does not exist")
            elif DIVERGENCES.name not in path.read_text(encoding="utf-8"):
                problems.append(f"runtime '{name}': {test} does not read {DIVERGENCES.name}")

    golden_keys = {(c["language"], c["input"]) for c in golden}
    seen: set[tuple[str, str, str]] = set()
    for i, entry in enumerate(registry.get("divergences") or []):
        key = (entry.get("language"), entry.get("input"))
        where = f"divergences[{i}] [{key[0]}] '{key[1]}'"
        entry_problems, listed = _check_common(entry, where, set(runtimes))
        problems += entry_problems
        for runtime in listed:
            if (runtime, *key) in seen:
                problems.append(f"{where}: duplicate entry for runtime '{runtime}'")
            seen.add((runtime, *key))
        if key not in golden_keys:
            problems.append(f"{where}: case not in phoneme_test_cases_golden.json")
        if entry.get("status") not in STATUSES:
            problems.append(f"{where}: status must be one of {list(STATUSES)}")
    return problems


def validate_no_drop(no_drop: dict[str, Any], runtimes: set[str]) -> list[str]:
    problems: list[str] = []
    if no_drop.get("schema_version") != 1:
        problems.append("english_no_drop_words.json: schema_version must be 1")

    words = no_drop.get("words") or []
    seen_words: set[str] = set()
    for word in words:
        if word in seen_words:
            problems.append(f"words: duplicate word '{word}'")
        seen_words.add(word)

    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(no_drop.get("known_drops") or []):
        word = entry.get("word")
        where = f"known_drops[{i}] '{word}'"
        entry_problems, listed = _check_common(entry, where, runtimes)
        problems += entry_problems
        if word not in seen_words:
            problems.append(f"{where}: not in words")
        for runtime in listed:
            if (runtime, word) in seen:
                problems.append(f"{where}: duplicate entry for runtime '{runtime}'")
            seen.add((runtime, word))
    return problems


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    root: Path = args.repo_root

    registry = _load(root / DIVERGENCES)
    problems = validate_divergences(registry, _load(root / GOLDEN)["test_cases"], root)
    problems += validate_no_drop(_load(root / NO_DROP), set(registry.get("runtimes") or {}))

    if problems:
        print(f"{len(problems)} problem(s) in the G2P known-difference lists:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OK: {DIVERGENCES.as_posix()} and {NO_DROP.as_posix()} are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
