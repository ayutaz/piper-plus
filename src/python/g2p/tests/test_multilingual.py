"""Tests for piper_plus_g2p.multilingual -- MultilingualPhonemizer."""

import pytest

from piper_plus_g2p.base import ProsodyInfo
from tests.conftest import requires_en, requires_ja, requires_zh


class TestUnicodeDetector:
    def test_unicode_detector_latin(self):
        """UnicodeLanguageDetector classifies Latin characters correctly."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("A") == "en"
        assert detector.detect_char("z") == "en"

    def test_unicode_detector_kana(self):
        """UnicodeLanguageDetector classifies kana as Japanese."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("\u3042") == "ja"  # hiragana 'a'
        assert detector.detect_char("\u30a2") == "ja"  # katakana 'a'

    def test_unicode_detector_cjk_disambiguation(self):
        """CJK ideographs are disambiguated by kana context."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "zh"], default_latin_language="ja")
        # Without kana context -> zh
        assert detector.detect_char("\u4e2d", context_has_kana=False) == "zh"
        # With kana context -> ja
        assert detector.detect_char("\u4e2d", context_has_kana=True) == "ja"

    def test_unicode_detector_hangul(self):
        """UnicodeLanguageDetector classifies Hangul as Korean."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en", "ko"], default_latin_language="en"
        )
        assert detector.detect_char("\uac00") == "ko"  # Hangul syllable 'ga'

    def test_unicode_detector_neutral(self):
        """Neutral characters (digits, whitespace) return None."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("1") is None
        assert detector.detect_char(" ") is None


class TestCompositeCode:
    def test_composite_code(self):
        """get_phonemizer('ja-en') returns a MultilingualPhonemizer."""
        from piper_plus_g2p.registry import get_phonemizer

        # This requires at least 'ja' and 'en' to be registered.
        # If they are not available, skip gracefully.
        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        assert isinstance(p, MultilingualPhonemizer)

    def test_canonical_key(self):
        """'ja-en' and 'en-ja' resolve to the same instance."""
        from piper_plus_g2p.registry import get_phonemizer

        try:
            p1 = get_phonemizer("ja-en")
            p2 = get_phonemizer("en-ja")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        assert p1 is p2

    def test_missing_language_raises(self):
        """Composite code with an unknown language raises ValueError."""
        from piper_plus_g2p.registry import get_phonemizer

        with pytest.raises(ValueError, match="Missing language"):
            get_phonemizer("ja-xx")


@requires_ja
class TestMixedText:
    def test_ja_en_mixed(self):
        """Mixed Japanese-English text is phonemized without error."""
        from piper_plus_g2p.registry import get_phonemizer

        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        tokens = p.phonemize("\u3053\u3093\u306b\u3061\u306fHello")
        assert len(tokens) > 0

    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_plus_g2p.registry import get_phonemizer

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


class TestMixedLanguageText:
    """Tests for mixed-language (code-switching) text via MultilingualPhonemizer."""

    @requires_ja
    @requires_en
    def test_mixed_ja_en(self):
        """Japanese-English mixed text produces phonemes from both languages."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        # "こんにちは Hello"
        tokens = p.phonemize("こんにちは Hello")
        assert len(tokens) > 0

        # Prosody alignment must hold for mixed text too
        tokens_p, prosody = p.phonemize_with_prosody("こんにちは Hello")
        assert len(tokens_p) == len(prosody)

    @requires_ja
    @requires_zh
    def test_mixed_ja_zh(self):
        """CJK mixed text: Japanese with kana context disambiguates from Chinese."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-zh")
        # "東京は Tokyo 北京是 Beijing" -- kana は triggers JA context for CJK
        # Use a simpler example with clear kana to force JA detection:
        # "東京のラーメン 北京烤鸭" (no kana in 北京烤鸭 part, but global kana
        # context applies)
        tokens = p.phonemize("東京のラーメン")
        assert len(tokens) > 0

        # Pure Chinese text (no kana) should also work
        tokens_zh = p.phonemize("北京是首都")
        assert len(tokens_zh) > 0

        # Prosody alignment
        tokens_p, prosody = p.phonemize_with_prosody("東京のラーメン")
        assert len(tokens_p) == len(prosody)

    @requires_ja
    @requires_en
    @requires_zh
    def test_mixed_three_languages(self):
        """Three-language mixed text (JA + EN + ZH) is phonemized correctly."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en-zh")
        # "こんにちは Hello 你好" -- JA kana + EN Latin + ZH ideographs
        # With kana present, CJK ideographs will be detected as JA, but
        # the phonemizer should still produce valid output for all segments.
        tokens = p.phonemize("こんにちは Hello 你好")
        assert len(tokens) > 0

        tokens_p, prosody = p.phonemize_with_prosody("こんにちは Hello 你好")
        assert len(tokens_p) == len(prosody)

    @requires_ja
    @requires_en
    def test_mixed_en_es_fr(self):
        """Three Latin-script languages: EN is default_latin, ES/FR are rule-based."""
        from piper_plus_g2p.registry import get_phonemizer

        # ES and FR are rule-based (always available). EN requires g2p-en.
        p = get_phonemizer("en-es-fr")
        # Latin text defaults to EN (highest priority in _LATIN_PRIORITY)
        tokens = p.phonemize("Hello world")
        assert len(tokens) > 0

    @requires_ja
    def test_single_language_in_multilingual_ja(self):
        """Single-language JA text through a multilingual phonemizer."""
        from piper_plus_g2p.registry import get_phonemizer

        try:
            p = get_phonemizer("ja-en")
        except ValueError:
            pytest.skip("ja and/or en phonemizers not registered")
        tokens = p.phonemize("今日は良い天気ですね")
        assert len(tokens) > 0

        tokens_p, prosody = p.phonemize_with_prosody("今日は良い天気ですね")
        assert len(tokens_p) == len(prosody)

    @requires_en
    def test_single_language_in_multilingual_en(self):
        """Single-language EN text through a multilingual phonemizer."""
        from piper_plus_g2p.registry import get_phonemizer

        # ES is rule-based (always available), EN requires g2p-en
        p = get_phonemizer("en-es")
        tokens = p.phonemize("This is a test sentence.")
        assert len(tokens) > 0

        tokens_p, prosody = p.phonemize_with_prosody("This is a test sentence.")
        assert len(tokens_p) == len(prosody)

    def test_single_language_in_multilingual_es(self):
        """Single-language ES text through a multilingual phonemizer (rule-based)."""
        from piper_plus_g2p.registry import get_phonemizer

        # ES, FR, PT are all rule-based -- no external dependency
        p = get_phonemizer("es-fr")
        tokens = p.phonemize("Hola mundo")
        assert len(tokens) > 0

    def test_empty_string_multilingual(self):
        """Empty string returns empty token list."""
        from piper_plus_g2p.registry import get_phonemizer

        # ES and PT are rule-based (always available)
        p = get_phonemizer("es-pt")
        tokens = p.phonemize("")
        assert tokens == []

        tokens_p, prosody = p.phonemize_with_prosody("")
        assert tokens_p == []
        assert prosody == []

    def test_whitespace_only_multilingual(self):
        """Whitespace-only string returns empty token list."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("es-pt")
        tokens = p.phonemize("   ")
        assert tokens == []

        tokens_p, prosody = p.phonemize_with_prosody("   ")
        assert tokens_p == []
        assert prosody == []

    @requires_ja
    @requires_en
    def test_mixed_ja_en_prosody_alignment(self):
        """Prosody alignment holds for multi-segment JA+EN text."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        # Multiple switches: JA -> EN -> JA
        text = "東京タワーはTokyoTowerと呼ばれています"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )


