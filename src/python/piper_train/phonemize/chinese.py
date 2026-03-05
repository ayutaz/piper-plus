"""Chinese (Mandarin) phonemizer using pypinyin for Piper TTS.

Converts Chinese text to IPA phonemes via pinyin intermediate representation.
pypinyin (MIT license) handles character-to-pinyin conversion including
polyphone disambiguation.
"""

import logging
import re

from .base import Phonemizer, ProsodyInfo
from .token_mapper import map_sequence

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "phonemize_chinese",
    "phonemize_chinese_with_prosody",
    "ChinesePhonemizer",
]

# Punctuation mapping (Chinese → Western equivalents)
_ZH_PUNCT_MAP: dict[str, str] = {
    "\u3002": ".",   # 。
    "\uff0c": ",",   # ，
    "\uff01": "!",   # ！
    "\uff1f": "?",   # ？
    "\u3001": ",",   # 、
    "\uff1b": ";",   # ；
    "\uff1a": ":",   # ：
}

_PUNCTUATION = set(",.;:!?\u3002\uff0c\uff01\uff1f\u3001\uff1b\uff1a\u201c\u201d\u2018\u2019\u2026\u2014")

# ---------------------------------------------------------------------------
# Pinyin initial → IPA mapping
# ---------------------------------------------------------------------------
# In Mandarin phonology, pinyin letters map differently from English:
# b=[p], p=[pʰ], d=[t], t=[tʰ], g=[k], k=[kʰ] (aspiration distinction)
# ---------------------------------------------------------------------------
_INITIAL_TO_IPA: dict[str, str] = {
    "b": "p",
    "p": "pʰ",
    "m": "m",
    "f": "f",
    "d": "t",
    "t": "tʰ",
    "n": "n",
    "l": "l",
    "g": "k",
    "k": "kʰ",
    "h": "x",
    "j": "tɕ",
    "q": "tɕʰ",
    "x": "ɕ",
    "zh": "tʂ",
    "ch": "tʂʰ",
    "sh": "ʂ",
    "r": "ɻ",
    "z": "ts",
    "c": "tsʰ",
    "s": "s",
}

# ---------------------------------------------------------------------------
# Pinyin final → IPA mapping (compound finals as single tokens)
# ---------------------------------------------------------------------------
_FINAL_TO_IPA: dict[str, str] = {
    # Simple vowels
    "a": "a",
    "o": "o",
    "e": "ɤ",
    "i": "i",
    "u": "u",
    "\u00fc": "y",   # ü
    "v": "y",
    # Diphthongs
    "ai": "aɪ",
    "ei": "eɪ",
    "ao": "aʊ",
    "ou": "oʊ",
    # Nasal finals
    "an": "an",
    "en": "ən",
    "ang": "aŋ",
    "eng": "əŋ",
    "ong": "uŋ",
    # Retroflex final
    "er": "ɑɻ",
    # i- compound finals (齐齿呼)
    "ia": "ia",
    "ie": "iɛ",
    "iao": "iaʊ",
    "iu": "iou",
    "iou": "iou",
    "ian": "iɛn",
    "in": "in",
    "iang": "iaŋ",
    "ing": "iŋ",
    "iong": "iuŋ",
    # u- compound finals (合口呼)
    "ua": "ua",
    "uo": "uo",
    "uai": "uaɪ",
    "ui": "ueɪ",
    "uei": "ueɪ",
    "uan": "uan",
    "un": "uən",
    "uen": "uən",
    "uang": "uaŋ",
    "ueng": "uəŋ",
    # ü- compound finals (撮口呼)
    "\u00fce": "yɛ",   # üe
    "ve": "yɛ",
    "\u00fcan": "yan",  # üan
    "van": "yan",
    "\u00fcn": "yn",    # ün
    "vn": "yn",
    # Syllabic consonants (internal keys set by _split_pinyin)
    "-i_retroflex": "ɻ̩",
    "-i_alveolar": "ɨ",
}

# Ordered list of consonant initials (two-char first for prefix matching)
_INITIALS_ORDER = [
    "zh", "ch", "sh",
    "b", "p", "m", "f",
    "d", "t", "n", "l",
    "g", "k", "h",
    "j", "q", "x",
    "r", "z", "c", "s",
]

_RETROFLEX_INITIALS = frozenset(("zh", "ch", "sh", "r"))
_ALVEOLAR_INITIALS = frozenset(("z", "c", "s"))

_RE_CHINESE_CHAR = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _normalize_pinyin(py: str) -> str:
    """Normalize pinyin y/w conventions and v→ü to canonical form."""
    # v is an alternate representation of ü in some pypinyin output
    py = py.replace("v", "\u00fc")  # v → ü

    # y- initial: represents medial i or ü
    if py.startswith("yu"):
        return "\u00fc" + py[2:] if len(py) > 2 else "\u00fc"
    if py.startswith("y"):
        remainder = py[1:]
        if remainder.startswith("i"):
            return remainder  # yi→i, yin→in, ying→ing
        return "i" + remainder  # ya→ia, ye→ie, yan→ian, etc.

    # w- initial: represents medial u
    if py.startswith("w"):
        remainder = py[1:]
        if remainder.startswith("u"):
            return remainder  # wu→u
        return "u" + remainder  # wa→ua, wo→uo, wai→uai, etc.

    return py


