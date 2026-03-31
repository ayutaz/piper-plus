"""piper-g2p: Multilingual G2P for TTS."""

__version__ = "0.0.1"

from .base import Phonemizer, ProsodyInfo
from .registry import available_languages, get_phonemizer, register_language

__all__ = [
    "__version__",
    "Phonemizer",
    "ProsodyInfo",
    "get_phonemizer",
    "register_language",
    "available_languages",
]
