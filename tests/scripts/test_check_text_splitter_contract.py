"""Tests for the split-case consumer check in check_text_splitter_contract.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_text_splitter_contract as gate  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _contract(*tests: str) -> dict:
    return {"consumers": {"split_case_tests": list(tests)}}


READS_SPLIT_CASES = 'load("tests/fixtures/text_splitter/contract.json")["split_cases"]'


def test_a_test_that_reads_split_cases_passes(tmp_path: Path) -> None:
    _write(tmp_path, "a_test.py", READS_SPLIT_CASES)
    assert gate.consumer_problems(_contract("a_test.py"), tmp_path) == []


def test_an_empty_consumer_list_fails(tmp_path: Path) -> None:
    assert gate.consumer_problems(_contract(), tmp_path) != []


def test_a_missing_consumer_section_fails(tmp_path: Path) -> None:
    assert gate.consumer_problems({}, tmp_path) != []


def test_a_listed_test_that_does_not_exist_fails(tmp_path: Path) -> None:
    problems = gate.consumer_problems(_contract("gone_test.py"), tmp_path)
    assert any("gone_test.py" in p for p in problems)


@pytest.mark.parametrize(
    "text",
    [
        # Reads the fixture but not the split cases.
        'load("tests/fixtures/text_splitter/contract.json")["canonical"]',
        # Mentions split_cases but not the fixture.
        'cases = split_cases()',
    ],
)
def test_a_test_that_stops_reading_split_cases_fails(tmp_path: Path, text: str) -> None:
    _write(tmp_path, "a_test.py", text)
    problems = gate.consumer_problems(_contract("a_test.py"), tmp_path)
    assert any("a_test.py" in p for p in problems)


def test_the_repository_contract_lists_every_runtime() -> None:
    contract = gate.load_contract()
    tests = contract["consumers"]["split_case_tests"]
    # One per runtime that splits sentences: Python, Rust, Go, C#, C++, JS.
    assert len(tests) == 6
    assert gate.consumer_problems(contract) == []
