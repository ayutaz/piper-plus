"""Rule-based Spanish G2P (grapheme-to-phoneme) module.

Converts Spanish text to IPA phonemes using orthographic rules.
No external dependencies required — Spanish has nearly phonemic
orthography, making rule-based G2P highly effective.

Uses Latin American Spanish pronunciation by default (seseo: c/z → s).
"""

import re
import unicodedata

from .base import Phonemizer, ProsodyInfo

__all__ = [
    "phonemize_spanish",
    "phonemize_spanish_with_prosody",
    "SpanishPhonemizer",
]

# Punctuation characters passed through as-is
_PUNCTUATION = set(",.;:!?¡¿")

# Vowels (for context checks)
_VOWELS = set("aeiou")

# Accented vowel → base vowel mapping
_ACCENT_MAP = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u"}

# Letters that trigger word-final stress (Spanish stress rule:
# words ending in consonant other than n/s get final-syllable stress)
_STRESS_FINAL_EXCEPTIONS = {"n", "s"}

# Regex: split text into word tokens and punctuation
_RE_TOKEN = re.compile(r"([a-záéíóúüñ]+|[,.;:!?¡¿]+)", re.IGNORECASE)


def _normalize(text: str) -> str:
    """Lowercase and normalize unicode."""
    text = text.lower()
    # Normalize to NFC to handle combining accents
    text = unicodedata.normalize("NFC", text)
    return text


def _has_accent(word: str) -> int | None:
    """Return index of the accented vowel in *word*, or None."""
    for i, ch in enumerate(word):
        if ch in _ACCENT_MAP:
            return i
    return None


def _find_syllable_boundaries(word: str) -> list[int]:
    """Return list of character indices where each syllable starts.

    Uses a simplified Spanish syllabification algorithm:
    - V = vowel, C = consonant
    - Split between V.CV, VC.CV, VCC.CV patterns
    """
    base = ""
    for ch in word:
        base += _ACCENT_MAP.get(ch, ch)

    is_vowel = [c in _VOWELS for c in base]
    n = len(base)
    boundaries = [0]

    i = 1
    while i < n:
        if is_vowel[i]:
            # Check for hiatus vs diphthong
            if i > 0 and is_vowel[i - 1]:
                # Strong+strong vowel = hiatus (new syllable)
                strong = set("aeo")
                if base[i - 1] in strong and base[i] in strong:
                    boundaries.append(i)
            i += 1
        else:
            # Consonant — find how many consonants before next vowel
            cons_start = i
            while i < n and not is_vowel[i]:
                i += 1
            cons_count = i - cons_start
            if i < n:  # there's a vowel after
                if cons_count == 1:
                    # V.CV
                    boundaries.append(cons_start)
                elif cons_count >= 2:
                    # Check for inseparable clusters
                    cluster = base[cons_start : cons_start + 2]
                    inseparable = {
                        "bl",
                        "br",
                        "cl",
                        "cr",
                        "dr",
                        "fl",
                        "fr",
                        "gl",
                        "gr",
                        "pl",
                        "pr",
                        "tr",
                        "tl",
                    }
                    if cons_count == 2 and cluster in inseparable:
                        # VC.CV where CC is inseparable → V.CCV
                        boundaries.append(cons_start)
                    elif cons_count == 2:
                        # VC.CV
                        boundaries.append(cons_start + 1)
                    elif cons_count >= 3:
                        # Put split before last 2 if they form cluster
                        last2 = base[i - 2 : i]
                        if last2 in inseparable:
                            boundaries.append(i - 2)
                        else:
                            boundaries.append(i - 1)

    return boundaries


