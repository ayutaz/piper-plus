"""Tests for infer_onnx module, specifically the --text functionality."""

import numpy as np
import pytest

from piper_train.infer_onnx import (
    DEFAULT_HOP_SIZE,
    MIN_BODY_FOR_STRATEGY_A,
    MIN_PHONEME_IDS,
    TRIM_EOS_MAX_FRAMES,
    TRIM_MIN_SAMPLES,
    TRIM_THRESHOLD_RMS,
    _adjust_scales_for_short_input,
    _pad_phoneme_ids,
    _trim_padding_by_durations,
    _trim_silence,
    text_to_phoneme_ids_and_prosody,
)
from piper_plus_g2p.encode.id_maps import get_phoneme_id_map


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


class TestPadPhonemeIds:
    """Tests for Strategy A: _pad_phoneme_ids."""

    def test_no_padding_when_long_enough(self):
        """Sequences >= MIN_PHONEME_IDS should not be padded."""
        ids = list(range(MIN_PHONEME_IDS))
        prosody = [None] * MIN_PHONEME_IDS
        result_ids, result_prosody, was_padded, _, _ = _pad_phoneme_ids(ids, prosody)
        assert not was_padded
        assert result_ids == ids
        assert result_prosody == prosody

    def test_padding_applied_when_short(self):
        """Short sequences should be padded to MIN_PHONEME_IDS."""
        # BOS=1, some content, EOS=2
        ids = [1, 10, 20, 30, 2]
        prosody = [None, {"a1": 1, "a2": 2, "a3": 3}, None, None, None]
        result_ids, result_prosody, was_padded, _, _ = _pad_phoneme_ids(ids, prosody)
        assert was_padded
        assert len(result_ids) == MIN_PHONEME_IDS
        assert len(result_prosody) == MIN_PHONEME_IDS

    def test_bos_eos_preserved(self):
        """BOS (first) and EOS (last) tokens should be preserved."""
        # body length must be >= MIN_BODY_FOR_STRATEGY_A for padding to apply.
        ids = [1] + list(range(10, 10 + MIN_BODY_FOR_STRATEGY_A)) + [2]
        result_ids, _, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert was_padded
        assert result_ids[0] == 1  # BOS
        assert result_ids[-1] == 2  # EOS

    def test_padding_is_zero(self):
        """Inserted padding tokens should be 0 (blank/pad)."""
        # body=3 (>= MIN_BODY_FOR_STRATEGY_A) so padding applies.
        ids = [1, 10, 20, 30, 2]
        result_ids, _, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert was_padded
        # Middle content (10, 20, 30) should still be present
        assert 10 in result_ids
        assert 20 in result_ids
        assert 30 in result_ids
        # All padding tokens are 0
        pad_count = result_ids.count(0)
        assert pad_count == MIN_PHONEME_IDS - len(ids)

    def test_prosody_none_passthrough(self):
        """When prosody_features is None, output prosody should also be None."""
        # body=3 (>= MIN_BODY_FOR_STRATEGY_A).
        ids = [1, 10, 20, 30, 2]
        result_ids, result_prosody, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert was_padded
        assert result_prosody is None

    def test_prosody_padded_with_none(self):
        """Prosody padding entries should be None."""
        # body=3 with prosody.
        ids = [1, 10, 20, 30, 2]
        prosody = [
            None,
            {"a1": 1, "a2": 2, "a3": 3},
            {"a1": 4, "a2": 5, "a3": 6},
            {"a1": 7, "a2": 8, "a3": 9},
            None,
        ]
        result_ids, result_prosody, was_padded, _, _ = _pad_phoneme_ids(ids, prosody)
        assert was_padded
        # Count non-None entries -- should still be 3 (the original content)
        non_none = [p for p in result_prosody if p is not None]
        assert len(non_none) == 3

    def test_even_split(self):
        """Padding should be approximately even between front and back."""
        # body=3 so padding applies.
        ids = [1, 10, 20, 30, 2]
        result_ids, _, _, _, _ = _pad_phoneme_ids(ids, None)
        # Find position of first content token 10
        pos = result_ids.index(10)
        front_pads = pos - 1  # subtract BOS
        # Find last content token 30
        last_pos = len(result_ids) - 1 - result_ids[::-1].index(30)
        back_pads = len(result_ids) - last_pos - 2  # subtract content + EOS
        assert abs(front_pads - back_pads) <= 1

    def test_skips_when_body_too_short(self):
        """body shorter than MIN_BODY_FOR_STRATEGY_A skips Strategy A.

        Tiny bodies (e.g. 「あ。」) would have padding-to-body ratio so high
        that pad-token audio dominates over content (issue #356).
        """
        # body = 0 (only BOS + EOS)
        ids = [1, 2]
        result_ids, result_prosody, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert not was_padded
        assert result_ids == ids

        # body = 1
        ids = [1, 10, 2]
        result_ids, _, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert not was_padded
        assert result_ids == ids

        # body = 2 (e.g. 「あ。」 with [BOS, a, ., EOS])
        if MIN_BODY_FOR_STRATEGY_A > 2:
            ids = [1, 10, 11, 2]
            result_ids, _, was_padded, _, _ = _pad_phoneme_ids(ids, None)
            assert not was_padded
            assert result_ids == ids


