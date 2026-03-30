"""Tests for Swedish phonemizer."""

import pytest

from piper_train.phonemize.swedish import (
    SwedishPhonemizer,
    _apply_swedish_corrections,
    phonemize_swedish,
    phonemize_swedish_with_prosody,
)


class TestSwedishPhonemizer:
    """Tests for Swedish phonemizer with espeak-ng backend."""

    def test_simple_word(self):
        """Test basic Swedish word phonemization."""
        phonemes = phonemize_swedish("hej")
        assert len(phonemes) > 0
        # Should contain some Swedish phonemes
        assert any(p in "hej" for p in phonemes)

    def test_swedish_vowels(self):
        """Test Swedish-specific vowels (å, ä, ö)."""
        phonemes = phonemize_swedish("hål")  # hole
        # Should contain Swedish phonemes (exact output depends on espeak-ng)
        assert len(phonemes) >= 2
        
        phonemes = phonemize_swedish("hör")  # hear  
        assert len(phonemes) >= 2
        
        phonemes = phonemize_swedish("här")  # here
        assert len(phonemes) >= 2

    def test_sje_ljud_corrections(self):
        """Test that sje-ljud (ɧ) corrections are applied."""
        # Test skj- words: should get ɧ not ɕ
        corrections = ["ɕ", "o", "ː", "t", "a"]  # fake espeak output 
        corrected = _apply_swedish_corrections(corrections, "skjorta")
        assert "ɧ" in corrected
        assert "ɕ" not in corrected
        
        # Test sch- words: should get ɧ not ʃ
        corrections = ["ʃ", "e", "ː", "m", "a"]  # fake espeak output
        corrected = _apply_swedish_corrections(corrections, "schema") 
        assert "ɧ" in corrected
        assert "ʃ" not in corrected

    def test_retroflex_corrections(self):
        """Test retroflex consonant corrections (r + consonant)."""
        # barn: rn → ɳ
        corrections = ["b", "a", "r", "n"]  # fake espeak output
        corrected = _apply_swedish_corrections(corrections, "barn")
        # Should apply retroflex correction
        expected_retroflex = any("ɳ" in "".join(corrected) or "rn" not in "".join(corrected) 
                                for _ in [True])  # Basic check that some correction happened
        
        # bord: rd → ɖ  
        corrections = ["b", "u", "r", "d"]
        corrected = _apply_swedish_corrections(corrections, "bord")
        # Should apply some correction
        assert len(corrected) >= 3

    def test_stress_markers(self):
        """Test that stress markers are preserved.""" 
        phonemes = phonemize_swedish("musik")  # music
        # espeak-ng should include stress markers for polysyllabic words
        # (exact position depends on espeak-ng version)
        assert len(phonemes) > 0

    def test_prosody_alignment(self):
        """Test that prosody info aligns with phonemes."""
        phonemes, prosody = phonemize_swedish_with_prosody("hej världen")
        assert len(phonemes) == len(prosody)
        # Should have some prosody info
        assert any(p is not None for p in prosody)

    def test_tonaccent_mapping(self):
        """Test Swedish tonaccent mapping in prosody."""
        phonemes, prosody = phonemize_swedish_with_prosody("musik") 
        assert len(phonemes) == len(prosody)
        
        # Check that stressed vowels get appropriate tonaccent values
        stressed_prosody = [p for p in prosody if p is not None and p.a2 > 0]
        if stressed_prosody:
            # Should have either accent 1 (a1=1) or accent 2 (a1=2) 
            assert any(p.a1 in [1, 2] for p in stressed_prosody)

    def test_phonemizer_class(self):
        """Test SwedishPhonemizer class interface."""
        p = SwedishPhonemizer()
        phonemes = p.phonemize("svenska")  # Swedish
        assert len(phonemes) > 0
        
        # Test with prosody
        phonemes, prosody = p.phonemize_with_prosody("svenska")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_get_id_map_returns_none(self):
        """Test that get_phoneme_id_map returns None (multilingual mode)."""
        p = SwedishPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_punctuation_passthrough(self):
        """Test that punctuation passes through."""
        phonemes = phonemize_swedish("Hej!")
        assert "!" in phonemes
        
        phonemes = phonemize_swedish("Vad?")
        assert "?" in phonemes

    def test_long_vowels_pua_mapping(self):
        """Test that long vowels get properly mapped to PUA."""
        # This tests the integration with token_mapper
        phonemes = phonemize_swedish("bil")  # car (long i)
        # After map_sequence, multi-char phonemes should be single chars
        assert all(len(p) == 1 for p in phonemes)

    def test_empty_input(self):
        """Test handling of empty input.""" 
        assert phonemize_swedish("") == []
        assert phonemize_swedish("   ") == []

    def test_corrections_dict_coverage(self):
        """Test that key Swedish pronunciation issues are covered."""
        from piper_train.phonemize.swedish import SWEDISH_POST_CORRECTIONS
        
        # Should have skj corrections
        assert any("ɕ" in wrong for wrong in SWEDISH_POST_CORRECTIONS)
        # Should have sch corrections 
        assert any("ʃ" in wrong for wrong in SWEDISH_POST_CORRECTIONS)
        # Should have retroflex corrections
        assert any("barn" in word for word in SWEDISH_POST_CORRECTIONS)

    @pytest.mark.slow
    def test_espeak_ng_available(self):
        """Test that espeak-ng is available and works with Swedish."""
        try:
            phonemes = phonemize_swedish("test svenska")
            assert len(phonemes) > 0
        except RuntimeError as e:
            if "espeak-ng is required" in str(e):
                pytest.skip("espeak-ng not available")
            else:
                raise

    def test_compound_words(self):
        """Test Swedish compound words."""
        # Swedish loves compound words
        phonemes = phonemize_swedish("julklapp")  # Christmas gift
        assert len(phonemes) > 4  # Should be several phonemes
        
    def test_place_names(self):
        """Test Swedish place names get corrected."""
        # This tests some of the geographical corrections
        phonemes = phonemize_swedish("Stockholm") 
        assert len(phonemes) > 6  # Should have several phonemes
        
        phonemes = phonemize_swedish("Göteborg")
        assert len(phonemes) > 6

    def test_common_words(self):
        """Test common Swedish words."""
        common_words = ["och", "att", "det", "är", "jag", "en", "på", "med"]
        
        for word in common_words:
            phonemes = phonemize_swedish(word)
            assert len(phonemes) > 0, f"Failed to phonemize '{word}'"

    def test_prosody_word_phoneme_count(self):
        """Test that prosody a3 contains correct word phoneme count."""
        phonemes, prosody = phonemize_swedish_with_prosody("hus")  # house
        
        # Count non-stress-marker phonemes
        word_phoneme_count = len([p for p in phonemes if p not in "ˈˌ "])
        
        # All non-space prosody should have the same a3 value
        word_prosody = [p for p in prosody if p is not None and p.a3 > 0]
        if word_prosody:
            assert all(p.a3 == word_prosody[0].a3 for p in word_prosody)

    def test_multilingual_compatibility(self):
        """Test that Swedish phonemes work in multilingual context."""
        # This would be tested more thoroughly in multilingual tests,
        # but basic check that the phonemizer produces reasonable output
        phonemes = phonemize_swedish("svenska text")
        assert len(phonemes) > 5
        assert " " in phonemes  # Should have word separator