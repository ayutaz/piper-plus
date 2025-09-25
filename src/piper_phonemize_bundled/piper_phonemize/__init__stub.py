"""
piper_phonemize - Python-only stub implementation for CI testing
Provides minimal implementations of required functions
"""

__version__ = "1.2.0"


def phonemize_espeak(text: str, voice: str = "en-us") -> list:
    """Stub implementation for testing"""
    # Return ASCII-only phonemes to avoid Windows encoding issues
    return (
        ["h", "e", "l", "o"]
        if text.lower().startswith("hello")
        else ["t", "e", "s", "t"]
    )


def phonemize_codepoints(text: str) -> list:
    """Stub implementation for testing"""
    # Return codepoint values for testing
    return [ord(c) for c in text[:4]]


def phoneme_ids_espeak(phonemes: list) -> list:
    """Stub implementation for testing"""
    # Return simple IDs for testing
    return list(range(len(phonemes)))


def tashkeel_run(text: str) -> str:
    """Stub implementation for testing"""
    return text


# Constants
DEFAULT_PHONEME_ID_MAP = {}


# Backwards compatibility
def phonemize_text(text: str, voice: str = "en-us") -> list:
    """Legacy function name for compatibility"""
    return phonemize_espeak(text, voice)


def phonemize(
    text: str,
    language: str = "en-us",
    return_phonemes: bool = True,
    return_ids: bool = False,
) -> tuple:
    """High-level phonemization function"""
    result = []

    if return_phonemes:
        phonemes = phonemize_espeak(text, language)
        result.append(phonemes)
    else:
        result.append(None)

    if return_ids:
        if return_phonemes:
            ids = phoneme_ids_espeak(result[0])
        else:
            phonemes = phonemize_espeak(text, language)
            ids = phoneme_ids_espeak(phonemes)
        result.append(ids)
    else:
        result.append(None)

    if len(result) == 1:
        return result[0]
    return tuple(result)


def is_available() -> bool:
    """Check if the C++ extension is available (always False for stub)"""
    return False


# Public API
__all__ = [
    "phonemize_espeak",
    "phonemize_codepoints",
    "phoneme_ids_espeak",
    "tashkeel_run",
    "DEFAULT_PHONEME_ID_MAP",
    "phonemize",
    "is_available",
]
