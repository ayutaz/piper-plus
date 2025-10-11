"""Japanese text preprocessing utilities for enhanced phonemization.

This module provides additional preprocessing functions for Japanese text
before OpenJTalk phonemization, including:
- Half-width to full-width conversion
- Variant kanji normalization
- English to Katakana conversion
- BERT-based reading disambiguation (Phase 2)

Original source: kabosu-core (https://github.com/q9uri/kabosu-core)
"""

import re
import warnings


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

try:
    from yomikata.dbert import dBert

    HAS_YOMIKATA = True
    # Global instance of yomikata reader (lazy initialization)
    _global_yomikata_reader: dBert | None = None
except ImportError:
    HAS_YOMIKATA = False
    _global_yomikata_reader = None

from .itaiji import normalize_itaiji


__all__ = [
    "preprocess_japanese_text",
    "convert_half_to_full",
    "convert_english_to_katakana",
    "apply_yomikata",
]


# Regular expression to find English alphabet sequences
_RE_ALPHABET = re.compile(r"[a-z]+", re.IGNORECASE)

# Regular expression to find furigana patterns: {word/yomi}
_RE_FURIGANA = re.compile(r"\{(.+?)/(.+?)\}")


def convert_half_to_full(text: str) -> str:
    """Convert half-width characters to full-width (全角).

    Note: ASCII alphabets are NOT converted by this function, as they should be
    handled by convert_english_to_katakana() instead. Only kana, digits, and
    symbols are converted.

    Args:
        text: Input text with potential half-width characters

    Returns:
        Text with half-width kana, digits, and symbols converted to full-width

    Examples:
        >>> convert_half_to_full("ｱｲｳｴｵ")
        "アイウエオ"
        >>> convert_half_to_full("123")
        "１２３"
    """
    if not HAS_JACONV:
        return text

    # Convert kana and digits, but NOT ascii alphabets
    # ASCII alphabets should be handled by convert_english_to_katakana
    return jaconv.h2z(text, kana=True, ascii=False, digit=True)


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


def apply_yomikata(text: str) -> str:
    """Apply BERT-based reading disambiguation using yomikata.

    Uses yomikata library to determine context-appropriate readings for
    ambiguous kanji (heteronyms). For example:
    - 表 → おもて (surface) vs ひょう (table)
    - 風 → かぜ (wind) vs ふう (style)
    - 今日 → きょう (today) vs こんにち (nowadays)

    Args:
        text: Input text with potential ambiguous kanji

    Returns:
        Text with ambiguous kanji converted to katakana based on context

    Examples:
        >>> apply_yomikata("畳の表は美しい")
        "畳のオモテは美しい"
        >>> apply_yomikata("風が強い")
        "カゼが強い"

    Note:
        Requires yomikata library and BERT model download:
        $ pip install git+https://github.com/q9uri/yomikata.git
        $ python -m yomikata download
    """
    if not HAS_YOMIKATA:
        return text

    global _global_yomikata_reader

    # Lazy initialization of yomikata reader
    if _global_yomikata_reader is None:
        try:
            _global_yomikata_reader = dBert()
        except Exception as e:
            # If model not downloaded, provide helpful error message
            if "model" in str(e).lower() or "download" in str(e).lower():
                warnings.warn(
                    "yomikata BERT model not found. Please download it with: "
                    "python -m yomikata download",
                    stacklevel=2,
                )
            return text

    try:
        # Generate furigana text with {word/yomi} format
        furigana_text = _global_yomikata_reader.furigana(text)

        # Extract all {word/yomi} patterns
        matches = _RE_FURIGANA.findall(furigana_text)

        # Replace each word with its reading in katakana
        for word, yomi in matches:
            # Convert hiragana reading to katakana
            if HAS_JACONV:
                yomi_katakana = jaconv.hira2kata(yomi)
            else:
                # If jaconv not available, use hiragana as-is
                yomi_katakana = yomi

            # Replace the word with its reading
            text = text.replace(word, yomi_katakana)

    except Exception:
        # If yomikata fails, return original text
        pass

    return text


def preprocess_japanese_text(
    text: str,
    normalize_variants: bool = True,
    convert_hankaku: bool = True,
    convert_english: bool = True,
    use_yomikata: bool = True,
) -> str:
    """Apply comprehensive preprocessing to Japanese text before phonemization.

    This is the main entry point for Japanese text preprocessing. It applies
    multiple normalization steps in sequence to improve phonemization accuracy.

    Args:
        text: Input Japanese text
        normalize_variants: If True, normalize variant kanji to standard forms
        convert_hankaku: If True, convert half-width to full-width characters
        convert_english: If True, convert English words to Katakana
        use_yomikata: If True, apply BERT-based reading disambiguation

    Returns:
        Preprocessed text ready for OpenJTalk phonemization

    Examples:
        >>> preprocess_japanese_text("dockerを使います")
        "ドッカーを使います"
        >>> preprocess_japanese_text("齋藤さんはpythonが好きです")
        "斎藤さんはパイソンが好きです"
        >>> preprocess_japanese_text("畳の表は美しい")
        "畳のオモテは美しい"
    """
    # Step 1: Normalize variant kanji first
    if normalize_variants:
        text = normalize_itaiji(text)

    # Step 2: Apply BERT-based reading disambiguation (Phase 2)
    # This should be done after normalization but before other conversions
    if use_yomikata and HAS_YOMIKATA:
        text = apply_yomikata(text)

    # Step 3: Convert English to Katakana
    # IMPORTANT: This must be done BEFORE convert_half_to_full
    # to avoid converting ASCII letters to full-width before katakana conversion
    if convert_english and HAS_KANALIZER:
        text = convert_english_to_katakana(text)

    # Step 4: Convert half-width to full-width
    # This should be done last to handle any remaining half-width characters
    if convert_hankaku and HAS_JACONV:
        text = convert_half_to_full(text)

    return text


# Future enhancements placeholder
# These features from kabosu-core can be added in Phase 3:
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
