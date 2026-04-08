"""piper-g2p: Multilingual G2P for TTS."""

__version__ = "0.2.0"

from .base import Phonemizer, ProsodyInfo
from .encode.encoder import PiperEncoder
from .multilingual import MultilingualPhonemizer, UnicodeLanguageDetector
from .registry import (
    PhonemizerRegistry,
    available_languages,
    get_phonemizer,
    register_language,
)
from .ssml import SSMLParser, SSMLSegment

__all__ = [
    "__version__",
    "Phonemizer",
    "PhonemizerRegistry",
    "PiperEncoder",
    "ProsodyInfo",
    "MultilingualPhonemizer",
    "UnicodeLanguageDetector",
    "SSMLParser",
    "SSMLSegment",
    "get_phonemizer",
    "register_language",
    "available_languages",
]
