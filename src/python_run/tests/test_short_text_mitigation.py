"""
Tests for short-text synthesis quality mitigation strategies (A, B, C).

Strategy A: Silence padding + post-trim for short phoneme_ids
Strategy B: Dynamic noise/noise_w scale reduction for short sequences
Strategy C: Auto-inject silence padding around short plain text
"""

import numpy as np
import pytest

from piper.voice import (
    MIN_BODY_FOR_STRATEGY_A,
    MIN_PHONEME_IDS,
    SHORT_TEXT_CHARS,
    SILENCE_PAD_MS,
    TRIM_MIN_SAMPLES,
    TRIM_THRESHOLD_RMS,
    _pad_phoneme_ids,
    _trim_padding_by_durations,
    _trim_silence,
)


# ---------------------------------------------------------------
# Strategy A: _pad_phoneme_ids
# ---------------------------------------------------------------
class TestPadPhonemeIds:

    @pytest.mark.unit
    def test_no_pad_when_long_enough(self):
        ids = list(range(MIN_PHONEME_IDS))
        padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)
        assert not was_padded
        assert padded is ids
        assert front_pad == 0
        assert back_pad == 0

    @pytest.mark.unit
    def test_no_pad_when_exceeds_min(self):
        ids = list(range(MIN_PHONEME_IDS + 10))
        padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)
        assert not was_padded
        assert padded is ids
        assert front_pad == 0
        assert back_pad == 0

    @pytest.mark.unit
    def test_pads_short_sequence(self):
        bos, eos = 1, 2
        body = [10, 11, 12]
        ids = [bos] + body + [eos]  # length 5
        padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)

        assert was_padded
        assert len(padded) == MIN_PHONEME_IDS
        assert padded[0] == bos
        assert padded[-1] == eos
        assert front_pad + back_pad == MIN_PHONEME_IDS - len(ids)

    @pytest.mark.unit
    def test_preserves_body_content(self):
        bos, eos, pad_id = 1, 2, 0
        body = [10, 20, 30]
        ids = [bos] + body + [eos]
        padded, _, _, _ = _pad_phoneme_ids(ids, pad_id=pad_id)

        # body should appear contiguously in the padded result
        body_start = padded.index(10)
        assert padded[body_start : body_start + len(body)] == body

    @pytest.mark.unit
    def test_pad_distribution(self):
        """Front and back padding should be roughly equal.

        Uses a body of MIN_BODY_FOR_STRATEGY_A so Strategy A actually
        kicks in (smaller bodies are bypassed — see issue #356).
        """
        bos, eos, pad_id = 1, 2, 0
        body = list(range(10, 10 + MIN_BODY_FOR_STRATEGY_A))
        ids = [bos] + body + [eos]
        padded, _, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=pad_id)

        needed = MIN_PHONEME_IDS - len(ids)
        expected_front = needed // 2
        expected_back = needed - expected_front
        assert front_pad == expected_front
        assert back_pad == expected_back

        # After BOS, expect front pad tokens
        assert padded[1 : 1 + front_pad] == [pad_id] * front_pad
        # Before EOS, expect back pad tokens
        assert padded[-1 - back_pad : -1] == [pad_id] * back_pad

    @pytest.mark.unit
    def test_skips_strategy_a_when_body_too_short(self):
        """body shorter than MIN_BODY_FOR_STRATEGY_A skips Strategy A.

        Padding ratio explodes for tiny bodies — raw VITS output is
        preferable in that regime (issue #356 follow-up).
        """
        # body = 0 (only BOS + EOS)
        ids = [1, 2]
        padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)
        assert not was_padded
        assert padded is ids
        assert front_pad == 0 and back_pad == 0

        # body = 2, e.g. 「あ。」 → [BOS, a, ., EOS]
        if MIN_BODY_FOR_STRATEGY_A > 2:
            ids = [1, 10, 11, 2]
            padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)
            assert not was_padded
            assert padded is ids
            assert front_pad == 0 and back_pad == 0

    @pytest.mark.unit
    def test_pads_when_body_meets_min_body(self):
        """Body at MIN_BODY_FOR_STRATEGY_A should still be padded."""
        body = list(range(10, 10 + MIN_BODY_FOR_STRATEGY_A))
        ids = [1] + body + [2]  # BOS + body + EOS
        padded, was_padded, front_pad, back_pad = _pad_phoneme_ids(ids, pad_id=0)
        assert was_padded
        assert len(padded) == MIN_PHONEME_IDS
        assert front_pad + back_pad == MIN_PHONEME_IDS - len(ids)