class TestTrimPaddingByDurations:
    """Tests for Strategy A precise post-trim: _trim_padding_by_durations.

    Mirrors src/python_run/tests/test_short_text_mitigation.py to keep the
    runtime and training implementations behaviourally identical
    (cross-runtime contract — issue #356).
    """

    def test_no_op_when_no_padding(self):
        audio = np.arange(1000, dtype=np.int16)
        durations = np.array([1.0] * 5, dtype=np.float32)
        result = _trim_padding_by_durations(audio, durations, 0, 0, hop_size=256)
        assert np.array_equal(result, audio)

    def test_trims_front_padding_only(self):
        # Layout: BOS=2, pad×3 (3+3+3), body=4, EOS=1 → 19 frames total
        durations = np.array([2.0, 3.0, 3.0, 3.0, 4.0, 1.0], dtype=np.float32)
        hop = 100
        total = int(durations.sum() * hop)  # 1900
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=3, back_pad=0, hop_size=hop, eos_max_frames=6
        )
        # BOS + front padding samples = (2+3+3+3) * 100 = 1100
        assert len(result) == total - 1100

    def test_default_strips_eos_completely(self):
        """Default eos_max_frames=0 drops the entire EOS region (#356)."""
        # body × 2, pads × 2, EOS=8
        durations = np.array(
            [2.0, 5.0, 5.0, 4.0, 4.0, 5.0, 5.0, 8.0], dtype=np.float32
        )
        hop = 100
        total = int(durations.sum() * hop)  # 3800
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop
        )
        # BOS + front padding = (2+5+5)*100 = 1200
        # back padding + entire EOS = (5+5+8)*100 = 1800
        assert len(result) == total - 1200 - 1800

    def test_clamps_inflated_eos_duration(self):
        # EOS=10 frames, eos_max_frames=6 → excess 4 frames trimmed.
        durations = np.array([2.0, 3.0, 3.0, 4.0, 3.0, 3.0, 10.0], dtype=np.float32)
        hop = 100
        total = int(durations.sum() * hop)  # 2800
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop, eos_max_frames=6
        )
        assert len(result) == total - 800 - 1000

    def test_returns_input_when_durations_none(self):
        audio = np.arange(1000, dtype=np.int16)
        result = _trim_padding_by_durations(audio, None, 3, 3, hop_size=256)
        assert np.array_equal(result, audio)

    def test_returns_input_when_durations_too_short(self):
        # durations has fewer entries than 1 + front + back + 1
        audio = np.arange(1000, dtype=np.int16)
        durations = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=5, back_pad=5, hop_size=256
        )
        assert np.array_equal(result, audio)

    def test_returns_input_when_hop_size_zero(self):
        audio = np.arange(1000, dtype=np.int16)
        durations = np.array([1.0] * 8, dtype=np.float32)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=0
        )
        assert np.array_equal(result, audio)

    def test_truncation_matches_int_cast(self):
        """Sample count must use truncation (int()) — cross-runtime contract."""
        # Layout (front_pad=1, back_pad=1, body=3):
        #   [BOS=0.701, pad=0.701, body=2, body=2, body=2, pad=0.703, EOS=0.701]
        # 0.701 / 0.703 chosen to expose float-rounding drift between runtimes.
        durations = np.array(
            [0.701, 0.701, 2.0, 2.0, 2.0, 0.703, 0.701], dtype=np.float32
        )
        hop = 100
        total_samples = len(np.arange(int(durations.sum() * hop), dtype=np.int16))
        audio = np.arange(total_samples, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=1, back_pad=1, hop_size=hop
        )
        # Front trim = int((BOS + pad) * 100)
        #            = int((0.701 + 0.701) * 100) = int(140.2) → 140 (truncated)
        # Back trim  = int(pad * 100) + int(EOS * 100)  (eos_max_frames=0)
        #            = int(0.703 * 100) + int(0.701 * 100)
        #            = 70 + 70 = 140 (each truncated independently)
        # If a runtime mistakenly used round() it would yield 141 + 70 = 141.
        assert len(result) == total_samples - 140 - 140


