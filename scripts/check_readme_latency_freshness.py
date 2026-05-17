#!/usr/bin/env python3
# Wave 5-6 — README latency table freshness checker.
#
# Why: README.md の Latency P50 表 (27ms / 35ms / 53ms 等) は hardcoded だが
#   benchmark 再実行と sync する仕組みがない。 ベンチ実機環境 (Xeon E5-2650 v4)
#   や測定スクリプトの変更を catch するため、 最終更新日が一定期間以上前なら
#   warning を出す。 値そのものの正しさは check しない (CI runner と原実機で
#   spec が異なるため byte-for-byte 比較は不可)。
#
# How to apply: warning-only。 git log から README.md の Benchmark セクション
#   touch 日を取得、 freshness_days を超えていたら warn 出力。 90 日 default。
#   block しない (新規ベンチを強制すると流れが詰まる)。

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

from platform_utils import force_utf8_output

force_utf8_output()

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
FRESHNESS_DAYS = 90

# Latency 数値を含む行の anchor (README で table 周辺を grep)
LATENCY_ANCHORS = [
    r"Latency P50",
    r"\d+ms",
    r"RTF",
]


def _readme_section_last_touch(path: Path, anchor: str) -> dt.date | None:
    """Anchor を含む line range の git log 最新 commit date を返す。

    `git log -L:<regex>:<file>` でその anchor 周辺の history を絞り込み、
    最新の author date を 1 つ取得。 git history が取れない (e.g.
    shallow clone) は None を返して silent skip。
    """
    try:
        # 単純化: README 全体の最後 commit date を取る (anchor 別の絞り込みは
        # `-L` regex で複雑になりやすい。 全体 freshness で十分目的を満たす)。
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%aI", "--", str(path.relative_to(ROOT))],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if not out:
            return None
        return dt.datetime.fromisoformat(out).date()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main() -> int:
    if not README.exists():
        print(f"::warning::README.md not found at {README}", file=sys.stderr)
        return 0

    text = README.read_text(encoding="utf-8")
    has_latency = any(re.search(p, text) for p in LATENCY_ANCHORS)
    if not has_latency:
        # Latency 表のない README は監視対象外
        print("[check_readme_latency_freshness] no latency anchors found, skip")
        return 0

    last_date = _readme_section_last_touch(README, "Latency P50")
    if last_date is None:
        print(
            "[check_readme_latency_freshness] git history unavailable "
            "(shallow clone?) — skip",
            file=sys.stderr,
        )
        return 0

    age_days = (dt.date.today() - last_date).days
    if age_days <= FRESHNESS_DAYS:
        print(
            f"[check_readme_latency_freshness] OK — README last touched "
            f"{age_days} day(s) ago (≤ {FRESHNESS_DAYS} d threshold)"
        )
        return 0

    print(
        f"::warning file=README.md::README latency table appears stale: "
        f"last commit {age_days} days ago (threshold {FRESHNESS_DAYS} d). "
        f"Consider re-running tools/benchmark/ and refreshing the table."
    )
    print(
        f"[check_readme_latency_freshness] WARN — README touched "
        f"{age_days} days ago (> {FRESHNESS_DAYS}). Warning-only, not blocking."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
