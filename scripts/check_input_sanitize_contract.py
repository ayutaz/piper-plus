#!/usr/bin/env python3
"""Every runtime strips control characters before phonemizing, the same way.

Contract: ``docs/spec/input-sanitize-contract.toml``.
Shared cases: ``tests/fixtures/g2p/input_sanitize_cases.json``.

Why this gate exists: #934 (2026-11) added C1 stripping to the Python G2P
and said it matched Rust's ``validate_input``. It did not. The Python helper
ran for ja / en / sv only, the Rust ``validate_input`` had no caller, and no
other runtime stripped anything. A rule each runtime re-implements drifts
unless something reads all of them. This gate checks:

* the fixture follows the rule it pins (``strip_cases`` recomputed from
  ``unicodedata``; every ``dirty`` strips to its ``clean``), and has a word
  for every language the contract lists;
* the fixture's mirrors equal the canonical byte for byte;
* every ``enforced`` runtime has the consumer tests the contract names, and
  each of them reads the fixture;
* every ``enforced`` entry point still calls the runtime's stripping
  function (a call removed later is caught here, not in review);
* every file the contract names is in the pre-commit hook's ``files:``,
  because a hook does not run on a change it does not watch.

``pending`` runtimes are printed on every run (``PENDING: <name>``) so an
unfinished rollout stays visible.

Exit codes: 0 = no violations, 1 = at least one violation.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import unicodedata
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = "docs/spec/input-sanitize-contract.toml"
FIXTURE_NAME = "input_sanitize_cases"
HOOK_ID = "input-sanitize-contract"
STATUSES = ("enforced", "pending")


def strip(text: str, keep: str) -> str:
    """The contract's rule: drop Unicode Cc except the characters in *keep*."""
    return "".join(
        ch for ch in text if unicodedata.category(ch) != "Cc" or ch in keep
    )


def _hook_files_regex(root: Path) -> re.Pattern[str] | None:
    """Return the ``files:`` regex of the hook, or None without a config.

    Parsed by line instead of with PyYAML so the gate runs on a bare
    ``setup-python`` (lint-gates installs nothing but pytest).
    """
    config = root / ".pre-commit-config.yaml"
    if not config.exists():
        return None
    in_hook = False
    for line in config.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            in_hook = stripped.split(":", 1)[1].strip() == HOOK_ID
            continue
        if in_hook and stripped.startswith("files:"):
            return re.compile(stripped.split(":", 1)[1].strip())
    return re.compile(r"(?!)")  # configured repo without the hook: nothing is watched


def _check_fixture(
    root: Path, fixture: dict, keep: str, languages: list[str]
) -> list[str]:
    errors: list[str] = []
    canonical = fixture.get("canonical", "")
    path = root / canonical
    if not path.exists():
        return [f"{CONTRACT}: fixture {canonical} does not exist"]
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = path.read_bytes()

    for mirror in fixture.get("mirrors", []):
        mpath = root / mirror
        if not mpath.exists():
            errors.append(f"{mirror}: mirror of {canonical} is missing")
        elif mpath.read_bytes() != raw:
            errors.append(f"{mirror}: differs from {canonical} (copy the canonical)")

    for case in data.get("strip_cases", []):
        want = strip(case["input"], keep)
        if case["expected"] != want:
            errors.append(
                f"{canonical}: strip_cases[{case['name']}] expects "
                f"{case['expected']!r}, the rule gives {want!r}"
            )

    for group in ("word_cases", "pipeline_cases"):
        for case in data.get(group, []):
            label = case.get("language") or case.get("name")
            if strip(case["dirty"], keep) != case["clean"]:
                errors.append(
                    f"{canonical}: {group}[{label}] dirty does not strip to clean"
                )

    have = {case["language"] for case in data.get("word_cases", [])}
    for lang in languages:
        if lang not in have:
            errors.append(
                f"{canonical}: no word_cases entry for language '{lang}' "
                f"(add a word for every language in {CONTRACT})"
            )
    return errors


def _check_runtime(root: Path, runtime: dict) -> list[str]:
    name = runtime.get("name", "?")
    status = runtime.get("status")
    if status not in STATUSES:
        return [f"{CONTRACT}: runtime {name} has status {status!r}, expected one of {STATUSES}"]
    if status != "enforced":
        return []

    errors: list[str] = []
    tests = runtime.get("consumer_tests", [])
    if not tests:
        errors.append(f"{CONTRACT}: runtime {name} is enforced but lists no consumer_tests")
    for test in tests:
        tpath = root / test
        if not tpath.exists():
            errors.append(f"{test}: consumer test of {name} does not exist")
        elif FIXTURE_NAME not in tpath.read_text(encoding="utf-8"):
            errors.append(f"{test}: consumer test of {name} does not read {FIXTURE_NAME}")

    for entry in runtime.get("entry_points", []):
        epath = root / entry["file"]
        call = re.compile(rf"\b{re.escape(entry['calls'])}\s*\(")
        if not epath.exists():
            errors.append(f"{entry['file']}: entry point of {name} does not exist")
        elif not call.search(epath.read_text(encoding="utf-8")):
            errors.append(
                f"{entry['file']}: entry point of {name} no longer calls {entry['calls']}()"
            )
    return errors


def _contract_paths(contract: dict) -> list[str]:
    fixture = contract.get("fixture", {})
    paths = [CONTRACT, fixture.get("canonical", ""), *fixture.get("mirrors", [])]
    for runtime in contract.get("runtime", []):
        paths += runtime.get("consumer_tests", [])
        paths += [e["file"] for e in runtime.get("entry_points", [])]
    return [p for p in paths if p]


def check(root: Path) -> list[str]:
    """Return one message per violation; empty when the contract holds."""
    cpath = root / CONTRACT
    if not cpath.exists():
        return [f"{CONTRACT} does not exist"]
    contract = tomllib.loads(cpath.read_text(encoding="utf-8"))
    keep = "".join(contract.get("rule", {}).get("keep", []))
    fixture = contract.get("fixture", {})

    errors = _check_fixture(root, fixture, keep, fixture.get("languages", []))
    for runtime in contract.get("runtime", []):
        errors += _check_runtime(root, runtime)

    files = _hook_files_regex(root)
    if files is not None:
        for path in _contract_paths(contract):
            if not files.match(path):
                errors.append(
                    f"{path}: not in the files: of the {HOOK_ID} pre-commit hook, "
                    "so a change to it never runs this gate"
                )
    return errors


def pending(root: Path) -> list[str]:
    contract = tomllib.loads((root / CONTRACT).read_text(encoding="utf-8"))
    return [
        r.get("name", "?")
        for r in contract.get("runtime", [])
        if r.get("status") == "pending"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    errors = check(args.root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if (args.root / CONTRACT).exists():
        for name in pending(args.root):
            print(f"PENDING: {name} (does not strip control characters yet)")
    if errors:
        return 1
    print("input-sanitize contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
