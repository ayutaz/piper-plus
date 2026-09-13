"""Hinglish per-word LID — Python runtime mirror."""

import pytest

from piper_plus.phonemize.multilingual import (
    UnicodeLanguageDetector,
    _segment_text_multilingual,
)


pytestmark = pytest.mark.unit


def _langs(text, languages=("hi", "en"), default_latin_language="en"):
    det = UnicodeLanguageDetector(
        list(languages), default_latin_language=default_latin_language
    )
    return [lang for lang, _ in _segment_text_multilingual(text, det)]


def test_devanagari_word_is_hindi():
    assert _langs("आपका") == ["hi"]


def test_lexicon_word_reclassified_from_english():
    assert _langs("aapka") == ["hi"]
    assert _langs("hai") == ["hi"]


def test_detection_requires_hi_in_language_set():
    assert "hi" not in _langs("aapka", languages=("en", "es"))
