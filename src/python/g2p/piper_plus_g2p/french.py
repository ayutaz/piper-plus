"""Rule-based French phonemizer for piper-g2p.

Converts French text to IPA phonemes using grapheme-to-phoneme rules.
No external G2P engine required.

Liaison / elision support (limited):
    - **Elision**: apostrophe clitics (l', d', j', n', s', c', qu', m', t')
      are merged with the following word so no spurious space or silent-final
      rule fires between the clitic and its host.
    - **Liaison**: the most frequent *obligatory* liaison patterns are handled:
      determiner/pronoun + vowel-initial word (les amis -> /lez‿ami/,
      un ami -> /ɛ̃n‿ami/, en été -> /ɑ̃n‿ete/, etc.).
    - **Known limitations**: h aspiré / h muet distinction is not implemented
      (all h is treated as silent).  Enchaînement, optional liaisons, and
      liaison blocking (e.g. after singular nouns) are not handled.
"""

import logging
import re
import unicodedata

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "phonemize_french",
    "phonemize_french_with_prosody",
    "FrenchPhonemizer",
]

# Punctuation characters
_PUNCTUATION = set(",.;:!?¡¿—–…«»")

# Vowel letters (for context checks)
_VOWELS = set("aeiouyàâæéèêëîïôùûüœ")

# Consonant letters
_CONSONANTS = set("bcdfghjklmnpqrstvwxz")

# Common silent final consonants
_SILENT_FINAL = set("dghmnpstxz")

# Words where "ille" is pronounced /il/ not /ij/
_ILLE_AS_IL = {"ville", "mille", "tranquille"}

# Elision clitics: word fragments that appear before an apostrophe.
# When followed by a vowel-initial word, the clitic is merged with
# the host word for phonemization (no space, no silent-final rule).
_ELISION_CLITICS = {"l", "d", "j", "n", "s", "c", "m", "t", "qu"}

# Liaison rules: (trigger_word, linking_consonant)
# Only the most frequent obligatory liaison contexts are covered.
# The linking consonant is prepended to the following vowel-initial word.
_LIAISON_WORDS: dict[str, str] = {
    # Articles / determiners
    "les": "z",
    "des": "z",
    "ces": "z",
    "mes": "z",
    "tes": "z",
    "ses": "z",
    "nos": "z",
    "vos": "z",
    "aux": "z",
    # Adjectives (common prenominal)
    "petits": "z",
    "grands": "z",
    "gros": "z",
    # Numerals
    "deux": "z",
    "trois": "z",
    "six": "z",
    "dix": "z",
    # Subject pronouns
    "nous": "z",
    "vous": "z",
    "ils": "z",
    "elles": "z",
    "on": "n",
    # Prepositions / adverbs
    "en": "n",
    "dans": "z",
    "sans": "z",
    "chez": "z",
    # "un" -> /n/ liaison
    "un": "n",
    # "mon/ton/son" already end in pronounced /n/ via nasal rules,
    # but liaison adds explicit /n/ before vowel-initial words.
    "mon": "n",
    "ton": "n",
    "son": "n",
    # Common short words
    "tout": "t",
    "quand": "t",
    "très": "z",
    "plus": "z",
    # est (3rd person singular of être)
    "est": "t",
    # Verbs (3rd person plural)
    "ont": "t",
    "sont": "t",
    "font": "t",
    "vont": "t",
}

# Polysyllabic words ending in -er that are pronounced /ɛʁ/ (not /e/)
# These are exceptions to the verb infinitive -er → /e/ rule.
_ER_AS_EHR = {
    "hiver",
    "enfer",
    "amer",
    "cancer",
    "super",
    "laser",
    "hamster",
    "master",
    "poster",
    "cluster",
    "starter",
    "leader",
    "transfer",
    "fer",
}


def _normalize(text: str) -> str:
    """Normalize text: lowercase, normalize unicode, strip extra whitespace."""
    text = text.strip()
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _is_vowel_char(ch: str) -> bool:
    return ch in _VOWELS


def _is_consonant_char(ch: str) -> bool:
    return ch in _CONSONANTS


