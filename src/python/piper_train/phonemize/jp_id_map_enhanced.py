"""Enhanced Japanese phoneme ID map with accent strength levels."""

from .token_mapper import register

__all__ = ["get_japanese_enhanced_id_map", "JAPANESE_PHONEMES", "SPECIAL_TOKENS", "ACCENT_STRENGTH_TOKENS"]

# Prosody / sentence boundary tokens
SPECIAL_TOKENS: list[str] = [
    "_",  # short pause (pau)
    "^",  # BOS
    "$",  # EOS (declarative)
    "?",  # EOS (interrogative)
    "#",  # accent phrase boundary
    "[",  # rising pitch mark (basic - for compatibility)
    "]",  # falling pitch mark (basic - for compatibility)
]

# Enhanced accent strength tokens
ACCENT_STRENGTH_TOKENS: list[str] = [
    "[1",  # weak rising pitch
    "[2",  # medium rising pitch
    "[3",  # strong rising pitch
    "]1",  # weak falling pitch
    "]2",  # medium falling pitch
    "]3",  # strong falling pitch
    "?!",  # WH question end
    "?.",  # Rhetorical question end
    "?~",  # Tag question end
]

# Core phoneme set
JAPANESE_PHONEMES: list[str] = [
    # voiced vowels
    "a", "i", "u", "e", "o",
    # unvoiced vowels (uppercase)
    "A", "I", "U", "E", "O",
    # long vowels
    "a:", "i:", "u:", "e:", "o:",
    # special consonant-centric phonemes
    "N",  # 撥音 (ん)
    "cl",  # 促音 / 終止閉鎖
    "q",  # 促音 (alternate label)
    # plosives + voiced counterparts
    "k", "g",
    "ky", "gy",
    "s", "z",
    "sh", "j",
    "t", "d",
    "ts",
    "ch",
    "ty",
    "dy",
    "n",
    "ny",
    "h", "b", "p",
    "hy", "by", "py",
    "f",
    "m",
    "my",
    "y",
    "r",
    "ry",
    "w",
    "v",
]

# Register all tokens with the mapper
for token in SPECIAL_TOKENS + ACCENT_STRENGTH_TOKENS + JAPANESE_PHONEMES:
    register(token)


def get_japanese_enhanced_id_map() -> dict[str, list[int]]:
    """Get enhanced Japanese phoneme to ID mapping with accent strength levels.
    
    Returns:
        Dictionary mapping phoneme strings to lists of token IDs.
    """
    id_map: dict[str, list[int]] = {}
    token_id = 0
    
    # Add padding token
    id_map["_PAD_"] = [token_id]
    token_id += 1
    
    # Add all tokens
    all_tokens = SPECIAL_TOKENS + ACCENT_STRENGTH_TOKENS + JAPANESE_PHONEMES
    
    for token in all_tokens:
        if token not in id_map:
            id_map[token] = [token_id]
            token_id += 1
    
    # Add compatibility mappings (old marks map to medium strength)
    if "[2" in id_map and "[" not in id_map:
        id_map["["] = id_map["[2"]  # Medium rise
    if "]2" in id_map and "]" not in id_map:
        id_map["]"] = id_map["]2"]  # Medium fall
    
    return id_map