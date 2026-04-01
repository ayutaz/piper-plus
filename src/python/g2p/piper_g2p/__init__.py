"""piper-g2p: Multilingual G2P for TTS."""

__version__ = "0.1.0"

from .base import Phonemizer, ProsodyInfo
from .encode.encoder import PiperEncoder
from .multilingual import MultilingualPhonemizer, UnicodeLanguageDetector
from .registry import (
    PhonemizerRegistry,
    available_languages,
    get_phonemizer,
    register_language,
)

__all__ = [
    "__version__",
    "Phonemizer",
    "PhonemizerRegistry",
    "ProsodyInfo",
    "MultilingualPhonemizer",
    "UnicodeLanguageDetector",
    "get_phonemizer",
    "register_language",
    "available_languages",
]
