"""Korean phoneme inventory for Piper TTS.

Only phonemes unique to Korean that are NOT already present in the
JA + EN inventories are listed here. Shared phonemes (a, i, u, e, o,
k, t, p, s, h, m, n, l, ŋ, w, j, ʌ, ɛ, etc.) are deduplicated
by multilingual_id_map.py.
"""

from .token_mapper import register

__all__ = ["KOREAN_PHONEMES"]


# Korean-unique phonemes (IPA).
# Multi-char tokens are registered via register() which assigns
# PUA codepoints dynamically (or reuses existing mappings).
KOREAN_PHONEMES: list[str] = [
    # Aspirated consonants
    "pʰ",
    "tʰ",
    "kʰ",
    # Tense consonants (fortis / 경음)
    "p͈",
    "t͈",
    "k͈",
    "s͈",
    # Affricates
    "tɕ",
    "tɕʰ",
    "t͈ɕ",
    # Unreleased finals (내파음)
    "k̚",
    "t̚",
    "p̚",
    # Vowels unique to Korean
    "ɯ",  # close back unrounded vowel (ㅡ)
    "ø",  # close-mid front rounded vowel (ㅚ)
    # Consonants / glides
    "ɾ",  # alveolar flap (ㄹ initial)
    "ɰ",  # velar approximant (ㅢ first element)
]

# Register multi-character tokens to get PUA codepoints
for _token in KOREAN_PHONEMES:
    register(_token)
