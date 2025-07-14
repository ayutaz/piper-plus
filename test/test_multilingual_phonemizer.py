#!/usr/bin/env python3
"""Unit tests for multilingual phonemizer."""

import sys
import unittest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "python"))

from piper_train.phonemize.multilingual import (
    MultilingualPhonemizer,
    Language,
    LanguageDetector,
    phonemize_multilingual,
)
from piper_train.phonemize.multilingual_phoneme_map import get_multilingual_phoneme_mapper
from piper_train.phonemize.multilingual_dataset import (
    MultilingualDatasetFormatter,
    MultilingualUtterance,
)


class TestLanguageDetector(unittest.TestCase):
    """Test language detection functionality."""
    
    def setUp(self):
        self.detector = LanguageDetector()
    
    def test_japanese_detection(self):
        """Test Japanese text detection."""
        # Hiragana
        self.assertEqual(self.detector.detect_language("こんにちは"), Language.JAPANESE)
        # Katakana
        self.assertEqual(self.detector.detect_language("コンニチハ"), Language.JAPANESE)
        # Kanji
        self.assertEqual(self.detector.detect_language("日本語"), Language.JAPANESE)
        # Mixed
        self.assertEqual(self.detector.detect_language("日本語です"), Language.JAPANESE)
    
    def test_english_detection(self):
        """Test English text detection."""
        self.assertEqual(self.detector.detect_language("Hello world"), Language.ENGLISH)
        self.assertEqual(self.detector.detect_language("This is a test"), Language.ENGLISH)
    
    def test_mixed_text_splitting(self):
        """Test splitting mixed language text."""
        segments = self.detector.split_mixed_text("こんにちは、Hello world!")
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "こんにちは、")
        self.assertEqual(segments[0].language, Language.JAPANESE)
        self.assertEqual(segments[1].text, "Hello world!")
        self.assertEqual(segments[1].language, Language.ENGLISH)
    
    def test_complex_mixed_text(self):
        """Test complex mixed text."""
        text = "今日はいい天気ですね。Let's go outside!"
        segments = self.detector.split_mixed_text(text)
        
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].language, Language.JAPANESE)
        self.assertEqual(segments[1].language, Language.ENGLISH)


class TestMultilingualPhonemizer(unittest.TestCase):
    """Test multilingual phonemizer functionality."""
    
    def setUp(self):
        self.phonemizer = MultilingualPhonemizer()
    
    def test_japanese_only(self):
        """Test Japanese-only text."""
        phonemes = self.phonemizer.phonemize("こんにちは", Language.JAPANESE)
        
        # Should have language tags
        self.assertEqual(phonemes[0], "<lang:ja>")
        self.assertEqual(phonemes[-1], "</lang:ja>")
        
        # Should have phonemes in between
        self.assertGreater(len(phonemes), 2)
    
    def test_english_only(self):
        """Test English-only text."""
        phonemes = self.phonemizer.phonemize("Hello world", Language.ENGLISH)
        
        # Should have language tags
        self.assertEqual(phonemes[0], "<lang:en>")
        self.assertEqual(phonemes[-1], "</lang:en>")
        
        # Should have phonemes in between
        self.assertGreater(len(phonemes), 2)
    
    def test_mixed_language(self):
        """Test mixed language text."""
        phonemes = self.phonemizer.phonemize("こんにちは、Hello!")
        
        # Should have both Japanese and English tags
        self.assertIn("<lang:ja>", phonemes)
        self.assertIn("</lang:ja>", phonemes)
        self.assertIn("<lang:en>", phonemes)
        self.assertIn("</lang:en>", phonemes)
    
    def test_phoneme_to_ids(self):
        """Test conversion of phonemes to IDs."""
        ids = self.phonemizer.phonemize_to_ids("Hello", Language.ENGLISH)
        
        # All IDs should be integers
        self.assertTrue(all(isinstance(id, int) for id in ids))
        
        # Should not contain unknown tokens (ID 1)
        self.assertNotIn(1, ids)


