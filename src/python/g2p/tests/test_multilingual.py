"""Tests for piper_g2p.multilingual -- MultilingualPhonemizer."""

import pytest

from tests.conftest import requires_ja


class TestUnicodeDetector:
    def test_unicode_detector_latin(self):
        """UnicodeLanguageDetector classifies Latin characters correctly."""
        from piper_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en"], default_latin_language="en"
        )
        assert detector.detect_char("A") == "en"
        assert detector.detect_char("z") == "en"

    def test_unicode_detector_kana(self):
        """UnicodeLanguageDetector classifies kana as Japanese."""
        from piper_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en"], default_latin_language="en"
        )
        assert detector.detect_char("\u3042") == "ja"  # hiragana 'a'
        assert detector.detect_char("\u30A2") == "ja"  # katakana 'a'

    def test_unicode_detector_cjk_disambiguation(self):
        """CJK ideographs are disambiguated by kana context."""
        from piper_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "zh"], default_latin_language="ja"
        )
        # Without kana context -> zh
        assert detector.detect_char("\u4e2d", context_has_kana=False) == "zh"
        # With kana context -> ja
        assert detector.detect_char("\u4e2d", context_has_kana=True) == "ja"

    def test_unicode_detector_hangul(self):
        """UnicodeLanguageDetector classifies Hangul as Korean."""
        from piper_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en", "ko"], default_latin_language="en"
        )
        assert detector.detect_char("\uAC00") == "ko"  # Hangul syllable 'ga'

    def test_unicode_detector_neutral(self):
        """Neutral characters (digits, whitespace) return None."""
        from piper_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en"], default_latin_language="en"
        )
        assert detector.detect_char("1") is None
        assert detector.detect_char(" ") is None


class TestCompositeCode:
    def test_composite_code(self):
        """get_phonemizer('ja-en') returns a MultilingualPhonemizer."""
        from piper_g2p.registry import get_phonemizer

        # This requires at least 'ja' and 'en' to be registered.
        # If they are not available, skip gracefully.
        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        from piper_g2p.multilingual import MultilingualPhonemizer

        assert isinstance(p, MultilingualPhonemizer)

    def test_canonical_key(self):
        """'ja-en' and 'en-ja' resolve to the same instance."""
        from piper_g2p.registry import get_phonemizer

        try:
            p1 = get_phonemizer("ja-en")
            p2 = get_phonemizer("en-ja")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        assert p1 is p2

    def test_missing_language_raises(self):
        """Composite code with an unknown language raises ValueError."""
        from piper_g2p.registry import get_phonemizer

        with pytest.raises(ValueError, match="Missing language"):
            get_phonemizer("ja-xx")


@requires_ja
class TestMixedText:
    def test_ja_en_mixed(self):
        """Mixed Japanese-English text is phonemized without error."""
        from piper_g2p.registry import get_phonemizer

        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        tokens = p.phonemize("\u3053\u3093\u306b\u3061\u306fHello")
        assert len(tokens) > 0

    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_g2p.registry import get_phonemizer

        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        tokens, prosody = p.phonemize_with_prosody(
            "\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3067\u3059\u306d"
        )
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )
