"""Korean G2P module using g2pk2 and Hangul decomposition.

Converts Korean text to IPA phonemes for TTS training/inference.
g2pk2 (Apache-2.0) applies phonological rules (연음화 liaison, 비음화
nasalization, 격음화 aspiration, 경음화 tensification), then Hangul
syllables are decomposed into jamo and mapped to IPA.
"""

import logging
import re
import unicodedata

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "phonemize_korean",
    "phonemize_korean_with_prosody",
    "KoreanPhonemizer",
]

# ---------------------------------------------------------------------------
# Hangul syllable block range (U+AC00 .. U+D7A3)
# ---------------------------------------------------------------------------
_HANGUL_START = 0xAC00
_HANGUL_END = 0xD7A3

# Decomposition constants
_N_MEDIALS = 21
_N_FINALS = 28

# ---------------------------------------------------------------------------
# Initial consonants (초성) – 19 entries, index → IPA token list
# ---------------------------------------------------------------------------
_INITIAL_TO_IPA: list[list[str]] = [
    ["k"],  # 0: ㄱ
    ["k͈"],  # 1: ㄲ
    ["n"],  # 2: ㄴ
    ["t"],  # 3: ㄷ
    ["t͈"],  # 4: ㄸ
    ["ɾ"],  # 5: ㄹ
    ["m"],  # 6: ㅁ
    ["p"],  # 7: ㅂ
    ["p͈"],  # 8: ㅃ
    ["s"],  # 9: ㅅ
    ["s͈"],  # 10: ㅆ
    [],  # 11: ㅇ (silent in initial position)
    ["tɕ"],  # 12: ㅈ
    ["t͈ɕ"],  # 13: ㅉ
    ["tɕʰ"],  # 14: ㅊ
    ["kʰ"],  # 15: ㅋ
    ["tʰ"],  # 16: ㅌ
    ["pʰ"],  # 17: ㅍ
    ["h"],  # 18: ㅎ
]

# ---------------------------------------------------------------------------
# Medial vowels (중성) – 21 entries, index → IPA token list
# Diphthongs are decomposed into glide + vowel sequences.
# ---------------------------------------------------------------------------
_MEDIAL_TO_IPA: list[list[str]] = [
    ["a"],  # 0: ㅏ
    ["ɛ"],  # 1: ㅐ
    ["j", "a"],  # 2: ㅑ
    ["j", "ɛ"],  # 3: ㅒ
    ["ʌ"],  # 4: ㅓ
    ["e"],  # 5: ㅔ
    ["j", "ʌ"],  # 6: ㅕ
    ["j", "e"],  # 7: ㅖ
    ["o"],  # 8: ㅗ
    ["w", "a"],  # 9: ㅘ
    ["w", "ɛ"],  # 10: ㅙ
    ["w", "e"],  # 11: ㅚ (modern Seoul: diphthong [we], not monophthong [ø])
    ["j", "o"],  # 12: ㅛ
    ["u"],  # 13: ㅜ
    ["w", "ʌ"],  # 14: ㅝ
    ["w", "e"],  # 15: ㅞ
    ["w", "i"],  # 16: ㅟ
    ["j", "u"],  # 17: ㅠ
    ["ɯ"],  # 18: ㅡ
    ["ɰ", "i"],  # 19: ㅢ
    ["i"],  # 20: ㅣ
]

# ---------------------------------------------------------------------------
# Final consonants (종성) – 28 entries, index → IPA token list
# Index 0 = no final consonant.
# Complex finals (겹받침) are simplified to their representative sound.
# g2pk2 handles most complex-final resolution before we reach this stage.
# ---------------------------------------------------------------------------
_FINAL_TO_IPA: list[list[str]] = [
    [],  # 0: (none)
    ["k̚"],  # 1: ㄱ
    ["k̚"],  # 2: ㄲ
    ["k̚"],  # 3: ㄳ (ㄱ+ㅅ → k̚)
    ["n"],  # 4: ㄴ
    ["n"],  # 5: ㄵ (ㄴ+ㅈ → n)
    ["n"],  # 6: ㄶ (ㄴ+ㅎ → n)
    ["t̚"],  # 7: ㄷ
    ["l"],  # 8: ㄹ
    ["k̚"],  # 9: ㄺ (ㄹ+ㄱ → k̚)
    ["m"],  # 10: ㄻ (ㄹ+ㅁ → m)
    ["l"],  # 11: ㄼ (ㄹ+ㅂ → l)
    ["l"],  # 12: ㄽ (ㄹ+ㅅ → l)
    ["l"],  # 13: ㄾ (ㄹ+ㅌ → l)
    ["l"],  # 14: ㄿ (ㄹ+ㅍ → l)
    ["l"],  # 15: ㅀ (ㄹ+ㅎ → l)
    ["m"],  # 16: ㅁ
    ["p̚"],  # 17: ㅂ
    ["p̚"],  # 18: ㅄ (ㅂ+ㅅ → p̚)
    ["t̚"],  # 19: ㅅ
    ["t̚"],  # 20: ㅆ
    ["ŋ"],  # 21: ㅇ
    ["t̚"],  # 22: ㅈ
    ["t̚"],  # 23: ㅊ
    ["k̚"],  # 24: ㅋ
    ["t̚"],  # 25: ㅌ
    ["p̚"],  # 26: ㅍ
    ["t̚"],  # 27: ㅎ
]

