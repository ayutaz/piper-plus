"""Multilingual phonemizer for code-switching text across N languages.

Generalizes BilingualPhonemizer to support arbitrary language combinations.
Detects language segments via Unicode ranges, delegates to language-specific
phonemizers, and returns unified phoneme tokens.
"""

import functools
import json
import logging
import re
from pathlib import Path

from .token_mapper import TOKEN2CHAR, map_sequence


_LOGGER = logging.getLogger(__name__)


__all__ = ["MultilingualPhonemizer", "UnicodeLanguageDetector"]

# ---------------------------------------------------------------------------
# Swedish per-word LID support (Issue #539)
# ---------------------------------------------------------------------------
# The char-level detector maps å/ä/ö to ``default_latin_language`` (shared with
# other Latin scripts). A conservative word-level post-pass then re-classifies
# default-Latin segments to Swedish when a STRONG indicator is present:
# the å/Å character, or an exact match in the Swedish function-word set.
# Weak chars ä/ö alone are NOT sufficient (shared with German/Finnish/loanwords).
#
# This mirrors the canonical g2p implementation
# (``src/python/g2p/piper_plus_g2p/multilingual.py``); the bundled JSON below is
# a byte-for-byte copy of ``src/python/g2p/piper_plus_g2p/data/sv_function_words.json``
# (a sync gate enforces this).
_SV_FUNCTION_WORDS_DATA_PATH = Path(__file__).parent / "data" / "sv_function_words.json"


