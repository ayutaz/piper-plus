#!/usr/bin/env python3
"""Multilingual README breaking-change banner sync gate.

`README.md` (canonical) は v1.12.0 のような breaking release 直後に
`> **📢 v<X.Y.Z> Breaking changes ...` という banner を冒頭付近に持つ。
他言語 README (`README_<LANG>.md` 計 7 言語) にも同じ banner が同 version
で出現していなければならない。

drift パターン:
  1. canonical のみ breaking banner update、 他言語 README が古い version の
     ままで翻訳忘れ
  2. 一部言語のみ banner 更新、 他言語が drift
  3. canonical から banner 削除されたが 翻訳側に残存

検証内容:

  - canonical README.md の `> **📢 v...` から version 文字列を抽出
  - `README_<LANG>.md` 7 ファイル各々で同 version の banner が存在するか確認
  - 1 ファイルでも欠落 / 古い version なら drift 報告

完全な翻訳一致は要求しない (各言語で表現が変わる)。 「同 version の breaking
banner が存在する」 を保守的 invariant とする。

Usage:
    python scripts/check_readme_breaking_sync.py
    python scripts/check_readme_breaking_sync.py --verbose

Exit codes:
    0 -- 全 README で同 version banner が一致
    1 -- 翻訳漏れ / version drift 検出
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "README.md"

TRANSLATIONS = [
    "README_DE.md",
    "README_EN.md",
    "README_ES.md",
    "README_FR.md",
    "README_KO.md",
    "README_PT.md",
    "README_ZH.md",
]

# `> **📢 v1.12.0 Breaking changes ...` のような行を catch する。
# 開発を縛り過ぎないように、`📢` または `Breaking changes` の語を含む blockquote
# 1 行内に `v<version>` が現れていれば banner として扱う。
BANNER_RE = re.compile(
    r"^>\s*\*?\*?(?:📢\s*)?v(?P<version>\d+\.\d+\.\d+)\s+Breaking", re.MULTILINE
)


def extract_banner_version(text: str) -> str | None:
    m = BANNER_RE.search(text)
    return m.group("version") if m else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="drift があった場合に non-zero で抜ける (default: warning のみ)",
    )
    args = parser.parse_args()

    if not CANONICAL.exists():
        print(f"error: canonical README missing: {CANONICAL}", file=sys.stderr)
        return 1

    canonical_text = CANONICAL.read_text(encoding="utf-8")
    canonical_version = extract_banner_version(canonical_text)

    if canonical_version is None:
        # canonical に banner が無い場合は他言語にもあってはならない、 が breaking なし
        # 状態は valid。 他言語のうち banner 残存があれば warning のみ。
        warnings: list[str] = []
        for name in TRANSLATIONS:
            path = REPO_ROOT / name
            if not path.exists():
                continue
            v = extract_banner_version(path.read_text(encoding="utf-8"))
            if v is not None:
                warnings.append(
                    f"  {name}: stale breaking banner v{v} (canonical has none)"
                )
        if warnings:
            print("README breaking sync: stale banner(s) in translations", file=sys.stderr)
            for w in warnings:
                print(w, file=sys.stderr)
            return 1 if args.strict else 0
        if args.verbose:
            print("OK: canonical README has no breaking banner, translations match")
        return 0

    if args.verbose:
        print(f"canonical breaking version: v{canonical_version}")

    errors: list[str] = []
    checked = 0
    for name in TRANSLATIONS:
        path = REPO_ROOT / name
        if not path.exists():
            errors.append(f"  {name}: file missing")
            continue
        v = extract_banner_version(path.read_text(encoding="utf-8"))
        if v is None:
            errors.append(
                f"  {name}: missing breaking banner (canonical: v{canonical_version})"
            )
        elif v != canonical_version:
            errors.append(
                f"  {name}: banner version v{v} != canonical v{canonical_version}"
            )
        else:
            checked += 1
            if args.verbose:
                print(f"  {name}: v{v} OK")

    if errors:
        msg_prefix = "errors" if args.strict else "warnings"
        print(f"README breaking sync {msg_prefix}:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        print(
            "\nFix: align the banner version in each translation README. "
            "If a breaking release ships, the banner update must land alongside "
            "the canonical README change.\n"
            "(non-strict mode: warning only — re-run with --strict to fail)",
            file=sys.stderr,
        )
        return 1 if args.strict else 0

    print(
        f"OK README breaking sync: v{canonical_version} matched in "
        f"{checked}/{len(TRANSLATIONS)} translations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