class TestTrimSilence:
    """Tests for Strategy A post-trim: _trim_silence."""

    def test_no_trim_on_non_silent_audio(self):
        """Audio without leading/trailing silence should not be trimmed."""
        # Generate a 1-second tone at 440 Hz
        sr = 22050
        t = np.linspace(0, 1.0, sr, endpoint=False)
        audio_f = np.sin(2 * np.pi * 440 * t) * 0.5
        audio = (audio_f * 32768).astype(np.int16)
        trimmed = _trim_silence(audio, sample_rate=sr)
        # Should keep most of the audio (allow small trimming at edges)
        assert len(trimmed) >= len(audio) * 0.9

    def test_trim_leading_silence(self):
        """Leading silence should be trimmed."""
        sr = 22050
        silence = np.zeros(sr, dtype=np.int16)  # 1s silence
        t = np.linspace(0, 0.5, sr // 2, endpoint=False)
        tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        audio = np.concatenate([silence, tone])
        trimmed = _trim_silence(audio, sample_rate=sr)
        assert len(trimmed) < len(audio)

    def test_trim_trailing_silence(self):
        """Trailing silence should be trimmed."""
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, endpoint=False)
        tone = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        silence = np.zeros(sr, dtype=np.int16)
        audio = np.concatenate([tone, silence])
        trimmed = _trim_silence(audio, sample_rate=sr)
        assert len(trimmed) < len(audio)

    def test_all_silence_keeps_minimum(self):
        """All-silent audio should keep at least TRIM_MIN_SAMPLES."""
        sr = 22050
        audio = np.zeros(sr, dtype=np.int16)
        trimmed = _trim_silence(audio, sample_rate=sr)
        assert len(trimmed) >= TRIM_MIN_SAMPLES

    def test_short_audio_preserved(self):
        """Audio shorter than window_size should be returned as-is."""
        audio = np.array([100, 200, 300], dtype=np.int16)
        trimmed = _trim_silence(audio)
        np.testing.assert_array_equal(trimmed, audio)

    def test_minimum_length_enforced(self):
        """Trimmed audio should not be shorter than TRIM_MIN_SAMPLES."""
        sr = 22050
        # Very short tone surrounded by silence
        silence_front = np.zeros(sr, dtype=np.int16)
        short_tone = (np.ones(100, dtype=np.float32) * 16000).astype(np.int16)
        silence_back = np.zeros(sr, dtype=np.int16)
        audio = np.concatenate([silence_front, short_tone, silence_back])
        trimmed = _trim_silence(audio, sample_rate=sr)
        assert len(trimmed) >= TRIM_MIN_SAMPLES


