"""Swedish phoneme inventory for Piper TTS.

Only phonemes unique to Swedish that are NOT already present in the
JA + EN inventories are listed here. Shared phonemes are deduplicated
by multilingual_id_map.py.
"""

from .token_mapper import register


__all__ = ["SWEDISH_PHONEMES"]

# -------------------------------------------------------------------------
# Swedish-unique phonemes (IPA)
# -------------------------------------------------------------------------
# Shared with JA/EN (NOT listed here):
#   a, e, i, o, u — vowels (JA)
#   b, d, f, g, h, j, k, l, m, n, p, r, s, t, v — consonants (JA/EN)
#   ŋ — velar nasal (EN)
#   ɛ, ɪ, ʊ — vowels (EN)
# -------------------------------------------------------------------------

SWEDISH_PHONEMES: list[str] = [
    # --- Single-codepoint phonemes (no PUA needed) ---
    # Retroflex consonants
    "ɖ",  # U+0256  retroflex voiced plosive (rd)
    "ʈ",  # U+0288  retroflex voiceless plosive (rt)
    "ɳ",  # U+0273  retroflex nasal (rn)
    "ɭ",  # U+026D  retroflex lateral (rl)
    # Special fricatives
    "ɧ",  # U+0267  sj-sound (voiceless dorso-palatal/velar fricative)
    # Vowels unique to Swedish (single codepoint)
    "ɵ",  # U+0275  close-mid central rounded (not in JA/EN/ZH)
    "ʏ",  # U+028F  near-close front rounded
    "œ",  # U+0153  open-mid front rounded
    "ɑ",  # U+0251  open back unrounded
    "ø",  # U+00F8  close-mid front rounded
    # --- Long vowels (multi-codepoint → PUA) ---
    # These are registered as fixed PUA in token_mapper.py (0xE059-0xE061)
    "iː",  # 0xE059  close front unrounded long
    "yː",  # 0xE05A  close front rounded long
    "eː",  # 0xE05B  close-mid front unrounded long
    "ɛː",  # 0xE05C  open-mid front unrounded long
    "øː",  # 0xE05D  close-mid front rounded long
    "ɑː",  # 0xE05E  open back unrounded long
    "oː",  # 0xE05F  close-mid back rounded long
    "uː",  # 0xE060  close back rounded long
    "ʉː",  # 0xE061  close central rounded long
]

# Register multi-character tokens to get PUA codepoints
for _token in SWEDISH_PHONEMES:
    register(_token)
