#!/usr/bin/env python3
"""CHANGELOG.md [Unreleased] → [X.Y.Z] - YYYY-MM-DD 昇格 (Wave 3, S-3).

Release 直前に呼び出して [Unreleased] section の heading を新 version + 日付
に書き換え、 直後に新しい空 [Unreleased] section を挿入する。 release-please
本格移行前の bridging script。

動作:
  1. CHANGELOG.md の `## [Unreleased]` line を `## [X.Y.Z] - YYYY-MM-DD`
     に rename
  2. その上に新しい `## [Unreleased]` heading + 空 ### subsection を挿入
  3. dry-run option で書き換え前の preview のみ表示

Usage:
  uv run python scripts/promote_changelog.py --version 1.13.0
  uv run python scripts/promote_changelog.py --version 1.13.0 --date 2026-06-01
  uv run python scripts/promote_changelog.py --version 1.13.0 --dry-run

Exit codes:
  0 -- 昇格成功 (または dry-run 完了)
  1 -- [Unreleased] section 不在 / 重複 / 既に同 version exists
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

UNRELEASED_HEADING = "## [Unreleased]"
NEW_UNRELEASED_BLOCK = """## [Unreleased]

### Added

### Changed

### Fixed

"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote CHANGELOG [Unreleased]")
    parser.add_argument(
        "--version", required=True, help='target version (e.g. "1.13.0")'
    )
    parser.add_argument("--date", help="release date YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--dry-run", action="store_true", help="show diff without writing"
    )
    args = parser.parse_args()

    if not CHANGELOG.exists():
        print(f"error: {CHANGELOG} not found", file=sys.stderr)
        return 1

    if not re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$", args.version):
        print(
            f"error: --version must be semver-like, got '{args.version}'",
            file=sys.stderr,
        )
        return 1

    release_date = args.date or datetime.date.today().isoformat()
    new_heading = f"## [{args.version}] - {release_date}"

    text = CHANGELOG.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    unreleased_idx: int | None = None
    duplicate_version_idx: int | None = None
    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if stripped == UNRELEASED_HEADING:
            if unreleased_idx is not None:
                print(
                    f"error: multiple `{UNRELEASED_HEADING}` sections "
                    f"(lines {unreleased_idx + 1} and {i + 1})",
                    file=sys.stderr,
                )
                return 1
            unreleased_idx = i
        if stripped.startswith(f"## [{args.version}]"):
            duplicate_version_idx = i

    if unreleased_idx is None:
        print(f"error: `{UNRELEASED_HEADING}` not found in CHANGELOG", file=sys.stderr)
        return 1

    if duplicate_version_idx is not None:
        print(
            f"error: version {args.version} already in CHANGELOG "
            f"(line {duplicate_version_idx + 1})",
            file=sys.stderr,
        )
        return 1

    # Replace the [Unreleased] heading line with the new release heading,
    # and prepend a fresh empty [Unreleased] block above it.
    promoted_line = new_heading + "\n"
    new_lines = (
        lines[:unreleased_idx]
        + [NEW_UNRELEASED_BLOCK]
        + [promoted_line]
        + lines[unreleased_idx + 1 :]
    )
    new_text = "".join(new_lines)

    if args.dry_run:
        print(
            f"--- dry-run: would promote [Unreleased] → [{args.version}] - "
            f"{release_date} ---"
        )
        # Show ~30 lines around the change
        ctx_start = max(0, unreleased_idx - 2)
        ctx_end = min(len(new_lines), unreleased_idx + 15)
        for line in new_lines[ctx_start:ctx_end]:
            print(line, end="")
        return 0

    CHANGELOG.write_text(new_text, encoding="utf-8")
    print(f"promoted [Unreleased] → [{args.version}] - {release_date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
