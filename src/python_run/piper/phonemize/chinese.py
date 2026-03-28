"""Chinese (Mandarin) phonemizer using pypinyin for Piper TTS.

Runtime version for piper-plus inference.
Converts Chinese text to IPA phonemes via pinyin intermediate representation.
G2P logic is identical to the training side (piper_train.phonemize.chinese).
"""

import logging
import re

from .token_mapper import map_sequence


_LOGGER = logging.getLogger(__name__)

# Punctuation mapping (Chinese → Western equivalents)
_ZH_PUNCT_MAP: dict[str, str] = {
    "\u3002": ".",  # 。
    "\uff0c": ",",  # ，
    "\uff01": "!",  # ！
    "\uff1f": "?",  # ？
    "\u3001": ",",  # 、
    "\uff1b": ";",  # ；
    "\uff1a": ":",  # ：
    "\u2026": ".",  # … (ellipsis)
    "\u2014": ",",  # — (em-dash → pause)
    "\u201c": '"',  # " (left curly double quote)
    "\u201d": '"',  # " (right curly double quote)
    "\u2018": "'",  # ' (left curly single quote)
    "\u2019": "'",  # ' (right curly single quote)
}

_PUNCTUATION = set(
    ",.;:!?\u3002\uff0c\uff01\uff1f\u3001\uff1b\uff1a\u201c\u201d\u2018\u2019\u2026\u2014"
)

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
    "\u00fc": "y_vowel",  # ü → y_vowel (avoids collision with JA glide "y")
    "v": "y_vowel",
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
    "er": "ɚ",
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
    "\u00fce": "yɛ",  # üe
    "ve": "yɛ",
    "\u00fcan": "yɛn",  # üan
    "van": "yɛn",
    "\u00fcn": "yn",  # ün
    "vn": "yn",
    # Syllabic consonants (internal keys set by _split_pinyin)
    "-i_retroflex": "ɻ̩",
    "-i_alveolar": "ɨ",
}

# Ordered list of consonant initials (two-char first for prefix matching)
_INITIALS_ORDER = [
    "zh",
    "ch",
    "sh",
    "b",
    "p",
    "m",
    "f",
    "d",
    "t",
    "n",
    "l",
    "g",
    "k",
    "h",
    "j",
    "q",
    "x",
    "r",
    "z",
    "c",
    "s",
]

_RETROFLEX_INITIALS = frozenset(("zh", "ch", "sh", "r"))
_ALVEOLAR_INITIALS = frozenset(("z", "c", "s"))

