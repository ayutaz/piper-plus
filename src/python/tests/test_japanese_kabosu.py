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
        apply_yomikata,
    )

    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False

# Check if yomikata is available
try:
    from yomikata.dbert import dBert

    HAS_YOMIKATA = True
except ImportError:
    HAS_YOMIKATA = False

try:
    from piper_train.phonemize import phonemize_japanese

    HAS_PHONEMIZE = True
except ImportError:
    HAS_PHONEMIZE = False

# Check if jpreprocess is available for Phase 3 tests
try:
    from jpreprocess import JPreprocess

    HAS_JPREPROCESS = True
except ImportError:
    HAS_JPREPROCESS = False


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


@pytest.mark.skipif(
    not HAS_UTILS or not HAS_YOMIKATA,
    reason="japanese_utils or yomikata not available"
)
class TestYomikataIntegration:
    """Test BERT-based reading disambiguation (Phase 2)."""

    def test_apply_yomikata_heteronym(self):
        """Test yomikata with ambiguous kanji (heteronym)."""
        # 表 can be read as おもて (surface) or ひょう (table)
        # In context "畳の表", it should be おもて (tatami surface)
        text = "畳の表"
        result = apply_yomikata(text)
        # Should convert 表 to オモテ (katakana)
        assert "オモテ" in result or "おもて" in result

    def test_apply_yomikata_multiple_heteronyms(self):
        """Test yomikata with multiple ambiguous kanji."""
        # Test text from kabosu-core test suite
        text = "そして、畳の表は、すでに幾年前に換えられたのか分らなかった。"
        result = apply_yomikata(text)
        # Should disambiguate 表
        assert isinstance(result, str)
        assert len(result) > 0

    def test_apply_yomikata_no_heteronyms(self):
        """Test yomikata with text containing no ambiguous kanji."""
        text = "こんにちは、世界"
        result = apply_yomikata(text)
        # Should return without changes (or minimal changes)
        assert isinstance(result, str)

    def test_preprocess_with_yomikata_enabled(self):
        """Test preprocessing pipeline with yomikata enabled."""
        text = "畳の表は美しい"
        result = preprocess_japanese_text(text, use_yomikata=True)
        # Should apply yomikata processing
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preprocess_with_yomikata_disabled(self):
        """Test preprocessing pipeline with yomikata disabled."""
        text = "畳の表は美しい"
        result = preprocess_japanese_text(text, use_yomikata=False)
        # Should skip yomikata processing
        assert isinstance(result, str)
        # 表 should remain unchanged
        assert "表" in result

    def test_yomikata_with_variant_kanji(self):
        """Test yomikata works correctly after variant kanji normalization."""
        # Variant kanji should be normalized before yomikata processing
        text = "齋藤さんの畳の表"
        result = preprocess_japanese_text(
            text,
            normalize_variants=True,
            use_yomikata=True
        )
        # 齋 should be normalized to 斎
        assert "齋" not in result
        assert "斎" in result
        # 表 should be disambiguated
        assert isinstance(result, str)


@pytest.mark.skipif(
    not HAS_PHONEMIZE or not HAS_YOMIKATA,
    reason="phonemize_japanese or yomikata not available"
)
class TestYomikataPhoneDization:
    """Test phonemization with yomikata integration."""

    def test_phonemize_with_yomikata(self):
        """Test that yomikata-preprocessed text phonemizes correctly."""
        # Text with ambiguous kanji
        result = phonemize_japanese("畳の表", use_kabosu_preprocessing=True)

        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

        # Should start with beginning marker
        assert result[0] in ["^", "\ue000"]


@pytest.mark.skipif(
    not HAS_UTILS or not HAS_JPREPROCESS,
    reason="japanese_utils or jpreprocess not available",
)
class TestAdvancedPostprocessing:
    """Test advanced postprocessing functions (Phase 3)."""

    def test_retreat_acc_nuc(self):
        """Test accent nucleus adjustment for long vowels."""
        # Test with text containing long vowel mark
        text = "ラーメン"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_modify_acc_after_chaining(self):
        """Test conjugation accent correction for masu form."""
        # Test with masu verb form
        text = "書きます"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_process_odori_features_single_kanji(self):
        """Test iteration mark processing for single kanji."""
        # Test with 々 (odoriji)
        text = "叙々苑"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_process_odori_features_multiple_kanji(self):
        """Test iteration mark processing for multiple kanji."""
        # Test with 々 after multiple kanji
        text = "民主々義"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_process_repetition_marks(self):
        """Test repetition mark processing (ゝ, ゞ, ヽ, ヾ)."""
        # Test with repetition marks
        text = "こゝろ"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_advanced_postprocessing_disabled(self):
        """Test that phonemization works when advanced postprocessing is disabled."""
        text = "叙々苑"
        result = phonemize_japanese(text, use_advanced_postprocessing=False)
        # Should still work
        assert isinstance(result, list)
        assert len(result) > 0

    def test_integrated_preprocessing_and_postprocessing(self):
        """Test that both preprocessing and postprocessing work together."""
        # Text with variant kanji, English, and iteration marks
        text = "齋藤さんはdockerを使って叙々苑に行きます"
        result = phonemize_japanese(
            text,
            use_kabosu_preprocessing=True,
            use_advanced_postprocessing=True,
        )
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_modify_filler_accent(self):
        """Test filler accent modification."""
        # Test with filler word (えー, あのー, etc.)
        # Note: Direct testing requires jpreprocess to mark as フィラー
        text = "えーと、それは違います"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_modify_kanji_yomi_kaze(self):
        """Test multi-reading kanji disambiguation (風 = kaze/fū)."""
        # 風 in "風が強い" should be "カゼ" (wind, not style)
        text = "風が強い"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0
        # Note: Actual reading verification would require inspecting NJD features

    def test_modify_kanji_yomi_nani(self):
        """Test multi-reading kanji disambiguation (何 = nani/nan)."""
        # 何 should be disambiguated using ONNX model
        text = "何ですか"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0

    def test_complete_phase3_pipeline(self):
        """Test all Phase 3 functions work together in correct order."""
        # Text that exercises all Phase 3 functions:
        # - Long vowels (ラーメン)
        # - Iteration marks (叙々苑)
        # - Masu form (行きます)
        text = "ラーメン屋の叙々苑に行きます"
        result = phonemize_japanese(text, use_advanced_postprocessing=True)
        # Should return phoneme tokens
        assert isinstance(result, list)
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
