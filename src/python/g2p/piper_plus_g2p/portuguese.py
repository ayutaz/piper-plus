"""Rule-based Brazilian Portuguese phonemizer for piper-g2p.

Converts Brazilian Portuguese text to IPA phonemes using grapheme-to-phoneme
rules. No external G2P engine required.

Known limitations
-----------------
* **Brazilian Portuguese (PT-BR) only** -- European Portuguese (PT-PT)
  phonology differs significantly (e.g. vowel reduction patterns,
  sibilant realisations, absence of /tʃ dʒ/ palatalisation) and is
  not modelled.
* The ``x`` grapheme is highly irregular in Portuguese; only a simplified
  positional heuristic is applied (initial/post-consonant -> /ʃ/,
  intervocalic -> /z/).
* Vowel harmony and pretonic mid-vowel raising are not implemented.
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
_PUNCTUATION = set(",.;:!?\u00a1\u00bf\u2014\u2013\u2026")

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

# IPA vowel phonemes (oral, for reduction checks in post-processing)
_IPA_ORAL_VOWELS = set("aeioɛɔu")

# IPA nasal vowel phonemes
_IPA_NASAL_VOWELS = set("ãẽĩõũ")

# IPA vowel phonemes (all)
_IPA_VOWELS = _IPA_ORAL_VOWELS | _IPA_NASAL_VOWELS

# IPA consonant phonemes (for coda-l detection)
_IPA_CONSONANTS = set("bcdfɡhjklmnpɲɾʁsʃtʎvwzʒ")


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


def _is_intervocalic(i: int, word: str) -> bool:
    """Return True if position i in word has a vowel immediately before and after.

    Used for context-dependent r: intervocalic r -> tap, coda r -> uvular.
    """
    if i <= 0 or i >= len(word) - 1:
        # Cannot be intervocalic at word edge
        return False
    return _is_vowel_char(word[i - 1]) and _is_vowel_char(word[i + 1])


def _has_accent(word: str) -> bool:
    """Check if word has any accent mark."""
    return any(ch in _ACCENTED for ch in word)


def _count_vowel_groups(word: str) -> int:
    """Count vowel groups in a word, properly handling digraphs.

    Digraphs like 'ou', 'qu' (before e/i), and 'gu' (before e/i) consume
    two characters but may count differently for vowel group tracking.
    """
    count = 0
    i = 0
    n = len(word)
    while i < n:
        ch = word[i]
        # Handle 'qu' digraph: u is silent before e/i, produces /kw/ before a/o
        if ch == "q" and i + 1 < n and word[i + 1] == "u":
            if i + 2 < n and word[i + 2] in "eiéêí":
                # qu before e/i: u is silent, skip both q and u
                i += 2
                continue
            else:
                # qu before a/o: u is pronounced as /w/ glide (consonant),
                # not a vowel group; skip both q and u
                i += 2
                continue
        # Handle 'gu' digraph: u is silent before e/i
        if (
            ch == "g"
            and i + 1 < n
            and word[i + 1] == "u"
            and i + 2 < n
            and word[i + 2] in "eiéêí"
        ):
            # gu before e/i: u is silent, skip both g and u
            i += 2
            continue
        # Handle 'ou' diphthong: two vowel letters but one vowel group
        if ch == "o" and i + 1 < n and word[i + 1] == "u":
            count += 1
            i += 2
            continue
        if ch in _VOWELS:
            count += 1
        i += 1
    return count


def _find_stress_position(word: str) -> int:
    """Find the stressed syllable index (0-based from end).

    Returns the position of the stressed vowel group from the end of the word.
    Portuguese stress rules:
    - Words with acute/circumflex/tilde accent: stress on accented syllable
    - Words ending in a, e, o, am, em, en, ens: penultimate (paroxytone)
    - Words ending in consonant (except s), i, u: ultimate (oxytone)
    """
    # Count vowel groups properly (handling digraphs)
    vowel_group_count = _count_vowel_groups(word)

    # Find accented vowel group position (digraph-aware)
    accent_group = -1
    current_group = 0
    i = 0
    n = len(word)
    while i < n:
        ch = word[i]
        # Skip digraphs the same way as _count_vowel_groups
        if ch == "q" and i + 1 < n and word[i + 1] == "u":
            if i + 2 < n and word[i + 2] in "eiéêí":
                i += 2
                continue
            else:
                # qu before a/o: u is /w/ glide, not a vowel group
                i += 2
                continue
        if (
            ch == "g"
            and i + 1 < n
            and word[i + 1] == "u"
            and i + 2 < n
            and word[i + 2] in "eiéêí"
        ):
            i += 2
            continue
        if ch == "o" and i + 1 < n and word[i + 1] == "u":
            # Check if either letter in 'ou' is accented (e.g. 'óu')
            if ch in _STRESS_ACCENTS or ch in _CIRCUMFLEX or ch in _TILDE:
                accent_group = current_group
            current_group += 1
            i += 2
            continue
        if ch in _VOWELS:
            if ch in _STRESS_ACCENTS or ch in _CIRCUMFLEX or ch in _TILDE:
                accent_group = current_group
            current_group += 1
        i += 1

    if vowel_group_count == 0:
        return 0

    if accent_group >= 0:
        # Stress on accented syllable (convert to from-end index)
        return vowel_group_count - 1 - accent_group

    # Default rules based on ending
    stripped = word.rstrip("s")
    if stripped.endswith(("a", "e", "o", "am", "em", "en")):
        # Paroxytone: penultimate syllable
        # "ens" -> strip s -> "en" -> paroxytone
        return min(1, vowel_group_count - 1)
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

    # Determine which vowel group gets stress (using digraph-aware counting)
    stress_from_end = _find_stress_position(word)
    vowel_group_count = _count_vowel_groups(word)
    stress_vowel_target = vowel_group_count - 1 - stress_from_end
    current_vowel_group = 0

    while i < n:
        ch = word[i]

        # --- Multi-character sequences (check longest first) ---

        # "nh" -> ɲ
        if ch == "n" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ɲ")
            i += 2
            continue

        # "lh" -> ʎ
        if ch == "l" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ʎ")
            i += 2
            continue

        # "ch" -> ʃ
        if ch == "c" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ʃ")
            i += 2
            continue

        # "rr" -> ʁ
        if ch == "r" and i + 1 < n and word[i + 1] == "r":
            phonemes.append("ʁ")
            i += 2
            continue

        # "ss" -> s
        if ch == "s" and i + 1 < n and word[i + 1] == "s":
            phonemes.append("s")
            i += 2
            continue

        # "sc" before e/i -> s (no geminate; like Spanish seseo)
        if (
            ch == "s"
            and i + 1 < n
            and word[i + 1] == "c"
            and i + 2 < n
            and word[i + 2] in "eiéêí"
        ):
            phonemes.append("s")
            i += 2  # skip "sc", vowel handled next
            continue

        # "qu" before e/i -> k (u is silent)
        # "qu" before a/o -> kw (u is pronounced)
        if ch == "q" and i + 1 < n and word[i + 1] == "u":
            phonemes.append("k")
            if i + 2 < n and word[i + 2] in "eiéêí":
                # Silent u before e/i
                i += 2
            else:
                # Pronounced u before a/o -> append w glide
                phonemes.append("w")
                i += 2
            continue

        # "gu" before e/i -> ɡ (u is silent)
        if (
            ch == "g"
            and i + 1 < n
            and word[i + 1] == "u"
            and i + 2 < n
            and word[i + 2] in "eiéêí"
        ):
            phonemes.append("ɡ")
            i += 2
            continue

        # "ou" -> o (common BR reduction, single vowel group)
        if ch == "o" and i + 1 < n and word[i + 1] == "u":
            is_stressed = current_vowel_group == stress_vowel_target
            if is_stressed:
                stress_idx = len(phonemes)
            phonemes.append("o")
            current_vowel_group += 1
            i += 2
            continue

        # --- Consonants ---

        if ch == "r":
            # Intervocalic r (vowel before AND vowel after) -> ɾ (tap)
            # All other positions (word-initial, word-final, after consonant,
            # before consonant / coda) -> ʁ (uvular fricative)
            if _is_intervocalic(i, word):
                phonemes.append("ɾ")
            else:
                phonemes.append("ʁ")
            i += 1
            continue

        if ch == "s":
            # Intervocalic s -> z
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
            # Initial or after "en" -> ʃ, between vowels -> ks or z or s
            if i == 0:
                phonemes.append("ʃ")
            elif (
                i > 0
                and _is_vowel_char(word[i - 1])
                and i + 1 < n
                and _is_vowel_char(word[i + 1])
            ):
                phonemes.append("z")
            else:
                phonemes.append("ʃ")
            i += 1
            continue

        if ch == "c":
            # c before e/i -> s, otherwise -> k
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
            # g before e/i -> ʒ, otherwise -> ɡ
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
            # Brazilian Portuguese: t before i -> tʃ (single affricate token)
            # (palatalization before unstressed final -e is handled in
            # _apply_br_postprocessing)
            if i + 1 < n and word[i + 1] in "ií":
                phonemes.append("tʃ")
            else:
                phonemes.append("t")
            i += 1
            continue

        if ch == "d":
            # Brazilian Portuguese: d before i -> dʒ (single affricate token)
            # (palatalization before unstressed final -e is handled in
            # _apply_br_postprocessing)
            if i + 1 < n and word[i + 1] in "ií":
                phonemes.append("dʒ")
            else:
                phonemes.append("d")
            i += 1
            continue

        if ch == "h":
            # h is silent in Portuguese (except in digraphs already handled)
            i += 1
            continue

        # Simple 1-to-1 consonant mappings (identity: grapheme == phoneme)
        if ch in "bfklmnpvwz":
            phonemes.append(ch)
            i += 1
            continue

        # --- Vowels ---

        if ch in _VOWELS:
            is_stressed = current_vowel_group == stress_vowel_target
            base = _ACCENTED.get(ch, ch)

            # Check for nasalization: tilde or vowel before n/m + consonant/end
            # Exception: vowel before "nh" digraph is NOT nasal (nh = /ɲ/)
            is_nasal = False
            nasal_absorbed = False  # True when n/m is absorbed into nasalization
            if ch in _TILDE:
                is_nasal = True
            elif i + 1 < n and word[i + 1] in "nm":
                # Check for "nh" digraph -- do NOT nasalize before nh
                if word[i + 1] == "n" and i + 2 < n and word[i + 2] == "h":
                    is_nasal = False
                elif i + 2 >= n:
                    # Nasal: n/m at end of word -- absorb the nasal consonant
                    is_nasal = True
                    nasal_absorbed = True
                elif not _is_vowel_char(word[i + 2]):
                    # Nasal: n/m followed by consonant -- absorb the nasal coda
                    is_nasal = True
                    nasal_absorbed = True

            if is_nasal:
                nasal_map = {"a": "ã", "e": "ẽ", "i": "ĩ", "o": "õ", "u": "ũ"}
                phoneme = nasal_map.get(base, base)
            # Open vs closed vowels based on accent
            elif ch in _STRESS_ACCENTS:
                # Acute accent = open vowel
                vowel_map = {
                    "a": "a",
                    "e": "ɛ",
                    "i": "i",
                    "o": "ɔ",
                    "u": "u",
                }
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
            # Advance past the absorbed nasal consonant (n/m already encoded
            # in the nasal vowel; skip it to avoid redundant coda)
            if nasal_absorbed:
                i += 2  # skip vowel + nasal consonant
            else:
                i += 1
            continue

        # Punctuation or unknown: pass through
        if ch in _PUNCTUATION:
            phonemes.append(ch)
            i += 1
            continue

        # Skip unknown characters
        i += 1

    # Apply BR Portuguese post-processing
    phonemes = _remove_duplicate_nasal_coda(phonemes)
    phonemes = _apply_coda_l_vocalization(phonemes)
    phonemes = _apply_br_postprocessing(phonemes, stress_idx)

    # Recalculate stress_idx after post-processing may have shifted indices
    # Find the first stressed vowel (it should still be at approximately the
    # same position but t->tʃ insertion may have shifted it)
    # The post-processing functions preserve the vowel positions relative order.

    return phonemes, stress_idx


def _remove_duplicate_nasal_coda(phonemes: list[str]) -> list[str]:
    """Remove duplicate nasal consonant after nasal vowel at word end.

    When a word ends in a nasal vowel + nasal consonant (n or m), the nasal
    consonant is redundant because the nasality is already encoded in the
    vowel. Remove the trailing nasal consonant.

    Example: "bom" might produce [b, õ, m] -> [b, õ]
    """
    result = list(phonemes)
    # Process from end, looking for patterns: nasal_vowel + n/m at word boundary
    i = len(result) - 1
    while i >= 1:
        # Check for nasal vowel followed by n/m
        if result[i] in ("n", "m") and result[i - 1] in _IPA_NASAL_VOWELS:
            # Check this is at word end (next is space, punctuation, or end)
            at_boundary = (i == len(result) - 1) or (
                result[i + 1] == " " or result[i + 1] in _PUNCTUATION
            )
            if at_boundary:
                result.pop(i)
        i -= 1
    return result


def _apply_coda_l_vocalization(phonemes: list[str]) -> list[str]:
    """Vocalize l in syllable coda position to [w] (BR Portuguese).

    In Brazilian Portuguese, /l/ becomes [w] when in coda position
    (before a consonant or at word end).

    Examples: "Brasil" -> [w] not [l], "alto" -> [w] not [l]
    """
    result = list(phonemes)
    for i, ph in enumerate(result):
        if ph != "l":
            continue
        # l at end of phoneme list -> coda
        if i == len(result) - 1:
            result[i] = "w"
            continue
        next_ph = result[i + 1]
        # l before space or punctuation -> coda (word-final)
        if next_ph == " " or next_ph in _PUNCTUATION:
            result[i] = "w"
            continue
        # l before a consonant -> coda
        # Check first character for multi-char phonemes like tʃ, dʒ
        if (
            next_ph in _IPA_CONSONANTS
            or (len(next_ph) > 1 and next_ph[0] in _IPA_CONSONANTS)
        ) and next_ph not in _IPA_VOWELS:
            result[i] = "w"
            continue
    return result


def _apply_br_postprocessing(phonemes: list[str], stress_idx: int) -> list[str]:
    """Apply Brazilian Portuguese phonological rules as post-processing.

    1. t/d palatalization before unstressed final -e:
       - te# (unstressed) -> tʃi
       - de# (unstressed) -> dʒi
    2. Unstressed final vowel reduction:
       - Unstressed final e -> i
       - Unstressed final o -> u
    """
    result = list(phonemes)

    # --- Pass 1: t/d palatalization + unstressed final -e reduction ---
    # Find word boundaries in the phoneme list
    # Words are separated by spaces; also handle end-of-list
    word_ranges = _find_word_ranges(result)

    for start, end in word_ranges:
        # Check for t/d + e at word end (before punctuation or end)
        # end is exclusive index
        if end - start < 2:
            continue

        last_phoneme_idx = end - 1
        # Skip trailing punctuation within this word range
        while last_phoneme_idx >= start and result[last_phoneme_idx] in _PUNCTUATION:
            last_phoneme_idx -= 1
        if last_phoneme_idx < start:
            continue

        # Check if last phoneme is unstressed 'e'
        if result[last_phoneme_idx] == "e" and last_phoneme_idx != stress_idx:
            # Check if preceded by 't'
            if last_phoneme_idx >= start + 1 and result[last_phoneme_idx - 1] == "t":
                # t + unstressed final e -> tʃ i (single affricate token)
                result[last_phoneme_idx - 1] = "tʃ"
                result[last_phoneme_idx] = "i"
                continue
            # Check if preceded by 'd'
            if last_phoneme_idx >= start + 1 and result[last_phoneme_idx - 1] == "d":
                # d + unstressed final e -> dʒ i (single affricate token)
                result[last_phoneme_idx - 1] = "dʒ"
                result[last_phoneme_idx] = "i"
                continue
            # Unstressed final e -> i (general reduction)
            result[last_phoneme_idx] = "i"
        elif result[last_phoneme_idx] == "o" and last_phoneme_idx != stress_idx:
            # Unstressed final o -> u
            result[last_phoneme_idx] = "u"

    return result


def _find_word_ranges(phonemes: list[str]) -> list[tuple[int, int]]:
    """Find (start, end) ranges for each word in the phoneme list.

    Words are delimited by space phonemes.
    """
    ranges = []
    start = 0
    for i, ph in enumerate(phonemes):
        if ph == " ":
            if i > start:
                ranges.append((start, i))
            start = i + 1
    if start < len(phonemes):
        ranges.append((start, len(phonemes)))
    return ranges


def _split_words(text: str) -> list[str]:
    """Split text into words and punctuation tokens."""
    tokens = re.findall(
        r"[a-záàâãéêíóôõúüçñ]+|[,.;:!?\u00a1\u00bf\u2014\u2013\u2026]",
        text,
        re.IGNORECASE,
    )
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
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))

        need_space = True

    return phonemes, prosody_list


def phonemize_portuguese(text: str) -> list[str]:
    """Convert Brazilian Portuguese text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_portuguese_with_prosody(text)
    return phonemes


class PortuguesePhonemizer(Phonemizer):
    """Brazilian Portuguese rule-based phonemizer."""

    @property
    def language_code(self) -> str:
        return "pt"

    def phonemize(self, text: str) -> list[str]:
        return phonemize_portuguese(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_portuguese_with_prosody(text)
