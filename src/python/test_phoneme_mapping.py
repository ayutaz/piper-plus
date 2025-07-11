#!/usr/bin/env python3
"""
Test phoneme mapping for Japanese with unvoiced vowels.
"""

from jp_phoneme_map import PHONEME_TO_PUA, get_phoneme_id_map


def test_phoneme_mapping():
    """Test that all phonemes are correctly mapped."""
    phoneme_map = get_phoneme_id_map()

    print("Japanese Phoneme Mapping Test")
    print("=" * 60)

    # Test basic vowels
    print("\n1. Basic Vowels:")
    for vowel in ["a", "i", "u", "e", "o"]:
        voiced_id = phoneme_map.get(vowel, -1)
        unvoiced_id = phoneme_map.get(vowel.upper(), -1)
        print(f"   {vowel}: ID {voiced_id} (voiced)")
        print(f"   {vowel.upper()}: ID {unvoiced_id} (unvoiced)")

    # Test special phonemes
    print("\n2. Special Phonemes:")
    special = {"N": "Moraic nasal ん", "q": "Glottal stop っ", "_": "Pause/silence"}
    for phoneme, desc in special.items():
        id_val = phoneme_map.get(phoneme, -1)
        print(f"   {phoneme}: ID {id_val} ({desc})")

    # Test multi-character phonemes
    print("\n3. Multi-character Phonemes (PUA):")
    for orig, pua in sorted(PHONEME_TO_PUA.items()):
        id_val = phoneme_map.get(pua, -1)
        print(f"   {orig} → U+{ord(pua):04X}: ID {id_val}")

    # Test example conversions
    print("\n4. Example Phoneme Sequences:")
    examples = [
        ("です", ["d", "e", "s", "U"]),  # Unvoiced う
        ("でした", ["d", "e", "sh", "I", "t", "a"]),  # Unvoiced い
        ("学生", ["g", "a", "k", "u", "s", "e", "e"]),  # No unvoicing
        ("ありがとう", ["a", "r", "i", "g", "a", "t", "o", "o"]),  # Long vowel
    ]

    for text, phonemes in examples:
        print(f"\n   {text}:")
        print(f"   Phonemes: {' '.join(phonemes)}")

        # Convert to IDs
        ids = []
        for p in phonemes:
            if p in PHONEME_TO_PUA:
                # Multi-character phoneme
                pua = PHONEME_TO_PUA[p]
                id_val = phoneme_map.get(pua, -1)
            else:
                # Single character
                id_val = phoneme_map.get(p, -1)
            ids.append(id_val)

        print(f"   IDs: {ids}")

        # Check for missing mappings
        missing = [p for p, i in zip(phonemes, ids, strict=False) if i == -1]
        if missing:
            print(f"   WARNING: Missing mappings for: {missing}")

    # Statistics
    print("\n5. Statistics:")
    print(f"   Total phonemes: {len(phoneme_map)}")
    print(
        f"   Single-character phonemes: {len([p for p in phoneme_map if len(p) == 1])}"
    )
    print(
        f"   PUA phonemes: {len([p for p in phoneme_map if len(p) == 1 and ord(p) >= 0xE000])}"
    )

    # Verify no ID conflicts
    id_to_phoneme = {}
    conflicts = []
    for phoneme, id_val in phoneme_map.items():
        if id_val in id_to_phoneme:
            conflicts.append((phoneme, id_to_phoneme[id_val], id_val))
        else:
            id_to_phoneme[id_val] = phoneme

    if conflicts:
        print("\n   WARNING: ID conflicts found:")
        for p1, p2, id_val in conflicts:
            print(f"     '{p1}' and '{p2}' both map to ID {id_val}")
    else:
        print("   ✓ No ID conflicts found")


if __name__ == "__main__":
    test_phoneme_mapping()
