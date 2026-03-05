"""Bilingual phonemizer for code-switching text (e.g. JA+EN mixed).

Backward-compatible wrapper around MultilingualPhonemizer.
Detects language segments via Unicode ranges, delegates to the
appropriate language-specific phonemizer, and returns unified phoneme IDs.
"""

from .bilingual_id_map import get_bilingual_id_map
from .multilingual import MultilingualPhonemizer, _segment_text_multilingual


__all__ = ["BilingualPhonemizer"]


def _segment_text(text: str) -> list[tuple[str, str]]:
    """Split text into (language, segment) pairs.

    Backward-compatible wrapper around _segment_text_multilingual.
    Uses a simple heuristic: characters in CJK/Hiragana/Katakana ranges
    are tagged as "ja", ASCII Latin characters as "en". Whitespace and
    punctuation are absorbed into the preceding segment.

    Returns:
        List of (lang, text) tuples, e.g.:
        [("ja", "今日は"), ("en", "good morning"), ("ja", "ですね")]
    """
    from .multilingual import UnicodeLanguageDetector  # noqa: PLC0415

    detector = UnicodeLanguageDetector(["ja", "en"], default_latin_language="en")
    return _segment_text_multilingual(text, detector)


class BilingualPhonemizer(MultilingualPhonemizer):
    """Phonemizer that handles code-switching between two languages.

    Backward-compatible subclass of MultilingualPhonemizer.
    Defaults to JA+EN bilingual mode.

    Parameters
    ----------
    languages : list[str]
        Language codes to support, e.g. ["ja", "en"].
        Each must be registered in the phonemizer registry.
    """

    def __init__(self, languages: list[str]):
        super().__init__(languages, default_latin_language="en")

    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        """Return the unified bilingual phoneme ID map.

        For backward compatibility, uses get_bilingual_id_map() when
        languages are exactly ["ja", "en"].
        """
        if self._id_map is None:
            if set(self._languages) == {"ja", "en"}:
                self._id_map = get_bilingual_id_map()
            else:
                from .multilingual_id_map import get_multilingual_id_map  # noqa: PLC0415

                self._id_map = get_multilingual_id_map(self._languages)
        return self._id_map
