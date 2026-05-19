"""Unit tests for scripts/fuzz_forward_compat.py (M4.1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "fuzz_forward_compat.py"


def _load():
    spec = importlib.util.spec_from_file_location("fuzz_forward_compat", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ffc():
    return _load()


def test_known_seed_reproducible(ffc):
    a = ffc.fuzz(seed=42, iterations=50)
    b = ffc.fuzz(seed=42, iterations=50)
    assert a.passes == b.passes
    assert [f[1] for f in a.failures] == [f[1] for f in b.failures]


def test_default_iterations_have_no_failures(ffc):
    """The reference lenient_loader must accept all randomised future schemas."""
    result = ffc.fuzz(seed=0, iterations=500)
    assert result.failures == [], f"unexpected loader failures: {result.failures}"


def test_lenient_loader_accepts_unknown_top_level_keys(ffc):
    payload = {
        "schema_version": 99,
        "acronyms": {"USB": ["U", "S", "B"]},
        "loanwords": {},
        "letter_fallback": {},
        "future_unknown": {"deep": {"value": 1}},
    }
    ffc.lenient_loader(payload)


def test_lenient_loader_rejects_non_dict_top_level_section(ffc):
    payload = {
        "schema_version": 99,
        "acronyms": [1, 2, 3],  # invalid; must be a dict
    }
    with pytest.raises(TypeError):
        ffc.lenient_loader(payload)


def test_cli_fuzz_writes_summary(ffc, tmp_path):
    out = tmp_path / "summary.json"
    args = ffc.build_parser().parse_args([
        "fuzz", "--iterations", "100", "--seed", "1", "--output", str(out),
    ])
    rc = args.func(args)
    assert rc == 0
    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["seed"] == 1
    assert summary["iterations"] == 100
    assert summary["passes"] == 100


def test_cli_record_appends_to_dashboard(ffc, tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"seed": 1, "iterations": 5, "passes": 5, "failures": []}))
    dashboard = tmp_path / "fwc.jsonl"
    args = ffc.build_parser().parse_args([
        "record", "--input", str(summary), "--dashboard", str(dashboard),
    ])
    rc = args.func(args)
    assert rc == 0
    lines = dashboard.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["seed"] == 1
    assert record["passes"] == 5
    assert record["failure_count"] == 0
