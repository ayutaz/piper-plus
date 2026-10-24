"""Contract tests for .github/workflows/required_status_check_gate.yml.

``check_required_gate.py`` is covered by tests/scripts/test_check_required_gate.py,
but every defect found in the gate so far lived in the WORKFLOW that invokes
it -- the script did exactly what it was told with the wrong arguments:

  * ``--branch-for-supersede`` was given the PR's base ref, so every
    ``pull_request`` firing deferred and exited 0 (4 of 4 measured runs).
  * ``--paths-filtered`` named 2 of the 4 path-filtered spokes, so the gate
    reported the other 2 as missing and failed.
  * The verdict that did evaluate everything came from ``workflow_run``
    firings, which are recorded against dev and so never appeared on the PR;
    it only reached a PR comment, and no ruleset required it.

The gate now waits for every pull_request workflow and publishes a commit
status on the PR head. The invariants below are derived from the workflow
files rather than restated by hand.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
GATE_WORKFLOW = WORKFLOW_DIR / "required_status_check_gate.yml"
GATE_NAME = "Required Status Check Gate"
STATUS_CONTEXT = "required-gate/all-workflows"
ANCHOR = "CI"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _triggers(doc: dict) -> dict:
    """``on:`` parses as the boolean True under YAML 1.1, so accept both."""
    on = doc.get(True, doc.get("on"))
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {key: None for key in on}
    return on if isinstance(on, dict) else {}


@pytest.fixture(scope="module")
def gate_doc() -> dict:
    return _load(GATE_WORKFLOW)


@pytest.fixture(scope="module")
def gate_text() -> str:
    return GATE_WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflows() -> dict[str, dict]:
    by_name: dict[str, dict] = {}
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        doc = _load(path)
        name = doc.get("name")
        assert isinstance(name, str), f"{path.name} has no name"
        assert name not in by_name, f"duplicate workflow name {name!r}"
        by_name[name] = doc
    return by_name


# ``workflow_run.workflows`` entries are filter patterns, not names: GitHub
# treats these characters as pattern syntax unless each is escaped with ``\``.
# An unescaped ``C++ Tests`` made GitHub reject the whole trigger, and every
# firing of the gate ended in startup_failure without running a job.
FILTER_SPECIALS = frozenset("*?+[]!")


def _literal_name(pattern: str) -> str | None:
    """The workflow name ``pattern`` matches exactly, or None if it is a glob."""
    name = []
    chars = iter(pattern)
    for char in chars:
        if char == "\\":
            escaped = next(chars, None)
            if escaped is None:
                return None
            name.append(escaped)
        elif char in FILTER_SPECIALS:
            return None
        else:
            name.append(char)
    return "".join(name)


@pytest.fixture(scope="module")
def listed_patterns(gate_doc: dict) -> list[str]:
    return list(_triggers(gate_doc)["workflow_run"]["workflows"])


@pytest.fixture(scope="module")
def listed(listed_patterns: list[str]) -> list[str]:
    return [_literal_name(pattern) for pattern in listed_patterns]


@pytest.mark.parametrize(
    ("pattern", "name"),
    [
        ("CI", "CI"),
        ("C\\+\\+ Tests", "C++ Tests"),
        ("Co-install Smoke (piper-tts \\+ piper-plus)", "Co-install Smoke (piper-tts + piper-plus)"),
        ("C++ Tests", None),
        ("Build*", None),
        ("!CI", None),
        ("trailing\\", None),
    ],
)
def test_literal_name(pattern, name):
    assert _literal_name(pattern) == name


def test_listed_entries_match_one_name_literally(listed_patterns):
    """Escape every special character, e.g. ``'C\\+\\+ Tests'`` for ``C++ Tests``."""
    globs = [pattern for pattern in listed_patterns if _literal_name(pattern) is None]
    assert not globs


def test_workflow_names_are_not_cut_by_a_yaml_comment():
    """An unquoted ``name: E2E Issue #426`` is the name ``E2E Issue``: YAML
    reads `` #`` onwards as a comment, and GitHub shows the cut name."""
    cut = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("name:"):
                value = line[len("name:") :].strip()
                if value[:1] not in ("'", '"') and " #" in value:
                    cut.append(f"{path.name}: {line}")
                break
    assert not cut