def _get_stressed_syllable(word: str) -> int:
    """Return the 0-based syllable index that receives stress.

    Spanish stress rules:
    1. If accent mark → stressed syllable contains that vowel
    2. Words ending in vowel, n, s → penultimate syllable
    3. Words ending in other consonant → final syllable
    """
    boundaries = _find_syllable_boundaries(word)
    num_syllables = len(boundaries)
    if num_syllables == 0:
        return 0

    # Check for explicit accent mark
    accent_idx = _has_accent(word)
    if accent_idx is not None:
        # Find which syllable contains this index
        for syl_idx in range(len(boundaries) - 1, -1, -1):
            if boundaries[syl_idx] <= accent_idx:
                return syl_idx
        return 0

    if num_syllables == 1:
        return 0

    # Get base form of last character
    base_word = ""
    for ch in word:
        base_word += _ACCENT_MAP.get(ch, ch)

    last_char = base_word[-1] if base_word else ""

    if last_char in _VOWELS or last_char in _STRESS_FINAL_EXCEPTIONS:
        # Penultimate
        return max(0, num_syllables - 2)
    else:
        # Final
        return num_syllables - 1


def _is_vowel_char(ch: str) -> bool:
    """Check if character is a Spanish vowel (including accented)."""
    return ch in _VOWELS or ch in _ACCENT_MAP


def _get_base_vowel(ch: str) -> str:
    """Get base vowel from potentially accented character."""
    return _ACCENT_MAP.get(ch, ch)


