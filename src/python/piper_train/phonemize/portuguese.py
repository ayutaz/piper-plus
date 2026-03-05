"""Rule-based Brazilian Portuguese phonemizer for Piper TTS.

Converts Brazilian Portuguese text to IPA phonemes using grapheme-to-phoneme
rules. No external G2P engine required.
"""

import logging
import re
import unicodedata

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "phonemize_portuguese",
    "phonemize_portuguese_with_prosody",
    "PortuguesePhonemizer",
]

# Punctuation characters (attached to previous word, no space before)
_PUNCTUATION = set(",.;:!?¡¿—–…")

# Vowel letters (for voicing/nasalization context checks)
_VOWELS = set("aeiouáàâãéêíóôõúü")

# Accent-to-base mapping for stress detection
_ACCENTED = {
    "á": "a",
    "à": "a",
    "â": "a",
    "ã": "a",
    "é": "e",
    "ê": "e",
    "í": "i",
    "ó": "o",
    "ô": "o",
    "õ": "o",
    "ú": "u",
    "ü": "u",
}

# Acute/grave accents indicate stressed open vowels
_STRESS_ACCENTS = set("áéíóú")
# Circumflex indicates stressed closed vowels
_CIRCUMFLEX = set("âêô")
# Tilde indicates nasal vowels (also stressed when it's the only accent)
_TILDE = set("ãõ")


def _normalize(text: str) -> str:
    """Normalize text: lowercase, normalize unicode, strip extra whitespace."""
    text = text.strip()
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text


def _is_vowel_char(ch: str) -> bool:
    return ch in _VOWELS


def _has_accent(word: str) -> bool:
    """Check if word has any accent mark."""
    for ch in word:
        if ch in _ACCENTED:
            return True
    return False


def _find_stress_position(word: str) -> int:
    """Find the stressed syllable index (0-based from end).

    Returns the position of the stressed vowel group from the end of the word.
    Portuguese stress rules:
    - Words with acute/circumflex/tilde accent: stress on accented syllable
    - Words ending in a, e, o, am, em, ens: penultimate (paroxytone)
    - Words ending in consonant (except s), i, u: ultimate (oxytone)
    """
    # Find accented vowel position
    vowel_positions = []
    accent_pos = -1
    for i, ch in enumerate(word):
        if ch in _VOWELS:
            vowel_positions.append(i)
            if ch in _STRESS_ACCENTS or ch in _CIRCUMFLEX or ch in _TILDE:
                accent_pos = len(vowel_positions) - 1

    if not vowel_positions:
        return 0

    if accent_pos >= 0:
        # Stress on accented syllable (convert to from-end index)
        return len(vowel_positions) - 1 - accent_pos

    # Default rules based on ending
    stripped = word.rstrip("s")
    if stripped.endswith(("a", "e", "o", "am", "em")):
        # Paroxytone: penultimate syllable
        return min(1, len(vowel_positions) - 1)
    else:
        # Oxytone: last syllable
        return 0


