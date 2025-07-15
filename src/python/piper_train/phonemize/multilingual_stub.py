#!/usr/bin/env python3
"""
Stub implementation for multilingual phonemization when piper_phonemize is not available.
This allows the multilingual system to work with Japanese-only mode.
"""

import logging
from dataclasses import dataclass
from enum import Enum

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


def phonemize_espeak_stub(text: str, language: str) -> list[list[str]]:
    """
    Stub function for espeak phonemization.
    Returns a simple character-based phonemization as fallback.
    """
    _LOGGER.warning(
        f"piper_phonemize not available. Using stub phonemization for {language}. "
        "Install piper_phonemize for proper non-Japanese language support."
    )

    # Simple character-based fallback
    # This is NOT accurate phonemization but allows testing
    words = text.split()
    sentences = []
    current_sentence = []

    for word in words:
        # Convert to lowercase and split into characters
        chars = list(word.lower())
        current_sentence.extend(chars)
        current_sentence.append("_")  # word boundary

        # Simple sentence detection
        if word.endswith((".", "!", "?")):
            sentences.append(current_sentence[:-1])  # Remove last "_"
            current_sentence = []

    if current_sentence:
        sentences.append(current_sentence[:-1])  # Remove last "_"

    return sentences if sentences else [[]]


class LanguageDetectorStub:
    """Stub language detector that only recognizes Japanese."""

    def detect_language(self, text: str) -> Language:
        """Detect if text contains Japanese characters."""
        for char in text:
            code_point = ord(char)
            # Check for Japanese scripts
            if (0x3040 <= code_point <= 0x309F or  # Hiragana
                0x30A0 <= code_point <= 0x30FF or  # Katakana
                0x4E00 <= code_point <= 0x9FFF):   # Kanji
                return Language.JAPANESE

        # Default to English for non-Japanese text
        return Language.ENGLISH

    def split_mixed_text(self, text: str) -> list[TextSegment]:
        """Simple split that treats entire text as one segment."""
        language = self.detect_language(text)
        return [TextSegment(
            text=text,
            language=language,
            start_idx=0,
            end_idx=len(text)
        )]


class MultilingualPhonemizerStub:
    """Stub multilingual phonemizer that only supports Japanese."""

    def __init__(self):
        self.language_detector = LanguageDetectorStub()
        _LOGGER.warning(
            "Using stub multilingual phonemizer. "
            "Only Japanese is fully supported. "
            "Install piper_phonemize for other languages."
        )

    def phonemize(self, text: str, primary_language: Language | None = None) -> list[str]:
        """Phonemize text (Japanese only in stub mode)."""
        try:
            from .japanese import phonemize_japanese
        except ImportError:
            from piper_train.phonemize.japanese import phonemize_japanese

        try:
            from .multilingual_phoneme_map import get_multilingual_phoneme_mapper
        except ImportError:
            from piper_train.phonemize.multilingual_phoneme_map import (
                get_multilingual_phoneme_mapper,
            )

        mapper = get_multilingual_phoneme_mapper()

        # Detect language
        segments = self.language_detector.split_mixed_text(text)

        if not segments:
            return []

        # Override detected language if specified
        if primary_language and len(segments) == 1:
            segments[0].language = primary_language

        all_phonemes = []

        for segment in segments:
            if segment.language == Language.JAPANESE:
                # Use real Japanese phonemizer
                phonemes = phonemize_japanese(segment.text)
                tagged_phonemes = mapper.add_language_tags(phonemes, "ja")
            else:
                # Use stub for other languages
                phoneme_sentences = phonemize_espeak_stub(segment.text, segment.language.value)
                phonemes = []
                for sentence in phoneme_sentences:
                    phonemes.extend(sentence)
                tagged_phonemes = mapper.add_language_tags(phonemes, segment.language.value)

            all_phonemes.extend(tagged_phonemes)

        return all_phonemes


def get_multilingual_phonemizer(stub_mode: bool = False):
    """
    Get appropriate multilingual phonemizer based on available dependencies.
    """
    if stub_mode:
        return MultilingualPhonemizerStub()

    try:
        # Try to import the full implementation
        from .multilingual import MultilingualPhonemizer
        return MultilingualPhonemizer()
    except ImportError as e:
        _LOGGER.warning(f"Failed to import full multilingual phonemizer: {e}")
        return MultilingualPhonemizerStub()


# For backward compatibility
def phonemize_multilingual(text: str, primary_language: str | None = None) -> list[str]:
    """
    Convenience function to phonemize multilingual text.
    Falls back to stub if dependencies are missing.
    """
    phonemizer = get_multilingual_phonemizer()

    # Convert language code to enum
    lang_enum = None
    if primary_language:
        try:
            lang_enum = Language(primary_language)
        except ValueError:
            _LOGGER.warning(f"Unknown language: {primary_language}")

    return phonemizer.phonemize(text, lang_enum)
