"""Rule-based Hindi G2P (Devanagari + Latin Hinglish).

Converts Hindi text to IPA tokens from the Phase 0 inventory.
No external G2P engine (no espeak-ng). English words in Latin Hinglish
are delegated to :class:`EnglishPhonemizer`.

Known limitations
-----------------
* Informal Latin spelling merges dental त and retroflex ट as ``t`` → ``t̪``.
* Word-final Latin ``a`` is mapped to ``ɑ`` (आ), which matches ``aapka``
  but is an approximation for other spellings.
* ``the`` / ``to`` / ``main`` are in the Hindi LID lexicon because they are
  common romanizations of थे / तो / मैं; English uses of those spellings
  are therefore classified as Hindi when ``hi`` is in the language set.
"""

from __future__ import annotations

import functools
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "classify_latin_word",
    "split_latin_hinglish_runs",
    "phonemize_hindi",
    "phonemize_hindi_with_prosody",
    "HindiPhonemizer",
]

_SCHWA = "ə"
_HINGLISH_WORDS_PATH = Path(__file__).parent / "data" / "hi_hinglish_words.json"

_PUNCTUATION = set(",.;:!?।॥")
_STRIP_MARKS = ".,;:!?"

_RE_TOKEN = re.compile(
    r"([\u0900-\u0963\u0966-\u097F]+|[A-Za-z]+|[,.;:!?\u0964\u0965]+|\s+)",
    re.UNICODE,
)
_RE_LATIN_SPLIT = re.compile(r"([A-Za-z]+)|([^A-Za-z]+)")

# ZWJ / ZWNJ
_JOINERS = frozenset("\u200c\u200d")

# ---------------------------------------------------------------------------
# Devanagari tables
# ---------------------------------------------------------------------------

_INDEPENDENT_VOWELS: dict[str, list[str]] = {
    "अ": [_SCHWA],
    "आ": ["ɑ"],
    "इ": ["ɪ"],
    "ई": ["i"],
    "उ": ["ʊ"],
    "ऊ": ["u"],
    "ऋ": ["r", "ɪ"],
    "ॠ": ["r", "i"],
    "ऌ": ["l", "ɪ"],
    "ए": ["e"],
    "ऐ": ["ɛ"],
    "ओ": ["o"],
    "औ": ["ɔ"],
    "ॲ": ["ɛ"],
    "ऍ": ["ɛ"],
    "ऑ": ["ɔ"],
}

_MATRAS: dict[str, list[str]] = {
    "ा": ["ɑ"],
    "ि": ["ɪ"],
    "ी": ["i"],
    "ु": ["ʊ"],
    "ू": ["u"],
    "ृ": ["r", "ɪ"],
    "ॄ": ["r", "i"],
    "े": ["e"],
    "ै": ["ɛ"],
    "ो": ["o"],
    "ौ": ["ɔ"],
    "ॉ": ["ɔ"],
    "ॅ": ["ɛ"],
}

_CONSONANTS: dict[str, str] = {
    "क": "k",
    "ख": "kʰ",
    "ग": "g",
    "घ": "gʱ",
    "ङ": "ŋ",
    "च": "tʃ",
    "छ": "tʃʰ",
    "ज": "dʒ",
    "झ": "dʒʱ",
    "ञ": "ɲ",
    "ट": "ʈ",
    "ठ": "ʈʰ",
    "ड": "ɖ",
    "ढ": "ɖʱ",
    "ण": "ɳ",
    "त": "t̪",
    "थ": "t̪ʰ",
    "द": "d̪",
    "ध": "d̪ʱ",
    "न": "n",
    "प": "p",
    "फ": "pʰ",
    "ब": "b",
    "भ": "bʱ",
    "म": "m",
    "य": "j",
    "र": "r",
    "ल": "l",
    "ळ": "ɭ",
    "व": "ʋ",
    "श": "ʃ",
    "ष": "ʂ",
    "स": "s",
    "ह": "ɦ",
}

# Precomposed nukta letters (Unicode compatibility)
_NUKTA_PRECOMPOSED: dict[str, str] = {
    "क़": "q_uvular",
    "ख़": "x",
    "ग़": "ɣ",
    "ज़": "z",
    "ड़": "ɽ",
    "ढ़": "ɽʱ",
    "फ़": "f",
    "य़": "j",
}

_NUKTA_OVERRIDE: dict[str, str] = {
    "क": "q_uvular",
    "ख": "x",
    "ग": "ɣ",
    "ज": "z",
    "ड": "ɽ",
    "ढ": "ɽʱ",
    "फ": "f",
    "य": "j",
}

