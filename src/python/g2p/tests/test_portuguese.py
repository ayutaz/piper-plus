"""Tests for piper_plus_g2p.portuguese -- PortuguesePhonemizer."""

from piper_plus_g2p.portuguese import PortuguesePhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns a non-empty token list for 'Ola mundo'."""
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Ol\u00e1 mundo")
        assert len(tokens) > 0

    def test_no_pua(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Bom dia")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_nasal_vowel(self):
        """Nasal vowel is produced for nasal context (e.g. 'mundo' -> nasal u)."""
        p = PortuguesePhonemizer()
        tokens = p.phonemize("mundo")
        # "mundo" contains "un" before consonant -> nasal vowel "u\u0303" (ũ)
        # ã, ẽ, ĩ, õ, ũ
        nasal_vowels = {"\u00e3", "\u1ebd", "\u0129", "\u00f5", "\u0169"}
        has_nasal = any(t in nasal_vowels for t in tokens)
        assert has_nasal, f"Expected nasal vowel in {tokens}"

    def test_word_boundary(self):
        """Multi-word text includes space as word boundary."""
        p = PortuguesePhonemizer()
        tokens = p.phonemize("Bom dia")
        assert " " in tokens, f"Expected space token in {tokens}"


class TestProsody:
    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        p = PortuguesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Ol\u00e1 mundo")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_stress(self):
        """Stressed syllable has a2=2 in prosody info."""
        from piper_plus_g2p.base import ProsodyInfo

        p = PortuguesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Ol\u00e1")
        has_stress = any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
        assert has_stress, "Expected at least one ProsodyInfo with a2=2 (stress)"
