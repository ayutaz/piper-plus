"""CJK punctuation contract (Issue #823), inference-side runtime.

Reads ``tests/fixtures/g2p/cjk_punctuation_cases.json``, which
``scripts/build_cjk_punctuation_fixture.py`` builds from
``docs/spec/cjk-punctuation-contract.toml``. Mirrors
src/python/g2p/tests/test_cjk_punctuation_contract.py for
``piper_plus.phonemize.multilingual``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus.phonemize.multilingual import (
    MultilingualPhonemizer,
    UnicodeLanguageDetector,
    normalize_cjk_punctuation_for_latin,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "g2p" / "cjk_punctuation_cases.json"
# The languages this runtime can phonemize.
LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt"]


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def detector(fixture: dict) -> UnicodeLanguageDetector:
    return UnicodeLanguageDetector(
        fixture["detector_languages"], default_latin_language=fixture["default_latin"]
    )


def test_fixture_is_not_empty(fixture: dict) -> None:
    assert len(fixture["neutral"]) > 100
    assert len(fixture["fullwidth_latin"]) == 52


@pytest.mark.parametrize("context_has_kana", [False, True])
def test_neutral_code_points_belong_to_no_language(
    fixture: dict, detector: UnicodeLanguageDetector, context_has_kana: bool
) -> None:
    wrong = [
        (c["code_point"], lang)
        for c in fixture["neutral"]
        if (lang := detector.detect_char(c["char"], context_has_kana=context_has_kana))
        is not None
    ]
    assert wrong == []


def test_fullwidth_latin_letters_stay_latin(
    fixture: dict, detector: UnicodeLanguageDetector
) -> None:
    wrong = [
        c["code_point"]
        for c in fixture["fullwidth_latin"]
        if detector.detect_char(c["char"]) != fixture["default_latin"]
    ]
    assert wrong == []


def test_latin_segment_rewrite(fixture: dict) -> None:
    wrong = [
        (c["code_point"], normalize_cjk_punctuation_for_latin(c["char"]), c["latin"])
        for c in fixture["neutral"]
        if normalize_cjk_punctuation_for_latin(c["char"]) != c["latin"]
    ]
    assert wrong == []
    for text in ["Hello, world!", "café", "ＡＢＣ", "你好", "こんにちは", ""]:
        assert normalize_cjk_punctuation_for_latin(text) == text


@pytest.fixture(scope="module")
def phonemizer() -> MultilingualPhonemizer:
    pytest.importorskip("pypinyin", reason="pypinyin not installed")
    pytest.importorskip(
        "piper_plus._vendor.g2p_en", reason="English backend dependencies not installed"
    )
    return MultilingualPhonemizer(LANGUAGES, default_latin_language="en")


def test_chinese_sentence_keeps_its_punctuation(phonemizer: MultilingualPhonemizer) -> None:
    tokens = phonemizer.phonemize("你好，今天天气很好。")
    assert tokens.count(",") == 1
    assert tokens[-1] == "."


def test_english_after_chinese_comma_is_read_as_a_loanword(
    phonemizer: MultilingualPhonemizer,
) -> None:
    with_comma = phonemizer.phonemize("你好，GPS")
    without = phonemizer.phonemize("你好GPS")
    assert [t for t in with_comma if t != ","] == without


@pytest.mark.parametrize(
    ("cjk", "ascii_text"),
    [
        ("Hello，world", "Hello,world"),
        ("Hello、world。", "Hello,world."),
        ("Hola，amigo！", "Hola,amigo!"),
        ("I have ３ cats．", "I have 3 cats."),
    ],
)
def test_latin_text_with_cjk_punctuation_reads_like_ascii(
    phonemizer: MultilingualPhonemizer, cjk: str, ascii_text: str
) -> None:
    assert phonemizer.phonemize(cjk) == phonemizer.phonemize(ascii_text)
