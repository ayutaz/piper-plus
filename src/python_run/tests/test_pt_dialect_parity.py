"""Portuguese BR vs EU dialect parity test (Python canonical).

Drives the per-phenomenon BR/EU post-processing in
`piper_plus_g2p.portuguese.PortuguesePhonemizer` from a runtime-neutral
JSON fixture (`tests/fixtures/g2p/pt_dialect_parity.json`). The same
fixture is intended for reuse by Rust/Go/C#/C++/WASM ports as the BR/EU
implementations land per-runtime (the path is stable so they can pin it
directly).

Why a per-phenomenon fixture? `docs/spec/pt-dialect-contract.toml`
enumerates 5 canonical phonological differences; a single-list "input ->
expected tokens" fixture would let a regression in one phenomenon pass
silently as long as another phenomenon's words still matched. Grouping
by phenomenon means a runtime can skip / xfail a single block while the
remaining 4 continue to gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/g2p/pt_dialect_parity.json"


def _load_fixture() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(f"fixture missing: {FIXTURE_PATH}")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _phonemize(phonemizer, word: str) -> list[str]:
    """Normalize PhonemizeResult / list-of-tokens return shapes."""
    result = phonemizer.phonemize(word)
    if hasattr(result, "tokens"):
        return list(result.tokens)
    if isinstance(result, list):
        return list(result)
    raise TypeError(f"unexpected phonemize() return type: {type(result).__name__}")


@pytest.fixture(scope="module")
def fixture() -> dict:
    return _load_fixture()


@pytest.fixture(scope="module")
def phonemizers():
    try:
        from piper_plus_g2p.portuguese import Dialect, PortuguesePhonemizer
    except ImportError as exc:
        pytest.skip(f"piper_plus_g2p not importable: {exc}")
    return {
        "br": PortuguesePhonemizer(dialect=Dialect.BR),
        "eu": PortuguesePhonemizer(dialect=Dialect.EU),
    }


def test_fixture_has_all_canonical_phenomena(fixture):
    """The fixture must cover the 5 phenomena pinned in pt-dialect-contract."""
    expected = {
        "t/d palatalisation before unstressed final /e/",
        "Final unstressed -e",
        "Final -s / -z and pre-consonantal -s",
        "Coda /l/",
        "Strong /r/ and word-final r",
    }
    actual = {tc["phenomenon"] for tc in fixture["test_cases"]}
    assert actual == expected, (
        f"phenomenon coverage drift: missing={sorted(expected - actual)}, "
        f"extra={sorted(actual - expected)} — keep this set in sync with "
        f"docs/spec/pt-dialect-contract.toml"
    )


def test_fixture_examples_are_well_formed(fixture):
    """Each example must declare word + br + eu (non-empty lists of strings)."""
    for case in fixture["test_cases"]:
        for ex in case["examples"]:
            assert "word" in ex and isinstance(ex["word"], str) and ex["word"]
            for dialect in ("br", "eu"):
                assert dialect in ex, f"example missing {dialect!r}: {ex}"
                tokens = ex[dialect]
                assert isinstance(tokens, list) and tokens, (
                    f"example {ex['word']!r}.{dialect} must be a non-empty list"
                )
                assert all(isinstance(t, str) for t in tokens), (
                    f"example {ex['word']!r}.{dialect} must be list[str]"
                )


@pytest.mark.parametrize(
    "phenomenon,word,expected",
    [
        # Flattened (phenomenon, word, expected-br-tokens) triples for BR
        # so pytest reports a clear nodeid per failing word.
        pytest.param(
            case["phenomenon"],
            ex["word"],
            ex["br"],
            id=f"BR::{case['phenomenon']}::{ex['word']}",
        )
        for case in _load_fixture()["test_cases"]
        for ex in case["examples"]
    ],
)
def test_pt_br_dialect_matches_fixture(phonemizers, phenomenon, word, expected):
    """BR phonemizer must produce the fixture-pinned tokens for each word."""
    actual = _phonemize(phonemizers["br"], word)
    assert actual == expected, (
        f"BR drift on {phenomenon!r}/{word!r}: got {actual}, want {expected}"
    )


@pytest.mark.parametrize(
    "phenomenon,word,expected",
    [
        pytest.param(
            case["phenomenon"],
            ex["word"],
            ex["eu"],
            id=f"EU::{case['phenomenon']}::{ex['word']}",
        )
        for case in _load_fixture()["test_cases"]
        for ex in case["examples"]
    ],
)
def test_pt_eu_dialect_matches_fixture(phonemizers, phenomenon, word, expected):
    """EU phonemizer must produce the fixture-pinned tokens for each word."""
    actual = _phonemize(phonemizers["eu"], word)
    assert actual == expected, (
        f"EU drift on {phenomenon!r}/{word!r}: got {actual}, want {expected}"
    )


def test_br_eu_differ_on_documented_phenomena(fixture, phonemizers):
    """Sanity-check: every phenomenon EXCEPT 'Strong /r/ ...' must show at
    least one example where BR != EU. The /r/ phenomenon is currently
    BR=EU because the BR implementation does not produce 'h' allophones
    — this is documented in the fixture's spec_mechanism field.
    """
    for case in fixture["test_cases"]:
        phenomenon = case["phenomenon"]
        diffs = [
            ex
            for ex in case["examples"]
            if _phonemize(phonemizers["br"], ex["word"])
            != _phonemize(phonemizers["eu"], ex["word"])
        ]
        if phenomenon == "Strong /r/ and word-final r":
            # No observable difference today — documented in spec_mechanism.
            continue
        assert diffs, (
            f"phenomenon {phenomenon!r} produced zero BR/EU diffs across "
            f"{len(case['examples'])} examples — either the implementation "
            "regressed or the fixture words no longer trigger the rule"
        )
