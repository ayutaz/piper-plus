"""Tests for kabosu-core integration features in Japanese phonemization.

This test suite validates the enhanced Japanese preprocessing features
from kabosu-core integration, including:
- Variant kanji normalization
- English to Katakana conversion
- Half-width to full-width conversion
- Integrated preprocessing pipeline
"""

import pytest

# Test imports
from piper_train.phonemize.itaiji import normalize_itaiji

# These imports are optional - tests will be skipped if not available
try:
    from piper_train.phonemize.japanese_utils import (
        convert_english_to_katakana,
        convert_half_to_full,
        preprocess_japanese_text,
    )

    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False

try:
    from piper_train.phonemize import phonemize_japanese

    HAS_PHONEMIZE = True
except ImportError:
    HAS_PHONEMIZE = False


class TestVariantKanjiNormalization:
    """Test variant kanji (異体字) normalization."""

    def test_jinmei_variants(self):
        """Test personal name kanji variants."""
        # 齋 → 斎
        assert normalize_itaiji("齋藤") == "斎藤"
        # 邊 → 辺
        assert normalize_itaiji("邊") == "辺"

    def test_joyo_variants(self):
        """Test standard kanji variants."""
        # Tests depend on dictionary content
        # Basic sanity check
        text = "常用漢字"
        result = normalize_itaiji(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_itaiji("") == ""

    def test_no_variants(self):
        """Test text with no variants returns unchanged."""
        text = "こんにちは、世界"
        assert normalize_itaiji(text) == text

    def test_mixed_text(self):
        """Test text with mixed variants and normal characters."""
        # Should only replace variants
        text = "齋藤さんは東京に住んでいます"
        result = normalize_itaiji(text)
        assert "齋" not in result
        assert "斎" in result
        assert "東京" in result


@pytest.mark.skipif(not HAS_UTILS, reason="japanese_utils not available")
class TestHalfWidthConversion:
    """Test half-width to full-width character conversion."""

    def test_halfwidth_katakana(self):
        """Test half-width Katakana conversion."""
        assert convert_half_to_full("ｱｲｳｴｵ") == "アイウエオ"

    def test_halfwidth_numbers(self):
        """Test half-width number conversion."""
        result = convert_half_to_full("123")
        # Should convert to full-width
        assert result == "１２３"

    def test_mixed_halfwidth(self):
        """Test mixed half-width content."""
        text = "ｶﾀｶﾅ123ABC"
        result = convert_half_to_full(text)
        # All should be full-width
        assert "ｶ" not in result
        assert "カ" in result


@pytest.mark.skipif(not HAS_UTILS, reason="japanese_utils not available")
class TestEnglishToKatakana:
    """Test English to Katakana conversion using kanalizer."""

    def test_simple_word(self):
        """Test simple English word conversion."""
        assert convert_english_to_katakana("docker") == "ドッカー"

    def test_word_in_sentence(self):
        """Test English word within Japanese sentence."""
        result = convert_english_to_katakana("dockerを使います")
        assert "docker" not in result.lower()
        assert "ドッカー" in result

    def test_multiple_words(self):
        """Test multiple English words."""
        result = convert_english_to_katakana("github and docker")
        assert "github" not in result.lower()
        assert "docker" not in result.lower()
        # Should contain Katakana equivalents
        assert "ギ" in result or "ド" in result

    def test_uppercase(self):
        """Test uppercase English words."""
        result = convert_english_to_katakana("DOCKER")
        assert "DOCKER" not in result
        assert "ドッカー" in result

    def test_no_english(self):
        """Test text with no English returns unchanged."""
        text = "日本語のテキスト"
        assert convert_english_to_katakana(text) == text


@pytest.mark.skipif(not HAS_UTILS, reason="japanese_utils not available")
class TestPreprocessJapaneseText:
    """Test integrated Japanese text preprocessing pipeline."""

    def test_all_preprocessing(self):
        """Test all preprocessing steps combined."""
        # Text with variants, English, and half-width
        text = "齋藤さんはdockerを使います"
        result = preprocess_japanese_text(text)

        # Variant should be normalized
        assert "齋" not in result
        assert "斎" in result

        # English should be converted
        assert "docker" not in result.lower()
        assert "ドッカー" in result

    def test_disable_variant_normalization(self):
        """Test preprocessing with variant normalization disabled."""
        text = "齋藤"
        result = preprocess_japanese_text(text, normalize_variants=False)
        assert "齋" in result

    def test_disable_english_conversion(self):
        """Test preprocessing with English conversion disabled."""
        text = "dockerを使います"
        result = preprocess_japanese_text(text, convert_english=False)
        assert "docker" in result.lower()

    def test_empty_string(self):
        """Test empty string handling."""
        assert preprocess_japanese_text("") == ""


@pytest.mark.skipif(not HAS_PHONEMIZE, reason="phonemize_japanese not available")
class TestIntegratedPhonemization:
    """Test phonemization with kabosu-core preprocessing."""

    def test_phonemize_with_preprocessing(self):
        """Test phonemization with preprocessing enabled."""
        # Text with English word
        result = phonemize_japanese("dockerを使います", use_kabosu_preprocessing=True)

        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

        # Should start with beginning marker
        assert result[0] in ["^", "\ue000"]  # ^ or its PUA mapping

    def test_phonemize_without_preprocessing(self):
        """Test phonemization with preprocessing disabled."""
        result = phonemize_japanese(
            "こんにちは", use_kabosu_preprocessing=False
        )

        # Should still work
        assert isinstance(result, list)
        assert len(result) > 0

    def test_variant_kanji_phonemization(self):
        """Test that variant kanji are properly phonemized."""
        # 齋藤 should be normalized to 斎藤 before phonemization
        result_variant = phonemize_japanese("齋藤", use_kabosu_preprocessing=True)
        result_standard = phonemize_japanese("斎藤", use_kabosu_preprocessing=True)

        # Both should produce same phonemes (modulo boundary markers)
        # Remove boundary markers for comparison
        variant_phonemes = [p for p in result_variant if p not in ["^", "$", "?", "\ue000", "\ue001", "\ue002"]]
        standard_phonemes = [p for p in result_standard if p not in ["^", "$", "?", "\ue000", "\ue001", "\ue002"]]

        assert variant_phonemes == standard_phonemes


@pytest.mark.skipif(not HAS_UTILS, reason="japanese_utils not available")
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_long_text(self):
        """Test preprocessing with very long text."""
        text = "あいうえお" * 1000
        result = preprocess_japanese_text(text)
        assert len(result) == len(text)

    def test_special_characters(self):
        """Test preprocessing with special characters."""
        text = "Hello！？、。・"
        result = preprocess_japanese_text(text)
        assert isinstance(result, str)

    def test_mixed_scripts(self):
        """Test text with multiple scripts."""
        text = "Hello世界こんにちはworld"
        result = preprocess_japanese_text(text)
        # Should handle gracefully
        assert isinstance(result, str)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
