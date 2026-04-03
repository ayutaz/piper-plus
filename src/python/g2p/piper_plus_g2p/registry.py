"""Language phonemizer registry.

This module provides two ways to interact with the registry:

1. **Recommended** -- Use :class:`PhonemizerRegistry` directly to create
   isolated registries (useful for testing or embedding scenarios)::

       registry = PhonemizerRegistry()
       registry.register("ja", JapanesePhonemizer())
       phonemizer = registry.get("ja")

2. **Module-level convenience functions** -- :func:`register_language`,
   :func:`get_phonemizer`, and :func:`available_languages` delegate to
   a default singleton :class:`PhonemizerRegistry` instance.  They are
   kept for backward compatibility::

       register_language("ja", JapanesePhonemizer())
       phonemizer = get_phonemizer("ja")
"""

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
    ("sv", ".swedish", "SwedishPhonemizer"),
]

# Human-readable skip reasons for languages with optional dependencies
_SKIP_REASONS: dict[str, str] = {
    "ja": "pyopenjtalk not installed",
    "en": "g2p_en not installed",
    "zh": "pypinyin not installed",
    "ko": "g2pk2 not installed",
}


class PhonemizerRegistry:
    """Registry that maps language codes to :class:`Phonemizer` instances.

    Each instance maintains its own isolated mapping.  For most
    applications the module-level convenience functions
    (:func:`register_language`, :func:`get_phonemizer`,
    :func:`available_languages`) are sufficient -- they delegate to a
    shared default instance created at import time.

    Create your own :class:`PhonemizerRegistry` when you need an
    isolated set of phonemizers (e.g. in tests or multi-tenant
    scenarios).
    """

    def __init__(self) -> None:
        self._registry: dict[str, Phonemizer] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, code: str, phonemizer: Phonemizer) -> None:
        """Register *phonemizer* under the language *code*.

        Parameters
        ----------
        code:
            ISO 639-1 language code (e.g. ``"ja"``, ``"en"``).
        phonemizer:
            A :class:`Phonemizer` instance.  A :class:`TypeError` is
            raised if *phonemizer* is not a :class:`Phonemizer` instance.

        Raises
        ------
        TypeError
            If *phonemizer* is not a :class:`Phonemizer` instance.
        """
        if not isinstance(phonemizer, Phonemizer):
            raise TypeError(
                f"Expected a Phonemizer instance, got {type(phonemizer).__name__}"
            )
        self._registry[code] = phonemizer

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, language: str) -> Phonemizer:
        """Return the :class:`Phonemizer` registered for *language*.

        Supports composite language codes (e.g. ``"ja-en-zh"``) which
        automatically create a :class:`MultilingualPhonemizer` wrapping
        the individual registered phonemizers.

        Parameters
        ----------
        language:
            A single language code (``"ja"``) or a composite code
            (``"ja-en-zh"``).

        Returns
        -------
        Phonemizer
            The registered phonemizer (or a newly created
            :class:`MultilingualPhonemizer` for composite codes).

        Raises
        ------
        ValueError
            If the language code (or any component of a composite code)
            is not registered.
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

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def available(self) -> list[str]:
        """Return a list of all registered language codes."""
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
# Backward-compatible module-level functions
# ------------------------------------------------------------------
# These convenience functions delegate to ``_default_registry``, the
# singleton :class:`PhonemizerRegistry` created at import time.
# They are kept for backward compatibility; prefer using
# :class:`PhonemizerRegistry` directly for new code.
# ------------------------------------------------------------------


def register_language(code: str, phonemizer: Phonemizer) -> None:
    """Register *phonemizer* under *code* in the default registry.

    This is a convenience wrapper around
    :meth:`PhonemizerRegistry.register` on the default singleton
    instance.  For new code, prefer creating and using a
    :class:`PhonemizerRegistry` directly.
    """
    _default_registry.register(code, phonemizer)


def get_phonemizer(language: str) -> Phonemizer:
    """Return the :class:`Phonemizer` for *language* from the default registry.

    This is a convenience wrapper around
    :meth:`PhonemizerRegistry.get` on the default singleton instance.
    For new code, prefer creating and using a
    :class:`PhonemizerRegistry` directly.

    Supports composite language codes (e.g. ``"ja-en-zh"``) -- see
    :meth:`PhonemizerRegistry.get` for details.
    """
    return _default_registry.get(language)


def available_languages() -> list[str]:
    """Return registered language codes from the default registry.

    This is a convenience wrapper around
    :meth:`PhonemizerRegistry.available` on the default singleton
    instance.  For new code, prefer creating and using a
    :class:`PhonemizerRegistry` directly.
    """
    return _default_registry.available()


# ------------------------------------------------------------------
# Auto-registration
# ------------------------------------------------------------------


def _auto_register() -> None:
    """Register available language phonemizers at import time.

    Built-in phonemizers are loaded from ``_LANGUAGE_TABLE``.
    Third-party phonemizers are discovered via the
    ``piper_plus_g2p.phonemizers`` entry-point group.
    """
    # Built-in phonemizers (table-driven)
    for code, module, class_name in _LANGUAGE_TABLE:
        try:
            mod = importlib.import_module(module, package=__package__)
            cls = getattr(mod, class_name)
            register_language(code, cls())
        except ModuleNotFoundError:
            reason = _SKIP_REASONS.get(code, "missing dependency")
            _LOGGER.info("Skipping %s: %s", code.upper(), reason)
        except ImportError:
            _LOGGER.warning(
                "Failed to import %s phonemizer from %s",
                code.upper(),
                module,
                exc_info=True,
            )

    # Third-party phonemizers via entry_points
    try:
        from importlib.metadata import entry_points  # noqa: PLC0415

        for ep in entry_points(group="piper_plus_g2p.phonemizers"):
            try:
                cls = ep.load()
                _default_registry.register(ep.name, cls())
            except Exception:
                _LOGGER.debug("Failed to load entry point %s", ep.name, exc_info=True)
    except Exception:
        pass


_auto_register()