class TestMultilingualProsodyPunctuation:
    """Tests for prosody and punctuation handling in mixed-language text."""

    @requires_ja
    @requires_en
    def test_punctuation_mixed_ja_en_zh_sentence(self):
        """Punctuated mixed text: JA period + EN comma/exclamation."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        text = "こんにちは。Hello, world!"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0, "Should produce phoneme tokens"
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    @requires_ja
    @requires_en
    @requires_zh
    def test_punctuation_mixed_three_lang(self):
        """Punctuated mixed text across three languages: JA + EN + ZH."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en-zh")
        # Note: With kana present, CJK ideographs are detected as JA,
        # but the phonemizer still produces valid output.
        text = "こんにちは。Hello, world! 你好。"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    @requires_ja
    @requires_en
    def test_language_switch_boundary_prosody(self):
        """Prosody features at language switch boundaries are well-formed."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        text = "東京のTokyo Tower"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) == len(prosody)

        # JA segment should have ProsodyInfo entries (a1/a2/a3 from OpenJTalk)
        ja_prosody = [pr for pr in prosody if isinstance(pr, ProsodyInfo)]
        assert len(ja_prosody) > 0, "JA segment should produce ProsodyInfo entries"

        # Every prosody entry must be either ProsodyInfo or None
        for i, pr in enumerate(prosody):
            assert pr is None or isinstance(pr, ProsodyInfo), (
                f"prosody[{i}] is {type(pr).__name__}, expected ProsodyInfo or None"
            )

    @requires_ja
    @requires_en
    def test_question_mark_mixed_ja_en(self):
        """Question marks in mixed JA-EN text: JA '？' + EN '?'."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        text = "これは何？What is this?"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    @requires_ja
    @requires_en
    def test_question_mark_ja_produces_marker(self):
        """JA segment with '？' should produce a question marker token."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        # Pure JA question through multilingual phonemizer
        text = "これは何ですか？"
        tokens = p.phonemize(text)
        # JA question markers: bare "?" for standard questions,
        # or extended markers "?!", "?.", "?~" for specific types.
        question_markers = {"?", "?!", "?.", "?~"}
        has_question = any(t in question_markers for t in tokens)
        assert has_question, (
            f"Expected a question marker token in {tokens}, "
            f"but none of {question_markers} found"
        )

    @requires_ja
    @requires_en
    def test_prosody_valid_for_en_segment(self):
        """EN segments should have valid prosody entries (ProsodyInfo or None)."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        # Pure EN through multilingual phonemizer
        text = "Hello world"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
        # EN phonemizer returns ProsodyInfo with a1=0, a2=stress, a3=word length.
        # Every entry must be either ProsodyInfo or None.
        for i, pr in enumerate(prosody):
            assert pr is None or isinstance(pr, ProsodyInfo), (
                f"prosody[{i}]: expected ProsodyInfo|None, got {type(pr).__name__}"
            )

    @requires_ja
    @requires_en
    def test_mixed_multiple_switches_prosody(self):
        """Multiple JA-EN-JA switches maintain prosody alignment."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        text = "今日はGood morningですね"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)

        # Should have both ProsodyInfo (from JA) and None (from EN)
        has_prosody_info = any(isinstance(pr, ProsodyInfo) for pr in prosody)
        has_none = any(pr is None for pr in prosody)
        assert has_prosody_info, "JA segments should contribute ProsodyInfo"
        assert has_none, "EN segment should contribute None prosody"

    @requires_ja
    @requires_en
    def test_exclamation_mixed(self):
        """Exclamation marks in mixed text do not break prosody alignment."""
        from piper_plus_g2p.registry import get_phonemizer

        p = get_phonemizer("ja-en")
        text = "すごい！Amazing!"
        tokens, prosody = p.phonemize_with_prosody(text)
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
