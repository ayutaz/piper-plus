"""Tests for the consumer check in build_english_normalize_fixture.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_english_normalize_fixture as fixture  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_test_that_reads_the_fixture_passes(tmp_path: Path) -> None:
    _write(tmp_path, "a_test.go", 'load("english_normalize_cases.json")')
    assert fixture.consumer_problems(["a_test.go"], tmp_path) == []


def test_a_listed_test_that_does_not_exist_fails(tmp_path: Path) -> None:
    problems = fixture.consumer_problems(["gone_test.go"], tmp_path)
    assert any("gone_test.go" in p for p in problems)


def test_a_test_that_stops_reading_the_fixture_fails(tmp_path: Path) -> None:
    _write(tmp_path, "a_test.go", 'load("english_cases.json")')
    problems = fixture.consumer_problems(["a_test.go"], tmp_path)
    assert any("a_test.go" in p for p in problems)


def test_an_empty_consumer_list_fails(tmp_path: Path) -> None:
    assert fixture.consumer_problems([], tmp_path) != []


@pytest.mark.parametrize("runtime_dir", ["src/cpp/", "src/rust/", "src/go/"])
def test_every_ported_runtime_has_a_consumer(runtime_dir: str) -> None:
    # The C++, Rust (#821) and Go (#841) ports are each checked against the
    # fixture; a runtime that drops its test would drift without a failure.
    assert any(t.startswith(runtime_dir) for t in fixture.CONSUMER_TESTS)


def test_the_repository_consumers_read_the_fixture() -> None:
    assert fixture.consumer_problems(fixture.CONSUMER_TESTS) == []
