"""Spanish phoneme inventory for Piper TTS.

Only phonemes NOT already present in Japanese (jp_id_map.py) or English
(bilingual_id_map.py) are listed here.  Shared symbols are deduplicated
automatically when building the unified ID map.
"""

from .token_mapper import register

__all__ = ["get_spanish_id_map", "SPANISH_PHONEMES"]

# -----------------------------------------------------------------------
# Spanish-only phonemes (IPA symbols not in JA or EN inventories)
# -----------------------------------------------------------------------
# Shared with JA/EN (NOT listed here):
#   a, e, i, o, u          — vowels (JA)
#   b, d, f, k, l, m, n,   — consonants (JA+EN)
#   p, s, t, w, j, v, z
#   ɡ, tʃ, ˈ, ˌ, ː        — EN
#   θ, ð                   — EN (also used in Peninsular Spanish)
#   " ", ",", ".", etc.     — punctuation (EN)
#
# Spanish-ONLY phonemes that need new IDs:
SPANISH_PHONEMES: list[str] = [
    "ɲ",   # ñ (palatal nasal)
    "ɾ",   # tap/flap r (single r between vowels)
    "rr",  # trill r (rr, word-initial r) — multi-char, needs PUA
    "β",   # allophone of /b/ (intervocalic)
    "ɣ",   # allophone of /ɡ/ (intervocalic)
    "x",   # jota (/x/ as in "jardín")
    "ʝ",   # palatal fricative (y, ll — yeísmo)
]


def get_spanish_id_map() -> dict[str, list[int]]:
    """Return a mapping {symbol: [id]} for Spanish-only phonemes.

    This is used by the trilingual ID map builder to extend the
    bilingual (JA+EN) map with Spanish phonemes.
    """
    symbols: list[str] = [register(s) for s in SPANISH_PHONEMES]
    id_map: dict[str, list[int]] = {}
    for idx, symbol in enumerate(symbols):
        id_map[symbol] = [idx]
    return id_map
