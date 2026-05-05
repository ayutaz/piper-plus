"""Integration tests for PiperVoice phoneme timing features.

Tests the timing-related methods on PiperVoice:
- has_duration_output property
- _synthesize_ids_core() returning (bytes, ndarray|None, list)
- synthesize_ids_to_raw() backward-compatible wrapper
- synthesize_with_timing() full synthesis with timing

Since we cannot load real ONNX models in unit tests, we mock the
ONNX InferenceSession.  The mock's ``session.run()`` returns both
audio and durations tensors to exercise the timing code path.
"""

from __future__ import annotations

import wave
from io import BytesIO
from unittest.mock import MagicMock

import numpy as np
import pytest

from piper.config import PhonemeType, PiperConfig
from piper.timing import PhonemeTimingInfo, TimingResult
from piper.voice import PiperVoice


# ---------------------------------------------------------------------------
# Helper: build a PiperVoice with a mocked ONNX session
# ---------------------------------------------------------------------------


def _make_mock_voice(
    *,
    num_speakers: int = 1,
    sample_rate: int = 22050,
    has_durations: bool = True,
    phoneme_ids_len: int = 50,
    has_speaker_embedding: bool = False,
    speaker_embedding_dim: int = 256,
) -> PiperVoice:
    """Create a PiperVoice with a mocked ONNX session.

    Parameters
    ----------
    num_speakers:
        Number of speakers in the config.
    sample_rate:
        Audio sample rate for the config and generated audio.
    has_durations:
        Whether the mock model advertises a ``durations`` output.
    phoneme_ids_len:
        Length of the durations tensor returned by session.run().
    has_speaker_embedding:
        Whether the mock model advertises ``speaker_embedding`` /
        ``speaker_embedding_mask`` inputs (regression coverage for issue #385).
    speaker_embedding_dim:
        Embedding dimension reported by the mocked input shape.
    """
    config = PiperConfig(
        num_symbols=100,
        num_speakers=num_speakers,
        sample_rate=sample_rate,
        length_scale=1.0,
        noise_scale=0.667,
        noise_w=0.8,
        phoneme_id_map={
            "_": [0],
            "^": [1],
            "$": [2],
            "a": [10],
            "k": [12],
            "o": [15],
        },
        phoneme_type=PhonemeType.MULTILINGUAL,
    )

    session = MagicMock()

    # -- Mock get_inputs (names the model expects) --
    input_mock = MagicMock()
    input_mock.name = "input"
    input_lengths_mock = MagicMock()
    input_lengths_mock.name = "input_lengths"
    scales_mock = MagicMock()
    scales_mock.name = "scales"
    inputs_list = [input_mock, input_lengths_mock, scales_mock]
    if has_speaker_embedding:
        spk_emb_mock = MagicMock()
        spk_emb_mock.name = "speaker_embedding"
        spk_emb_mock.shape = ["batch_size", speaker_embedding_dim]
        spk_emb_mask_mock = MagicMock()
        spk_emb_mask_mock.name = "speaker_embedding_mask"
        spk_emb_mask_mock.shape = ["batch_size", 1]
        inputs_list.extend([spk_emb_mock, spk_emb_mask_mock])
    session.get_inputs.return_value = inputs_list

    # -- Mock get_outputs (include "durations" when requested) --
    output_mock = MagicMock()
    output_mock.name = "output"
    outputs_list = [output_mock]
    if has_durations:
        dur_output_mock = MagicMock()
        dur_output_mock.name = "durations"
        outputs_list.append(dur_output_mock)
    session.get_outputs.return_value = outputs_list

    # -- Mock session.run() return values --
    audio_samples = np.random.randn(1, 1, sample_rate).astype(np.float32)
    durations_array = np.random.uniform(3, 15, size=(1, phoneme_ids_len)).astype(
        np.float32
    )

    if has_durations:
        session.run.return_value = [audio_samples, durations_array]
    else:
        session.run.return_value = [audio_samples]

    return PiperVoice(session=session, config=config)


