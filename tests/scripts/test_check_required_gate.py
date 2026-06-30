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