_RE_CHINESE_CHAR = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _apply_tone_sandhi(
    py_tones: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Apply basic Mandarin tone sandhi rules.

    Rules applied in order:
      1. T3 + T3 → T2 + T3 (third tone sandhi: 你好 nǐhǎo → níhǎo)
      2. 一 (yi T1) before T4 → T2  (一定 yī dìng → yí dìng)
      3. 一 (yi T1) before T1/T2/T3 → T4  (一般 yī bān → yì bān)
      4. 不 (bu T4) before T4 → T2  (不对 bù duì → bú duì)
    """
    result = list(py_tones)
    for i in range(len(result) - 1):
        syllable_i, tone_i = result[i]
        _, tone_next = result[i + 1]
        # Rule 1: third tone sandhi
        if tone_i == 3 and tone_next == 3:
            result[i] = (syllable_i, 2)
            continue
        # Rule 2 & 3: 一 tone sandhi
        # Note: _normalize_pinyin("yi") → "i", so we match normalized form
        if syllable_i == "i" and tone_i == 1:
            if tone_next == 4:
                result[i] = (syllable_i, 2)  # T1 → T2 before T4
            elif tone_next in (1, 2, 3):
                result[i] = (syllable_i, 4)  # T1 → T4 before T1/T2/T3
            continue
        # Rule 4: 不 tone sandhi (identified by pinyin "bu" + tone 4)
        if syllable_i == "bu" and tone_i == 4 and tone_next == 4:
            result[i] = (syllable_i, 2)  # T4 → T2 before T4
    return result


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
            final = pinyin[len(init) :]

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
        elif group_start is not None:
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


def _phonemize_chinese_raw(text: str) -> list[str]:
    """Convert Chinese text to raw IPA phonemes (without BOS/EOS).

    Uses pypinyin for Hanzi→pinyin conversion, then converts to IPA.
    Returns PUA-mapped tokens (before BOS/EOS wrapping).
    """
    try:
        from pypinyin import Style, pinyin  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "pypinyin is required for Chinese phonemization. "
            "Install with: pip install pypinyin"
        ) from None

    phonemes: list[str] = []

    # Get per-character pinyin for the entire text
    py_result = pinyin(text, style=Style.TONE3, neutral_tone_with_five=True)

    # Build word groups: contiguous Chinese character ranges for prosody
    _build_word_info(text)

    # --- Build per-character pinyin lookup ---
    # pypinyin groups consecutive non-Chinese characters into single entries,
    # so len(py_result) can be less than len(text). We build a mapping from
    # text character index to pinyin syllable for Chinese characters only.
    char_pinyin: dict[int, str] = {}
    text_pos = 0
    for syllable_list in py_result:
        syllable = syllable_list[0]
        if text_pos < len(text) and _RE_CHINESE_CHAR.match(text[text_pos]):
            # Chinese char: 1:1 mapping
            char_pinyin[text_pos] = syllable
            text_pos += 1
        else:
            # Non-Chinese group: pypinyin merges consecutive non-Chinese chars
            # into one entry. Skip past all non-Chinese chars in the text.
            while text_pos < len(text) and not _RE_CHINESE_CHAR.match(text[text_pos]):
                text_pos += 1

    # --- First pass: extract tones for Chinese characters ---
    # Collect (normalized_pinyin, tone) per text char_idx for tone sandhi
    char_tones: dict[int, tuple[str, int]] = {}
    chinese_indices: list[int] = []
    for char_idx, syllable in char_pinyin.items():
        tone = 5  # default neutral
        if syllable and syllable[-1].isdigit():
            tone = int(syllable[-1])
            syllable_base = syllable[:-1]
        else:
            syllable_base = syllable
        normalized = _normalize_pinyin(syllable_base)
        char_tones[char_idx] = (normalized, tone)
        chinese_indices.append(char_idx)

    # Apply tone sandhi to consecutive Chinese character sequences
    if chinese_indices:
        # Group consecutive Chinese character indices
        groups: list[list[int]] = []
        current_group: list[int] = [chinese_indices[0]]
        for k in range(1, len(chinese_indices)):
            if chinese_indices[k] == chinese_indices[k - 1] + 1:
                current_group.append(chinese_indices[k])
            else:
                groups.append(current_group)
                current_group = [chinese_indices[k]]
        groups.append(current_group)

        for group in groups:
            py_tones = [char_tones[idx] for idx in group]
            sandhi_result = _apply_tone_sandhi(py_tones)
            for idx, (norm, tone) in zip(group, sandhi_result, strict=False):
                char_tones[idx] = (norm, tone)

    # --- Second pass: generate phonemes ---
    # Iterate through the original text character by character (not pypinyin
    # results) to avoid index misalignment when non-Chinese characters are
    # grouped by pypinyin.
    for char_idx, ch in enumerate(text):
        # Handle punctuation
        if ch in _ZH_PUNCT_MAP:
            phonemes.append(_ZH_PUNCT_MAP[ch])
            continue

        if ch in _PUNCTUATION:
            phonemes.append(ch)
            continue

        # Handle whitespace
        if ch.isspace():
            phonemes.append(" ")
            continue

        # Handle digits (pass through as-is)
        if ch.isdigit():
            phonemes.append(ch)
            continue

        # Handle non-Chinese characters (pass through)
        if not _RE_CHINESE_CHAR.match(ch):
            if ch.isalpha():
                phonemes.append(ch)
            continue

        # Chinese character: use tone-sandhi-corrected data
        normalized, tone = char_tones[char_idx]

        # Erhua (儿化音): if the normalized pinyin ends with "r" but is not
        # the standalone "er" syllable, strip the trailing "r", convert the
        # base syllable, then append ɚ for the r-coloring.
        erhua_token: str | None = None
        if normalized.endswith("r") and len(normalized) > 1 and normalized != "er":
            erhua_token = "ɚ"
            normalized = normalized[:-1]

        # Convert to IPA tokens
        ipa_tokens = _pinyin_to_ipa(normalized, tone)
        if erhua_token is not None:
            # Insert ɚ after the vowel tokens but before the tone marker
            tone_marker = (
                ipa_tokens[-1]
                if ipa_tokens and ipa_tokens[-1].startswith("tone")
                else None
            )
            if tone_marker is not None:
                ipa_tokens = ipa_tokens[:-1] + [erhua_token] + [tone_marker]
            else:
                ipa_tokens.append(erhua_token)

        for token in ipa_tokens:
            phonemes.append(token)

    # Map multi-character tokens to PUA codepoints
    return map_sequence(phonemes)


def phonemize_chinese(text: str) -> list[str]:
    """Phonemize Chinese text. Returns tokens after map_sequence."""
    phonemes = _phonemize_chinese_raw(text)
    tokens = ["^"] + phonemes + ["$"]
    return map_sequence(tokens)
