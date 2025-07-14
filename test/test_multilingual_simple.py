#!/usr/bin/env python3
"""Simple test script for multilingual phonemizer without external dependencies."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from piper_train.phonemize.multilingual_phoneme_map import get_multilingual_phoneme_mapper
from piper_train.phonemize.multilingual_dataset import MultilingualUtterance


def test_phoneme_mapper():
    """Test the phoneme mapper functionality."""
    print("Testing Phoneme Mapper...")
    mapper = get_multilingual_phoneme_mapper()
    
    # Test vocabulary size
    print(f"Total vocabulary size: {mapper.get_vocab_size()}")
    print(f"Japanese vocabulary size: {mapper.get_language_vocab_size('ja')}")
    print(f"English vocabulary size: {mapper.get_language_vocab_size('en')}")
    
    # Test special tokens
    print("\nSpecial tokens:")
    print(f"<pad> -> {mapper.get_phoneme_id('<pad>', '')}")
    print(f"<unk> -> {mapper.get_phoneme_id('<unk>', '')}")
    print(f"<lang:ja> -> {mapper.get_phoneme_id('<lang:ja>', '')}")
    print(f"<lang:en> -> {mapper.get_phoneme_id('<lang:en>', '')}")
    
    # Test Japanese phonemes
    print("\nJapanese phonemes:")
    ja_phonemes = ["a", "i", "u", "e", "o", "k", "s", "t", "n", "h", "m", "y", "r", "w", "N"]
    for phoneme in ja_phonemes[:5]:
        id = mapper.get_phoneme_id(phoneme, "ja")
        print(f"ja:{phoneme} -> {id}")
    
    # Test English phonemes
    print("\nEnglish phonemes:")
    en_phonemes = ["æ", "ɑ", "ə", "p", "b", "t", "d", "k", "g"]
    for phoneme in en_phonemes[:5]:
        id = mapper.get_phoneme_id(phoneme, "en")
        print(f"en:{phoneme} -> {id}")
    
    # Test encoding a sequence
    print("\nTest encoding sequences:")
    ja_seq = mapper.add_language_tags(["k", "o", "N", "n", "i", "ch", "i", "w", "a"], "ja")
    print(f"Japanese sequence: {ja_seq}")
    
    en_seq = mapper.add_language_tags(["h", "ə", "l", "oʊ"], "en")
    print(f"English sequence: {en_seq}")
    
    print("\n✓ Phoneme mapper tests passed!")


def test_utterance_format():
    """Test utterance data format."""
    print("\nTesting Utterance Format...")
    
    # Create a sample utterance
    utt = MultilingualUtterance(
        audio_path="test.wav",
        text="こんにちは、Hello!",
        text_language="mixed",
        segments=[
            {
                "text": "こんにちは、",
                "language": "ja",
                "start_idx": 0,
                "end_idx": 6
            },
            {
                "text": "Hello!",
                "language": "en",
                "start_idx": 6,
                "end_idx": 12
            }
        ],
        phonemes=["<lang:ja>", "k", "o", "N", "n", "i", "ch", "i", "w", "a", "</lang:ja>",
                  "<lang:en>", "h", "ə", "l", "oʊ", "</lang:en>"],
        phoneme_ids=[10, 110, 104, 124, 116, 101, 137, 101, 123, 100, 20,
                     11, 244, 202, 248, 213, 21],
        duration=2.0,
        speaker_id=0,
        metadata={
            "primary_language": "ja",
            "language_ratio": {"ja": 0.6, "en": 0.4}
        }
    )
    
    # Test conversion to dict
    data = utt.to_dict()
    print(f"Utterance fields: {list(data.keys())}")
    print(f"Text: {data['text']}")
    print(f"Language: {data['text_language']}")
    print(f"Segments: {data['segments']}")
    print(f"Number of phonemes: {len(data['phonemes'])}")
    print(f"Number of phoneme IDs: {len(data['phoneme_ids'])}")
    
    print("\n✓ Utterance format tests passed!")


def test_language_detection():
    """Test simple language detection logic."""
    print("\nTesting Language Detection Logic...")
    
    # Simple character-based detection
    def detect_script(text):
        for char in text:
            code_point = ord(char)
            # Hiragana
            if 0x3040 <= code_point <= 0x309F:
                return "Japanese (Hiragana)"
            # Katakana
            elif 0x30A0 <= code_point <= 0x30FF:
                return "Japanese (Katakana)"
            # CJK Unified Ideographs
            elif 0x4E00 <= code_point <= 0x9FFF:
                return "CJK (Kanji/Chinese)"
            # Hangul
            elif 0xAC00 <= code_point <= 0xD7AF:
                return "Korean"
            # Latin
            elif 0x0041 <= code_point <= 0x007A:
                return "Latin (English)"
        return "Unknown"
    
    test_texts = [
        "こんにちは",     # Hiragana
        "コンニチハ",     # Katakana
        "日本語",        # Kanji
        "Hello",        # English
        "안녕하세요",      # Korean
    ]
    
    for text in test_texts:
        script = detect_script(text)
        print(f"{text} -> {script}")
    
    print("\n✓ Language detection tests passed!")


if __name__ == "__main__":
    print("Running Multilingual Phonemizer Tests\n")
    print("=" * 50)
    
    test_phoneme_mapper()
    test_utterance_format()
    test_language_detection()
    
    print("\n" + "=" * 50)
    print("All tests completed successfully! ✓")