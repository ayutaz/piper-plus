"""Japanese text preprocessing utilities for enhanced phonemization.

This module provides additional preprocessing functions for Japanese text
before OpenJTalk phonemization, including:
- Half-width to full-width conversion
- Variant kanji normalization
- English to Katakana conversion
- (Future) BERT-based reading estimation

Original source: kabosu-core (https://github.com/q9uri/kabosu-core)
"""

import re
from typing import Optional

# Optional dependencies
try:
    import jaconv

    HAS_JACONV = True
except ImportError:
    HAS_JACONV = False

try:
    import kanalizer

    HAS_KANALIZER = True
except ImportError:
    HAS_KANALIZER = False

from .itaiji import normalize_itaiji


__all__ = [
    "preprocess_japanese_text",
    "convert_half_to_full",
    "convert_english_to_katakana",
]


# Regular expression to find English alphabet sequences
_RE_ALPHABET = re.compile(r"[a-z]+", re.IGNORECASE)


def convert_half_to_full(text: str) -> str:
    """Convert half-width characters to full-width (全角).

    Args:
        text: Input text with potential half-width characters

    Returns:
        Text with all half-width characters converted to full-width

    Examples:
        >>> convert_half_to_full("ｱｲｳｴｵ")
        "アイウエオ"
        >>> convert_half_to_full("ABC123")
        "ＡＢＣ１２３"
    """
    if not HAS_JACONV:
        return text

    return jaconv.h2z(text)


def convert_english_to_katakana(text: str) -> str:
    """Convert English words to Katakana using kanalizer.

    Uses VOICEVOX-derived kanalizer library for accurate English to Katakana
    conversion. Handles common English words and technical terms.

    Args:
        text: Input text with English words

    Returns:
        Text with English words converted to Katakana

    Examples:
        >>> convert_english_to_katakana("docker")
        "ドッカー"
        >>> convert_english_to_katakana("githubを使います")
        "ギットハブを使います"
        >>> convert_english_to_katakana("hello world")
        "ハロー ワールド"
    """
    if not HAS_KANALIZER:
        return text

    # Convert to lowercase for processing
    text_lower = text.lower()

    # Find all English word sequences
    matches = _RE_ALPHABET.findall(text_lower)

    # Convert each English word to Katakana
    for word in matches:
        try:
            # kanalizer handles the conversion
            katakana = kanalizer.convert(word, on_invalid_input="warning")
            # Replace in original text (preserving case context)
            text = text.replace(word, katakana)
            text = text.replace(word.upper(), katakana)
            text = text.replace(word.capitalize(), katakana)
        except Exception:
            # If conversion fails, keep original
            continue

    return text


def preprocess_japanese_text(
    text: str,
    normalize_variants: bool = True,
    convert_hankaku: bool = True,
    convert_english: bool = True,
) -> str:
    """Apply comprehensive preprocessing to Japanese text before phonemization.

    This is the main entry point for Japanese text preprocessing. It applies
    multiple normalization steps in sequence to improve phonemization accuracy.

    Args:
        text: Input Japanese text
        normalize_variants: If True, normalize variant kanji to standard forms
        convert_hankaku: If True, convert half-width to full-width characters
        convert_english: If True, convert English words to Katakana

    Returns:
        Preprocessed text ready for OpenJTalk phonemization

    Examples:
        >>> preprocess_japanese_text("dockerを使います")
        "ドッカーを使います"
        >>> preprocess_japanese_text("齋藤さんはpythonが好きです")
        "斎藤さんはパイソンが好きです"
    """
    # Step 1: Convert half-width to full-width
    if convert_hankaku and HAS_JACONV:
        text = convert_half_to_full(text)

    # Step 2: Normalize variant kanji
    if normalize_variants:
        text = normalize_itaiji(text)

    # Step 3: Convert English to Katakana
    # Note: This should be done before any other processing that might
    # interfere with English word detection
    if convert_english and HAS_KANALIZER:
        text = convert_english_to_katakana(text)

    return text


# Future enhancements placeholder
# These features from kabosu-core can be added in Phase 2:
#
# def apply_yomikata(text: str) -> str:
#     """Apply BERT-based reading estimation using yomikata.
#
#     Handles ambiguous readings like:
#     - 畳の表 (たたみのおもて vs たたみのひょう)
#     - 今日 (きょう vs こんにち)
#     """
#     pass
#
# def apply_advanced_postprocessing(labels: list[str]) -> list[str]:
#     """Apply advanced postprocessing from kabosu-core:
#
#     - retreat_acc_nuc: Adjust accent nucleus position
#     - modify_acc_after_chaining: Fix verb + auxiliary accents
#     - process_odori_features: Handle iteration marks (々, ゝ, etc.)
#     - modify_filler_accent: Normalize filler accents
#     """
#     pass
