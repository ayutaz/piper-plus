#!/usr/bin/env python3
"""docs/spec/*.toml の [meta] section に forward_compat_policy を統一付与 (Wave 3).

既存 24 spec TOML の [meta] section を audit し、 統一の `forward_compat_policy`
フィールドを追加。 既存値は変更しない (idempotent)。

統一フィールド:
  - forward_compat_policy: "strict" | "accept_unknown_fields" | "ignore_future_entries"
    default: "strict"  (未知 field を受理しない conservative 設定)

既存の `spec_version` / `schema_version` / `last_updated` 等のフィールドは
そのまま保持。 互換性維持のため rename はしない。

[meta] section が存在しない TOML には冒頭 (最初の [section] 直前) に新規追加。

Usage:
    uv run python scripts/migrate_spec_meta.py            # 適用
    uv run python scripts/migrate_spec_meta.py --dry-run  # 表示のみ
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "docs" / "spec"


def already_has_forward_compat(text: str) -> bool:
    """[meta] section 内に forward_compat_policy があるか。"""
    in_meta = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[meta]"):
            in_meta = True
            continue
        if stripped.startswith("[") and stripped != "[meta]":
            in_meta = False
        if in_meta and stripped.startswith("forward_compat_policy"):
            return True
    return False


def find_meta_section(text: str) -> tuple[int, int] | None:
    """Return (start_line, end_line_exclusive) of [meta] section, or None."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "[meta]":
            start = i
            break
    if start is None:
        return None
    # Find next [section] header or EOF
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("[") and not s.startswith("[meta]"):
            return (start, j)
    return (start, len(lines))


def insert_forward_compat(text: str) -> tuple[str, str]:
    """Insert forward_compat_policy = "strict" into existing [meta] section.

    Returns (new_text, action_msg).
    """
    section = find_meta_section(text)
    if section is None:
        # [meta] section 不在 → 冒頭に追加。 最初の `[` で始まる行の直前か、
        # 最初の comment block の後ろに挿入。
        lines = text.splitlines(keepends=True)
        insert_at = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("["):
                insert_at = i
                break
            if not stripped.startswith("#") and stripped:
                # First non-comment, non-empty, non-section line — insert before it.
                insert_at = i
                break
        meta_block = '[meta]\nforward_compat_policy = "strict"\n\n'
        lines.insert(insert_at, meta_block)
        return ("".join(lines), "ADDED new [meta] section")

    start, end = section
    lines = text.splitlines(keepends=True)
    # 既存 [meta] の最終 valid line (空行ではない) 直後に挿入。
    insert_at = start + 1
    last_field_line = start + 1
    for k in range(start + 1, end):
        s = lines[k].strip()
        if s and not s.startswith("#"):
            last_field_line = k + 1
    insert_at = last_field_line
    new_field = 'forward_compat_policy = "strict"\n'
    lines.insert(insert_at, new_field)
    return ("".join(lines), f"INSERTED at line {insert_at + 1}")


def process_file(path: Path, dry_run: bool) -> str:
    """Return result string for this file (no side effect in dry_run)."""
    text = path.read_text(encoding="utf-8")
    if already_has_forward_compat(text):
        return f"  skip (already has forward_compat_policy): {path.name}"
    new_text, action = insert_forward_compat(text)
    if dry_run:
        return f"  would update ({action}): {path.name}"
    path.write_text(new_text, encoding="utf-8")
    return f"  updated ({action}): {path.name}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate spec TOML [meta] sections")
    parser.add_argument(
        "--dry-run", action="store_true", help="report changes without writing"
    )
    args = parser.parse_args()

    if not SPEC_DIR.is_dir():
        print(f"error: {SPEC_DIR} not found", file=sys.stderr)
        return 1

    tomls = sorted(SPEC_DIR.glob("*.toml"))
    if not tomls:
        print(f"no TOML files in {SPEC_DIR}")
        return 0

    print(
        f"Processing {len(tomls)} spec TOML file(s) "
        f"({'dry-run' if args.dry_run else 'apply'}):"
    )
    for path in tomls:
        result = process_file(path, args.dry_run)
        print(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
