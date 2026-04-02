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