def _g2p_word(word: str) -> tuple[list[str], int]:
    """Convert a Spanish word to IPA phonemes.

    Returns (phonemes, stressed_syllable_index).
    """
    phonemes: list[str] = []
    n = len(word)
    i = 0

    # Track position for allophonic rules
    # We need the base form for consonant context
    base_word = ""
    for ch in word:
        base_word += _ACCENT_MAP.get(ch, ch)

    def _prev_is_vowel() -> bool:
        """Check if previous character in word is a vowel."""
        return i > 0 and _is_vowel_char(word[i - 1])

    def _next_is_vowel() -> bool:
        """Check if next character in word is a vowel."""
        return i + 1 < n and _is_vowel_char(word[i + 1])

    def _is_after_nasal() -> bool:
        """Check if previous phoneme is a nasal."""
        return i > 0 and base_word[i - 1] in ("m", "n")

    def _is_word_initial() -> bool:
        return i == 0

    while i < n:
        ch = word[i]
        base_ch = _get_base_vowel(ch) if ch in _ACCENT_MAP else ch

        # --- Vowels ---
        if base_ch in _VOWELS:
            phonemes.append(base_ch)
            i += 1
            continue

        # --- Multi-character sequences (check longest first) ---

        # "qu" before e/i → k
        if base_ch == "q" and i + 1 < n and base_word[i + 1] == "u":
            if i + 2 < n and base_word[i + 2] in ("e", "i"):
                phonemes.append("k")
                i += 2  # skip "qu", vowel handled next iteration
                continue
            else:
                phonemes.append("k")
                i += 2
                continue

        # "ch" → tʃ
        if base_ch == "c" and i + 1 < n and base_word[i + 1] == "h":
            phonemes.append("tʃ")
            i += 2
            continue

        # "ll" → ʝ (yeísmo)
        if base_ch == "l" and i + 1 < n and base_word[i + 1] == "l":
            phonemes.append("ʝ")
            i += 2
            continue

        # "rr" → trill
        if base_ch == "r" and i + 1 < n and base_word[i + 1] == "r":
            phonemes.append("rr")
            i += 2
            continue

        # "gü" before e/i → ɡw
        if (
            base_ch == "g"
            and i + 1 < n
            and word[i + 1] == "ü"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            phonemes.append("ɡ")
            phonemes.append("w")
            i += 2  # skip "gü", vowel handled next
            continue

        # "gu" before e/i → ɡ (u is silent)
        if (
            base_ch == "g"
            and i + 1 < n
            and base_word[i + 1] == "u"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            # g with allophonic variation
            if _prev_is_vowel() and not _is_after_nasal():
                phonemes.append("ɣ")
            else:
                phonemes.append("ɡ")
            i += 2  # skip "gu"
            continue

        # --- Single character rules ---

        if base_ch == "b" or base_ch == "v":
            # b/v → b (word-initial, after nasal) or β (intervocalic)
            if _is_word_initial() or _is_after_nasal():
                phonemes.append("b")
            elif _prev_is_vowel():
                phonemes.append("β")
            else:
                phonemes.append("b")
            i += 1
            continue

        if base_ch == "c":
            # c before e/i → s (Latin American seseo)
            if i + 1 < n and base_word[i + 1] in ("e", "i"):
                phonemes.append("s")
            else:
                # c before a/o/u or consonant → k
                phonemes.append("k")
            i += 1
            continue

        if base_ch == "d":
            # d → d (word-initial, after n/l) or ð (intervocalic, word-final)
            if _is_word_initial() or _is_after_nasal():
                phonemes.append("d")
            elif i > 0 and base_word[i - 1] == "l":
                phonemes.append("d")
            elif _prev_is_vowel():
                phonemes.append("ð")
            elif i == n - 1:
                # Word-final d → ð (often silent, but we keep ð)
                phonemes.append("ð")
            else:
                phonemes.append("d")
            i += 1
            continue

        if base_ch == "f":
            phonemes.append("f")
            i += 1
            continue

        if base_ch == "g":
            # g before e/i → x (jota sound)
            if i + 1 < n and base_word[i + 1] in ("e", "i"):
                phonemes.append("x")
            elif _is_word_initial() or _is_after_nasal():
                phonemes.append("ɡ")
            elif _prev_is_vowel():
                phonemes.append("ɣ")
            else:
                phonemes.append("ɡ")
            i += 1
            continue

        if base_ch == "h":
            # h is silent in Spanish
            i += 1
            continue

        if base_ch == "j":
            phonemes.append("x")
            i += 1
            continue

        if base_ch == "k":
            phonemes.append("k")
            i += 1
            continue

        if base_ch == "l":
            phonemes.append("l")
            i += 1
            continue

        if base_ch == "m":
            phonemes.append("m")
            i += 1
            continue

        if base_ch == "n":
            phonemes.append("n")
            i += 1
            continue

        if base_ch == "ñ":
            phonemes.append("ɲ")
            i += 1
            continue

        if base_ch == "p":
            phonemes.append("p")
            i += 1
            continue

        if base_ch == "r":
            # r at word start → trill
            if _is_word_initial():
                phonemes.append("rr")
            elif i > 0 and base_word[i - 1] in ("l", "n", "s"):
                # r after l/n/s → trill
                phonemes.append("rr")
            else:
                # r elsewhere → tap
                phonemes.append("ɾ")
            i += 1
            continue

        if base_ch == "s":
            phonemes.append("s")
            i += 1
            continue

        if base_ch == "t":
            phonemes.append("t")
            i += 1
            continue

        if base_ch == "w":
            phonemes.append("w")
            i += 1
            continue

        if base_ch == "x":
            # x → ks (general), but in some words like "México" → x
            # Default to ks for simplicity
            phonemes.append("k")
            phonemes.append("s")
            i += 1
            continue

        if base_ch == "y":
            # y as consonant → ʝ, as vowel (word-final "y") → i
            if i == n - 1:
                phonemes.append("i")
            elif _next_is_vowel():
                phonemes.append("ʝ")
            else:
                phonemes.append("ʝ")
            i += 1
            continue

        if base_ch == "z":
            # z → s (Latin American seseo)
            phonemes.append("s")
            i += 1
            continue

        if base_ch == "ñ":
            phonemes.append("ɲ")
            i += 1
            continue

        # Unknown character — skip
        i += 1

    stressed_syl = _get_stressed_syllable(word)
    return phonemes, stressed_syl


def _insert_stress_marker(
    phonemes: list[str], word: str
) -> list[str]:
    """Insert stress marker ˈ before the stressed syllable's first vowel."""
    if not phonemes:
        return phonemes

    boundaries = _find_syllable_boundaries(word)
    stressed_syl = _get_stressed_syllable(word)

    if not boundaries:
        return phonemes

    # Map syllable boundaries (character indices) to phoneme indices.
    # We need to find which phoneme corresponds to the start of the
    # stressed syllable, then insert ˈ before that syllable's first vowel.

    # Build character-to-phoneme index mapping
    # Walk through the word and phoneme list in parallel
    base_word = ""
    for ch in word:
        base_word += _ACCENT_MAP.get(ch, ch)

    # Find the vowel in the stressed syllable
    if stressed_syl < len(boundaries):
        syl_start = boundaries[stressed_syl]
        syl_end = boundaries[stressed_syl + 1] if stressed_syl + 1 < len(boundaries) else len(base_word)

        # Find first vowel in this syllable range
        stressed_vowel_char_idx = None
        for ci in range(syl_start, syl_end):
            if ci < len(base_word) and base_word[ci] in _VOWELS:
                stressed_vowel_char_idx = ci
                break

        if stressed_vowel_char_idx is None:
            return phonemes

        # Now map character index to phoneme index
        # Walk through word chars and phonemes together
        char_i = 0
        ph_i = 0
        target_ph_i = None

        while char_i < len(base_word) and ph_i < len(phonemes):
            if char_i == stressed_vowel_char_idx:
                target_ph_i = ph_i
                break

            ch = base_word[char_i]

            # Skip silent h
            if ch == "h":
                char_i += 1
                continue

            # Multi-char graphemes that produce one phoneme
            if ch == "c" and char_i + 1 < len(base_word) and base_word[char_i + 1] == "h":
                char_i += 2
                ph_i += 1
                continue
            if ch == "l" and char_i + 1 < len(base_word) and base_word[char_i + 1] == "l":
                char_i += 2
                ph_i += 1
                continue
            if ch == "r" and char_i + 1 < len(base_word) and base_word[char_i + 1] == "r":
                char_i += 2
                ph_i += 1
                continue
            if ch == "q" and char_i + 1 < len(base_word) and base_word[char_i + 1] == "u":
                char_i += 2
                ph_i += 1
                continue
            if ch == "g" and char_i + 1 < len(base_word) and base_word[char_i + 1] == "u":
                if char_i + 2 < len(base_word) and base_word[char_i + 2] in ("e", "i"):
                    char_i += 2
                    ph_i += 1
                    continue
            if ch == "x":
                # x → k + s (2 phonemes)
                char_i += 1
                ph_i += 2
                continue

            char_i += 1
            # Vowels and consonants each produce one phoneme
            if ch in _VOWELS or ch not in ("h",):
                ph_i += 1

        if target_ph_i is not None:
            result = phonemes[:target_ph_i] + ["ˈ"] + phonemes[target_ph_i:]
            return result

    return phonemes


def phonemize_spanish_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Spanish text to phoneme list and prosody features.

    Returns:
        (phonemes, prosody_info_list) where each phoneme has corresponding
        prosody info with a1=0, a2=stress-based (0 or 2), a3=word phoneme count.
    """
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    for token in tokens:
        # Check if pure punctuation
        if all(c in _PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue

        # Regular word
        if need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        word_phonemes, stressed_syl = _g2p_word(token)
        word_with_stress = _insert_stress_marker(word_phonemes, token)

        word_phoneme_count = len(word_phonemes)  # count without stress marker

        for ph in word_with_stress:
            if ph == "ˈ":
                phonemes.append("ˈ")
                prosody_list.append(ProsodyInfo(a1=0, a2=2, a3=word_phoneme_count))
            else:
                is_stressed_vowel = False
                # Check if this phoneme is right after a stress marker
                if phonemes and phonemes[-1] == "ˈ" and ph in _VOWELS:
                    is_stressed_vowel = True

                a2 = 2 if is_stressed_vowel else 0
                phonemes.append(ph)
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))

        need_space = True

    return phonemes, prosody_list


def phonemize_spanish(text: str) -> list[str]:
    """Convert Spanish text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_spanish_with_prosody(text)
    return phonemes


class SpanishPhonemizer(Phonemizer):
    """Spanish phonemizer using rule-based G2P."""

    def phonemize(self, text: str) -> list[str]:
        return phonemize_spanish(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_spanish_with_prosody(text)

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        return None

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding for Spanish."""
        pad_ids = phoneme_id_map.get("_", [0])
        bos_ids = phoneme_id_map.get("^")
        eos_ids = phoneme_id_map.get("$")

        # Insert pad between every phoneme ID
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

        # Wrap with BOS/EOS
        if bos_ids:
            phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
            prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
        if eos_ids:
            phoneme_ids = phoneme_ids + eos_ids
            prosody_features = prosody_features + [None] * len(eos_ids)

        return phoneme_ids, prosody_features
