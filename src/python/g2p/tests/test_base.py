"""Tests for piper_plus_g2p.base — Phonemizer ABC and ProsodyInfo."""

import pytest

from piper_plus_g2p.base import Phonemizer, ProsodyInfo


class TestProsodyInfo:
    def test_dataclass_creation(self):
        """ProsodyInfo can be created with a1, a2, a3 fields."""
        info = ProsodyInfo(a1=-2, a2=1, a3=5)
        assert info.a1 == -2
        assert info.a2 == 1
        assert info.a3 == 5


class TestPhonemizerABC:
    def test_cannot_instantiate_directly(self):
        """Phonemizer is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Phonemizer()

    def test_concrete_subclass_instantiation(self):
        """A concrete subclass implementing all abstract methods can be instantiated."""

        class ConcretePhonemizer(Phonemizer):
            def phonemize(self, text: str) -> list[str]:
                return list(text)

            def phonemize_with_prosody(self, text, /):
                return list(text), [None] * len(text)

        p = ConcretePhonemizer()
        assert isinstance(p, Phonemizer)
        assert p.phonemize("hi") == ["h", "i"]

    def test_missing_phonemize_with_prosody_raises(self):
        """Subclass missing phonemize_with_prosody cannot be instantiated."""

        class PartialPhonemizer(Phonemizer):
            def phonemize(self, text: str) -> list[str]:
                return list(text)

        with pytest.raises(TypeError):
            PartialPhonemizer()


class _EchoPhonemizer(Phonemizer):
    def phonemize_with_prosody(self, text: str):
        return list(text), [None] * len(text)


class TestPhonemizerInputContract:
    def test_strips_c0_and_c1_controls_but_keeps_line_whitespace(self):
        phonemizer = _EchoPhonemizer()

        assert phonemizer.phonemize("A\x00B\x7fC\u0085D\n\t\r") == list("ABCD\n\t\r")

    def test_rejects_non_string_input(self):
        phonemizer = _EchoPhonemizer()

        with pytest.raises(TypeError, match="Expected str, got int"):
            phonemizer.phonemize(123)

    def test_accepts_input_at_maximum_length(self):
        phonemizer = _EchoPhonemizer()
        text = "a" * phonemizer.MAX_INPUT_LENGTH

        assert len(phonemizer.phonemize(text)) == phonemizer.MAX_INPUT_LENGTH

    def test_rejects_input_over_maximum_length(self):
        phonemizer = _EchoPhonemizer()
        text = "a" * (phonemizer.MAX_INPUT_LENGTH + 1)

        with pytest.raises(ValueError, match="Input too long"):
            phonemizer.phonemize(text)
