"""Tests for the language_code property on all Phonemizer subclasses."""

from tests.conftest import requires_en, requires_ja, requires_ko, requires_zh


class TestLanguageCode:
    @requires_ja
    def test_japanese_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ja")
        assert p.language_code == "ja"

    @requires_en
    def test_english_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("en")
        assert p.language_code == "en"

    @requires_zh
    def test_chinese_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("zh")
        assert p.language_code == "zh"

    @requires_ko
    def test_korean_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("ko")
        assert p.language_code == "ko"

    def test_spanish_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("es")
        assert p.language_code == "es"

    def test_french_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("fr")
        assert p.language_code == "fr"

    def test_portuguese_language_code(self):
        from piper_plus_g2p import get_phonemizer

        p = get_phonemizer("pt")
        assert p.language_code == "pt"
