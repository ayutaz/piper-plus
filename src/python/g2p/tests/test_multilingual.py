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

    def test_unicode_detector_hangul_compat_jamo(self):
        """UnicodeLanguageDetector classifies Hangul Compat Jamo (U+3130-U+318F)
        as Korean.

        Regression for the previously-unclear branch ordering: the Compat
        Jamo block sits inside the U+3040-U+31FF kana super-range, but must
        be routed to "ko" rather than "ja" or None.
        """
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en", "ko"], default_latin_language="en"
        )
        # Boundaries and a representative character in the middle.
        assert detector.detect_char("\u3130") == "ko"  # block start
        assert detector.detect_char("\u3131") == "ko"  # \u3131 (kiyeok)
        assert detector.detect_char("\u3134") == "ko"  # \u3134 (nieun)
        assert detector.detect_char("\u3137") == "ko"  # \u3137 (tikeut)
        assert detector.detect_char("\u3147") == "ko"  # \u3147 (ieung)
        assert detector.detect_char("\u318f") == "ko"  # block end

    def test_unicode_detector_hangul_compat_jamo_no_ko(self):
        """Compat Jamo returns None when Korean is not in the language set."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("\u3131") is None
        assert detector.detect_char("\u3147") is None

    def test_unicode_detector_kana_still_works_after_compat_jamo_hoist(self):
        """Hoisting the Compat Jamo branch must not regress kana detection."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "en", "ko"], default_latin_language="en"
        )
        # Hiragana and Katakana proper still map to JA.
        assert detector.detect_char("\u3042") == "ja"  # \u3042
        assert detector.detect_char("\u30a2") == "ja"  # \u30a2
        # Katakana Phonetic Extensions (U+31F0-U+31FF) still map to JA.
        assert detector.detect_char("\u31f0") == "ja"
        assert detector.detect_char("\u31ff") == "ja"
        # Bopomofo / Hangul Jamo Extended-A in the same super-range stay
        # neutral (None).
        assert detector.detect_char("\u3100") is None  # Bopomofo block start
        assert detector.detect_char("\u312f") is None  # Bopomofo end
        assert detector.detect_char("\u3190") is None  # Kanbun start

    def test_segment_compat_jamo_only(self):
        """Pure Hangul Compat Jamo input segments to a single 'ko' chunk."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        # Use ko + a rule-based language so we don't require g2pk2 to instantiate.
        p = MultilingualPhonemizer(["ko", "es"], default_latin_language="es")
        segments = p.segment_text("\u3131\u3134\u3137")  # \u3131\u3134\u3137
        assert len(segments) == 1
        assert segments[0]["language"] == "ko"
        assert segments[0]["text"] == "\u3131\u3134\u3137"

    def test_segment_hangul_syllable_plus_compat_jamo(self):
        """Hangul Syllable + Compat Jamo merges into one 'ko' segment."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ko", "es"], default_latin_language="es")
        segments = p.segment_text("\ud55c\u3131")  # \ud55c\u3131
        assert len(segments) == 1
        assert segments[0]["language"] == "ko"
        assert segments[0]["text"] == "\ud55c\u3131"

    def test_segment_compat_jamo_plus_latin(self):
        """Compat Jamo followed by Latin produces two correctly-typed segments."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ko", "es"], default_latin_language="es")
        segments = p.segment_text("\u3131hola")  # \u3131hola
        assert len(segments) == 2
        assert segments[0]["language"] == "ko"
        assert segments[0]["text"] == "\u3131"
        assert segments[1]["language"] == "es"
        assert segments[1]["text"] == "hola"

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


class TestFullwidthDetection:
    """Regression / behavior-pinning tests for fullwidth (U+FF00-FFEF) chars.

    The current implementation routes U+FF21-FF3A and U+FF41-FF5A
    (fullwidth ASCII letters) to ``default_latin_language``, but routes
    fullwidth digits (U+FF10-FF19) and fullwidth ASCII punctuation
    (U+FF00-FF20, U+FF3B-FF40, U+FF5B-FFEF) to "ja" when JA is present
    (otherwise None). These tests pin that behavior so an accidental
    routing change is caught by CI.

    See ``UnicodeLanguageDetector.detect_char`` in
    ``piper_plus_g2p/multilingual.py``. Some of these assertions encode
    behavior that arguably should be revisited (e.g. fullwidth digits
    routed to JA inside a JA-EN-ZH detector) — those cases are flagged
    via ``xfail(strict=False)`` and listed under "Future Work" in the
    accompanying PR description so the next contributor can decide
    whether to keep, tighten, or relax the contract.
    """

    def test_fullwidth_uppercase_letters_map_to_default_latin(self):
        """U+FF21-FF3A (ＡＢＣ...) routes to default_latin_language."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        # Boundaries (FF21=Ａ, FF3A=Ｚ) and a representative middle (FF23=Ｃ).
        assert detector.detect_char("Ａ") == "en"
        assert detector.detect_char("Ｃ") == "en"
        assert detector.detect_char("Ｚ") == "en"

    def test_fullwidth_lowercase_letters_map_to_default_latin(self):
        """U+FF41-FF5A (ａｂｃ...) routes to default_latin_language."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("ａ") == "en"
        assert detector.detect_char("ｃ") == "en"
        assert detector.detect_char("ｚ") == "en"

    def test_fullwidth_letters_respect_default_latin_when_not_en(self):
        """When default_latin_language='es', fullwidth letters route to 'es'."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "es"], default_latin_language="es")
        assert detector.detect_char("Ａ") == "es"
        assert detector.detect_char("ｚ") == "es"

    def test_fullwidth_letters_none_when_no_supported_latin(self):
        """Fullwidth letters return None when no Latin language is supported."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        # default_latin_language defaults to 'en'; with only ['ja'] supported
        # the pre-computed _default_latin is None.
        detector = UnicodeLanguageDetector(["ja"], default_latin_language="en")
        assert detector.detect_char("Ａ") is None
        assert detector.detect_char("ａ") is None

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Fullwidth digits (U+FF10-FF19) currently route to 'ja' when JA is "
            "present, but they are language-neutral semantically (just like "
            "ASCII digits which return None). Future Work: consider returning "
            "None to be consistent with ASCII digit handling."
        ),
    )
    def test_fullwidth_digits_should_be_neutral(self):
        """Future Work: fullwidth digits ideally return None like ASCII digits."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        # Currently returns "ja". Marked xfail so when the implementation is
        # tightened this flips to xpass and the contract update lands.
        assert detector.detect_char("０") is None  # １
        assert detector.detect_char("５") is None  # ５
        assert detector.detect_char("９") is None  # ９

    def test_fullwidth_digits_current_behavior(self):
        """Pin the *current* fullwidth digit behavior (route to JA when JA in set)."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector_ja = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        # With JA in language set: fullwidth digits route to 'ja'.
        assert detector_ja.detect_char("０") == "ja"
        assert detector_ja.detect_char("９") == "ja"

        # Without JA in language set: fullwidth digits return None.
        detector_no_ja = UnicodeLanguageDetector(
            ["en", "zh"], default_latin_language="en"
        )
        assert detector_no_ja.detect_char("０") is None
        assert detector_no_ja.detect_char("９") is None

    def test_fullwidth_punctuation_routes_to_ja(self):
        """U+FF01 (！), U+FF3B ([)、U+FF5E (~) route to 'ja' when JA supported."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        # Fullwidth ! (FF01), [ (FF3B), ~ (FF5E) all map to 'ja'.
        assert detector.detect_char("！") == "ja"
        assert detector.detect_char("［") == "ja"
        assert detector.detect_char("～") == "ja"

    def test_fullwidth_mixed_segment_with_jp_context(self):
        """Fullwidth ＡＢＣ inside JA text is segmented into a 'en' chunk."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en"], default_latin_language="en")
        # こんにちはＡＢＣさん -> [ja, en, ja]
        segments = p.segment_text("こんにちはＡＢＣさん")
        languages = [s["language"] for s in segments]
        assert "en" in languages, f"Expected an 'en' segment, got {languages}"
        assert "ja" in languages, f"Expected a 'ja' segment, got {languages}"

    def test_fullwidth_only_text_segments_cleanly(self):
        """Pure fullwidth letter input segments to a single Latin chunk."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en"], default_latin_language="en")
        segments = p.segment_text("ＡＢＣａｂｃ")
        assert len(segments) == 1
        assert segments[0]["language"] == "en"


