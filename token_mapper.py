"""
OpenJTalk phoneme to PUA character mapping for Piper TTS
This ensures compatibility between Python training and C++ inference
"""

# Multi-character phoneme to PUA character mapping
MULTI_CHAR_TO_PUA = {
    # Long vowels
    "a:": "\ue000",
    "i:": "\ue001", 
    "u:": "\ue002",
    "e:": "\ue003",
    "o:": "\ue004",
    # Special consonants
    "cl": "\ue005",
    # Palatalized consonants
    "ky": "\ue006",
    "kw": "\ue007",
    "gy": "\ue008",
    "gw": "\ue009",
    "ty": "\ue00a",
    "dy": "\ue00b",
    "py": "\ue00c",
    "by": "\ue00d",
    # Affricates and special sounds
    "ch": "\ue00e",
    "ts": "\ue00f",
    "sh": "\ue010",
    "zy": "\ue011",
    "hy": "\ue012",
    # Palatalized nasals/liquids
    "ny": "\ue013",
    "my": "\ue014",
    "ry": "\ue015"
}

def map_phonemes(phonemes):
    """
    Map multi-character phonemes to PUA characters
    
    Args:
        phonemes: List of phoneme strings from OpenJTalk
        
    Returns:
        List of mapped phonemes (single characters)
    """
    mapped = []
    for phoneme in phonemes:
        if phoneme in MULTI_CHAR_TO_PUA:
            mapped.append(MULTI_CHAR_TO_PUA[phoneme])
        else:
            # Single character phonemes remain unchanged
            mapped.append(phoneme)
    return mapped

def get_phoneme_id_map():
    """
    Generate phoneme_id_map for model config.json
    
    Returns:
        Dictionary mapping phonemes to IDs
    """
    # Basic phonemes
    phoneme_map = {}
    phoneme_id = 0
    
    # Add padding/special tokens
    for special in ["_", "^", "$", " "]:
        phoneme_map[special] = [phoneme_id]
        phoneme_id += 1
    
    # Add single character phonemes (Japanese phonemes)
    single_phonemes = [
        "a", "i", "u", "e", "o",
        "k", "g", "s", "z", "t", "d", "n", "h", "b", "p", "m", "y", "r", "w",
        "f", "v", "j", "q", "N"
    ]
    
    for phoneme in single_phonemes:
        phoneme_map[phoneme] = [phoneme_id]
        phoneme_id += 1
    
    # Add PUA mapped phonemes
    for pua_char in MULTI_CHAR_TO_PUA.values():
        phoneme_map[pua_char] = [phoneme_id]
        phoneme_id += 1
    
    return phoneme_map

if __name__ == "__main__":
    # Example usage
    import json
    
    # Generate phoneme_id_map for config.json
    phoneme_id_map = get_phoneme_id_map()
    
    print("Phoneme ID map for config.json:")
    print(json.dumps({"phoneme_id_map": phoneme_id_map}, ensure_ascii=False, indent=2))
    
    # Example phoneme mapping
    test_phonemes = ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
    mapped = map_phonemes(test_phonemes)
    print(f"\nOriginal: {test_phonemes}")
    print(f"Mapped: {mapped}")