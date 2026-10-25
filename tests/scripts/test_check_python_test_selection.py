"""Tests for scripts/check_python_test_selection.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_python_test_selection.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"
CONFTEST = REPO_ROOT / "src" / "python" / "tests" / "conftest.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_python_test_selection", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expressions():
    return _module().extract_expressions(
        yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    )


def test_reads_the_unix_expressions_of_python_tests_yml():
    assert _expressions() == [
        "unit and not training and not benchmark and not inference",
        "integration and not benchmark",
        "inference and unit",
        "training and unit",
        "benchmark",
    ]


def test_windows_step_is_not_counted():
    """The Windows step runs a subset (no torch); counting it would hide a
    test that only Windows selects but Unix never runs."""
    workflow = {
        "jobs": {
            "test": {
                "steps": [
                    {
                        "if": "runner.os == 'Windows'",
                        "run": 'cd src/python\npytest tests/ -m "unit"\n',
                    },
                    {"run": 'cd src/python_run\npytest tests/ -m "unit"\n'},
                    {"run": 'cd src/python\npytest tests/ -v -m "integration"\n'},
                ]
            }
        }
    }
    assert _module().extract_expressions(workflow) == ["integration"]


def test_reports_a_test_no_expression_selects():
    full = {"a::t1", "a::t2", "b::t3"}
    assert _module().unselected(full, [{"a::t1"}, {"b::t3"}]) == ["a::t2"]
    assert _module().unselected(full, [{"a::t1", "a::t2"}, {"b::t3"}]) == []


def test_conftest_markers_match_what_the_expressions_build_on():
    """The selectable markers in conftest.py are exactly the ones the CI
    expressions select by; adding a marker on one side only reopens the gap."""
    text = CONFTEST.read_text(encoding="utf-8")
    assert (
        'SELECTABLE_MARKERS = frozenset({"unit", "integration", "benchmark"})' in text
    )
    assert "@pytest.hookimpl(tryfirst=True)" in text
    positive = set()
    for expr in _expressions():
        for clause in expr.split(" and "):
            if not clause.startswith("not "):
                positive.add(clause.strip())
    assert positive - {"training", "inference"} == {"unit", "integration", "benchmark"}