_VIRAMA = "्"
_NUKTA = "़"
_ANUSVARA = "ं"
_CANDRABINDU = "ँ"
_VISARGA = "ः"

_VELAR = frozenset({"k", "kʰ", "g", "gʱ", "ŋ", "q_uvular", "x", "ɣ"})
_PALATAL = frozenset({"tʃ", "tʃʰ", "dʒ", "dʒʱ", "ɲ"})
_RETROFLEX = frozenset({"ʈ", "ʈʰ", "ɖ", "ɖʱ", "ɳ", "ɽ", "ɽʱ", "ʂ", "ɭ"})
_DENTAL = frozenset({"t̪", "t̪ʰ", "d̪", "d̪ʱ", "n"})
_LABIAL = frozenset({"p", "pʰ", "b", "bʱ", "m"})

# ---------------------------------------------------------------------------
# Latin Hinglish romanization (longest match first)
# ---------------------------------------------------------------------------

_LATIN_MULTI: tuple[tuple[str, list[str]], ...] = (
    ("chh", ["tʃʰ"]),
    ("kh", ["kʰ"]),
    ("gh", ["gʱ"]),
    ("ch", ["tʃ"]),
    ("jh", ["dʒʱ"]),
    ("th", ["t̪ʰ"]),
    ("dh", ["d̪ʱ"]),
    ("ph", ["pʰ"]),
    ("bh", ["bʱ"]),
    ("sh", ["ʃ"]),
    ("ng", ["ŋ"]),
    ("ny", ["ɲ"]),
    ("aa", ["ɑ"]),
    ("ee", ["i"]),
    ("ii", ["i"]),
    ("oo", ["u"]),
    ("uu", ["u"]),
    ("ai", ["ɛ"]),
    ("au", ["ɔ"]),
    ("ei", ["e"]),
)

_LATIN_SINGLE: dict[str, list[str]] = {
    "a": [_SCHWA],
    "e": ["e"],
    "i": ["ɪ"],
    "o": ["o"],
    "u": ["ʊ"],
    "k": ["k"],
    "g": ["g"],
    "c": ["tʃ"],
    "j": ["dʒ"],
    "t": ["t̪"],
    "d": ["d̪"],
    "n": ["n"],
    "p": ["p"],
    "b": ["b"],
    "m": ["m"],
    "y": ["j"],
    "r": ["r"],
    "l": ["l"],
    "v": ["ʋ"],
    "w": ["ʋ"],
    "h": ["ɦ"],
    "s": ["s"],
    "z": ["z"],
    "f": ["f"],
    "q": ["q_uvular"],
    "x": ["k", "s"],
}


@dataclass
class _Syllable:
    onset: list[str] = field(default_factory=list)
    vowel: list[str] = field(default_factory=list)
    inherent: bool = False
    nasal: str | None = None  # homorganic nasal or ə̃
    visarga: bool = False


# ---------------------------------------------------------------------------
# Lexicon / LID
# ---------------------------------------------------------------------------


