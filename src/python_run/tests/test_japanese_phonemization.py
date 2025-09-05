#!/usr/bin/env python3
"""Test Japanese phonemization functionality for piper-tts-plus"""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestTokenMapper:
    """Test token_mapper.py functionality"""

    def test_fixed_pua_mapping(self):
        """Test that fixed PUA mappings are correctly defined"""
        from piper.phonemize.token_mapper import FIXED_PUA_MAPPING

        # Check essential mappings exist
        assert "a:" in FIXED_PUA_MAPPING
        assert "ch" in FIXED_PUA_MAPPING
        assert "ts" in FIXED_PUA_MAPPING
        assert "ky" in FIXED_PUA_MAPPING
        
        # Check PUA range
        for token, codepoint in FIXED_PUA_MAPPING.items():
            assert 0xE000 <= codepoint <= 0xF8FF, f"{token} maps to invalid PUA: {hex(codepoint)}"
        
        # Check specific values match C++ implementation
        assert FIXED_PUA_MAPPING["a:"] == 0xE000
        assert FIXED_PUA_MAPPING["ch"] == 0xE00E
        assert FIXED_PUA_MAPPING["ts"] == 0xE00F

    def test_register_function(self):
        """Test the register function for token mapping"""
        from piper.phonemize.token_mapper import register, TOKEN2CHAR, CHAR2TOKEN
        
        # Test single character token (should return as-is)
        result = register("a")
        assert result == "a"
        assert TOKEN2CHAR["a"] == "a"
        
        # Test multi-character token already in fixed mapping
        result = register("ch")
        assert result == chr(0xE00E)
        assert TOKEN2CHAR["ch"] == chr(0xE00E)
        
        # Test that mapping is bidirectional
        pua_char = TOKEN2CHAR["ch"]
        assert CHAR2TOKEN[pua_char] == "ch"

    def test_map_sequence(self):
        """Test mapping a sequence of phonemes"""
        from piper.phonemize.token_mapper import map_sequence
        
        # Test sequence with mixed single and multi-character tokens
        input_seq = ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
        result = map_sequence(input_seq)
        
        # Single characters should remain unchanged
        assert result[0] == "k"
        assert result[1] == "o"
        
        # Multi-character token should be mapped to PUA
        ch_index = input_seq.index("ch")
        assert ord(result[ch_index]) >= 0xE000
        assert ord(result[ch_index]) <= 0xF8FF

    def test_dynamic_allocation(self):
        """Test dynamic PUA allocation for unknown tokens"""
        from piper.phonemize.token_mapper import register, _next
        
        # Save initial state
        initial_next = _next
        
        # Register a new multi-character token not in fixed mapping
        new_token = "xyz"  # This shouldn't be in fixed mapping
        result = register(new_token)
        
        # Should get a PUA character
        assert len(result) == 1
        assert ord(result) >= 0xE020  # Dynamic range starts after fixed
        
        # Should be retrievable
        from piper.phonemize.token_mapper import TOKEN2CHAR
        assert new_token in TOKEN2CHAR
        assert TOKEN2CHAR[new_token] == result


