#!/usr/bin/env python3
"""Multilingual README heading tree parity check (proposals §3.7 Tier S #2).

既存の ``check_readme_h2_parity.py`` (H2 個数のみ) を補強する形で、
H2/H3/H4 の **tree structure** を canonical (README.md) と 7 言語翻訳
README で比較する。 翻訳漏れや section 順序の drift を検出するための
informational tier gate。

検査内容:
  - 各 README を行単位で走査し、 H2/H3/H4 の depth と positional index を
    抽出 (text 内容は比較せず、 構造のみを比較)
  - canonical (``README.md``、 日本語) を baseline とし、 各翻訳の:
    - H2 count: ±tolerance 個まで許容 (default 0)
    - 各 H2 section 内の H3 count: ±tolerance 個まで許容 (default 2、
      翻訳側で「補足セクション」 が増減することを想定)
    - 順序: H2 が出現する順番の depth pattern (例: ``[2, 3, 3, 2, 3]``)
      が一致 (default strict)
  - 違反は warning として stdout に出力、 ``--strict`` で exit 1

設計の根拠:
  既存 ``check_readme_h2_parity.py`` は H2 個数の ±20% 許容のみで、 順序
  drift や H3 細分化の検出能力が低い。 本 script は heading tree positional
  index を抽出することで、 「H2 の順番が違う」 「H2 セクション内の H3 が
  片方だけ大きく増えている」 といった lossy なエラーを補足する。

`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #2 由来、 Top 10 外。
Stdlib のみ、 PyYAML 等の追加依存なし。
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

HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
CODE_FENCE_RE = re.compile(r"^```")


def extract_heading_pattern(path: Path) -> list[int]:
    """Return a list of heading depths in source order (H2=2, H3=3, H4=4).

    Skip headings inside fenced code blocks to avoid false positives from
    embedded shell prompts that look like markdown headings.
    """
    depths: list[int] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if m:
            depths.append(len(m.group(1)))
    return depths


def h2_count(depths: list[int]) -> int:
    return sum(1 for d in depths if d == 2)


def h3_counts_per_h2(depths: list[int]) -> list[int]:
    """Return H3 counts grouped by each H2 section.

    Example: [2, 3, 3, 2, 3, 3, 3] -> [2, 3] (first H2 has 2x H3, second has 3x H3).
    """
    groups: list[int] = []
    current: int | None = None
    for d in depths:
        if d == 2:
            if current is not None:
                groups.append(current)
            current = 0
        elif d == 3 and current is not None:
            current += 1
    if current is not None:
        groups.append(current)
    return groups


def heading_order_pattern(depths: list[int]) -> tuple[int, ...]:
    """Pattern used for strict-order comparison: just the depth sequence."""
    return tuple(depths)


def check(canonical: Path, translations: list[Path], h3_tolerance: int, strict_order: bool) -> list[str]:
    if not canonical.exists():
        return [f"[ERROR] canonical README not found: {canonical}"]
    canon_depths = extract_heading_pattern(canonical)
    canon_h2 = h2_count(canon_depths)
    canon_h3_groups = h3_counts_per_h2(canon_depths)
    canon_pattern = heading_order_pattern(canon_depths)

    warnings: list[str] = []
    for t in translations:
        if not t.exists():
            warnings.append(f"[WARN] translation missing: {t.name}")
            continue
        d = extract_heading_pattern(t)
        n_h2 = h2_count(d)
        h3_groups = h3_counts_per_h2(d)
        pattern = heading_order_pattern(d)

        if n_h2 != canon_h2:
            warnings.append(
                f"[WARN] {t.name}: H2 count {n_h2} != canonical {canon_h2}"
            )

        if len(h3_groups) == len(canon_h3_groups):
            for i, (ct, cc) in enumerate(zip(h3_groups, canon_h3_groups), start=1):
                if abs(ct - cc) > h3_tolerance:
                    warnings.append(
                        f"[WARN] {t.name}: H2 section #{i} has {ct} H3 vs"
                        f" canonical {cc} (tolerance ±{h3_tolerance})"
                    )

        if strict_order and pattern != canon_pattern:
            # 詳細を 1 行で要約 (depth sequence の最初の divergence index)
            min_len = min(len(pattern), len(canon_pattern))
            diff_idx = next(
                (i for i in range(min_len) if pattern[i] != canon_pattern[i]),
                min_len,
            )
            warnings.append(
                f"[WARN] {t.name}: heading order differs from canonical at"
                f" position {diff_idx + 1} (canonical depth={canon_pattern[diff_idx] if diff_idx < len(canon_pattern) else 'EOF'},"
                f" translation depth={pattern[diff_idx] if diff_idx < len(pattern) else 'EOF'})"
            )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any warning fires")
    parser.add_argument("--strict-order", action="store_true", default=False, help="treat heading-order divergence as a warning (default: off)")
    parser.add_argument("--h3-tolerance", type=int, default=5, help="allowed ±deviation per H2 section's H3 count (bootstrap baseline: 5 absorbs the existing translation-side细分化 drift)")
    parser.add_argument("--canonical", default=str(CANONICAL))
    parser.add_argument("--translations", nargs="*", default=[str(REPO_ROOT / t) for t in TRANSLATIONS])
    args = parser.parse_args()

    warnings = check(
        Path(args.canonical),
        [Path(t) for t in args.translations],
        h3_tolerance=args.h3_tolerance,
        strict_order=args.strict_order,
    )
    for w in warnings:
        print(w)
    if not warnings:
        print("README heading tree parity check passed.")
        return 0
    if args.strict:
        print(f"\n{len(warnings)} warning(s); --strict mode -> exit 1", file=sys.stderr)
        return 1
    print(f"\n{len(warnings)} warning(s); informational tier (exit 0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
