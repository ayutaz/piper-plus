"""
piper_phonemize - Phonemization library for piper-plus
Provides text-to-phoneme conversion using espeak-ng
"""

__version__ = "1.2.0"
__author__ = "Piper-Plus Contributors"

import os
import sys
from pathlib import Path
from typing import Optional


# Add the module directory to DLL search path on Windows
if sys.platform == "win32":
    _module_dir = Path(__file__).parent
    if _module_dir.exists():
        os.add_dll_directory(str(_module_dir))
        # Also add subdirectories that might contain DLLs
        for subdir in ["bin", "lib"]:
            dll_dir = _module_dir / subdir
            if dll_dir.exists():
                os.add_dll_directory(str(dll_dir))

# Import the C++ extension
try:
    from piper_phonemize_cpp import (
        # Constants
        get_espeak_map as DEFAULT_PHONEME_ID_MAP,
        phoneme_ids_espeak,
        phonemize_codepoints as _phonemize_codepoints_raw,
        # Main functions
        phonemize_espeak as _phonemize_espeak_raw,
        # Tashkeel functions (Arabic support)
        tashkeel_run,
    )

    _cpp_available = True

    # Wrapper functions with automatic dataPath handling
    def phonemize_espeak(text: str, voice: str = "en-us", dataPath: str = "") -> list:
        """Phonemize text using espeak-ng with automatic data path detection"""
        if not dataPath:
            # Use the bundled data directory if available
            _data_dir = Path(__file__).parent / "data"
            if _data_dir.exists():
                # Convert to absolute Windows path and replace backslashes
                dataPath = str(_data_dir.resolve())
                # On Windows, ensure we use the correct separator
                if sys.platform == "win32":
                    dataPath = dataPath.replace("/", "\\")
            else:
                # Fall back to empty string - espeak-ng will use its default
                dataPath = ""
        return _phonemize_espeak_raw(text, voice, dataPath)

    def phonemize_codepoints(text: str, casing: str = "lower") -> list:
        """Phonemize text as UTF-8 codepoints"""
        return _phonemize_codepoints_raw(text, casing)

except ImportError as e:
    _cpp_available = False
    _import_error = str(e)

    # Provide stub functions when C++ module is not available
    def phonemize_espeak(
        text: str, voice: str = "en-us", dataPath: str = ""
    ) -> list[str]:
        raise ImportError(
            f"piper_phonemize C++ extension not available: {_import_error}"
        )

    def phonemize_codepoints(text: str, casing: str = "lower") -> list[int]:
        raise ImportError(
            f"piper_phonemize C++ extension not available: {_import_error}"
        )

    def phoneme_ids_espeak(phonemes: list[str]) -> list[int]:
        raise ImportError(
            f"piper_phonemize C++ extension not available: {_import_error}"
        )

    def tashkeel_run(text: str) -> str:
        raise ImportError(
            f"piper_phonemize C++ extension not available: {_import_error}"
        )

    DEFAULT_PHONEME_ID_MAP = {}


# Public API
__all__ = [
    "phonemize_espeak",
    "phonemize_codepoints",
    "phoneme_ids_espeak",
    "tashkeel_run",
    "DEFAULT_PHONEME_ID_MAP",
    "phonemize",  # High-level function
    "is_available",
]


def is_available() -> bool:
    """Check if the C++ extension is available"""
    return _cpp_available


def phonemize(
    text: str,
    language: str = "en-us",
    return_phonemes: bool = True,
    return_ids: bool = False,
) -> tuple:
    """
    High-level phonemization function

    Args:
        text: Text to phonemize
        language: Language/voice code (e.g., "en-us", "de", "fr")
        return_phonemes: Whether to return phoneme strings
        return_ids: Whether to return phoneme IDs

    Returns:
        Tuple of (phonemes, ids) based on flags.
        Returns None for disabled options.
    """
    if not _cpp_available:
        raise ImportError(
            f"piper_phonemize C++ extension not available: {_import_error}"
        )

    result = []

    if return_phonemes:
        phonemes = phonemize_espeak(text, language)
        result.append(phonemes)
    else:
        result.append(None)

    if return_ids:
        if return_phonemes:
            # Use the phonemes we already got
            ids = phoneme_ids_espeak(result[0])
        else:
            # Get phonemes first, then convert to IDs
            phonemes = phonemize_espeak(text, language)
            ids = phoneme_ids_espeak(phonemes)
        result.append(ids)
    else:
        result.append(None)

    if len(result) == 1:
        return result[0]
    return tuple(result)


# Backwards compatibility
def phonemize_text(text: str, voice: str = "en-us") -> list[str]:
    """Legacy function name for compatibility"""
    return phonemize_espeak(text, voice)


# Set up data directory path
_DATA_DIR = Path(__file__).parent / "data"
if _DATA_DIR.exists():
    # Set environment variable for espeak-ng data
    os.environ["ESPEAK_DATA_PATH"] = str(_DATA_DIR / "espeak-ng-data")


# Print debug info if requested
if os.environ.get("PIPER_PHONEMIZE_DEBUG"):
    print(f"piper_phonemize version: {__version__}")
    print(f"C++ extension available: {_cpp_available}")
    if not _cpp_available:
        print(f"Import error: {_import_error}")
    print(f"Data directory: {_DATA_DIR}")
    print(f"ESPEAK_DATA_PATH: {os.environ.get('ESPEAK_DATA_PATH', 'not set')}")