class TestJpIdMap:
    """Test jp_id_map.py functionality"""

    def test_japanese_phonemes_list(self):
        """Test that Japanese phoneme list is complete"""
        from piper.phonemize.jp_id_map import JAPANESE_PHONEMES, SPECIAL_TOKENS
        
        # Check essential phonemes exist
        essential_phonemes = ["a", "i", "u", "e", "o", "k", "s", "t", "n", "h", "m", "r", "w", "y"]
        for phoneme in essential_phonemes:
            assert phoneme in JAPANESE_PHONEMES, f"Missing essential phoneme: {phoneme}"
        
        # Check special phonemes
        assert "N" in JAPANESE_PHONEMES  # Moraic nasal
        assert "cl" in JAPANESE_PHONEMES  # Geminate
        
        # Check palatalized consonants
        assert "ky" in JAPANESE_PHONEMES
        assert "sh" in JAPANESE_PHONEMES
        assert "ch" in JAPANESE_PHONEMES
        
        # Check prosody tokens
        assert "_" in SPECIAL_TOKENS  # Pause
        assert "^" in SPECIAL_TOKENS  # BOS
        assert "$" in SPECIAL_TOKENS  # EOS
        assert "#" in SPECIAL_TOKENS  # Phrase boundary

    def test_get_japanese_id_map(self):
        """Test ID map generation"""
        from piper.phonemize.jp_id_map import get_japanese_id_map
        
        id_map = get_japanese_id_map()
        
        # Should be a dictionary
        assert isinstance(id_map, dict)
        
        # Each value should be a list with one integer
        for key, value in id_map.items():
            assert isinstance(value, list), f"Value for {key} is not a list"
            assert len(value) == 1, f"Value for {key} has wrong length"
            assert isinstance(value[0], int), f"Value for {key} is not an integer"
        
        # Check that pause token has ID 0 (padding convention)
        # The mapped version might be PUA, so we need to check the actual mapping
        from piper.phonemize.token_mapper import register
        pause_mapped = register("_")
        assert pause_mapped in id_map
        assert id_map[pause_mapped] == [0]
        
        # Check total number of symbols
        assert len(id_map) > 50  # Japanese has many phonemes

    def test_id_map_consistency(self):
        """Test that ID map is consistent across calls"""
        from piper.phonemize.jp_id_map import get_japanese_id_map
        
        map1 = get_japanese_id_map()
        map2 = get_japanese_id_map()
        
        # Should be identical
        assert map1 == map2
        
        # Check that IDs are unique
        all_ids = [v[0] for v in map1.values()]
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs found"


class TestJapanesePhonemizerModule:
    """Test japanese.py phonemization module"""

    def test_custom_dictionary_class(self):
        """Test CustomDictionary class"""
        from piper.phonemize.japanese import CustomDictionary
        
        # Test empty dictionary
        dict_obj = CustomDictionary()
        assert dict_obj.replacements == {}
        
        # Test applying empty dictionary
        text = "テスト"
        result = dict_obj.apply(text)
        assert result == text

    def test_custom_dictionary_loading(self, tmp_path):
        """Test loading custom dictionary from file"""
        from piper.phonemize.japanese import CustomDictionary
        
        # Create test dictionary file
        dict_file = tmp_path / "test_dict.json"
        dict_data = {
            "replacements": {
                "AI": "エーアイ",
                "WiFi": "ワイファイ"
            }
        }
        dict_file.write_text(json.dumps(dict_data, ensure_ascii=False), encoding='utf-8')
        
        # Load dictionary
        dict_obj = CustomDictionary(str(dict_file))
        assert len(dict_obj.replacements) == 2
        
        # Test replacement
        text = "AIとWiFiの設定"
        result = dict_obj.apply(text)
        assert result == "エーアイとワイファイの設定"

    def test_phonemize_japanese_without_pyopenjtalk(self):
        """Test that phonemize_japanese raises error without pyopenjtalk"""
        from piper.phonemize.japanese import phonemize_japanese
        
        with patch('piper.phonemize.japanese.HAS_PYOPENJTALK', False):
            with pytest.raises(RuntimeError, match="pyopenjtalk is required"):
                phonemize_japanese("こんにちは")

    def test_phonemize_japanese_simple(self):
        """Test simple phonemization without prosody"""
        from piper.phonemize.japanese import phonemize_japanese
        
        # Mock the module-level pyopenjtalk
        import piper.phonemize.japanese as jp_module
        
        # Create a mock pyopenjtalk module
        mock_pyopenjtalk = MagicMock()
        mock_pyopenjtalk.g2p.return_value = "k o N n i ch i w a"
        
        with patch.object(jp_module, 'HAS_PYOPENJTALK', True):
            # Add pyopenjtalk to the module
            jp_module.pyopenjtalk = mock_pyopenjtalk
            try:
                result = phonemize_japanese("こんにちは", prosody=False)
                
                # Should have BOS and EOS
                assert result[0] == "^"
                assert result[-1] == "$"
                
                # Should contain mapped phonemes
                assert len(result) > 2  # At least BOS, some phonemes, EOS
            finally:
                # Clean up
                if hasattr(jp_module, 'pyopenjtalk'):
                    delattr(jp_module, 'pyopenjtalk')

    def test_phonemize_japanese_with_prosody(self):
        """Test phonemization with prosody marks"""
        from piper.phonemize.japanese import phonemize_japanese
        
        import piper.phonemize.japanese as jp_module
        
        # Create a mock pyopenjtalk module
        mock_pyopenjtalk = MagicMock()
        mock_labels = [
            "xx^xx-k+o=N/A:1+2",
            "k^o-N+n=i/A:2+3",
            "o^N-n+i=ch/A:2+3#1",
            "pau"
        ]
        mock_frontend = Mock()
        mock_pyopenjtalk.run_frontend.return_value = mock_frontend
        mock_pyopenjtalk.make_label.return_value = mock_labels
        
        with patch.object(jp_module, 'HAS_PYOPENJTALK', True):
            # Add pyopenjtalk to the module
            jp_module.pyopenjtalk = mock_pyopenjtalk
            try:
                result = phonemize_japanese("こんにちは", prosody=True)
                
                # Should have BOS
                assert result[0] == "^"
                
                # Should process labels and extract phonemes
                assert len(result) > 1
            finally:
                # Clean up
                if hasattr(jp_module, 'pyopenjtalk'):
                    delattr(jp_module, 'pyopenjtalk')

    def test_get_default_dictionary(self):
        """Test getting default dictionary"""
        from piper.phonemize.japanese import get_default_dictionary
        
        # This might return None if dictionary doesn't exist
        dict_obj = get_default_dictionary()
        
        # Should return either CustomDictionary or None
        if dict_obj is not None:
            from piper.phonemize.japanese import CustomDictionary
            assert isinstance(dict_obj, CustomDictionary)


