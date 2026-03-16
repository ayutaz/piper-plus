"""Tests for multilingual phonemizer (N-language support)."""

import pytest


# ---------------------------------------------------------------------------
# UnicodeLanguageDetector tests
# ---------------------------------------------------------------------------


class TestUnicodeLanguageDetector:
    """Tests for Unicode-based language detection."""

    def test_detect_hiragana_as_japanese(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        assert detector.detect_char("あ") == "ja"
        assert detector.detect_char("ん") == "ja"

    def test_detect_katakana_as_japanese(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        assert detector.detect_char("ア") == "ja"
        assert detector.detect_char("ン") == "ja"

    def test_detect_hangul_as_korean(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en", "ko"])
        assert detector.detect_char("한") == "ko"
        assert detector.detect_char("글") == "ko"

    def test_detect_cjk_with_kana_context_as_japanese(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        # CJK ideograph with kana context → Japanese
        assert detector.detect_char("漢", context_has_kana=True) == "ja"

    def test_detect_cjk_without_kana_context_as_chinese(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        # CJK ideograph without kana context → Chinese
        assert detector.detect_char("漢", context_has_kana=False) == "zh"

    def test_detect_latin_as_default(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
        assert detector.detect_char("h") == "en"
        assert detector.detect_char("A") == "en"

    def test_detect_latin_custom_default(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(
            ["ja", "es", "fr"], default_latin_language="es"
        )
        assert detector.detect_char("h") == "es"

    def test_detect_neutral_returns_none(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "en"])
        assert detector.detect_char(" ") is None
        assert detector.detect_char("1") is None
        assert detector.detect_char(",") is None

    def test_has_kana(self):
        from piper_train.phonemize.multilingual import UnicodeLanguageDetector

        detector = UnicodeLanguageDetector(["ja", "zh"])
        assert detector.has_kana("漢字をかく") is True
        assert detector.has_kana("漢字") is False


# ---------------------------------------------------------------------------
# _segment_text_multilingual tests
# ---------------------------------------------------------------------------


class TestSegmentTextMultilingual:
    """Tests for N-language text segmentation."""

    def test_pure_japanese(self):
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en"])
        segments = _segment_text_multilingual("こんにちは", detector)
        assert len(segments) == 1
        assert segments[0] == ("ja", "こんにちは")

    def test_pure_english(self):
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en"])
        segments = _segment_text_multilingual("hello world", detector)
        assert len(segments) == 1
        assert segments[0][0] == "en"

    def test_mixed_ja_en(self):
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en"])
        segments = _segment_text_multilingual("今日はgoodですね", detector)
        assert len(segments) == 3
        assert segments[0][0] == "ja"
        assert segments[1][0] == "en"
        assert segments[2][0] == "ja"

    def test_mixed_ja_en_zh(self):
        """Japanese text with CJK should be detected as Japanese due to kana."""
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        segments = _segment_text_multilingual("漢字をhelloで書く", detector)
        # "漢字を" → ja (kana in context), "hello" → en, "で書く" → ja
        assert len(segments) == 3
        assert segments[0][0] == "ja"
        assert segments[1][0] == "en"
        assert segments[2][0] == "ja"

    def test_chinese_only(self):
        """Pure CJK without kana → Chinese."""
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en", "zh"])
        segments = _segment_text_multilingual("你好世界", detector)
        assert len(segments) == 1
        assert segments[0][0] == "zh"

    def test_korean_text(self):
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en", "ko"])
        segments = _segment_text_multilingual("안녕하세요hello", detector)
        assert len(segments) == 2
        assert segments[0][0] == "ko"
        assert segments[1][0] == "en"

    def test_empty_text(self):
        from piper_train.phonemize.multilingual import (
            UnicodeLanguageDetector,
            _segment_text_multilingual,
        )

        detector = UnicodeLanguageDetector(["ja", "en"])
        assert _segment_text_multilingual("", detector) == []
        assert _segment_text_multilingual("   ", detector) == []


# ---------------------------------------------------------------------------
# MultilingualPhonemizer tests
# ---------------------------------------------------------------------------


class TestMultilingualPhonemizer:
    """Tests for the N-language phonemizer."""

    def test_ja_en_backward_compat(self):
        """MultilingualPhonemizer with ["ja","en"] should work like BilingualPhonemizer."""
        from piper_train.phonemize.multilingual import MultilingualPhonemizer

        mp = MultilingualPhonemizer(["ja", "en"])
        phonemes = mp.phonemize("こんにちは")
        assert len(phonemes) > 0

    def test_get_phoneme_id_map(self):
        from piper_train.phonemize.multilingual import MultilingualPhonemizer

        mp = MultilingualPhonemizer(["ja", "en"])
        id_map = mp.get_phoneme_id_map()
        assert id_map is not None
        assert len(id_map) > 0

    def test_prosody_alignment(self):
        from piper_train.phonemize.multilingual import MultilingualPhonemizer

        mp = MultilingualPhonemizer(["ja", "en"])
        phonemes, prosody = mp.phonemize_with_prosody("今日はgoodですね")
        assert len(phonemes) == len(prosody)

    def test_post_process_adds_bos_eos(self):
        from piper_train.phonemize.multilingual import MultilingualPhonemizer
        from piper_train.phonemize.token_mapper import register

        mp = MultilingualPhonemizer(["ja", "en"])
        id_map = mp.get_phoneme_id_map()

        a_sym = register("a")
        a_id = id_map[a_sym][0]

        result_ids, result_prosody = mp.post_process_ids([a_id], [None], id_map)
        bos_sym = register("^")
        eos_sym = register("$")
        bos_id = id_map[bos_sym][0]
        eos_id = id_map[eos_sym][0]
        assert result_ids[0] == bos_id
        assert result_ids[-1] == eos_id
        assert len(result_ids) == len(result_prosody)


# ---------------------------------------------------------------------------
# Backward compatibility with BilingualPhonemizer
# ---------------------------------------------------------------------------


class TestBilingualBackwardCompat:
    """Ensure BilingualPhonemizer still works as before."""

    def test_bilingual_is_subclass(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer
        from piper_train.phonemize.multilingual import MultilingualPhonemizer

        assert issubclass(BilingualPhonemizer, MultilingualPhonemizer)

    def test_bilingual_phonemize(self):
        from piper_train.phonemize.bilingual import BilingualPhonemizer

        bp = BilingualPhonemizer(["ja", "en"])
        phonemes = bp.phonemize("今日はgoodですね")
        assert len(phonemes) > 0

    def test_bilingual_id_map_uses_bilingual(self):
        """BilingualPhonemizer with ["ja","en"] should use get_bilingual_id_map."""
        from piper_train.phonemize.bilingual import BilingualPhonemizer
        from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map

        bp = BilingualPhonemizer(["ja", "en"])
        bp_map = bp.get_phoneme_id_map()
        bi_map = get_bilingual_id_map()
        assert bp_map == bi_map

    def test_segment_text_backward_compat(self):
        from piper_train.phonemize.bilingual import _segment_text

        segments = _segment_text("今日はgoodですね")
        assert len(segments) == 3
        assert segments[0][0] == "ja"
        assert segments[1][0] == "en"
        assert segments[2][0] == "ja"


# ---------------------------------------------------------------------------
# Registry combo support tests
# ---------------------------------------------------------------------------


class TestRegistryCombo:
    """Tests for multi-language combo registration."""

    def test_ja_en_registered(self):
        from piper_train.phonemize.registry import available_languages, get_phonemizer

        assert "ja-en" in available_languages()
        p = get_phonemizer("ja-en")
        assert p is not None

    def test_dynamic_combo_creation(self):
        """Multi-language combos should be created on demand."""
        from piper_train.phonemize.registry import get_phonemizer

        # ja-en is pre-registered, but the phonemizer should work
        p = get_phonemizer("ja-en")
        assert p is not None
        phonemes = p.phonemize("hello")
        assert len(phonemes) > 0

    def test_invalid_language_raises(self):
        from piper_train.phonemize.registry import get_phonemizer

        with pytest.raises(ValueError, match="Unsupported language"):
            get_phonemizer("xx")

    def test_invalid_combo_raises(self):
        from piper_train.phonemize.registry import get_phonemizer

        with pytest.raises(ValueError):
            get_phonemizer("ja-xx")
