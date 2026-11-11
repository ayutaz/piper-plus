#!/usr/bin/env python3
"""Steps that post to a PR must be skipped on fork PRs, and only those steps.

A fork PR runs with a read-only GITHUB_TOKEN, so a step that writes to the PR
fails with "Resource not accessible by integration" and takes the job, and
required-gate/all-workflows, down with it (PR #934). In a workflow triggered
by ``pull_request`` or ``workflow_call`` (a callee runs with its caller's
token), the gate fails when:

* a step that writes to the PR has no step-level fork guard. The step ``if``,
  split on its outermost ``&&``, must have one term that is exactly
  ``FORK_GUARD`` (whitespace and enclosing parentheses aside), or one that
  limits the step to ``push`` / ``workflow_dispatch`` / ``schedule``. An
  outermost ``||`` fails the guard (``<guard> || always()`` runs on forks
  too), and so do ``!(...)`` and ``== github.repository_owner``. A job-level
  guard and ``continue-on-error: true`` do not count: the first skips the
  check with the comment, the second still marks the failed step on the PR;
* a job ``if`` contains ``FORK_GUARD``: that skips the whole job, the check
  included, on every fork PR (until 2026-11 the size, memory and RTF checks
  never ran on forks for this reason);
* a sticky-pull-request-comment step posts a ``path`` that no step in the
  same job writes to ``$GITHUB_STEP_SUMMARY`` on the same ``run`` line, so
  fork PR authors would not see the report at all.

Writes, as detected: sticky-pull-request-comment; github-script calling
create/update/deleteComment, createReview(Comment), add/remove/setLabels,
requestReviewers, createCommitStatus, ``issues.update`` / ``pulls.update``,
``checks.create`` / ``checks.update``, a GraphQL mutation, or
``github.request`` with POST / PATCH / PUT / DELETE (as a string or as
``method:``); ``gh pr comment|review|edit`` and ``gh issue comment|edit``
(``-R`` allowed); any ``gh api`` call that is not a GET or a GraphQL query,
whatever its target, because every write fails with the read-only token
(lines continued with a backslash are joined first); benchmark-action with
``comment-on-alert`` or ``comment-always``. A script loaded with
``require()`` is not read. A new way to write gets a pattern here and a row
in the parametrized tests.

The fork guard may also be written reversed (``github.repository ==
...head.repo.full_name``) or as ``!github.event.pull_request.head.repo.fork``
/ ``... .fork == false``; a job ``if`` that reads ``head.repo.full_name`` or
``head.repo.fork`` at all is reported.

Usage:
    uv run python scripts/check_fork_pr_comment_guard.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml
from platform_utils import force_utf8_output


force_utf8_output()

REPO_ROOT = Path(__file__).resolve().parent.parent
FORK_GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
STICKY = "marocchino/sticky-pull-request-comment@"
BENCHMARK = "benchmark-action/github-action-benchmark@"
SCRIPT_CALLS = (
    "createComment",
    "updateComment",
    "deleteComment",
    "createReview",  # also matches createReviewComment
    "addLabels",
    "removeLabel",
    "setLabels",
    "requestReviewers",
    "createCommitStatus",
)
SCRIPT_WRITES = re.compile(
    r"""github\.request\(\s*['"`](POST|PATCH|PUT|DELETE)\b"""
    r"""|\bmethod\s*:\s*['"`](POST|PATCH|PUT|DELETE)\b"""
    r"""|\.(issues|pulls)\.update\("""
    r"""|\.checks\.(create|update)\("""
)
SCRIPT_GRAPHQL = re.compile(r"\bgraphql\(")
RUN_CALLS = re.compile(
    r"\bgh\s+(?:(?:-R|--repo)[\s=]\S+\s+)?"
    r"(pr\s+(comment|review|edit)|issue\s+(comment|edit))\b"
)
GH_API = re.compile(r"\bgh\s+api\b")
GH_API_METHOD = re.compile(r"""(?:^|\s)(?:-X|--method)(?:\s+|=)?['"]?([A-Za-z]+)""")
GH_API_FIELD = re.compile(r"(?:^|\s)(?:-[fF]|--field|--raw-field|--input)(?=[\s=]|\S)")
GH_API_GRAPHQL = re.compile(r"\bgh\s+api\s+graphql\b")
WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")
NON_PR_EVENTS = ("push", "workflow_dispatch", "schedule")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


# The fork guard, and the forms that mean the same.
FORK_GUARD_FORMS = {
    _squash(FORK_GUARD),
    "github.repository==github.event.pull_request.head.repo.full_name",
    "!github.event.pull_request.head.repo.fork",
    "github.event.pull_request.head.repo.fork==false",
}
GUARD_TERMS = FORK_GUARD_FORMS | {
    f"github.event_name=={q}{event}{q}" for event in NON_PR_EVENTS for q in "'\""
}
# Any job `if` that reads these decides by fork.
JOB_FORK_TERMS = ("head.repo.full_name", "head.repo.fork")


def _unwrap(expr: str) -> str:
    """Drop ``${{ }}`` and parentheses that enclose the whole expression."""
    expr = expr.strip()
    if expr.startswith("${{") and expr.endswith("}}"):
        expr = expr[3:-2].strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            depth += {"(": 1, ")": -1}.get(ch, 0)
            if depth == 0 and i < len(expr) - 1:
                return expr  # the first "(" closes before the end
        expr = expr[1:-1].strip()
    return expr


def _conjuncts(expr: str) -> list[str] | None:
    """Split *expr* on its outermost ``&&``; None if it has an outermost ``||``."""
    expr = _unwrap(expr)
    terms: list[str] = []
    depth = 0
    quote = ""
    start = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith("||", i):
            return None
        elif depth == 0 and expr.startswith("&&", i):
            terms.append(expr[start:i])
            start = i + 2
            i += 1
        i += 1
    terms.append(expr[start:])
    return [_unwrap(t) for t in terms]


def _step_guarded(step: dict) -> bool:
    terms = _conjuncts(str(step.get("if", "")))
    return terms is not None and any(_squash(t) in GUARD_TERMS for t in terms)


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _gh_api_writes(line: str) -> bool:
    """A ``gh api`` call writes unless it is a GET or a GraphQL query.

    Any write fails with the read-only token, so the target does not matter
    (it is often in a variable). Without ``-X`` / ``--method``, ``gh api``
    sends a POST when it has a field or an input.
    """
    method = GH_API_METHOD.search(line)
    if method:
        return method.group(1).upper() in WRITE_METHODS
    if GH_API_GRAPHQL.search(line):
        return "mutation" in line
    return GH_API_FIELD.search(line) is not None


def _run_lines(run: str) -> list[str]:
    """The lines of *run*, with lines that end in a backslash joined."""
    return re.sub(r"\\[ \t]*\n", " ", run).splitlines()


def _posts_to_pr(step: dict) -> bool:
    uses = str(step.get("uses") or "")
    with_ = step.get("with") if isinstance(step.get("with"), dict) else {}
    if uses.startswith(STICKY):
        return True
    if uses.startswith("actions/github-script@"):
        script = str(with_.get("script", ""))
        if any(call in script for call in SCRIPT_CALLS) or SCRIPT_WRITES.search(script):
            return True
        if SCRIPT_GRAPHQL.search(script) and "mutation" in script:
            return True
    if uses.startswith(BENCHMARK):
        if _truthy(with_.get("comment-on-alert")) or _truthy(with_.get("comment-always")):
            return True
    for line in _run_lines(str(step.get("run") or "")):
        if RUN_CALLS.search(line):
            return True
        if GH_API.search(line) and _gh_api_writes(line):
            return True
    return False


def _events(doc: dict) -> set[str]:
    # PyYAML (YAML 1.1) reads the bare key `on` as the boolean True.
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, (list, dict)):
        return {str(e) for e in on}
    return set()


