"""Tests for English G2P module (g2p-en based)."""

import pytest

from piper_train.phonemize.english import (
    ARPABET_TO_IPA,
    EnglishProsodyInfo,
    _arpabet_to_ipa,
    phonemize_english,
    phonemize_english_with_prosody,
)


class TestArpabetToIpa:
    """Tests for ARPAbet to IPA conversion."""

    def test_consonant_no_stress(self):
        ipa, stress = _arpabet_to_ipa("B")
        assert ipa == "b"
        assert stress == -1

    def test_vowel_with_primary_stress(self):
        ipa, stress = _arpabet_to_ipa("OW1")
        assert ipa == "oʊ"
        assert stress == 1

    def test_vowel_with_secondary_stress(self):
        ipa, stress = _arpabet_to_ipa("AO2")
        assert ipa == "ɔː"
        assert stress == 2

    def test_vowel_unstressed(self):
        ipa, stress = _arpabet_to_ipa("IH0")
        assert ipa == "ɪ"
        assert stress == 0

    def test_ah_unstressed_is_schwa(self):
        ipa, stress = _arpabet_to_ipa("AH0")
        assert ipa == "ə"
        assert stress == 0

    def test_ah_stressed_is_not_schwa(self):
        ipa, stress = _arpabet_to_ipa("AH1")
        assert ipa == "ʌ"
        assert stress == 1

    def test_punctuation_passthrough(self):
        ipa, stress = _arpabet_to_ipa(",")
        assert ipa == ","
        assert stress == -1

    def test_all_arpabet_symbols_mapped(self):
        """Every ARPAbet symbol should produce a non-empty IPA string."""
        for arpa, expected_ipa in ARPABET_TO_IPA.items():
            ipa, stress = _arpabet_to_ipa(arpa)
            assert ipa == expected_ipa
            assert stress == -1  # No stress digit → -1


class TestStressToProsody:
    """Tests for stress marker to prosody A2 mapping."""

    def test_primary_stress_maps_to_a2_2(self):
        _, prosody_list = phonemize_english_with_prosody("go")
        # "go" → G OW1 → at least one phoneme with a2=2
        a2_values = [p.a2 for p in prosody_list]
        assert 2 in a2_values

    def test_unstressed_maps_to_a2_0(self):
        _, prosody_list = phonemize_english_with_prosody("the")
        # "the" → DH AH0 → schwa should have a2=0
        a2_values = [p.a2 for p in prosody_list]
        assert 0 in a2_values

    def test_a1_always_zero(self):
        _, prosody_list = phonemize_english_with_prosody("Hello world")
        for p in prosody_list:
            assert p.a1 == 0


class TestPhonemizeEnglish:
    """Tests for full English phonemization pipeline."""

    def test_basic_word(self):
        phonemes = phonemize_english("hello")
        assert len(phonemes) > 0
        # Should contain IPA characters
        assert all(isinstance(p, str) for p in phonemes)

    def test_multiple_words(self):
        phonemes = phonemize_english("Hello world")
        assert len(phonemes) > 0

    def test_with_prosody_lengths_match(self):
        phonemes, prosody = phonemize_english_with_prosody("How are you?")
        assert len(phonemes) == len(prosody)

    def test_prosody_info_type(self):
        _, prosody = phonemize_english_with_prosody("test")
        for p in prosody:
            assert isinstance(p, EnglishProsodyInfo)

    def test_a3_is_word_phoneme_count(self):
        """A3 should reflect the total IPA character count for the word."""
        phonemes, prosody = phonemize_english_with_prosody("cat")
        # "cat" → K AE1 T → k æ t → 3 IPA chars
        # All phonemes from this single word should have the same a3
        a3_values = {p.a3 for p in prosody}
        assert len(a3_values) == 1  # Single word, single a3 value
        # a3 should equal the actual number of phoneme tokens produced
        assert a3_values.pop() == len(phonemes)

    def test_empty_string(self):
        phonemes, prosody = phonemize_english_with_prosody("")
        assert phonemes == []
        assert prosody == []

    def test_numbers(self):
        """g2p-en should handle numbers."""
        phonemes = phonemize_english("123")
        assert len(phonemes) > 0


class TestPhonemeIdMapIntegration:
    """Test that English phonemes can be mapped to IDs using a phoneme_id_map."""

    def test_phonemes_are_single_chars(self):
        """Each phoneme should be a single character (mappable to phoneme_id_map)."""
        phonemes = phonemize_english("Hello, how are you today?")
        for p in phonemes:
            assert len(p) == 1, f"Multi-char phoneme found: {p!r}"
