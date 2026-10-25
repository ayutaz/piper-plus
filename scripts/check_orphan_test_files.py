#!/usr/bin/env python3
"""Fail when a test file is run by no CI workflow.

Several test suites are run by naming their files, so a new file runs locally
and never in CI. Before this gate existed, 27 of the 71 files in
``tests/scripts`` were named by no workflow (including the tests of the merge
gate itself), and two ``node:test`` files of the npm package were in no
script a workflow runs.

Checked here:

* ``tests/scripts/test_*.py``: a workflow must run the whole directory
  (``pytest tests/scripts`` with no file after it) or name the file.
* ``node:test`` files of the npm packages (``src/wasm/g2p/test``,
  ``src/wasm/openjtalk-web/test/js``): a workflow must name the file, or run a
  ``package.json`` script that names it, directly or through
  ``npm run`` / ``npm test`` from another script.

``src/python_run/tests`` has its own gate (the pre-commit hook
``python-run-test-ci-coverage``), and ``src/python/tests`` is checked by
marker selection in ``python-tests.yml``.

Exit codes: 0 = every file is run, 1 = at least one file is run by nothing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

PYTHON_DIRS = ["tests/scripts"]
# package directory -> directory of its node:test files (relative to it)
NODE_PACKAGES = {
    "src/wasm/g2p": "test",
    "src/wasm/openjtalk-web": "test/js",
}

_NODE_TEST_IMPORT = re.compile(r"""(from\s+|require\()\s*["']node:test["']""")
_NPM_RUN = re.compile(r"\bnpm\s+(?:run|run-script)\s+([A-Za-z0-9:_.-]+)")
_NPM_TEST = re.compile(r"\bnpm\s+(?:test|t)\b")


def runs_whole_dir(workflow_text: str, rel_dir: str) -> bool:
    """True if a workflow runs ``pytest <rel_dir>`` with no file after it."""
    pattern = re.compile(
        r"pytest\b[^\n]*?\s" + re.escape(rel_dir) + r"/?(?=\s|$|['\"])", re.M
    )
    return bool(pattern.search(workflow_text))


def invoked_scripts(text: str) -> set[str]:
    names = set(_NPM_RUN.findall(text))
    if _NPM_TEST.search(text):
        names.add("test")
    return names


def reachable_scripts(scripts: dict[str, str], roots: set[str]) -> set[str]:
    """Scripts in ``roots`` plus every script they reach through npm run/test."""
    seen: set[str] = set()
    todo = [name for name in roots if name in scripts]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(n for n in invoked_scripts(scripts[name]) if n in scripts)
    return seen


def python_orphans(workflow_text: str, repo: Path) -> list[str]:
    orphans: list[str] = []
    for rel_dir in PYTHON_DIRS:
        files = sorted((repo / rel_dir).glob("test_*.py"))
        if not files:
            orphans.append(f"{rel_dir}/ (no test_*.py: the check would pass vacuously)")
            continue
        if runs_whole_dir(workflow_text, rel_dir):
            continue
        orphans.extend(
            f"{rel_dir}/{f.name}" for f in files if f.name not in workflow_text
        )
    return orphans


def node_orphans(workflow_text: str, repo: Path) -> list[str]:
    roots = invoked_scripts(workflow_text)
    orphans: list[str] = []
    for pkg, test_dir in NODE_PACKAGES.items():
        manifest = json.loads((repo / pkg / "package.json").read_text(encoding="utf-8"))
        scripts: dict[str, str] = manifest.get("scripts", {})
        reached = "\n".join(scripts[n] for n in reachable_scripts(scripts, roots))
        files = [
            f
            for f in sorted((repo / pkg / test_dir).glob("*.*js"))
            if _NODE_TEST_IMPORT.search(f.read_text(encoding="utf-8"))
        ]
        if not files:
            orphans.append(f"{pkg}/{test_dir}/ (no node:test files: the check would pass vacuously)")
            continue
        for f in files:
            if f.name not in reached and f.name not in workflow_text:
                orphans.append(f"{pkg}/{test_dir}/{f.name}")
    return orphans


def run_commands(workflow: dict) -> list[str]:
    """The ``run:`` scripts of every step, without shell comment lines.

    Only what a step executes counts: a file named in a YAML or shell comment
    is not run.
    """
    commands: list[str] = []
    for job in (workflow or {}).get("jobs", {}).values():
        for step in job.get("steps", []) or []:
            run = step.get("run")
            if isinstance(run, str):
                commands.append(
                    "\n".join(
                        line
                        for line in run.splitlines()
                        if not line.lstrip().startswith("#")
                    )
                )
    return commands


def workflow_commands(repo: Path) -> str:
    return "\n".join(
        command
        for path in sorted((repo / ".github" / "workflows").glob("*.y*ml"))
        for command in run_commands(yaml.safe_load(path.read_text(encoding="utf-8")))
    )


def main(argv: list[str] | None = None) -> int:
    repo = Path(argv[0]) if argv else REPO_ROOT
    workflow_text = workflow_commands(repo)
    orphans = python_orphans(workflow_text, repo) + node_orphans(workflow_text, repo)
    if orphans:
        print("ERROR: these test files are run by no CI workflow:", file=sys.stderr)
        for name in orphans:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nRun the file from a workflow, or add it to a package.json script "
            "that a workflow runs (for example test:npm-package:all).",
            file=sys.stderr,
        )
        return 1
    print("OK: every tests/scripts and npm node:test file is run by a CI workflow")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
