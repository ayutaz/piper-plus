"""Swedish per-word LID (conservative policy) — Issue #539 regression tests."""

from piper_plus_g2p.multilingual import MultilingualPhonemizer


def _langs(text):
    phon = MultilingualPhonemizer(["en", "sv"], default_latin_language="en")
    return [s["language"] for s in phon.segment_text(text)]


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
    phon = MultilingualPhonemizer(["en", "es"], default_latin_language="en")
    langs = [s["language"] for s in phon.segment_text("från")]
    assert "sv" not in langs


def test_sentence_reclassified_whole_segment():
    assert _langs("jag heter Anna") == ["sv"]
