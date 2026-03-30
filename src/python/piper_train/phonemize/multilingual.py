"""Multilingual phonemizer for code-switching text across N languages.

Generalizes BilingualPhonemizer to support arbitrary language combinations.
Detects language segments via Unicode ranges, delegates to language-specific
phonemizers, and returns unified phoneme IDs.
"""

import logging
import re

from .base import Phonemizer, ProsodyInfo
from .multilingual_id_map import get_multilingual_id_map
from .registry import get_phonemizer
from .token_mapper import TOKEN2CHAR


_LOGGER = logging.getLogger(__name__)


__all__ = ["MultilingualPhonemizer", "UnicodeLanguageDetector"]


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
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr", "sv")
        }

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

    return segments


class MultilingualPhonemizer(Phonemizer):
    """Phonemizer that handles code-switching between N languages.

    Segments the input text by language using Unicode ranges, delegates to
    language-specific phonemizers, and concatenates results in a unified
    phoneme space.

    Parameters
    ----------
    languages : list[str]
        Language codes to support, e.g. ["ja", "en", "zh", "ko"].
        Each must be registered in the phonemizer registry.
    default_latin_language : str
        Language code for Latin-script characters (default: "en").
    """

    def __init__(self, languages: list[str], default_latin_language: str = "en"):
        self._languages = languages

        # Validate that default_latin_language is one of the supported
        # languages.  If not (e.g. the caller passed "en" but languages is
        # ["ja", "zh"]), fall back to the first language so that
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
        self._id_map: dict[str, list[int]] | None = None
        # Note: _last_eos is set by phonemize_with_prosody and read by
        # post_process_ids. This is NOT thread-safe. For concurrent use,
        # callers must use a separate MultilingualPhonemizer per thread.
        self._last_eos: str = "$"

    @property
    def languages(self) -> list[str]:
        """Return the list of supported languages."""
        return self._languages

    def phonemize(self, text: str) -> list[str]:
        """Convert mixed-language text to a list of phoneme tokens."""
        phonemes, _ = self.phonemize_with_prosody(text)
        return phonemes

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """Convert mixed-language text to phoneme tokens with prosody.

        Each language segment is phonemized independently, then
        concatenated. BOS/EOS markers are NOT added here -- they are
        handled in post_process_ids.
        """
        segments = _segment_text_multilingual(text, self._detector)
        if not segments:
            return [], []

        all_phonemes: list[str] = []
        all_prosody: list[ProsodyInfo | None] = []
        last_eos = "$"

        # Build set of BOS/EOS tokens to strip (including PUA-mapped variants)
        # Japanese question markers ?!, ?., ?~ are PUA-encoded single chars
        _bos_eos_tokens = {"^", "$", "?"}
        for marker in ("?!", "?.", "?~"):
            if marker in TOKEN2CHAR:
                _bos_eos_tokens.add(TOKEN2CHAR[marker])
        # Also track which ones are EOS-like (for last_eos tracking)
        _eos_tokens = {"$", "?"}
        for marker in ("?!", "?.", "?~"):
            if marker in TOKEN2CHAR:
                _eos_tokens.add(TOKEN2CHAR[marker])

        for lang, segment_text in segments:
            phonemizer = get_phonemizer(lang)
            phonemes, prosody_list = phonemizer.phonemize_with_prosody(segment_text)

            # Strip BOS/EOS from individual segments
            # This includes PUA-encoded question markers from Japanese
            stripped_phonemes: list[str] = []
            stripped_prosody: list[ProsodyInfo | None] = []
            for ph, pr in zip(phonemes, prosody_list, strict=True):
                if ph in _bos_eos_tokens:
                    if ph in _eos_tokens:
                        last_eos = ph
                    continue
                stripped_phonemes.append(ph)
                stripped_prosody.append(pr)

            all_phonemes.extend(stripped_phonemes)
            all_prosody.extend(stripped_prosody)

        self._last_eos = last_eos
        return all_phonemes, all_prosody

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        """Return the unified multilingual phoneme ID map."""
        if self._id_map is None:
            self._id_map = get_multilingual_id_map(self._languages)
        return self._id_map

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """Add BOS/EOS and inter-phoneme padding (espeak-ng compatible).

        Delegates to the base class implementation, passing the dynamic EOS
        token captured during the most recent ``phonemize_with_prosody`` call.
        """
        return super().post_process_ids(
            phoneme_ids, prosody_features, phoneme_id_map, eos_token=self._last_eos
        )
