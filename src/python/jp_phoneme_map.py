#!/usr/bin/env python3
"""
Japanese phoneme mapping for OpenJTalk with support for unvoiced vowels.
This module defines the phoneme-to-ID mapping for Japanese text-to-speech.
"""

# OpenJTalk phoneme to PUA (Private Use Area) mapping
# This must match the mapping in openjtalk_phonemize.cpp
PHONEME_TO_PUA = {
    # Long vowels
    "a:": "\uE000", "i:": "\uE001", "u:": "\uE002", "e:": "\uE003", "o:": "\uE004",
    # Special consonants
    "cl": "\uE005",  # 促音/終止閉鎖
    # Palatalized consonants
    "ky": "\uE006", "kw": "\uE007", "gy": "\uE008", "gw": "\uE009",
    "ty": "\uE00A", "dy": "\uE00B", "py": "\uE00C", "by": "\uE00D",
    "ch": "\uE00E", "ts": "\uE00F", "sh": "\uE010",
    "zy": "\uE011", "hy": "\uE012", "ny": "\uE013",
    "my": "\uE014", "ry": "\uE015"
}

def get_phoneme_id_map():
    """
    Returns the complete phoneme-to-ID mapping for Japanese.
    Includes support for both voiced and unvoiced vowels.
    """
    phoneme_id_map = {
        # Special tokens
        "_": 0,  # Pause/silence
        "^": 1,  # Start
        "$": 2,  # End
        "?": 3,  # Question
        "#": 4,  # Boundary
        "[": 5,  # Left bracket
        "]": 6,  # Right bracket

        # Voiced vowels (lowercase)
        "a": 7, "i": 8, "u": 9, "e": 10, "o": 11,

        # Unvoiced vowels (uppercase) - NEW
        "A": 12, "I": 13, "U": 14, "E": 15, "O": 16,

        # Special phonemes
        "N": 17,  # Moraic nasal ん
        "q": 18,  # Glottal stop っ

        # Consonants
        "k": 19, "g": 20, "t": 21, "d": 22, "p": 23, "b": 24,
        "s": 25, "z": 26, "j": 27, "f": 28, "h": 29, "v": 30,
        "n": 31, "m": 32, "r": 33, "w": 34, "y": 35,

        # PUA mappings (multi-character phonemes)
        "\uE000": 36,  # a:
        "\uE001": 37,  # i:
        "\uE002": 38,  # u:
        "\uE003": 39,  # e:
        "\uE004": 40,  # o:
        "\uE005": 41,  # cl
        "\uE006": 42,  # ky
        "\uE007": 43,  # kw
        "\uE008": 44,  # gy
        "\uE009": 45,  # gw
        "\uE00A": 46,  # ty
        "\uE00B": 47,  # dy
        "\uE00C": 48,  # py
        "\uE00D": 49,  # by
        "\uE00E": 50,  # ch
        "\uE00F": 51,  # ts
        "\uE010": 52,  # sh
        "\uE011": 53,  # zy
        "\uE012": 54,  # hy
        "\uE013": 55,  # ny
        "\uE014": 56,  # my
        "\uE015": 57,  # ry
    }

    return phoneme_id_map

def get_phoneme_list():
    """Returns a list of all phonemes in order of their IDs."""
    phoneme_map = get_phoneme_id_map()
    # Create reverse mapping
    id_to_phoneme = {v: k for k, v in phoneme_map.items()}
    # Return sorted by ID
    return [id_to_phoneme[i] for i in sorted(id_to_phoneme.keys())]

def convert_phonemes_to_ids(phonemes):
    """
    Converts a list of phonemes to their corresponding IDs.

    Args:
        phonemes: List of phoneme strings

    Returns:
        List of phoneme IDs
    """
    phoneme_map = get_phoneme_id_map()
    ids = []

    for phoneme in phonemes:
        # Check if it's a multi-character phoneme that needs PUA conversion
        if phoneme in PHONEME_TO_PUA:
            pua_char = PHONEME_TO_PUA[phoneme]
            if pua_char in phoneme_map:
                ids.append(phoneme_map[pua_char])
            else:
                print(f"Warning: PUA character for '{phoneme}' not in phoneme map")
                ids.append(0)  # Use silence as fallback
        elif phoneme in phoneme_map:
            ids.append(phoneme_map[phoneme])
        else:
            print(f"Warning: Unknown phoneme '{phoneme}'")
            ids.append(0)  # Use silence as fallback

    return ids

def create_model_config(model_path="ja_JP-openjtalk-medium"):
    """
    Creates a model configuration with Japanese phoneme mappings.

    Args:
        model_path: Base path for the model

    Returns:
        Dictionary containing model configuration
    """
    phoneme_map = get_phoneme_id_map()

    # Convert to format expected by Piper
    phoneme_id_map = {}
    for phoneme, id_val in phoneme_map.items():
        phoneme_id_map[phoneme] = [id_val]

    config = {
        "dataset": "japanese_tts",
        "audio": {
            "sample_rate": 22050,
            "quality": "medium"
        },
        "espeak": {
            "voice": "ja"
        },
        "language": {
            "code": "ja"
        },
        "inference": {
            "noise_scale": 0.667,
            "length_scale": 1,
            "noise_w": 0.8
        },
        "phoneme_type": "openjtalk",
        "phoneme_map": {},
        "phoneme_id_map": phoneme_id_map,
        "num_symbols": len(phoneme_map),
        "num_speakers": 1,
        "speaker_id_map": {},
        "piper_version": "1.0.0"
    }

    return config

if __name__ == "__main__":
    # Test the mappings
    print("Japanese Phoneme ID Mapping:")
    print("=" * 60)

    phoneme_list = get_phoneme_list()
    phoneme_map = get_phoneme_id_map()

    for i, phoneme in enumerate(phoneme_list):
        if len(phoneme) == 1 and ord(phoneme) >= 0xE000:
            # Find the original phoneme for PUA characters
            original = None
            for orig, pua in PHONEME_TO_PUA.items():
                if pua == phoneme:
                    original = orig
                    break
            print(f"{i:3d}: {repr(phoneme)} (PUA for '{original}')")
        else:
            print(f"{i:3d}: {repr(phoneme)}")

    print(f"\nTotal phonemes: {len(phoneme_list)}")

    # Test conversion
    print("\nTest conversion:")
    test_phonemes = ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
    test_ids = convert_phonemes_to_ids(test_phonemes)
    print(f"Phonemes: {test_phonemes}")
    print(f"IDs: {test_ids}")

    # Test with unvoiced vowels
    test_phonemes2 = ["d", "e", "s", "U"]  # です with unvoiced う
    test_ids2 = convert_phonemes_to_ids(test_phonemes2)
    print(f"\nPhonemes: {test_phonemes2}")
    print(f"IDs: {test_ids2}")
