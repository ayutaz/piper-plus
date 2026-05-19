#!/usr/bin/env python3
"""Weekly first-PR fast lane health snapshot (M1.3).

Runs on a schedule and counts:

* PRs merged in the last 7 days where the original author had
  ``author_association ∈ {FIRST_TIME_CONTRIBUTOR, FIRST_TIMER, NONE}``.
* Of those, how many ended up with a maintainer follow-up commit/PR within
  14 days (a proxy for "fast lane let something slip through").

The output is appended to ``docs/reference/first-pr-metrics.md`` as a
single dated row. The 4-week (and later 12-week) review of those rows
informs whether the fast lane stays, gets tightened, or gets retired —
i.e., the success criterion in the M1.3 ticket.

stdlib only; uses ``urllib`` + ``json`` and reads ``GITHUB_TOKEN`` /
``GITHUB_REPOSITORY`` from the environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


GITHUB_API = "https://api.github.com"
USER_AGENT = "piper-plus-first-pr-health/1.0"

FAST_LANE_ASSOC = {"FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"}


def gh_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{GITHUB_API}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def list_recently_merged_prs(repo: str, since: dt.datetime, token: str) -> list[dict]:
    """Return PRs merged into the default branch in the last `since..now` window.

    Uses search API ``is:merged merged:>YYYY-MM-DD`` — cheaper than walking
    the full PR list. Caps at the first 100 results which is plenty for a
    7-day window in piper-plus's typical merge rate.
    """
    q = f"repo:{repo} is:pr is:merged merged:>={since.strftime('%Y-%m-%d')}"
    params = urllib.parse.urlencode({"q": q, "per_page": "100"})
    data = gh_get(f"/search/issues?{params}", token)
    return list(data.get("items", []))


def pr_author_association(repo: str, pr: int, token: str) -> str:
    data = gh_get(f"/repos/{repo}/pulls/{pr}", token)
    return str(data.get("author_association", "NONE"))


def count_followup_commits(
    repo: str, pr_number: int, after: dt.datetime, token: str
) -> int:
    """A *very rough* proxy: how many later commits to the default branch
    mention this PR number in their message? In practice GitHub UI shows
    "linked PRs" but the API for that is finicky, so we keyword-match.
    """
    since = after.strftime("%Y-%m-%dT%H:%M:%SZ")
    commits = gh_get(
        f"/repos/{repo}/commits?since={since}&per_page=100",
        token,
    )
    if not isinstance(commits, list):
        return 0
    needle = f"#{pr_number}"
    return sum(
        1 for c in commits if needle in (c.get("commit", {}).get("message") or "")
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument(
        "--metrics-md",
        type=Path,
        default=Path("docs/reference/first-pr-metrics.md"),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token or not args.repo:
        print("GITHUB_TOKEN + --repo (or GITHUB_REPOSITORY) required", file=sys.stderr)
        return 2

    now = dt.datetime.now(dt.UTC)
    since = now - dt.timedelta(days=args.window_days)

    merged = list_recently_merged_prs(args.repo, since, token)
    first_pr_count = 0
    followup_count = 0
    for item in merged:
        number = int(item["number"])
        try:
            assoc = pr_author_association(args.repo, number, token)
        except Exception as exc:  # pragma: no cover (network)
            print(f"WARN: PR #{number} lookup failed: {exc}", file=sys.stderr)
            continue
        if assoc not in FAST_LANE_ASSOC:
            continue
        first_pr_count += 1
        followup = count_followup_commits(args.repo, number, since, token)
        if followup > 0:
            followup_count += 1

    follow_pct = (followup_count / first_pr_count * 100) if first_pr_count else 0.0
    row = (
        f"| {now.strftime('%Y-%m-%d')} | {args.window_days}d | {first_pr_count} "
        f"| {followup_count} | {follow_pct:.1f}% |"
    )
    print(row)

    md = args.metrics_md
    if not md.exists():
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(
            "# First-PR fast lane health metrics\n\n"
            "Weekly snapshot produced by `scripts/first_pr_health.py`. The\n"
            "`follow-up %` column is a rough proxy for how often a maintainer\n"
            "had to fix something the fast lane let through. Sustained >5%\n"
            "is the trigger to tighten the lane (M1.3 success criterion).\n\n"
            "| date | window | first-PR merged | with follow-up | follow-up % |\n"
            "|------|--------|----------------|----------------|-------------|\n",
            encoding="utf-8",
        )
    with md.open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