def test_gate_waits_for_every_pull_request_workflow(listed, workflows):
    """The final firing comes from the last workflow to complete.

    A pull_request workflow missing from this list can finish last without
    firing the gate, leaving the status pending (merge blocked) or, worse, a
    stale success from an earlier firing. Add new workflows here.
    """
    expected = {
        name
        for name, doc in workflows.items()
        if "pull_request" in _triggers(doc) and name != GATE_NAME
    }
    assert set(listed) == expected, {
        "not listed": sorted(expected - set(listed)),
        "listed but not a pull_request workflow": sorted(set(listed) - expected),
    }


def test_listed_workflows_are_not_themselves_workflow_run_chains(listed, workflows):
    """``workflow_run`` cannot chain more than three levels."""
    chained = [name for name in listed if "workflow_run" in _triggers(workflows[name])]
    assert not chained


def test_gate_runs_only_from_workflow_run(gate_doc):
    """A ``pull_request`` firing evaluates before anything finished, and its
    check run would be a second, always-deferred verdict on the PR."""
    assert set(_triggers(gate_doc)) == {"workflow_run"}
    assert _triggers(gate_doc)["workflow_run"]["types"] == ["completed"]


def test_gate_job_is_limited_to_pull_request_heads(gate_doc):
    job = gate_doc["jobs"]["gate"]
    assert job["if"] == (
        "github.event.workflow_run.event == 'pull_request'"
        " && github.event.workflow_run.conclusion != 'cancelled'"
    )


def test_a_skipped_firing_cannot_publish_success(gate_doc):
    """Skipping cancelled completions is safe only because nothing else
    publishes the status: the last published verdict saw that run unfinished
    (pending), or saw it cancelled (failure)."""
    steps = gate_doc["jobs"]["gate"]["steps"]
    assert sum("check_required_gate.py" in step.get("run", "") for step in steps) == 1


def test_gate_can_publish_a_commit_status(gate_doc):
    assert gate_doc["permissions"].get("statuses") == "write"
    assert gate_doc["permissions"].get("actions") == "read"
    assert "pull-requests" not in gate_doc["permissions"]


def test_firings_for_one_head_never_cancel_a_running_evaluation(gate_doc):
    concurrency = gate_doc["concurrency"]
    assert "github.event.workflow_run.head_sha" in concurrency["group"]
    assert concurrency["cancel-in-progress"] is False


def test_gate_is_invoked_in_all_workflows_mode(gate_text):
    for flag in (
        "--all-workflows",
        "--event pull_request",
        f'--exclude "{GATE_NAME}"',
        f"--require-present {ANCHOR}",
        "--on-cancelled fail",
        f'--status-context "{STATUS_CONTEXT}"',
        '--head-sha "${HEAD_SHA}"',
        "HEAD_SHA: ${{ github.event.workflow_run.head_sha }}",
    ):
        assert flag in gate_text, flag
    assert "--monitored" not in gate_text
    assert "--branch-for-supersede" not in gate_text


def test_excluded_name_is_the_gate_itself(gate_doc):
    """Excluding any other name would drop a real workflow from the verdict."""
    assert gate_doc["name"] == GATE_NAME


def test_anchor_runs_on_every_pull_request(workflows):
    """``--require-present CI`` holds the verdict at pending until CI's run
    exists. If CI could be absent from a PR, that PR would never go green."""
    pull_request = _triggers(workflows[ANCHOR])["pull_request"] or {}
    assert not pull_request.get("paths")
    assert not pull_request.get("paths-ignore")
    assert pull_request.get("branches") in (None, ["dev"])
