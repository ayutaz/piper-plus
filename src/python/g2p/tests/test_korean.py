"""Tests for piper_g2p.korean -- KoreanPhonemizer."""

import pytest

from tests.conftest import requires_ko


@requires_ko
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns a non-empty token list."""
        from piper_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        tokens = p.phonemize("안녕하세요")
        assert len(tokens) > 0

    def test_no_pua(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        from piper_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        tokens = p.phonemize("한국어를 공부합니다")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_phonemes_present(self):
        """phonemize() produces IPA tokens from Hangul decomposition."""
        from piper_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        tokens = p.phonemize("가나다")
        # Should contain at least some IPA vowels/consonants
        ipa_chars = set("aeiouɛʌɯkntpmslɾ")
        has_ipa = any(t in ipa_chars for t in tokens)
        assert has_ipa, f"Expected IPA phonemes in {tokens}"


@requires_ko
class TestProsody:
    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_g2p.korean import KoreanPhonemizer

        p = KoreanPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("안녕하세요")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )
