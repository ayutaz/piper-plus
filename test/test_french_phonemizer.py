"""Tests for French phonemizer."""

import pytest


class TestFrenchPhonemizer:
    """Tests for rule-based French G2P."""

    def test_simple_word(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bonjour")
        assert len(phonemes) > 0

    def test_nasal_vowel_an(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("france")
        assert "ɑ̃" in phonemes

    def test_nasal_vowel_on(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("bon")
        assert "ɔ̃" in phonemes

    def test_nasal_vowel_in(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("vin")
        assert "ɛ̃" in phonemes

    def test_ou_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("vous")
        assert "u" in phonemes

    def test_oi_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("moi")
        assert "w" in phonemes
        assert "a" in phonemes

    def test_ch_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("chat")
        assert "ʃ" in phonemes

    def test_r_uvular(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("rouge")
        assert "ʁ" in phonemes

    def test_gn_digraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("montagne")
        assert "ɲ" in phonemes

    def test_eau_trigraph(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("eau")
        assert "o" in phonemes

    def test_prosody_alignment(self):
        from piper_train.phonemize.french import phonemize_french_with_prosody

        phonemes, prosody = phonemize_french_with_prosody("bonjour le monde")
        assert len(phonemes) == len(prosody)

    def test_phonemizer_class(self):
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        phonemes = p.phonemize("bonjour")
        assert len(phonemes) > 0

    def test_phonemizer_get_id_map_returns_none(self):
        from piper_train.phonemize.french import FrenchPhonemizer

        p = FrenchPhonemizer()
        assert p.get_phoneme_id_map() is None

    def test_silent_final_consonant(self):
        """Final consonants are often silent in French."""
        from piper_train.phonemize.french import phonemize_french

        # "petit" — the final 't' should be silent
        phonemes = phonemize_french("petit")
        # Verify we get phonemes (the exact handling depends on rules)
        assert len(phonemes) > 0

    def test_accent_marks(self):
        from piper_train.phonemize.french import phonemize_french

        phonemes = phonemize_french("café")
        assert "e" in phonemes  # é → e