# ---------------------------------------------------------------------------
# 1. has_duration_output property
# ---------------------------------------------------------------------------


class TestHasDurationOutput:
    """Tests for the has_duration_output property."""

    def test_has_duration_output_true(self):
        """Voice whose ONNX model includes a 'durations' output returns True."""
        voice = _make_mock_voice(has_durations=True)
        assert voice.has_duration_output is True

    def test_has_duration_output_false(self):
        """Voice whose ONNX model lacks a 'durations' output returns False."""
        voice = _make_mock_voice(has_durations=False)
        assert voice.has_duration_output is False


# ---------------------------------------------------------------------------
# 2. _synthesize_ids_core
# ---------------------------------------------------------------------------


class TestSynthesizeIdsCore:
    """Tests for the internal _synthesize_ids_core method."""

    def test_returns_tuple(self):
        """_synthesize_ids_core returns a 3-tuple (bytes, ndarray, list)."""
        voice = _make_mock_voice(has_durations=True)
        phoneme_ids = [1, 0, 10, 0, 12, 0, 15, 0, 2]

        result = voice._synthesize_ids_core(phoneme_ids)

        assert isinstance(result, tuple)
        assert len(result) == 3

        audio_bytes, durations, original_ids = result
        assert isinstance(audio_bytes, bytes)
        assert len(audio_bytes) > 0
        assert isinstance(durations, np.ndarray)
        assert isinstance(original_ids, list)

    def test_no_durations_returns_none(self):
        """Model without durations output returns None for the durations element."""
        voice = _make_mock_voice(has_durations=False)
        phoneme_ids = [1, 0, 10, 0, 12, 0, 15, 0, 2]

        audio_bytes, durations, original_ids = voice._synthesize_ids_core(phoneme_ids)

        assert isinstance(audio_bytes, bytes)
        assert len(audio_bytes) > 0
        assert durations is None
        assert isinstance(original_ids, list)

    def test_preserves_original_phoneme_ids(self):
        """The returned original_ids match the input (even when padding occurs)."""
        voice = _make_mock_voice(has_durations=True)
        phoneme_ids = [1, 0, 10, 0, 2]  # short enough to trigger padding

        _, _, original_ids = voice._synthesize_ids_core(phoneme_ids)

        assert original_ids == [1, 0, 10, 0, 2]


# ---------------------------------------------------------------------------
# 3. synthesize_ids_to_raw (backward compatibility)
# ---------------------------------------------------------------------------


class TestSynthesizeIdsToRaw:
    """Tests for the backward-compatible synthesize_ids_to_raw wrapper."""

    def test_returns_bytes(self):
        """synthesize_ids_to_raw returns plain bytes, not a tuple."""
        voice = _make_mock_voice(has_durations=True)
        phoneme_ids = [1, 0, 10, 0, 12, 0, 15, 0, 2]

        result = voice.synthesize_ids_to_raw(phoneme_ids)

        assert isinstance(result, bytes)
        assert not isinstance(result, tuple)
        assert len(result) > 0

    def test_backward_compat_no_durations(self):
        """synthesize_ids_to_raw still returns bytes when model has no durations."""
        voice = _make_mock_voice(has_durations=False)
        phoneme_ids = [1, 0, 10, 0, 12, 0, 15, 0, 2]

        result = voice.synthesize_ids_to_raw(phoneme_ids)

        assert isinstance(result, bytes)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 4. synthesize_with_timing
# ---------------------------------------------------------------------------


