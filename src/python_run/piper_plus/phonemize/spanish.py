"""Rule-based Spanish G2P (grapheme-to-phoneme) module.

Runtime version for piper-plus inference.
Converts Spanish text to IPA phonemes using orthographic rules.
G2P logic is identical to the training side (piper_train.phonemize.spanish).

Uses Latin American Spanish pronunciation by default (seseo: c/z → s).
"""

import re
import unicodedata

from .token_mapper import map_sequence


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

# Common monosyllabic function words that are phonologically unstressed
# in connected speech and should not receive the primary stress marker ˈ.
_UNSTRESSED_FUNCTION_WORDS: frozenset[str] = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "de",
        "del",
        "al",
        "a",
        "en",
        "con",
        "por",
        "y",
        "o",
        "que",
        "se",
        "me",
        "te",
        "le",
        "lo",
        "nos",
        "su",
        "mi",
        "tu",
        "es",
        "no",
        "si",
    }
)


def _has_accent_on_char(grapheme: str) -> bool:
    """Return True if *grapheme* is an accented vowel character."""
    return grapheme in ("á", "é", "í", "ó", "ú")


def _normalize(text: str) -> str:
    """Lowercase and normalize unicode."""
    text = text.lower()
    # Normalize to NFC to handle combining accents
    text = unicodedata.normalize("NFC", text)
    return text


def _has_accent(word: str) -> int | None:
    """Return index of the accented vowel in *word*, or None.

    Only stress-indicating accents (á é í ó ú) are considered.
    The diaeresis (ü) changes pronunciation but does NOT affect stress.
    """
    _STRESS_ACCENTS = {"á", "é", "í", "ó", "ú"}
    for i, ch in enumerate(word):
        if ch in _STRESS_ACCENTS:
            return i
    return None


# ---------------------------------------------------------------------------
# Grapheme segmentation — shared by G2P, syllabification, and stress mapping.
# ---------------------------------------------------------------------------

# Each grapheme unit is a tuple of (grapheme_str, is_vowel, is_silent).
# ``is_vowel`` marks vowels for syllabification; ``is_silent`` marks letters
# that produce no phoneme output (e.g. silent ``u`` in ``qu``/``gu``).
_GraphemeUnit = tuple[str, bool, bool]