def _convert_word(word: str) -> list[str]:
    """Convert a French word to IPA phonemes.

    Handles French grapheme-to-phoneme rules including:
    - Nasal vowels
    - Vowel digraphs (ou, au, eau, ai, ei, eu, oi, etc.)
    - Silent letters and final consonants
    - Consonant digraphs (ch, gn, ph, th, qu, gu)
    - Intervocalic s voicing (s between vowels -> z)
    - -er verb endings
    - Context-dependent x handling
    - Semi-vowel ɥ (u before i after consonant)
    - -aille/-eille/-ouille/-ille patterns
    """
    phonemes: list[str] = []
    i = 0
    n = len(word)

    while i < n:
        ch = word[i]

        # ---------------------------------------------------------------
        # Multi-character sequences (longest match first)
        # ---------------------------------------------------------------

        # -er word-final: verb infinitive ending -> /e/
        # Only apply to polysyllabic words (parler, manger); monosyllabic words
        # like mer, fer, ver keep /ɛʁ/ pronunciation.
        # Exception list (_ER_AS_EHR): polysyllabic words like "hiver", "enfer"
        # that keep /ɛʁ/ pronunciation.
        if ch == "e" and i + 1 == n - 1 and word[i + 1] == "r":
            # Only apply -er→/e/ for words with at least 2 vowel groups
            # AND not in the exception list
            vowel_count = sum(1 for c in word if c in _VOWELS)
            if vowel_count >= 2 and word not in _ER_AS_EHR:
                # Word ends in "er" (polysyllabic)
                if i > 0 and word[i - 1] in "iy":
                    # -ier/-yer: the 'i'/'y' already produced 'j' (or 'i'),
                    # just produce /e/ for 'er' and skip 'r'
                    phonemes.append("e")
                else:
                    phonemes.append("e")
                i += 2
                continue
            # else: monosyllabic -er (mer, fer) — fall through to normal e handling

        # "eau" -> o
        if ch == "e" and i + 2 < n and word[i + 1 : i + 3] == "au":
            phonemes.append("o")
            i += 3
            continue

        # "ouille" -> /uj/ (before end or consonant)
        if (
            ch == "o"
            and i + 5 <= n
            and word[i + 1 : i + 6] == "uille"
            and (i + 6 >= n or not _is_vowel_char(word[i + 6]))
        ):
            phonemes.append("u")
            phonemes.append("j")
            i += 6
            # Skip final silent 'e' already consumed
            continue

        # "aille" -> /aj/
        if (
            ch == "a"
            and i + 4 <= n
            and word[i + 1 : i + 5] == "ille"
            and (i + 5 >= n or not _is_vowel_char(word[i + 5]))
        ):
            phonemes.append("a")
            phonemes.append("j")
            i += 5
            continue

        # "euille" -> /œj/ (feuille, écureuil)
        if ch == "e" and i + 5 <= n and word[i + 1 : i + 6] == "uille" and i + 6 >= n:
            phonemes.append("œ")
            phonemes.append("j")
            i += 6
            continue

        # "eil" at word end -> /ɛj/ (soleil, réveil)
        if ch == "e" and i + 2 < n and word[i + 1 : i + 3] == "il" and i + 3 >= n:
            phonemes.append("ɛ")
            phonemes.append("j")
            i += 3
            continue

        # "eille" -> /ɛj/
        if (
            ch == "e"
            and i + 4 <= n
            and word[i + 1 : i + 5] == "ille"
            and (i + 5 >= n or not _is_vowel_char(word[i + 5]))
        ):
            phonemes.append("ɛ")
            phonemes.append("j")
            i += 5
            continue

        # "ain", "aim" -> ɛ̃ (before consonant or end)
        if (
            ch == "a"
            and i + 2 < n
            and word[i + 1] == "i"
            and word[i + 2] in "nm"
            and (i + 3 >= n or not _is_vowel_char(word[i + 3]))
        ):
            phonemes.append("ɛ̃")
            i += 3
            continue

        # "ein", "eim" -> ɛ̃
        if (
            ch == "e"
            and i + 2 < n
            and word[i + 1] == "i"
            and word[i + 2] in "nm"
            and (i + 3 >= n or not _is_vowel_char(word[i + 3]))
        ):
            phonemes.append("ɛ̃")
            i += 3
            continue

        # "oin" -> wɛ̃
        if (
            ch == "o"
            and i + 2 < n
            and word[i + 1 : i + 3] == "in"
            and (i + 3 >= n or not _is_vowel_char(word[i + 3]))
        ):
            phonemes.append("w")
            phonemes.append("ɛ̃")
            i += 3
            continue

        # "ien" -> jɛ̃
        if (
            ch == "i"
            and i + 2 < n
            and word[i + 1 : i + 3] == "en"
            and (i + 3 >= n or not _is_vowel_char(word[i + 3]))
        ):
            phonemes.append("j")
            phonemes.append("ɛ̃")
            i += 3
            continue

        # "stion" -> /stjɔ̃/ (NOT /ssjɔ̃/)
        # "tion" -> /sjɔ̃/ (only when NOT preceded by 's')
        if (
            ch == "t"
            and i + 3 < n
            and word[i + 1 : i + 4] == "ion"
            and (i + 4 >= n or not _is_vowel_char(word[i + 4]))
        ):
            # Check if preceded by 's' — if so, produce /tjɔ̃/
            # (the 's' already produced /s/, so we just need /t/)
            if i > 0 and word[i - 1] == "s":
                phonemes.append("t")
            else:
                phonemes.append("s")
            phonemes.append("j")
            phonemes.append("ɔ̃")
            i += 4
            continue

        # "ille" -> /ij/ by default, but /il/ for exceptions (ville, mille, etc.)
        if (
            ch == "i"
            and i + 3 < n
            and word[i + 1 : i + 4] == "lle"
            and (i + 4 >= n or not _is_vowel_char(word[i + 4]))
        ):
            if word in _ILLE_AS_IL:
                phonemes.append("i")
                phonemes.append("l")
            else:
                phonemes.append("i")
                phonemes.append("j")
            i += 4
            continue

        # "gn" -> ɲ
        if ch == "g" and i + 1 < n and word[i + 1] == "n":
            phonemes.append("ɲ")
            i += 2
            continue

        # "ph" -> f
        if ch == "p" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("f")
            i += 2
            continue

        # "th" -> t
        if ch == "t" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("t")
            i += 2
            continue

        # "ch" -> ʃ
        if ch == "c" and i + 1 < n and word[i + 1] == "h":
            phonemes.append("ʃ")
            i += 2
            continue

        # "qu" -> k
        if ch == "q" and i + 1 < n and word[i + 1] == "u":
            phonemes.append("k")
            i += 2
            continue

        # "gu" before e/i -> ɡ (u silent)
        if (
            ch == "g"
            and i + 1 < n
            and word[i + 1] == "u"
            and i + 2 < n
            and word[i + 2] in "eiéèêëîï"
        ):
            phonemes.append("ɡ")
            i += 2
            continue

        # ---------------------------------------------------------------
        # Nasal vowels: vowel + n/m before consonant or end
        # ---------------------------------------------------------------

        # "an", "am", "en", "em" -> ɑ̃
        if ch in "ae" and i + 1 < n and word[i + 1] in "nm":
            # Not nasal if followed by another vowel or doubled n/m
            if i + 2 >= n:
                phonemes.append("ɑ̃")
                i += 2
                continue
            if not _is_vowel_char(word[i + 2]) and word[i + 2] != word[i + 1]:
                phonemes.append("ɑ̃")
                i += 2
                continue

        # "in", "im" -> ɛ̃
        if ch == "i" and i + 1 < n and word[i + 1] in "nm":
            if i + 2 >= n:
                phonemes.append("ɛ̃")
                i += 2
                continue
            if not _is_vowel_char(word[i + 2]) and word[i + 2] != word[i + 1]:
                phonemes.append("ɛ̃")
                i += 2
                continue

        # "on", "om" -> ɔ̃
        if ch == "o" and i + 1 < n and word[i + 1] in "nm":
            if i + 2 >= n:
                phonemes.append("ɔ̃")
                i += 2
                continue
            if not _is_vowel_char(word[i + 2]) and word[i + 2] != word[i + 1]:
                phonemes.append("ɔ̃")
                i += 2
                continue

        # "un", "um" -> ɛ̃ (modern French merger)
        if ch == "u" and i + 1 < n and word[i + 1] in "nm":
            if i + 2 >= n:
                phonemes.append("ɛ̃")
                i += 2
                continue
            if not _is_vowel_char(word[i + 2]) and word[i + 2] != word[i + 1]:
                phonemes.append("ɛ̃")
                i += 2
                continue

        # "yn", "ym" before consonant -> ɛ̃ (syndicat, symbole)
        if ch == "y" and i + 1 < n and word[i + 1] in "nm":
            if i + 2 >= n:
                phonemes.append("ɛ̃")
                i += 2
                continue
            if not _is_vowel_char(word[i + 2]) and word[i + 2] != word[i + 1]:
                phonemes.append("ɛ̃")
                i += 2
                continue

        # ---------------------------------------------------------------
        # Vowel digraphs
        # ---------------------------------------------------------------

        # "ou" -> u
        if ch == "o" and i + 1 < n and word[i + 1] == "u":
            phonemes.append("u")
            i += 2
            continue

        # "au" -> o
        if ch == "a" and i + 1 < n and word[i + 1] == "u":
            phonemes.append("o")
            i += 2
            continue

        # "oi" -> wa
        if ch == "o" and i + 1 < n and word[i + 1] == "i":
            phonemes.append("w")
            phonemes.append("a")
            i += 2
            continue

        # "ai" -> ɛ
        if ch == "a" and i + 1 < n and word[i + 1] == "i":
            phonemes.append("ɛ")
            i += 2
            continue

        # "ei" -> ɛ
        if ch == "e" and i + 1 < n and word[i + 1] == "i":
            phonemes.append("ɛ")
            i += 2
            continue

        # "eu", "œu" -> ø (closed) or œ (open, before pronounced consonant)
        if (ch == "e" and i + 1 < n and word[i + 1] == "u") or (
            ch == "œ" and i + 1 < n and word[i + 1] == "u"
        ):
            # Open before pronounced consonant in same syllable
            if (
                i + 2 < n
                and _is_consonant_char(word[i + 2])
                and word[i + 2] not in _SILENT_FINAL
            ):
                phonemes.append("œ")
            else:
                phonemes.append("ø")
            i += 2
            continue

        # ---------------------------------------------------------------
        # Single vowels
        # ---------------------------------------------------------------

        if ch == "é":
            phonemes.append("e")
            i += 1
            continue

        if ch in "èê":
            phonemes.append("ɛ")
            i += 1
            continue

        if ch == "ë":
            phonemes.append("ɛ")
            i += 1
            continue

        if ch in "àâ":
            phonemes.append("a")
            i += 1
            continue

        if ch == "a":
            phonemes.append("a")
            i += 1
            continue

        if ch in "îï":
            phonemes.append("i")
            i += 1
            continue

        if ch == "i":
            # "i" before vowel -> j (semi-vowel), EXCEPT before word-final
            # silent 'e' (vie→/vi/, amie→/ami/, not */vj/, */amj/)
            if i + 1 < n and _is_vowel_char(word[i + 1]):
                # Don't glide before word-final silent 'e'
                if i + 1 == n - 1 and word[i + 1] == "e":
                    phonemes.append("i")
                else:
                    phonemes.append("j")
            else:
                phonemes.append("i")
            i += 1
            continue

        if ch == "ô":
            phonemes.append("o")
            i += 1
            continue

        if ch == "o":
            # Open /ɔ/ before a pronounced consonant at word end (porte, or, homme).
            # Closed /o/ elsewhere (mot, beau already handled above).
            # Strip a trailing silent 'e' (or 'es') for the check, e.g. "porte" → "rt".
            remaining = word[i + 1 :]
            effective = remaining
            if effective.endswith("es"):
                effective = effective[:-2]
            elif effective.endswith("e"):
                effective = effective[:-1]
            if (
                effective
                and all(c in _CONSONANTS for c in effective)
                and any(c not in _SILENT_FINAL for c in effective)
            ):
                phonemes.append("ɔ")
            else:
                phonemes.append("o")
            i += 1
            continue

        if ch in "ùû":
            phonemes.append("y_vowel")
            i += 1
            continue

        if ch == "ü":
            phonemes.append("y_vowel")
            i += 1
            continue

        if ch == "u":
            # Semi-vowel ɥ: u before i (after consonant) -> ɥ
            if i + 1 < n and word[i + 1] == "i":
                phonemes.append("ɥ")
                phonemes.append("i")
                i += 2
                continue
            # "u" after g/q already handled; standalone u -> y_vowel
            phonemes.append("y_vowel")
            i += 1
            continue

        if ch == "y":
            # 'y' in French usually acts as 'i'
            if i + 1 < n and _is_vowel_char(word[i + 1]):
                phonemes.append("j")
            else:
                phonemes.append("i")
            i += 1
            continue

        if ch == "œ":
            phonemes.append("œ")
            i += 1
            continue

        if ch == "æ":
            phonemes.append("e")
            i += 1
            continue

        # "e" context-dependent
        if ch == "e":
            # Final silent e (e muet) -- skip at word end
            if i == n - 1:
                # Word-final 'e' is usually silent
                i += 1
                continue
            remaining = word[i + 1 :]
            # ɛ in closed syllable:
            #   (a) before 2+ leading consonants (merci, service, berceau)
            #   (b) before only consonant(s) with at least one pronounced final one
            if remaining:
                consonant_count = 0
                for c in remaining:
                    if c in _CONSONANTS:
                        consonant_count += 1
                    else:
                        break
                if (
                    consonant_count >= 2
                    or all(c in _CONSONANTS for c in remaining)
                    and any(c not in _SILENT_FINAL for c in remaining)
                ):
                    phonemes.append("ɛ")
                else:
                    phonemes.append("ə")
            else:
                phonemes.append("ə")
            i += 1
            continue

        # ---------------------------------------------------------------
        # Consonants
        # ---------------------------------------------------------------

        if ch == "c":
            # c before e, i, y -> s
            if i + 1 < n and word[i + 1] in "eiyéèêë":
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
            # g before e, i, y -> ʒ
            if i + 1 < n and word[i + 1] in "eiyéèêë":
                phonemes.append("ʒ")
            else:
                phonemes.append("ɡ")
            i += 1
            continue

        if ch == "j":
            phonemes.append("ʒ")
            i += 1
            continue

        if ch == "r":
            phonemes.append("ʁ")
            # Skip doubled r (terre, guerre → single /ʁ/)
            if i + 1 < n and word[i + 1] == "r":
                i += 2
            else:
                i += 1
            continue

        # x: context-dependent handling
        if ch == "x":
            # Word-final x is usually silent
            if i == n - 1:
                i += 1
                continue
            # Also silent before final silent 'e'/'es'
            remaining_after = word[i + 1 :]
            if remaining_after in ("e", "es"):
                i += 1
                continue
            # "ex" + vowel -> /ɛgz/ (handled: x is after e, next is vowel)
            if (
                i > 0
                and word[i - 1] == "e"
                and i + 1 < n
                and _is_vowel_char(word[i + 1])
            ):
                phonemes.append("ɡ")
                phonemes.append("z")
                i += 1
                continue
            # Default: x -> /ks/
            phonemes.append("k")
            phonemes.append("s")
            i += 1
            continue

        if ch == "h":
            # h is always silent in French
            i += 1
            continue

        # Double consonants -> single
        if i + 1 < n and word[i + 1] == ch and ch in _CONSONANTS:
            # Just produce one consonant sound
            pass  # fall through to simple mapping below

        # Simple consonant mappings
        simple_consonants = {
            "b": "b",
            "d": "d",
            "f": "f",
            "k": "k",
            "l": "l",
            "m": "m",
            "n": "n",
            "p": "p",
            "s": "s",
            "t": "t",
            "v": "v",
            "w": "w",
            "z": "z",
        }

        if ch in simple_consonants:
            # Handle final silent consonants
            # A consonant is "final" if it's word-final or before final silent e/es
            # BUT: consonant before final 'e' should be PRONOUNCED (e is silent,
            # not the consonant). Only truly word-final consonants may be silent.
            is_word_final = i == n - 1
            # Before final 's' (e.g., "temps") — the consonant+s are both silent
            is_before_final_s = i == n - 2 and word[n - 1] == "s"
            is_final = is_word_final or is_before_final_s

            if is_final and ch in _SILENT_FINAL:
                i += 1
                continue

            # Intervocalic s voicing: single 's' between two vowels -> /z/
            if ch == "s":
                prev_is_vowel = i > 0 and _is_vowel_char(word[i - 1])
                next_is_vowel = i + 1 < n and _is_vowel_char(word[i + 1])
                is_single = not (i + 1 < n and word[i + 1] == "s")
                if prev_is_vowel and next_is_vowel and is_single:
                    phonemes.append("z")
                    i += 1
                    continue

            phonemes.append(simple_consonants[ch])
            # Skip doubled consonant
            if i + 1 < n and word[i + 1] == ch:
                i += 2
            else:
                i += 1
            continue

        # Punctuation or unknown
        if ch in _PUNCTUATION:
            phonemes.append(ch)
            i += 1
            continue

        # Skip unknown characters
        i += 1

    return phonemes


