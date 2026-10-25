#!/usr/bin/env python3
"""Required status-check gate (M1.1 — cancelled / skipped baseline alarm).

GitHub branch protection treats ``cancelled`` and ``skipped`` workflow runs
as a pass (fail-open). PR #419 (memory ``feedback_ci_cancelled_baseline``)
showed how that lets a baseline collapse merge silently. This script is the
hub of a hub-and-spoke gateway: it asks the REST API for the latest run of
every monitored spoke workflow at ``head_sha`` and exits non-zero if any
spoke is missing, cancelled, skipped, failed, or timed out.

A spoke that is still running is reported but does NOT fail the gate — see
``classify`` for why deferring is both necessary (the gate fires while other
spokes run) and safe (the last spoke to complete triggers an authoritative
final firing).

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

``--all-workflows`` replaces the spoke list with every workflow run recorded
for ``head_sha`` (filtered by ``--event``, minus ``--exclude``), and
``--status-context`` publishes the verdict as a commit status on that SHA.
That is the mode the gate workflow uses: a ``workflow_run`` firing is recorded
against the default branch, so its own check never shows up on the PR, while a
commit status on the PR head does and can be required by a ruleset::

    python scripts/check_required_gate.py \
        --head-sha "$HEAD_SHA" --all-workflows --event pull_request \
        --exclude "Required Status Check Gate" --require-present CI \
        --status-context all-workflows --target-url "$RUN_URL"

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

# GitHub truncates a commit status description beyond this many characters.
STATUS_DESCRIPTION_MAX = 140


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
    # A PR head already carries ~55 runs; a single page of 100 would silently
    # drop the rest once the repository grows past that, and a dropped failed
    # run is a fail-open path. Walk every page.
    runs: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"head_sha": head_sha, "per_page": "100", "page": str(page)}
        )
        data = gh_get(f"/repos/{repo}/actions/runs?{query}", token)
        batch = list(data.get("workflow_runs", []))
        runs.extend(batch)
        if not batch or len(runs) >= int(data.get("total_count", 0)):
            return runs
        page += 1


def fetch_branch_head_sha(repo: str, branch: str, token: str) -> str:
    data = gh_get(f"/repos/{repo}/branches/{urllib.parse.quote(branch)}", token)
    return str(data["commit"]["sha"])


def pick_latest_per_workflow(
    runs: list[dict], monitored: list[str] | None, head_sha: str
) -> tuple[dict[str, SpokeRun], list[str]]:
    """Return (latest_run_per_workflow, missing_workflow_names).

    ``runs`` is the raw ``workflow_runs`` list from the REST API. We filter
    to entries whose ``head_sha`` matches and whose ``name`` is in
    ``monitored``, then keep the most recent ``run_number`` per workflow.
    Workflows that monitored expects but never appear are reported as
    missing — those are also a fail-open path (paths-filter skipped the
    workflow entirely, no run was queued). ``monitored=None`` keeps every
    workflow (``--all-workflows``) and reports nothing as missing.
    """
    best: dict[str, tuple[int, SpokeRun]] = {}
    for raw in runs:
        if raw.get("head_sha") != head_sha:
            continue
        name = raw.get("name")
        if monitored is not None and name not in monitored:
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
    missing = sorted(set(monitored or []) - set(by_name))
    return by_name, missing


def classify(
    spokes: dict[str, SpokeRun],
    *,
    on_cancelled: str,
    on_skipped: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return ``(bad, pending)`` spoke lists.

    ``bad`` are spokes that must fail the gate. ``pending`` are spokes that
    have not reached ``status == "completed"`` yet.

    Pending is deliberately NOT a failure. The gate is triggered by
    ``workflow_run: completed`` on each monitored spoke, so by construction
    it fires while the *other* spokes are still running: every firing but
    the last one would see a pending spoke. Treating that as a failure made
    2-7 of the ~3-8 firings per push red (38 failure / 22 success over the
    60 runs preceding this fix) and buried genuine gate failures in noise.

    Deferring is safe because the last monitored spoke to complete always
    triggers a final firing, and at that point every other monitored spoke
    has completed — so the authoritative evaluation always happens. This is
    the same reasoning as the ``--branch-for-supersede`` escape hatch, which
    already covered the "head_sha is stale" case but not this one.
    """
    bad: list[tuple[str, str]] = []
    pending: list[tuple[str, str]] = []
    for name, run in spokes.items():
        if run.status != "completed":
            pending.append((name, f"still {run.status}"))
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
    return bad, pending


