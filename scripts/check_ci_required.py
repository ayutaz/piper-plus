#!/usr/bin/env python3
"""Verdict of the ``ci-required`` job in .github/workflows/ci.yml.

``ci-required`` is the check the dev ruleset requires. It reads the results
of every job it needs (``${{ toJSON(needs) }}``) and fails unless:

  * each job named in ``--always-run`` succeeded, and
  * every other job succeeded or was skipped.

Skipped is accepted only for the path-filtered test jobs, and only because
``changes`` (the job that decides which of them run) is in ``--always-run``:
when ``changes`` failed, every job depending on it was skipped and the old
check, which did not look at ``changes`` at all, passed with no test run.

Usage (in the workflow)::

    NEEDS='${{ toJSON(needs) }}' python3 scripts/check_ci_required.py \\
        --always-run release-contract,changes,wasm-onnx-contract
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def verdict(needs: dict, always_run: list[str]) -> list[str]:
    """Return one message per job that must fail the check (empty = pass)."""
    problems: list[str] = []
    for name in always_run:
        if name not in needs:
            problems.append(f"{name}: not in needs (it must always run)")
    for name, info in sorted(needs.items()):
        result = (info or {}).get("result", "missing")
        allowed = {"success"} if name in always_run else {"success", "skipped"}
        if result not in allowed:
            problems.append(f"{name}: {result}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--always-run", required=True)
    args = parser.parse_args(argv)
    raw = os.environ.get("NEEDS", "")
    if not raw:
        print("NEEDS is empty; pass ${{ toJSON(needs) }}", file=sys.stderr)
        return 2
    needs = json.loads(raw)
    always_run = [n.strip() for n in args.always_run.split(",") if n.strip()]
    problems = verdict(needs, always_run)
    for name, info in sorted(needs.items()):
        print(f"{name}: {(info or {}).get('result')}")
    if problems:
        print("ci-required fails:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("All jobs passed (path-filtered jobs may be skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
