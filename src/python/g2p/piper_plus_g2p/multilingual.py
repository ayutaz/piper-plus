"""Multilingual phonemizer for code-switching text across N languages.

Generalizes single-language phonemizers to support arbitrary language
combinations. Detects language segments via Unicode ranges, delegates to
language-specific phonemizers, and returns unified phoneme tokens.
"""

import logging

from .base import Phonemizer, ProsodyInfo

_LOGGER = logging.getLogger(__name__)


__all__ = ["MultilingualPhonemizer", "UnicodeLanguageDetector"]


class UnicodeLanguageDetector:
    """Detect language from Unicode character ranges.

    Supports CJK disambiguation (JA vs ZH) by checking for kana presence.
    Latin characters are mapped to a configurable default language.

    Language detection uses ``ord()``-based range checks instead of compiled
    regular expressions for better per-character throughput.

    Parameters
    ----------
    languages : list[str]
        Language codes supported by this detector.
    default_latin_language : str
        Language code for Latin-script characters (default: "en").
    """

    def __init__(self, languages: list[str], default_latin_language: str = "en"):
        self.languages = set(languages)
        self.default_latin_language = default_latin_language

        # Determine which CJK detection to use based on available languages
        self._has_ja = "ja" in self.languages
        self._has_zh = "zh" in self.languages
        self._has_ko = "ko" in self.languages

        # Pre-compute the default latin return value (None when unsupported)
        self._default_latin: str | None = (
            default_latin_language if default_latin_language in self.languages else None
        )

        # Latin-script languages available (for disambiguation if needed)
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr")
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
        code = ord(ch)

        # Hiragana U+3040-309F, Katakana U+30A0-30FF, Katakana Phonetic U+31F0-31FF
        if 0x3040 <= code <= 0x31FF:
            # Skip Bopomofo (U+3100-U+312F) and Hangul Compat Jamo (U+3130-U+318F)
            # that fall within this range but are not kana.
            if code <= 0x30FF or code >= 0x31F0:
                return "ja" if self._has_ja else None
            # Hangul Compatibility Jamo: U+3130-318F
            if 0x3130 <= code <= 0x318F:
                return "ko" if self._has_ko else None
            return None

        # Hangul Jamo: U+1100-11FF
        if 0x1100 <= code <= 0x11FF:
            return "ko" if self._has_ko else None

        # CJK Extension A: U+3400-4DBF
        if 0x3400 <= code <= 0x4DBF:
            if self._has_ja and self._has_zh:
                return "ja" if context_has_kana else "zh"
            if self._has_ja:
                return "ja"
            if self._has_zh:
                return "zh"
            return None

        # CJK Unified Ideographs: U+4E00-9FFF
        if 0x4E00 <= code <= 0x9FFF:
            if self._has_ja and self._has_zh:
                return "ja" if context_has_kana else "zh"
            if self._has_ja:
                return "ja"
            if self._has_zh:
                return "zh"
            return None

        # Hangul Syllables: U+AC00-D7AF
        if 0xAC00 <= code <= 0xD7AF:
            return "ko" if self._has_ko else None

        # CJK Compatibility Ideographs: U+F900-FAFF
        if 0xF900 <= code <= 0xFAFF:
            if self._has_ja and self._has_zh:
                return "ja" if context_has_kana else "zh"
            if self._has_ja:
                return "ja"
            if self._has_zh:
                return "zh"
            return None

        # CJK Symbols and Punctuation: U+3000-303F (Japanese-specific punct)
        if 0x3000 <= code <= 0x303F:
            return "ja" if self._has_ja else None

        # Fullwidth forms: U+FF00-FFEF
        if 0xFF00 <= code <= 0xFFEF:
            # Fullwidth Latin uppercase U+FF21-FF3A, lowercase U+FF41-FF5A
            if (0xFF21 <= code <= 0xFF3A) or (0xFF41 <= code <= 0xFF5A):
                return self._default_latin
            # Remaining fullwidth forms -> Japanese punctuation/symbols
            # (digits U+FF00-FF20, brackets U+FF3B-FF40, braces U+FF5B-FFEF)
            return "ja" if self._has_ja else None

        # Basic Latin letters: A-Z (0x41-5A), a-z (0x61-7A)
        if (0x41 <= code <= 0x5A) or (0x61 <= code <= 0x7A):
            return self._default_latin

        # Extended Latin with diacritics:
        # U+00C0-00D6 (À-Ö), U+00D8-00F6 (Ø-ö), U+00F8-00FF (ø-ÿ)
        if (
            (0x00C0 <= code <= 0x00D6)
            or (0x00D8 <= code <= 0x00F6)
            or (0x00F8 <= code <= 0x00FF)
        ):
            return self._default_latin

        # Neutral: whitespace, digits, ASCII punctuation, etc.
        return None

    def has_kana(self, text: str) -> bool:
        """Check if text contains any kana characters."""
        for ch in text:
            code = ord(ch)
            # Hiragana U+3040-309F, Katakana U+30A0-30FF,
            # Katakana Phonetic Extensions U+31F0-31FF
            if (0x3040 <= code <= 0x30FF) or (0x31F0 <= code <= 0x31FF):
                return True
        return False


def _segment_text_multilingual(
    text: str,
    detector: UnicodeLanguageDetector,
    *,
    context_has_kana: bool | None = None,
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
    context_has_kana : bool | None
        Pre-computed result of ``detector.has_kana(text)``.  When ``None``
        (default) the scan is performed here.  Callers that already know
        the result can pass it to avoid a redundant full-text scan.

    Returns
    -------
    list[tuple[str, str]]
        List of (lang_code, text_segment) tuples.
    """
    if not text.strip():
        return []

    # Use pre-computed value or scan now
    if context_has_kana is None:
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

    @property
    def language_code(self) -> str:
        return "multilingual"

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
        the responsibility of ``piper_plus_g2p.encode.PiperEncoder``.
        """
        from .registry import get_phonemizer  # noqa: PLC0415

        # Pre-compute has_kana once and pass to _segment_text_multilingual
        # to avoid a redundant full-text scan inside the segmenter.
        context_has_kana = self._detector.has_kana(text)
        segments = _segment_text_multilingual(
            text, self._detector, context_has_kana=context_has_kana
        )
        if not segments:
            return [], []

        all_phonemes: list[str] = []
        all_prosody: list[ProsodyInfo | None] = []

        for lang, segment_text in segments:  # noqa: PLW2901
            phonemizer = get_phonemizer(lang)
            phonemes, prosody_list = phonemizer.phonemize_with_prosody(segment_text)

            all_phonemes.extend(phonemes)
            all_prosody.extend(prosody_list)

        return all_phonemes, all_prosody

    def segment_text(self, text: str) -> list[dict[str, str]]:
        """Segment mixed-language text into per-language chunks.

        Each segment contains contiguous characters of the same detected
        language. Neutral characters (whitespace, digits, punctuation)
        are absorbed into the preceding segment.

        Returns
        -------
        list[dict[str, str]]
            List of dicts with ``'language'`` and ``'text'`` keys.
        """
        segments = _segment_text_multilingual(text, self._detector)
        return [{"language": lang, "text": seg} for lang, seg in segments]