def _starts_with_vowel_sound(word: str) -> bool:
    """Check whether a word starts with a vowel sound.

    In French, words starting with a vowel letter or silent 'h' followed by a
    vowel are considered vowel-initial for liaison / elision purposes.

    Known limitation: h aspiré (e.g. "haricot", "héros") is NOT distinguished
    from h muet (e.g. "homme", "heure").  All 'h' is treated as silent.
    """
    if not word:
        return False
    first = word[0]
    if first in _VOWELS:
        return True
    # Silent h + vowel
    return bool(first == "h" and len(word) > 1 and word[1] in _VOWELS)


def _split_words(text: str) -> list[str]:
    """Split text into words and punctuation tokens.

    Apostrophes (both straight ' and curly right-single-quote) act as word
    boundaries in French elision.  Recognised elision clitics (l', d', j',
    n', s', c', qu', m', t') are merged with the following word so that the
    phonemizer treats them as a single unit -- e.g. "l'ami" -> ["lami"],
    "d'accord" -> ["daccord"], "qu'il" -> ["quil"].

    This prevents spurious silent-final rules from firing on the clitic
    fragment and ensures the clitic consonant is always pronounced.
    """
    # Normalise curly/typographic apostrophes to straight apostrophe.
    text = text.replace("\u2019", "'").replace("\u2018", "'")

    # Tokenise keeping apostrophes attached so we can detect clitics.
    # Pattern: sequences of letters possibly containing internal apostrophes,
    # OR standalone punctuation.
    raw_tokens = re.findall(
        r"[a-zàâæéèêëîïôùûüœçñ]+(?:'[a-zàâæéèêëîïôùûüœçñ]+)*|[,.;:!?¡¿—–…«»]",
        text,
        re.IGNORECASE,
    )

    tokens: list[str] = []
    for raw in raw_tokens:
        if "'" not in raw:
            tokens.append(raw)
            continue

        # Split on apostrophe and merge recognised clitics.
        parts = raw.split("'")
        buf = ""
        for k, part in enumerate(parts):
            if buf:
                # Previous part was a recognised clitic -- merge.
                buf += part
            elif k < len(parts) - 1 and part.lower() in _ELISION_CLITICS:
                # This part is a clitic; start merging with next part.
                buf = part
            else:
                # Not a clitic; emit as standalone token.
                if part:
                    tokens.append(part)
        if buf:
            tokens.append(buf)

    return tokens


