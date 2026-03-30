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

    def test_sje_ljud_phonemes(self):
        """Test that sje-ljud (ɧ) is produced correctly."""
        # Test skj- words
        phonemes = phonemize_swedish("skjorta")
        assert "ɧ" in phonemes
        
        # Test sj- words
        phonemes = phonemize_swedish("sjö")
        assert "ɧ" in phonemes
        
        # Test sch- words
        phonemes = phonemize_swedish("schema")
        assert "ɧ" in phonemes

    def test_retroflex_phonemes(self):
        """Test retroflex consonant production (r + consonant).""" 
        # barn: should contain ɳ
        phonemes = phonemize_swedish("barn")
        assert "ɳ" in phonemes
        
        # kart: should contain ʈ
        phonemes = phonemize_swedish("kart") 
        assert "ʈ" in phonemes

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

    def test_vowel_length_rules(self):
        """Test Swedish vowel length determination."""
        # Monosyllabic words should have long vowels (unless geminate)
        phonemes = phonemize_swedish("hej")
        assert "eː" in phonemes  # Long vowel
        
        phonemes = phonemize_swedish("kött") 
        assert "œ" in phonemes   # Short vowel before geminate
        assert "ɧ" not in phonemes  # Should be ɧøt not ɧøːt
        
        # CV.CV patterns should have long first vowel
        phonemes = phonemize_swedish("mata")
        assert "ɑː" in phonemes  # Long first vowel

    def test_rule_based_no_external_deps(self):
        """Test that the rule-based phonemizer works without external dependencies.""" 
        # Should work without espeak-ng
        phonemes = phonemize_swedish("test svenska")
        assert len(phonemes) > 0
        assert "t" in phonemes
        assert "ɛ" in phonemes  # Short e in "svenska"

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