def format_diagnostic(
    head_sha: str,
    missing: list[str],
    bad: list[tuple[str, str]],
    spokes: dict[str, SpokeRun],
    exempt_missing: list[str] | None = None,
    pending: list[tuple[str, str]] | None = None,
) -> str:
    deferred = bool(pending) and not missing and not bad
    heading = (
        "## Required status-check gate (deferred — spokes still running)"
        if deferred
        else "## Required status-check gate"
    )
    lines = [
        STICKY_MARKER,
        heading,
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
    if pending:
        lines.append(
            "**Spokes still running** (not a failure — the gate re-fires when "
            "each one completes):"
        )
        for name, reason in pending:
            url = spokes[name].html_url if name in spokes else ""
            suffix = f" — [run]({url})" if url else ""
            lines.append(f"- `{name}` → `{reason}`{suffix}")
        lines.append("")
    if exempt_missing:
        lines.append("**Paths-filtered spokes (intentionally not run on this push)**:")
        for name in exempt_missing:
            lines.append(f"- `{name}`")
        lines.append("")
    if deferred:
        lines.append(
            "Deferring: no spoke has failed so far. The final firing "
            "(triggered by the last monitored spoke to complete) is the "
            "authoritative evaluation."
        )
    elif not missing and not bad:
        if exempt_missing:
            # Don't emit the unqualified success line — it contradicts the
            # Paths-filtered section above (Copilot review on PR #587).
            lines.append(
                "All eligible spokes succeeded "
                "(paths-filtered spokes listed above did not run by design)."
            )
        else:
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


def post_commit_status(repo: str, sha: str, payload: dict, token: str) -> None:
    req = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/statuses/{sha}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    urllib.request.urlopen(req, timeout=30).close()


@dataclass(frozen=True)
class Verdict:
    state: str  # commit status state: success / failure / pending
    description: str
    body: str
    exit_code: int


def _summarise(state: str, count: int, names: list[str]) -> str:
    if state == "success":
        text = f"All {count} workflows succeeded"
    else:
        label = "failed" if state == "failure" else "waiting"
        text = f"{len(names)} {label}: " + ", ".join(names)
    if len(text) > STATUS_DESCRIPTION_MAX:
        text = text[: STATUS_DESCRIPTION_MAX - 3] + "..."
    return text


def parse_monitored(arg: str) -> list[str]:
    return [w.strip() for w in arg.split(",") if w.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--head-sha", required=True)
    p.add_argument(
        "--monitored",
        default="",
        help="Comma-separated list of spoke workflow names (case-sensitive).",
    )
    p.add_argument(
        "--all-workflows",
        action="store_true",
        help=(
            "Monitor every workflow run recorded for head-sha instead of "
            "--monitored. A run skipped as a whole (every job's `if:` false) "
            "passes; any other non-success conclusion fails."
        ),
    )
    p.add_argument(
        "--event",
        default="",
        help="Only count runs triggered by this event (e.g. pull_request).",
    )
    p.add_argument(
        "--exclude",
        default="",
        help="Comma-separated workflow names to leave out (the gate itself).",
    )
    p.add_argument(
        "--require-present",
        default="",
        help=(
            "Comma-separated workflows whose run must exist before the verdict "
            "can be success. Until then the verdict is pending: a firing right "
            "after the push can otherwise see only the fastest workflows."
        ),
    )
    p.add_argument(
        "--status-context",
        default="",
        help="If set, publish the verdict as a commit status with this context.",
    )
    p.add_argument("--target-url", default="", help="Link for the commit status.")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--on-cancelled", choices=["fail", "ignore"], default="fail")
    p.add_argument("--on-skipped", choices=["fail", "ignore"], default="fail")
    p.add_argument(
        "--paths-filtered",
        default="",
        help=(
            "Comma-separated list of monitored workflow names that have paths "
            "filters. If such a workflow is missing at head_sha (no run queued "
            "because the push diff didn't match its paths filter), treat it as "
            "OK instead of fail. The gate still fails if such a workflow DID "
            "run and produced cancelled/skipped/failure."
        ),
    )
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


def _load_runs(args: argparse.Namespace, token: str) -> list[dict] | None:
    if args.runs_json is not None:
        payload = json.loads(args.runs_json.read_text())
        return list(payload.get("workflow_runs", payload if isinstance(payload, list) else []))
    if not token or not args.repo:
        print("GITHUB_TOKEN and --repo (or GITHUB_REPOSITORY) required", file=sys.stderr)
        return None
    return fetch_runs_for_sha(args.repo, args.head_sha, token)


def _verdict(
    body: str,
    count: int,
    failed: list[str],
    pending: list[tuple[str, str]],
) -> Verdict:
    if failed:
        state, names = "failure", failed
    elif pending:
        state, names = "pending", [name for name, _ in pending]
    else:
        state, names = "success", []
    # `pending` alone defers (exit 0); a real failure still fails the gate
    # immediately even while other spokes run, so the signal is not delayed.
    return Verdict(
        state=state,
        description=_summarise(state, count, sorted(names)),
        body=body,
        exit_code=1 if failed else 0,
    )


def _evaluate_all_workflows(args: argparse.Namespace, runs: list[dict]) -> Verdict:
    excluded = set(parse_monitored(args.exclude))
    eligible = [
        r
        for r in runs
        if r.get("name") not in excluded and (not args.event or r.get("event") == args.event)
    ]
    spokes, _ = pick_latest_per_workflow(eligible, None, args.head_sha)
    # A workflow skipped as a whole (all jobs' `if:` false) is intentional
    # here: unlike a named spoke, nothing says it should have run.
    bad, pending = classify(spokes, on_cancelled=args.on_cancelled, on_skipped="ignore")
    absent = [n for n in parse_monitored(args.require_present) if n not in spokes]
    pending = pending + [(name, "no run yet") for name in absent]
    body = format_diagnostic(args.head_sha, [], bad, spokes, None, pending)
    return _verdict(body, len(spokes), [name for name, _ in bad], pending)


def evaluate(args: argparse.Namespace) -> Verdict | None:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not args.all_workflows and not parse_monitored(args.monitored):
        print("--monitored is empty (or pass --all-workflows)", file=sys.stderr)
        return None
    runs = _load_runs(args, token)
    if runs is None:
        return None

    latest_sha = args.latest_sha_for_supersede
    if not latest_sha and args.branch_for_supersede and args.runs_json is None:
        latest_sha = fetch_branch_head_sha(args.repo, args.branch_for_supersede, token)
    if latest_sha and latest_sha != args.head_sha:
        body = format_deferred(args.head_sha, latest_sha)
        return Verdict("pending", "Superseded by a newer commit", body, 0)

    if args.all_workflows:
        return _evaluate_all_workflows(args, runs)

    monitored = parse_monitored(args.monitored)
    spokes, missing = pick_latest_per_workflow(runs, monitored, args.head_sha)
    paths_filtered = parse_monitored(args.paths_filtered) if args.paths_filtered else []
    exempt_missing = [m for m in missing if m in paths_filtered]
    missing = [m for m in missing if m not in paths_filtered]
    bad, pending = classify(
        spokes, on_cancelled=args.on_cancelled, on_skipped=args.on_skipped
    )
    body = format_diagnostic(
        args.head_sha, missing, bad, spokes, exempt_missing, pending
    )
    return _verdict(body, len(spokes), missing + [name for name, _ in bad], pending)


def run(args: argparse.Namespace) -> int:
    verdict = evaluate(args)
    if verdict is None:
        return 2
    print(verdict.body)
    token = os.environ.get("GITHUB_TOKEN", "")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(verdict.body)
    if args.post_pr_comment and token and args.repo and args.runs_json is None:
        upsert_sticky_comment(args.repo, args.post_pr_comment, verdict.body, token)
    if args.status_context and token and args.repo:
        post_commit_status(
            args.repo,
            args.head_sha,
            {
                "state": verdict.state,
                "context": args.status_context,
                "description": verdict.description,
                "target_url": args.target_url,
            },
            token,
        )
    return verdict.exit_code


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