@functools.cache
def _load_sv_function_words() -> tuple[frozenset[str], frozenset[str]]:
    """Load the bundled Swedish function-word + strong-char data (cached).

    Returns ``(function_words, strong_chars)`` as frozensets: function words
    are lowercased; strong chars are kept as-is (see below). The loader is
    forward-compatible: unknown top-level keys (e.g. a future
    ``schema_version`` bump or added sections) are ignored.

    This is called at module import time. Missing *or* malformed data
    (FileNotFoundError / other OSError / JSON parse error) degrades
    gracefully to empty sets — warned via ``_LOGGER`` — so the per-word
    post-pass simply becomes a no-op rather than bricking the import.

    Case-folding: callers lowercase each word before matching, so the
    uppercase ``Å`` entry in ``strong_chars`` is a *defensive* convention
    shared with the C#/Go/C++ runtimes (which store the uppercase form too).
    It is intentional, not dead data — do not drop it or switch the strong
    check to case-sensitive.

    Note: ``sv_function_words.json`` is the LID-discriminative word list
    (used only for language detection, and deliberately excludes
    cross-language-ambiguous words like i/en/av/de/du). It is intentionally
    DISTINCT from the prosody/stress ``FUNCTION_WORDS`` list maintained in the
    Swedish phonemizer; do not try to sync the two.
    """
    try:
        with open(_SV_FUNCTION_WORDS_DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        # OSError covers FileNotFoundError (missing bundle) and other I/O
        # failures; json.JSONDecodeError covers a corrupt/truncated file.
        _LOGGER.warning(
            "Swedish function-word data unavailable at %s (%s); "
            "per-word Swedish LID will be disabled.",
            _SV_FUNCTION_WORDS_DATA_PATH,
            exc,
        )
        return frozenset(), frozenset()

    words_raw = data.get("function_words", []) if isinstance(data, dict) else []
    chars_raw = data.get("strong_chars", []) if isinstance(data, dict) else []

    function_words = frozenset(w.lower() for w in words_raw if isinstance(w, str) and w)
    strong_chars = frozenset(c for c in chars_raw if isinstance(c, str) and c)
    return function_words, strong_chars


_SV_FUNCTION_WORDS, _SV_STRONG_CHARS = _load_sv_function_words()


class UnicodeLanguageDetector:
    """Detect language from Unicode character ranges.

    Supports CJK disambiguation (JA vs ZH) by checking for kana presence.
    Latin characters are mapped to a configurable default language.

    Parameters
    ----------
    languages : list[str]
        Language codes supported by this detector.
    default_latin_language : str
        Language code for Latin-script characters (default: "en").
    """

    # Hiragana: U+3040-309F, Katakana: U+30A0-30FF, Katakana Phonetic: U+31F0-31FF
    _RE_KANA = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF]")

    # CJK Unified Ideographs: U+4E00-9FFF, Extension A: U+3400-4DBF
    # CJK Compatibility: U+F900-FAFF
    _RE_CJK = re.compile(r"[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]")

    # Japanese-specific: CJK punctuation (。、「」etc) + fullwidth forms
    # Excludes fullwidth Latin letters (U+FF21-FF3A, U+FF41-FF5A) which are
    # handled separately as Latin characters.
    _RE_JA_PUNCT = re.compile(
        r"[\u3000-\u303F"
        r"\uFF00-\uFF20"  # Fullwidth digits and symbols (！＂...＠)
        r"\uFF3B-\uFF40"  # Fullwidth brackets and symbols (［＼...｀)
        r"\uFF5B-\uFFEF"  # Fullwidth braces onwards (｛｜...halfwidth/fullwidth forms)
        r"]"
    )

    # Fullwidth Latin letters: U+FF21-FF3A (Ａ-Ｚ), U+FF41-FF5A (ａ-ｚ)
    _RE_FULLWIDTH_LATIN = re.compile(r"[\uFF21-\uFF3A\uFF41-\uFF5A]")

    # Hangul Syllables: U+AC00-D7AF, Jamo: U+1100-11FF, Compat Jamo: U+3130-318F
    _RE_HANGUL = re.compile(r"[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]")

    # Basic Latin letters (including extended Latin with diacritics)
    # Excludes × (U+00D7) and ÷ (U+00F7) which are in the À-ÿ range
    _RE_LATIN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")

    def __init__(self, languages: list[str], default_latin_language: str = "en"):
        self.languages = set(languages)
        self.default_latin_language = default_latin_language

        # Determine which CJK detection to use based on available languages
        self._has_ja = "ja" in self.languages
        self._has_zh = "zh" in self.languages
        self._has_ko = "ko" in self.languages

        # Latin-script languages available (for disambiguation if needed)
        self._has_sv = "sv" in self.languages
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr", "sv")
        }
        # Conservative gate for the Swedish per-word post-pass (Issue #539):
        # only when Swedish is requested alongside >=2 Latin-script languages
        # (i.e. genuine code-switching context, not a Swedish-only model).
        self._detect_swedish = self._has_sv and len(self._latin_languages) >= 2

    def detect_char(self, ch: str, context_has_kana: bool = False) -> str | None:  # noqa: PLR0911
        """Detect language for a single character.

        Parameters
        ----------
        ch : str
            Single character to classify.
        context_has_kana : bool
            Whether the surrounding text contains kana (for CJK disambiguation).

        Returns
        -------
        str | None
            Language code, or None for neutral characters (whitespace, digits, etc.).
        """
        # Kana → always Japanese
        if self._RE_KANA.match(ch):
            return "ja" if self._has_ja else None

        # Hangul → Korean
        if self._RE_HANGUL.match(ch):
            return "ko" if self._has_ko else None

        # CJK ideographs → JA or ZH depending on context
        if self._RE_CJK.match(ch):
            if self._has_ja and self._has_zh:
                # Disambiguate: if context has kana, it's Japanese
                return "ja" if context_has_kana else "zh"
            if self._has_ja:
                return "ja"
            if self._has_zh:
                return "zh"
            return None

        # Fullwidth Latin letters (Ａ-Ｚ, ａ-ｚ) → treat as Latin, not Japanese
        if self._RE_FULLWIDTH_LATIN.match(ch):
            if self.default_latin_language in self.languages:
                return self.default_latin_language
            return None

        # Japanese-specific punctuation (CJK punct + fullwidth forms,
        # excluding fullwidth Latin already handled above)
        if self._RE_JA_PUNCT.match(ch):
            if self._has_ja:
                return "ja"
            return None

        # Latin characters
        if self._RE_LATIN.match(ch):
            if self.default_latin_language in self.languages:
                return self.default_latin_language
            return None

        # Neutral: whitespace, digits, punctuation
        return None

    def has_kana(self, text: str) -> bool:
        """Check if text contains any kana characters."""
        return bool(self._RE_KANA.search(text))