class TestPhonemeMapper(unittest.TestCase):
    """Test phoneme ID mapping functionality."""
    
    def setUp(self):
        self.mapper = get_multilingual_phoneme_mapper()
    
    def test_special_tokens(self):
        """Test special token mapping."""
        self.assertEqual(self.mapper.get_phoneme_id("<pad>", ""), 0)
        self.assertEqual(self.mapper.get_phoneme_id("<unk>", ""), 1)
        self.assertEqual(self.mapper.get_phoneme_id("_", ""), 4)
    
    def test_language_tags(self):
        """Test language tag mapping."""
        self.assertEqual(self.mapper.get_phoneme_id("<lang:ja>", ""), 10)
        self.assertEqual(self.mapper.get_phoneme_id("</lang:ja>", ""), 20)
        self.assertEqual(self.mapper.get_phoneme_id("<lang:en>", ""), 11)
        self.assertEqual(self.mapper.get_phoneme_id("</lang:en>", ""), 21)
    
    def test_japanese_phonemes(self):
        """Test Japanese phoneme mapping."""
        # Basic vowels
        self.assertGreater(self.mapper.get_phoneme_id("a", "ja"), 99)
        self.assertLess(self.mapper.get_phoneme_id("a", "ja"), 200)
        
        # Consonants
        self.assertGreater(self.mapper.get_phoneme_id("k", "ja"), 99)
        self.assertLess(self.mapper.get_phoneme_id("k", "ja"), 200)
    
    def test_english_phonemes(self):
        """Test English phoneme mapping."""
        # Vowels
        self.assertGreater(self.mapper.get_phoneme_id("æ", "en"), 199)
        self.assertLess(self.mapper.get_phoneme_id("æ", "en"), 300)
        
        # Consonants
        self.assertGreater(self.mapper.get_phoneme_id("p", "en"), 199)
        self.assertLess(self.mapper.get_phoneme_id("p", "en"), 300)
    
    def test_vocab_size(self):
        """Test vocabulary size calculation."""
        vocab_size = self.mapper.get_vocab_size()
        self.assertGreater(vocab_size, 100)  # Should have many phonemes
        
        # Language-specific sizes
        ja_size = self.mapper.get_language_vocab_size("ja")
        en_size = self.mapper.get_language_vocab_size("en")
        
        self.assertGreater(ja_size, 40)  # Japanese has many phonemes
        self.assertGreater(en_size, 30)  # English also has many


class TestDatasetFormatter(unittest.TestCase):
    """Test dataset formatting functionality."""
    
    def setUp(self):
        self.formatter = MultilingualDatasetFormatter()
    
    def test_format_japanese_utterance(self):
        """Test formatting Japanese utterance."""
        utt = self.formatter.format_utterance(
            text="こんにちは",
            audio_path="test.wav",
            duration=1.5,
            speaker_id=0,
            primary_language="ja"
        )
        
        self.assertEqual(utt.text_language, "ja")
        self.assertEqual(len(utt.segments), 1)
        self.assertEqual(utt.segments[0]["language"], "ja")
        self.assertGreater(len(utt.phonemes), 0)
        self.assertGreater(len(utt.phoneme_ids), 0)
    
    def test_format_mixed_utterance(self):
        """Test formatting mixed language utterance."""
        utt = self.formatter.format_utterance(
            text="こんにちは、Hello!",
            audio_path="test.wav",
            duration=2.0,
            speaker_id=0
        )
        
        self.assertEqual(utt.text_language, "mixed")
        self.assertEqual(len(utt.segments), 2)
        self.assertIn("ja", [s["language"] for s in utt.segments])
        self.assertIn("en", [s["language"] for s in utt.segments])
    
    def test_utterance_to_dict(self):
        """Test utterance serialization."""
        utt = self.formatter.format_utterance(
            text="Test",
            audio_path="test.wav",
            duration=1.0
        )
        
        data = utt.to_dict()
        self.assertIn("audio_path", data)
        self.assertIn("text", data)
        self.assertIn("phonemes", data)
        self.assertIn("phoneme_ids", data)
        self.assertIn("metadata", data)


if __name__ == "__main__":
    unittest.main()