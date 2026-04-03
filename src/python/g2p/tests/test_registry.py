"""Tests for piper_plus_g2p.registry — language phonemizer registry."""

import pytest

from piper_plus_g2p.base import Phonemizer
from piper_plus_g2p.registry import (
    available_languages,
    get_phonemizer,
    register_language,
)


class _DummyPhonemizer(Phonemizer):
    """Minimal concrete phonemizer for testing registration."""

    def phonemize(self, text: str) -> list[str]:
        return list(text)

    def phonemize_with_prosody(self, text, /):
        return list(text), [None] * len(text)


class TestRegistry:
    def test_register_and_get(self):
        """register_language + get_phonemizer round-trips correctly."""
        dummy = _DummyPhonemizer()
        register_language("xx-test", dummy)
        assert get_phonemizer("xx-test") is dummy

    def test_unregistered_language_raises(self):
        """get_phonemizer raises ValueError for an unregistered language."""
        with pytest.raises(ValueError):
            get_phonemizer("zz_nonexistent")

    def test_available_languages_contains_registered(self):
        """available_languages includes previously registered language codes."""
        dummy = _DummyPhonemizer()
        register_language("xx-avail", dummy)
        langs = available_languages()
        assert "xx-avail" in langs

    def test_auto_register_no_import_error(self):
        """_auto_register (called at import time) does not raise ImportError.

        Even if pyopenjtalk or g2p-en are not installed, auto_register
        should silently skip them.
        """
        # If we got this far, the module imported without error.
        # Re-invoke to ensure idempotent behavior.
        from piper_plus_g2p.registry import _auto_register

        _auto_register()  # should not raise
