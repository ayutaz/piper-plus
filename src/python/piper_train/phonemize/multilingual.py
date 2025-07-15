#!/usr/bin/env python3
"""Multilingual phonemizer that combines Japanese (OpenJTalk) and other languages (espeak-ng)."""

import logging
from dataclasses import dataclass
from enum import Enum

# Language-specific phonemizers
try:
    from .japanese import phonemize_japanese
    from .multilingual_phoneme_map import get_multilingual_phoneme_mapper
    pass  # token_mapper import removed - unused
except ImportError:
    from piper_train.phonemize.japanese import phonemize_japanese
    from piper_train.phonemize.multilingual_phoneme_map import (
        get_multilingual_phoneme_mapper,
    )

from piper_phonemize import phonemize_espeak

_LOGGER = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported languages."""
    JAPANESE = "ja"
    ENGLISH = "en"
    CHINESE = "zh"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    KOREAN = "ko"


@dataclass
class TextSegment:
    """A segment of text with its detected language."""
    text: str
    language: Language
    start_idx: int
    end_idx: int


@dataclass
class PhonemeSegment:
    """Phonemes for a text segment."""
    phonemes: list[str]
    language: Language
    text: str


class LanguageDetector:
    """Simple rule-based language detector for mixed text."""

    # Unicode ranges for different scripts
    SCRIPT_RANGES = {
        Language.JAPANESE: [
            (0x3040, 0x309F),  # Hiragana
            (0x30A0, 0x30FF),  # Katakana
            (0x4E00, 0x9FFF),  # CJK Unified Ideographs (Kanji)
        ],
        Language.CHINESE: [
            (0x4E00, 0x9FFF),  # CJK Unified Ideographs
        ],
        Language.KOREAN: [
            (0xAC00, 0xD7AF),  # Hangul Syllables
            (0x1100, 0x11FF),  # Hangul Jamo
        ],
    }

    def detect_language(self, text: str) -> Language:
        """Detect the primary language of a text segment."""
        # Count characters by script
        script_counts = {lang: 0 for lang in Language}

        for char in text:
            code_point = ord(char)

            # Check Japanese (prioritize over Chinese for shared characters)
            if self._is_in_ranges(code_point, self.SCRIPT_RANGES.get(Language.JAPANESE, [])):
                # Check if it's specifically Hiragana or Katakana
                if 0x3040 <= code_point <= 0x30FF:
                    script_counts[Language.JAPANESE] += 2  # Weight kana higher
                else:
                    script_counts[Language.JAPANESE] += 1

            # Check Korean
            elif self._is_in_ranges(code_point, self.SCRIPT_RANGES.get(Language.KOREAN, [])):
                script_counts[Language.KOREAN] += 1

            # Check if it's Latin script (could be multiple languages)
            elif 0x0041 <= code_point <= 0x007A or 0x00C0 <= code_point <= 0x00FF:
                # Default to English for now (can be improved with better detection)
                script_counts[Language.ENGLISH] += 1

        # Return language with highest count
        if script_counts[Language.JAPANESE] > 0:
            return Language.JAPANESE
        elif script_counts[Language.KOREAN] > 0:
            return Language.KOREAN
        elif script_counts[Language.ENGLISH] > 0:
            return Language.ENGLISH
        else:
            # Default to English
            return Language.ENGLISH

    def _is_in_ranges(self, code_point: int, ranges: list[tuple[int, int]]) -> bool:
        """Check if a code point is in any of the given ranges."""
        for start, end in ranges:
            if start <= code_point <= end:
                return True
        return False

    def split_mixed_text(self, text: str) -> list[TextSegment]:
        """Split mixed-language text into segments."""
        segments = []
        current_segment = ""
        current_language = None
        start_idx = 0

        for i, char in enumerate(text):
            # Skip whitespace and punctuation for language detection
            if char.isspace() or char in ".,!?;:\"'()[]{}。、！？；：「」『』（）":
                if current_segment:
                    current_segment += char
                continue

            char_language = self.detect_language(char)

            if current_language is None:
                current_language = char_language
                current_segment = char
            elif char_language == current_language:
                current_segment += char
            else:
                # Language changed, save current segment
                if current_segment.strip():
                    segments.append(TextSegment(
                        text=current_segment,
                        language=current_language,
                        start_idx=start_idx,
                        end_idx=i
                    ))

                # Start new segment
                current_segment = char
                current_language = char_language
                start_idx = i

        # Add final segment
        if current_segment.strip():
            segments.append(TextSegment(
                text=current_segment,
                language=current_language,
                start_idx=start_idx,
                end_idx=len(text)
            ))

        return segments


class MultilingualPhonemizer:
    """Phonemizer that handles multiple languages in a single text."""

    def __init__(self):
        self.language_detector = LanguageDetector()
        self.phoneme_mapper = get_multilingual_phoneme_mapper()

    def phonemize(self, text: str, primary_language: Language | None = None) -> list[str]:
        """
        Phonemize mixed-language text.

        Args:
            text: Input text (can contain multiple languages)
            primary_language: Primary language hint (optional)

        Returns:
            List of phonemes with language tags
        """
        # Detect and split text by language
        segments = self.language_detector.split_mixed_text(text)

        if not segments:
            return []

        # Override detected language if primary language is specified
        if primary_language and len(segments) == 1:
            segments[0].language = primary_language

        # Phonemize each segment
        all_phonemes = []

        for segment in segments:
            # Get phonemes for this segment
            phoneme_segment = self._phonemize_segment(segment)

            # Add language tags and phonemes
            tagged_phonemes = self.phoneme_mapper.add_language_tags(
                phoneme_segment.phonemes,
                phoneme_segment.language.value
            )

            all_phonemes.extend(tagged_phonemes)

        return all_phonemes

    def _phonemize_segment(self, segment: TextSegment) -> PhonemeSegment:
        """Phonemize a single-language text segment."""
        text = segment.text
        language = segment.language

        if language == Language.JAPANESE:
            # Use OpenJTalk for Japanese
            phonemes = phonemize_japanese(text)
        else:
            # Use espeak-ng for other languages
            espeak_lang = self._get_espeak_language(language)
            phoneme_sentences = phonemize_espeak(text, espeak_lang)

            # Flatten sentences
            phonemes = []
            for sentence in phoneme_sentences:
                phonemes.extend(sentence)

        return PhonemeSegment(
            phonemes=phonemes,
            language=language,
            text=text
        )

    def _get_espeak_language(self, language: Language) -> str:
        """Map Language enum to espeak language code."""
        mapping = {
            Language.ENGLISH: "en-us",
            Language.CHINESE: "cmn",  # Mandarin Chinese
            Language.SPANISH: "es",
            Language.FRENCH: "fr-fr",
            Language.GERMAN: "de",
            Language.KOREAN: "ko",
        }
        return mapping.get(language, "en-us")

    def phonemize_to_ids(self, text: str, primary_language: Language | None = None) -> list[int]:
        """
        Phonemize text and convert to phoneme IDs.

        Args:
            text: Input text
            primary_language: Primary language hint

        Returns:
            List of phoneme IDs
        """
        phonemes = self.phonemize(text, primary_language)

        # Convert phonemes to IDs
        ids = []
        current_language = None

        for phoneme in phonemes:
            # Check if it's a language tag
            if phoneme.startswith("<lang:") and phoneme.endswith(">"):
                # Extract language from tag
                lang_code = phoneme[6:-1]
                current_language = lang_code
                ids.append(self.phoneme_mapper.get_phoneme_id(phoneme, ""))
            elif phoneme.startswith("</lang:") and phoneme.endswith(">"):
                ids.append(self.phoneme_mapper.get_phoneme_id(phoneme, ""))
                current_language = None
            # Regular phoneme
            elif current_language:
                ids.append(self.phoneme_mapper.get_phoneme_id(phoneme, current_language))
            else:
                # This shouldn't happen, but handle gracefully
                ids.append(self.phoneme_mapper.get_phoneme_id(phoneme, "en"))

        return ids


def phonemize_multilingual(text: str, primary_language: str | None = None) -> list[str]:
    """
    Convenience function to phonemize multilingual text.

    Args:
        text: Input text
        primary_language: Primary language code (e.g., "ja", "en")

    Returns:
        List of phonemes with language tags
    """
    phonemizer = MultilingualPhonemizer()

    # Convert language code to enum
    lang_enum = None
    if primary_language:
        try:
            lang_enum = Language(primary_language)
        except ValueError:
            _LOGGER.warning(f"Unknown language: {primary_language}, will auto-detect")

    return phonemizer.phonemize(text, lang_enum)


if __name__ == "__main__":
    # Test the multilingual phonemizer
    test_texts = [
        ("こんにちは", "ja"),
        ("Hello world", "en"),
        ("こんにちは、Hello world!", None),
        ("今日はいい天気ですね。Let's go outside!", None),
        ("Python プログラミング", None),
    ]

    phonemizer = MultilingualPhonemizer()

    for text, lang in test_texts:
        print(f"\nText: {text}")
        print(f"Primary language: {lang}")

        # Detect segments
        segments = phonemizer.language_detector.split_mixed_text(text)
        print(f"Segments: {[(s.text, s.language.value) for s in segments]}")

        # Phonemize
        lang_enum = Language(lang) if lang else None
        phonemes = phonemizer.phonemize(text, lang_enum)
        print(f"Phonemes: {phonemes}")

        # Convert to IDs
        ids = phonemizer.phonemize_to_ids(text, lang_enum)
        print(f"IDs: {ids}")