def _segment_text_multilingual(
    text: str, detector: UnicodeLanguageDetector
) -> list[tuple[str, str]]:
    """Split text into (language, segment) pairs using Unicode detection.

    Neutral characters (whitespace, digits, punctuation) are absorbed into
    the preceding segment.

    Parameters
    ----------
    text : str
        Input text to segment.
    detector : UnicodeLanguageDetector
        Language detector instance.

    Returns
    -------
    list[tuple[str, str]]
        List of (lang_code, text_segment) tuples.
    """
    if not text.strip():
        return []

    # Pre-scan for kana to help CJK disambiguation
    context_has_kana = detector.has_kana(text)

    segments: list[tuple[str, str]] = []
    current_lang: str | None = None
    current_chars: list[str] = []

    for ch in text:
        lang = detector.detect_char(ch, context_has_kana=context_has_kana)

        if lang is not None and lang != current_lang and current_lang is not None:
            segments.append((current_lang, "".join(current_chars)))
            current_chars = []

        if lang is not None:
            current_lang = lang
        current_chars.append(ch)

    if current_chars and current_lang is not None:
        segments.append((current_lang, "".join(current_chars)))

    # If no language-specific characters were detected (e.g., text is only
    # numbers, URLs, or punctuation), fall back to the default language so
    # the text is processed rather than silently dropped.
    if not segments and text.strip():
        default_lang = detector.default_latin_language
        _LOGGER.debug(
            "No language-specific characters detected in %r; "
            "falling back to default language '%s'.",
            text,
            default_lang,
        )
        segments = [(default_lang, text)]

    # Conservative Swedish per-word post-pass (Issue #539): re-classify
    # default-Latin segments containing a strong Swedish indicator to "sv".
    if detector._detect_swedish:
        segments = _refine_latin_segments_for_swedish(segments, detector)

    return segments


def _refine_latin_segments_for_swedish(
    segments: list[tuple[str, str]],
    detector: "UnicodeLanguageDetector",
) -> list[tuple[str, str]]:
    """Re-classify default-Latin segments as Swedish (conservative).

    Strong indicators (sufficient): å/Å, or an exact function-word match.
    Weak chars ä/ö are NOT sufficient alone (shared with German etc.).
    """
    default = detector.default_latin_language
    if default == "sv":
        return segments

    result: list[tuple[str, str]] = []
    for lang, text in segments:
        if lang != default:
            result.append((lang, text))
            continue
        strong = False
        for word in text.split():
            # The 5-mark strip set (. , ; : !  ?) is PINNED: all runtimes
            # (C++/C#/Go) strip exactly these ASCII marks, and byte-identical
            # tokenization across runtimes is required for parity. Do not
            # broaden it (no Unicode punctuation, no smart quotes, etc.).
            w = word.strip(".,;:!?").lower()
            if not w:
                continue
            if w in _SV_FUNCTION_WORDS:
                strong = True
                break
            # ``w`` is already lowercased here, so the å/Å strong-char set
            # only needs the lowercase form to match; the uppercase ``Å``
            # entry is kept for cross-runtime parity (see loader docstring).
            if any(c in _SV_STRONG_CHARS for c in w):
                strong = True
                break
        result.append(("sv", text) if strong else (default, text))
    return result


# ---------------------------------------------------------------------------
# Per-language phonemizer dispatch
# ---------------------------------------------------------------------------

_PHONEMIZE_FUNCS: dict[str, object] = {}


