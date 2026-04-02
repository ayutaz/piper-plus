"""Edge case tests for piper_plus_g2p phonemizers."""

import pytest

from piper_plus_g2p import get_phonemizer
from tests.conftest import requires_en, requires_ja, requires_ko, requires_zh


class TestEmptyInput:
    """Test behavior with empty or whitespace-only input."""

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])  # rule-based (no deps)
    def test_empty_string(self, lang):
        ph = get_phonemizer(lang)
        result = ph.phonemize("")
        assert isinstance(result, list)

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    def test_whitespace_only(self, lang):
        ph = get_phonemizer(lang)
        result = ph.phonemize("   ")
        assert isinstance(result, list)

    @requires_ja
    def test_empty_string_ja(self):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        result = ph.phonemize("")
        assert isinstance(result, list)

    @requires_en
    def test_empty_string_en(self):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        result = ph.phonemize("")
        assert isinstance(result, list)

    @requires_zh
    def test_empty_string_zh(self):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        result = ph.phonemize("")
        assert isinstance(result, list)

    @requires_ko
    def test_empty_string_ko(self):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        result = ph.phonemize("")
        assert isinstance(result, list)

    @requires_ja
    def test_whitespace_only_ja(self):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        result = ph.phonemize("   ")
        assert isinstance(result, list)

    @requires_en
    def test_whitespace_only_en(self):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        result = ph.phonemize("   ")
        assert isinstance(result, list)

    @requires_zh
    def test_whitespace_only_zh(self):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        result = ph.phonemize("   ")
        assert isinstance(result, list)

    @requires_ko
    def test_whitespace_only_ko(self):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        result = ph.phonemize("   ")
        assert isinstance(result, list)


class TestSpecialCharacters:
    """Test behavior with special characters."""

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    def test_numbers_only(self, lang):
        ph = get_phonemizer(lang)
        result = ph.phonemize("12345")
        assert isinstance(result, list)

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    def test_punctuation_only(self, lang):
        ph = get_phonemizer(lang)
        result = ph.phonemize("...!?")
        assert isinstance(result, list)

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    def test_emoji(self, lang):
        ph = get_phonemizer(lang)
        result = ph.phonemize("Hello :)")
        assert isinstance(result, list)

    @requires_ja
    def test_numbers_only_ja(self):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        result = ph.phonemize("12345")
        assert isinstance(result, list)

    @requires_en
    def test_numbers_only_en(self):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        result = ph.phonemize("12345")
        assert isinstance(result, list)

    @requires_zh
    def test_numbers_only_zh(self):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        result = ph.phonemize("12345")
        assert isinstance(result, list)

    @requires_ko
    def test_numbers_only_ko(self):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        result = ph.phonemize("12345")
        assert isinstance(result, list)

    @requires_ja
    def test_punctuation_only_ja(self):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        result = ph.phonemize("...!?")
        assert isinstance(result, list)

    @requires_en
    def test_punctuation_only_en(self):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        result = ph.phonemize("...!?")
        assert isinstance(result, list)

    @requires_zh
    def test_punctuation_only_zh(self):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        result = ph.phonemize("...!?")
        assert isinstance(result, list)

    @requires_ko
    def test_punctuation_only_ko(self):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        result = ph.phonemize("...!?")
        assert isinstance(result, list)


class TestLongInput:
    """Test behavior with very long input."""

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    def test_long_text(self, lang):
        ph = get_phonemizer(lang)
        text = "Hola mundo. " * 100  # 1200 chars
        result = ph.phonemize(text)
        assert isinstance(result, list)
        assert len(result) > 0

    @requires_ja
    def test_long_text_ja(self):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        text = "こんにちは世界。" * 100
        result = ph.phonemize(text)
        assert isinstance(result, list)
        assert len(result) > 0

    @requires_en
    def test_long_text_en(self):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        text = "Hello world. " * 100
        result = ph.phonemize(text)
        assert isinstance(result, list)
        assert len(result) > 0

    @requires_zh
    def test_long_text_zh(self):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        text = "你好世界。" * 100
        result = ph.phonemize(text)
        assert isinstance(result, list)
        assert len(result) > 0

    @requires_ko
    def test_long_text_ko(self):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        text = "안녕하세요 세계. " * 100
        result = ph.phonemize(text)
        assert isinstance(result, list)
        assert len(result) > 0


class TestProsodyConsistency:
    """Test that prosody length always matches token length."""

    @pytest.mark.parametrize("lang", ["es", "fr", "pt"])
    @pytest.mark.parametrize("text", ["Hello", "", "123", "test test test"])
    def test_prosody_length_equals_tokens(self, lang, text):
        ph = get_phonemizer(lang)
        tokens, prosody = ph.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)

    @requires_ja
    @pytest.mark.parametrize("text", ["こんにちは", "", "123", "今日は良い天気です"])
    def test_prosody_length_equals_tokens_ja(self, text):
        from piper_plus_g2p.japanese import JapanesePhonemizer

        ph = JapanesePhonemizer()
        tokens, prosody = ph.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)

    @requires_en
    @pytest.mark.parametrize("text", ["Hello", "", "123", "test test test"])
    def test_prosody_length_equals_tokens_en(self, text):
        from piper_plus_g2p.english import EnglishPhonemizer

        ph = EnglishPhonemizer()
        tokens, prosody = ph.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)

    @requires_zh
    @pytest.mark.parametrize("text", ["你好", "", "123", "今天天气很好"])
    def test_prosody_length_equals_tokens_zh(self, text):
        from piper_plus_g2p.chinese import ChinesePhonemizer

        ph = ChinesePhonemizer()
        tokens, prosody = ph.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)

    @requires_ko
    @pytest.mark.parametrize("text", ["안녕하세요", "", "123", "오늘 날씨가 좋습니다"])
    def test_prosody_length_equals_tokens_ko(self, text):
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        tokens, prosody = ph.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)
