"""Language phonemizer registry."""

from .base import Phonemizer


_REGISTRY: dict[str, Phonemizer] = {}


def register_language(code: str, phonemizer: Phonemizer):
    """Register a phonemizer for a language code."""
    _REGISTRY[code] = phonemizer


def get_phonemizer(language: str) -> Phonemizer:
    """Get the phonemizer for a language code."""
    if language not in _REGISTRY:
        raise ValueError(
            f"Unsupported language: {language}. Available: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[language]


def available_languages() -> list[str]:
    """Return list of registered language codes."""
    return list(_REGISTRY.keys())


def _auto_register():
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
    try:
        from .bilingual import BilingualPhonemizer  # noqa: PLC0415

        register_language("ja-en", BilingualPhonemizer(["ja", "en"]))
    except ImportError:
        pass


_auto_register()
