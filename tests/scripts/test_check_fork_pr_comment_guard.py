"""Steps that post to a PR must be skipped on fork PRs, and only those steps.

Regression focus: PR #934 (2026-11, the first fork PR in months) failed
required-gate/all-workflows although every check passed. Five sticky-comment
steps ran with the fork's read-only GITHUB_TOKEN and failed with "Resource
not accessible by integration". A fork PR has to be able to go green; only
the comment is skipped, never the check, and the report the comment would
have carried is written to the job summary instead.

Follow-up (2026-11): four workflows skipped whole jobs on forks (the size,
memory and RTF checks never ran), the gate accepted that, and a guard such
as ``<guard> || always()`` passed because the gate only searched for the
guard text. A new way to write to a PR gets a row in the parametrized
tables below.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_fork_pr_comment_guard.py"

GUARD = "github.event.pull_request.head.repo.full_name == github.repository"
EXPECTED = f"(expected: if: ... && {GUARD})"
NO_GUARD = f"ci.yml / build / Post sticky: no fork guard {EXPECTED}"
COMMENT_NO_GUARD = f"ci.yml / build / Comment: no fork guard {EXPECTED}"
JOB_GUARD = (
    "ci.yml / build: job-level fork guard skips the whole job on forks; "
    "guard the comment step instead"
)


def _load_module():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "check_fork_pr_comment_guard", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _write(root: Path, text: str, name: str = "ci.yml") -> None:
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(textwrap.dedent(text), encoding="utf-8")


def _sticky_workflow(
    *,
    on: str = "on: pull_request",
    step_if: str | None = "github.event_name == 'pull_request'",
    job_extra: str = "",
    path: str | None = None,
    summary_step: bool = False,
) -> str:
    lines = [on, "jobs:", "  build:", "    runs-on: ubuntu-24.04"]
    if job_extra:
        lines.append(f"    {job_extra}")
    lines.append("    steps:")
    if summary_step:
        lines += [
            "      - name: Write report to job summary",
            f'        run: cat {path} >> "$GITHUB_STEP_SUMMARY"',
        ]
    lines += [
        "      - name: Post sticky",
        "        uses: marocchino/sticky-pull-request-comment@v2.9.4",
    ]
    if step_if is not None:
        lines.append(f'        if: "{step_if}"')
    lines += ["        with:", "          header: report"]
    if path is not None:
        lines.append(f"          path: {path}")
    return "\n".join(lines) + "\n"


def _run_step(run: str) -> str:
    return textwrap.dedent(
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Comment
                run: {run}
        """
    )


def _script_step(script: str) -> str:
    return textwrap.dedent(
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Comment
                uses: actions/github-script@v7.1.0
                with:
                  script: "{script}"
        """
    )


def test_unguarded_sticky_step_is_reported(gate, tmp_path):
    _write(tmp_path, _sticky_workflow())
    assert gate.check(tmp_path) == [NO_GUARD]


def test_step_level_guard_passes(gate, tmp_path):
    _write(
        tmp_path,
        _sticky_workflow(step_if=f"github.event_name == 'pull_request' && {GUARD}"),
    )
    assert gate.check(tmp_path) == []


def test_job_level_guard_is_reported(gate, tmp_path):
    # Skipping the job on forks skips the check too; only the comment may go.
    job_if = f"if: \"{GUARD} || github.event_name != 'pull_request'\""
    _write(tmp_path, _sticky_workflow(job_extra=job_if))
    assert gate.check(tmp_path) == [JOB_GUARD, NO_GUARD]


def test_job_continue_on_error_is_reported(gate, tmp_path):
    # The job stays green, but the failed step still shows on the fork PR.
    _write(tmp_path, _sticky_workflow(job_extra="continue-on-error: true"))
    assert gate.check(tmp_path) == [NO_GUARD]


def test_job_guard_without_comment_step_is_reported(gate, tmp_path):
    _write(
        tmp_path,
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            if: {GUARD}
            steps:
              - run: make check
        """,
    )
    assert gate.check(tmp_path) == [JOB_GUARD]


