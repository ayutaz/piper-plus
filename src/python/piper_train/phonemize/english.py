"""English G2P module using g2p-en (Apache-2.0 licensed).

Converts English text to phoneme IDs and prosody features without
requiring espeak-ng or piper-phonemize (GPL dependencies).
"""

import logging
import re
from dataclasses import dataclass


_LOGGER = logging.getLogger(__name__)

__all__ = ["phonemize_english", "phonemize_english_with_prosody", "EnglishProsodyInfo"]

# ARPAbet to espeak-compatible IPA mapping
ARPABET_TO_IPA: dict[str, str] = {
    "AA": "ɑː",
    "AE": "æ",
    "AH": "ʌ",
    "AO": "ɔː",
    "AW": "aʊ",
    "AY": "aɪ",
    "B": "b",
    "CH": "tʃ",
    "D": "d",
    "DH": "ð",
    "EH": "ɛ",
    "ER": "ɜːr",
    "EY": "eɪ",
    "F": "f",
    "G": "ɡ",
    "HH": "h",
    "IH": "ɪ",
    "IY": "iː",
    "JH": "dʒ",
    "K": "k",
    "L": "l",
    "M": "m",
    "N": "n",
    "NG": "ŋ",
    "OW": "oʊ",
    "OY": "ɔɪ",
    "P": "p",
    "R": "ɹ",
    "S": "s",
    "SH": "ʃ",
    "T": "t",
    "TH": "θ",
    "UH": "ʊ",
    "UW": "uː",
    "V": "v",
    "W": "w",
    "Y": "j",
    "Z": "z",
    "ZH": "ʒ",
}

# Unstressed AH maps to schwa
_AH_UNSTRESSED_IPA = "ə"

# Regex to split ARPAbet token into base + optional stress digit
_RE_ARPABET = re.compile(r"^([A-Z]+)(\d)?$")


@dataclass
class EnglishProsodyInfo:
    """Prosody information for English phonemes."""

    a1: int  # Fixed at 0 (no accent nucleus concept in English)
    a2: int  # Stress level: 0=none, 1=secondary, 2=primary
    a3: int  # Number of phonemes in the word


def _g2p_en_to_arpabet_tokens(text: str) -> list[list[str]]:
    """Convert text to ARPAbet tokens using g2p-en, grouped by word.

    Returns a list of words, each word being a list of ARPAbet tokens
    (e.g. ["HH", "AH0", "L", "OW1"]).
    """
    from g2p_en import G2p  # noqa: PLC0415

    g2p = G2p()
    raw = g2p(text)

    # g2p-en returns a flat list of phonemes with spaces as word boundaries
    words: list[list[str]] = []
    current_word: list[str] = []
    for token in raw:
        if token == " ":
            if current_word:
                words.append(current_word)
                current_word = []
        else:
            current_word.append(token)
    if current_word:
        words.append(current_word)

    return words


def _arpabet_to_ipa(token: str) -> tuple[str, int]:
    """Convert a single ARPAbet token to IPA.

    Returns (ipa_string, stress) where stress is 0/1/2 or -1 for consonants.
    """
    m = _RE_ARPABET.match(token)
    if not m:
        # Punctuation or unknown - return as-is
        return token, -1

    base = m.group(1)
    stress_str = m.group(2)
    stress = int(stress_str) if stress_str is not None else -1

    # Special case: unstressed AH → schwa
    if base == "AH" and stress == 0:
        return _AH_UNSTRESSED_IPA, stress

    ipa = ARPABET_TO_IPA.get(base)
    if ipa is None:
        _LOGGER.warning("Unknown ARPAbet symbol: %s", base)
        return token, stress

    return ipa, stress


def phonemize_english_with_prosody(
    text: str,
) -> tuple[list[str], list[EnglishProsodyInfo]]:
    """Convert English text to phoneme list and prosody features.

    Returns:
        (phonemes, prosody_info_list) where each phoneme has corresponding
        prosody info with a1=0, a2=stress-based, a3=word phoneme count.
    """
    words = _g2p_en_to_arpabet_tokens(text)

    phonemes: list[str] = []
    prosody_list: list[EnglishProsodyInfo] = []

    for word_tokens in words:
        # Convert all tokens in the word to IPA
        word_ipas: list[tuple[str, int]] = []
        for token in word_tokens:
            ipa, stress = _arpabet_to_ipa(token)
            word_ipas.append((ipa, stress))

        word_phoneme_count = len(word_ipas)

        for ipa, stress in word_ipas:
            # stress → A2: primary(1)→2, secondary(2)→1, none(0)→0, consonant(-1)→0
            if stress == 1:
                a2 = 2
            elif stress == 2:
                a2 = 1
            else:
                a2 = 0

            # Each IPA character becomes a separate phoneme token
            for ch in ipa:
                prosody_list.append(
                    EnglishProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count)
                )
                phonemes.append(ch)

    return phonemes, prosody_list


def phonemize_english(text: str) -> list[str]:
    """Convert English text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_english_with_prosody(text)
    return phonemes
