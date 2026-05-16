#!/usr/bin/env python3
"""CHANGELOG.md → CHANGELOG-archive.md 自動移動 (Wave 3, S-3).

`--before X.Y.Z` で指定した version 未満の release section を CHANGELOG.md
から CHANGELOG-archive.md の冒頭 (Heading の直後) に移動。 maintenance
window を「直近 18 ヶ月」 程度に保つための定期メンテナンス用。

動作:
  1. CHANGELOG.md から `## [X.Y.Z] - YYYY-MM-DD` heading を全て抽出
  2. `--before` で指定された version より古い release を抽出
  3. それらを CHANGELOG.md から削除し、 CHANGELOG-archive.md の頭近くに挿入
  4. 重複した version は archive 側で skip (idempotent)

Usage:
  uv run python scripts/archive_changelog.py --before 1.10.0 --dry-run
  uv run python scripts/archive_changelog.py --before 1.10.0

Exit codes:
  0 -- archive 成功 (または dry-run 完了、 対象なしも 0)
  1 -- file 不在 / --before format error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
ARCHIVE = REPO_ROOT / "CHANGELOG-archive.md"

VERSION_HEADING_RE = re.compile(
    r"^## \[(?P<ver>\d+\.\d+\.\d+(?:-[a-zA-Z0-9.]+)?)\](?: - (?P<date>\d{4}-\d{2}-\d{2}))?\s*$"
)


def parse_version(v: str) -> tuple[int, ...]:
    """Parse semver to int tuple. Pre-release suffix dropped for comparison."""
    main = v.split("-", 1)[0]
    return tuple(int(x) for x in main.split("."))


def split_sections(text: str) -> list[tuple[str | None, str, str]]:
    """Split CHANGELOG body into release sections.

    Returns list of (version_or_None, heading_line, body_lines) tuples.
    version=None means "preamble" (everything before the first ## [...] line).
    body_lines includes the heading line itself for re-emission.
    """
    sections: list[tuple[str | None, str, str]] = []
    current_ver: str | None = None
    current_heading = ""
    buf: list[str] = []
    for line in text.splitlines(keepends=True):
        m = VERSION_HEADING_RE.match(line.rstrip("\n"))
        if m:
            if buf:
                sections.append((current_ver, current_heading, "".join(buf)))
                buf = []
            current_ver = m.group("ver")
            current_heading = line.rstrip("\n")
            buf.append(line)
        else:
            buf.append(line)
    if buf:
        sections.append((current_ver, current_heading, "".join(buf)))
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive old CHANGELOG entries")
    parser.add_argument(
        "--before", required=True, help='archive versions < this (e.g. "1.10.0")'
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report changes without writing"
    )
    args = parser.parse_args()

    if not CHANGELOG.exists():
        print(f"error: {CHANGELOG} not found", file=sys.stderr)
        return 1
    if not re.match(r"^\d+\.\d+\.\d+$", args.before):
        print("error: --before must be 'major.minor.patch'", file=sys.stderr)
        return 1

    threshold = parse_version(args.before)

    body = CHANGELOG.read_text(encoding="utf-8")
    sections = split_sections(body)

    keep_sections: list[tuple[str | None, str, str]] = []
    archive_sections: list[tuple[str | None, str, str]] = []

    for ver, heading, content in sections:
        if ver is None:
            keep_sections.append((ver, heading, content))
            continue
        # [Unreleased] や non-semver headings は keep
        try:
            v_tuple = parse_version(ver)
        except ValueError:
            keep_sections.append((ver, heading, content))
            continue
        if v_tuple < threshold:
            archive_sections.append((ver, heading, content))
        else:
            keep_sections.append((ver, heading, content))

    if not archive_sections:
        print(f"no sections older than {args.before} to archive")
        return 0

    print(f"would archive {len(archive_sections)} section(s):")
    for _ver, heading, _ in archive_sections:
        print(f"  - {heading}")

    if args.dry_run:
        return 0

    # Write new CHANGELOG.md
    new_changelog = "".join(content for _, _, content in keep_sections)
    CHANGELOG.write_text(new_changelog, encoding="utf-8")

    # Insert archived sections into CHANGELOG-archive.md at the top
    # (after its top-level # title, if present).
    archive_body = ARCHIVE.read_text(encoding="utf-8") if ARCHIVE.exists() else ""
    # Split archive into top-block (heading + intro) and rest
    lines = archive_body.splitlines(keepends=True)
    insert_at = 0
    seen_h1 = False
    for i, line in enumerate(lines):
        if line.startswith("# "):
            seen_h1 = True
            insert_at = i + 1
        elif (
            seen_h1
            and line.startswith("## ")
            and VERSION_HEADING_RE.match(line.rstrip("\n"))
        ):
            insert_at = i
            break
        else:
            insert_at = i + 1
    archived_text = "\n".join(content for _, _, content in archive_sections) + "\n"
    new_lines = lines[:insert_at] + ["\n" + archived_text] + lines[insert_at:]
    ARCHIVE.write_text("".join(new_lines), encoding="utf-8")

    print(
        f"archived {len(archive_sections)} section(s) to "
        f"{ARCHIVE.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
