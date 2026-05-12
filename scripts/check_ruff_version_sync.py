#!/usr/bin/env python3
# editorconfig-checker-disable-file (docstring uses 2-space indented numbered list)
"""Ruff version pin synchronization gate.

CLAUDE.md says "ruff version is pinned in 3 places" but the actual count
is **6 pin sites** across 3 files:

  1. .pre-commit-config.yaml      `rev: v<VER>`            (ruff-pre-commit)
  2. .github/workflows/python-lint.yml `pip install ruff==<VER>`
  3. .github/workflows/ci.yml          `uv pip install ... ruff==<VER>`
  4. pyproject.toml                    `"ruff==<VER>"` × 3 (dev / test / quality groups)

Drift between any of these = local-clean / CI-fail mismatch (PR #401 cause).
Dependabot's uv-workspace ecosystem PR (#442) bumped pyproject.toml only,
leaving the workflow pins behind → PR #445 + #446 follow-up to sync.

This script extracts the version string from each site, compares them, and
fails CI if they don't all match. Use `pyproject.toml`'s `ruff==X` (first
occurrence) as the canonical version.

Sites where `ruff>=X` (min-version) is used are intentionally NOT checked:
  - src/python/pyproject.toml      "ruff>=0.12"
  - src/python/g2p/pyproject.toml  "ruff>=0.8.0"
These declare minimum compatibility, not the pinned tool version, and lag
the active pin deliberately.

Usage:
    python scripts/check_ruff_version_sync.py

Exit codes:
    0 -- all pin sites agree
    1 -- drift detected (lists each site and the version found)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def grep_first(path: Path, pattern: str) -> tuple[str | None, int | None]:
    """Return (version, line_number) for the first match of `pattern` in `path`.

    The pattern must capture the version in group 1.
    """
    if not path.exists():
        return None, None
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = re.search(pattern, line)
        if m:
            return m.group(1), i
    return None, None


def grep_all(path: Path, pattern: str) -> list[tuple[str, int]]:
    """Return (version, line_number) for every match of `pattern` in `path`."""
    out: list[tuple[str, int]] = []
    if not path.exists():
        return out
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = re.search(pattern, line)
        if m:
            out.append((m.group(1), i))
    return out


def main(argv: list[str] | None = None) -> int:
    # Site → (path, pattern, "single" or "all")
    # Pattern must capture the version in group 1.
    sites: list[tuple[str, Path, str, str]] = [
        (
            ".pre-commit-config.yaml",
            REPO_ROOT / ".pre-commit-config.yaml",
            r"ruff-pre-commit\s*$",  # marker line, version is on next line
            "next",
        ),
        (
            ".github/workflows/python-lint.yml",
            REPO_ROOT / ".github/workflows/python-lint.yml",
            r"pip install\s+ruff==([0-9][0-9.]*)",
            "single",
        ),
        (
            ".github/workflows/ci.yml",
            REPO_ROOT / ".github/workflows/ci.yml",
            r"ruff==([0-9][0-9.]*)",
            "single",
        ),
        (
            "pyproject.toml",
            REPO_ROOT / "pyproject.toml",
            r'"ruff==([0-9][0-9.]*)"',
            "all",
        ),
    ]

    findings: list[tuple[str, str, int]] = []  # (site, version, line)
    missing: list[str] = []

    for label, path, pattern, mode in sites:
        if not path.exists():
            missing.append(f"{label} ({path})")
            continue

        if mode == "next":
            # Special case for pre-commit-config: find ruff-pre-commit then
            # parse the next `rev: v<VER>` line.
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if re.search(pattern, line):
                    for j in range(i + 1, min(i + 4, len(lines))):
                        m = re.match(r"\s*rev:\s*v([0-9][0-9.]*)", lines[j])
                        if m:
                            findings.append((label, m.group(1), j + 1))
                            break
                    break
        elif mode == "single":
            ver, lineno = grep_first(path, pattern)
            if ver and lineno:
                findings.append((label, ver, lineno))
        elif mode == "all":
            for ver, lineno in grep_all(path, pattern):
                findings.append((label, ver, lineno))

    if missing:
        print(f"ERROR: pin sites missing: {missing}", file=sys.stderr)
        return 1

    if not findings:
        print("ERROR: no ruff version pins found at any expected site", file=sys.stderr)
        return 1

    print(f"Found {len(findings)} ruff pin site(s):")
    for site, ver, lineno in findings:
        print(f"  {site}:{lineno}  ruff=={ver}")

    versions = {ver for _, ver, _ in findings}
    if len(versions) > 1:
        print(
            f"\nDRIFT: pin sites disagree — versions seen: {sorted(versions)}",
            file=sys.stderr,
        )
        print(
            "All 6 sites (1 pre-commit rev + 2 workflow installs + 3 pyproject "
            "dependency-group entries) must use the same version.\n"
            "Update them together; CLAUDE.md has the rationale (PR #401 / #442 "
            "drift events).",
            file=sys.stderr,
        )
        return 1

    canonical = next(iter(versions))
    print(f"\nOK all sites pin ruff=={canonical}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