class TestSynthesizeWithTiming:
    """Tests for the full synthesize_with_timing method."""

    @staticmethod
    def _patch_phonemize(voice: PiperVoice) -> None:
        """Replace voice.phonemize with a mock returning known phonemes."""
        voice.phonemize = MagicMock(return_value=[["a", "k", "o"]])

    def test_returns_tuple(self):
        """synthesize_with_timing returns a 2-tuple (bytes, TimingResult)."""
        voice = _make_mock_voice(has_durations=True)
        self._patch_phonemize(voice)

        result = voice.synthesize_with_timing("ako")

        assert isinstance(result, tuple)
        assert len(result) == 2

        wav_bytes, timing = result
        assert isinstance(wav_bytes, bytes)
        assert isinstance(timing, TimingResult)

    def test_no_durations_returns_none_timing(self):
        """When model lacks durations output, timing_result is None."""
        voice = _make_mock_voice(has_durations=False)
        self._patch_phonemize(voice)

        wav_bytes, timing = voice.synthesize_with_timing("ako")

        assert isinstance(wav_bytes, bytes)
        assert len(wav_bytes) > 0
        assert timing is None

    def test_timing_has_phonemes(self):
        """TimingResult.phonemes is a non-empty list of PhonemeTimingInfo."""
        voice = _make_mock_voice(has_durations=True)
        self._patch_phonemize(voice)

        _, timing = voice.synthesize_with_timing("ako")

        assert timing is not None
        assert len(timing.phonemes) > 0
        for entry in timing.phonemes:
            assert isinstance(entry, PhonemeTimingInfo)
            assert isinstance(entry.phoneme, str)
            assert entry.duration_ms >= 0.0
            assert entry.end_ms >= entry.start_ms

    def test_wav_bytes_valid(self):
        """Returned bytes form a valid WAV file that can be opened."""
        voice = _make_mock_voice(has_durations=True)
        self._patch_phonemize(voice)

        wav_bytes, _ = voice.synthesize_with_timing("ako")

        buf = BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == voice.config.sample_rate
            assert wf.getnframes() > 0

    def test_timing_sample_rate_matches_config(self):
        """TimingResult.sample_rate matches the voice config."""
        voice = _make_mock_voice(has_durations=True, sample_rate=22050)
        self._patch_phonemize(voice)

        _, timing = voice.synthesize_with_timing("ako")

        assert timing is not None
        assert timing.sample_rate == 22050

    def test_timing_total_duration_positive(self):
        """TimingResult.total_duration_ms is positive for non-trivial input."""
        voice = _make_mock_voice(has_durations=True)
        self._patch_phonemize(voice)

        _, timing = voice.synthesize_with_timing("ako")

        assert timing is not None
        assert timing.total_duration_ms > 0.0


class TestSynthesizeWithTimingAdvanced:
    """Advanced timing integration tests."""

    def test_multi_sentence_cumulative_offset(self):
        """Multiple sentences should have cumulative timing offsets."""
        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=5)
        # phonemize returns 2 sentences
        voice.phonemize = MagicMock(return_value=[["a", "k"], ["o", "n"]])

        wav_bytes, timing = voice.synthesize_with_timing("text1. text2.")

        assert timing is not None
        assert len(timing.phonemes) > 2
        # Second sentence phonemes should start after first sentence ends
        # Find where second sentence starts (after first sentence's last phoneme)
        # At minimum, no phoneme should have start < previous phoneme's start
        for i in range(1, len(timing.phonemes)):
            assert timing.phonemes[i].start_ms >= timing.phonemes[i - 1].start_ms

    def test_sentence_silence_increases_gap(self):
        """sentence_silence should increase gap between sentences."""
        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=5)
        voice.phonemize = MagicMock(return_value=[["a"], ["k"]])

        _, timing_no_silence = voice.synthesize_with_timing("a. b.", sentence_silence=0.0)
        _, timing_with_silence = voice.synthesize_with_timing("a. b.", sentence_silence=0.5)

        assert timing_no_silence is not None
        assert timing_with_silence is not None
        # With silence should have larger total duration
        assert timing_with_silence.total_duration_ms > timing_no_silence.total_duration_ms

    def test_hop_size_from_config(self):
        """Timing should use hop_size from PiperConfig."""
        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=5)
        voice.phonemize = MagicMock(return_value=[["a"]])
        # Default hop_size is 256, verify it's used
        assert voice.config.hop_size == 256

        _, timing = voice.synthesize_with_timing("a")
        assert timing is not None
        assert timing.sample_rate == voice.config.sample_rate


