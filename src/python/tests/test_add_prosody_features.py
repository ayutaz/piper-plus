"""
Tests for piper_train.tools.add_prosody_features preprocessing script.

This module tests the preprocessing script that adds prosody_features and
updates phoneme_ids with new token system (Issue #204, #207).
"""

import json
import pytest


# Japanese imports are optional
try:
    import pyopenjtalk  # noqa: F401

    from piper_plus_g2p.japanese import JapanesePhonemizer
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map

    def get_japanese_id_map():
        return get_phoneme_id_map("ja")

    HAS_JAPANESE = True
except ImportError:
    HAS_JAPANESE = False


# Import the function under test (internal module - ImportError should fail the test)
from piper_train.tools.add_prosody_features import process_utterance

HAS_SCRIPT = True


class TestProcessUtterance:
    """Tests for process_utterance function."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_basic_text_processing(self):
        """Test basic text processing returns expected structure."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "こんにちは", "audio_path": "/test/audio.wav"}
        result = process_utterance(item)

        assert result is not None
        assert "phoneme_ids" in result
        assert "prosody_features" in result
        assert "prosody_ids" in result
        assert isinstance(result["phoneme_ids"], list)
        assert isinstance(result["prosody_features"], list)
        assert result["prosody_ids"] == []

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_empty_text_returns_none(self):
        """Test empty text returns None."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "", "audio_path": "/test/audio.wav"}
        result = process_utterance(item)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_missing_text_returns_none(self):
        """Test missing text field returns None."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"audio_path": "/test/audio.wav"}
        result = process_utterance(item)
        assert result is None

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_phoneme_ids_prosody_features_length_match(self):
        """Test phoneme_ids and prosody_features have same length."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        test_texts = [
            "こんにちは",
            "今日は良い天気です",
            "これは何ですか？",
            "さんぽ",  # Contains N before p
            "ぎんこう",  # Contains N before k
        ]

        for text in test_texts:
            item = {"text": text}
            result = process_utterance(item)

            assert result is not None, f"Failed for text: {text}"
            assert len(result["phoneme_ids"]) == len(result["prosody_features"]), (
                f"Length mismatch for text '{text}': "
                f"phoneme_ids={len(result['phoneme_ids'])}, "
                f"prosody_features={len(result['prosody_features'])}"
            )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_prosody_features_structure(self):
        """Test prosody_features have correct structure."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "こんにちは"}
        result = process_utterance(item)

        assert result is not None

        for i, feat in enumerate(result["prosody_features"]):
            if feat is not None:
                assert isinstance(feat, dict), f"Index {i}: expected dict, got {type(feat)}"
                assert "a1" in feat, f"Index {i}: missing 'a1'"
                assert "a2" in feat, f"Index {i}: missing 'a2'"
                assert "a3" in feat, f"Index {i}: missing 'a3'"
                assert isinstance(feat["a1"], int), f"Index {i}: a1 not int"
                assert isinstance(feat["a2"], int), f"Index {i}: a2 not int"
                assert isinstance(feat["a3"], int), f"Index {i}: a3 not int"

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_original_fields_preserved(self):
        """Test original fields are preserved in output."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {
            "text": "こんにちは",
            "audio_path": "/test/audio.wav",
            "speaker_id": 5,
            "custom_field": "value",
        }
        result = process_utterance(item)

        assert result is not None
        assert result["text"] == "こんにちは"
        assert result["audio_path"] == "/test/audio.wav"
        assert result["speaker_id"] == 5
        assert result["custom_field"] == "value"


class TestNPhonemeVariants:
    """Tests for N phoneme variant handling (Issue #207)."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_bilabial_p(self):
        """Test N_m variant before p (bilabial)."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # さんぽ: ん before p → N_m (0xE019)
        item = {"text": "さんぽ"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_m_id = id_map.get("\ue019", [None])[0]  # N_m PUA character

        assert n_m_id in result["phoneme_ids"], (
            f"N_m (ID={n_m_id}) not found in phoneme_ids: {result['phoneme_ids']}"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_bilabial_b(self):
        """Test N_m variant before b (bilabial)."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # しんぶん: first ん before b → N_m
        item = {"text": "しんぶん"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_m_id = id_map.get("\ue019", [None])[0]

        assert n_m_id in result["phoneme_ids"], (
            f"N_m (ID={n_m_id}) not found for しんぶん"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_alveolar(self):
        """Test N_n variant before alveolar consonants."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # あんない: ん before n → N_n (0xE01A)
        item = {"text": "あんない"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_n_id = id_map.get("\ue01a", [None])[0]

        assert n_n_id in result["phoneme_ids"], (
            f"N_n (ID={n_n_id}) not found for あんない"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_velar_k(self):
        """Test N_ng variant before k (velar)."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # ぎんこう: ん before k → N_ng (0xE01B)
        item = {"text": "ぎんこう"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_ng_id = id_map.get("\ue01b", [None])[0]

        assert n_ng_id in result["phoneme_ids"], (
            f"N_ng (ID={n_ng_id}) not found for ぎんこう"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_velar_g(self):
        """Test N_ng variant before g (velar)."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # てんごく: ん before g → N_ng
        item = {"text": "てんごく"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_ng_id = id_map.get("\ue01b", [None])[0]

        assert n_ng_id in result["phoneme_ids"], (
            f"N_ng (ID={n_ng_id}) not found for てんごく"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_at_end_uvular(self):
        """Test N_uvular variant at phrase end."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # ほん: ん at end → N_uvular (0xE01C)
        item = {"text": "ほん"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_uvular_id = id_map.get("\ue01c", [None])[0]

        assert n_uvular_id in result["phoneme_ids"], (
            f"N_uvular (ID={n_uvular_id}) not found for ほん"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_n_before_vowel_uvular(self):
        """Test N_uvular variant before vowel."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # れんあい: ん before a → N_uvular
        item = {"text": "れんあい"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        n_uvular_id = id_map.get("\ue01c", [None])[0]

        assert n_uvular_id in result["phoneme_ids"], (
            f"N_uvular (ID={n_uvular_id}) not found for れんあい"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_no_generic_n_remaining(self):
        """Test that no generic 'N' remains after processing."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # All N should be converted to variants
        test_texts = ["さんぽ", "しんぶん", "あんない", "ぎんこう", "ほん", "れんあい"]
        id_map = get_japanese_id_map()
        generic_n_id = id_map.get("N", [None])[0]

        for text in test_texts:
            item = {"text": text}
            result = process_utterance(item)

            if result is not None and generic_n_id is not None:
                assert generic_n_id not in result["phoneme_ids"], (
                    f"Generic N (ID={generic_n_id}) found in phoneme_ids for '{text}'"
                )


class TestQuestionMarkers:
    """Tests for question marker handling (Issue #204)."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_generic_question_marker(self):
        """Test generic question marker ?"""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "本当？"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        question_id = id_map.get("?", [None])[0]

        assert question_id in result["phoneme_ids"], (
            f"Question marker (ID={question_id}) not found"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_emphatic_question_marker(self):
        """Test emphatic question marker ?!"""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "本当?!"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        emphatic_id = id_map.get("\ue016", [None])[0]

        assert emphatic_id in result["phoneme_ids"], (
            f"Emphatic question marker ?! (ID={emphatic_id}) not found"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_neutral_question_marker(self):
        """Test neutral/rhetorical question marker ?."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "そうですか?."}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        neutral_id = id_map.get("\ue017", [None])[0]

        assert neutral_id in result["phoneme_ids"], (
            f"Neutral question marker ?. (ID={neutral_id}) not found"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_tag_question_marker(self):
        """Test tag question marker ?~"""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "行くよね?~"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        tag_id = id_map.get("\ue018", [None])[0]

        assert tag_id in result["phoneme_ids"], (
            f"Tag question marker ?~ (ID={tag_id}) not found"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_japanese_style_emphatic_question(self):
        """Test Japanese-style emphatic question ！？"""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "本当！？"}
        result = process_utterance(item)

        assert result is not None
        id_map = get_japanese_id_map()
        emphatic_id = id_map.get("\ue016", [None])[0]

        assert emphatic_id in result["phoneme_ids"], (
            f"Japanese emphatic ！？ (ID={emphatic_id}) not found"
        )


class TestPhonemeIdMap:
    """Tests for phoneme ID map correctness."""

    @pytest.mark.unit
    @pytest.mark.japanese
    def test_id_map_has_all_new_tokens(self):
        """Test ID map contains all new tokens."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        id_map = get_japanese_id_map()

        # Question markers (Issue #204)
        assert "?" in id_map, "Missing generic question marker"
        assert "\ue016" in id_map, "Missing ?! (emphatic question)"
        assert "\ue017" in id_map, "Missing ?. (neutral question)"
        assert "\ue018" in id_map, "Missing ?~ (tag question)"

        # N variants (Issue #207)
        assert "\ue019" in id_map, "Missing N_m"
        assert "\ue01a" in id_map, "Missing N_n"
        assert "\ue01b" in id_map, "Missing N_ng"
        assert "\ue01c" in id_map, "Missing N_uvular"

    @pytest.mark.unit
    @pytest.mark.japanese
    def test_id_map_num_symbols(self):
        """Test ID map has correct number of symbols."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        id_map = get_japanese_id_map()

        # 10 special tokens + 55 phonemes = 65
        assert len(id_map) == 65, f"Expected 65 symbols, got {len(id_map)}"

    @pytest.mark.unit
    @pytest.mark.japanese
    def test_id_map_unique_ids(self):
        """Test all IDs in the map are unique."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        id_map = get_japanese_id_map()

        # Each token maps to a list of IDs, extract all IDs
        all_ids = []
        for token, ids in id_map.items():
            all_ids.extend(ids)

        # Check uniqueness
        unique_ids = set(all_ids)
        assert len(all_ids) == len(unique_ids), (
            f"Duplicate IDs found: {len(all_ids)} total, {len(unique_ids)} unique"
        )

    @pytest.mark.unit
    @pytest.mark.japanese
    def test_id_map_ids_are_sequential(self):
        """Test IDs are sequential from 0 to num_symbols-1."""
        if not HAS_JAPANESE:
            pytest.skip("Japanese phonemizer not available")

        id_map = get_japanese_id_map()

        all_ids = []
        for token, ids in id_map.items():
            all_ids.extend(ids)

        sorted_ids = sorted(all_ids)
        expected_ids = list(range(len(id_map)))

        assert sorted_ids == expected_ids, (
            f"IDs not sequential. Expected 0-{len(id_map)-1}, got {sorted_ids[:5]}...{sorted_ids[-5:]}"
        )


class TestResultJsonSerialization:
    """Tests for JSON serialization of results."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_result_is_json_serializable(self):
        """Test result can be serialized to JSON."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "こんにちは", "speaker_id": 0}
        result = process_utterance(item)

        assert result is not None

        # Should not raise
        json_str = json.dumps(result, ensure_ascii=False)
        assert json_str is not None

        # Should be deserializable
        restored = json.loads(json_str)
        assert restored["phoneme_ids"] == result["phoneme_ids"]
        assert restored["prosody_features"] == result["prosody_features"]

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_result_matches_jsonl_format(self):
        """Test result matches expected JSONL format for training."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {
            "text": "今日は良い天気です",
            "speaker_id": 3,
            "audio_spec_path": "/data/cache/audio.pt",
        }
        result = process_utterance(item)

        assert result is not None

        # Required fields for training
        assert "phoneme_ids" in result
        assert "prosody_features" in result
        assert isinstance(result["phoneme_ids"], list)
        assert isinstance(result["prosody_features"], list)
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

        # Preserved fields
        assert result["speaker_id"] == 3
        assert result["audio_spec_path"] == "/data/cache/audio.pt"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_single_character(self):
        """Test single character text."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "あ"}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) > 0
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_long_text(self):
        """Test long text processing."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        long_text = "今日は良い天気です。" * 10
        item = {"text": long_text}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) > 100
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_text_with_punctuation(self):
        """Test text with various punctuation."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "はい、そうです。いいえ、違います！"}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_text_with_numbers(self):
        """Test text with numbers."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "2024年1月1日"}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_text_with_mixed_scripts(self):
        """Test text with mixed scripts."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        item = {"text": "Hello こんにちは World"}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) == len(result["prosody_features"])

    @pytest.mark.unit
    @pytest.mark.japanese
    @pytest.mark.requires_openjtalk
    def test_known_problematic_text(self):
        """Test known problematic text that caused length mismatch."""
        if not HAS_JAPANESE or not HAS_SCRIPT:
            pytest.skip("Japanese phonemizer or script not available")

        # This text was known to cause issues
        item = {"text": "何をしている。たかがパンツが、どうして気になる"}
        result = process_utterance(item)

        assert result is not None
        assert len(result["phoneme_ids"]) == len(result["prosody_features"]), (
            f"Length mismatch: phoneme_ids={len(result['phoneme_ids'])}, "
            f"prosody_features={len(result['prosody_features'])}"
        )