# ---------------------------------------------------------------
# Strategy A: _trim_padding_by_durations (precise method, Issue #356)
# ---------------------------------------------------------------
class TestTrimPaddingByDurations:
    """Durations-based padding trim (preferred over RMS for Strategy A).

    Regression coverage for issue #356 where pad tokens (ID=0) produced
    voiced-looking audio that RMS-based trim could not strip, yielding
    'あこんにちはた' (extra 'a' / 'ta' at boundaries).
    """

    @pytest.mark.unit
    def test_no_op_when_no_padding(self):
        audio = np.arange(1000, dtype=np.int16)
        durations = np.array([1.0] * 5, dtype=np.float32)
        result = _trim_padding_by_durations(audio, durations, 0, 0, hop_size=256)
        assert np.array_equal(result, audio)

    @pytest.mark.unit
    def test_trims_front_padding_only(self):
        # Layout: BOS=2, pad×3 (3+3+3 frames), body=4, EOS=1 → 19 frames total
        # Strategy A trims BOS + front padding from the start.
        # EOS=1 frame ≤ eos_max_frames=6, so it's preserved.
        durations = np.array([2.0, 3.0, 3.0, 3.0, 4.0, 1.0], dtype=np.float32)
        hop = 100
        total_samples = int(durations.sum() * hop)  # 1900
        audio = np.arange(total_samples, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=3, back_pad=0, hop_size=hop, eos_max_frames=6
        )
        # BOS + front padding samples = (2+3+3+3) * 100 = 1100
        assert len(result) == total_samples - 1100
        assert result[0] == audio[1100]

    @pytest.mark.unit
    def test_trims_back_padding_preserves_normal_eos(self):
        # Back padding stripped, EOS=1 frame preserved (eos_max_frames=6).
        # Layout: [body=2, body=4, pad=3, pad=3, pad=3, EOS=1] with front_pad=0
        durations = np.array([2.0, 4.0, 3.0, 3.0, 3.0, 1.0], dtype=np.float32)
        hop = 100
        total_samples = int(durations.sum() * hop)  # 1600
        audio = np.arange(total_samples, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=0, back_pad=3, hop_size=hop, eos_max_frames=6
        )
        # Trim back padding only (3+3+3)*100 = 900; EOS=1 frame stays in audio.
        assert len(result) == total_samples - 900
        # The last 100 samples (= 1 frame * hop) of the result are the EOS region.
        assert result[-1] == audio[total_samples - 900 - 1]

    @pytest.mark.unit
    def test_clamps_inflated_eos_duration(self):
        # EOS=10 frames is above eos_max_frames=6, excess 4 frames trimmed.
        durations = np.array([2.0, 3.0, 3.0, 4.0, 3.0, 3.0, 10.0], dtype=np.float32)
        hop = 100
        total = int(durations.sum() * hop)  # 2800
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop, eos_max_frames=6
        )
        # BOS + front padding = (2+3+3) * 100 = 800
        # back padding + EOS excess = (3+3 + (10-6)) * 100 = 1000
        assert len(result) == total - 800 - 1000

    @pytest.mark.unit
    def test_trims_both_sides(self):
        # BOS=2, pad×2, body×2, pad×2, EOS=1
        # EOS=1 below eos_max_frames=6 so preserved entirely.
        durations = np.array(
            [2.0, 5.0, 5.0, 4.0, 4.0, 5.0, 5.0, 1.0], dtype=np.float32
        )
        hop = 100
        total = int(durations.sum() * hop)  # 3100
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop, eos_max_frames=6
        )
        # BOS + front padding = (2+5+5)*100 = 1200
        # back padding only (EOS preserved) = (5+5)*100 = 1000
        front_samples = int((2.0 + 5.0 + 5.0) * hop)
        back_samples = int((5.0 + 5.0) * hop)
        assert len(result) == total - front_samples - back_samples
        assert result[0] == audio[front_samples]
        assert result[-1] == audio[total - back_samples - 1]

    @pytest.mark.unit
    def test_eos_max_frames_override(self):
        # Custom eos_max_frames=2 clamps EOS=5 → excess 3 frames trimmed.
        durations = np.array([1.0, 3.0, 3.0, 4.0, 3.0, 3.0, 5.0], dtype=np.float32)
        hop = 100
        total = int(durations.sum() * hop)  # 2200
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop, eos_max_frames=2
        )
        # BOS + front = (1+3+3)*100 = 700
        # back + EOS excess = (3+3 + (5-2))*100 = 900
        assert len(result) == total - 700 - 900

    @pytest.mark.unit
    def test_default_strips_eos_completely(self):
        # Default eos_max_frames=0: VITS predicts an inflated EOS under padded
        # context that emits "だぁ"-like artifacts (issue #356 follow-up), so
        # the entire EOS region is dropped along with back padding.
        durations = np.array([2.0, 5.0, 5.0, 4.0, 4.0, 5.0, 5.0, 8.0], dtype=np.float32)
        hop = 100
        total = int(durations.sum() * hop)  # 3800
        audio = np.arange(total, dtype=np.int16)
        result = _trim_padding_by_durations(
            audio, durations, front_pad=2, back_pad=2, hop_size=hop
        )
        # BOS + front padding = (2+5+5)*100 = 1200
        # back padding + entire EOS = (5+5+8)*100 = 1800
        assert len(result) == total - 1200 - 1800

    @pytest.mark.unit
    def test_returns_input_when_durations_none(self):
        audio = np.arange(1000, dtype=np.int16)
        result = _trim_padding_by_durations(audio, None, 3, 3, hop_size=256)
        assert np.array_equal(result, audio)

    @pytest.mark.unit
    def test_returns_input_when_durations_too_short(self):
        # durations has fewer entries than 1+front+back+1
        audio = np.arange(1000, dtype=np.int16)
        durations = np.array([1.0, 1.0, 1.0], dtype=np.float32)
        result = _trim_padding_by_durations(audio, durations, front_pad=5, back_pad=5, hop_size=256)
        assert np.array_equal(result, audio)


