"""Tests for piper_plus_g2p.hindi — HindiPhonemizer (Phase 1)."""

from piper_plus_g2p.hindi import HindiPhonemizer, classify_latin_word
from tests.conftest import requires_en


class TestDevanagari:
    def test_aapka(self):
        p = HindiPhonemizer()
        assert p.phonemize("आपका") == ["ɑ", "p", "k", "ɑ"]

    def test_namaste(self):
        p = HindiPhonemizer()
        assert p.phonemize("नमस्ते") == ["n", "ə", "m", "s", "t̪", "e"]

    def test_kamal_keeps_medial_schwa(self):
        p = HindiPhonemizer()
        assert p.phonemize("कमल") == ["k", "ə", "m", "ə", "l"]

    def test_dental_vs_retroflex(self):
        p = HindiPhonemizer()
        assert p.phonemize("ताल") == ["t̪", "ɑ", "l"]
        assert p.phonemize("टाल") == ["ʈ", "ɑ", "l"]

    def test_aspirate_contrast(self):
        p = HindiPhonemizer()
        assert p.phonemize("कल") == ["k", "ə", "l"]
        assert p.phonemize("खल") == ["kʰ", "ə", "l"]

    def test_nukta_q_uvular_not_japanese_q(self):
        p = HindiPhonemizer()
        tokens = p.phonemize("क़लम")
        assert "q_uvular" in tokens
        assert "q" not in tokens

    def test_nukta_f_z(self):
        p = HindiPhonemizer()
        assert "f" in p.phonemize("फ़")
        assert "z" in p.phonemize("ज़")

    def test_flap_and_glottal(self):
        p = HindiPhonemizer()
        assert p.phonemize("ड़") == ["ɽ", "ə"]
        assert p.phonemize("व") == ["ʋ", "ə"]
        assert p.phonemize("ह") == ["ɦ", "ə"]

    def test_anusvara_homorganic_before_k(self):
        p = HindiPhonemizer()
        tokens = p.phonemize("अंक")
        assert "ŋ" in tokens

    def test_hai(self):
        p = HindiPhonemizer()
        assert p.phonemize("है") == ["ɦ", "ɛ"]

    def test_danda_passthrough(self):
        p = HindiPhonemizer()
        tokens = p.phonemize("नमस्ते।")
        assert "।" in tokens

    def test_no_pua_in_output(self):
        p = HindiPhonemizer()
        for token in p.phonemize("आपका लॉजिक सही है"):
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF)


class TestLatinHinglish:
    def test_aapka_not_english_ash(self):
        p = HindiPhonemizer()
        tokens = p.phonemize("Aapka")
        assert tokens == ["ɑ", "p", "k", "ɑ"]
        assert "æ" not in tokens

    def test_hai_latin(self):
        p = HindiPhonemizer()
        assert p.phonemize("hai") == ["ɦ", "ɛ"]

    def test_classify_lexicon_wins(self):
        assert classify_latin_word("aapka") == "hi"
        assert classify_latin_word("hai") == "hi"
        assert classify_latin_word("the") == "hi"

    @requires_en
    def test_classify_english_tech_words(self):
        assert classify_latin_word("asynchronous") == "en"
        assert classify_latin_word("function") == "en"
        assert classify_latin_word("await") == "en"
        assert classify_latin_word("logic") == "en"

    @requires_en
    def test_unknown_latin_defaults_to_hindi(self):
        assert classify_latin_word("lagana") == "hi"
        assert classify_latin_word("bhool") == "hi"

    @requires_en
    def test_acceptance_sentence_splits_hi_en(self):
        p = HindiPhonemizer()
        text = (
            "Aapka logic bilkul sahi hai, bas yahan asynchronous function "
            "mein await lagana bhool gaye the."
        )
        tokens = p.phonemize(text)
        # Hindi "Aapka" is not English ash.
        assert tokens[:4] == ["ɑ", "p", "k", "ɑ"]
        assert "æ" not in tokens[:8]
        # English tech words keep English IPA (g2p-en uses ː / ɡ etc.).
        joined = " ".join(tokens)
        assert "ɑ" in tokens
        assert any(t in tokens for t in ("ə", "ʌ", "ɪ", "ŋ", "k"))
        assert "asynchronous" not in joined


class TestRegistryAndMixed:
    def test_registered(self):
        from piper_plus_g2p import available_languages, get_phonemizer

        assert "hi" in available_languages()
        p = get_phonemizer("hi")
        assert p.language_code == "hi"

    def test_devanagari_detected(self):
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        det = UnicodeLanguageDetector(["hi", "en"], default_latin_language="en")
        assert det.detect_char("आ") == "hi"
        assert det.detect_char("A") == "en"

    def test_devanagari_requires_hi_in_set(self):
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        det = UnicodeLanguageDetector(["en"], default_latin_language="en")
        assert det.detect_char("आ") is None

    @requires_en
    def test_multilingual_acceptance_sentence(self):
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        phon = MultilingualPhonemizer(["hi", "en"], default_latin_language="en")
        langs = [s["language"] for s in phon.segment_text("Aapka logic sahi hai")]
        assert langs[0] == "hi"
        assert "en" in langs
        assert "hi" in langs
        tokens = phon.phonemize("Aapka logic")
        assert tokens[:4] == ["ɑ", "p", "k", "ɑ"]
        assert "æ" not in tokens[:6]
