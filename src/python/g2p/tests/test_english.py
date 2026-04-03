"""Tests for piper_plus_g2p.english — EnglishPhonemizer."""

from tests.conftest import requires_en


@requires_en
class TestBasic:
    def test_basic_phonemize(self):
        """phonemize() returns a non-empty token list."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens = p.phonemize("Hello")
        assert len(tokens) > 0

    def test_word_boundary(self):
        """'Hello world' contains a space token as word boundary."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens = p.phonemize("Hello world")
        assert " " in tokens, f"Expected space token in {tokens}"


@requires_en
class TestStress:
    def test_primary_stress(self):
        """'happy' should include primary stress marker."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens = p.phonemize("happy")
        assert "\u02c8" in tokens, f"Expected primary stress marker in {tokens}"

    def test_secondary_stress(self):
        """'multiplication' should include secondary stress marker."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens = p.phonemize("multiplication")
        assert "\u02cc" in tokens, f"Expected secondary stress marker in {tokens}"

    def test_function_word_no_stress(self):
        """Function word 'the' in 'the cat' should have stress removed (a2=0)."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("the cat")
        # Find tokens before the first space (= "the")
        space_idx = tokens.index(" ") if " " in tokens else len(tokens)
        the_prosody = prosody[:space_idx]
        for pi in the_prosody:
            if pi is not None:
                assert pi.a2 == 0, f"Function word 'the' should have a2=0, got {pi.a2}"


@requires_en
class TestProsody:
    def test_prosody_a1_zero(self):
        """English prosody a1 is always 0."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        _tokens, prosody = p.phonemize_with_prosody("Hello world")
        for pi in prosody:
            if pi is not None:
                assert pi.a1 == 0, f"Expected a1=0, got {pi.a1}"

    def test_prosody_length_matches(self):
        """phonemize_with_prosody returns tokens and prosody of same length."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        tokens, prosody = p.phonemize_with_prosody("Hello world")
        assert len(tokens) == len(prosody), (
            f"Length mismatch: {len(tokens)} tokens vs {len(prosody)} prosody"
        )
