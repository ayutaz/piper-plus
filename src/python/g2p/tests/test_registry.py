"""Tests for piper_plus_g2p.registry — language phonemizer registry."""

import pytest

from piper_plus_g2p.base import Phonemizer
from piper_plus_g2p.registry import (
    PhonemizerRegistry,
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


class TestPortugueseDialectAlias:
    """BCP-47 alias / fallback contract for Portuguese — see
    ``docs/spec/pt-dialect-contract.toml``.

    These tests use isolated :class:`PhonemizerRegistry` instances so
    they do not depend on ``_auto_register`` actually loading the rule
    based ``PortuguesePhonemizer`` (which is dependency-free, but the
    isolated registry keeps the test focused on the alias mechanism).
    """

    def test_pt_BR_resolves_to_same_instance_as_pt(self):
        """pt-BR must return the exact same Phonemizer object as pt."""
        registry = PhonemizerRegistry()
        dummy = _DummyPhonemizer()
        registry.register("pt", dummy)
        assert registry.get("pt-BR") is dummy
        assert registry.get("pt") is registry.get("pt-BR")

    def test_pt_br_lowercase_alias_also_resolves(self):
        """Region-subtag is case-insensitive: pt-br must work too."""
        registry = PhonemizerRegistry()
        dummy = _DummyPhonemizer()
        registry.register("pt", dummy)
        assert registry.get("pt-br") is dummy

    def test_pt_PT_raises_explicit_error(self):
        """pt-PT (European Portuguese) must raise an explicit ValueError
        rather than silently routing through the BR phonemizer.
        """
        registry = PhonemizerRegistry()
        dummy = _DummyPhonemizer()
        registry.register("pt", dummy)
        with pytest.raises(ValueError, match="European Portuguese"):
            registry.get("pt-PT")

    def test_pt_pt_lowercase_also_rejected(self):
        registry = PhonemizerRegistry()
        registry.register("pt", _DummyPhonemizer())
        with pytest.raises(ValueError, match="European Portuguese"):
            registry.get("pt-pt")

    def test_pt_PT_error_does_not_leak_into_composite_path(self):
        """The pt-PT rejection must NOT be a side effect of the
        composite-code splitter — it must fire even if PT is registered
        as a separate language.
        """
        registry = PhonemizerRegistry()
        registry.register("pt", _DummyPhonemizer())
        registry.register("PT", _DummyPhonemizer())  # hypothetical
        with pytest.raises(ValueError, match="European Portuguese"):
            registry.get("pt-PT")

    def test_alias_is_cached_after_first_lookup(self):
        """The first pt-BR lookup must populate the registry under
        'pt-BR' so subsequent ``available()`` reflects it.
        """
        registry = PhonemizerRegistry()
        registry.register("pt", _DummyPhonemizer())
        assert "pt-BR" not in registry.available()
        registry.get("pt-BR")
        assert "pt-BR" in registry.available()

    def test_unsupported_dialect_does_not_pollute_registry(self):
        """A failed pt-PT lookup must NOT add 'pt-PT' to the registry
        (no silent side effect from the failure path).
        """
        registry = PhonemizerRegistry()
        registry.register("pt", _DummyPhonemizer())
        with pytest.raises(ValueError):
            registry.get("pt-PT")
        assert "pt-PT" not in registry.available()
        assert "pt-pt" not in registry.available()