def _split_pinyin(pinyin: str) -> tuple[str, str]:
    """Split normalized pinyin syllable into (initial, final)."""
    for init in _INITIALS_ORDER:
        if pinyin.startswith(init):
            final = pinyin[len(init):]

            # Syllabic consonant: bare "i" after retroflex or alveolar initials
            if final == "i":
                if init in _RETROFLEX_INITIALS:
                    return init, "-i_retroflex"
                if init in _ALVEOLAR_INITIALS:
                    return init, "-i_alveolar"

            # After j/q/x, u represents ü
            if init in ("j", "q", "x") and final.startswith("u"):
                final = "\u00fc" + final[1:]

            return init, final

    # No consonant initial
    return "", pinyin


def _pinyin_to_ipa(pinyin_syllable: str, tone: int) -> list[str]:
    """Convert a single pinyin syllable (without tone number) to IPA tokens.

    Returns a list of IPA tokens including tone marker.
    """
    initial, final = _split_pinyin(pinyin_syllable)

    tokens: list[str] = []

    # Initial consonant
    if initial:
        ipa = _INITIAL_TO_IPA.get(initial)
        if ipa:
            tokens.append(ipa)
        else:
            _LOGGER.debug("Unknown initial: %s", initial)

    # Final vowel(s) — as a single compound token
    if final:
        ipa = _FINAL_TO_IPA.get(final)
        if ipa:
            tokens.append(ipa)
        else:
            # Fallback: decompose unknown finals character by character
            for ch in final:
                if ch in _FINAL_TO_IPA:
                    tokens.append(_FINAL_TO_IPA[ch])
                elif ch.isalpha():
                    tokens.append(ch)
                    _LOGGER.debug(
                        "Unknown final char: %s (from %s)", ch, pinyin_syllable
                    )

    # Tone marker
    if 1 <= tone <= 5:
        tokens.append(f"tone{tone}")

    return tokens


def phonemize_chinese_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Chinese text to IPA phonemes with prosody information.

    Uses pypinyin for Hanzi→pinyin conversion, then converts to IPA.

    Prosody values:
    - a1: tone number (1-5)
    - a2: syllable position in word (1-based)
    - a3: word length in syllables

    Returns:
        (phonemes, prosody_list) where phonemes are PUA-mapped tokens.
    """
    try:
        from pypinyin import Style, pinyin  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning(
            "pypinyin not installed; Chinese phonemization unavailable. "
            "Install with: pip install pypinyin"
        )
        return [], []

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []

    # Get per-character pinyin for the entire text
    py_result = pinyin(text, style=Style.TONE3, neutral_tone_with_five=True)

    # Build word groups: contiguous Chinese character ranges for prosody
    word_info = _build_word_info(text)

    for char_idx, syllable_list in enumerate(py_result):
        ch = text[char_idx] if char_idx < len(text) else ""
        syllable = syllable_list[0]

        # Handle punctuation
        if ch in _ZH_PUNCT_MAP:
            phonemes.append(_ZH_PUNCT_MAP[ch])
            prosody_list.append(None)
            continue

        if ch in _PUNCTUATION:
            phonemes.append(ch)
            prosody_list.append(None)
            continue

        # Handle whitespace
        if ch.isspace():
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue

        # Handle non-Chinese characters (pass through)
        if not _RE_CHINESE_CHAR.match(ch):
            if ch.isalpha():
                phonemes.append(ch)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=1))
            continue

        # Chinese character: extract tone and convert to IPA
        tone = 5  # default neutral
        if syllable and syllable[-1].isdigit():
            tone = int(syllable[-1])
            syllable_base = syllable[:-1]
        else:
            syllable_base = syllable

        # Normalize pinyin conventions
        normalized = _normalize_pinyin(syllable_base)

        # Convert to IPA tokens
        ipa_tokens = _pinyin_to_ipa(normalized, tone)

        # Prosody: a1=tone, a2=position in word, a3=word length
        syl_pos, word_len = word_info.get(char_idx, (1, 1))
        syl_prosody = ProsodyInfo(a1=tone, a2=syl_pos, a3=word_len)

        for token in ipa_tokens:
            phonemes.append(token)
            prosody_list.append(syl_prosody)

    # Map multi-character tokens to PUA codepoints
    mapped = map_sequence(phonemes)
    return mapped, prosody_list


def _build_word_info(text: str) -> dict[int, tuple[int, int]]:
    """Build word position info for prosody from contiguous Chinese char groups.

    Returns a dict mapping character index → (syllable_position, word_length)
    where syllable_position is 1-based and word_length is the total number of
    Chinese characters in the contiguous group.
    """
    info: dict[int, tuple[int, int]] = {}
    group_start: int | None = None
    group_indices: list[int] = []

    for i, ch in enumerate(text):
        if _RE_CHINESE_CHAR.match(ch):
            if group_start is None:
                group_start = i
                group_indices = []
            group_indices.append(i)
        else:
            if group_start is not None:
                word_len = len(group_indices)
                for pos, idx in enumerate(group_indices):
                    info[idx] = (pos + 1, word_len)
                group_start = None
                group_indices = []

    # Handle trailing group
    if group_start is not None:
        word_len = len(group_indices)
        for pos, idx in enumerate(group_indices):
            info[idx] = (pos + 1, word_len)

    return info


def phonemize_chinese(text: str) -> list[str]:
    """Convert Chinese text to a list of IPA phoneme tokens."""
    phonemes, _ = phonemize_chinese_with_prosody(text)
    return phonemes


class ChinesePhonemizer(Phonemizer):
    """Chinese (Mandarin) phonemizer using pypinyin."""

    def phonemize(self, text: str) -> list[str]:
        return phonemize_chinese(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        return phonemize_chinese_with_prosody(text)

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        return None

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding."""
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
