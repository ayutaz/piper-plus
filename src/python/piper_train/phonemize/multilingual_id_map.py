"""Unified phoneme ID map for multilingual models.

Generalizes bilingual_id_map.py to support N languages.
Merges phoneme inventories from multiple languages into a single ID space
with no collisions. Shared symbols get a single ID.
"""

from .jp_id_map import JAPANESE_PHONEMES, SPECIAL_TOKENS
from .token_mapper import register


__all__ = ["get_multilingual_id_map", "LANGUAGE_PHONEMES"]

# -----------------------------------------------------------------------
# Language-specific phoneme inventories
# Each language registers its unique phonemes here. Shared phonemes
# (e.g., "b", "d", "m") appear in multiple lists but get a single ID.
# -----------------------------------------------------------------------
LANGUAGE_PHONEMES: dict[str, list[str]] = {}


def _register_builtin_phonemes():
    """Register built-in language phoneme inventories."""
    # Japanese (always available)
    LANGUAGE_PHONEMES["ja"] = JAPANESE_PHONEMES

    # English
    try:
        from .bilingual_id_map import ENGLISH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["en"] = ENGLISH_PHONEMES
    except ImportError:
        pass

    # Chinese
    try:
        from .zh_id_map import CHINESE_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["zh"] = CHINESE_PHONEMES
    except ImportError:
        pass

    # Korean
    try:
        from .ko_id_map import KOREAN_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["ko"] = KOREAN_PHONEMES
    except ImportError:
        pass

    # Spanish
    try:
        from .es_id_map import SPANISH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["es"] = SPANISH_PHONEMES
    except ImportError:
        pass

    # Portuguese
    try:
        from .pt_id_map import PORTUGUESE_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["pt"] = PORTUGUESE_PHONEMES
    except ImportError:
        pass

    # French
    try:
        from .fr_id_map import FRENCH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["fr"] = FRENCH_PHONEMES
    except ImportError:
        pass


_register_builtin_phonemes()


def get_multilingual_id_map(languages: list[str]) -> dict[str, list[int]]:
    """Return a unified {symbol: [id]} map covering phonemes from all specified languages.

    ID layout:
      0-N_special:     shared special tokens (_, ^, $, ?, ?!, ?., ?~, #, [, ])
      next:            first language phonemes
      next:            second language unique phonemes
      ...

    Symbols shared between languages get a single ID from the first language
    that defines them.

    Parameters
    ----------
    languages : list[str]
        Language codes to include, e.g. ["ja", "en"] or ["ja", "en", "zh", "ko"].

    Returns
    -------
    dict[str, list[int]]
        Mapping from single-codepoint symbol to [id].
    """
    all_symbols: list[str] = []
    seen: set[str] = set()

    # Start with shared special tokens
    for s in SPECIAL_TOKENS:
        mapped = register(s)
        if mapped not in seen:
            all_symbols.append(mapped)
            seen.add(mapped)

    # Add phonemes from each language in order
    for lang in languages:
        phonemes = LANGUAGE_PHONEMES.get(lang)
        if phonemes is None:
            raise ValueError(
                f"Unknown language '{lang}' for multilingual ID map. "
                f"Available: {list(LANGUAGE_PHONEMES.keys())}"
            )
        for s in phonemes:
            mapped = register(s)
            if mapped not in seen:
                all_symbols.append(mapped)
                seen.add(mapped)

    # Build the ID map
    id_map: dict[str, list[int]] = {}
    for idx, symbol in enumerate(all_symbols):
        id_map[symbol] = [idx]
    return id_map