class TestSurrogateAndEmojiHandling:
    """Behavior pinning for emoji / non-BMP characters.

    Single-character emoji (U+1F600, etc.) and BMP variation selectors
    (U+FE0F, ZWJ, skin-tone modifiers) all return None from detect_char
    because they fall outside the explicit Unicode ranges in
    ``detect_char``. The phonemizer must not crash when emoji appear in
    input — they should be silently absorbed into the surrounding
    segment (neutral-char absorption rule).
    """

    def test_detect_char_emoji_returns_none(self):
        """Single emoji codepoints are neutral (return None)."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("\U0001f600") is None  # 😀
        assert detector.detect_char("\U0001f602") is None  # 😂
        assert detector.detect_char("\U0001f680") is None  # 🚀

    def test_detect_char_emoji_modifiers_return_none(self):
        """Variation selectors, ZWJ, skin-tone modifiers are neutral."""
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("️") is None  # VS-16
        assert detector.detect_char("‍") is None  # ZWJ
        assert detector.detect_char("\U0001f3fb") is None  # skin tone 1

    def test_emoji_only_text_does_not_crash(self):
        """Pure emoji input must not raise; produces empty or default segment."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        # ES is rule-based -> no external phonemizer dependency required.
        p = MultilingualPhonemizer(["es", "pt"], default_latin_language="es")
        # No exception, and segment_text falls back to default language.
        segments = p.segment_text("\U0001f600\U0001f602\U0001f680")
        assert isinstance(segments, list)
        # Emoji-only phonemize: tokens may be empty, but must not raise.
        tokens = p.phonemize("\U0001f600\U0001f602\U0001f680")
        assert isinstance(tokens, list)

    def test_emoji_mixed_with_latin_text(self):
        """Emoji absorbed into surrounding Latin segment without crash."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["es", "pt"], default_latin_language="es")
        # Latin + emoji + Latin should still produce phonemes.
        tokens = p.phonemize("Hola \U0001f600 mundo")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    @requires_ja
    def test_emoji_mixed_with_japanese_text(self):
        """Emoji in JA text: no crash, JA portion still phonemized."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en"], default_latin_language="en")
        tokens = p.phonemize("こんにちは\U0001f600世界")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_utf16_surrogate_pair_safe(self):
        """UTF-16 surrogate codepoints (when input as a 2-char string) do not crash.

        Python 3 strings are stored as code points (not UTF-16 code units),
        but it is possible to construct a string containing lone surrogates
        via ``chr(0xD83D)``. detect_char must accept these without raising.
        """
        from piper_plus_g2p.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        # Lone high/low surrogates are neutral (return None).
        assert detector.detect_char("\ud83d") is None
        assert detector.detect_char("\ude00") is None


