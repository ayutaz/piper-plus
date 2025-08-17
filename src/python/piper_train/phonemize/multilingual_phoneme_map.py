#!/usr/bin/env python3
"""Unified phoneme ID mapping for multilingual TTS model."""

import json
from pathlib import Path


# Special tokens
SPECIAL_TOKENS = {
    "<pad>": 0,
    "<unk>": 1,
    "<bos>": 2,
    "<eos>": 3,
    "_": 4,  # pause/silence
    # Language tags (start)
    "<lang:ja>": 10,
    "<lang:en>": 11,
    "<lang:zh>": 12,
    "<lang:es>": 13,
    "<lang:fr>": 14,
    "<lang:de>": 15,
    "<lang:ko>": 16,
    # Language tags (end)
    "</lang:ja>": 20,
    "</lang:en>": 21,
    "</lang:zh>": 22,
    "</lang:es>": 23,
    "</lang:fr>": 24,
    "</lang:de>": 25,
    "</lang:ko>": 26,
}

# Japanese phonemes (100-199)
# Based on OpenJTalk phoneme set
JAPANESE_PHONEMES = {
    # Vowels
    "a": 100,
    "i": 101,
    "u": 102,
    "e": 103,
    "o": 104,
    "A": 105,
    "I": 106,
    "U": 107,
    "E": 108,
    "O": 109,  # Unvoiced vowels
    # Consonants
    "k": 110,
    "g": 111,
    "s": 112,
    "z": 113,
    "t": 114,
    "d": 115,
    "n": 116,
    "h": 117,
    "b": 118,
    "p": 119,
    "m": 120,
    "y": 121,
    "r": 122,
    "w": 123,
    "N": 124,  # ん
    # Special moras
    "ky": 125,
    "gy": 126,
    "sy": 127,
    "zy": 128,
    "ty": 129,
    "dy": 130,
    "ny": 131,
    "hy": 132,
    "by": 133,
    "py": 134,
    "my": 135,
    "ry": 136,
    # Other sounds
    "ch": 137,
    "ts": 138,
    "f": 139,
    "j": 140,
    "sh": 141,
    # Prosody marks (Japanese specific)
    "^": 150,  # beginning of sentence
    "$": 151,  # end of sentence (declarative)
    "?": 152,  # end of sentence (interrogative)
    "#": 153,  # accent phrase boundary
    "[": 154,  # rising-pitch mark
    "]": 155,  # falling-pitch mark
}

# English phonemes (200-299)
# Based on espeak-ng phoneme set
ENGLISH_PHONEMES = {
    # Vowels
    "æ": 200,
    "ɑ": 201,
    "ə": 202,
    "ɛ": 203,
    "ɪ": 204,
    "i": 205,
    "ɔ": 206,
    "ʊ": 207,
    "u": 208,
    "ʌ": 209,
    "eɪ": 210,
    "aɪ": 211,
    "ɔɪ": 212,
    "oʊ": 213,
    "aʊ": 214,
    "ɝ": 215,
    "ɚ": 216,
    "ɑɹ": 217,
    "ɔɹ": 218,
    "ɛɹ": 219,
    "ɪɹ": 220,
    "ʊɹ": 221,
    # Consonants
    "p": 230,
    "b": 231,
    "t": 232,
    "d": 233,
    "k": 234,
    "g": 235,
    "f": 236,
    "v": 237,
    "θ": 238,
    "ð": 239,
    "s": 240,
    "z": 241,
    "ʃ": 242,
    "ʒ": 243,
    "h": 244,
    "m": 245,
    "n": 246,
    "ŋ": 247,
    "l": 248,
    "ɹ": 249,
    "w": 250,
    "j": 251,
    "tʃ": 252,
    "dʒ": 253,
    # Stress markers
    "ˈ": 260,  # primary stress
    "ˌ": 261,  # secondary stress
}

# Common phonemes shared across languages (400-499)
# These will be mapped during preprocessing
COMMON_PHONEMES = {
    # Common vowels
    "a_common": 400,
    "i_common": 401,
    "u_common": 402,
    "e_common": 403,
    "o_common": 404,
    # Common consonants
    "p_common": 410,
    "b_common": 411,
    "t_common": 412,
    "d_common": 413,
    "k_common": 414,
    "g_common": 415,
    "m_common": 416,
    "n_common": 417,
    "s_common": 418,
    "h_common": 419,
    "l_common": 420,
    "r_common": 421,
}