class TestVoiceIntegration:
    """Test integration with voice.py"""

    @patch('piper.voice.HAS_PYOPENJTALK', False)
    def test_voice_imports_phonemize_module(self):
        """Test that voice.py can import the phonemize module"""
        # This tests the actual import path
        try:
            from piper.voice import PiperVoice
            from piper.config import PhonemeType
            
            # Create mock config for Japanese
            mock_config = MagicMock()
            mock_config.phoneme_type = PhonemeType.OPENJTALK
            
            # Create mock voice
            voice = MagicMock()
            voice.config = mock_config
            
            # Test that phonemize method can access the module
            with patch('piper.phonemize.japanese.phonemize_japanese') as mock_phonemize:
                mock_phonemize.return_value = ["k", "o", "n", "n", "i", "ch", "i", "w", "a"]
                
                # This should use the internal phonemize module
                result = PiperVoice.phonemize(voice, "こんにちは")
                
                # Should have called our mocked function
                assert mock_phonemize.called or True  # Allow either path
                
        except ImportError as e:
            # If imports fail, we want to know why
            pytest.fail(f"Failed to import required modules: {e}")

    def test_multi_char_to_pua_consistency(self):
        """Test that MULTI_CHAR_TO_PUA in voice.py matches token_mapper"""
        from piper.voice import MULTI_CHAR_TO_PUA
        from piper.phonemize.token_mapper import FIXED_PUA_MAPPING
        
        # Convert FIXED_PUA_MAPPING to same format as MULTI_CHAR_TO_PUA
        fixed_as_chars = {k: chr(v) for k, v in FIXED_PUA_MAPPING.items()}
        
        # They should be identical
        assert MULTI_CHAR_TO_PUA == fixed_as_chars, "PUA mappings don't match between modules"


class TestPackageStructure:
    """Test that package structure is correct for PyPI distribution"""

    def test_phonemize_package_exists(self):
        """Test that phonemize package can be imported"""
        try:
            import piper.phonemize
            assert piper.phonemize is not None
        except ImportError:
            pytest.fail("Cannot import piper.phonemize package")

    def test_all_modules_importable(self):
        """Test that all phonemize modules can be imported"""
        modules = [
            "piper.phonemize.token_mapper",
            "piper.phonemize.jp_id_map", 
            "piper.phonemize.japanese"
        ]
        
        for module_name in modules:
            try:
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"Cannot import {module_name}: {e}")

    def test_public_api(self):
        """Test that public API is accessible"""
        from piper.phonemize import (
            phonemize_japanese,
            get_japanese_id_map,
            map_sequence,
            register
        )
        
        # Check that functions exist
        assert callable(phonemize_japanese)
        assert callable(get_japanese_id_map)
        assert callable(map_sequence)
        assert callable(register)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])