def test_guard_inside_expression_wrapper_passes(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(step_if="${{ !cancelled() && " + GUARD + " }}"))
    assert gate.check(tmp_path) == []


def test_negated_guard_is_reported(gate, tmp_path):
    negated = "github.event.pull_request.head.repo.full_name != github.repository"
    _write(tmp_path, _sticky_workflow(step_if=negated))
    assert gate.check(tmp_path) == [NO_GUARD]


@pytest.mark.parametrize(
    "step_if",
    [
        f"{GUARD} || always()",
        f"always() || {GUARD}",
        f"!({GUARD})",
        GUARD.replace("github.repository", "github.repository_owner"),
        f"({GUARD} || always()) && success()",
    ],
    ids=["or-always", "or-first", "negated-in-parens", "owner", "or-in-parens"],
)
def test_guard_loopholes_are_reported(gate, tmp_path, step_if):
    _write(tmp_path, _sticky_workflow(step_if=step_if))
    assert gate.check(tmp_path) == [NO_GUARD]


@pytest.mark.parametrize(
    "step_if",
    [
        f"{GUARD} && (github.event.action == 'opened' || github.event.action == 'reopened')",
        GUARD.replace(" ", "  "),
        f"({GUARD})",
        "github.event_name == 'push' && always()",
        "always() && github.event_name == 'workflow_dispatch'",
        "github.event_name == 'schedule'",
    ],
    ids=["and-parenthesized-or", "extra-spaces", "parenthesized", "push", "dispatch", "schedule"],
)
def test_guarded_or_non_pr_steps_pass(gate, tmp_path, step_if):
    _write(tmp_path, _sticky_workflow(step_if=step_if))
    assert gate.check(tmp_path) == []


def test_github_script_create_comment_is_reported(gate, tmp_path):
    _write(
        tmp_path,
        """\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Comment
                uses: actions/github-script@v7.1.0
                with:
                  script: |
                    await github.rest.issues.createComment({
                      owner: context.repo.owner, repo: context.repo.repo,
                      issue_number: context.issue.number, body: 'x' });
        """,
    )
    assert gate.check(tmp_path) == [COMMENT_NO_GUARD]


@pytest.mark.parametrize(
    "script",
    [
        "github.rest.issues.addLabels({issue_number: 1, labels: ['x']})",
        "github.rest.issues.removeLabel({issue_number: 1, name: 'x'})",
        "github.rest.pulls.createReviewComment({pull_number: 1})",
        "github.request('POST /repos/{owner}/{repo}/issues/{n}/labels')",
        "github.request('PATCH /repos/{owner}/{repo}/issues/comments/1')",
    ],
    ids=["addLabels", "removeLabel", "createReviewComment", "request-post", "request-patch"],
)
def test_github_script_writes_are_reported(gate, tmp_path, script):
    _write(tmp_path, _script_step(script))
    assert gate.check(tmp_path) == [COMMENT_NO_GUARD]


def test_github_request_get_is_not_a_write(gate, tmp_path):
    _write(tmp_path, _script_step("github.request('GET /repos/{owner}/{repo}/pulls/1')"))
    assert gate.check(tmp_path) == []


@pytest.mark.parametrize(
    "run",
    [
        'gh pr comment "$PR" --body-file report.md',
        "gh pr review 1 --approve",
        "gh issue comment 1 --body x",
        "gh pr edit 1 --add-label x",
        "gh api repos/o/r/issues/1/comments -f body=x",
        "gh api -X POST repos/o/r/pulls/1/reviews",
        "gh api repos/o/r/issues/1/labels -f labels[]=x",
    ],
)
def test_gh_cli_writes_are_reported(gate, tmp_path, run):
    _write(tmp_path, _run_step(run))
    assert gate.check(tmp_path) == [COMMENT_NO_GUARD]


