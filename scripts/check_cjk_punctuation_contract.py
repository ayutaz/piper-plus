#!/usr/bin/env python3
"""Gate for docs/spec/cjk-punctuation-contract.toml (Issue #823).

Fails when
  * tests/fixtures/g2p/cjk_punctuation_cases.json is not what
    scripts/build_cjk_punctuation_fixture.py builds from the contract, or
  * a test listed in [consumers].tests is missing or no longer reads the
    fixture, so a runtime could drift from the contract without a failing
    test.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_cjk_punctuation_fixture as fixture  # noqa: E402


FIXTURE_NAME = "cjk_punctuation_cases.json"


def consumer_problems(contract: dict, root: Path = REPO_ROOT) -> list[str]:
    problems: list[str] = []
    tests = contract.get("consumers", {}).get("tests", [])
    if not tests:
        problems.append("[consumers].tests is empty")
    for rel in tests:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: listed in [consumers].tests but does not exist")
        elif FIXTURE_NAME not in path.read_text(encoding="utf-8"):
            problems.append(f"{rel}: does not read {FIXTURE_NAME}")
    return problems


def main() -> int:
    problems: list[str] = []
    if fixture.main(["--check"]) != 0:
        problems.append(f"{FIXTURE_NAME} is out of date")
    contract = tomllib.loads(fixture.CONTRACT.read_text(encoding="utf-8"))
    problems += consumer_problems(contract)
    for p in problems:
        print(f"ERROR: {p}", file=sys.stderr)
    if problems:
        return 1
    print("OK: CJK punctuation contract, fixture and consumers agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
