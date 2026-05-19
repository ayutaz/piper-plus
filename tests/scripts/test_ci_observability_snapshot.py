"""Unit tests for scripts/ci_observability_snapshot.py.

`docs/proposals/ci-expansion-2026-05.md` §3.9 #1 由来の CI observability
data layer のテスト。 gh CLI に依存せず ``--input`` 経路で fixture JSON を
食わせて集計ロジックを検証する。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "ci_observability_snapshot.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ci_observability_snapshot", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_filter_window_drops_old_runs(mod):
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    runs = [
        {"createdAt": _iso(now - timedelta(days=2)), "workflowName": "A", "conclusion": "success"},
        {"createdAt": _iso(now - timedelta(days=8)), "workflowName": "A", "conclusion": "success"},
        {"createdAt": _iso(now - timedelta(hours=1)), "workflowName": "A", "conclusion": "failure"},
    ]
    out = mod.filter_window(runs, days=7, now=now)
    assert len(out) == 2


def test_aggregate_basic(mod):
    runs = [
        {"workflowName": "A", "conclusion": "success", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
        {"workflowName": "A", "conclusion": "failure", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
        {"workflowName": "A", "conclusion": "cancelled", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
        {"workflowName": "B", "conclusion": "success", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
    ]
    stats = mod.aggregate(runs)
    assert stats["A"]["total"] == 3
    assert stats["A"]["success"] == 1
    assert stats["A"]["failure"] == 1
    assert stats["A"]["cancelled"] == 1
    assert pytest.approx(stats["A"]["cancellation_rate"], abs=1e-9) == 1 / 3
    assert pytest.approx(stats["A"]["failure_rate"], abs=1e-9) == 1 / 3
    assert pytest.approx(stats["A"]["success_rate"], abs=1e-9) == 1 / 3
    assert stats["B"]["total"] == 1
    assert stats["B"]["success_rate"] == 1.0


def test_aggregate_in_progress_handled(mod):
    runs = [
        {"workflowName": "A", "conclusion": None, "status": "in_progress", "createdAt": "2026-05-18T00:00:00Z"},
        {"workflowName": "A", "conclusion": "success", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
    ]
    stats = mod.aggregate(runs)
    assert stats["A"]["in_progress"] == 1
    assert stats["A"]["total"] == 2


def test_aggregate_skipped_bucketed(mod):
    runs = [
        {"workflowName": "A", "conclusion": "skipped", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
        {"workflowName": "A", "conclusion": "success", "status": "completed", "createdAt": "2026-05-18T00:00:00Z"},
    ]
    stats = mod.aggregate(runs)
    assert stats["A"]["skipped"] == 1
    assert stats["A"]["success"] == 1


def test_flake_candidates_threshold(mod):
    stats = {
        "A": {"total": 10, "cancelled": 3, "cancellation_rate": 0.3},
        "B": {"total": 10, "cancelled": 1, "cancellation_rate": 0.1},
        "C": {"total": 100, "cancelled": 15, "cancellation_rate": 0.15},
        "D": {"total": 3, "cancelled": 3, "cancellation_rate": 1.0},  # below min_runs
    }
    out = mod.flake_candidates(stats, cancel_threshold=0.10, min_runs=5)
    # B is exactly at threshold (not strictly >); D is below min_runs
    assert any(s.startswith("A:") for s in out)
    assert any(s.startswith("C:") for s in out)
    assert not any(s.startswith("B:") for s in out)
    assert not any(s.startswith("D:") for s in out)


def test_main_writes_snapshot(mod, tmp_path: Path, monkeypatch):
    fixture = tmp_path / "runs.json"
    now = datetime.now(tz=timezone.utc)
    fixture.write_text(
        json.dumps(
            [
                {"workflowName": "A", "conclusion": "success", "status": "completed", "createdAt": _iso(now)},
                {"workflowName": "A", "conclusion": "cancelled", "status": "completed", "createdAt": _iso(now)},
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ci_observability_snapshot",
            "--input",
            str(fixture),
            "--output",
            str(output),
            "--min-runs",
            "1",
            "--cancel-threshold",
            "0.4",
        ],
    )
    rc = mod.main()
    assert rc == 0
    snap = json.loads(output.read_text(encoding="utf-8"))
    assert snap["total_runs_in_window"] == 2
    assert "A" in snap["workflows"]
    assert snap["workflows"]["A"]["cancelled"] == 1
    # cancellation_rate == 0.5 > threshold 0.4
    assert any("A:" in s for s in snap["flake_candidates"])
