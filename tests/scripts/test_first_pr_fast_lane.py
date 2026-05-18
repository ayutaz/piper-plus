"""Unit tests for scripts/first_pr_fast_lane.py (M1.3)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "first_pr_fast_lane.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "first_pr"

GATES = (
    "Parity Hub,PUA Consistency Gate,ZH-EN Loanword Sync Gate,"
    "Migration Guide Lint,ORT Version Sync"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("first_pr_fast_lane", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fpfl():
    return _load_module()


# ---------------- evaluate -------------------------------------------------

@pytest.mark.parametrize(
    ("assoc", "labels", "expected"),
    [
        ("FIRST_TIME_CONTRIBUTOR", "", True),
        ("FIRST_TIMER", "", True),
        ("NONE", "", True),
        ("CONTRIBUTOR", "", False),
        ("COLLABORATOR", "", False),
        ("MEMBER", "", False),
        ("OWNER", "", False),
        ("FIRST_TIME_CONTRIBUTOR", "run-full-gate", False),
        ("FIRST_TIME_CONTRIBUTOR", "bug,run-full-gate,docs", False),
        ("NONE", "documentation", True),
    ],
)
def test_evaluate(fpfl, assoc, labels, expected):
    fast_lane, reason = fpfl.evaluate(assoc, fpfl.parse_labels(labels))
    assert fast_lane is expected, reason


def test_evaluate_emits_github_output(fpfl, tmp_path, capsys):
    output = tmp_path / "github_output.txt"
    args = fpfl.build_parser().parse_args([
        "evaluate",
        "--author-association", "FIRST_TIME_CONTRIBUTOR",
        "--labels", "",
        "--github-output", str(output),
    ])
    rc = args.func(args)
    assert rc == 0
    content = output.read_text()
    assert "fast_lane=true" in content


# ---------------- neutralize -----------------------------------------------

def _neutralize_dry(fpfl, fixture_name: str):
    args = fpfl.build_parser().parse_args([
        "neutralize",
        "--gates", GATES,
        "--runs-json", str(FIXTURES / fixture_name),
    ])
    rc = args.func(args)
    return rc


def test_neutralize_collects_failing_contract_gates(fpfl, capsys):
    rc = _neutralize_dry(fpfl, "check_runs_mixed.json")
    out = capsys.readouterr().out
    assert rc == 0
    # Failing contract gates should be reported (Parity Hub id=1, PUA id=2).
    # `id=6 Parity Hub conclusion=neutral` must be skipped — only failures count.
    assert "DRY-RUN check-run 1" in out
    assert "DRY-RUN check-run 2" in out
    # ZH-EN Loanword was success — not patched.
    assert "DRY-RUN check-run 3" not in out
    # ruff format is not in the contract gate list — not patched.
    assert "DRY-RUN check-run 5" not in out
    # The pre-existing neutral run is skipped.
    assert "DRY-RUN check-run 6" not in out
    # In-progress run is skipped.
    assert "DRY-RUN check-run 4" not in out


def test_neutralize_idempotent_on_already_neutral(fpfl, capsys):
    rc = _neutralize_dry(fpfl, "check_runs_already_neutral.json")
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" not in out  # nothing to do


def test_neutralize_internals(fpfl):
    runs = fpfl.load_check_runs_fixture(FIXTURES / "check_runs_mixed.json")
    gates = fpfl.parse_labels(GATES)
    targets = fpfl.neutralize(runs, gates, repo=None, token=None, apply=False)
    names_conclusions = sorted((t.name, t.conclusion) for t in targets)
    assert names_conclusions == [
        ("PUA Consistency Gate", "failure"),
        ("Parity Hub", "failure"),
    ]


def test_neutralize_requires_token_when_applying(fpfl, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    args = fpfl.build_parser().parse_args([
        "neutralize",
        "--gates", GATES,
        "--runs-json", str(FIXTURES / "check_runs_mixed.json"),
        "--apply",
        "--repo", "owner/name",
    ])
    with pytest.raises(SystemExit):
        args.func(args)


def test_format_sticky_comment_includes_marker(fpfl):
    body = fpfl.format_sticky_comment("Fast lane active", [])
    assert fpfl.STICKY_MARKER in body
    assert "core lint" in body.lower()
