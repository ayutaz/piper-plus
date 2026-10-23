"""Tests for scripts/check_g2p_known_divergences.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_g2p_known_divergences as gate  # noqa: E402

GOLDEN = [
    {"language": "en", "input": "0", "expected_phonemes": "z ˈ ɪ ɹ o ʊ"},
    {"language": "fr", "input": "c'est", "expected_phonemes": "s ɛ s"},
]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal repository with one runtime test that reads the registry."""
    _write(
        tmp_path / "src/cpp/tests/test_golden.cpp",
        '// reads tests/fixtures/g2p/known_divergences.json and english_no_drop_words.json\n',
    )
    return tmp_path


def _registry(*entries: dict, runtimes: dict | None = None) -> dict:
    return {
        "schema_version": 1,
        "runtimes": runtimes
        if runtimes is not None
        else {"cpp": {"description": "libpiper_plus", "tests": ["src/cpp/tests/test_golden.cpp"]}},
        "divergences": list(entries),
    }


def _entry(**overrides) -> dict:
    entry = {
        "runtimes": ["cpp"],
        "language": "en",
        "input": "0",
        "status": "planned",
        "issue": 821,
        "reason": "digits are dropped",
    }
    entry.update(overrides)
    return entry


def _no_drop(*known: dict, words: list[str] | None = None) -> dict:
    return {
        "schema_version": 1,
        "words": words if words is not None else ["hello", "0"],
        "known_drops": list(known),
    }


def _drop(**overrides) -> dict:
    drop = {"runtimes": ["cpp"], "word": "0", "issue": 821, "reason": "digits are dropped"}
    drop.update(overrides)
    return drop


# ---- divergence registry --------------------------------------------------


def test_valid_registry_has_no_problems(repo: Path) -> None:
    assert gate.validate_divergences(_registry(_entry()), GOLDEN, repo) == []


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"reason": "  "}, "reason is empty"),
        ({"issue": 0}, "issue must be a GitHub issue number"),
        ({"status": "maybe"}, "status must be one of"),
        ({"input": "missing"}, "not in phoneme_test_cases_golden.json"),
        ({"runtimes": ["kotlin"]}, "unknown runtime 'kotlin'"),
        ({"runtimes": []}, "no runtimes"),
    ],
)
def test_entry_problems_are_reported(repo: Path, overrides: dict, needle: str) -> None:
    problems = gate.validate_divergences(_registry(_entry(**overrides)), GOLDEN, repo)
    assert any(needle in p for p in problems), problems


def test_duplicate_entry_is_reported(repo: Path) -> None:
    problems = gate.validate_divergences(_registry(_entry(), _entry(reason="again")), GOLDEN, repo)
    assert any("duplicate entry for runtime 'cpp'" in p for p in problems), problems


def test_wrong_schema_version_is_reported(repo: Path) -> None:
    registry = _registry(_entry())
    registry["schema_version"] = 2
    assert any("schema_version" in p for p in gate.validate_divergences(registry, GOLDEN, repo))


def test_runtime_without_tests_is_reported(repo: Path) -> None:
    registry = _registry(runtimes={"cpp": {"description": "libpiper_plus", "tests": []}})
    problems = gate.validate_divergences(registry, GOLDEN, repo)
    assert any("runtime 'cpp' lists no tests" in p for p in problems), problems


def test_missing_runtime_test_is_reported(repo: Path) -> None:
    registry = _registry(runtimes={"cpp": {"description": "x", "tests": ["src/cpp/tests/gone.cpp"]}})
    problems = gate.validate_divergences(registry, GOLDEN, repo)
    assert any("src/cpp/tests/gone.cpp does not exist" in p for p in problems), problems


def test_runtime_test_that_ignores_the_registry_is_reported(repo: Path) -> None:
    _write(repo / "src/cpp/tests/other.cpp", "// compares nothing\n")
    registry = _registry(runtimes={"cpp": {"description": "x", "tests": ["src/cpp/tests/other.cpp"]}})
    problems = gate.validate_divergences(registry, GOLDEN, repo)
    assert any("does not read known_divergences.json" in p for p in problems), problems


# ---- english no-drop list -------------------------------------------------


def test_valid_no_drop_list_has_no_problems() -> None:
    assert gate.validate_no_drop(_no_drop(_drop()), {"cpp"}) == []


@pytest.mark.parametrize(
    ("drop", "needle"),
    [
        ({"word": "missing"}, "not in words"),
        ({"runtimes": ["kotlin"]}, "unknown runtime 'kotlin'"),
        ({"issue": -1}, "issue must be a GitHub issue number"),
        ({"reason": ""}, "reason is empty"),
    ],
)
def test_no_drop_problems_are_reported(drop: dict, needle: str) -> None:
    problems = gate.validate_no_drop(_no_drop(_drop(**drop)), {"cpp"})
    assert any(needle in p for p in problems), problems


def test_duplicate_no_drop_word_is_reported() -> None:
    problems = gate.validate_no_drop(_no_drop(words=["hello", "hello"]), {"cpp"})
    assert any("duplicate word 'hello'" in p for p in problems), problems


def test_duplicate_known_drop_is_reported() -> None:
    problems = gate.validate_no_drop(_no_drop(_drop(), _drop()), {"cpp"})
    assert any("duplicate entry for runtime 'cpp'" in p for p in problems), problems


# ---- main -----------------------------------------------------------------


def test_main_passes_on_the_repository() -> None:
    assert gate.main([]) == 0


def test_main_fails_on_a_broken_registry(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixtures = repo / "tests/fixtures/g2p"
    _write(fixtures / "phoneme_test_cases_golden.json", json.dumps({"test_cases": GOLDEN}))
    _write(fixtures / "known_divergences.json", json.dumps(_registry(_entry(issue=0))))
    _write(fixtures / "english_no_drop_words.json", json.dumps(_no_drop()))

    assert gate.main(["--repo-root", str(repo)]) == 1
    assert "issue must be a GitHub issue number" in capsys.readouterr().out
