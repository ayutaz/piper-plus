"""Language phonemizer registry."""

import logging

from .base import Phonemizer

_REGISTRY: dict[str, Phonemizer] = {}
_LOGGER = logging.getLogger(__name__)


def register_language(code: str, phonemizer: Phonemizer) -> None:
    """Register a phonemizer for a language code."""
    _REGISTRY[code] = phonemizer


def get_phonemizer(language: str) -> Phonemizer:
    """Get the phonemizer for a language code."""
    if language in _REGISTRY:
        return _REGISTRY[language]
    raise ValueError(
        f"Unsupported language: {language}. "
        f"Available: {list(_REGISTRY.keys())}"
    )


def available_languages() -> list[str]:
    """Return list of registered language codes."""
    return list(_REGISTRY.keys())


def _auto_register() -> None:
    """Register available language phonemizers at import time."""
    try:
        from .japanese import JapanesePhonemizer  # noqa: PLC0415

        register_language("ja", JapanesePhonemizer())
    except ImportError:
        pass
    try:
        from .english import EnglishPhonemizer  # noqa: PLC0415

        register_language("en", EnglishPhonemizer())
    except ImportError:
        pass


_auto_register()
