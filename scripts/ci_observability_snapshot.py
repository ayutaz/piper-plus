#!/usr/bin/env python3
"""CI flake / cancel / skip observability snapshot (proposals §3.9 #1).

`docs/proposals/ci-expansion-2026-05.md` §3.9 #1 由来、 Top 10 外の CI
observability 拡張。 M1.1 cancelled baseline alarm が「個別 PR の cancelled
silent skip」 を gate するのに対し、 本 script は「過去 N 日の workflow run
を集計して flake / cancel / skip 比率を可視化する」 trend dashboard の data
layer を提供する。

機能:
  - `gh run list -L <N> --json conclusion,workflowName,status,createdAt` を
    実行し、 過去 ``--days`` (default 7) の run を workflow 単位に集計
  - 各 workflow について total / success / failure / cancelled / skipped
    count + cancellation_rate / failure_rate を算出
  - cancellation_rate > ``--cancel-threshold`` (default 0.10) の workflow を
    "flake watch" 候補として明示
  - 結果を JSON artifact (default ``/tmp/ci-observability.json``) に書き出し

Stdlib + ``gh`` CLI のみ。 GitHub-hosted runner では ``gh`` が pre-installed。
informational tier (PR を block せず、 schedule で trend を観測)。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def fetch_runs(limit: int) -> list[dict[str, Any]]:
    """Return up to ``limit`` recent runs via ``gh run list --json ...``."""
    cmd = [
        "gh",
        "run",
        "list",
        "-L",
        str(limit),
        "--json",
        "conclusion,workflowName,status,createdAt,databaseId",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def filter_window(
    runs: list[dict[str, Any]], days: int, now: datetime | None = None
) -> list[dict[str, Any]]:
    cutoff = (now or datetime.now(tz=UTC)) - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for r in runs:
        # createdAt is ISO-8601 e.g. "2026-05-18T11:14:46Z"
        ts = r.get("createdAt", "")
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if dt >= cutoff:
            out.append(r)
    return out


def aggregate(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "total": 0,
            "success": 0,
            "failure": 0,
            "cancelled": 0,
            "skipped": 0,
            "in_progress": 0,
            "other": 0,
        }
    )
    for r in runs:
        wf = r.get("workflowName", "<unknown>")
        conc = (r.get("conclusion") or "").lower() or "in_progress"
        if r.get("status") == "in_progress":
            buckets[wf]["in_progress"] += 1
        else:
            key = {
                "success": "success",
                "failure": "failure",
                "cancelled": "cancelled",
                "skipped": "skipped",
            }.get(conc, "other")
            buckets[wf][key] += 1
        buckets[wf]["total"] += 1
    out: dict[str, dict[str, Any]] = {}
    for wf, b in buckets.items():
        total = b["total"]
        out[wf] = {
            **b,
            "cancellation_rate": (b["cancelled"] / total) if total else 0.0,
            "failure_rate": (b["failure"] / total) if total else 0.0,
            "success_rate": (b["success"] / total) if total else 0.0,
        }
    return out


def flake_candidates(
    stats: dict[str, dict[str, Any]], cancel_threshold: float, min_runs: int
) -> list[str]:
    out: list[str] = []
    for wf, s in stats.items():
        if s["total"] < min_runs:
            continue
        if s["cancellation_rate"] > cancel_threshold:
            out.append(
                f"{wf}: cancelled {s['cancelled']}/{s['total']}"
                f" ({s['cancellation_rate']:.1%}) > {cancel_threshold:.0%} threshold"
            )
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="max runs fetched from gh (default 1000)",
    )
    parser.add_argument(
        "--days", type=int, default=7, help="window in days (default 7)"
    )
    parser.add_argument(
        "--cancel-threshold",
        type=float,
        default=0.10,
        help="flake-watch threshold for cancellation_rate (default 0.10)",
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=5,
        help="ignore workflows with fewer total runs (default 5)",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/ci-observability.json")
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="testing aid: read runs from a JSON file instead of running gh",
    )
    args = parser.parse_args()

    if args.input:
        runs_all = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        try:
            runs_all = fetch_runs(args.limit)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"[ERROR] gh CLI failed: {e}", file=sys.stderr)
            return 2

    window = filter_window(runs_all, days=args.days)
    stats = aggregate(window)
    flakes = flake_candidates(
        stats, cancel_threshold=args.cancel_threshold, min_runs=args.min_runs
    )
    snapshot = {
        "generated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": args.days,
        "total_runs_in_window": len(window),
        "workflows": stats,
        "flake_candidates": flakes,
        "cancel_threshold": args.cancel_threshold,
    }
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"snapshot written: {args.output}")
    print(f"total runs (last {args.days}d): {len(window)}")
    if flakes:
        print(
            f"\nflake watch ({len(flakes)} workflow(s) over {args.cancel_threshold:.0%} cancel rate):"
        )
        for f in flakes:
            print(f"  - {f}")
    else:
        print("no flake watch candidates (informational tier).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
