"""Unit tests for scripts/check_required_gate.py (M1.1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_required_gate.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
HEAD_SHA = "deadbeef0000000000000000000000000000beef"
MONITORED = (
    "Multi-Runtime RTF Benchmark,Memory regression (per-language),"
    "CodeQL,Parity Hub,PUA Consistency Gate"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("check_required_gate", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def _run(gate, fixture_name: str, **extra) -> tuple[int, str]:
    argv = [
        "--head-sha", HEAD_SHA,
        "--monitored", MONITORED,
        "--runs-json", str(FIXTURES / fixture_name),
    ]
    for k, v in extra.items():
        argv.append(f"--{k.replace('_', '-')}")
        argv.append(str(v))
    parser = gate.build_parser()
    args = parser.parse_args(argv)
    rc = gate.run(args)
    return rc, ""


def test_all_success_exits_zero(gate, capsys):
    rc, _ = _run(gate, "gh_runs_all_success.json")
    captured = capsys.readouterr()
    assert rc == 0
    assert "All monitored spokes succeeded" in captured.out


def test_single_cancelled_fails_gate(gate, capsys):
    rc, _ = _run(gate, "gh_runs_cancelled.json")
    captured = capsys.readouterr()
    assert rc == 1
    assert "Multi-Runtime RTF Benchmark" in captured.out
    assert "cancelled" in captured.out


def test_single_skipped_fails_gate(gate, capsys):
    rc, _ = _run(gate, "gh_runs_skipped.json")
    captured = capsys.readouterr()
    assert rc == 1
    assert "CodeQL" in captured.out
    assert "skipped" in captured.out


def test_single_failure_fails_gate(gate, capsys):
    rc, _ = _run(gate, "gh_runs_failure.json")
    captured = capsys.readouterr()
    assert rc == 1
    assert "Memory regression (per-language)" in captured.out
    assert "failure" in captured.out


def test_supersede_returns_zero_with_deferred_message(gate, capsys):
    rc, _ = _run(
        gate,
        "gh_runs_supersede.json",
        latest_sha_for_supersede="cafebabe0000000000000000000000000000babe",
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "deferred" in captured.out.lower()
    assert "cafebab" in captured.out


def test_head_sha_mismatch_is_missing(gate, capsys):
    """Runs whose head_sha differs from the requested SHA must not satisfy
    the spoke — even if the workflow name matches."""
    rc, _ = _run(gate, "gh_runs_head_sha_mismatch.json")
    captured = capsys.readouterr()
    assert rc == 1
    # Multi-Runtime RTF Benchmark exists in fixture but at the wrong head_sha,
    # so it must be reported as missing rather than as a success.
    assert "Multi-Runtime RTF Benchmark" in captured.out
    assert "Missing spokes" in captured.out


def test_on_cancelled_ignore_lets_cancelled_pass(gate, capsys):
    rc, _ = _run(gate, "gh_runs_cancelled.json", on_cancelled="ignore")
    captured = capsys.readouterr()
    assert rc == 0
    assert "All monitored spokes succeeded" in captured.out


def test_on_skipped_ignore_lets_skipped_pass(gate, capsys):
    rc, _ = _run(gate, "gh_runs_skipped.json", on_skipped="ignore")
    captured = capsys.readouterr()
    assert rc == 0


def test_diagnostic_contains_sticky_marker(gate, capsys):
    _run(gate, "gh_runs_cancelled.json")
    captured = capsys.readouterr()
    assert gate.STICKY_MARKER in captured.out


def test_neutral_conclusion_treated_as_success(gate, tmp_path):
    """The first-PR fast lane (M1.3) downgrades contract gates to ``neutral``;
    the gateway must not flag those as fail-open."""
    payload = {
        "workflow_runs": [
            {
                "id": 7001, "name": "Parity Hub", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "neutral", "run_number": 1,
                "html_url": "https://example/7001",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(payload))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA,
        "--monitored", "Parity Hub",
        "--runs-json", str(runs_file),
    ])
    rc = gate.run(args)
    assert rc == 0


def test_picks_most_recent_run_per_workflow(gate, tmp_path):
    payload = {
        "workflow_runs": [
            {
                "id": 1, "name": "Parity Hub", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "cancelled", "run_number": 1,
                "html_url": "https://example/1",
            },
            {
                "id": 2, "name": "Parity Hub", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "success", "run_number": 2,
                "html_url": "https://example/2",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(payload))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA,
        "--monitored", "Parity Hub",
        "--runs-json", str(runs_file),
    ])
    rc = gate.run(args)
    assert rc == 0


def test_paths_filtered_missing_is_exempt(gate, tmp_path, capsys):
    """A workflow listed in --paths-filtered that didn't queue (missing) must
    exit 0 and be rendered in the 'Paths-filtered spokes' informational
    section, not as a Missing-spokes failure."""
    payload = {
        "workflow_runs": [
            {
                "id": 1, "name": "Parity Hub", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "success", "run_number": 1,
                "html_url": "https://example/1",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(payload))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA,
        "--monitored", "Parity Hub,PUA Consistency Gate",
        "--paths-filtered", "PUA Consistency Gate",
        "--runs-json", str(runs_file),
    ])
    rc = gate.run(args)
    captured = capsys.readouterr()
    assert rc == 0
    assert "Paths-filtered spokes" in captured.out
    assert "PUA Consistency Gate" in captured.out
    assert "Missing spokes" not in captured.out
    # The unqualified "All monitored spokes succeeded." line would contradict
    # the Paths-filtered section above (Copilot review on PR #587). Use the
    # qualified phrasing instead.
    assert "All monitored spokes succeeded." not in captured.out
    assert "All eligible spokes succeeded" in captured.out


def test_paths_filtered_workflow_still_fails_when_run_cancelled(gate, tmp_path, capsys):
    """The paths-filter exemption only covers the missing-from-runs case. If
    the workflow DID queue and was cancelled, the gate must still fail."""
    payload = {
        "workflow_runs": [
            {
                "id": 1, "name": "PUA Consistency Gate", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "cancelled", "run_number": 1,
                "html_url": "https://example/1",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(payload))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA,
        "--monitored", "PUA Consistency Gate",
        "--paths-filtered", "PUA Consistency Gate",
        "--runs-json", str(runs_file),
    ])
    rc = gate.run(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "PUA Consistency Gate" in captured.out
    assert "cancelled" in captured.out


def test_unfiltered_missing_workflow_still_fails(gate, tmp_path, capsys):
    """Regression guard: a missing workflow NOT named in --paths-filtered
    must still fail the gate (the historical behavior)."""
    payload = {
        "workflow_runs": [
            {
                "id": 1, "name": "Parity Hub", "head_sha": HEAD_SHA,
                "status": "completed", "conclusion": "success", "run_number": 1,
                "html_url": "https://example/1",
            },
        ]
    }
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps(payload))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA,
        "--monitored", "Parity Hub,CodeQL",
        "--paths-filtered", "PUA Consistency Gate",
        "--runs-json", str(runs_file),
    ])
    rc = gate.run(args)
    captured = capsys.readouterr()
    assert rc == 1
    assert "Missing spokes" in captured.out
    assert "CodeQL" in captured.out


# ---------------------------------------------------------------------------
# Spoke still running == deferred, not failed.
#
# The gate is triggered by `workflow_run: completed` on each monitored spoke,
# so every firing but the last one observes a spoke that has not finished.
# Failing on that made 38 of the 60 runs preceding this fix red while the
# final (authoritative) firing was green — noise that hides real failures.
# ---------------------------------------------------------------------------


def test_pending_spoke_defers_instead_of_failing(gate, capsys):
    rc, _ = _run(gate, "gh_runs_pending.json")
    captured = capsys.readouterr()
    assert rc == 0
    assert "deferred — spokes still running" in captured.out
    assert "Spokes still running" in captured.out
    assert "Multi-Runtime RTF Benchmark" in captured.out
    # The unqualified success line must not appear — not every spoke is done.
    assert "All monitored spokes succeeded" not in captured.out


def test_pending_does_not_mask_a_real_failure(gate, capsys):
    rc, _ = _run(gate, "gh_runs_pending_with_failure.json")
    captured = capsys.readouterr()
    assert rc == 1
    assert "deferred" not in captured.out
    assert "Non-success spokes" in captured.out
    assert "CodeQL" in captured.out
    # The still-running spoke is still reported, just not as a failure.
    assert "Spokes still running" in captured.out


def test_classify_returns_pending_separately(gate):
    runs = json.loads((FIXTURES / "gh_runs_pending.json").read_text())["workflow_runs"]
    monitored = gate.parse_monitored(MONITORED)
    spokes, _missing = gate.pick_latest_per_workflow(runs, monitored, HEAD_SHA)
    bad, pending = gate.classify(spokes, on_cancelled="fail", on_skipped="fail")
    assert bad == []
    assert [name for name, _ in pending] == ["Multi-Runtime RTF Benchmark"]


# ---------------------------------------------------------------------------
# --all-workflows: wait for EVERY workflow run at head_sha and report the
# verdict as a commit status.
#
# The spoke list above covered 5 of the ~90 workflows a PR can trigger, and the
# authoritative (workflow_run) verdict never reached the PR: workflow_run runs
# are recorded against dev, so the final evaluation was only a sticky comment
# while the PR's own check was a pull_request firing that always deferred.
# These tests pin the replacement: every run for the PR head counts, and the
# verdict is a commit status on that head, which a ruleset can require.
# ---------------------------------------------------------------------------

GATE_NAME = "Required Status Check Gate"


def _r(run_id, name, *, status="completed", conclusion="success", event="pull_request",
       sha=HEAD_SHA, run_number=1):
    return {
        "id": run_id, "name": name, "head_sha": sha, "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "event": event, "run_number": run_number,
        "html_url": f"https://example/{run_id}",
    }


def _all_mode(gate, tmp_path, runs, *extra):
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps({"workflow_runs": runs}))
    argv = [
        "--head-sha", HEAD_SHA,
        "--all-workflows",
        "--event", "pull_request",
        "--exclude", GATE_NAME,
        "--require-present", "CI",
        "--runs-json", str(runs_file),
        *extra,
    ]
    args = gate.build_parser().parse_args(argv)
    return gate.evaluate(args)


def test_all_workflows_success_when_every_run_succeeded(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"), _r(2, "Go CI"), _r(3, "PR Title Check"),
    ])
    assert verdict.state == "success"
    assert verdict.exit_code == 0
    assert "3" in verdict.description


def test_all_workflows_failure_names_the_failed_workflow(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"), _r(2, "Go CI", conclusion="failure"), _r(3, "Kotlin G2P CI"),
    ])
    assert verdict.state == "failure"
    assert verdict.exit_code == 1
    assert "Go CI" in verdict.description


def test_all_workflows_failure_is_reported_while_others_still_run(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI", status="in_progress"), _r(2, "Go CI", conclusion="timed_out"),
    ])
    assert verdict.state == "failure"


def test_all_workflows_pending_while_any_run_is_unfinished(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"), _r(2, "Build All Platforms", status="queued"),
    ])
    assert verdict.state == "pending"
    assert verdict.exit_code == 0
    assert "Build All Platforms" in verdict.body


def test_all_workflows_cancelled_run_fails(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [_r(1, "CI"), _r(2, "Go CI", conclusion="cancelled")])
    assert verdict.state == "failure"


def test_all_workflows_skipped_and_neutral_runs_pass(gate, tmp_path):
    """A run whose jobs were all skipped by `if:` is intentional, and
    `neutral` is the first-PR fast lane's downgrade."""
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"), _r(2, "Release Kotlin G2P (Maven Central)", conclusion="skipped"),
        _r(3, "Parity Hub", conclusion="neutral"),
    ])
    assert verdict.state == "success"