def _label(step: dict) -> str:
    return step.get("name") or step.get("uses") or "<unnamed step>"


def _written_to_summary(path: str, steps: list[dict]) -> bool:
    return any(
        "GITHUB_STEP_SUMMARY" in line and path in line
        for s in steps
        for line in str(s.get("run") or "").splitlines()
    )


def check(root: Path) -> list[str]:
    errors: list[str] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.y*ml"))
    for wf in workflows:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            continue
        # A workflow_call callee runs with its caller's token, which is the
        # read-only one when the caller is a fork PR.
        if not _events(doc) & {"pull_request", "workflow_call"}:
            continue
        jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            job_if = _squash(str(job.get("if", "")))
            if any(term in job_if for term in JOB_FORK_TERMS):
                errors.append(
                    f"{wf.name} / {job_id}: job-level fork guard skips the whole "
                    "job on forks; guard the comment step instead"
                )
            raw_steps = job.get("steps") if isinstance(job.get("steps"), list) else []
            steps = [s for s in raw_steps if isinstance(s, dict)]
            for step in steps:
                if not _posts_to_pr(step):
                    continue
                where = f"{wf.name} / {job_id} / {_label(step)}"
                if not _step_guarded(step):
                    errors.append(
                        f"{where}: no fork guard (expected: if: ... && {FORK_GUARD})"
                    )
                with_ = step.get("with") if isinstance(step.get("with"), dict) else {}
                path = with_.get("path")
                if str(step.get("uses") or "").startswith(STICKY) and path:
                    if not _written_to_summary(str(path), steps):
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
