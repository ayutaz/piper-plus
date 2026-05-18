#!/usr/bin/env python3
"""CHANGELOG.md が keep-a-changelog 形式に従っているかを検証する。

`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #1 由来。 Top 10 外の
docs / i18n / CHANGELOG 拡張で、 M1.2 migration-guide-lint (anchor link 強制)
と相補的に「CHANGELOG.md 自体の format drift」 を検出する。

検査項目 (error tier):
  1. ``# Changelog`` H1 が冒頭にある
  2. ``## [Unreleased]`` セクションが存在し、 最初のバージョンセクション
     より前にある
  3. リリースバージョン header は ``## [X.Y.Z[-pre]] - YYYY-MM-DD`` 形式
  4. リリースバージョンは降順 (新しい順) で並んでいる

検査項目 (warning tier):
  5. 各リリース内のサブセクション (``### Foo``) が keep-a-changelog の
     7 種 (Added/Changed/Deprecated/Removed/Fixed/Security/Breaking) または
     piper-plus 既知の拡張セクション (Limitations 等) のいずれか

stdlib のみ。 既存 CHANGELOG.md に対して bootstrap して合格すること。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Keep-a-changelog 公式の 6 セクション + piper-plus 独自の Breaking。
CANONICAL_SECTIONS = frozenset(
    {
        "Added",
        "Changed",
        "Deprecated",
        "Removed",
        "Fixed",
        "Security",
        "Breaking",
    }
)

# piper-plus が CHANGELOG.md で実際に使用している拡張セクション。
# 新規セクションを増やしたい場合はこのセットに追加する。
EXTENDED_SECTIONS = frozenset(
    {
        "Limitations",
        "Tests",
        "Documentation",
        "Chore",
        "Changed (Breaking)",
    }
)

# v1.5 系以前のリリースで絵文字 prefix 付きセクションが使われていた。
# 既存 entries は履歴改ざんを避けるためそのまま残し、 警告対象から外す
# (新規 entries は CANONICAL / EXTENDED のみを推奨)。
HISTORIC_SECTIONS = frozenset(
    {
        "🚀 Major Features",
        "🎯 Performance",
        "🔧 Improvements",
        "📚 Documentation",
        "🧹 Maintenance",
        "📦 Build System",
        "🧪 Developer Experience",
    }
)

ALLOWED_SECTIONS = CANONICAL_SECTIONS | EXTENDED_SECTIONS | HISTORIC_SECTIONS

VERSION_HEADER_RE = re.compile(
    r"^## \[(?P<version>\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?)\]"
    r" - (?P<date>\d{4}-\d{2}-\d{2})\s*$"
)
UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\]\s*$")
H1_RE = re.compile(r"^# Change[ ]?[Ll]og\s*$")
SECTION_HEADER_RE = re.compile(r"^### (?P<name>.+?)\s*$")


def semver_tuple(v: str) -> tuple[int, ...]:
    """Return a sortable tuple for descending comparison; pre-release sorts lower."""
    core, _, pre = v.partition("-")
    parts = tuple(int(x) for x in core.split("."))
    # 同じ core なら pre-release を normal release より前に出したい。
    # ここでは「降順チェック」 用なので、 pre 付きを "less than" にするため
    # tail に sentinel を付ける。
    if pre:
        return parts + (0, pre)
    return parts + (1,)


def check(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or not H1_RE.match(lines[0]):
        errors.append("L1: expected '# Changelog' as the H1 title")

    unreleased_idx: int | None = None
    version_indices: list[tuple[int, str]] = []  # (line_no, version)
    in_release_section = False
    in_terminator_section = False  # `## Older Releases` 以降は version check 範囲外
    current_release_line = 0
    sections_in_release: set[str] = set()

    for idx, line in enumerate(lines, start=1):
        if UNRELEASED_HEADER_RE.match(line):
            unreleased_idx = idx
            in_release_section = True
            in_terminator_section = False
            current_release_line = idx
            sections_in_release = set()
            continue
        m = VERSION_HEADER_RE.match(line)
        if m:
            version_indices.append((idx, m.group("version")))
            in_release_section = True
            in_terminator_section = False
            current_release_line = idx
            sections_in_release = set()
            continue
        if line.startswith("## "):
            # `## [...]` で始まらない H2 は terminator (例: ``## Older Releases``)。
            # 以降は version 構造の検証を停止する。
            if not line.startswith("## ["):
                in_terminator_section = True
                in_release_section = False
                continue
            errors.append(
                f"L{idx}: H2 header '{line}' does not match"
                " '## [X.Y.Z] - YYYY-MM-DD' or '## [Unreleased]'"
            )
        if in_terminator_section:
            continue
        sm = SECTION_HEADER_RE.match(line)
        if sm and in_release_section:
            name = sm.group("name").strip()
            if name in sections_in_release:
                warnings.append(
                    f"L{idx}: section '{name}' repeated within release"
                    f" starting at L{current_release_line}"
                )
            sections_in_release.add(name)
            # ``Limitations (v1.13.0 iOS xcframework)`` のような suffix 付きを
            # 許容するため、 EXTENDED は startswith マッチ、 CANONICAL / HISTORIC は equality。
            allowed = (
                name in CANONICAL_SECTIONS
                or name in HISTORIC_SECTIONS
                or any(
                    name == ext or name.startswith(ext + " ") for ext in EXTENDED_SECTIONS
                )
            )
            if not allowed:
                warnings.append(
                    f"L{idx}: section '### {name}' is not in the allowed list."
                    " Add to EXTENDED_SECTIONS if intentional."
                )

    if unreleased_idx is None:
        errors.append("missing '## [Unreleased]' section")
    elif version_indices and unreleased_idx > version_indices[0][0]:
        errors.append(
            f"L{unreleased_idx}: '[Unreleased]' must precede the first"
            f" versioned release (currently at L{version_indices[0][0]})"
        )

    for (l_a, v_a), (l_b, v_b) in zip(version_indices, version_indices[1:]):
        if semver_tuple(v_a) <= semver_tuple(v_b):
            errors.append(
                f"L{l_b}: version '{v_b}' must be strictly older than"
                f" '{v_a}' (L{l_a}); release entries must be in"
                " descending order"
            )

    return errors, warnings


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else [Path("CHANGELOG.md")]
    total_errors = 0
    for p in paths:
        if not p.exists():
            print(f"[skip] {p}: not found", file=sys.stderr)
            continue
        errors, warnings = check(p)
        for w in warnings:
            print(f"[WARN] {p}:{w}")
        for e in errors:
            print(f"[ERROR] {p}:{e}", file=sys.stderr)
        total_errors += len(errors)
    if total_errors:
        print(f"\n{total_errors} error(s) in CHANGELOG format.", file=sys.stderr)
        return 1
    print("CHANGELOG format check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
