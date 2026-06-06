"""Swedish per-word LID (conservative policy) — Python *runtime* mirror.

Issue #539 Phase 1: regression tests for the runtime package
(``piper.phonemize.multilingual``), mirroring the canonical g2p tests in
``src/python/g2p/tests/test_swedish_lid.py``.

The runtime ``MultilingualPhonemizer`` intentionally has a different public
surface from the canonical g2p phonemizer: it exposes only ``phonemize`` and
has **no** ``segment_text`` method. The conservative per-word post-pass is
therefore exercised here through the module-level helper
``_segment_text_multilingual`` + ``UnicodeLanguageDetector``, asserting on the
returned ``(lang, text)`` tuples.

The Swedish LID post-pass is pure logic (no per-language phonemizer
dependency), so these tests run unconditionally — no ``importorskip`` needed.
"""

import pytest

from piper.phonemize.multilingual import (
    UnicodeLanguageDetector,
    _segment_text_multilingual,
)


pytestmark = pytest.mark.unit


def _langs(text, languages=("en", "sv"), default_latin_language="en"):
    """Return the per-segment language codes for *text* via the runtime path."""
    det = UnicodeLanguageDetector(
        list(languages), default_latin_language=default_latin_language
    )
    return [lang for lang, _ in _segment_text_multilingual(text, det)]


def test_strong_char_a_ring_detected_as_swedish():
    assert "sv" in _langs("så")
    assert "sv" in _langs("från")


def test_function_word_detected_as_swedish():
    assert _langs("och") == ["sv"]
    assert _langs("jag") == ["sv"]
    assert _langs("inte") == ["sv"]


def test_function_words_with_diacritics_detected():
    assert _langs("för") == ["sv"]
    assert _langs("när") == ["sv"]
    assert _langs("är") == ["sv"]


def test_bare_umlaut_not_swedish_conservative():
    assert "sv" not in _langs("Mädchen")
    assert "sv" not in _langs("schön")


def test_bare_umlaut_nonfunction_word_not_swedish():
    # ä/ö are weak: a word containing only ä/ö that is NOT a function word
    # must NOT be reclassified as Swedish (German "wörter", made-up "xöx").
    assert "sv" not in _langs("wörter")
    assert "sv" not in _langs("xöx")


def test_detection_requires_sv_in_language_set():
    assert "sv" not in _langs("från", languages=("en", "es"))


def test_sentence_reclassified_whole_segment():
    assert _langs("jag heter Anna") == ["sv"]
