"""Phonemization modules for piper-plus inference."""

from .chinese import phonemize_chinese
from .english import phonemize_english
from .french import phonemize_french
from .japanese import phonemize_japanese
from .jp_id_map import get_japanese_id_map
from .portuguese import phonemize_european_portuguese, phonemize_portuguese
from .spanish import phonemize_spanish
from .ssml import SynthesisSegment, process_ssml
from .token_mapper import map_sequence, register


__all__ = [
    "SynthesisSegment",
    "get_japanese_id_map",
    "map_sequence",
    "phonemize_chinese",
    "phonemize_english",
    "phonemize_european_portuguese",
    "phonemize_french",
    "phonemize_japanese",
    "phonemize_portuguese",
    "phonemize_spanish",
    "process_ssml",
    "register",
]