def _segment_graphemes(word: str) -> list[_GraphemeUnit]:
    """Split *word* into grapheme units respecting Spanish digraphs.

    Multi-character graphemes (``ch``, ``ll``, ``rr``, ``qu``, ``gu``,
    ``gü``, ``sc`` before e/i) are kept as single units so that
    syllabification and the char-to-phoneme walker never tear them apart.

    The original (un-normalised) characters are used so that accented
    vowels can be detected downstream, but an ``is_vowel`` flag is also
    stored for convenience (based on the *base* form of the character).
    """
    base_word = ""
    for ch in word:
        base_word += _ACCENT_MAP.get(ch, ch)

    units: list[_GraphemeUnit] = []
    n = len(word)
    i = 0
    while i < n:
        bch = base_word[i]

        # --- Multi-character graphemes (longest match first) ---

        # ``qu`` (u is silent; the following vowel is separate)
        if bch == "q" and i + 1 < n and base_word[i + 1] == "u":
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``gü`` before e/i — diaeresis makes the u pronounced (/gw/)
        if (
            bch == "g"
            and i + 1 < n
            and word[i + 1] == "ü"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``gu`` before e/i — u is silent
        if (
            bch == "g"
            and i + 1 < n
            and base_word[i + 1] == "u"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``ch`` → single consonant unit
        if bch == "c" and i + 1 < n and base_word[i + 1] == "h":
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``ll`` → single consonant unit
        if bch == "l" and i + 1 < n and base_word[i + 1] == "l":
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``rr`` → single consonant unit
        if bch == "r" and i + 1 < n and base_word[i + 1] == "r":
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``sc`` before e/i → single consonant unit (seseo: /s/, no geminate)
        if (
            bch == "s"
            and i + 1 < n
            and base_word[i + 1] == "c"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # ``xc`` before e/i → single consonant unit (/ks/, c is absorbed)
        if (
            bch == "x"
            and i + 1 < n
            and base_word[i + 1] == "c"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            units.append((word[i : i + 2], False, False))
            i += 2
            continue

        # --- Single characters ---

        # Silent ``h``
        if bch == "h":
            units.append((word[i], False, True))
            i += 1
            continue

        # Vowels (including accented)
        if bch in _VOWELS:
            units.append((word[i], True, False))
            i += 1
            continue

        # All other consonants
        units.append((word[i], False, False))
        i += 1

    return units


# ---------------------------------------------------------------------------
# Syllabification
# ---------------------------------------------------------------------------


def _find_syllable_boundaries(
    word: str,
    *,
    units: list[_GraphemeUnit] | None = None,
) -> list[int]:
    """Return list of *grapheme-unit* indices where each syllable starts.

    Operates on grapheme units produced by ``_segment_graphemes`` so that
    digraphs (``ch``, ``ll``, ``rr``, ``qu``, ``gu``, ``gü``) are treated
    as single consonant units and are never split across syllables.

    If *units* is provided, it is used directly instead of calling
    ``_segment_graphemes(word)`` again (performance optimisation).
    """
    if units is None:
        units = _segment_graphemes(word)

    # Build a simple vowel/consonant mask, skipping silent units
    # (silent letters like ``h`` are attached to the previous unit and
    # don't affect syllable structure).
    #
    # However we need to track the *unit index* for each non-silent unit
    # so that the boundaries we return refer to grapheme-unit positions.
    non_silent_idx: list[int] = []
    is_vowel_ns: list[bool] = []
    for idx, (_grapheme, is_v, is_silent) in enumerate(units):
        if is_silent:
            continue
        non_silent_idx.append(idx)
        is_vowel_ns.append(is_v)

    ns_n = len(non_silent_idx)
    if ns_n == 0:
        return [0]

    # We'll track syllable start positions in the non-silent index list,
    # then map back to grapheme-unit indices.
    ns_boundaries: list[int] = [0]

    i = 1
    while i < ns_n:
        if is_vowel_ns[i]:
            if i > 0 and is_vowel_ns[i - 1]:
                # Check hiatus vs diphthong: strong+strong = hiatus
                strong = set("aeo")
                prev_grapheme = units[non_silent_idx[i - 1]][0][-1]
                curr_grapheme = units[non_silent_idx[i]][0][-1]
                prev_base = _get_base_vowel(prev_grapheme)
                curr_base = _get_base_vowel(curr_grapheme)
                if prev_base in strong and curr_base in strong:
                    ns_boundaries.append(i)
                else:
                    # Accented weak vowel forces hiatus (diphthong breaking)
                    weak = {"i", "u"}
                    if curr_base in weak and _has_accent_on_char(curr_grapheme):
                        ns_boundaries.append(i)
                    elif prev_base in weak and _has_accent_on_char(prev_grapheme):
                        ns_boundaries.append(i)
            i += 1
        else:
            # Consonant cluster before next vowel
            cons_start = i
            while i < ns_n and not is_vowel_ns[i]:
                i += 1
            cons_count = i - cons_start
            if i < ns_n:  # vowel follows
                if cons_count == 1:
                    # V.CV
                    ns_boundaries.append(cons_start)
                elif cons_count >= 2:
                    # Check inseparable onset cluster (last 2 consonants)
                    def _base_cons(ns_idx: int) -> str:
                        """Return the base consonant letter for an ns index."""
                        g = units[non_silent_idx[ns_idx]][0]
                        return _ACCENT_MAP.get(g[-1], g[-1])

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
                    if cons_count == 2:
                        pair = _base_cons(cons_start) + _base_cons(cons_start + 1)
                        if pair in inseparable:
                            ns_boundaries.append(cons_start)
                        else:
                            ns_boundaries.append(cons_start + 1)
                    else:
                        # 3+ consonants — split before last 2 if they form
                        # an inseparable cluster, else before last 1.
                        last2 = _base_cons(i - 2) + _base_cons(i - 1)
                        if last2 in inseparable:
                            ns_boundaries.append(i - 2)
                        else:
                            ns_boundaries.append(i - 1)

    # Map non-silent indices back to grapheme-unit indices
    return [non_silent_idx[b] for b in ns_boundaries]


def _get_stressed_syllable(
    word: str,
    *,
    units: list[_GraphemeUnit] | None = None,
    boundaries: list[int] | None = None,
) -> int:
    """Return the 0-based syllable index that receives stress.

    Spanish stress rules:
    1. If accent mark → stressed syllable contains that vowel
    2. Words ending in vowel, n, s → penultimate syllable
    3. Words ending in other consonant → final syllable

    If *units* and/or *boundaries* are provided, they are used directly
    instead of recomputing them (performance optimisation).
    """
    if units is None:
        units = _segment_graphemes(word)
    if boundaries is None:
        boundaries = _find_syllable_boundaries(word, units=units)
    num_syllables = len(boundaries)
    if num_syllables == 0:
        return 0

    # Check for explicit accent mark
    accent_idx = _has_accent(word)
    if accent_idx is not None:
        # Find which grapheme-unit contains this character index.
        # Walk through units accumulating character offsets.
        char_offset = 0
        accent_unit_idx = 0
        for uid, (grapheme, _is_v, _is_s) in enumerate(units):
            if char_offset <= accent_idx < char_offset + len(grapheme):
                accent_unit_idx = uid
                break
            char_offset += len(grapheme)

        # Find which syllable contains this unit index
        for syl_idx in range(len(boundaries) - 1, -1, -1):
            if boundaries[syl_idx] <= accent_unit_idx:
                return syl_idx
        return 0

    if num_syllables == 1:
        return 0

    # Get base form of last character
    base_last = _get_base_vowel(word[-1])

    if base_last in _VOWELS or base_last in _STRESS_FINAL_EXCEPTIONS:
        return max(0, num_syllables - 2)
    else:
        return num_syllables - 1


def _is_vowel_char(ch: str) -> bool:
    """Check if character is a Spanish vowel (including accented)."""
    return ch in _VOWELS or ch in _ACCENT_MAP


def _get_base_vowel(ch: str) -> str:
    """Get base vowel from potentially accented character."""
    return _ACCENT_MAP.get(ch, ch)


# ---------------------------------------------------------------------------
# G2P — grapheme to phoneme conversion
# ---------------------------------------------------------------------------


def _g2p_word(
    word: str,
) -> tuple[list[str], int, list[_GraphemeUnit], list[int]]:
    """Convert a Spanish word to IPA phonemes.

    Returns (phonemes, stressed_syllable_index, grapheme_units, syllable_boundaries).
    The extra return values allow callers to avoid redundant recomputation.
    """
    phonemes: list[str] = []
    n = len(word)
    i = 0

    # Base form for consonant context checks
    base_word = ""
    for ch in word:
        base_word += _ACCENT_MAP.get(ch, ch)

    def _prev_is_vowel() -> bool:
        return i > 0 and _is_vowel_char(word[i - 1])

    def _is_after_nasal() -> bool:
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
            phonemes.append("k")
            i += 2  # skip "qu", vowel handled next iteration
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
            if _prev_is_vowel() and not _is_after_nasal():
                phonemes.append("ɣ")
            else:
                phonemes.append("ɡ")
            i += 2  # skip "gu"
            continue

        # "sc" before e/i → s (seseo: avoid geminate ss)
        if (
            base_ch == "s"
            and i + 1 < n
            and base_word[i + 1] == "c"
            and i + 2 < n
            and base_word[i + 2] in ("e", "i")
        ):
            # Latin American seseo: sc + e/i → just /s/ (no geminate)
            phonemes.append("s")
            i += 2  # skip "sc", vowel handled next
            continue

        # --- Single character rules ---

        if base_ch in ("b", "v"):
            if (
                _is_word_initial()
                or _is_after_nasal()
                or (i > 0 and base_word[i - 1] == "l")
            ):
                phonemes.append("b")
            else:
                phonemes.append("β")  # fricative in all other positions
            i += 1
            continue

        if base_ch == "c":
            if i + 1 < n and base_word[i + 1] in ("e", "i"):
                phonemes.append("s")
            else:
                phonemes.append("k")
            i += 1
            continue

        if base_ch == "d":
            if (
                _is_word_initial()
                or _is_after_nasal()
                or (i > 0 and base_word[i - 1] == "l")
            ):
                phonemes.append("d")
            else:
                phonemes.append("ð")  # fricative in all other positions
            i += 1
            continue

        if base_ch == "f":
            phonemes.append("f")
            i += 1
            continue

        if base_ch == "g":
            if i + 1 < n and base_word[i + 1] in ("e", "i"):
                phonemes.append("x")
            elif (
                _is_word_initial()
                or _is_after_nasal()
                or (i > 0 and base_word[i - 1] == "l")
            ):
                phonemes.append("ɡ")
            else:
                phonemes.append("ɣ")  # fricative in all other positions
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
            if _is_word_initial():
                phonemes.append("rr")
            elif i > 0 and base_word[i - 1] in ("l", "n", "s"):
                phonemes.append("rr")
            else:
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
            # Check for xc+e/i: the following c is silent (x already provides /ks/)
            if (
                i + 1 < n
                and base_word[i + 1] == "c"
                and i + 2 < n
                and base_word[i + 2] in ("e", "i")
            ):
                phonemes.append("k")
                phonemes.append("s")
                i += 2  # skip both x and c
                continue
            # Normal x → /ks/
            phonemes.append("k")
            phonemes.append("s")
            i += 1
            continue

        if base_ch == "y":
            if i == n - 1:
                phonemes.append("i")
            else:
                phonemes.append("ʝ")
            i += 1
            continue

        if base_ch == "z":
            phonemes.append("s")
            i += 1
            continue

        # Unknown character — skip
        i += 1

    units = _segment_graphemes(word)
    boundaries = _find_syllable_boundaries(word, units=units)
    stressed_syl = _get_stressed_syllable(word, units=units, boundaries=boundaries)
    return phonemes, stressed_syl, units, boundaries


# ---------------------------------------------------------------------------
# Phoneme count per grapheme unit — used by the stress-marker walker.
# ---------------------------------------------------------------------------


def _phoneme_count_for_unit(
    grapheme: str,
    word: str,  # noqa: ARG001
    unit_idx: int,  # noqa: ARG001
    units: list[_GraphemeUnit],  # noqa: ARG001
) -> int:
    """Return the number of phonemes produced by a single grapheme unit.

    Most units produce exactly 1 phoneme.  Exceptions:
    - ``gü`` before e/i → 2 phonemes (ɡ + w)
    - ``x`` → 2 phonemes (k + s)
    - silent ``h`` → 0 phonemes
    """
    base = ""
    for ch in grapheme:
        base += _ACCENT_MAP.get(ch, ch)

    # Silent h
    if base == "h":
        return 0

    # gü digraph → 2 phonemes
    if len(base) == 2 and base[0] == "g" and grapheme[1] == "ü":
        return 2

    # x → ks (2 phonemes)
    if base == "x":
        return 2

    # sc digraph (consumed as single unit in _g2p_word when before e/i)
    # This doesn't apply here because _segment_graphemes doesn't produce
    # an "sc" unit — it's handled by the G2P loop.  So "s" alone → 1.

    # Everything else (single chars, ch, ll, rr, qu, gu) → 1
    return 1


def _insert_stress_marker(
    phonemes: list[str],
    word: str,
    *,
    units: list[_GraphemeUnit] | None = None,
    boundaries: list[int] | None = None,
    stressed_syl: int | None = None,
) -> list[str]:
    """Insert stress marker ˈ before the stressed syllable's first vowel.

    Uses ``_segment_graphemes`` for reliable char-to-phoneme mapping so
    that digraphs like ``qu``, ``gu``, ``gü`` are handled correctly.

    If *units*, *boundaries*, and/or *stressed_syl* are provided, they
    are used directly instead of recomputing them (performance optimisation).
    """
    if not phonemes:
        return phonemes

    if units is None:
        units = _segment_graphemes(word)
    if boundaries is None:
        boundaries = _find_syllable_boundaries(word, units=units)
    if stressed_syl is None:
        stressed_syl = _get_stressed_syllable(word, units=units, boundaries=boundaries)

    if not boundaries:
        return phonemes

    num_units = len(units)

    if stressed_syl >= len(boundaries):
        return phonemes

    syl_start = boundaries[stressed_syl]
    syl_end = (
        boundaries[stressed_syl + 1]
        if stressed_syl + 1 < len(boundaries)
        else num_units
    )

    # Find first vowel grapheme-unit in the stressed syllable
    stressed_unit_idx = None
    for uid in range(syl_start, syl_end):
        if uid < num_units and units[uid][1]:  # is_vowel
            stressed_unit_idx = uid
            break

    if stressed_unit_idx is None:
        return phonemes

    # Walk grapheme units and accumulate phoneme count to map
    # the stressed unit index to a phoneme index.
    ph_i = 0
    for uid in range(num_units):
        if uid == stressed_unit_idx:
            # ph_i now points to the phoneme for this vowel
            return phonemes[:ph_i] + ["ˈ"] + phonemes[ph_i:]
        count = _phoneme_count_for_unit(units[uid][0], word, uid, units)
        ph_i += count

    return phonemes


def _phonemize_spanish_raw(text: str) -> list[str]:
    """Convert Spanish text to raw phoneme list (without BOS/EOS).

    Returns PUA-mapped tokens.
    """
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes: list[str] = []
    need_space = False

    for token in tokens:
        # Check if pure punctuation
        if all(c in _PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
            continue

        # Regular word
        if need_space:
            phonemes.append(" ")

        word_phonemes, stressed_syl, units, boundaries = _g2p_word(token)
        # Skip stress marker for common unstressed function words
        if token in _UNSTRESSED_FUNCTION_WORDS:
            word_with_stress = word_phonemes
        else:
            word_with_stress = _insert_stress_marker(
                word_phonemes,
                token,
                units=units,
                boundaries=boundaries,
                stressed_syl=stressed_syl,
            )

        for ph in word_with_stress:
            phonemes.append(ph)

        need_space = True

    # Map multi-character tokens (rr, tʃ, etc.) to PUA codepoints
    return map_sequence(phonemes)


def phonemize_spanish(text: str) -> list[str]:
    """Phonemize Spanish text. Returns tokens after map_sequence."""
    phonemes = _phonemize_spanish_raw(text)
    tokens = ["^"] + phonemes + ["$"]
    return map_sequence(tokens)
