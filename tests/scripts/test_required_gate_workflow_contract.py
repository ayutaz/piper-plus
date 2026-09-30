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
def declared_paths_filtered(gate_text: str) -> list[str]:
    match = re.search(r'--paths-filtered "([^"]*)"', gate_text)
    assert match, "--paths-filtered not found in the gate workflow"
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


def test_paths_filtered_declares_exactly_the_filtered_spokes(
    monitored, declared_paths_filtered, workflow_by_name
):
    """--paths-filtered must equal the monitored spokes that really are filtered.

    Under-declaring fails the gate on any PR whose diff misses that spoke's
    paths (the original symptom). Over-declaring exempts a spoke that should
    always run, which silently removes it from the gate.
    """
    actually_filtered = {
        name
        for name in monitored
        if _has_pull_request_paths_filter(workflow_by_name[name])
    }
    assert set(declared_paths_filtered) == actually_filtered


def test_a_monitored_spoke_without_a_paths_filter_stays_undeclared(
    monitored, declared_paths_filtered, workflow_by_name
):
    """Anti-vacuity: the equality above must not be "declare everything".

    At least one monitored spoke runs on every PR (no paths filter), and a
    missing run for it is a real gate failure, so it must be absent from
    --paths-filtered. Without this, widening the list to all five would still
    satisfy the test above.
    """
    unfiltered = [
        name
        for name in monitored
        if not _has_pull_request_paths_filter(workflow_by_name[name])
    ]
    assert unfiltered, "expected at least one monitored spoke with no paths filter"
    for name in unfiltered:
        assert name not in declared_paths_filtered, name


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
