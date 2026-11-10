"""Steps that post to a PR must be skipped on fork PRs.

Regression focus: PR #934 (2026-11, the first fork PR in months) failed
required-gate/all-workflows although every check passed. Five sticky-comment
steps ran with the fork's read-only GITHUB_TOKEN and failed with "Resource
not accessible by integration". A fork PR has to be able to go green; only
the comment is skipped, never the check, and the report the comment would
have carried is written to the job summary instead.
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
NO_GUARD = "ci.yml / build / Post sticky: no fork guard"


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


def test_unguarded_sticky_step_is_reported(gate, tmp_path):
    _write(tmp_path, _sticky_workflow())
    assert gate.check(tmp_path) == [NO_GUARD]


def test_step_level_guard_passes(gate, tmp_path):
    _write(
        tmp_path,
        _sticky_workflow(step_if=f"github.event_name == 'pull_request' && {GUARD}"),
    )
    assert gate.check(tmp_path) == []


def test_job_level_guard_passes(gate, tmp_path):
    job_if = f"if: \"{GUARD} || github.event_name != 'pull_request'\""
    _write(tmp_path, _sticky_workflow(job_extra=job_if))
    assert gate.check(tmp_path) == []


def test_job_continue_on_error_passes(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(job_extra="continue-on-error: true"))
    assert gate.check(tmp_path) == []


def test_guard_inside_expression_wrapper_passes(gate, tmp_path):
    _write(tmp_path, _sticky_workflow(step_if="${{ !cancelled() && " + GUARD + " }}"))
    assert gate.check(tmp_path) == []


def test_negated_guard_is_reported(gate, tmp_path):
    negated = "github.event.pull_request.head.repo.full_name != github.repository"
    _write(tmp_path, _sticky_workflow(step_if=negated))
    assert gate.check(tmp_path) == [NO_GUARD]


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
    assert gate.check(tmp_path) == ["ci.yml / build / Comment: no fork guard"]


def test_gh_pr_comment_in_run_is_reported(gate, tmp_path):
    _write(
        tmp_path,
        """\
        on: pull_request
        jobs:
          build:
            runs-on: ubuntu-24.04
            steps:
              - name: Comment
                run: gh pr comment "$PR" --body-file report.md
        """,
    )
    assert gate.check(tmp_path) == ["ci.yml / build / Comment: no fork guard"]


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
