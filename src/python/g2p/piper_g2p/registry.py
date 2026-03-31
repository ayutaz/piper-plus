"""Language phonemizer registry."""

import logging

from .base import Phonemizer

_REGISTRY: dict[str, Phonemizer] = {}
_LOGGER = logging.getLogger(__name__)

# Latin-script language priority for default_latin_language detection
_LATIN_PRIORITY = ("en", "es", "pt", "fr")


def register_language(code: str, phonemizer: Phonemizer) -> None:
    """Register a phonemizer for a language code."""
    _REGISTRY[code] = phonemizer


def _detect_default_latin(parts: list[str]) -> str:
    """Detect the best default Latin-script language from a list of codes.

    Priority order: en > es > pt > fr.  Falls back to the first language
    in the list if no Latin-script language is present.
    """
    for lang in _LATIN_PRIORITY:
        if lang in parts:
            return lang
    return parts[0]


def get_phonemizer(language: str) -> Phonemizer:
    """Get the phonemizer for a language code.

    Supports composite language codes (e.g. "ja-en-zh") which
    automatically create a ``MultilingualPhonemizer`` wrapping the
    individual registered phonemizers.
    """
    if language in _REGISTRY:
        return _REGISTRY[language]

    # Composite code: "ja-en-zh" etc.
    parts = language.split("-")
    if len(parts) >= 2:
        canonical_parts = sorted(parts)
        canonical_key = "-".join(canonical_parts)
        if canonical_key in _REGISTRY:
            _REGISTRY[language] = _REGISTRY[canonical_key]
            return _REGISTRY[canonical_key]

        missing = [p for p in canonical_parts if p not in _REGISTRY]
        if not missing:
            from .multilingual import MultilingualPhonemizer  # noqa: PLC0415

            phonemizer = MultilingualPhonemizer(
                canonical_parts,
                default_latin_language=_detect_default_latin(canonical_parts),
            )
            _REGISTRY[canonical_key] = phonemizer
            if language != canonical_key:
                _REGISTRY[language] = phonemizer
            return phonemizer

        raise ValueError(
            f"Missing language(s) {missing} for composite code '{language}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )

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
    try:
        from .chinese import ChinesePhonemizer  # noqa: PLC0415

        register_language("zh", ChinesePhonemizer())
    except ImportError:
        pass
    try:
        from .korean import KoreanPhonemizer  # noqa: PLC0415

        register_language("ko", KoreanPhonemizer())
    except ImportError:
        pass
    try:
        from .spanish import SpanishPhonemizer  # noqa: PLC0415

        register_language("es", SpanishPhonemizer())
    except ImportError:
        pass
    try:
        from .french import FrenchPhonemizer  # noqa: PLC0415

        register_language("fr", FrenchPhonemizer())
    except ImportError:
        pass
    try:
        from .portuguese import PortuguesePhonemizer  # noqa: PLC0415

        register_language("pt", PortuguesePhonemizer())
    except ImportError:
        pass


_auto_register()
