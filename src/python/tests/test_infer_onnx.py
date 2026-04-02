"""Tests for infer_onnx module, specifically the --text functionality."""

import pytest

from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody
from piper_g2p.encode.id_maps import get_phoneme_id_map


class TestTextToPhonemeIdsAndProsody:
    """Tests for text_to_phoneme_ids_and_prosody function."""

    @pytest.fixture
    def phoneme_id_map(self):
        """Get the Japanese phoneme ID map."""
        return get_phoneme_id_map("ja")

    def test_basic_conversion(self, phoneme_id_map):
        """Test basic text to phoneme conversion."""
        text = "こんにちは"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        # Should produce non-empty output
        assert len(phoneme_ids) > 0
        assert len(prosody_features) > 0

        # phoneme_ids and prosody_features should have same length
        assert len(phoneme_ids) == len(prosody_features)

        # All phoneme IDs should be valid integers
        assert all(isinstance(pid, int) for pid in phoneme_ids)

    def test_prosody_features_structure(self, phoneme_id_map):
        """Test that prosody features have correct structure."""
        text = "今日は良い天気ですね"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        for pf in prosody_features:
            if pf is not None:
                # Should have a1, a2, a3 keys
                assert "a1" in pf
                assert "a2" in pf
                assert "a3" in pf
                # Values should be integers
                assert isinstance(pf["a1"], int)
                assert isinstance(pf["a2"], int)
                assert isinstance(pf["a3"], int)

    def test_question_sentence(self, phoneme_id_map):
        """Test question sentence conversion."""
        text = "今日は何曜日ですか？"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        # Should produce non-empty output
        assert len(phoneme_ids) > 0
        # Length should match
        assert len(phoneme_ids) == len(prosody_features)

    def test_long_sentence(self, phoneme_id_map):
        """Test long sentence conversion."""
        text = "現在の滑走を目的とした、スキーブーツは、硬いプラスチックシェルと、柔らかいインナーブーツからなる。"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        # Should produce non-empty output
        assert len(phoneme_ids) > 0
        # Length should match
        assert len(phoneme_ids) == len(prosody_features)

    def test_empty_string(self, phoneme_id_map):
        """Test empty string handling."""
        text = ""
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        # Empty input should produce minimal output (BOS/EOS)
        # The exact behavior depends on the phonemizer
        assert isinstance(phoneme_ids, list)
        assert isinstance(prosody_features, list)

    def test_single_character(self, phoneme_id_map):
        """Test single character conversion."""
        text = "あ"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        assert len(phoneme_ids) > 0
        assert len(phoneme_ids) == len(prosody_features)

    def test_punctuation(self, phoneme_id_map):
        """Test sentence with punctuation."""
        text = "こんにちは、世界！"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        assert len(phoneme_ids) > 0
        assert len(phoneme_ids) == len(prosody_features)

    def test_numbers(self, phoneme_id_map):
        """Test sentence with numbers."""
        text = "今日は2024年1月8日です"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        assert len(phoneme_ids) > 0
        assert len(phoneme_ids) == len(prosody_features)

    def test_mixed_scripts(self, phoneme_id_map):
        """Test sentence with mixed scripts (hiragana, katakana, kanji)."""
        text = "私はコーヒーが好きです"
        phoneme_ids, prosody_features = text_to_phoneme_ids_and_prosody(
            text, phoneme_id_map
        )

        assert len(phoneme_ids) > 0
        assert len(phoneme_ids) == len(prosody_features)


class TestPhonemeIdMapCompatibility:
    """Tests to ensure phoneme_id_map from config.json works."""

    def test_config_phoneme_id_map_format(self):
        """Test that get_japanese_id_map returns correct format."""
        phoneme_id_map = get_phoneme_id_map("ja")

        # Should be a dictionary
        assert isinstance(phoneme_id_map, dict)

        # Each value should be a list of integers
        for symbol, ids in phoneme_id_map.items():
            assert isinstance(ids, list)
            assert all(isinstance(i, int) for i in ids)

    def test_required_symbols_present(self):
        """Test that required symbols are in the map."""
        phoneme_id_map = get_phoneme_id_map("ja")

        # BOS and EOS should be present
        assert "^" in phoneme_id_map  # BOS
        assert "$" in phoneme_id_map  # EOS
        assert "_" in phoneme_id_map  # pause

        # Basic vowels
        for vowel in ["a", "i", "u", "e", "o"]:
            assert vowel in phoneme_id_map
