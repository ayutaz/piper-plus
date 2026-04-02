"""Tests for piper_plus_g2p.spanish -- SpanishPhonemizer."""

from piper_plus_g2p.spanish import SpanishPhonemizer


class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns a non-empty token list for 'Hola mundo'."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola mundo")
        assert len(tokens) > 0

    def test_stress_marker(self):
        """phonemize() includes primary stress marker for content words."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola")
        assert "\u02c8" in tokens, f"Expected primary stress marker in {tokens}"

    def test_trill_r(self):
        """'perro' produces the trill 'rr' token."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("perro")
        assert "rr" in tokens, f"Expected trill 'rr' in {tokens}"

    def test_word_boundary(self):
        """Multi-word text includes space as word boundary."""
        p = SpanishPhonemizer()
        tokens = p.phonemize("Hola mundo")
        assert " " in tokens, f"Expected space token in {tokens}"


class TestProsody:
    def test_prosody_length(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        p = SpanishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Buenos dias")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )

    def test_prosody_stress_value(self):
        """Stressed phonemes have a2=2 in prosody info."""
        from piper_plus_g2p.base import ProsodyInfo

        p = SpanishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Hola")
        has_stress = any(isinstance(pi, ProsodyInfo) and pi.a2 == 2 for pi in prosody)
        assert has_stress, "Expected at least one ProsodyInfo with a2=2 (stress)"
