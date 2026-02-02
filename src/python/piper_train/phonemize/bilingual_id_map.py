"""Unified phoneme ID map for bilingual (JA+EN) models.

Merges Japanese and English phoneme inventories into a single ID space
with no collisions. Shared special tokens (_, ^, $) use common IDs.
"""

from .jp_id_map import JAPANESE_PHONEMES, SPECIAL_TOKENS
from .token_mapper import register

__all__ = ["get_bilingual_id_map", "ENGLISH_PHONEMES"]

# -----------------------------------------------------------------------
# English phoneme inventory (IPA symbols produced by EnglishPhonemizer)
# -----------------------------------------------------------------------
# These are the IPA characters that appear in english.py output.
# They do NOT overlap with the Japanese set (Japanese uses plain Latin
# letters like "a", "k"; English uses IPA like "ɑ", "æ", "ʃ").
# -----------------------------------------------------------------------
ENGLISH_PHONEMES: list[str] = [
    # Vowels (monophthongs)
    "ɑ",
    "æ",
    "ʌ",
    "ə",
    "ɔː",
    "ɛ",
    "ɚ",
    "ɜː",
    "ɪ",
    "iː",
    "ʊ",
    "uː",
    # Diphthongs
    "aʊ",
    "aɪ",
    "eɪ",
    "oʊ",
    "ɔɪ",
    # Combined vowel+r
    "ɑːɹ",
    # Consonants
    "b",  # shared with JA but same symbol, same ID
    "d",  # shared
    "f",  # shared
    "h",  # shared
    "k",  # shared
    "l",
    "m",  # shared
    "n",  # shared
    "p",  # shared
    "s",  # shared
    "t",  # shared
    "w",  # shared
    "j",  # shared (English Y → j)
    "v",  # shared
    "z",  # shared
    "ɡ",  # note: IPA ɡ (U+0261), not ASCII g
    "ŋ",
    "ɹ",
    "ʃ",
    "ʒ",
    "θ",
    "ð",
    "tʃ",
    "dʒ",
    # Stress markers
    "ˈ",
    "ˌ",
    # Word boundary (space)
    " ",
    # Punctuation (passed through by EnglishPhonemizer)
    ",",
    ".",
    ";",
    ":",
    "!",
    "?",  # already in SPECIAL_TOKENS but also used standalone by EN
]


def get_bilingual_id_map() -> dict[str, list[int]]:
    """Return a unified {symbol: [id]} map covering both JA and EN phonemes.

    ID layout:
      0-N_ja_special:  shared special tokens (_, ^, $, ?, ?!, ?., ?~, #, [, ])
      next:            Japanese phonemes (a, i, u, e, o, ...)
      next:            English-only phonemes (ɑ, æ, ʌ, ...)

    Symbols shared between JA and EN (b, d, f, k, m, n, p, s, t, w, j, v, z)
    get a single ID from the Japanese block (they appear in JAPANESE_PHONEMES).
    """
    # Start with shared special tokens + Japanese phonemes (same as jp_id_map)
    all_symbols: list[str] = []
    seen: set[str] = set()

    for s in SPECIAL_TOKENS + JAPANESE_PHONEMES:
        mapped = register(s)
        if mapped not in seen:
            all_symbols.append(mapped)
            seen.add(mapped)

    # Add English-only phonemes (skip any already covered)
    for s in ENGLISH_PHONEMES:
        mapped = register(s)
        if mapped not in seen:
            all_symbols.append(mapped)
            seen.add(mapped)

    # Build the ID map
    id_map: dict[str, list[int]] = {}
    for idx, symbol in enumerate(all_symbols):
        id_map[symbol] = [idx]
    return id_map
