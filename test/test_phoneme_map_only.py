#!/usr/bin/env python3
"""Test script for phoneme mapping only (no external dependencies)."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from piper_train.phonemize.multilingual_phoneme_map import (
    get_multilingual_phoneme_mapper,
    SPECIAL_TOKENS,
    JAPANESE_PHONEMES,
    ENGLISH_PHONEMES,
    COMMON_PHONEMES
)


def test_phoneme_mapper():
    """Test the phoneme mapper functionality."""
    print("Testing Multilingual Phoneme Mapper\n")
    print("=" * 50)
    
    mapper = get_multilingual_phoneme_mapper()
    
    # Test vocabulary size
    print("\n1. Vocabulary Statistics:")
    print(f"   Total vocabulary size: {mapper.get_vocab_size()}")
    print(f"   Japanese vocabulary size: {mapper.get_language_vocab_size('ja')}")
    print(f"   English vocabulary size: {mapper.get_language_vocab_size('en')}")
    print(f"   Special tokens count: {len(SPECIAL_TOKENS)}")
    print(f"   Common phonemes count: {len(COMMON_PHONEMES)}")
    
    # Test special tokens
    print("\n2. Special Token Mapping:")
    for token, expected_id in SPECIAL_TOKENS.items():
        actual_id = mapper.get_phoneme_id(token, "")
        status = "✓" if actual_id == expected_id else "✗"
        print(f"   {status} {token:15} -> {actual_id:3} (expected: {expected_id})")
    
    # Test Japanese phonemes
    print("\n3. Japanese Phoneme Mapping (sample):")
    test_ja = ["a", "i", "u", "e", "o", "k", "s", "t", "n", "N", "ch", "ts", "^", "$", "#", "[", "]"]
    for phoneme in test_ja:
        id = mapper.get_phoneme_id(phoneme, "ja")
        print(f"   ja:{phoneme:3} -> {id:3}")
    
    # Test English phonemes
    print("\n4. English Phoneme Mapping (sample):")
    test_en = ["æ", "ɑ", "ə", "p", "b", "t", "d", "s", "z", "ˈ", "ˌ"]
    for phoneme in test_en:
        id = mapper.get_phoneme_id(phoneme, "en")
        print(f"   en:{phoneme:3} -> {id:3}")
    
    # Test common phoneme mapping
    print("\n5. Common Phoneme Mapping:")
    common_test = [("ja", "a"), ("ja", "k"), ("en", "p"), ("en", "t")]
    for lang, phoneme in common_test:
        id = mapper.get_phoneme_id(phoneme, lang)
        common = mapper._get_common_mapping(phoneme, lang)
        print(f"   {lang}:{phoneme} -> {id:3} (common: {common})")
    
    # Test encoding sequences
    print("\n6. Sequence Encoding:")
    
    # Japanese example: こんにちは
    ja_phonemes = ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
    ja_with_tags = mapper.add_language_tags(ja_phonemes, "ja")
    ja_ids = mapper.encode_phoneme_sequence(ja_with_tags, "ja")
    
    print(f"\n   Japanese: こんにちは")
    print(f"   Phonemes: {ja_phonemes}")
    print(f"   With tags: {ja_with_tags}")
    print(f"   IDs: {ja_ids}")
    
    # English example: hello
    en_phonemes = ["h", "ə", "l", "oʊ"]
    en_with_tags = mapper.add_language_tags(en_phonemes, "en")
    en_ids = mapper.encode_phoneme_sequence(en_with_tags, "en")
    
    print(f"\n   English: hello")
    print(f"   Phonemes: {en_phonemes}")
    print(f"   With tags: {en_with_tags}")
    print(f"   IDs: {en_ids}")
    
    # Test decoding
    print("\n7. Sequence Decoding:")
    decoded_ja = mapper.decode_id_sequence(ja_ids)
    decoded_en = mapper.decode_id_sequence(en_ids)
    
    print(f"   Japanese decoded: {decoded_ja}")
    print(f"   English decoded: {decoded_en}")
    
    # Test mixed sequence
    print("\n8. Mixed Language Sequence:")
    mixed_ids = ja_ids[:-1] + en_ids  # Remove one </lang:ja> tag
    mixed_decoded = mapper.decode_id_sequence(mixed_ids)
    print(f"   Mixed IDs: {mixed_ids}")
    print(f"   Decoded: {mixed_decoded}")
    
    print("\n" + "=" * 50)
    print("✓ All phoneme mapping tests completed successfully!")


if __name__ == "__main__":
    test_phoneme_mapper()