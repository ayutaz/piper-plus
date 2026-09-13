"""Hindi / Hinglish per-word LID tests."""

from piper_plus_g2p.multilingual import MultilingualPhonemizer
from tests.conftest import requires_en


def _langs(text, languages=("hi", "en"), default="en"):
    phon = MultilingualPhonemizer(list(languages), default_latin_language=default)
    return [s["language"] for s in phon.segment_text(text)]


def test_devanagari_word_is_hindi():
    assert _langs("आपका") == ["hi"]


def test_lexicon_word_reclassified_from_english():
    assert _langs("aapka") == ["hi"]
    assert _langs("hai") == ["hi"]


@requires_en
def test_english_tech_word_stays_english():
    assert _langs("asynchronous") == ["en"]
    assert _langs("function") == ["en"]
    assert _langs("await") == ["en"]


@requires_en
def test_mixed_sentence_splits_hi_en():
    segs = MultilingualPhonemizer(
        ["hi", "en"], default_latin_language="en"
    ).segment_text("Aapka logic hai")
    by_word: dict[str, str] = {}
    for s in segs:
        for w in s["text"].split():
            key = w.strip(".,;:!?")
            if key.isalpha():
                by_word[key.lower()] = s["language"]
    assert by_word["aapka"] == "hi"
    assert by_word["logic"] == "en"
    assert by_word["hai"] == "hi"


def test_detection_requires_hi_in_language_set():
    phon = MultilingualPhonemizer(["en", "es"], default_latin_language="en")
    langs = [s["language"] for s in phon.segment_text("aapka")]
    assert "hi" not in langs