# Punctuation characters (passed through as-is)
_PUNCTUATION = set(",.;:!?。，！？、")

# Regex to split text into word-tokens and whitespace
_RE_WORD_SPLIT = re.compile(r"(\s+)")


def _is_hangul_syllable(ch: str) -> bool:
    """Check if character is a composed Hangul syllable (U+AC00..U+D7A3)."""
    code = ord(ch)
    return _HANGUL_START <= code <= _HANGUL_END


def _decompose_syllable(ch: str) -> tuple[int, int, int]:
    """Decompose a Hangul syllable into (initial, medial, final) indices."""
    code = ord(ch) - _HANGUL_START
    initial = code // (_N_MEDIALS * _N_FINALS)
    medial = (code % (_N_MEDIALS * _N_FINALS)) // _N_FINALS
    final = code % _N_FINALS
    return initial, medial, final


def _syllable_to_ipa(ch: str) -> list[str]:
    """Convert a single Hangul syllable to a list of IPA tokens."""
    initial, medial, final = _decompose_syllable(ch)
    phonemes: list[str] = []
    phonemes.extend(_INITIAL_TO_IPA[initial])
    phonemes.extend(_MEDIAL_TO_IPA[medial])
    phonemes.extend(_FINAL_TO_IPA[final])
    return phonemes


_g2p_instance = None
_g2p_unavailable = False


def _apply_g2p(text: str) -> str:
    """Apply g2pk2 phonological rules to Korean text.

    Raises ImportError if g2pk2 is not installed.
    Falls back to the original text if g2pk2 encounters a runtime error
    (e.g. mecab backend missing or unexpected input).
    """
    global _g2p_instance, _g2p_unavailable  # noqa: PLW0603
    if _g2p_unavailable:
        raise ImportError(
            "g2pk2 is required for Korean phonemization. "
            "Install with: pip install g2pk2"
        )
    if _g2p_instance is None:
        try:
            from g2pk2 import G2p  # noqa: PLC0415

            _g2p_instance = G2p()
        except (ImportError, SyntaxError, AttributeError) as exc:
            _g2p_unavailable = True
            raise ImportError(
                "g2pk2 is required for Korean phonemization. "
                "Install with: pip install g2pk2"
            ) from exc
    try:
        return str(_g2p_instance(text))
    except AttributeError:
        # G2p() succeeded but mecab is None (python-mecab-ko not installed).
        _g2p_instance = None
        _g2p_unavailable = True
        raise ImportError(
            "g2pk2 mecab backend not available. "
            "Install with: pip install python-mecab-ko"
        ) from None
    except Exception as exc:  # noqa: BLE001
        # Catch any other runtime error (IndexError, KeyError, ValueError, etc.)
        # that can occur with unusual or mixed-script input.
        _LOGGER.debug("g2pk2 failed on input %r: %s", text, exc)
        return text


def _count_hangul_syllables(word: str) -> int:
    """Count the number of Hangul syllables in a word."""
    return sum(1 for ch in word if _is_hangul_syllable(ch))


def phonemize_korean_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Korean text to IPA phonemes with prosody information.

    Uses g2pk2 for phonological rule application (연음화, 비음화, 격음화,
    경음화), then decomposes Hangul syllables into jamo and maps to IPA.

    Prosody values:
    - a1: 0 (Korean has no pitch accent like Japanese)
    - a2: 0 (Korean has no lexical stress like English)
    - a3: number of Hangul syllables in the current word

    Returns:
        (phonemes, prosody_list) where phonemes are raw IPA tokens.
    """
    # Normalize to NFC to handle NFD-decomposed Hangul jamo
    text = unicodedata.normalize("NFC", text)

    # Apply phonological rules via g2pk2
    processed = _apply_g2p(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []

    # Split by whitespace while preserving structure
    parts = _RE_WORD_SPLIT.split(processed)

    need_space = False
    for part in parts:
        # Skip empty strings from split
        if not part:
            continue

        # Whitespace between words → mark that next word needs a space
        if part.isspace():
            need_space = True
            continue

        # Insert word-boundary space token
        if need_space and phonemes:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        syllable_count = _count_hangul_syllables(part)
        word_prosody = ProsodyInfo(a1=0, a2=0, a3=max(syllable_count, 1))

        for ch in part:
            if _is_hangul_syllable(ch):
                ipa_tokens = _syllable_to_ipa(ch)
                for token in ipa_tokens:
                    phonemes.append(token)
                    prosody_list.append(word_prosody)
            elif ch in _PUNCTUATION:
                phonemes.append(ch)
                prosody_list.append(None)
            elif ch.isalpha():
                # Non-Hangul alphabetic characters (e.g., Latin) — pass through
                phonemes.append(ch)
                prosody_list.append(word_prosody)
            # Digits and other characters are skipped

        need_space = True

    return phonemes, prosody_list


def phonemize_korean(text: str) -> list[str]:
    """Convert Korean text to a list of IPA phoneme tokens."""
    phonemes, _ = phonemize_korean_with_prosody(text)
    return phonemes


class KoreanPhonemizer(Phonemizer):
    """Korean phonemizer using g2pk2 and Hangul decomposition."""

    @property
    def language_code(self) -> str:
        return "ko"

    def phonemize(self, text: str) -> list[str]:
        return phonemize_korean(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_korean_with_prosody(text)
