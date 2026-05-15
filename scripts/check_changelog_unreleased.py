#!/usr/bin/env python3
"""CHANGELOG [Unreleased] cleanup gate.

After releasing a version (e.g., v1.12.0), the workflow is:

  1. Move content from `## [Unreleased]` to a new `## [1.12.0] - YYYY-MM-DD`
     sibling section.
  2. Update `docs/spec/release-versions.toml::expected_prefix`.
  3. Leave `## [Unreleased]` empty (or with content for the *next* version).

If step 1 is skipped or done wrong, the `[Unreleased]` section will contain
release-style headings (e.g., `### [1.12.0]` or `### v1.12.0 - 2026-...`)
that should have been moved out. This script catches that drift.

Detection rule (intentionally conservative to minimize false positives):

- Find the `## [Unreleased]` section bounds.
- Inside it, look for ``### [vX.Y.Z]`` / ``### X.Y.Z`` style sub-headings
  whose major.minor (e.g., ``1.12.``) matches a current
  ``expected_prefix`` from ``docs/spec/release-versions.toml``.
- Flag those as drift (= misplaced release section).

Legitimate cross-references like "since v1.12.0, foo bar" in prose are NOT
flagged — only structural sub-headings.

Usage:
    python scripts/check_changelog_unreleased.py

Exit codes:
    0 -- [Unreleased] has no stray release-style sub-headings
    1 -- drift detected (file:line + content listed)
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
RELEASE_VERSIONS_PATH = REPO_ROOT / "docs" / "spec" / "release-versions.toml"


def _load_expected_prefixes(path: Path) -> set[str]:
    """Return the set of ``expected_prefix`` values declared in
    ``release-versions.toml``.

    The TOML file groups manifests under nested tables (e.g.,
    ``[python]``, ``[rust]``, ``[dotnet.core]``); we walk the full tree.
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    prefixes: set[str] = set()

    def walk(d: dict) -> None:
        for k, v in d.items():
            if isinstance(v, dict):
                walk(v)
            elif k == "expected_prefix" and isinstance(v, str):
                prefixes.add(v)

    walk(data)
    return prefixes


def _find_unreleased_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Return ``(start_idx, end_idx)`` (0-based, end exclusive) of the
    ``## [Unreleased]`` section.

    Heading variants accepted: ``## [Unreleased]``, ``## Unreleased``,
    case-insensitive. ``None`` if not present.
    """
    start = None
    heading_re = re.compile(r"^## \[?Unreleased\]?", re.IGNORECASE)
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i + 1  # content starts after the heading
            break
    if start is None:
        return None
    for j in range(start, len(lines)):
        if re.match(r"^## ", lines[j]):
            return (start, j)
    return (start, len(lines))


def _detect_drift(
    lines: list[str], prefixes: set[str], bounds: tuple[int, int]
) -> list[tuple[int, str, str]]:
    """Return list of ``(line_number_1_based, version, line_content)`` for
    each release-style sub-heading found inside ``[Unreleased]``.

    A heading is "release-style" if it matches ``### [vX.Y.Z]`` /
    ``### X.Y.Z`` / ``### v X.Y.Z`` and the major.minor (``X.Y.``) is one
    of the currently active ``expected_prefix`` values.
    """
    start, end = bounds
    drifts: list[tuple[int, str, str]] = []
    heading_re = re.compile(r"^###+\s*\[?v?(\d+\.\d+\.\d+)\]?")
    for idx in range(start, end):
        m = heading_re.match(lines[idx])
        if not m:
            continue
        version = m.group(1)
        parts = version.split(".")
        major_minor_prefix = f"{parts[0]}.{parts[1]}."
        if major_minor_prefix in prefixes:
            drifts.append((idx + 1, version, lines[idx]))
    return drifts


def main() -> int:
    if not CHANGELOG_PATH.exists():
        print(f"ERROR: {CHANGELOG_PATH.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 1
    if not RELEASE_VERSIONS_PATH.exists():
        print(
            f"ERROR: {RELEASE_VERSIONS_PATH.relative_to(REPO_ROOT)} not found",
            file=sys.stderr,
        )
        return 1

    prefixes = _load_expected_prefixes(RELEASE_VERSIONS_PATH)
    if not prefixes:
        print(
            f"ERROR: no expected_prefix entries found in "
            f"{RELEASE_VERSIONS_PATH.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1

    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    bounds = _find_unreleased_bounds(lines)
    if bounds is None:
        print(
            f"WARN: [Unreleased] section not found in "
            f"{CHANGELOG_PATH.relative_to(REPO_ROOT)} — skipping check"
        )
        return 0

    drifts = _detect_drift(lines, prefixes, bounds)
    if drifts:
        print(
            f"ERROR: {len(drifts)} stray release-style sub-heading(s) inside "
            f"[Unreleased] (released versions per release-versions.toml):",
            file=sys.stderr,
        )
        for line_no, version, content in drifts:
            print(
                f"  {CHANGELOG_PATH.relative_to(REPO_ROOT)}:{line_no}: v{version}",
                file=sys.stderr,
            )
            print(f"    {content}", file=sys.stderr)
        print(
            "\nFix: a sub-heading matching a current release prefix usually "
            "means a section was left under [Unreleased] after the release "
            "tag was cut. Move it to a sibling ## [X.Y.Z] heading, or "
            "restructure if it's intentional cross-reference text.",
            file=sys.stderr,
        )
        print(
            f"\nActive expected_prefixes from "
            f"{RELEASE_VERSIONS_PATH.relative_to(REPO_ROOT)}: {sorted(prefixes)}",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: [Unreleased] section has no stray release-style sub-headings "
        f"({len(prefixes)} prefixes checked)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
