"""Cross-runtime parity test: Python text_splitter against contract.json.

Loads ``tests/fixtures/text_splitter/contract.json`` and asserts that the
Python canonical implementation's ``_CLOSING_PUNCTUATION`` and
``_SENTENCE_TERMINATORS`` sets match the ``runtimes.python.*`` projection of
the toml-generated fixture.

Sibling tests for Rust/Go/C# live in their own runtime CIs and use the same
fixture. The toml drift gate (`parity-hub.yml` text-splitter matrix entry) ensures the fixture
stays in sync with the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/text_splitter/contract.json"


@pytest.fixture(scope="module")
def contract():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.unit
class TestTextSplitterContract:
    def test_fixture_loads(self, contract):
        assert contract["schema_version"] == 1
        assert "runtimes" in contract and "python" in contract["runtimes"]

    def test_python_closing_punctuation_matches_fixture(self, contract):
        from piper.text_splitter import _CLOSING_PUNCTUATION

        expected = {
            chr(cp) for cp in contract["runtimes"]["python"]["closing_punctuation"]
        }
        assert set(_CLOSING_PUNCTUATION) == expected

    def test_python_sentence_terminators_match_fixture(self, contract):
        from piper.text_splitter import _SENTENCE_TERMINATORS

        expected = {
            chr(cp) for cp in contract["runtimes"]["python"]["sentence_terminators"]
        }
        assert set(_SENTENCE_TERMINATORS) == expected

    def test_python_strategy_is_post_consume(self, contract):
        # Behavioural assertion: after a terminator, a closing-punct codepoint
        # is greedily consumed into the same sentence chunk.
        from piper.text_splitter import split_sentences

        # Use the fullwidth right corner bracket 」 (in python's set).
        chunks = split_sentences("彼は「元気です。」次の文。")
        assert chunks == ["彼は「元気です。」", "次の文。"]
        assert contract["runtimes"]["python"]["strategy"] == "post-consume"

    def test_python_canonical_matches_runtime(self, contract):
        # Python is the canonical reference: its set equals the canonical set.
        assert (
            contract["runtimes"]["python"]["closing_punctuation"]
            == contract["canonical"]["closing_punctuation"]
        )
        assert (
            contract["runtimes"]["python"]["sentence_terminators"]
            == contract["canonical"]["sentence_terminators"]
        )
