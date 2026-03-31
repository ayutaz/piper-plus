"""Language phonemizer registry."""

from __future__ import annotations

import importlib
import logging

from .base import Phonemizer

_LOGGER = logging.getLogger(__name__)

# Latin-script language priority for default_latin_language detection
_LATIN_PRIORITY = ("en", "es", "pt", "fr")

# Table of built-in language phonemizers: (code, module, class_name)
_LANGUAGE_TABLE = [
    ("ja", ".japanese", "JapanesePhonemizer"),
    ("en", ".english", "EnglishPhonemizer"),
    ("zh", ".chinese", "ChinesePhonemizer"),
    ("ko", ".korean", "KoreanPhonemizer"),
    ("es", ".spanish", "SpanishPhonemizer"),
    ("fr", ".french", "FrenchPhonemizer"),
    ("pt", ".portuguese", "PortuguesePhonemizer"),
]


class PhonemizerRegistry:
    """Registry that maps language codes to ``Phonemizer`` instances."""

    def __init__(self) -> None:
        self._registry: dict[str, Phonemizer] = {}

    def register(self, code: str, phonemizer: Phonemizer) -> None:
        """Register a phonemizer for a language code."""
        self._registry[code] = phonemizer

    def get(self, language: str) -> Phonemizer:
        """Get the phonemizer for a language code.

        Supports composite language codes (e.g. "ja-en-zh") which
        automatically create a ``MultilingualPhonemizer`` wrapping the
        individual registered phonemizers.
        """
        if language in self._registry:
            return self._registry[language]

        # Composite code: "ja-en-zh" etc.
        parts = language.split("-")
        if len(parts) >= 2:
            canonical_parts = sorted(parts)
            canonical_key = "-".join(canonical_parts)
            if canonical_key in self._registry:
                self._registry[language] = self._registry[canonical_key]
                return self._registry[canonical_key]

            missing = [p for p in canonical_parts if p not in self._registry]
            if not missing:
                from .multilingual import MultilingualPhonemizer  # noqa: PLC0415

                phonemizer = MultilingualPhonemizer(
                    canonical_parts,
                    default_latin_language=_detect_default_latin(canonical_parts),
                )
                self._registry[canonical_key] = phonemizer
                if language != canonical_key:
                    self._registry[language] = phonemizer
                return phonemizer

            raise ValueError(
                f"Missing language(s) {missing} for composite code '{language}'. "
                f"Available: {list(self._registry.keys())}"
            )

        raise ValueError(
            f"Unsupported language: {language}. "
            f"Available: {list(self._registry.keys())}"
        )

    def available(self) -> list[str]:
        """Return list of registered language codes."""
        return list(self._registry.keys())


# Default singleton instance
_default_registry = PhonemizerRegistry()


def _detect_default_latin(parts: list[str]) -> str:
    """Detect the best default Latin-script language from a list of codes.

    Priority order: en > es > pt > fr.  Falls back to the first language
    in the list if no Latin-script language is present.
    """
    for lang in _LATIN_PRIORITY:
        if lang in parts:
            return lang
    return parts[0]


# ------------------------------------------------------------------
# Backward-compatible module-level functions (delegate to _default_registry)
# ------------------------------------------------------------------


def register_language(code: str, phonemizer: Phonemizer) -> None:
    """Register a phonemizer for a language code."""
    _default_registry.register(code, phonemizer)


def get_phonemizer(language: str) -> Phonemizer:
    """Get the phonemizer for a language code.

    Supports composite language codes (e.g. "ja-en-zh") which
    automatically create a ``MultilingualPhonemizer`` wrapping the
    individual registered phonemizers.
    """
    return _default_registry.get(language)


def available_languages() -> list[str]:
    """Return list of registered language codes."""
    return _default_registry.available()


# ------------------------------------------------------------------
# Auto-registration
# ------------------------------------------------------------------


def _auto_register() -> None:
    """Register available language phonemizers at import time.

    Built-in phonemizers are loaded from ``_LANGUAGE_TABLE``.
    Third-party phonemizers are discovered via the
    ``piper_g2p.phonemizers`` entry-point group.
    """
    # Built-in phonemizers (table-driven)
    for code, module, class_name in _LANGUAGE_TABLE:
        try:
            mod = importlib.import_module(module, package=__package__)
            cls = getattr(mod, class_name)
            register_language(code, cls())
        except ImportError:
            pass

    # Third-party phonemizers via entry_points
    try:
        from importlib.metadata import entry_points  # noqa: PLC0415

        for ep in entry_points(group="piper_g2p.phonemizers"):
            try:
                cls = ep.load()
                _default_registry.register(ep.name, cls())
            except Exception:
                _LOGGER.debug("Failed to load entry point %s", ep.name, exc_info=True)
    except Exception:
        pass


_auto_register()