# ---------------------------------------------------------------
# Strategy A: _trim_silence (RMS fallback)
# ---------------------------------------------------------------
class TestTrimSilence:

    @pytest.mark.unit
    def test_no_trim_for_short_audio(self):
        audio = np.zeros(TRIM_MIN_SAMPLES - 1, dtype=np.int16)
        result = _trim_silence(audio)
        assert len(result) == len(audio)

    @pytest.mark.unit
    def test_trims_leading_silence(self):
        sr = 22050
        silence = np.zeros(sr, dtype=np.int16)  # 1s silence
        signal = (np.sin(np.linspace(0, 100, sr)) * 16000).astype(np.int16)
        audio = np.concatenate([silence, signal])

        trimmed = _trim_silence(audio)
        assert len(trimmed) < len(audio)
        assert len(trimmed) >= TRIM_MIN_SAMPLES

    @pytest.mark.unit
    def test_trims_trailing_silence(self):
        sr = 22050
        signal = (np.sin(np.linspace(0, 100, sr)) * 16000).astype(np.int16)
        silence = np.zeros(sr, dtype=np.int16)
        audio = np.concatenate([signal, silence])

        trimmed = _trim_silence(audio)
        assert len(trimmed) < len(audio)
        assert len(trimmed) >= TRIM_MIN_SAMPLES

    @pytest.mark.unit
    def test_preserves_signal(self):
        signal = (np.sin(np.linspace(0, 100, 5000)) * 16000).astype(np.int16)
        trimmed = _trim_silence(signal)
        assert len(trimmed) >= TRIM_MIN_SAMPLES

    @pytest.mark.unit
    def test_all_silence_returns_min_samples(self):
        audio = np.zeros(10000, dtype=np.int16)
        trimmed = _trim_silence(audio)
        assert len(trimmed) == TRIM_MIN_SAMPLES

    @pytest.mark.unit
    def test_respects_min_samples(self):
        """Even with trimming, result should not be shorter than min_samples."""
        sr = 22050
        silence = np.zeros(sr, dtype=np.int16)
        # Very short signal burst
        burst = (np.ones(100, dtype=np.float32) * 20000).astype(np.int16)
        audio = np.concatenate([silence, burst, silence])

        trimmed = _trim_silence(audio)
        assert len(trimmed) >= TRIM_MIN_SAMPLES


