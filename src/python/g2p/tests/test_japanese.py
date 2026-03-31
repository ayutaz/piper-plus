"""Tests for piper_g2p.japanese — JapanesePhonemizer."""

import pytest

from tests.conftest import requires_ja


@requires_ja
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns tokens without BOS/EOS markers."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert len(tokens) > 0
        assert "^" not in tokens, "BOS should not be present"
        assert "$" not in tokens, "EOS should not be present"

    def test_no_pua_characters(self):
        """phonemize() returns no PUA characters (U+E000-U+F8FF)."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("東京タワーに行きましょう")
        for token in tokens:
            for ch in token:
                assert not (0xE000 <= ord(ch) <= 0xF8FF), (
                    f"PUA character found: U+{ord(ch):04X} in token {token!r}"
                )

    def test_prosody_symbols(self):
        """phonemize() includes prosody markers '#', '[', ']'."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        # Use a multi-phrase sentence to trigger prosody markers
        tokens = p.phonemize("今日は良い天気ですね。")
        all_tokens_str = " ".join(tokens)
        has_prosody = any(t in ("#", "[", "]") for t in tokens)
        assert has_prosody, (
            f"Expected at least one prosody marker in: {all_tokens_str}"
        )


@requires_ja
class TestNVariants:
    def test_n_bilabial(self):
        """'新聞' should produce N_m (before bilabial m/b/p)."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("新聞")
        assert "N_m" in tokens, f"Expected N_m in {tokens}"

    def test_n_alveolar(self):
        """'こんにちは' should produce N_n (before alveolar n)."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert "N_n" in tokens, f"Expected N_n in {tokens}"

    def test_n_velar(self):
        """'文化' should produce N_ng (before velar k/g)."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("文化")
        assert "N_ng" in tokens, f"Expected N_ng in {tokens}"

    def test_n_uvular(self):
        """'本' should produce N_uvular (phrase-final)."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("本")
        assert "N_uvular" in tokens, f"Expected N_uvular in {tokens}"


@requires_ja
class TestQuestionMarkers:
    def test_generic_question(self):
        """'何？' should produce '?' marker."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何？")
        assert "?" in tokens, f"Expected '?' in {tokens}"

    def test_emphatic_question(self):
        """'何？！' should produce '?!' marker."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何？！")
        assert "?!" in tokens, f"Expected '?!' in {tokens}"

    def test_neutral_question(self):
        """'何。？' should produce '?.' marker."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens = p.phonemize("何。？")
        assert "?." in tokens, f"Expected '?.' in {tokens}"

    def test_tag_question(self):
        """'何～？' should produce '?~' marker."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        # U+FF5E (full-width tilde) + U+FF1F (full-width question mark)
        tokens = p.phonemize("何\uFF5E\uFF1F")
        assert "?~" in tokens, f"Expected '?~' in {tokens}"


@requires_ja
class TestProsody:
    def test_prosody_length_matches(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("こんにちは")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_has_values(self):
        """At least some prosody entries are ProsodyInfo (not all None)."""
        from piper_g2p.base import ProsodyInfo
        from piper_g2p.japanese import JapanesePhonemizer

        p = JapanesePhonemizer()
        tokens, prosody = p.phonemize_with_prosody("こんにちは")
        has_info = any(isinstance(pi, ProsodyInfo) for pi in prosody)
        assert has_info, "Expected at least one non-None ProsodyInfo entry"