def _apply_liaison(tokens: list[str]) -> list[tuple[str, str | None]]:
    """Determine liaison linking consonants between adjacent word tokens.

    Returns a list of ``(token, liaison_phoneme)`` pairs.  ``liaison_phoneme``
    is a single IPA consonant string (e.g. ``"z"``, ``"n"``, ``"t"``) when
    the token triggers a liaison with the *next* vowel-initial word, or
    ``None`` otherwise.

    Only the most frequent obligatory liaison contexts are handled
    (determiners, pronouns, common prepositions).  Optional and forbidden
    liaisons are not attempted.
    """
    result: list[tuple[str, str | None]] = []
    for idx, token in enumerate(tokens):
        is_punct = all(ch in _PUNCTUATION for ch in token)
        if is_punct:
            result.append((token, None))
            continue

        linking: str | None = None
        lower_token = token.lower()
        if lower_token in _LIAISON_WORDS:
            # Look ahead for the next non-punctuation token.
            next_word: str | None = None
            for j in range(idx + 1, len(tokens)):
                candidate = tokens[j]
                if not all(ch in _PUNCTUATION for ch in candidate):
                    next_word = candidate
                    break
                # Stop at punctuation (liaison blocked by sentence boundary).
                break
            if next_word is not None and _starts_with_vowel_sound(next_word.lower()):
                linking = _LIAISON_WORDS[lower_token]

        result.append((token, linking))
    return result


