"""Contract tests for .github/workflows/required_status_check_gate.yml.

``check_required_gate.py`` is well covered by tests/scripts/test_check_required_gate.py,
but every defect found here lived in the WORKFLOW that invokes it -- the script
did exactly what it was told with the wrong arguments:

  * ``--branch-for-supersede`` was given the PR's BASE ref. The script defers
    when ``head_sha`` is not that branch's tip, and a PR head is never the tip
    of its own base, so the gate exited 0 on every ``pull_request`` firing
    without aggregating a single spoke. Measured: 4 of 4 ``pull_request`` runs
    printed "Head SHA <pr-head> is no longer the branch tip (latest: <dev
    tip>)". The hub whose purpose is closing a fail-open path was itself
    fail-open on the event a PR's check list consults.
  * ``--paths-filtered`` named 2 of the 4 monitored spokes that actually carry
    a ``pull_request: paths:`` filter, so the ``workflow_run`` firing (the one
    that did evaluate) reported ``Multi-Runtime RTF Benchmark`` and
    ``Parity Hub`` as missing and failed.

Both are invariants that can be derived from the workflow files rather than
restated by hand, which is what these tests do.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
GATE_WORKFLOW = WORKFLOW_DIR / "required_status_check_gate.yml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _triggers(doc: dict) -> dict:
    """``on:`` parses as the boolean True under YAML 1.1, so accept both."""
    on = doc.get(True, doc.get("on"))
    return on if isinstance(on, dict) else {}


def _comma_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


@pytest.fixture(scope="module")
def gate_text() -> str:
    return GATE_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def monitored(gate_text: str) -> list[str]:
    match = re.search(r"MONITORED_WORKFLOWS:\s*>-\s*\n\s*(.+)", gate_text)
    assert match, "MONITORED_WORKFLOWS not found in the gate workflow"
    return _comma_list(match.group(1))


@pytest.fixture(scope="module")
def declared_pr_filtered(gate_text: str) -> list[str]:
    match = re.search(r'PR_FILTERED="([^"]*)"', gate_text)
    assert match, "PR_FILTERED not found in the gate workflow"
    return _comma_list(match.group(1))


@pytest.fixture(scope="module")
def declared_push_filtered(gate_text: str) -> list[str]:
    match = re.search(r'PUSH_FILTERED="([^"]*)"', gate_text)
    assert match, "PUSH_FILTERED not found in the gate workflow"
    return _comma_list(match.group(1))


@pytest.fixture(scope="module")
def workflow_by_name() -> dict[str, Path]:
    by_name: dict[str, Path] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        name = _load(path).get("name")
        if isinstance(name, str):
            by_name.setdefault(name, path)
    return by_name


def _has_pull_request_paths_filter(path: Path) -> bool:
    pull_request = _triggers(_load(path)).get("pull_request")
    return isinstance(pull_request, dict) and bool(pull_request.get("paths"))


def _may_be_absent_on_push_to_dev(path: Path) -> bool:
    """Can this workflow legitimately not run on a push to ``dev``?

    Yes if it has no ``push`` trigger, if ``dev`` is outside its push
    branches, or if its push trigger carries a paths filter. Otherwise a push
    to dev MUST produce a run, so the hub must not exempt it there.
    """
    push = _triggers(_load(path)).get("push")
    if push is None:
        return True
    if not isinstance(push, dict):
        return False
    if push.get("paths"):
        return True
    branches = push.get("branches")
    if isinstance(branches, list) and "dev" not in branches:
        return True
    return False


def test_every_monitored_spoke_resolves_to_a_workflow(monitored, workflow_by_name):
    """A renamed spoke must not vanish from the hub silently.

    MONITORED_WORKFLOWS holds display names, matched against the REST API's
    ``name`` field. If a spoke is renamed and this list is not updated, the
    hub reports it missing forever -- or, once it is also in --paths-filtered,
    exempts it forever and checks nothing.
    """
    assert monitored, "MONITORED_WORKFLOWS is empty"
    unresolved = [name for name in monitored if name not in workflow_by_name]
    assert not unresolved, f"monitored spokes with no matching workflow: {unresolved}"


def test_pr_list_declares_exactly_the_pull_request_filtered_spokes(
    monitored, declared_pr_filtered, workflow_by_name
):
    """PR_FILTERED must equal the monitored spokes filtered on pull_request.

    Under-declaring fails the gate on any PR whose diff misses that spoke's
    paths (the original symptom). Over-declaring exempts a spoke that should
    always run, which silently removes it from the gate.
    """
    actually_filtered = {
        name
        for name in monitored
        if _has_pull_request_paths_filter(workflow_by_name[name])
    }
    assert set(declared_pr_filtered) == actually_filtered


def test_push_list_declares_exactly_the_spokes_that_may_skip_a_dev_push(
    monitored, declared_push_filtered, workflow_by_name
):
    """PUSH_FILTERED must be derived from the PUSH triggers, not the PR ones.

    Two monitored spokes (Multi-Runtime RTF Benchmark, Parity Hub) are
    path-filtered on pull_request but have NO paths filter on push, so a push
    to dev must produce a run for them. Reusing the pull_request list on the
    push path would exempt them exactly where they are mandatory.
    """
    may_be_absent = {
        name
        for name in monitored
        if _may_be_absent_on_push_to_dev(workflow_by_name[name])
    }
    assert set(declared_push_filtered) == may_be_absent


def test_the_two_lists_actually_differ(declared_pr_filtered, declared_push_filtered):
    """Anti-vacuity for the pair above: one list must not stand in for both.

    If they were equal, both tests would still pass while the event-awareness
    this fix adds had been collapsed back to a single hardcoded list.
    """
    assert set(declared_pr_filtered) != set(declared_push_filtered)
    assert set(declared_push_filtered) < set(declared_pr_filtered)


def test_a_monitored_spoke_without_a_paths_filter_stays_undeclared(
    monitored, declared_pr_filtered, declared_push_filtered, workflow_by_name
):
    """Anti-vacuity: the equalities above must not be "declare everything".

    At least one monitored spoke runs on every PR and every push (no paths
    filter either way), and a missing run for it is a real gate failure, so it
    must be absent from BOTH lists. Without this, widening a list to all five
    would still satisfy the equality tests.
    """
    unfiltered = [
        name
        for name in monitored
        if not _has_pull_request_paths_filter(workflow_by_name[name])
        and not _may_be_absent_on_push_to_dev(workflow_by_name[name])
    ]
    assert unfiltered, "expected at least one spoke mandatory on both events"
    for name in unfiltered:
        assert name not in declared_pr_filtered, name
        assert name not in declared_push_filtered, name


def test_run_step_uses_the_resolved_list_not_a_hardcoded_one(gate_text):
    """The gate must be invoked with the ctx step's output.

    Re-hardcoding a literal here would reintroduce a single event-blind list
    while both declaration tests above kept passing.
    """
    assert '--paths-filtered "${PATHS_FILTERED}"' in gate_text
    assert "PATHS_FILTERED: ${{ steps.ctx.outputs.paths_filtered }}" in gate_text


def test_pull_request_firing_passes_no_supersede_branch(gate_text):
    """The PR branch of the ctx step must emit an EMPTY base_branch.

    A non-empty value becomes --branch-for-supersede, and comparing the PR
    head against any branch tip makes the gate defer instead of evaluating.
    """
    pr_branch = re.search(
        r'if \[ "\$\{EVENT_NAME\}" = "pull_request" \]; then\n(.*?)\n\s*else',
        gate_text,
        re.S,
    )
    assert pr_branch, "could not locate the pull_request branch of the ctx step"
    body = pr_branch.group(1)
    assert re.search(r'echo "base_branch="\s*>>', body), body
    assert "PR_BASE_REF" not in gate_text


def test_workflow_run_firing_still_passes_its_head_branch(gate_text):
    """Non-regression: the workflow_run path keeps the supersede guard.

    That path is why the guard exists -- a spoke completing late fires the hub
    on a SHA that is no longer the branch tip.
    """
    else_branch = gate_text.split('= "pull_request" ]; then', 1)[1].split("else", 1)[1]
    assert 'echo "base_branch=${RUN_HEAD_BRANCH}"' in else_branch


def test_workflow_run_firing_dispatches_on_the_original_event(gate_text):
    """A workflow_run firing must pick its list from the ORIGINAL event.

    ``workflow_run`` fires whenever a monitored spoke completes -- including
    spokes that ran for a feature-branch pull_request. Those spokes ARE
    path-filtered, so collapsing the workflow_run path to the push list makes
    the hub demand runs that a PR's diff never triggers. The original event is
    carried in ``github.event.workflow_run.event``, so the branch must test
    RUN_EVENT and select PR_FILTERED for pull_request.

    Pinned because a mutation that replaced this condition with a constant was
    NOT caught by the declaration tests: both lists stayed correct while only
    the dispatch between them was broken.
    """
    assert "RUN_EVENT: ${{ github.event.workflow_run.event }}" in gate_text
    else_branch = gate_text.split('= "pull_request" ]; then', 1)[1].split("else", 1)[1]
    dispatch = re.search(
        r'if \[ "\$\{RUN_EVENT\}" = "pull_request" \]; then\s*\n'
        r'\s*echo "paths_filtered=\$\{PR_FILTERED\}".*?\n'
        r"\s*else\s*\n"
        r'\s*echo "paths_filtered=\$\{PUSH_FILTERED\}"',
        else_branch,
        re.S,
    )
    assert dispatch, else_branch