class TestSynthesizeWithTimingParameters:
    """Parameter pass-through tests for `synthesize_with_timing()`."""

    def test_wav_file_parameter_writes_frames(self):
        """When a wav_file is provided, synthesize_with_timing writes frames to it."""
        import io as _io
        import wave as _wave

        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=5)
        voice.phonemize = MagicMock(return_value=[["a"]])

        buf = _io.BytesIO()
        with _wave.open(buf, "wb") as wav_file:
            wav_bytes, timing = voice.synthesize_with_timing("a", wav_file=wav_file)

        # wav_file should have received frames (buffer not empty)
        assert buf.tell() > 0

        # Verify the buffer is a valid WAV file with the expected sample rate
        buf.seek(0)
        with _wave.open(buf, "rb") as wav_read:
            assert wav_read.getframerate() == voice.config.sample_rate
            assert wav_read.getnchannels() == 1
            assert wav_read.getsampwidth() == 2
            assert wav_read.getnframes() > 0

    def test_language_id_parameter_forwarded_to_session(self):
        """language_id reaches the ONNX session.run call when the model has lid."""
        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=5)
        voice.phonemize = MagicMock(return_value=[["a"]])

        # Add 'lid' to the mock model's input names so the language_id path is taken.
        lid_mock = MagicMock()
        lid_mock.name = "lid"
        existing_inputs = voice.session.get_inputs.return_value
        voice.session.get_inputs.return_value = [*existing_inputs, lid_mock]

        _, _ = voice.synthesize_with_timing("a", language_id=3)

        # Inspect the feeds dict from the captured session.run call
        call_args = voice.session.run.call_args
        assert call_args is not None
        feeds = call_args[0][1]
        assert "lid" in feeds
        # Numpy array element access
        assert int(feeds["lid"][0]) == 3

    def test_speaker_id_parameter_forwarded_to_session(self):
        """speaker_id reaches the ONNX session.run call for multi-speaker models."""
        voice = _make_mock_voice(
            num_speakers=3, has_durations=True, phoneme_ids_len=5
        )
        voice.phonemize = MagicMock(return_value=[["a"]])

        _, _ = voice.synthesize_with_timing("a", speaker_id=2)

        call_args = voice.session.run.call_args
        assert call_args is not None
        feeds = call_args[0][1]
        assert "sid" in feeds
        # shape is [1, 1]
        assert int(feeds["sid"][0][0]) == 2


class TestSynthesizeCoreShortText:
    """Verifies short-text mitigation (Strategy A padding + Strategy B noise) in core."""

    def test_short_ids_reduce_noise_scale(self):
        """Phoneme sequences shorter than MIN_PHONEME_IDS reduce noise_scale."""
        from piper.voice import MIN_PHONEME_IDS, PiperVoice

        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=50)

        # Very short input (4 IDs, well below MIN_PHONEME_IDS=40)
        short_ids = [1, 10, 10, 2]
        PiperVoice._synthesize_ids_core(voice, short_ids)

        # Verify scales[0] (noise_scale) was reduced below the default 0.667
        call_args = voice.session.run.call_args
        assert call_args is not None
        feeds = call_args[0][1]
        scales = feeds["scales"]
        assert scales[0] < 0.667  # noise_scale reduced
        assert scales[2] < 0.8    # noise_w reduced
        assert abs(scales[1] - 1.0) < 1e-6  # length_scale unchanged

    def test_long_ids_keep_default_scales(self):
        """Phoneme sequences >= MIN_PHONEME_IDS use the default scales."""
        from piper.voice import MIN_PHONEME_IDS, PiperVoice

        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=50)

        long_ids = [1] + [10] * (MIN_PHONEME_IDS - 1) + [2]
        PiperVoice._synthesize_ids_core(voice, long_ids)

        call_args = voice.session.run.call_args
        assert call_args is not None
        feeds = call_args[0][1]
        scales = feeds["scales"]
        # Default values preserved
        assert abs(scales[0] - 0.667) < 1e-6
        assert abs(scales[1] - 1.0) < 1e-6
        assert abs(scales[2] - 0.8) < 1e-6

    def test_original_phoneme_ids_preserved_after_padding(self):
        """_synthesize_ids_core returns the original (pre-padding) phoneme IDs."""
        voice = _make_mock_voice(has_durations=True, phoneme_ids_len=50)

        short_ids = [1, 10, 10, 10, 2]
        _, _, original_ids = voice._synthesize_ids_core(short_ids)

        assert original_ids == [1, 10, 10, 10, 2]