class TestLongMultilineText:
    """Behavior pinning for ~1000-char multi-line / mixed-language input.

    The language splitter should:
    1. Not crash on newlines / tabs / large inputs.
    2. Detect multiple language segments consistently across the text.
    3. Treat whitespace (including \\n, \\t) as neutral and absorb into
        the surrounding segment per the existing contract.
    """

    def _build_long_text(self) -> str:
        """Build ~1000-char text with newlines, tabs, JA, EN, ZH."""
        unit = "こんにちは\nHello world\tTesting.\n你好。"
        # 30 repetitions * ~30 chars = ~900 chars
        return unit * 30

    def test_long_text_does_not_crash(self):
        """Detector and segmenter handle ~1000-char multi-line input."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en", "zh"], default_latin_language="en")
        text = self._build_long_text()
        assert len(text) >= 800
        segments = p.segment_text(text)
        assert isinstance(segments, list)
        assert len(segments) > 1, (
            "Expected multiple segments in a long multilingual text; "
            f"got {len(segments)}"
        )

    def test_long_text_segments_contain_multiple_languages(self):
        """Segmenter detects at least two distinct languages in long mixed text."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en", "zh"], default_latin_language="en")
        text = self._build_long_text()
        segments = p.segment_text(text)
        languages = {s["language"] for s in segments}
        # JA kana definitely present; EN Latin definitely present.
        # ZH ideographs may be re-routed to JA under kana context (current
        # CJK disambiguation rule). At minimum 2 languages must appear.
        assert len(languages) >= 2, f"Expected >=2 languages, got {languages}"
        assert "ja" in languages
        assert "en" in languages

    def test_long_text_preserves_input_characters(self):
        """Concatenating all segment text reproduces the input verbatim."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en", "zh"], default_latin_language="en")
        text = self._build_long_text()
        segments = p.segment_text(text)
        joined = "".join(s["text"] for s in segments)
        assert joined == text, (
            "Segment concatenation must be byte-for-byte identical to input "
            "(newlines, tabs, and punctuation must be preserved)"
        )

    @requires_ja
    @requires_en
    def test_long_text_phonemize_does_not_crash(self):
        """phonemize() on long multi-line JA-EN text completes and returns tokens."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ja", "en"], default_latin_language="en")
        unit = "こんにちは\nHello world\tTesting.\n"
        text = unit * 30
        tokens = p.phonemize(text)
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_pure_whitespace_long_text_returns_empty(self):
        """A long whitespace-only input returns an empty token list."""
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["es", "pt"], default_latin_language="es")
        text = " \n\t" * 400  # ~1200 chars of whitespace
        tokens = p.phonemize(text)
        assert tokens == []