def phonemize_french_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert French text to phoneme list and prosody features.

    French has fixed stress on the last syllable of each word/phrase.

    Elision clitics (l', d', j', ...) are merged with the following word
    during tokenisation so they are phonemized as one unit.  Obligatory
    liaison linking consonants (e.g. /z/ in "les amis") are inserted between
    words when the trigger word is in ``_LIAISON_WORDS`` and the next word
    starts with a vowel sound.

    Known limitations: h aspire / h muet distinction is not implemented.
    Enchainement and optional liaisons are not handled.

    Returns:
        (phonemes, prosody_list) with ProsodyInfo for each phoneme.
        a1=0, a2=stress level (0 or 2 for last syllable), a3=word phoneme count.
    """
    text = _normalize(text)
    tokens = _split_words(text)
    liaison_pairs = _apply_liaison(tokens)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    # Vowel phoneme set for stress detection
    vowel_phonemes = {
        "a",
        "e",
        "ɛ",
        "i",
        "o",
        "ɔ",
        "u",
        "y_vowel",
        "ə",
        "ø",
        "œ",
        "ɛ̃",
        "ɑ̃",
        "ɔ̃",
    }

    # IPA symbols for liaison consonant phonemes
    _liaison_consonant_ipa: dict[str, str] = {
        "z": "z",
        "n": "n",
        "t": "t",
    }

    for token, liaison in liaison_pairs:
        is_punct = all(ch in _PUNCTUATION for ch in token)

        if not is_punct and need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        if is_punct:
            for ch in token:
                phonemes.append(ch)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
        else:
            word_phonemes = _convert_word(token)

            # If this word has a liaison consonant, append it to the word's
            # phoneme list so it is heard before the following vowel-initial
            # word.  The linking consonant is treated as part of this word
            # for prosody purposes.
            if liaison is not None:
                ipa = _liaison_consonant_ipa.get(liaison, liaison)
                word_phonemes.append(ipa)

            word_phoneme_count = len(word_phonemes)

            # French: stress always on last syllable (last vowel phoneme)
            last_vowel_idx = -1
            for j in range(len(word_phonemes) - 1, -1, -1):
                if word_phonemes[j] in vowel_phonemes:
                    last_vowel_idx = j
                    break

            for j, ph in enumerate(word_phonemes):
                a2 = 2 if j == last_vowel_idx else 0
                phonemes.append(ph)
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))

        need_space = True

    return phonemes, prosody_list


def phonemize_french(text: str) -> list[str]:
    """Convert French text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_french_with_prosody(text)
    return phonemes


class FrenchPhonemizer(Phonemizer):
    """French rule-based phonemizer."""

    @property
    def language_code(self) -> str:
        return "fr"

    def phonemize(self, text: str) -> list[str]:
        return phonemize_french(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_french_with_prosody(text)
