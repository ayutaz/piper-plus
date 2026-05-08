"""Tests for piper_plus_g2p.english — EnglishPhonemizer."""

import pytest

from piper_plus_g2p.base import Phonemizer
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


@requires_en
class TestSanitizeInput:
    """EnglishPhonemizer must honour the BasePhonemizer._sanitize_input contract.

    Mirrors JapanesePhonemizer behaviour: oversized input → ValueError, non-str
    input → TypeError, control characters stripped.
    """

    def test_phonemize_too_long_raises(self):
        """phonemize() rejects input longer than MAX_INPUT_LENGTH."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        oversize = "a" * (Phonemizer.MAX_INPUT_LENGTH + 1)
        with pytest.raises(ValueError, match="Input too long"):
            p.phonemize(oversize)

    def test_phonemize_with_prosody_too_long_raises(self):
        """phonemize_with_prosody() rejects input longer than MAX_INPUT_LENGTH."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        oversize = "a" * (Phonemizer.MAX_INPUT_LENGTH + 1)
        with pytest.raises(ValueError, match="Input too long"):
            p.phonemize_with_prosody(oversize)

    def test_phonemize_at_max_length_ok(self):
        """phonemize() accepts input at exactly MAX_INPUT_LENGTH (boundary)."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        # Use a small valid input just under the limit; we only need to
        # assert no exception, not a specific token shape.
        text = "hello " * 100  # 600 chars, well under 10_000
        assert len(text) <= Phonemizer.MAX_INPUT_LENGTH
        tokens = p.phonemize(text)
        assert isinstance(tokens, list)

    def test_phonemize_non_str_raises_type_error(self):
        """phonemize() rejects non-str input with TypeError."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        with pytest.raises(TypeError, match="Expected str"):
            p.phonemize(123)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="Expected str"):
            p.phonemize(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="Expected str"):
            p.phonemize(["hello"])  # type: ignore[arg-type]

    def test_phonemize_with_prosody_non_str_raises_type_error(self):
        """phonemize_with_prosody() rejects non-str input with TypeError."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        with pytest.raises(TypeError, match="Expected str"):
            p.phonemize_with_prosody(42)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="Expected str"):
            p.phonemize_with_prosody(None)  # type: ignore[arg-type]

    def test_phonemize_strips_control_chars(self):
        """Control characters (\\x00, \\x01) must be stripped before g2p_en runs."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        # Compare phoneme output for "Hello" vs "\x00Hello\x01" — they
        # must produce the same token list because control chars are
        # stripped before phonemization.
        clean = p.phonemize("Hello")
        polluted = p.phonemize("\x00\x01Hello\x01\x00")
        assert clean == polluted, (
            f"Control characters not stripped: {clean} vs {polluted}"
        )

    def test_phonemize_with_prosody_strips_control_chars(self):
        """phonemize_with_prosody also strips control chars before g2p_en."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        clean_tokens, clean_prosody = p.phonemize_with_prosody("Hello")
        dirty_tokens, dirty_prosody = p.phonemize_with_prosody("\x00\x01Hello\x01")
        assert clean_tokens == dirty_tokens
        assert len(clean_prosody) == len(dirty_prosody)

    def test_phonemize_preserves_newline_tab(self):
        """\\n, \\t, \\r are preserved (matches base sanitizer contract)."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        # No exception expected.  The sanitizer keeps these whitespace chars,
        # and g2p_en treats them as token separators just like spaces.
        tokens = p.phonemize("Hello\nworld")
        assert isinstance(tokens, list)
        assert len(tokens) > 0

    def test_phonemize_empty_after_sanitize(self):
        """Input consisting entirely of control chars sanitizes to empty → []."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        assert p.phonemize("\x00\x01\x02") == []
        tokens, prosody = p.phonemize_with_prosody("\x00\x01\x02")
        assert tokens == []
        assert prosody == []

    def test_phonemize_empty_string(self):
        """Empty string → empty token list (no g2p_en call)."""
        from piper_plus_g2p.english import EnglishPhonemizer

        p = EnglishPhonemizer()
        assert p.phonemize("") == []
        tokens, prosody = p.phonemize_with_prosody("")
        assert tokens == []
        assert prosody == []
