"""English G2P module using g2p-en (Apache-2.0 licensed).

Converts English text to phoneme IDs and prosody features without
requiring espeak-ng or piper-phonemize (GPL dependencies).
"""

import logging
import re
import threading

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "phonemize_english",
    "phonemize_english_with_prosody",
    "EnglishPhonemizer",
]

# ---------------------------------------------------------------------------
# G2p instance cache — instantiating G2p() takes 100–500 ms; cache it at
# module level so repeated calls to phonemize_english() are fast.
# Thread-safe via double-checked locking.
# ---------------------------------------------------------------------------
_g2p_lock = threading.Lock()
_g2p_instance = None
_g2p_unavailable = False


def _get_g2p():
    """Return a cached G2p instance (or None if g2p_en is unavailable).

    Thread-safe: uses double-checked locking to avoid redundant
    instantiation when called from multiple threads.
    """
    global _g2p_instance, _g2p_unavailable
    if _g2p_unavailable:
        return None
    if _g2p_instance is not None:
        return _g2p_instance
    with _g2p_lock:
        # Double-check after acquiring lock
        if _g2p_unavailable:
            return None
        if _g2p_instance is None:
            try:
                from g2p_en import G2p  # noqa: PLC0415

                _g2p_instance = G2p()
            except ImportError as exc:
                _LOGGER.warning("g2p_en unavailable: %s", exc)
                _g2p_unavailable = True
                return None
    return _g2p_instance


