#!/usr/bin/env python3
"""Migration guide cross-reference lint (M1.2).

v1.12 で `Generator` 削除 + `phonemize()` 戻り値型変更を入れた際、
`docs/migration/v1.11-to-v1.12.md` は breaking commit より後に作成された。
本スクリプトは ``CHANGELOG.md`` の ``[Unreleased] > ### Breaking`` 節と
``docs/migration/v*.md`` の cross-ref を強制し、 同じ事故の再発を防ぐ。

検査ルール (false-positive 最小化のため意図的に保守的):

* ``## [Unreleased]`` セクション内に ``### Breaking`` 見出しがなければ skip。
* ``### Breaking`` 直下の bullet (``-`` で始まる) を 1 entry とみなす。
* 各 entry に少なくとも 1 つ ``[text](docs/migration/v<X>-to-v<Y>.md#anchor)``
  形式の link を要求 (anchor 省略は許可)。
* link 先 file の存在を確認、 anchor 付きなら見出し slug と照合。

slug 規約は GitHub Markdown 互換: lower-case ASCII alpha-num + hyphen、
複数空白は単一 hyphen、 非単語文字は drop。 全角・絵文字も lowercase 後に
drop されるので、 結果が空になる見出しは fixture で pinning。

CLI:

    python scripts/check_migration_xref.py
    python scripts/check_migration_xref.py --changelog CHANGELOG.md
    python scripts/check_migration_xref.py --strict-anchor  # anchor 必須

テストフック: ``--changelog`` で代替ファイル、 ``--root`` で migration doc
の検索 root を切り替える。 ``--strict-anchor`` を渡すと anchor 無しを fail
として扱う (fixture テスト用)。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ANCHOR_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((docs/migration/v[\d\.]+-to-v[\d\.]+\.md)(#[^\)]+)?\)"
)


@dataclass(frozen=True)
class BreakingEntry:
    line_no: int
    body: str


@dataclass
class Section:
    name: str
    entries: list[BreakingEntry] = field(default_factory=list)


def slugify(heading: str) -> str:
    """GitHub Markdown 互換の anchor slug を返す。

    Markdown フレーバーの厳密仕様は未公開だが、 GitHub の挙動は
    ``ascii lowercase → remove non-alphanumeric (except space, dash) →
    spaces to dashes`` で近似できる。 連続 dash の collapse は
    GitHub は行わないが、 fixture テストで pinning する。
    """
    s = heading.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-")


def extract_headings(path: Path) -> set[str]:
    """ファイル内の全 ATX 見出し (``## ...``) を slug 化して返す。"""
    slugs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if m:
            slug = slugify(m.group(1))
            if slug:
                slugs.add(slug)
    return slugs


def parse_unreleased_breaking(text: str) -> list[BreakingEntry]:
    """``## [Unreleased]`` の ``### Breaking`` セクションを抽出する。

    keep-a-changelog では heading の入れ子は固定 (``##`` = version、
    ``###`` = カテゴリ)。 別 version (``## [1.x]``) 見出しに到達したら
    停止する。 ``### Breaking`` 配下では ``-`` で始まる line を 1 entry
    とし、 continuation line (空でない / heading でない / ``-`` でない)
    は同 entry に append する。
    """
    lines = text.splitlines()
    in_unreleased = False
    in_breaking = False
    entries: list[BreakingEntry] = []
    current_start: int | None = None
    current_buf: list[str] = []

    def flush() -> None:
        nonlocal current_start, current_buf
        if current_start is not None:
            entries.append(
                BreakingEntry(line_no=current_start, body="\n".join(current_buf).rstrip())
            )
        current_start = None
        current_buf = []

    for i, line in enumerate(lines, start=1):
        if re.match(r"^##\s+\[?Unreleased\]?", line, re.IGNORECASE):
            in_unreleased = True
            in_breaking = False
            continue
        if in_unreleased and re.match(r"^##\s+\[", line):
            # Reached the next versioned section.
            flush()
            break
        if not in_unreleased:
            continue
        if re.match(r"^###\s+Breaking", line, re.IGNORECASE):
            in_breaking = True
            continue
        if in_breaking and re.match(r"^###\s+", line):
            flush()
            in_breaking = False
            continue
        if not in_breaking:
            continue
        if line.startswith("- "):
            flush()
            current_start = i
            current_buf = [line[2:].rstrip()]
        elif current_start is not None and line.startswith(" "):
            current_buf.append(line.rstrip())
        elif line.strip() == "" and current_start is not None:
            current_buf.append("")
    flush()
    return entries


def validate_entries(
    entries: list[BreakingEntry],
    root: Path,
    *,
    strict_anchor: bool = False,
) -> list[str]:
    errors: list[str] = []
    for entry in entries:
        links = ANCHOR_LINK_RE.findall(entry.body)
        if not links:
            errors.append(
                f"CHANGELOG.md:{entry.line_no}: breaking entry has no "
                f"docs/migration/v*-to-v*.md link: {entry.body.splitlines()[0][:80]!r}"
            )
            continue
        for _label, doc_path, anchor in links:
            full = root / doc_path
            if not full.exists():
                errors.append(
                    f"CHANGELOG.md:{entry.line_no}: migration doc not found: {doc_path}"
                )
                continue
            if not anchor:
                if strict_anchor:
                    errors.append(
                        f"CHANGELOG.md:{entry.line_no}: --strict-anchor: link to "
                        f"{doc_path} has no #anchor"
                    )
                continue
            anchor_slug = anchor.lstrip("#")
            headings = extract_headings(full)
            if anchor_slug not in headings:
                errors.append(
                    f"CHANGELOG.md:{entry.line_no}: anchor not found in "
                    f"{doc_path}: #{anchor_slug}"
                )
    return errors


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--changelog", type=Path, default=REPO_ROOT / "CHANGELOG.md")
    p.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root used to resolve docs/migration/... paths.",
    )
    p.add_argument(
        "--strict-anchor",
        action="store_true",
        help="Treat missing #anchor as an error (default: allow plain file link).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.changelog.exists():
        print(f"CHANGELOG not found: {args.changelog}", file=sys.stderr)
        return 2
    text = args.changelog.read_text(encoding="utf-8")
    entries = parse_unreleased_breaking(text)
    if not entries:
        print(f"{args.changelog.name}: no [Unreleased] > ### Breaking entries; skip.")
        return 0
    errors = validate_entries(entries, args.root, strict_anchor=args.strict_anchor)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(
            f"\nFAIL: {len(errors)} breaking-change cross-ref issue(s) in "
            f"{args.changelog.name}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"{args.changelog.name}: {len(entries)} breaking entries OK "
        f"(all cross-refs resolved)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