def test_all_workflows_startup_failure_fails(gate, tmp_path):
    """An invalid workflow file still creates a run, concluded startup_failure."""
    verdict = _all_mode(gate, tmp_path, [_r(1, "CI"), _r(2, "Go CI", conclusion="startup_failure")])
    assert verdict.state == "failure"


def test_all_workflows_ignores_the_gate_itself_and_other_events(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"),
        _r(2, GATE_NAME, status="in_progress"),
        _r(3, "CodeQL", conclusion="failure", event="schedule"),
        _r(4, "Go CI", conclusion="failure", sha="0" * 40),
    ])
    assert verdict.state == "success"


def test_all_workflows_uses_the_latest_attempt_per_workflow(gate, tmp_path):
    verdict = _all_mode(gate, tmp_path, [
        _r(1, "CI"),
        _r(2, "Go CI", conclusion="failure", run_number=7),
        _r(3, "Go CI", conclusion="success", run_number=8),
    ])
    assert verdict.state == "success"


def test_all_workflows_stays_pending_until_the_anchor_run_exists(gate, tmp_path):
    """Runs are created a moment after the push. A firing that sees only the
    fast workflows must not call the head green before CI's run exists."""
    verdict = _all_mode(gate, tmp_path, [_r(2, "PR Title Check")])
    assert verdict.state == "pending"
    assert "CI" in verdict.body