@pytest.mark.parametrize("key", ["comment-on-alert", "comment-always"])
def test_benchmark_action_comment_is_reported(gate, tmp_path, key):
    _write(
        tmp_path,
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Comment
                uses: benchmark-action/github-action-benchmark@v1.20.4
                with:
                  {key}: true
        """,
    )
    assert gate.check(tmp_path) == [COMMENT_NO_GUARD]


def test_benchmark_action_without_comment_passes(gate, tmp_path):
    _write(
        tmp_path,
        """\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Bench
                uses: benchmark-action/github-action-benchmark@v1.20.4
                with:
                  comment-on-alert: false
        """,
    )
    assert gate.check(tmp_path) == []


@pytest.mark.parametrize(
    "on_block",
    [
        "on: pull_request",
        "on: [push, pull_request]",
        "on:\n  pull_request:\n    paths: ['src/**']",
    ],
)
def test_trigger_forms_are_all_detected(gate, tmp_path, on_block):
    _write(tmp_path, _sticky_workflow(on=on_block))
    assert gate.check(tmp_path) == [NO_GUARD]


def test_push_only_workflow_is_ignored(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(on="on: push"))
    assert gate.check(tmp_path) == []


def test_pull_request_target_only_is_ignored(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(on="on: pull_request_target"))
    assert gate.check(tmp_path) == []


def test_null_job_and_non_dict_step_do_not_crash(gate, tmp_path):
    _write(
        tmp_path,
        """\
        on:
          pull_request: null
        jobs:
          a: null
          b:
            runs-on: ubuntu-24.04
            steps: ["x", null]
        """,
    )
    assert gate.check(tmp_path) == []


def test_bool_and_folded_if_are_read(gate, tmp_path):
    _write(
        tmp_path,
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            if: true
            steps:
              - name: Post sticky
                uses: marocchino/sticky-pull-request-comment@v2.9.4
                if: >-
                  github.event_name == 'pull_request' &&
                  {GUARD}
                with:
                  header: report
              - name: Other
                if: false
                run: echo x
        """,
    )
    assert gate.check(tmp_path) == []


def test_sticky_path_without_step_summary_is_reported(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(step_if=GUARD, path="/tmp/report.md"))
    assert gate.check(tmp_path) == [
        "ci.yml / build / Post sticky: /tmp/report.md is not written to $GITHUB_STEP_SUMMARY"
    ]


def test_sticky_path_with_step_summary_passes(gate, tmp_path):
    _write(
        tmp_path,
        _sticky_workflow(step_if=GUARD, path="/tmp/report.md", summary_step=True),
    )
    assert gate.check(tmp_path) == []


def test_summary_on_other_line_is_reported(gate, tmp_path):
    _write(
        tmp_path,
        f"""\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Summary
                run: |
                  echo heading >> "$GITHUB_STEP_SUMMARY"
                  cat /tmp/report.md
              - name: Post sticky
                uses: marocchino/sticky-pull-request-comment@v2.9.4
                if: {GUARD}
                with:
                  header: report
                  path: /tmp/report.md
        """,
    )
    assert gate.check(tmp_path) == [
        "ci.yml / build / Post sticky: /tmp/report.md is not written to $GITHUB_STEP_SUMMARY"
    ]


def test_main_returns_1_and_prints_error(gate, tmp_path, capsys):
    _write(tmp_path, _sticky_workflow())
    assert gate.main(["--root", str(tmp_path)]) == 1
    assert f"ERROR: {NO_GUARD}" in capsys.readouterr().err


def test_real_repository_has_no_violations(gate):
    assert gate.check(REPO_ROOT) == []


def test_reusable_workflow_is_checked(gate, tmp_path):
    # A workflow_call callee runs with its pull_request caller's read-only
    # token, so an unguarded comment there fails a fork PR the same way.
    _write(tmp_path, _sticky_workflow(on="on: workflow_call"))
    assert gate.check(tmp_path) == [NO_GUARD]