# ARPAbet to espeak-compatible IPA mapping
ARPABET_TO_IPA: dict[str, str] = {
    "AA": "ɑ",
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
    # ER: unstressed → ɚ, stressed → ɜː (handled in _convert_word_to_ipa)
    "ER": "ɚ",
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

# Punctuation characters (attached to previous word, no space before)
_PUNCTUATION = set(",.;:!?")

# English function words (89 words) — stress is removed to match espeak-ng
# behavior.  espeak-ng does not place primary stress on common function words
# in connected speech.  g2p-en, however, marks them with stress=1 by default.
_FUNCTION_WORDS = {
    # articles / determiners
    "a",
    "an",
    "the",
    # pronouns
    "i",
    "me",
    "my",
    "mine",
    "myself",
    "you",
    "your",
    "yours",
    "yourself",
    "he",
    "him",
    "his",
    "himself",
    "she",
    "her",
    "hers",
    "herself",
    "it",
    "its",
    "itself",
    "we",
    "us",
    "our",
    "ours",
    "ourselves",
    "they",
    "them",
    "their",
    "theirs",
    "themselves",
    # be-verbs
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    # auxiliaries
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "can",
    "could",
    "may",
    "might",
    "must",
    # prepositions
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "to",
    "with",
    "about",
    "after",
    "before",
    "between",
    "into",
    "through",
    "under",
    # conjunctions
    "and",
    "but",
    "or",
    "nor",
    "so",
    "yet",
    "if",
    "that",
    "than",
    "when",
    "while",
    "as",
    "because",
    "since",
    # others
    "not",
    "no",
}


def _g2p_en_to_arpabet_tokens(text: str) -> list[list[str]]:
    """Convert text to ARPAbet tokens using g2p-en, grouped by word.

    Returns a list of words, each word being a list of ARPAbet tokens
    (e.g. ["HH", "AH0", "L", "OW1"]).
    Punctuation-only groups are kept as separate "words".
    """
    g2p = _get_g2p()
    if g2p is None:
        raise ImportError(
            "g2p_en is required for English phonemization. "
            "Install it with: pip install g2p-en"
        )
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


def _is_punctuation_word(word_tokens: list[str]) -> bool:
    """Check if a word consists entirely of punctuation."""
    return all(t in _PUNCTUATION for t in word_tokens)


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


def _convert_word_to_ipa(tokens: list[str]) -> list[tuple[str, int]]:
    """Convert a list of ARPAbet tokens to IPA with context-dependent rules.

    Handles:
    - AA + R → ɑːɹ (merge into single vowel+r)
    - ER with stress=1 → ɜː (stressed r-colored vowel)
    """
    result: list[tuple[str, int]] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        m = _RE_ARPABET.match(token)

        if m:
            base = m.group(1)
            stress_str = m.group(2)
            stress = int(stress_str) if stress_str is not None else -1

            # AA + R → ɑːɹ
            if base == "AA" and i + 1 < len(tokens) and tokens[i + 1] == "R":
                result.append(("ɑːɹ", stress))
                i += 2
                continue

            # Stressed ER → ɜː
            if base == "ER" and stress == 1:
                result.append(("ɜː", stress))
                i += 1
                continue

        ipa, stress = _arpabet_to_ipa(token)
        result.append((ipa, stress))
        i += 1

    return result


def _get_source_words(text: str) -> list[str]:
    """Extract source words from text for function-word detection.

    Returns only alphabetic words (no punctuation), matching the order
    of non-punctuation word groups from g2p-en.
    """
    return re.findall(r"[a-zA-Z']+", text.lower())


def phonemize_english_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert English text to phoneme list and prosody features.

    Produces espeak-ng compatible output:
    - Stress markers (ˈ/ˌ) before stressed vowels
    - Word boundary spaces between words
    - Punctuation attached to preceding word (no space before)
    - Function words have stress removed

    Returns:
        (phonemes, prosody_info_list) where each phoneme has corresponding
        prosody info with a1=0, a2=stress-based, a3=word phoneme count.
    """
    words = _g2p_en_to_arpabet_tokens(text)
    source_words = _get_source_words(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []

    # Build a mapping from word index (skipping punctuation) to source word
    src_idx = 0
    word_is_function: list[bool] = []
    for word_tokens in words:
        if _is_punctuation_word(word_tokens):
            word_is_function.append(False)
        else:
            is_func = False
            if src_idx < len(source_words):
                is_func = source_words[src_idx] in _FUNCTION_WORDS
                src_idx += 1
            word_is_function.append(is_func)

    need_space = False  # track whether next word needs a preceding space

    for word_idx, word_tokens in enumerate(words):
        is_punct = _is_punctuation_word(word_tokens)
        is_func = word_is_function[word_idx]

        # Punctuation attaches to previous word (no space before)
        # Regular words get a space before them (except the first)
        if not is_punct and need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        # Convert all tokens in the word to IPA (with context-dependent rules)
        word_ipas = _convert_word_to_ipa(word_tokens)
        if is_func:
            # Remove primary/secondary stress from function words (are, you, the, etc.)
            word_ipas = [
                (ipa, 0 if stress >= 1 else stress) for ipa, stress in word_ipas
            ]

        # A3 = total IPA character count for the word (actual phoneme tokens)
        word_phoneme_count = sum(len(ipa) for ipa, _ in word_ipas)

        for ipa, stress in word_ipas:
            # stress → A2: primary(1)→2, secondary(2)→1, none(0)→0, consonant(-1)→0
            if stress == 1:
                a2 = 2
            elif stress == 2:
                a2 = 1
            else:
                a2 = 0

            # Insert stress marker before stressed vowels (espeak-ng compatible)
            if stress == 1:
                phonemes.append("ˈ")
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))
            elif stress == 2:
                phonemes.append("ˌ")
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))

            # Each IPA character becomes a separate phoneme token
            for ch in ipa:
                prosody_list.append(ProsodyInfo(a1=0, a2=a2, a3=word_phoneme_count))
                phonemes.append(ch)

        # After a punctuation word, next word still needs space
        # After a regular word, next word needs space
        need_space = True

    return phonemes, prosody_list


def phonemize_english(text: str) -> list[str]:
    """Convert English text to phoneme list (without prosody)."""
    phonemes, _ = phonemize_english_with_prosody(text)
    return phonemes


class EnglishPhonemizer(Phonemizer):
    """English phonemizer using g2p-en."""

    @property
    def language_code(self) -> str:
        return "en"

    def phonemize(self, text: str) -> list[str]:
        return phonemize_english(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_english_with_prosody(text)