# ---------------------------------------------------------------------------
# Regression: speaker_embedding inputs (issue #385)
# ---------------------------------------------------------------------------


class TestSpeakerEmbeddingDefaults:
    """Regression coverage for issue #385.

    ``export_onnx.py`` always declares ``speaker_embedding`` and
    ``speaker_embedding_mask`` inputs (forward-compat hook for future
    voice-cloning training; the bundled checkpoints are not trained for
    zero-shot transfer). The runtime must still feed those inputs to
    satisfy ORT — zeros with ``mask=0`` — so the inference falls back
    to the trained ``sid`` / ``lid`` conditioning. Without this, ORT
    raises ``ValueError: Required inputs (...) are missing from input feed``.
    """

    def test_synthesize_passes_zero_embedding_with_mask_off(self):
        """_synthesize_ids_core supplies zeros + mask=0 by default."""
        voice = _make_mock_voice(
            has_durations=True,
            has_speaker_embedding=True,
            speaker_embedding_dim=192,
        )
        phoneme_ids = [1, 0, 10, 0, 12, 0, 15, 0, 2]

        voice._synthesize_ids_core(phoneme_ids)

        assert voice.session.run.called
        feeds = voice.session.run.call_args[0][1]
        assert "speaker_embedding" in feeds
        assert "speaker_embedding_mask" in feeds
        assert feeds["speaker_embedding"].shape == (1, 192)
        assert feeds["speaker_embedding"].dtype == np.float32
        assert np.all(feeds["speaker_embedding"] == 0.0)
        assert feeds["speaker_embedding_mask"].tolist() == [[0]]
        assert feeds["speaker_embedding_mask"].dtype == np.int64

    def test_synthesize_falls_back_to_default_dim_when_shape_unknown(self):
        """When the ONNX input shape is symbolic, default to 256 dims."""
        voice = _make_mock_voice(has_speaker_embedding=True)
        # Overwrite the speaker_embedding input to advertise a symbolic dim
        for inp in voice.session.get_inputs.return_value:
            if inp.name == "speaker_embedding":
                inp.shape = ["batch_size", "emb_dim"]
                break

        voice._synthesize_ids_core([1, 0, 10, 0, 2])

        feeds = voice.session.run.call_args[0][1]
        assert feeds["speaker_embedding"].shape == (1, 256)

    def test_warmup_supplies_speaker_embedding_inputs(self):
        """_warmup_session feeds zero speaker_embedding + mask=0 when required."""
        from piper.voice import _warmup_session

        voice = _make_mock_voice(
            has_speaker_embedding=True,
            speaker_embedding_dim=192,
        )

        _warmup_session(voice.session, runs=1, phoneme_length=20)

        assert voice.session.run.called
        feeds = voice.session.run.call_args[0][1]
        assert feeds["speaker_embedding"].shape == (1, 192)
        assert feeds["speaker_embedding"].dtype == np.float32
        assert feeds["speaker_embedding_mask"].tolist() == [[0]]