def test_all_workflows_does_not_require_monitored(gate):
    args = gate.build_parser().parse_args(["--head-sha", HEAD_SHA, "--all-workflows"])
    assert args.all_workflows is True


def test_fetch_runs_for_sha_follows_every_page(gate, monkeypatch):
    pages = {
        "1": {"total_count": 150, "workflow_runs": [{"id": i} for i in range(100)]},
        "2": {"total_count": 150, "workflow_runs": [{"id": i} for i in range(100, 150)]},
    }
    seen = []

    def fake_get(path, token, **_):
        page = path.split("page=")[-1].split("&")[0]
        seen.append(page)
        return pages[page]

    monkeypatch.setattr(gate, "gh_get", fake_get)
    runs = gate.fetch_runs_for_sha("o/r", HEAD_SHA, "t")
    assert len(runs) == 150
    assert seen == ["1", "2"]


def test_status_payload_carries_state_context_and_target(gate, tmp_path, monkeypatch):
    posted = {}

    def fake_post(repo, sha, payload, token):
        posted.update(repo=repo, sha=sha, **payload)

    monkeypatch.setattr(gate, "post_commit_status", fake_post)
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    runs_file = tmp_path / "runs.json"
    runs_file.write_text(json.dumps({"workflow_runs": [_r(1, "CI", conclusion="failure")]}))
    args = gate.build_parser().parse_args([
        "--head-sha", HEAD_SHA, "--repo", "o/r", "--all-workflows",
        "--require-present", "CI", "--runs-json", str(runs_file),
        "--status-context", "all-workflows", "--target-url", "https://example/run",
    ])
    rc = gate.run(args)
    assert rc == 1
    assert posted["sha"] == HEAD_SHA
    assert posted["state"] == "failure"
    assert posted["context"] == "all-workflows"
    assert posted["target_url"] == "https://example/run"
    assert len(posted["description"]) <= 140
