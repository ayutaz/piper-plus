#!/usr/bin/env python3
"""Every src/python_run test file must be referenced by a CI workflow.

`.github/workflows/python-tests.yml` invokes pytest with an EXPLICIT file list
rather than a directory, so a newly added test file runs locally but never in
CI -- it is simply absent from the command line. Seven files had accumulated
in that state (131 tests that had never executed in CI) before this gate
existed.

That is the same failure shape as issues #652 and #659: the gate stays green
because its subject is not part of what the gate looks at. This script closes
it by requiring that every `src/python_run/tests/test_*.py` is named by at
least one workflow under `.github/workflows/`.

Referencing a file from ANY workflow counts -- several are deliberately driven
by a dedicated gate instead of the main matrix (for example
`test_phoneme_timing_parity.py` runs in `timing-parity.yml`).

Exit codes: 0 = every file referenced, 1 = at least one file unreferenced.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "src" / "python_run" / "tests"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def main() -> int:
    if not TESTS_DIR.is_dir():
        print(f"ERROR: test directory not found: {TESTS_DIR}", file=sys.stderr)
        return 1
    if not WORKFLOWS_DIR.is_dir():
        print(f"ERROR: workflow directory not found: {WORKFLOWS_DIR}", file=sys.stderr)
        return 1

    test_files = sorted(p.name for p in TESTS_DIR.glob("test_*.py"))
    if not test_files:
        # An empty directory would make this gate vacuously green, which is the
        # very thing it exists to prevent.
        print(
            f"ERROR: no test_*.py found under {TESTS_DIR.relative_to(REPO_ROOT)}; "
            "the gate would pass vacuously",
            file=sys.stderr,
        )
        return 1

    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
    )

    unreferenced = [name for name in test_files if name not in workflow_text]

    if unreferenced:
        print(
            "ERROR: these src/python_run test files are not referenced by any "
            "workflow under .github/workflows/, so CI never runs them:",
            file=sys.stderr,
        )
        for name in unreferenced:
            print(f"  - tests/{name}", file=sys.stderr)
        print(
            "\nAdd each one to the pytest invocation in "
            ".github/workflows/python-tests.yml (the 'Run runtime full tests' "
            "step), or to whichever dedicated workflow should own it.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: all {len(test_files)} src/python_run test files are referenced by "
        "a CI workflow"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
