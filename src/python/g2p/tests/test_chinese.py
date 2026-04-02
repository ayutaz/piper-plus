"""Tests for piper_plus_g2p.chinese -- ChinesePhonemizer."""

from tests.conftest import requires_zh


@requires_zh
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns tokens without BOS/EOS markers."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你好")
        assert len(tokens) > 0
        assert "^" not in tokens, "BOS should not be present"
        assert "$" not in tokens, "EOS should not be present"

    def test_no_pua_characters(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("今天天气很好")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_tone_markers(self):
        """phonemize() includes tone markers (tone1 through tone5)."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        # Use a sentence with varied tones
        tokens = p.phonemize("中国人民")
        tone_tokens = [t for t in tokens if t.startswith("tone")]
        assert len(tone_tokens) > 0, f"Expected tone markers in {tokens}"
        # Check that tone tokens are valid
        valid_tones = {"tone1", "tone2", "tone3", "tone4", "tone5"}
        for t in tone_tokens:
            assert t in valid_tones, f"Invalid tone marker: {t}"

    def test_punctuation(self):
        """Chinese punctuation characters are processed."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens = p.phonemize("你好！")
        assert "!" in tokens, f"Expected '!' (mapped from fullwidth) in {tokens}"


@requires_zh
class TestProsody:
    def test_prosody_length_matches(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("你好世界")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_tone_info(self):
        """ProsodyInfo a1 carries tone number for Chinese characters."""
        from piper_plus_g2p.base import ProsodyInfo
        from piper_plus_g2p.chinese import ChinesePhonemizer

        p = ChinesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("你好")
        # At least one prosody entry should have a1 in range 1-5 (tone)
        has_tone = any(
            isinstance(pi, ProsodyInfo) and 1 <= pi.a1 <= 5 for pi in prosody
        )
        assert has_tone, "Expected at least one ProsodyInfo with tone (a1=1..5)"
