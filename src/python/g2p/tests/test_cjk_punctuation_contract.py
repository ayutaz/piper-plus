"""CJK punctuation contract (Issue #823).

Reads ``tests/fixtures/g2p/cjk_punctuation_cases.json``, which
``scripts/build_cjk_punctuation_fixture.py`` builds from
``docs/spec/cjk-punctuation-contract.toml``. Every runtime has the same test,
so a detector or Latin-segment rewrite that drifts from the contract fails in
the runtime that drifted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from piper_plus_g2p.multilingual import (
    MultilingualPhonemizer,
    UnicodeLanguageDetector,
    normalize_cjk_punctuation_for_latin,
)

# tests/ -> g2p/ -> python/ -> src/ -> repo
_REPO_ROOT = Path(__file__).resolve().parents[4]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "g2p" / "cjk_punctuation_cases.json"
_LANGUAGES = ["en", "es", "fr", "ja", "ko", "pt", "sv", "zh"]


@pytest.fixture(scope="module")
def fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


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
    # Everything else is left alone, the fullwidth Latin letters included.
    for text in ["Hello, world!", "café", "ＡＢＣ", "你好", "こんにちは", ""]:
        assert normalize_cjk_punctuation_for_latin(text) == text


@pytest.fixture(scope="module")
def phonemizer() -> MultilingualPhonemizer:
    return MultilingualPhonemizer(_LANGUAGES, default_latin_language="en")


def test_chinese_sentence_keeps_its_punctuation(
    phonemizer: MultilingualPhonemizer,
) -> None:
    tokens = phonemizer.phonemize("你好，今天天气很好。")
    assert tokens.count(",") == 1
    assert tokens[-1] == "."
    assert phonemizer.phonemize("北京欢迎你。")[-1] == "."
    assert [s["language"] for s in phonemizer.segment_text("你好，今天天气很好。")] == [
        "zh"
    ]


def test_english_after_chinese_comma_is_read_as_a_loanword(
    phonemizer: MultilingualPhonemizer,
) -> None:
    # The ZH-EN dispatch needs the Chinese segment right before the English
    # one; a Japanese segment for "，" used to sit between them.
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
    # g2p_en deletes characters it does not know, which used to join
    # "Hello，world" into one word.
    assert phonemizer.phonemize(cjk) == phonemizer.phonemize(ascii_text)


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("zh", "你好，今天天气很好。"),
        ("zh", "北京欢迎你！你好吗？"),
        ("ja", "こんにちは、世界。"),
        ("ja", "「はい」と言った。"),
    ],
)
def test_one_language_text_matches_the_training_phonemizer(
    phonemizer: MultilingualPhonemizer, language: str, text: str
) -> None:
    # prepare_multilingual_dataset builds the training data with the
    # per-language phonemizer; inference goes through MultilingualPhonemizer.
    # Punctuation must not move a one-language sentence onto another path.
    from piper_plus_g2p import get_phonemizer

    if language == "ja":
        pytest.importorskip("pyopenjtalk")
    expected, _ = get_phonemizer(language).phonemize_with_prosody(text)
    actual, _ = phonemizer.phonemize_with_prosody(text)
    assert actual == expected
