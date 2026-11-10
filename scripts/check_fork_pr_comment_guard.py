#!/usr/bin/env python3
"""Steps that post to a PR must be skipped on fork PRs.

A fork PR runs with a read-only GITHUB_TOKEN, so a step that writes a PR
comment fails with "Resource not accessible by integration" and takes the
job, and required-gate/all-workflows, down with it (PR #934). The gate
fails when, in a workflow triggered by ``pull_request`` or ``workflow_call``
(a callee runs with its caller's token):

* a step that posts to the PR (sticky-pull-request-comment, github-script
  calling createComment / updateComment / createReview, ``gh pr comment`` /
  ``gh pr review``) has no fork guard: neither the step ``if`` nor the job
  ``if`` contains ``FORK_GUARD``, and the job is not
  ``continue-on-error: true``;
* a sticky-pull-request-comment step posts a ``path`` that no step in the
  same job writes to ``$GITHUB_STEP_SUMMARY``, so fork PR authors would not
  see the report at all.

Only the comment step is to be skipped. Skipping the whole job on forks
also skips the check, which is what this gate exists to avoid.

Usage:
    uv run python scripts/check_fork_pr_comment_guard.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
STICKY = "marocchino/sticky-pull-request-comment@"
SCRIPT_CALLS = ("createComment", "updateComment", "createReview")
RUN_CALLS = ("gh pr comment", "gh pr review")


def _events(doc: dict) -> set[str]:
    # PyYAML (YAML 1.1) reads the bare key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    if isinstance(on, dict):
        return set(on)
    return set()


def _posts_to_pr(step: dict) -> bool:
    uses = step.get("uses") or ""
    if uses.startswith(STICKY):
        return True
    if uses.startswith("actions/github-script@"):
        script = str((step.get("with") or {}).get("script", ""))
        if any(call in script for call in SCRIPT_CALLS):
            return True
    run = step.get("run") or ""
    return any(call in run for call in RUN_CALLS)


def _label(step: dict) -> str:
    return step.get("name") or step.get("uses") or "<unnamed step>"


def check(root: Path) -> list[str]:
    errors: list[str] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    for wf in workflows:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        # A workflow_call callee runs with its caller's token, which is the
        # read-only one when the caller is a fork PR.
        if not _events(doc) & {"pull_request", "workflow_call"}:
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            job_guarded = FORK_GUARD in str(job.get("if", ""))
            for step in steps:
                if not _posts_to_pr(step):
                    continue
                where = f"{wf.name} / {job_id} / {_label(step)}"
                guarded = (
                    job_guarded
                    or FORK_GUARD in str(step.get("if", ""))
                    or job.get("continue-on-error") is True
                )
                if not guarded:
                    errors.append(f"{where}: no fork guard")
                path = (step.get("with") or {}).get("path")
                if (step.get("uses") or "").startswith(STICKY) and path:
                    written = any(
                        "GITHUB_STEP_SUMMARY" in (s.get("run") or "")
                        and path in (s.get("run") or "")
                        for s in steps
                    )
                    if not written:
                        errors.append(
                            f"{where}: {path} is not written to $GITHUB_STEP_SUMMARY"
                        )
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    args = ap.parse_args(argv)
    errors = check(args.root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("OK: every step that posts to a PR is skipped on fork PRs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
