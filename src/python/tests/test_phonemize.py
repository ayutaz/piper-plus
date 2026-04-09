"""
Unified phonemization tests - combines all phonemization testing
"""

import pytest

from piper_plus_g2p.encode.pua import (
    CHAR2TOKEN,
    TOKEN2CHAR,
    map_token,
)

# Shared helper from conftest.py (auto_eos=False → unconditional "$").
from conftest import HAS_JAPANESE_G2P as HAS_JAPANESE, phonemize_japanese  # noqa: E402


class TestPhonemization:
    """All phonemization tests in one place"""

    @pytest.mark.unit
    def test_token_mapper_pua_mappings(self):
        """Test PUA character mappings are correct"""
        # Critical mappings for Japanese
        assert TOKEN2CHAR["ch"] == "\ue00e"
        assert TOKEN2CHAR["ts"] == "\ue00f"
        assert TOKEN2CHAR["ky"] == "\ue006"

        # Verify bidirectional mapping
        for token, char in TOKEN2CHAR.items():
            assert CHAR2TOKEN[char] == token

    @pytest.mark.unit
    def test_map_token_on_sequence(self):
        """Test phoneme sequence mapping using map_token"""
        input_seq = ["k", "o", "n", "n", "i", "ch", "i", "w", "a"]
        mapped = [map_token(t) for t in input_seq]

        # "ch" should be mapped to PUA
        assert mapped[5] == "\ue00e"
        # Others should remain unchanged
        assert mapped[0] == "k"
        assert mapped[6] == "i"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_japanese_basic(self):
        """Test basic Japanese phonemization"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Test hiragana
        phonemes = phonemize_japanese("あ")
        assert "^" in phonemes  # Start marker
        assert "a" in phonemes  # Phoneme
        assert "$" in phonemes  # End marker

        # Test with multi-char phonemes
        phonemes = phonemize_japanese("ちゃ")
        assert len(phonemes) > 2

    @pytest.mark.unit
    def test_empty_input(self):
        """Test empty input handling"""
        # Empty list
        result = [map_token(t) for t in []]
        assert result == []

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_katakana_to_phonemes(self):
        """Test katakana to phonemes conversion"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Basic katakana
        test_cases = [
            ("ア", ["a"]),
            ("カ", ["k", "a"]),
            ("ガ", ["g", "a"]),
            ("サ", ["s", "a"]),
            ("ザ", ["z", "a"]),
            ("タ", ["t", "a"]),
            ("ダ", ["d", "a"]),
            ("ナ", ["n", "a"]),
            ("ハ", ["h", "a"]),
            ("バ", ["b", "a"]),
            ("パ", ["p", "a"]),
            ("マ", ["m", "a"]),
            ("ヤ", ["y", "a"]),
            ("ラ", ["r", "a"]),
            ("ワ", ["w", "a"]),
            ("ン", ["\ue01c"]),  # N at end → N_uvular (PUA 0xE01C)
        ]

        for katakana, expected_phonemes in test_cases:
            phonemes = phonemize_japanese(katakana)
            # Remove markers for comparison
            # Filter out markers, accent symbols, and other OpenJTalk markers
            # Also filter question markers which are now PUA characters
            phoneme_list = [
                p for p in phonemes if p not in ["^", "$", "_", "[", "]", "#", "?",
                                                  "\ue016", "\ue017", "\ue018"]
            ]
            for expected in expected_phonemes:
                assert expected in phoneme_list, (
                    f"Expected '{expected}' in phonemes for '{katakana}', got {phoneme_list}"
                )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_long_vowel_handling(self):
        """Test handling of long vowels (ー)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        test_cases = [
            ("カー", ["k", "a", "a"]),  # Long 'a'
            ("キー", ["k", "i", "i"]),  # Long 'i'
            ("クー", ["k", "u", "u"]),  # Long 'u'
            ("ケー", ["k", "e", "e"]),  # Long 'e'
            ("コー", ["k", "o", "o"]),  # Long 'o'
            (
                "ソフトウェアー",
                ["s", "o", "f", "u", "t", "o", "w", "e", "a", "a"],
            ),  # Complex case
        ]

        for text, expected_phonemes in test_cases:
            phonemes = phonemize_japanese(text)
            # Filter out markers, accent symbols, and other OpenJTalk markers
            phoneme_list = [
                p for p in phonemes if p not in ["^", "$", "_", "[", "]", "#"]
            ]

            # Normalize devoiced vowels (uppercase to lowercase)
            phoneme_list = [
                p.lower() if p in {"A", "I", "U", "E", "O"} else p for p in phoneme_list
            ]

            # Check if all expected phonemes are present in order
            phoneme_str = "".join(phoneme_list)
            expected_str = "".join(expected_phonemes)
            assert expected_str in phoneme_str, (
                f"Expected phonemes {expected_phonemes} for '{text}', got {phoneme_list}"
            )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_invalid_input_handling(self):
        """Test handling of invalid inputs"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Test None input
        with pytest.raises((TypeError, AttributeError)):
            phonemize_japanese(None)

        # Test empty string - OpenJTalk may return empty list for empty input
        phonemes = phonemize_japanese("")
        assert isinstance(phonemes, list)
        # Empty string may not produce any phonemes

        # Test very long input (should not crash)
        long_text = "あ" * 1000
        phonemes = phonemize_japanese(long_text)
        assert len(phonemes) > 1000  # Should produce many phonemes

        # Test mixed scripts
        mixed_text = "Hello こんにちは World"
        phonemes = phonemize_japanese(mixed_text)
        assert len(phonemes) > 0  # Should handle gracefully

        # Test special characters
        special_chars = "！？。、・「」『』"
        phonemes = phonemize_japanese(special_chars)
        assert isinstance(phonemes, list)  # Should not crash

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_small_tsu_handling(self):
        """Test handling of small tsu (っ/ッ)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        test_cases = [
            ("がっこう", ["g", "a", "q", "k", "o", "u"]),  # 学校
            ("ハッピー", ["h", "a", "q", "p", "i", "i"]),  # Happy
            ("ロック", ["r", "o", "q", "k", "u"]),  # Rock
        ]

        for text, _expected_phonemes in test_cases:
            phonemes = phonemize_japanese(text)
            # Filter out markers, accent symbols, and other OpenJTalk markers
            phoneme_list = [
                p for p in phonemes if p not in ["^", "$", "_", "[", "]", "#"]
            ]

            # Check if 'cl' (small tsu) is present as PUA character
            assert (
                "\ue005" in phoneme_list  # cl is mapped to \ue005
            ), (
                f"Expected 'cl' (small tsu as \\ue005) in phonemes for '{text}', got {phoneme_list}"
            )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_compound_kana_handling(self):
        """Test handling of compound kana (きゃ, しゅ, etc.)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Expected PUA mappings for compound phonemes
        test_cases = [
            ("きゃ", ["\ue006", "a"]),  # ky → \ue006
            ("きゅ", ["\ue006", "u"]),  # ky → \ue006
            ("きょ", ["\ue006", "o"]),  # ky → \ue006
            ("しゃ", ["\ue010", "a"]),  # sh → \ue010
            ("しゅ", ["\ue010", "u"]),  # sh → \ue010
            ("しょ", ["\ue010", "o"]),  # sh → \ue010
            ("ちゃ", ["\ue00e", "a"]),  # ch → \ue00e
            ("ちゅ", ["\ue00e", "u"]),  # ch → \ue00e
            ("ちょ", ["\ue00e", "o"]),  # ch → \ue00e
            ("にゃ", ["\ue013", "a"]),  # ny → \ue013
            ("にゅ", ["\ue013", "u"]),  # ny → \ue013
            ("にょ", ["\ue013", "o"]),  # ny → \ue013
        ]

        for text, expected_phonemes in test_cases:
            phonemes = phonemize_japanese(text)
            # Filter out markers, accent symbols, and other OpenJTalk markers
            phoneme_list = [
                p for p in phonemes if p not in ["^", "$", "_", "[", "]", "#"]
            ]

            # Check if compound phonemes are handled correctly with PUA mapping
            assert expected_phonemes == phoneme_list, (
                f"Expected phonemes {expected_phonemes} for '{text}', got {phoneme_list}"
            )

    # =========================================================================
    # Question Type Marker Tests (Issue #204)
    # =========================================================================

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_question_type_generic(self):
        """Test generic question marker ?"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        phonemes = phonemize_japanese("本当？")
        # Generic question marker should be present
        assert "?" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_question_type_emphatic(self):
        """Test emphatic question marker ?!"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        phonemes = phonemize_japanese("本当?!")
        # Check that ?! marker is present (as PUA character 0xE016)
        assert "\ue016" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_question_type_neutral(self):
        """Test neutral/rhetorical question marker ?."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        phonemes = phonemize_japanese("そうですか?.")
        # Check that ?. marker is present (as PUA character 0xE017)
        assert "\ue017" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_question_type_tag(self):
        """Test tag question marker ?~"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        phonemes = phonemize_japanese("行くよね?~")
        # Check that ?~ marker is present (as PUA character 0xE018)
        assert "\ue018" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_question_type_japanese_emphatic(self):
        """Test Japanese style emphatic question ！？"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        phonemes = phonemize_japanese("本当！？")
        # Japanese-style emphatic should also map to ?! (0xE016)
        assert "\ue016" in phonemes

    # =========================================================================
    # N Phoneme Variant Tests (Issue #207)
    # =========================================================================

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_before_bilabial_p(self):
        """Test N_m variant before p (bilabial)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # さんぽ: ん before p → N_m
        phonemes = phonemize_japanese("さんぽ")
        # N_m is mapped to PUA 0xE019
        assert "\ue019" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_before_bilabial_b(self):
        """Test N_m variant before b (bilabial)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # しんぶん: first ん before b → N_m
        phonemes = phonemize_japanese("しんぶん")
        # N_m is mapped to PUA 0xE019
        assert "\ue019" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_before_alveolar_t(self):
        """Test N_n variant before t (alveolar)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # あんない: ん before n → N_n
        phonemes = phonemize_japanese("あんない")
        # N_n is mapped to PUA 0xE01A
        assert "\ue01a" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_before_velar_k(self):
        """Test N_ng variant before k (velar)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # ぎんこう: ん before k → N_ng
        phonemes = phonemize_japanese("ぎんこう")
        # N_ng is mapped to PUA 0xE01B
        assert "\ue01b" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_before_velar_g(self):
        """Test N_ng variant before g (velar)"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # てんごく: ん before g → N_ng
        phonemes = phonemize_japanese("てんごく")
        # N_ng is mapped to PUA 0xE01B
        assert "\ue01b" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_uvular_at_end(self):
        """Test N_uvular variant at phrase end"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # ほん: ん at end → N_uvular
        phonemes = phonemize_japanese("ほん")
        # N_uvular is mapped to PUA 0xE01C
        assert "\ue01c" in phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_variant_uvular_before_vowel(self):
        """Test N_uvular variant before vowel"""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # れんあい: ん before a → N_uvular
        phonemes = phonemize_japanese("れんあい")
        # N_uvular is mapped to PUA 0xE01C
        assert "\ue01c" in phonemes
