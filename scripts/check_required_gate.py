#!/usr/bin/env python3
"""Required status-check gate (M1.1 — cancelled / skipped baseline alarm).

GitHub branch protection treats ``cancelled`` and ``skipped`` workflow runs
as a pass (fail-open). PR #419 (memory ``feedback_ci_cancelled_baseline``)
showed how that lets a baseline collapse merge silently. This script is the
hub of a hub-and-spoke gateway: it asks the REST API for the latest run of
every monitored spoke workflow at ``head_sha`` and exits non-zero if any
spoke is missing, cancelled, skipped, failed, or timed out.

The script is deliberately stdlib-only (``urllib`` + ``json``) so the gate
workflow has no install step. ``GITHUB_TOKEN`` (read-only ``actions:read``
+ ``pull-requests:write`` is enough) is read from the environment.

CLI usage::

    python scripts/check_required_gate.py \
        --head-sha "$HEAD_SHA" \
        --monitored "Multi-Runtime RTF Benchmark,CodeQL,Parity Hub" \
        --repo owner/name \
        [--on-cancelled fail] [--on-skipped fail] \
        [--post-pr-comment 123] \
        [--latest-sha-for-supersede $(git rev-parse origin/dev)]

For unit tests the network layer is replaced via ``--runs-json`` (path to a
pre-recorded ``GET /actions/runs?head_sha=...`` payload) and
``--latest-sha-for-supersede`` (skips the second REST call).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

GITHUB_API = "https://api.github.com"
USER_AGENT = "piper-plus-required-gate/1.0"
STICKY_MARKER = "<!-- required-status-check-gate -->"

# Conclusions that branch protection treats as pass but we want to reject.
FAIL_OPEN_CONCLUSIONS = {"cancelled", "skipped", "failure", "timed_out", "action_required"}


@dataclass(frozen=True)
class SpokeRun:
    name: str
    conclusion: str | None
    status: str
    head_sha: str
    html_url: str
    run_id: int


def gh_get(path: str, token: str, *, max_retries: int = 4) -> dict:
    url = f"{GITHUB_API}{path}"
    backoff = 1.0
    last_err: Exception | None = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (403, 429) and attempt < max_retries - 1:
                reset = exc.headers.get("X-RateLimit-Reset")
                sleep_for = backoff
                if reset and reset.isdigit():
                    sleep_for = max(sleep_for, int(reset) - int(time.time()) + 1)
                time.sleep(min(sleep_for, 60))
                backoff *= 2
                continue
            raise
        except urllib.error.URLError as exc:
            last_err = exc
            if attempt < max_retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise
    raise RuntimeError(f"gh_get failed: {last_err}")


def fetch_runs_for_sha(repo: str, head_sha: str, token: str) -> list[dict]:
    query = urllib.parse.urlencode({"head_sha": head_sha, "per_page": "100"})
    data = gh_get(f"/repos/{repo}/actions/runs?{query}", token)
    return list(data.get("workflow_runs", []))


def fetch_branch_head_sha(repo: str, branch: str, token: str) -> str:
    data = gh_get(f"/repos/{repo}/branches/{urllib.parse.quote(branch)}", token)
    return str(data["commit"]["sha"])


def pick_latest_per_workflow(
    runs: list[dict], monitored: list[str], head_sha: str
) -> tuple[dict[str, SpokeRun], list[str]]:
    """Return (latest_run_per_workflow, missing_workflow_names).

    ``runs`` is the raw ``workflow_runs`` list from the REST API. We filter
    to entries whose ``head_sha`` matches and whose ``name`` is in
    ``monitored``, then keep the most recent ``run_number`` per workflow.
    Workflows that monitored expects but never appear are reported as
    missing — those are also a fail-open path (paths-filter skipped the
    workflow entirely, no run was queued).
    """
    best: dict[str, tuple[int, SpokeRun]] = {}
    for raw in runs:
        if raw.get("head_sha") != head_sha:
            continue
        name = raw.get("name")
        if name not in monitored:
            continue
        run_number = int(raw.get("run_number", 0))
        candidate = SpokeRun(
            name=name,
            conclusion=raw.get("conclusion"),
            status=raw.get("status", ""),
            head_sha=raw["head_sha"],
            html_url=raw.get("html_url", ""),
            run_id=int(raw.get("id", 0)),
        )
        prev = best.get(name)
        if prev is None or run_number >= prev[0]:
            best[name] = (run_number, candidate)
    by_name = {name: run for name, (_, run) in best.items()}
    missing = sorted(set(monitored) - set(by_name))
    return by_name, missing


def classify(
    spokes: dict[str, SpokeRun],
    *,
    on_cancelled: str,
    on_skipped: str,
) -> list[tuple[str, str]]:
    """Return [(workflow_name, reason)] of spokes that must fail the gate."""
    bad: list[tuple[str, str]] = []
    for name, run in spokes.items():
        if run.status != "completed":
            bad.append((name, f"still {run.status}"))
            continue
        conclusion = run.conclusion or "missing"
        if conclusion == "success":
            continue
        # `neutral` is what the first-PR fast lane (M1.3) writes when it
        # downgrades a contract gate to a warning. We honour that here so
        # the cancelled-baseline gateway doesn't undo the fast lane.
        if conclusion == "neutral":
            continue
        if conclusion == "cancelled" and on_cancelled != "fail":
            continue
        if conclusion == "skipped" and on_skipped != "fail":
            continue
        if conclusion in FAIL_OPEN_CONCLUSIONS:
            bad.append((name, conclusion))
        elif conclusion != "success":
            bad.append((name, conclusion))
    return bad


def format_diagnostic(
    head_sha: str,
    missing: list[str],
    bad: list[tuple[str, str]],
    spokes: dict[str, SpokeRun],
) -> str:
    lines = [
        STICKY_MARKER,
        "## Required status-check gate",
        "",
        f"Head SHA: `{head_sha[:7]}`",
        "",
    ]
    if missing:
        lines.append("**Missing spokes** (no run queued — paths filter or trigger gap):")
        for name in missing:
            lines.append(f"- `{name}`")
        lines.append("")
    if bad:
        lines.append("**Non-success spokes** (cancelled / skipped / failure / timed_out):")
        for name, reason in bad:
            url = spokes[name].html_url if name in spokes else ""
            suffix = f" — [run]({url})" if url else ""
            lines.append(f"- `{name}` → `{reason}`{suffix}")
        lines.append("")
    if not missing and not bad:
        lines.append("All monitored spokes succeeded.")
    return "\n".join(lines).rstrip() + "\n"


def format_deferred(head_sha: str, latest_sha: str) -> str:
    return (
        f"{STICKY_MARKER}\n"
        "## Required status-check gate (deferred)\n\n"
        f"Head SHA `{head_sha[:7]}` is no longer the branch tip "
        f"(latest: `{latest_sha[:7]}`). Waiting for the new commit's "
        "spoke runs to complete before re-evaluating.\n"
    )


def upsert_sticky_comment(repo: str, pr_number: int, body: str, token: str) -> None:
    comments = gh_get(
        f"/repos/{repo}/issues/{pr_number}/comments?per_page=100", token
    )
    target_id: int | None = None
    if isinstance(comments, list):
        for c in comments:
            if STICKY_MARKER in (c.get("body") or ""):
                target_id = int(c["id"])
                break
    payload = json.dumps({"body": body}).encode("utf-8")
    if target_id is None:
        url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
        method = "POST"
    else:
        url = f"{GITHUB_API}/repos/{repo}/issues/comments/{target_id}"
        method = "PATCH"
    req = urllib.request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    urllib.request.urlopen(req, timeout=30).close()


def parse_monitored(arg: str) -> list[str]:
    return [w.strip() for w in arg.split(",") if w.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--head-sha", required=True)
    p.add_argument(
        "--monitored",
        required=True,
        help="Comma-separated list of spoke workflow names (case-sensitive).",
    )
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--on-cancelled", choices=["fail", "ignore"], default="fail")
    p.add_argument("--on-skipped", choices=["fail", "ignore"], default="fail")
    p.add_argument("--post-pr-comment", type=int, default=None)
    p.add_argument(
        "--branch-for-supersede",
        default="",
        help="If set, gate defers when head-sha != branch tip.",
    )
    p.add_argument(
        "--latest-sha-for-supersede",
        default="",
        help="Test hook: skip the branch-tip REST call.",
    )
    p.add_argument(
        "--runs-json",
        type=Path,
        default=None,
        help="Test hook: read workflow_runs JSON from a file instead of REST.",
    )
    return p


def run(args: argparse.Namespace) -> int:
    monitored = parse_monitored(args.monitored)
    if not monitored:
        print("--monitored is empty", file=sys.stderr)
        return 2
    token = os.environ.get("GITHUB_TOKEN", "")
    if args.runs_json is not None:
        payload = json.loads(args.runs_json.read_text())
        runs = list(payload.get("workflow_runs", payload if isinstance(payload, list) else []))
    else:
        if not token or not args.repo:
            print("GITHUB_TOKEN and --repo (or GITHUB_REPOSITORY) required", file=sys.stderr)
            return 2
        runs = fetch_runs_for_sha(args.repo, args.head_sha, token)

    latest_sha = args.latest_sha_for_supersede
    if not latest_sha and args.branch_for_supersede and args.runs_json is None:
        latest_sha = fetch_branch_head_sha(args.repo, args.branch_for_supersede, token)
    if latest_sha and latest_sha != args.head_sha:
        body = format_deferred(args.head_sha, latest_sha)
        print(body)
        if args.post_pr_comment and token and args.repo:
            upsert_sticky_comment(args.repo, args.post_pr_comment, body, token)
        return 0

    spokes, missing = pick_latest_per_workflow(runs, monitored, args.head_sha)
    bad = classify(spokes, on_cancelled=args.on_cancelled, on_skipped=args.on_skipped)
    body = format_diagnostic(args.head_sha, missing, bad, spokes)
    print(body)
    if args.post_pr_comment and token and args.repo and args.runs_json is None:
        upsert_sticky_comment(args.repo, args.post_pr_comment, body, token)
    return 1 if (missing or bad) else 0


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