def _get_phonemize_func(lang: str):
    """Lazy-import and cache the per-language phonemize function."""
    if lang in _PHONEMIZE_FUNCS:
        return _PHONEMIZE_FUNCS[lang]

    if lang == "ja":
        from .japanese import phonemize_japanese  # noqa: PLC0415

        func = phonemize_japanese
    elif lang == "en":
        from .english import phonemize_english  # noqa: PLC0415

        func = phonemize_english
    elif lang == "zh":
        from .chinese import phonemize_chinese  # noqa: PLC0415

        func = phonemize_chinese
    elif lang == "es":
        from .spanish import phonemize_spanish  # noqa: PLC0415

        func = phonemize_spanish
    elif lang == "fr":
        from .french import phonemize_french  # noqa: PLC0415

        func = phonemize_french
    elif lang == "pt":
        from .portuguese import phonemize_portuguese  # noqa: PLC0415

        func = phonemize_portuguese
    elif lang == "pt-PT":
        from .portuguese import phonemize_european_portuguese  # noqa: PLC0415

        func = phonemize_european_portuguese
    else:
        raise ValueError(f"Unsupported language: {lang}")

    _PHONEMIZE_FUNCS[lang] = func
    return func


def _get_zh_embedded_english_func():
    """Lazy-import the embedded-English-in-Chinese phonemize function."""
    if "_zh_embedded_en" in _PHONEMIZE_FUNCS:
        return _PHONEMIZE_FUNCS["_zh_embedded_en"]
    from .chinese import phonemize_embedded_english  # noqa: PLC0415

    _PHONEMIZE_FUNCS["_zh_embedded_en"] = phonemize_embedded_english
    return phonemize_embedded_english


class MultilingualPhonemizer:
    """Phonemizer that handles code-switching between N languages.

    Segments the input text by language using Unicode ranges, delegates to
    language-specific phonemizers, and concatenates results in a unified
    phoneme space.

    Parameters
    ----------
    languages : list[str]
        Language codes to support, e.g. ["ja", "en", "zh"].
        Each must have a corresponding ``phonemize_<lang>`` function.
    default_latin_language : str
        Language code for Latin-script characters (default: "en").
    """

    def __init__(self, languages: list[str], default_latin_language: str = "en"):
        self._languages = languages

        # Validate that default_latin_language is one of the supported
        # languages.  If not, fall back to the first language so that
        # _segment_text_multilingual never produces segments with an
        # unsupported language code.
        if default_latin_language not in languages:
            _LOGGER.warning(
                "default_latin_language '%s' is not in supported languages %s; "
                "falling back to '%s'.",
                default_latin_language,
                languages,
                languages[0],
            )
            default_latin_language = languages[0]

        self._default_latin_language = default_latin_language
        self._detector = UnicodeLanguageDetector(
            languages, default_latin_language=default_latin_language
        )

    @property
    def languages(self) -> list[str]:
        """Return the list of supported languages."""
        return self._languages

    def phonemize(self, text: str) -> list[str]:
        """Phonemize mixed-language text. Returns tokens after map_sequence.

        Special case: an English segment adjacent to a Chinese segment
        (``[zh, en]``, ``[en, zh]``, or ``[zh, en, zh]``) is dispatched
        to the embedded-English-as-pinyin path so the English token is
        rendered in Mandarin pinyin instead of US English.
        """
        segments = _segment_text_multilingual(text, self._detector)
        if not segments:
            return []

        # Build set of BOS/EOS tokens to strip (including PUA-mapped variants)
        # Japanese question markers ?!, ?., ?~ are PUA-encoded single chars
        _bos_eos_tokens = {"^", "$", "?"}
        for marker in ("?!", "?.", "?~"):
            if marker in TOKEN2CHAR:
                _bos_eos_tokens.add(TOKEN2CHAR[marker])

        has_zh = "zh" in self._languages

        all_tokens: list[str] = []

        for i, (lang, segment_text) in enumerate(segments):
            func = _get_phonemize_func(lang)

            if has_zh and lang == "en":
                prev_is_zh = i > 0 and segments[i - 1][0] == "zh"
                next_is_zh = i + 1 < len(segments) and segments[i + 1][0] == "zh"
                if prev_is_zh or next_is_zh:
                    func = _get_zh_embedded_english_func()

            tokens = func(segment_text)

            # Strip BOS/EOS from individual segments
            # This includes PUA-encoded question markers from Japanese
            for tok in tokens:
                if tok in _bos_eos_tokens:
                    continue
                all_tokens.append(tok)

        # Do NOT add BOS/EOS here — voice.py's phonemes_to_ids() adds them.
        # This matches the training-side MultilingualPhonemizer behavior.
        return map_sequence(all_tokens)
