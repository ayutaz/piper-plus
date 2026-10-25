#!/usr/bin/env python3
"""Check that python-tests.yml selects every test in src/python/tests.

python-tests.yml runs ``src/python/tests`` only through ``pytest -m <expr>``
steps. A test outside every expression is collected and deselected by all of
them, so it never runs: 274 tests (25 files) were in that state, including
the Super-MAS dispatch guard and a speaker-encoder golden check that had been
failing unseen (#857).

This script reads the ``-m`` expressions of the Unix steps that run
``pytest tests/`` from ``src/python``, asks pytest itself to collect each one
(``--collect-only``), and fails if their union is not the full collection.
``src/python/tests/conftest.py`` makes the full collection fail for a test
with no ``unit`` / ``integration`` / ``benchmark`` marker, which this script
reports as a failure too.

Usage (from the repository root, in an environment with the train extras)::

    python scripts/check_python_test_selection.py
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"
TEST_ROOT = REPO_ROOT / "src" / "python"

# `pytest tests/ ... -m "<expr>"` inside a step that first does `cd src/python`.
_PYTEST_TESTS = re.compile(r"pytest tests/\s.*?-m \"([^\"]+)\"", re.S)


def extract_expressions(workflow: dict) -> list[str]:
    """``-m`` expressions of the non-Windows steps that run src/python/tests."""
    expressions: list[str] = []
    for job in workflow.get("jobs", {}).values():
        for step in job.get("steps", []):
            run = step.get("run") or ""
            if "cd src/python\n" not in run:
                continue
            if "runner.os == 'Windows'" in str(step.get("if", "")):
                continue
            expressions.extend(_PYTEST_TESTS.findall(run))
    return expressions


def collect(expression: str | None, python: str = sys.executable) -> set[str]:
    cmd = [
        python,
        "-m",
        "pytest",
        "tests/",
        "--collect-only",
        "-q",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
    ]
    if expression is not None:
        cmd += ["-m", expression]
    proc = subprocess.run(cmd, cwd=TEST_ROOT, capture_output=True, text=True)
    # 5 = nothing collected, which is a valid (empty) selection.
    if proc.returncode not in (0, 5):
        sys.stderr.write(proc.stdout[-4000:] + proc.stderr[-4000:])
        raise SystemExit(f"collection failed ({proc.returncode}): {' '.join(cmd)}")
    return {line.strip() for line in proc.stdout.splitlines() if "::" in line}


def unselected(full: set[str], selections: list[set[str]]) -> list[str]:
    chosen: set[str] = set().union(*selections) if selections else set()
    return sorted(full - chosen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", type=Path, default=WORKFLOW)
    args = parser.parse_args(argv)

    expressions = extract_expressions(
        yaml.safe_load(args.workflow.read_text(encoding="utf-8"))
    )
    if not expressions:
        print(f"no `pytest tests/ -m` steps found in {args.workflow}", file=sys.stderr)
        return 1
    full = collect(None)
    selections = []
    for expr in expressions:
        chosen = collect(expr)
        print(f"{len(chosen):5d}  -m {expr!r}")
        selections.append(chosen)
    missing = unselected(full, selections)
    print(f"{len(full):5d}  collected")
    if missing:
        print(f"{len(missing)} tests are selected by no CI step:", file=sys.stderr)
        for nodeid in missing:
            print(f"  {nodeid}", file=sys.stderr)
        return 1
    print("every collected test is selected by at least one CI step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
