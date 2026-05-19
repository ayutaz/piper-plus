"""Unit tests for scripts/check_timing_monotonicity.py (M4.2)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_timing_monotonicity.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_timing_monotonicity", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ctm():
    return _load()


def test_empty_events_pass(ctm):
    result = ctm.check_invariants([], audio_duration_ms=0.0)
    assert result.passed


def test_monotonic_sequence_passes(ctm):
    e = [
        ctm.TimingEvent("a", 0, 50),
        ctm.TimingEvent("b", 50, 120),
        ctm.TimingEvent("c", 120, 200),
    ]
    assert ctm.check_invariants(e, 220.0).passed


def test_overlap_violation(ctm):
    e = [
        ctm.TimingEvent("a", 0, 100),
        ctm.TimingEvent("b", 50, 120),  # starts before prev.end
    ]
    result = ctm.check_invariants(e)
    assert not result.passed
    assert any("starts" in v for v in result.violations)


def test_end_before_start_violation(ctm):
    e = [ctm.TimingEvent("a", 50, 0)]
    result = ctm.check_invariants(e)
    assert not result.passed
    assert any("end" in v and "start" in v for v in result.violations)


def test_event_after_audio_duration_violation(ctm):
    e = [
        ctm.TimingEvent("a", 0, 100),
        ctm.TimingEvent("b", 100, 1000),  # well past audio duration
    ]
    result = ctm.check_invariants(e, audio_duration_ms=500)
    assert not result.passed


def test_random_monotonic_sequences_always_pass(ctm):
    import random
    rng = random.Random(0)
    for _ in range(200):
        events, audio = ctm.random_monotonic_events(rng)
        result = ctm.check_invariants(events, audio)
        assert result.passed, result.violations


def test_cli_check_pass(ctm, tmp_path):
    inp = tmp_path / "events.json"
    inp.write_text(json.dumps({
        "audio_duration_ms": 220,
        "events": [
            {"phoneme": "a", "start_ms": 0, "end_ms": 50},
            {"phoneme": "b", "start_ms": 50, "end_ms": 120},
        ],
    }))
    args = ctm.build_parser().parse_args(["check", "--input", str(inp)])
    rc = args.func(args)
    assert rc == 0


def test_cli_check_fail(ctm, tmp_path):
    inp = tmp_path / "bad.json"
    inp.write_text(json.dumps({
        "events": [
            {"phoneme": "a", "start_ms": 50, "end_ms": 30},
        ],
    }))
    args = ctm.build_parser().parse_args(["check", "--input", str(inp)])
    rc = args.func(args)
    assert rc == 1


def test_cli_fuzz(ctm, tmp_path):
    out = tmp_path / "fuzz.json"
    args = ctm.build_parser().parse_args([
        "fuzz", "--iterations", "100", "--seed", "1", "--output", str(out),
    ])
    rc = args.func(args)
    assert rc == 0
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["seed"] == 1
    assert summary["iterations"] == 100