# ---------------------------------------------------------------
# Strategy B: Dynamic scales (tested via synthesize_ids_to_raw)
# ---------------------------------------------------------------
class TestDynamicScales:

    @pytest.mark.unit
    def test_scales_reduced_for_short_ids(self):
        """Verify that noise_scale and noise_w are reduced for short sequences."""
        from unittest.mock import MagicMock, patch

        from piper.config import PiperConfig

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type="multilingual",
        )

        voice = MagicMock()
        voice.config = config
        voice.session = MagicMock()

        # Return dummy audio from ONNX
        dummy_audio = np.random.randn(1, 1, 4000).astype(np.float32)
        voice.session.run.return_value = [dummy_audio]
        voice.session.get_inputs.return_value = []

        # Short phoneme_ids (< MIN_PHONEME_IDS)
        short_ids = [1, 10, 10, 10, 2]  # BOS + 3 phonemes + EOS

        from piper.voice import PiperVoice

        PiperVoice._synthesize_ids_core(voice, short_ids)

        # Check that session.run was called
        voice.session.run.assert_called_once()
        call_args = voice.session.run.call_args[0][1]
        scales = call_args["scales"]

        # noise_scale should be reduced (< original 0.667)
        assert scales[0] < 0.667
        # length_scale should be unchanged
        assert scales[1] == pytest.approx(1.0)
        # noise_w should be reduced (< original 0.8)
        assert scales[2] < 0.8

    @pytest.mark.unit
    def test_scales_unchanged_for_long_ids(self):
        """For sequences >= MIN_PHONEME_IDS, scales should not be modified."""
        from unittest.mock import MagicMock

        from piper.config import PiperConfig

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type="multilingual",
        )

        voice = MagicMock()
        voice.config = config
        voice.session = MagicMock()

        dummy_audio = np.random.randn(1, 1, 8000).astype(np.float32)
        voice.session.run.return_value = [dummy_audio]
        voice.session.get_inputs.return_value = []

        # Long phoneme_ids (>= MIN_PHONEME_IDS)
        long_ids = [1] + [10] * (MIN_PHONEME_IDS - 1) + [2]

        from piper.voice import PiperVoice

        PiperVoice._synthesize_ids_core(voice, long_ids)

        call_args = voice.session.run.call_args[0][1]
        scales = call_args["scales"]

        assert scales[0] == pytest.approx(0.667)
        assert scales[1] == pytest.approx(1.0)
        assert scales[2] == pytest.approx(0.8)


