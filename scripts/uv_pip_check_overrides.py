#!/usr/bin/env python3
"""`uv pip check` that accepts incompatibilities explained by declared overrides.

environments/webui overrides gradio's `pillow<13.0` cap with
`[tool.uv] override-dependencies = ["pillow>=13.0.0"]` (Pillow 13.0.0 fixes
5 CRITICAL advisories; docs/design/pillow-13-override-2026-10-24.md). Plain
`uv pip check` then reports "The package `gradio` requires `pillow>=8.0,<13.0`,
but `13.0.0` is installed" and fails.

This wrapper runs `uv pip check` and fails on every reported line except an
unmet requirement on an overridden package whose installed version satisfies
the override. Lines it does not recognise also fail, so a change in uv's
output cannot turn the check into a silent pass.

Usage:
    python scripts/uv_pip_check_overrides.py --python <interpreter> \
        --pyproject environments/webui/pyproject.toml
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


UNMET_RE = re.compile(
    r"^The package `(?P<pkg>[^`]+)` requires `(?P<req>[^`]+)`, "
    r"but `(?P<installed>[^`]+)` is installed$"
)
INFO_RE = re.compile(
    r"^(Using Python .*|Checked \d+ packages? in .*|Found \d+ incompatibilit(?:y|ies)"
    r"|All installed packages are compatible)$"
)


def load_overrides(pyproject: Path) -> list[str]:
    with pyproject.open("rb") as f:
        return list(
            tomllib.load(f)
            .get("tool", {})
            .get("uv", {})
            .get("override-dependencies", [])
        )


def unexplained(output: str, overrides: list[str]) -> list[str]:
    specs = {
        canonicalize_name(Requirement(o).name): Requirement(o).specifier
        for o in overrides
    }
    problems: list[str] = []
    for line in (ln.strip() for ln in output.splitlines()):
        if not line or INFO_RE.match(line):
            continue
        m = UNMET_RE.match(line)
        if m:
            name = canonicalize_name(Requirement(m.group("req")).name)
            spec = specs.get(name)
            if spec is not None and spec.contains(
                Version(m.group("installed")), prereleases=True
            ):
                continue
        problems.append(line)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--python", required=True)
    parser.add_argument("--pyproject", required=True, type=Path)
    args = parser.parse_args()

    overrides = load_overrides(args.pyproject)
    result = subprocess.run(
        ["uv", "pip", "check", "--python", args.python],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    print(output, end="")
    problems = unexplained(output, overrides)
    if problems:
        print("\nIncompatibilities not explained by override-dependencies:")
        for p in problems:
            print(f"  - {p}")
        return 1
    if result.returncode != 0:
        print(f"\nAccepted: every reported incompatibility comes from {overrides}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