class TestKoreanG2pk2Unavailable:
    """Behavior when ``g2pk2`` is not importable (fallback contract).

    The current implementation raises ``ImportError`` when ``g2pk2`` is
    missing and Korean phonemization is attempted. These tests pin that
    behavior. A graceful fallback (e.g. raw Hangul → IPA via syllable
    decomposition without g2pk2 phonological rules) would arguably be
    nicer; that is marked as "Future Work" via ``xfail(strict=False)``.
    """

    def _block_g2pk2(self, monkeypatch):
        """Force ``import g2pk2`` to raise ImportError, and reset cache."""
        import builtins

        from piper_plus_g2p import korean

        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "g2pk2":
                raise ImportError("simulated: g2pk2 not installed")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # Reset module-level cache so the patched import is reached.
        monkeypatch.setattr(korean, "_g2p_instance", None, raising=False)
        monkeypatch.setattr(korean, "_g2p_unavailable", False, raising=False)

    def test_korean_phonemizer_raises_when_g2pk2_missing(self, monkeypatch):
        """Pure-Hangul input through KoreanPhonemizer raises ImportError."""
        self._block_g2pk2(monkeypatch)
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        with pytest.raises(ImportError, match="g2pk2"):
            ph.phonemize("안녕하세요")  # 안녕하세요

    def test_multilingual_ko_segment_raises_when_g2pk2_missing(self, monkeypatch):
        """Mixed KO+Latin via MultilingualPhonemizer also raises ImportError."""
        self._block_g2pk2(monkeypatch)
        from piper_plus_g2p.multilingual import MultilingualPhonemizer

        p = MultilingualPhonemizer(["ko", "en"], default_latin_language="en")
        with pytest.raises(ImportError, match="g2pk2"):
            p.phonemize("Hello 안녕")  # Hello 안녕

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Future Work: when g2pk2 is unavailable, KoreanPhonemizer ideally "
            "falls back to raw Hangul syllable decomposition (skipping g2pk2 "
            "phonological rules) so that mixed-script text does not entirely "
            "fail at runtime. Today it raises ImportError, which propagates "
            "out of MultilingualPhonemizer."
        ),
    )
    def test_korean_graceful_fallback_future_work(self, monkeypatch):
        """Future Work: graceful fallback when g2pk2 missing (currently raises)."""
        self._block_g2pk2(monkeypatch)
        from piper_plus_g2p.korean import KoreanPhonemizer

        ph = KoreanPhonemizer()
        # Desired future contract: returns *something* (raw IPA from jamo
        # decomposition) instead of raising.
        tokens = ph.phonemize("안녕")  # 안녕
        assert isinstance(tokens, list)
        assert len(tokens) > 0