def _convert_word(word: str) -> tuple[list[str], int]:
    """Convert a Portuguese word to IPA phonemes.

    Returns (phonemes, stress_vowel_index) where stress_vowel_index is the
    index into phonemes of the primary stressed vowel.
    """
    phonemes: list[str] = []
    stress_idx = -1
    i = 0
    n = len(word)

    # Determine which vowel group gets stress
    stress_from_end = _find_stress_position(word)
    vowel_group_count = sum(1 for ch in word if ch in _VOWELS)
    stress_vowel_target = vowel_group_count - 1 - stress_from_end
    current_vowel_group = 0

    while i < n:
        ch = word[i]

        # --- Multi-character sequences (check longest first) ---

        # "nh" → ɲ
        if ch == "n" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ɲ")
            i += 2
            continue

        # "lh" → ʎ
        if ch == "l" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ʎ")
            i += 2
            continue

        # "ch" → ʃ
        if ch == "c" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ʃ")
            i += 2
            continue

        # "rr" → ʁ
        if ch == "r" and i + 1 < n and word[i + 1] == "r":
            phonemes.append("ʁ")
            i += 2
            continue

        # "ss" → s
        if ch == "s" and i + 1 < n and word[i + 1] == "s":
            phonemes.append("s")
            i += 2
            continue

        # "qu" before e/i → k
        if ch == "q" and i + 1 < n and word[i + 1] == "u":
            phonemes.append("k")
            # Skip 'u' before e/i (silent), keep it before a/o
            if i + 2 < n and word[i + 2] in "ei":
                i += 2
            else:
                i += 2
            continue

        # "gu" before e/i → ɡ (u is silent)
        if ch == "g" and i + 1 < n and word[i + 1] == "u":
            if i + 2 < n and word[i + 2] in "eiéê":
                phonemes.append("ɡ")
                i += 2
                continue

        # "ou" → o (common BR reduction)
        if ch == "o" and i + 1 < n and word[i + 1] == "u":
            is_stressed = current_vowel_group == stress_vowel_target
            if is_stressed:
                stress_idx = len(phonemes)
            phonemes.append("o")
            current_vowel_group += 1
            # Skip the 'u' as well but count it as vowel group
            i += 2
            current_vowel_group += 1
            continue

        # --- Consonants ---

        if ch == "r":
            # Initial r or after n/l/s → ʁ
            if i == 0 or (i > 0 and word[i - 1] in "nls"):
                phonemes.append("ʁ")
            else:
                # Intervocalic r → ɾ (tap)
                phonemes.append("ɾ")
            i += 1
            continue

        if ch == "s":
            # Intervocalic s → z
            if (
                i > 0
                and i + 1 < n
                and _is_vowel_char(word[i - 1])
                and _is_vowel_char(word[i + 1])
            ):
                phonemes.append("z")
            else:
                phonemes.append("s")
            i += 1
            continue

        if ch == "x":
            # Common x rules (simplified):
            # Initial or after "en" → ʃ, between vowels → ks or z or s
            if i == 0:
                phonemes.append("ʃ")
            elif i > 0 and word[i - 1] in "aeiou" and i + 1 < n and word[i + 1] in "aeiou":
                phonemes.append("z")
            else:
                phonemes.append("ʃ")
            i += 1
            continue

        if ch == "c":
            # c before e/i → s, otherwise → k
            if i + 1 < n and word[i + 1] in "eiéêí":
                phonemes.append("s")
            else:
                phonemes.append("k")
            i += 1
            continue

        if ch == "ç":
            phonemes.append("s")
            i += 1
            continue

        if ch == "g":
            # g before e/i → ʒ, otherwise → ɡ
            if i + 1 < n and word[i + 1] in "eiéêí":
                phonemes.append("ʒ")
            else:
                phonemes.append("ɡ")
            i += 1
            continue

        if ch == "j":
            phonemes.append("ʒ")
            i += 1
            continue

        if ch == "t":
            # Brazilian Portuguese: t before i → tʃ
            if i + 1 < n and word[i + 1] in "ií":
                phonemes.append("t")
                phonemes.append("ʃ")
            else:
                phonemes.append("t")
            i += 1
            continue

        if ch == "d":
            # Brazilian Portuguese: d before i → dʒ
            if i + 1 < n and word[i + 1] in "ií":
                phonemes.append("d")
                phonemes.append("ʒ")
            else:
                phonemes.append("d")
            i += 1
            continue

        if ch == "h":
            # h is silent in Portuguese (except in digraphs already handled)
            i += 1
            continue

        # Simple consonant mappings
        if ch in "bfklmnpv":
            phonemes.append(ch)
            i += 1
            continue

        if ch == "z":
            phonemes.append("z")
            i += 1
            continue

        if ch == "w":
            phonemes.append("w")
            i += 1
            continue

        # --- Vowels ---

        if ch in _VOWELS:
            is_stressed = current_vowel_group == stress_vowel_target
            base = _ACCENTED.get(ch, ch)

            # Check for nasalization: tilde or vowel before n/m + consonant/end
            is_nasal = False
            if ch in _TILDE:
                is_nasal = True
            elif i + 1 < n and word[i + 1] in "nm":
                # Nasal if n/m is followed by consonant or end of word
                if i + 2 >= n:
                    is_nasal = True
                elif not _is_vowel_char(word[i + 2]):
                    is_nasal = True

            if is_nasal:
                nasal_map = {"a": "ã", "e": "ẽ", "i": "ĩ", "o": "õ", "u": "ũ"}
                phoneme = nasal_map.get(base, base)
            else:
                # Open vs closed vowels based on accent
                if ch in _STRESS_ACCENTS:
                    # Acute accent = open vowel
                    vowel_map = {"a": "a", "e": "ɛ", "i": "i", "o": "ɔ", "u": "u"}
                    phoneme = vowel_map.get(base, base)
                elif ch in _CIRCUMFLEX:
                    # Circumflex = closed vowel
                    phoneme = base
                else:
                    phoneme = base

            if is_stressed:
                stress_idx = len(phonemes)
            phonemes.append(phoneme)
            current_vowel_group += 1
            i += 1
            continue

        # Punctuation or unknown: pass through
        if ch in _PUNCTUATION:
            phonemes.append(ch)
            i += 1
            continue

        # Skip unknown characters
        i += 1

    return phonemes, stress_idx


def _split_words(text: str) -> list[str]:
    """Split text into words and punctuation tokens."""
    tokens = re.findall(r"[a-záàâãéêíóôõúüçñ]+|[,.;:!?¡¿—–…]", text, re.IGNORECASE)
    return tokens


def phonemize_portuguese_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Brazilian Portuguese text to phoneme list and prosody features.

    Returns:
        (phonemes, prosody_list) with ProsodyInfo for each phoneme.
        a1=0, a2=stress level (0 or 2), a3=word phoneme count.
    """
    text = _normalize(text)
    tokens = _split_words(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    for token in tokens:
        is_punct = all(ch in _PUNCTUATION for ch in token)

        if not is_punct and need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        if is_punct:
            for ch in token:
                phonemes.append(ch)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
        else:
            word_phonemes, stress_idx = _convert_word(token)
            word_phoneme_count = len(word_phonemes)

            for j, ph in enumerate(word_phonemes):
                a2 = 2 if j == stress_idx else 0
                phonemes.append(ph)
                prosody_list.append(
                    ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count)
                )

        need_space = True

    return phonemes, prosody_list


def phonemize_portuguese(text: str) -> list[str]:
    """Convert Brazilian Portuguese text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_portuguese_with_prosody(text)
    return phonemes


class PortuguesePhonemizer(Phonemizer):
    """Brazilian Portuguese rule-based phonemizer."""

    def phonemize(self, text: str) -> list[str]:
        return phonemize_portuguese(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_portuguese_with_prosody(text)

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        return None

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding (espeak-ng compat)."""
        pad_ids = phoneme_id_map.get("_", [0])
        bos_ids = phoneme_id_map.get("^")
        eos_ids = phoneme_id_map.get("$")

        padded_ids: list[int] = []
        padded_prosody: list[dict | None] = []
        for phoneme_id, prosody_feature in zip(
            phoneme_ids, prosody_features, strict=True
        ):
            padded_ids.append(phoneme_id)
            padded_prosody.append(prosody_feature)
            padded_ids.extend(pad_ids)
            padded_prosody.extend([None] * len(pad_ids))

        phoneme_ids = padded_ids
        prosody_features = padded_prosody

        if bos_ids:
            phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
            prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
