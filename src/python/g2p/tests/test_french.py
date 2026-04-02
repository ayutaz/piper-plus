"""Tests for piper_plus_g2p.french -- FrenchPhonemizer."""

from piper_plus_g2p.french import FrenchPhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns a non-empty token list for 'Bonjour'."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour")
        assert len(tokens) > 0

    def test_nasal_vowels(self):
        """phonemize() produces nasal vowels for French nasal contexts."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour")
        # "Bonjour" contains "on" -> nasal vowel
        nasal_vowels = {"\u0254\u0303", "\u0251\u0303", "\u025b\u0303"}  # ɔ̃, ɑ̃, ɛ̃
        has_nasal = any(t in nasal_vowels for t in tokens)
        assert has_nasal, f"Expected nasal vowel in {tokens}"

    def test_word_boundary(self):
        """Multi-word text includes space as word boundary."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("Bonjour le monde")
        assert " " in tokens, f"Expected space token in {tokens}"

    def test_silent_final_consonant(self):
        """Final silent consonants are omitted (e.g. 'petit' -> no final t)."""
        p = FrenchPhonemizer()
        tokens = p.phonemize("petit")
        # "petit" should not end with "t" (silent final)
        assert tokens[-1] != "t", f"Expected silent final 't' to be omitted in {tokens}"


class TestProsody:
    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        p = FrenchPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Bonjour le monde")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_stress(self):
        """French word-final syllable receives stress (a2=2)."""
        from piper_plus_g2p.base import ProsodyInfo

        p = FrenchPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Bonjour")
        has_stress = any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
        assert has_stress, "Expected at least one ProsodyInfo with a2=2 (stress)"
