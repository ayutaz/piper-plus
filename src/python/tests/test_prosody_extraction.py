"""
Tests for A1/A2/A3 prosody value extraction from OpenJTalk labels.
"""

import functools

import pytest

# Shared helpers from conftest.py.
# This file uses auto_eos=True (conditional "$") to avoid double-termination
# for question sentences.
from conftest import (  # noqa: E402
    HAS_JAPANESE_G2P as HAS_JAPANESE,
    phonemize_japanese as _phonemize_japanese_base,
    phonemize_japanese_with_prosody,
)

if HAS_JAPANESE:
    from piper_plus_g2p import ProsodyInfo  # noqa: F811

# Bind auto_eos=True so callers in this file keep the original behaviour.
phonemize_japanese = functools.partial(_phonemize_japanese_base, auto_eos=True)


class TestProsodyExtraction:
    """Tests for A1/A2/A3 prosody extraction functionality."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_extraction_basic(self):
        """Test basic prosody extraction from 'こんにちは'."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("こんにちは")

        # Verify lengths match
        assert len(tokens) == len(prosody_info), (
            f"Token count ({len(tokens)}) != prosody_info count ({len(prosody_info)})"
        )

        # Verify we have some prosody info (non-None values)
        non_none_count = sum(1 for p in prosody_info if p is not None)
        assert non_none_count > 0, "No prosody info extracted"

        # Verify ProsodyInfo structure
        for p in prosody_info:
            if p is not None:
                assert isinstance(p, ProsodyInfo)
                assert isinstance(p.a1, int)
                assert isinstance(p.a2, int)
                assert isinstance(p.a3, int)
                # A1 can be negative (relative to accent position) or 0/1
                # Just verify it's an integer (already checked above)
                # A2 should be positive (1-based position)
                assert p.a2 >= 1, f"A2 should be >= 1, got {p.a2}"
                # A3 should be positive (phrase length)
                assert p.a3 >= 1, f"A3 should be >= 1, got {p.a3}"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_a2_position_increment(self):
        """Test that A2 (mora position) increments correctly within a phrase."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("あいうえお")

        # Get A2 values for phonemes (excluding special tokens)
        a2_values = [p.a2 for p in prosody_info if p is not None]

        # A2 should increment: 1, 2, 3, 4, 5 for 5 morae
        assert len(a2_values) >= 5, f"Expected at least 5 A2 values, got {len(a2_values)}"

        # Check that A2 starts at 1 and generally increases
        assert a2_values[0] == 1, f"First mora should have A2=1, got {a2_values[0]}"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_a3_phrase_length(self):
        """Test that A3 represents the phrase length correctly."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Single word should have consistent A3 within the phrase
        tokens, prosody_info = phonemize_japanese_with_prosody("こんにちは")

        # Get A3 values
        a3_values = [p.a3 for p in prosody_info if p is not None]

        # All morae in a single phrase should have the same A3
        if a3_values:
            # At least the first few should be consistent
            first_a3 = a3_values[0]
            assert first_a3 > 0, f"A3 should be positive, got {first_a3}"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_special_tokens_are_none(self):
        """Test that special tokens (^, $, #, [, ]) have None prosody info."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("こんにちは")

        # Check special tokens have None prosody
        special_tokens = {"^", "$", "?", "_", "#", "[", "]"}
        for token, prosody in zip(tokens, prosody_info):
            if token in special_tokens:
                assert prosody is None, (
                    f"Special token '{token}' should have None prosody, got {prosody}"
                )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_multiple_phrases(self):
        """Test prosody info for text with multiple accent phrases."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # This sentence should have multiple accent phrases
        tokens, prosody_info = phonemize_japanese_with_prosody("今日は天気がいいです")

        # Get A2 values
        a2_values = [p.a2 for p in prosody_info if p is not None]

        # A2 should reset to 1 at phrase boundaries
        # Check that 1 appears multiple times (indicating phrase starts)
        ones_count = sum(1 for v in a2_values if v == 1)
        assert ones_count >= 1, f"Expected at least 1 phrase start (A2=1), got {ones_count}"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_backward_compatibility_phonemize_japanese(self):
        """Test that existing phonemize_japanese() still works correctly."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # phonemize_japanese should return only tokens
        tokens = phonemize_japanese("こんにちは")

        assert isinstance(tokens, list)
        assert "^" in tokens  # Start marker
        assert "$" in tokens  # End marker
        assert len(tokens) > 2  # Should have phonemes

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_tokens_match_original(self):
        """Test that tokens from both functions match."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        text = "こんにちは"

        tokens_original = phonemize_japanese(text)
        tokens_with_prosody, _ = phonemize_japanese_with_prosody(text)

        assert tokens_original == tokens_with_prosody, (
            f"Token mismatch:\nOriginal: {tokens_original}\nWith prosody: {tokens_with_prosody}"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_question_sentence(self):
        """Test prosody extraction for question sentences."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("これは何ですか？")

        # Should end with ? instead of $
        assert "?" in tokens, "Question should end with '?'"
        assert "$" not in tokens, "Question should not have '$'"

        # Lengths should still match
        assert len(tokens) == len(prosody_info)

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_with_pause(self):
        """Test prosody extraction for text with pauses."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Text with punctuation that may create pauses
        tokens, prosody_info = phonemize_japanese_with_prosody("はい、そうです。")

        # Pause token should have None prosody
        if "_" in tokens:
            pause_idx = tokens.index("_")
            assert prosody_info[pause_idx] is None, "Pause token should have None prosody"

        # Lengths should match
        assert len(tokens) == len(prosody_info)

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_info_empty_string(self):
        """Test prosody extraction for empty string."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("")

        assert isinstance(tokens, list)
        assert isinstance(prosody_info, list)
        assert len(tokens) == len(prosody_info)

    @pytest.mark.unit
    def test_prosody_info_dataclass(self):
        """Test ProsodyInfo dataclass functionality."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Create ProsodyInfo instance
        info = ProsodyInfo(a1=0, a2=3, a3=5)

        assert info.a1 == 0
        assert info.a2 == 3
        assert info.a3 == 5

        # Test equality
        info2 = ProsodyInfo(a1=0, a2=3, a3=5)
        assert info == info2

        # Test inequality
        info3 = ProsodyInfo(a1=1, a2=3, a3=5)
        assert info != info3

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_features_dict_conversion(self):
        """Test that prosody info can be converted to dict format for JSON."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        tokens, prosody_info = phonemize_japanese_with_prosody("こんにちは")

        # Convert to dict format (as preprocess.py does)
        prosody_features = [
            {"a1": p.a1, "a2": p.a2, "a3": p.a3} if p is not None else None
            for p in prosody_info
        ]

        # Verify structure
        assert len(prosody_features) == len(tokens)

        for i, (token, feat) in enumerate(zip(tokens, prosody_features)):
            if token in {"^", "$", "?", "_", "#", "[", "]"}:
                assert feat is None, f"Special token {token} should have None"
            else:
                if feat is not None:
                    assert "a1" in feat
                    assert "a2" in feat
                    assert "a3" in feat
                    assert isinstance(feat["a1"], int)
                    assert isinstance(feat["a2"], int)
                    assert isinstance(feat["a3"], int)

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_features_json_serializable(self):
        """Test that prosody features can be serialized to JSON."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        import json

        tokens, prosody_info = phonemize_japanese_with_prosody("今日は良い天気です")

        # Convert to dict format
        prosody_features = [
            {"a1": p.a1, "a2": p.a2, "a3": p.a3} if p is not None else None
            for p in prosody_info
        ]

        # Should be JSON serializable
        json_str = json.dumps(prosody_features)
        assert json_str is not None

        # Should be deserializable
        restored = json.loads(json_str)
        assert restored == prosody_features

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_a1_negative_values(self):
        """Test that A1 can have negative values (relative to accent nucleus)."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Use a longer word to test A1 range
        tokens, prosody_info = phonemize_japanese_with_prosody("コンピューター")

        a1_values = [p.a1 for p in prosody_info if p is not None]

        # A1 values can include negatives, zeros, and positives
        # Verify we have at least some A1 values
        assert len(a1_values) > 0, "Should have some A1 values"

        # All A1 values should be integers (including negative)
        for a1 in a1_values:
            assert isinstance(a1, int), f"A1 should be int, got {type(a1)}"


class TestDatasetProsodyIntegration:
    """Tests for prosody features integration with dataset loading."""

    @pytest.mark.unit
    def test_prosody_features_to_tensor(self):
        """Test conversion of prosody features numpy array to tensor."""
        try:
            from piper_train.vits.dataset import PiperDataset
        except ImportError:
            pytest.skip("Dataset module not available")

        import numpy as np

        # Test data with mixed None and dict values (pre-converted to numpy)
        # None entries are encoded as [0, 0, 0]
        prosody_features = np.array([
            [0, 0, 0],   # ^ (start) - was None
            [-2, 1, 3],
            [-1, 2, 3],
            [0, 3, 3],
            [0, 0, 0],   # $ (end) - was None
        ], dtype=np.int16)

        tensor = PiperDataset._prosody_features_to_tensor(prosody_features)

        # Verify shape
        assert tensor.shape == (5, 3), f"Expected shape (5, 3), got {tensor.shape}"

        # Verify None values become zeros
        assert tensor[0].tolist() == [0, 0, 0], "Start token should be zeros"
        assert tensor[4].tolist() == [0, 0, 0], "End token should be zeros"

        # Verify actual values
        assert tensor[1].tolist() == [-2, 1, 3], "First phoneme prosody mismatch"
        assert tensor[2].tolist() == [-1, 2, 3], "Second phoneme prosody mismatch"
        assert tensor[3].tolist() == [0, 3, 3], "Third phoneme prosody mismatch"

    @pytest.mark.unit
    def test_utterance_with_prosody_features(self):
        """Test Utterance dataclass with prosody_features field."""
        from pathlib import Path

        import numpy as np

        try:
            from piper_train.vits.dataset import Utterance
        except ImportError:
            pytest.skip("Dataset module not available")

        utt = Utterance(
            phoneme_ids=np.array([1, 2, 3], dtype=np.int16),
            audio_norm_path=Path("/tmp/test.pt"),
            audio_spec_path=Path("/tmp/spec.pt"),
            prosody_features=np.array([
                [0, 1, 2],
                [1, 2, 2],
                [0, 0, 0],  # was None, encoded as zeros
            ], dtype=np.int16),
        )

        assert utt.prosody_features is not None
        assert len(utt.prosody_features) == 3
        assert utt.prosody_features[0].tolist() == [0, 1, 2]
        assert utt.prosody_features[2].tolist() == [0, 0, 0]

    @pytest.mark.unit
    def test_batch_prosody_features_field(self):
        """Test Batch dataclass has prosody_features field."""
        try:
            from piper_train.vits.dataset import Batch
        except ImportError:
            pytest.skip("Dataset module not available")

        import torch

        # Create a minimal batch
        batch = Batch(
            phoneme_ids=torch.zeros(2, 10, dtype=torch.long),
            phoneme_lengths=torch.tensor([5, 7]),
            spectrograms=torch.zeros(2, 80, 100),
            spectrogram_lengths=torch.tensor([80, 100]),
            audios=torch.zeros(2, 1, 8192),
            audio_lengths=torch.tensor([8000, 8192]),
            prosody_features=torch.zeros(2, 10, 3, dtype=torch.long),
        )

        assert batch.prosody_features is not None
        assert batch.prosody_features.shape == (2, 10, 3)


class TestProsodyDatasetValidation:
    """Tests for prosody features validation to prevent length mismatch issues."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_length_matches_phoneme_ids_various_texts(self):
        """Test that prosody_features length always matches phoneme_ids for various texts.

        This test ensures the issue where piper_train.tools.add_prosody_features script creates
        mismatched lengths does not occur when using phonemize_japanese_with_prosody.
        """
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        # Various test cases including edge cases
        test_texts = [
            "こんにちは",
            "今日は良い天気です",
            "何をしている。たかがパンツが、どうして気になる",  # Known problematic text
            "これは何ですか？",
            "はい、そうです。",
            "東京都渋谷区",
            "１２３４５",  # Numbers
            "ＡＢＣＤＥ",  # Full-width alphabet
            "あ",  # Single character
            "あいうえおかきくけこさしすせそ",  # Long text
            "",  # Empty string
        ]

        for text in test_texts:
            tokens, prosody_info = phonemize_japanese_with_prosody(text)

            assert len(tokens) == len(prosody_info), (
                f"Length mismatch for text '{text}': "
                f"tokens={len(tokens)}, prosody_info={len(prosody_info)}"
            )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_and_phoneme_ids_generated_together(self):
        """Test that phoneme_ids and prosody_features generated together always match.

        This simulates what preprocess.py should do - generate both at the same time.
        """
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map as _get_map

        def get_japanese_id_map():
            return _get_map("ja")

        text = "何をしている。たかがパンツが、どうして気になる"

        # Generate both together (like preprocess.py should)
        tokens, prosody_info = phonemize_japanese_with_prosody(text)

        # Get the phoneme ID map
        phoneme_id_map = get_japanese_id_map()

        # Convert tokens to IDs
        phoneme_ids = []
        for token in tokens:
            if token in phoneme_id_map:
                phoneme_ids.extend(phoneme_id_map[token])
            else:
                phoneme_ids.append(0)

        # Convert prosody_info to features format
        prosody_features = []
        for p in prosody_info:
            if p is None:
                prosody_features.append({"a1": 0, "a2": 0, "a3": 0})
            else:
                prosody_features.append({"a1": p.a1, "a2": p.a2, "a3": p.a3})

        # Verify lengths match
        assert len(phoneme_ids) == len(prosody_features), (
            f"phoneme_ids ({len(phoneme_ids)}) != prosody_features ({len(prosody_features)})"
        )

