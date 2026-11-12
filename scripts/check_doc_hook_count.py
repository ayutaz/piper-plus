#!/usr/bin/env python3
"""The hook counts in CLAUDE.md and .claude/README.md match .pre-commit-config.yaml.

Both documents give the size of the pre-commit setup as a number. In 2026-11
they said 119 while the config had 120: a PR that adds a hook has to update
two numbers in two files, and nothing failed when it did not. Hooks are
counted as ``- id:`` lines; contract gates as the ids that contain
``contract``. A document whose wording no longer matches is an error too, so
a rephrasing updates this gate instead of silently turning it off.

Usage:
    uv run python scripts/check_doc_hook_count.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = ".pre-commit-config.yaml"
ID_LINE = re.compile(r"^\s*- id:\s*(\S+)", re.MULTILINE)

# (document, pattern, the count kind of each group)
PHRASES = [
    (
        "CLAUDE.md",
        re.compile(r"\((\d+) hook、 うち id に `contract` を含む gate (\d+)"),
        ("hooks", "contract gates"),
    ),
    (".claude/README.md", re.compile(r"hook 数は (\d+)"), ("hooks",)),
]


def check(root: Path) -> list[str]:
    ids = ID_LINE.findall((root / CONFIG).read_text(encoding="utf-8"))
    actual = {"hooks": len(ids), "contract gates": sum("contract" in i for i in ids)}
    errors: list[str] = []
    for doc, pattern, kinds in PHRASES:
        found = pattern.search((root / doc).read_text(encoding="utf-8"))
        if found is None:
            errors.append(
                f"{doc}: the hook count was not found (pattern {pattern.pattern!r}); "
                "update scripts/check_doc_hook_count.py if the wording changed"
            )
            continue
        for kind, said in zip(kinds, map(int, found.groups()), strict=True):
            if said != actual[kind]:
                errors.append(f"{doc}: says {said} {kind}, {CONFIG} has {actual[kind]}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    args = ap.parse_args(argv)
    errors = check(args.root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: the documented hook counts match .pre-commit-config.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