@functools.cache
def _load_hinglish_words() -> frozenset[str]:
    try:
        with open(_HINGLISH_WORDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _LOGGER.warning(
            "Hinglish lexicon unavailable at %s (%s); "
            "Latin LID will default unknown words to Hindi.",
            _HINGLISH_WORDS_PATH,
            exc,
        )
        return frozenset()
    words_raw = data.get("words", []) if isinstance(data, dict) else []
    return frozenset(
        w.lower().strip() for w in words_raw if isinstance(w, str) and w.strip()
    )


def _word_in_cmu(word: str) -> bool:
    try:
        from .english import _get_g2p  # noqa: PLC0415
    except ImportError:
        return False
    g2p = _get_g2p()
    if g2p is None:
        return False
    cmu = getattr(g2p, "cmu", None)
    if not isinstance(cmu, dict):
        return False
    return word.lower() in cmu


def classify_latin_word(word: str) -> str:
    """Return ``hi`` or ``en`` for a Latin-script word.

    Hindi lexicon wins. Else CMU English. Else Hindi (Hinglish default).
    """
    w = word.strip(_STRIP_MARKS).lower()
    if not w:
        return "hi"
    if w in _load_hinglish_words():
        return "hi"
    if _word_in_cmu(w):
        return "en"
    return "hi"


def split_latin_hinglish_runs(text: str) -> list[tuple[str, str]]:
    """Split a Latin-script string into adjacent ``(lang, chunk)`` runs.

    Non-letter spans (spaces, punctuation) stay attached to the preceding
    word. A leading separator is attached to the first word.
    """
    pieces = [p for p in _RE_LATIN_SPLIT.split(text) if p]
    if not pieces:
        return []

    tagged: list[tuple[str | None, str]] = []
    for part in pieces:
        if part.isalpha():
            tagged.append((classify_latin_word(part), part))
        else:
            tagged.append((None, part))

    # Attach separators to the previous word; leading ones to the next.
    merged: list[tuple[str, str]] = []
    pending = ""
    current_lang: str | None = None
    buf = ""
    for lang, part in tagged:
        if lang is None:
            if current_lang is None:
                pending += part
            else:
                buf += part
            continue
        if current_lang is None:
            current_lang = lang
            buf = pending + part
            pending = ""
            continue
        if lang == current_lang:
            buf += part
            continue
        merged.append((current_lang, buf))
        current_lang = lang
        buf = part
    if current_lang is not None:
        merged.append((current_lang, buf + pending))
    elif pending:
        merged.append(("hi", pending))
    return merged


# ---------------------------------------------------------------------------
# Normalize / Devanagari parse
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return "".join(ch for ch in text if ch not in _JOINERS)


def _is_consonant_char(ch: str) -> bool:
    return ch in _CONSONANTS or ch in _NUKTA_PRECOMPOSED


def _consonant_ipa(ch: str, nukta: bool) -> str:
    if ch in _NUKTA_PRECOMPOSED:
        return _NUKTA_PRECOMPOSED[ch]
    base = _CONSONANTS.get(ch)
    if base is None:
        return ch
    if nukta:
        return _NUKTA_OVERRIDE.get(ch, base)
    return base


def _homorganic_nasal(next_c: str | None) -> str:
    if next_c is None:
        return "ə̃"
    if next_c in _VELAR:
        return "ŋ"
    if next_c in _PALATAL:
        return "ɲ"
    if next_c in _RETROFLEX:
        return "ɳ"
    if next_c in _DENTAL:
        return "n"
    if next_c in _LABIAL:
        return "m"
    return "ə̃"


def _parse_devanagari_word(word: str) -> list[_Syllable]:
    """Parse one Devanagari word into syllables (akshara units)."""
    syllables: list[_Syllable] = []
    n = len(word)
    i = 0

    def _peek(offset: int = 0) -> str | None:
        j = i + offset
        return word[j] if j < n else None

    while i < n:
        ch = word[i]

        if ch in _INDEPENDENT_VOWELS:
            syl = _Syllable(vowel=list(_INDEPENDENT_VOWELS[ch]), inherent=False)
            i += 1
            i = _consume_coda_marks(word, i, syl)
            syllables.append(syl)
            continue

        if _is_consonant_char(ch):
            onset: list[str] = []
            while True:
                c = word[i]
                i += 1
                has_nukta = i < n and word[i] == _NUKTA
                if has_nukta:
                    i += 1
                onset.append(_consonant_ipa(c, has_nukta))
                if i < n and word[i] == _VIRAMA:
                    nxt = _peek(1)
                    if nxt is not None and _is_consonant_char(nxt):
                        i += 1  # skip virama, loop to consume next C
                        continue
                    i += 1
                    syl = _Syllable(onset=onset, vowel=[], inherent=False)
                    i = _consume_coda_marks(word, i, syl)
                    syllables.append(syl)
                    break
                if i < n and word[i] in _MATRAS:
                    syl = _Syllable(
                        onset=onset, vowel=list(_MATRAS[word[i]]), inherent=False
                    )
                    i += 1
                else:
                    syl = _Syllable(onset=onset, vowel=[_SCHWA], inherent=True)
                i = _consume_coda_marks(word, i, syl)
                syllables.append(syl)
                break
            continue

        i += 1

    _apply_anusvara_place(syllables)
    return syllables


def _consume_coda_marks(word: str, i: int, syl: _Syllable) -> int:
    n = len(word)
    while i < n:
        ch = word[i]
        if ch in (_ANUSVARA, _CANDRABINDU):
            syl.nasal = "ə̃"
            i += 1
            continue
        if ch == _VISARGA:
            syl.visarga = True
            i += 1
            continue
        break
    return i


def _apply_anusvara_place(syllables: list[_Syllable]) -> None:
    for i, syl in enumerate(syllables):
        if syl.nasal is None:
            continue
        next_c = None
        if i + 1 < len(syllables) and syllables[i + 1].onset:
            next_c = syllables[i + 1].onset[0]
        syl.nasal = _homorganic_nasal(next_c)


def _apply_schwa_deletion(syllables: list[_Syllable]) -> None:
    """Inherent-schwa deletion (keep first-syllable schwa).

    1. Drop word-final inherent schwa if the word has another nucleus.
    2. Drop a non-initial inherent schwa when the next syllable has an
       explicit (non-schwa) vowel. Onsets stay; only the vowel is removed.
    """
    if not syllables:
        return

    last = syllables[-1]
    if last.inherent and last.vowel == [_SCHWA]:
        other = any(s.vowel for s in syllables[:-1])
        if other:
            last.vowel = []
            last.inherent = False

    for i in range(1, len(syllables) - 1):
        syl = syllables[i]
        if not (syl.inherent and syl.vowel == [_SCHWA]):
            continue
        nxt = syllables[i + 1]
        if nxt.vowel and not nxt.inherent:
            syl.vowel = []
            syl.inherent = False

    if not any(s.vowel for s in syllables):
        first = syllables[0]
        if not first.vowel:
            first.vowel = [_SCHWA]
            first.inherent = True


def _flatten_syllables(syllables: list[_Syllable]) -> list[str]:
    phones: list[str] = []
    for syl in syllables:
        phones.extend(syl.onset)
        phones.extend(syl.vowel)
        if syl.nasal:
            phones.append(syl.nasal)
        if syl.visarga:
            phones.append("h")
    return phones


def _g2p_devanagari_word(word: str) -> list[str]:
    syllables = _parse_devanagari_word(word)
    _apply_schwa_deletion(syllables)
    return _flatten_syllables(syllables)


# ---------------------------------------------------------------------------
# Latin Hinglish G2P
# ---------------------------------------------------------------------------


def _g2p_latin_hindi_word(word: str) -> list[str]:
    w = word.lower()
    phones: list[str] = []
    i = 0
    n = len(w)
    while i < n:
        matched = False
        for seq, ipa in _LATIN_MULTI:
            if w.startswith(seq, i):
                phones.extend(ipa)
                i += len(seq)
                matched = True
                break
        if matched:
            continue
        ch = w[i]
        phones.extend(_LATIN_SINGLE.get(ch, []))
        i += 1

    if phones and phones[-1] == _SCHWA:
        phones[-1] = "ɑ"
    return phones


def _g2p_english_word(word: str) -> list[str]:
    from .english import phonemize_english  # noqa: PLC0415

    return [p for p in phonemize_english(word) if p != " "]


def _is_devanagari_word(token: str) -> bool:
    return any(0x0900 <= ord(ch) <= 0x097F for ch in token)


def _g2p_word(token: str) -> list[str]:
    if _is_devanagari_word(token):
        return _g2p_devanagari_word(token)
    if token.isascii() and token.isalpha():
        if classify_latin_word(token) == "en":
            return _g2p_english_word(token)
        return _g2p_latin_hindi_word(token)
    if all(c in _PUNCTUATION for c in token):
        return list(token)
    return []


def phonemize_hindi_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Hindi / Hinglish text to IPA tokens plus conservative prosody."""
    text = _normalize(text)
    tokens = _RE_TOKEN.findall(text)

    phonemes: list[str] = []
    prosody_list: list[ProsodyInfo | None] = []
    need_space = False

    for token in tokens:
        if token.isspace():
            if phonemes and phonemes[-1] != " ":
                phonemes.append(" ")
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            need_space = False
            continue

        if all(c in _PUNCTUATION for c in token):
            for c in token:
                phonemes.append(c)
                prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))
            continue

        if need_space:
            phonemes.append(" ")
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=0))

        word_phonemes = _g2p_word(token)
        count = len(word_phonemes)
        for ph in word_phonemes:
            phonemes.append(ph)
            prosody_list.append(ProsodyInfo(a1=0, a2=0, a3=count))

        need_space = True

    return phonemes, prosody_list


def phonemize_hindi(text: str) -> list[str]:
    """Convert Hindi / Hinglish text to IPA tokens."""
    phonemes, _ = phonemize_hindi_with_prosody(text)
    return phonemes


class HindiPhonemizer(Phonemizer):
    """Hindi phonemizer (Devanagari + Latin Hinglish)."""

    @property
    def language_code(self) -> str:
        return "hi"

    def phonemize(self, text: str) -> list[str]:
        text = self._sanitize_input(text)
        if not text:
            return []
        return phonemize_hindi(text)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        text = self._sanitize_input(text)
        if not text:
            return [], []
        return phonemize_hindi_with_prosody(text)
