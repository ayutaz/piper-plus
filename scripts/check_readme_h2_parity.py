#!/usr/bin/env python3
"""Multilingual README H2 section parity gate (Wave 3).

`README.md` (Japanese canonical) と 7 言語 README (EN/ZH/DE/ES/FR/KO/PT) の
H2 section 個数を比較し、 大幅な乖離を warning で報告する。

なぜ canonical を Japanese にするか:
  本リポは作者が日本語話者で、 README.md = JP が history 上 first-author
  された。 EN は派生翻訳。 ただし structure 観点では JP/EN の section 数は
  概ね一致するため、 どちらを canonical にしても本 gate の判定は変わらない。

検証内容:
  - 各 README の H2 行 (``## ...`` で始まる) 個数を集計
  - canonical (README.md) の H2 個数を baseline とし、 他言語が ±20% 以内
    かを確認
  - 乖離があれば warning (merge を block しない、 翻訳遅延を許容するため)

Tolerance を 20% にしている理由:
  PR #498 wave2 調査で ZH README は H3 細分化のため H1/H3 count が 1.5-2x
  だった。 一方 H2 count は 13 一致だった。 つまり H2 は section topic の
  目印として安定しており、 ±20% であれば「意図的細分化」 vs 「翻訳漏れ」 を
  区別できる閾値。

Pre-commit 統合 (warning モード):
  - README*.md のいずれかが変更されたときに走る
  - failure ではなく warning のみ (--strict で fail に切替可)

Usage:
    uv run python scripts/check_readme_h2_parity.py
    uv run python scripts/check_readme_h2_parity.py --strict
    uv run python scripts/check_readme_h2_parity.py --verbose

Exit codes:
  0 -- 全 README が tolerance 内 (warning は出力するが exit 0)
  1 -- --strict 指定 + tolerance 超過、 もしくは canonical 存在しない
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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

H2_RE = re.compile(r"^##\s+\S")
DEFAULT_TOLERANCE = 0.20  # ±20%


def count_h2(path: Path) -> tuple[int, list[str]]:
    """Return (h2_count, h2_headings)."""
    if not path.exists():
        return 0, []
    headings: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if H2_RE.match(line):
            # strip leading "## " and trailing whitespace
            headings.append(line[3:].strip())
    return len(headings), headings


def main() -> int:
    parser = argparse.ArgumentParser(description="README H2 parity gate")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on tolerance exceeded (default: warn only)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="print full H2 lists per file")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE,
                        help=f"max relative diff (default {DEFAULT_TOLERANCE})")
    args = parser.parse_args()

    if not CANONICAL.exists():
        print(f"error: canonical {CANONICAL} not found", file=sys.stderr)
        return 1

    canon_count, canon_headings = count_h2(CANONICAL)
    if canon_count == 0:
        print(f"warning: canonical {CANONICAL.name} has 0 H2 sections — "
              "skipping comparison", file=sys.stderr)
        return 0

    print(f"canonical {CANONICAL.name}: {canon_count} H2 sections")
    if args.verbose:
        for h in canon_headings:
            print(f"  - {h}")

    out_of_tolerance: list[str] = []
    missing: list[str] = []

    for translation in TRANSLATIONS:
        path = REPO_ROOT / translation
        count, headings = count_h2(path)
        if count == 0:
            missing.append(translation)
            continue
        diff = (count - canon_count) / canon_count
        marker = "OK"
        if abs(diff) > args.tolerance:
            marker = f"DRIFT (diff {diff:+.1%})"
            out_of_tolerance.append(
                f"{translation}: {count} H2 vs canonical {canon_count} "
                f"(diff {diff:+.1%}, tolerance ±{args.tolerance:.0%})"
            )
        print(f"  {translation}: {count} H2 sections [{marker}]")
        if args.verbose:
            for h in headings:
                print(f"    - {h}")

    if missing:
        print("\nwarning: README translations missing:", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)

    if out_of_tolerance:
        print("\nwarning: H2 count drift detected:", file=sys.stderr)
        for line in out_of_tolerance:
            print(f"  {line}", file=sys.stderr)
        if args.strict:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