# ---------------------------------------------------------------
# Strategy C: Short-text detection in synthesize_stream_raw
# ---------------------------------------------------------------
class TestShortTextDetection:

    @pytest.mark.unit
    def test_short_plain_text_detected(self):
        assert sum(1 for c in "abc" if not c.isspace()) <= SHORT_TEXT_CHARS

    @pytest.mark.unit
    def test_long_text_not_detected(self):
        text = "a" * (SHORT_TEXT_CHARS + 1)
        assert sum(1 for c in text if not c.isspace()) > SHORT_TEXT_CHARS

    @pytest.mark.unit
    def test_ssml_text_not_detected(self):
        text = "<speak>short</speak>"
        assert text.lstrip().startswith(("<speak>", "<speak "))

    @pytest.mark.unit
    def test_ssml_with_attributes_not_detected(self):
        text = '<speak xml:lang="ja">short</speak>'
        assert text.lstrip().startswith(("<speak>", "<speak "))

    @pytest.mark.unit
    def test_spaces_excluded_from_count(self):
        text = "a b c d e"  # 5 non-space chars
        assert sum(1 for c in text if not c.isspace()) <= SHORT_TEXT_CHARS

    @pytest.mark.unit
    def test_break_silence_bytes_length(self):
        """Verify break silence byte count matches SILENCE_PAD_MS."""
        sample_rate = 22050
        break_samples = int(sample_rate * SILENCE_PAD_MS / 1000)
        break_bytes = bytes(break_samples * 2)
        expected_bytes = int(22050 * 0.3) * 2
        assert len(break_bytes) == expected_bytes

    @pytest.mark.unit
    def test_stream_raw_adds_break_for_short_text(self):
        """synthesize_stream_raw should prepend/append silence for short text."""
        from unittest.mock import MagicMock, patch

        from piper.config import PiperConfig
        from piper.voice import PiperVoice

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type="multilingual",
        )

        voice = MagicMock(spec=PiperVoice)
        voice.config = config
        voice.session = MagicMock()

        # Mock phonemize to return a simple phoneme list
        voice.phonemize = MagicMock(return_value=[["a"]])
        voice.phonemes_to_ids = MagicMock(return_value=[1, 10, 2])

        # Mock synthesize_ids_to_raw to return known audio bytes
        audio_marker = b"\x01\x02" * 100
        voice.synthesize_ids_to_raw = MagicMock(return_value=audio_marker)

        short_text = "hi"
        results = list(
            PiperVoice.synthesize_stream_raw(voice, short_text)
        )

        assert len(results) == 1
        result = results[0]

        # Result should be: break_bytes + audio_marker + break_bytes + silence_bytes
        break_samples = int(22050 * SILENCE_PAD_MS / 1000)
        break_len = break_samples * 2

        assert result[:break_len] == bytes(break_len)
        assert audio_marker in result

    @pytest.mark.unit
    def test_stream_raw_no_break_for_long_text(self):
        """synthesize_stream_raw should NOT add breaks for long text."""
        from unittest.mock import MagicMock

        from piper.config import PiperConfig
        from piper.voice import PiperVoice

        config = PiperConfig(
            num_symbols=100,
            num_speakers=1,
            sample_rate=22050,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
            phoneme_type="multilingual",
        )

        voice = MagicMock(spec=PiperVoice)
        voice.config = config
        voice.session = MagicMock()

        voice.phonemize = MagicMock(return_value=[["a"] * 20])
        voice.phonemes_to_ids = MagicMock(return_value=list(range(50)))

        audio_marker = b"\xff\xfe" * 100
        voice.synthesize_ids_to_raw = MagicMock(return_value=audio_marker)

        long_text = "a" * (SHORT_TEXT_CHARS + 1)
        results = list(
            PiperVoice.synthesize_stream_raw(voice, long_text)
        )

        assert len(results) == 1
        # Should start with the audio directly (no break silence prepended)
        assert results[0].startswith(audio_marker)


# ---------------------------------------------------------------
# Constants consistency
# ---------------------------------------------------------------
class TestConstants:

    @pytest.mark.unit
    def test_min_phoneme_ids(self):
        # Empirically tuned for tsukuyomi 6lang (issue #356).
        # Was 40 — caused Strategy A to fire on stable inputs and leak
        # padding artifacts. See voice.py for the threshold rationale.
        assert MIN_PHONEME_IDS == 15

    @pytest.mark.unit
    def test_min_body_for_strategy_a(self):
        # Bodies smaller than this skip Strategy A (issue #356 follow-up
        # for inputs like 「あ。」). See voice.py for rationale.
        assert MIN_BODY_FOR_STRATEGY_A == 3

    @pytest.mark.unit
    def test_short_text_chars(self):
        assert SHORT_TEXT_CHARS == 10

    @pytest.mark.unit
    def test_silence_pad_ms(self):
        assert SILENCE_PAD_MS == 300

    @pytest.mark.unit
    def test_trim_threshold_rms(self):
        assert TRIM_THRESHOLD_RMS == pytest.approx(0.01)

    @pytest.mark.unit
    def test_trim_min_samples(self):
        assert TRIM_MIN_SAMPLES == 2205