class TestAdjustScalesForShortInput:
    """Tests for Strategy B: _adjust_scales_for_short_input."""

    def test_no_adjustment_when_long_enough(self):
        """Scales should not change for sequences >= MIN_PHONEME_IDS."""
        ids = list(range(MIN_PHONEME_IDS))
        ns, ls, nw = _adjust_scales_for_short_input(ids, 0.667, 0.8, 1.0)
        assert ns == pytest.approx(0.667)
        assert ls == pytest.approx(1.0)
        assert nw == pytest.approx(0.8)

    def test_adjustment_applied_when_short(self):
        """Scales should be reduced for short sequences."""
        # Pick a length below MIN_PHONEME_IDS but above the noise_scale floor
        # (ratio = len/MIN >= 0.5 keeps us off the noise_scale clamp).
        ids = list(range(MIN_PHONEME_IDS - 1))
        ns, ls, nw = _adjust_scales_for_short_input(ids, 0.667, 0.8, 1.0)
        # noise_scale should be reduced
        assert ns < 0.667
        # length_scale should be unchanged
        assert ls == pytest.approx(1.0)
        # noise_w should be reduced
        assert nw < 0.8

    def test_noise_scale_floor_at_half(self):
        """noise_scale multiplier should not go below 0.5."""
        ids = [1]  # very short
        ns, _, _ = _adjust_scales_for_short_input(ids, 0.667, 0.8, 1.0)
        # ratio = 1/MIN_PHONEME_IDS, well below 0.5 floor
        assert ns == pytest.approx(0.667 * 0.5)

    def test_noise_w_floor_at_04(self):
        """noise_w multiplier should not go below 0.4."""
        ids = [1]  # very short
        _, _, nw = _adjust_scales_for_short_input(ids, 0.667, 0.8, 1.0)
        # ratio = 1/MIN_PHONEME_IDS, well below 0.4 floor
        assert nw == pytest.approx(0.8 * 0.4)

    def test_length_scale_unchanged(self):
        """length_scale should never be modified."""
        ids = [1]
        _, ls, _ = _adjust_scales_for_short_input(ids, 0.667, 0.8, 2.5)
        assert ls == pytest.approx(2.5)

    def test_ratio_proportional(self):
        """Scale reduction should be proportional to input length."""
        # Pick two lengths in (floor * MIN, MIN) so both stay off the floor.
        # MIN=15: high=12 (ratio 0.8), low=8 (ratio ~0.53)
        high = max(MIN_PHONEME_IDS - 3, 1)
        low = max(MIN_PHONEME_IDS // 2 + 1, 1)
        ids_high = list(range(high))
        ids_low = list(range(low))

        ns_high, _, nw_high = _adjust_scales_for_short_input(
            ids_high, 0.667, 0.8, 1.0
        )
        ns_low, _, nw_low = _adjust_scales_for_short_input(
            ids_low, 0.667, 0.8, 1.0
        )

        # Longer input should have less reduction than shorter input.
        assert ns_high > ns_low
        assert nw_high > nw_low

    def test_empty_input(self):
        """Empty phoneme_ids should use floor values."""
        ns, ls, nw = _adjust_scales_for_short_input([], 0.667, 0.8, 1.0)
        assert ns == pytest.approx(0.667 * 0.5)
        assert ls == pytest.approx(1.0)
        assert nw == pytest.approx(0.8 * 0.4)

    def test_original_len_overrides_phoneme_ids_length(self):
        """When original_len is given, it should be used instead of len(phoneme_ids)."""
        # phoneme_ids has 40 elements (>= MIN_PHONEME_IDS), but original_len=5
        padded_ids = list(range(MIN_PHONEME_IDS))
        ns, ls, nw = _adjust_scales_for_short_input(
            padded_ids, 0.667, 0.8, 1.0, original_len=5
        )
        # ratio = 5/40 = 0.125, clamped to floor -> noise*0.5, noise_w*0.4
        assert ns == pytest.approx(0.667 * 0.5)
        assert nw == pytest.approx(0.8 * 0.4)
        assert ls == pytest.approx(1.0)

    def test_original_len_no_adjustment_when_large(self):
        """When original_len >= MIN_PHONEME_IDS, no adjustment should happen."""
        short_ids = [1, 2, 3]
        ns, ls, nw = _adjust_scales_for_short_input(
            short_ids, 0.667, 0.8, 1.0, original_len=MIN_PHONEME_IDS
        )
        assert ns == pytest.approx(0.667)
        assert ls == pytest.approx(1.0)
        assert nw == pytest.approx(0.8)


class TestStrategyBUsesPrePaddingLength:
    """Integration tests: Strategy B must use the pre-padding length.

    This class tests the bug fix where Strategy B was incorrectly using the
    post-padding length (always MIN_PHONEME_IDS), making the adjustment a no-op.
    """

    def test_strategy_b_uses_original_length_after_padding(self):
        """Strategy B should adjust scales based on original (pre-padding) length.

        Simulates the main() call order: save original_len, then pad (Strategy A),
        then pass original_len to Strategy B.
        """
        # body length must be >= MIN_BODY_FOR_STRATEGY_A for Strategy A to apply.
        short_ids = [1] + list(range(10, 10 + MIN_BODY_FOR_STRATEGY_A)) + [2]
        original_len = len(short_ids)

        # Strategy A: pad
        padded_ids, _, was_padded, _, _ = _pad_phoneme_ids(short_ids, None)
        assert was_padded
        assert len(padded_ids) == MIN_PHONEME_IDS

        # Strategy B with original_len (correct behavior)
        ns, ls, nw = _adjust_scales_for_short_input(
            padded_ids, 0.667, 0.8, 1.0, original_len=original_len
        )
        # Short original_len → ratio well below the noise floors.
        assert ns == pytest.approx(0.667 * 0.5)
        assert nw == pytest.approx(0.8 * 0.4)
        assert ls == pytest.approx(1.0)

    def test_strategy_b_without_original_len_is_noop_after_padding(self):
        """Without original_len, Strategy B is a no-op after padding (the old bug).

        This test documents the buggy behavior to prevent regression.
        """
        short_ids = [1] + list(range(10, 10 + MIN_BODY_FOR_STRATEGY_A)) + [2]

        # Strategy A: pad to MIN_PHONEME_IDS
        padded_ids, _, was_padded, _, _ = _pad_phoneme_ids(short_ids, None)
        assert was_padded
        assert len(padded_ids) == MIN_PHONEME_IDS

        # Strategy B without original_len: uses len(padded_ids) == MIN_PHONEME_IDS
        # so it does NOT adjust (this was the bug)
        ns, ls, nw = _adjust_scales_for_short_input(padded_ids, 0.667, 0.8, 1.0)
        assert ns == pytest.approx(0.667)  # no reduction -- the old bug
        assert nw == pytest.approx(0.8)    # no reduction -- the old bug

    def test_combined_strategy_a_b_varying_lengths(self):
        """Shorter original inputs should get more aggressive scale reduction."""
        # Pick lengths inside the noise_scale floor band so Strategy B actually
        # differentiates them: low close to MIN/2 + 1, high close to MIN - 1.
        low = max(MIN_PHONEME_IDS // 2 + 1, MIN_BODY_FOR_STRATEGY_A + 2)
        high = max(MIN_PHONEME_IDS - 1, low + 1)

        # body length needs >= MIN_BODY_FOR_STRATEGY_A so Strategy A applies.
        ids_low = [1] + list(range(10, 10 + low - 2)) + [2]
        padded_low, _, _, _, _ = _pad_phoneme_ids(ids_low, None)
        ns_low, _, nw_low = _adjust_scales_for_short_input(
            padded_low, 0.667, 0.8, 1.0, original_len=len(ids_low)
        )

        ids_high = [1] + list(range(10, 10 + high - 2)) + [2]
        padded_high, _, _, _, _ = _pad_phoneme_ids(ids_high, None)
        ns_high, _, nw_high = _adjust_scales_for_short_input(
            padded_high, 0.667, 0.8, 1.0, original_len=len(ids_high)
        )

        # Longer original input should have less reduction than shorter.
        assert ns_high > ns_low
        assert nw_high > nw_low

        # Both should be less than the unadjusted values.
        assert ns_high < 0.667
        assert ns_low < 0.667

    def test_no_adjustment_when_original_at_threshold(self):
        """No adjustment when original length is exactly MIN_PHONEME_IDS."""
        ids = list(range(MIN_PHONEME_IDS))
        # No padding happens (already at threshold)
        padded, _, was_padded, _, _ = _pad_phoneme_ids(ids, None)
        assert not was_padded

        ns, ls, nw = _adjust_scales_for_short_input(
            padded, 0.667, 0.8, 1.0, original_len=MIN_PHONEME_IDS
        )
        assert ns == pytest.approx(0.667)
        assert ls == pytest.approx(1.0)
        assert nw == pytest.approx(0.8)