class MultilingualPhonemeMapper:
    """Handles phoneme to ID mapping for multilingual TTS."""

    def __init__(self):
        self.phoneme_to_id: dict[str, int] = {}
        self.id_to_phoneme: dict[int, str] = {}
        self.language_phonemes: dict[str, set[str]] = {
            "ja": set(),
            "en": set(),
        }

        # Initialize mappings
        self._init_mappings()

    def _init_mappings(self):
        """Initialize all phoneme mappings."""
        # Add special tokens
        for token, idx in SPECIAL_TOKENS.items():
            self.phoneme_to_id[token] = idx
            self.id_to_phoneme[idx] = token

        # Add Japanese phonemes
        for phoneme, idx in JAPANESE_PHONEMES.items():
            self.phoneme_to_id[f"ja:{phoneme}"] = idx
            self.id_to_phoneme[idx] = f"ja:{phoneme}"
            self.language_phonemes["ja"].add(phoneme)

        # Add English phonemes
        for phoneme, idx in ENGLISH_PHONEMES.items():
            self.phoneme_to_id[f"en:{phoneme}"] = idx
            self.id_to_phoneme[idx] = f"en:{phoneme}"
            self.language_phonemes["en"].add(phoneme)

        # Add common phonemes
        for phoneme, idx in COMMON_PHONEMES.items():
            self.phoneme_to_id[f"common:{phoneme}"] = idx
            self.id_to_phoneme[idx] = f"common:{phoneme}"

    def get_phoneme_id(self, phoneme: str, language: str) -> int:
        """Get ID for a phoneme in a specific language."""
        # Check if it's a special token
        if phoneme in SPECIAL_TOKENS:
            return SPECIAL_TOKENS[phoneme]

        # Check language-specific phoneme
        lang_phoneme = f"{language}:{phoneme}"
        if lang_phoneme in self.phoneme_to_id:
            return self.phoneme_to_id[lang_phoneme]

        # Check if it can be mapped to common phoneme
        common_mapping = self._get_common_mapping(phoneme, language)
        if common_mapping:
            return self.phoneme_to_id[f"common:{common_mapping}"]

        # Return unknown token
        return SPECIAL_TOKENS["<unk>"]

    def _get_common_mapping(self, phoneme: str, language: str) -> str | None:
        """Map language-specific phoneme to common phoneme if possible."""
        # Simple mapping rules (can be extended)
        mapping_rules = {
            ("ja", "a"): "a_common",
            ("ja", "i"): "i_common",
            ("ja", "u"): "u_common",
            ("ja", "e"): "e_common",
            ("ja", "o"): "o_common",
            ("ja", "p"): "p_common",
            ("ja", "b"): "b_common",
            ("ja", "t"): "t_common",
            ("ja", "d"): "d_common",
            ("ja", "k"): "k_common",
            ("ja", "g"): "g_common",
            ("ja", "m"): "m_common",
            ("ja", "n"): "n_common",
            ("ja", "s"): "s_common",
            ("ja", "h"): "h_common",
            ("ja", "r"): "r_common",
            ("en", "p"): "p_common",
            ("en", "b"): "b_common",
            ("en", "t"): "t_common",
            ("en", "d"): "d_common",
            ("en", "k"): "k_common",
            ("en", "g"): "g_common",
            ("en", "m"): "m_common",
            ("en", "n"): "n_common",
            ("en", "s"): "s_common",
            ("en", "h"): "h_common",
            ("en", "l"): "l_common",
        }

        return mapping_rules.get((language, phoneme))

    def encode_phoneme_sequence(self, phonemes: list[str], language: str) -> list[int]:
        """Encode a sequence of phonemes to IDs."""
        ids = []
        for phoneme in phonemes:
            ids.append(self.get_phoneme_id(phoneme, language))
        return ids

    def decode_id_sequence(self, ids: list[int]) -> list[str]:
        """Decode a sequence of IDs to phonemes."""
        phonemes = []
        for idx in ids:
            if idx in self.id_to_phoneme:
                phonemes.append(self.id_to_phoneme[idx])
            else:
                phonemes.append("<unk>")
        return phonemes

    def add_language_tags(self, phonemes: list[str], language: str) -> list[str]:
        """Add language tags to phoneme sequence."""
        start_tag = f"<lang:{language}>"
        end_tag = f"</lang:{language}>"
        return [start_tag] + phonemes + [end_tag]

    def save_mapping(self, filepath: Path):
        """Save phoneme mapping to JSON file."""
        data = {
            "special_tokens": SPECIAL_TOKENS,
            "japanese_phonemes": JAPANESE_PHONEMES,
            "english_phonemes": ENGLISH_PHONEMES,
            "common_phonemes": COMMON_PHONEMES,
            "phoneme_to_id": self.phoneme_to_id,
            "id_to_phoneme": self.id_to_phoneme,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_mapping(self, filepath: Path):
        """Load phoneme mapping from JSON file."""
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        self.phoneme_to_id = data["phoneme_to_id"]
        self.id_to_phoneme = {int(k): v for k, v in data["id_to_phoneme"].items()}

    def get_vocab_size(self) -> int:
        """Get total vocabulary size."""
        return len(self.phoneme_to_id)

    def get_language_vocab_size(self, language: str) -> int:
        """Get vocabulary size for a specific language."""
        return len(self.language_phonemes.get(language, set()))


# Singleton instance
_mapper_instance = None


def get_multilingual_phoneme_mapper() -> MultilingualPhonemeMapper:
    """Get singleton instance of phoneme mapper."""
    global _mapper_instance  # noqa: PLW0603
    if _mapper_instance is None:
        _mapper_instance = MultilingualPhonemeMapper()
    return _mapper_instance


if __name__ == "__main__":
    # Test the mapper
    mapper = get_multilingual_phoneme_mapper()

    print(f"Total vocabulary size: {mapper.get_vocab_size()}")
    print(f"Japanese vocabulary size: {mapper.get_language_vocab_size('ja')}")
    print(f"English vocabulary size: {mapper.get_language_vocab_size('en')}")

    # Test encoding
    ja_phonemes = ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
    ja_with_tags = mapper.add_language_tags(ja_phonemes, "ja")
    ja_ids = mapper.encode_phoneme_sequence(ja_with_tags, "ja")

    print("\nJapanese example:")
    print(f"Phonemes: {ja_with_tags}")
    print(f"IDs: {ja_ids}")

    en_phonemes = ["h", "ə", "l", "oʊ"]
    en_with_tags = mapper.add_language_tags(en_phonemes, "en")
    en_ids = mapper.encode_phoneme_sequence(en_with_tags, "en")

    print("\nEnglish example:")
    print(f"Phonemes: {en_with_tags}")
    print(f"IDs: {en_ids}")
