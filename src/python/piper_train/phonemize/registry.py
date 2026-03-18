"""Language phonemizer registry.

Supports both individual language codes (e.g., "ja", "en") and
multilingual combo codes (e.g., "ja-en-zh-ko") which automatically
create a MultilingualPhonemizer.
"""

import logging

from .base import Phonemizer


_REGISTRY: dict[str, Phonemizer] = {}
_LOGGER = logging.getLogger(__name__)


def register_language(code: str, phonemizer: Phonemizer):
    """Register a phonemizer for a language code."""
    _REGISTRY[code] = phonemizer


def get_phonemizer(language: str) -> Phonemizer:
    """Get the phonemizer for a language code.

    For multi-language codes like "ja-en-zh-ko", automatically creates
    and caches a MultilingualPhonemizer instance.
    """
    if language in _REGISTRY:
        return _REGISTRY[language]

    # Try to create a multilingual combo phonemizer
    parts = language.split("-")
    if len(parts) >= 2:
        # Canonicalize language order (sorted) so "en-ja" and "ja-en" share one instance
        canonical_parts = sorted(parts)
        canonical_key = "-".join(canonical_parts)
        if parts != canonical_parts:
            _LOGGER.warning(
                "Language code '%s' is not in canonical sorted order; "
                "using canonical form '%s' for cache lookup.",
                language,
                canonical_key,
            )
        # Check cache with canonical key first
        if canonical_key in _REGISTRY:
            # Also register the original key for direct lookup next time
            _REGISTRY[language] = _REGISTRY[canonical_key]
            return _REGISTRY[canonical_key]

        # Verify all component languages are registered
        missing = [p for p in canonical_parts if p not in _REGISTRY]
        if not missing:
            from .multilingual import MultilingualPhonemizer  # noqa: PLC0415

            phonemizer = MultilingualPhonemizer(
                canonical_parts,
                default_latin_language=_detect_default_latin(canonical_parts),
            )
            # Register under canonical key and original key
            _REGISTRY[canonical_key] = phonemizer
            if language != canonical_key:
                _REGISTRY[language] = phonemizer
            return phonemizer

        raise ValueError(
            f"Cannot create multilingual phonemizer for '{language}': "
            f"missing language(s) {missing}. Available: {list(_REGISTRY.keys())}"
        )

    raise ValueError(
        f"Unsupported language: {language}. Available: {list(_REGISTRY.keys())}"
    )


def _detect_default_latin(languages: list[str]) -> str:
    """Determine the default Latin-script language for a language combination.

    Returns the best Latin-script language from *languages*.  Prefers English,
    then falls back to other Latin-script languages in the list.  If none are
    present (e.g. "ja-zh"), returns ``languages[0]`` so the caller always gets
    a language that is actually in the combo.
    """
    latin_langs = ["en", "es", "pt", "fr"]
    for lang in latin_langs:
        if lang in languages:
            return lang
    # No Latin-script language in the combo -- fall back to first language
    return languages[0]


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
        from .portuguese import PortuguesePhonemizer  # noqa: PLC0415

        register_language("pt", PortuguesePhonemizer())
    except ImportError:
        pass
    try:
        from .french import FrenchPhonemizer  # noqa: PLC0415

        register_language("fr", FrenchPhonemizer())
    except ImportError:
        pass
    # Register ja-en bilingual combo (backward compatibility)
    # Also register under the canonical sorted key "en-ja" so that both
    # "ja-en" and "en-ja" resolve to the same instance.
    if "ja" in _REGISTRY and "en" in _REGISTRY:
        try:
            from .bilingual import BilingualPhonemizer  # noqa: PLC0415

            _bilingual_ja_en = BilingualPhonemizer(["ja", "en"])
            register_language("ja-en", _bilingual_ja_en)
            # Canonical sorted key: sorted(["ja","en"]) == ["en","ja"] → "en-ja"
            register_language("en-ja", _bilingual_ja_en)
        except ImportError:
            pass


_auto_register()
