"""
Tests for speaker_embedding support in PiperVoice and InferenceConfig.

Covers:
- synthesize(), synthesize_stream_raw(), synthesize_ids_to_raw() passthrough
- zero-vector fallback when speaker_embedding is None but model expects it
- 1D (192,) ndarray reshape to (1, 192)
- InferenceConfig.speaker_embedding round-trip and to_synthesize_args()
"""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from piper.config import PiperConfig
from piper.voice import PiperVoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(num_speakers: int = 1) -> PiperConfig:
    """Create a minimal PiperConfig for testing."""
    return PiperConfig(
        num_symbols=100,
        num_speakers=num_speakers,
        sample_rate=22050,
        noise_scale=0.667,
        length_scale=1.0,
        noise_w=0.8,
        phoneme_id_map={"_": [0], "^": [1], "$": [2], "a": [10]},
        phoneme_type="multilingual",
    )


def _make_input_descriptor(name: str) -> MagicMock:
    """Create a mock ONNX input descriptor with the given name."""
    inp = MagicMock()
    inp.name = name
    return inp


def _dummy_audio(samples: int = 8000) -> np.ndarray:
    """Return a dummy float32 audio array shaped [1, 1, samples]."""
    return np.random.randn(1, 1, samples).astype(np.float32)


def _make_voice(
    *,
    num_speakers: int = 1,
    onnx_input_names: list[str] | None = None,
) -> PiperVoice:
    """
    Build a real PiperVoice with a mocked ONNX session.

    Uses a real PiperVoice instance so internal helpers like
    ``_synthesize_ids_core`` execute (and thus reach ``session.run``).
    Only the ONNX session is mocked.

    onnx_input_names: names exposed by session.get_inputs().
    """
    if onnx_input_names is None:
        onnx_input_names = ["input", "input_lengths", "scales"]

    config = _make_config(num_speakers=num_speakers)
    session = MagicMock()
    session.get_inputs.return_value = [
        _make_input_descriptor(n) for n in onnx_input_names
    ]
    # Mock get_outputs (no 'durations' output for these tests)
    output_mock = MagicMock()
    output_mock.name = "output"
    session.get_outputs.return_value = [output_mock]
    session.run.return_value = [_dummy_audio()]

    return PiperVoice(session=session, config=config)


# ---------------------------------------------------------------------------
# Test: synthesize_ids_to_raw — speaker_embedding passthrough
# ---------------------------------------------------------------------------
class TestSynthesizeIdsToRaw:

    @pytest.mark.unit
    def test_speaker_embedding_passed_to_session(self):
        """When speaker_embedding input exists and embedding provided, tensor shape is [1,192]."""
        voice = _make_voice(
            num_speakers=2,
            onnx_input_names=["input", "input_lengths", "scales", "sid", "speaker_embedding"],
        )
        embedding = np.random.randn(192).astype(np.float32)

        long_ids = [1] + [10] * 48 + [2]  # >= MIN_PHONEME_IDS=40
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=embedding)

        voice.session.run.assert_called_once()
        call_args = voice.session.run.call_args[0][1]

        assert "speaker_embedding" in call_args
        emb_tensor = call_args["speaker_embedding"]
        assert emb_tensor.shape == (1, 192)
        assert emb_tensor.dtype == np.float32

    @pytest.mark.unit
    def test_speaker_embedding_values_preserved(self):
        """The values of the embedding are not modified (only reshaped)."""
        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        )
        embedding = np.arange(192, dtype=np.float32)

        long_ids = [1] + [10] * 48 + [2]
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=embedding)

        call_args = voice.session.run.call_args[0][1]
        emb_tensor = call_args["speaker_embedding"]
        np.testing.assert_array_equal(emb_tensor.flatten(), embedding)

    @pytest.mark.unit
    def test_2d_embedding_accepted(self):
        """A (1, 192) shaped embedding is accepted and kept as-is."""
        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        )
        embedding = np.random.randn(1, 192).astype(np.float32)

        long_ids = [1] + [10] * 48 + [2]
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=embedding)

        call_args = voice.session.run.call_args[0][1]
        emb_tensor = call_args["speaker_embedding"]
        assert emb_tensor.shape == (1, 192)

    @pytest.mark.unit
    def test_1d_embedding_reshaped_to_1x192(self):
        """A flat (192,) ndarray is reshaped to (1, 192) before being passed to the session."""
        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        )
        flat_embedding = np.random.randn(192).astype(np.float32)
        assert flat_embedding.shape == (192,)

        long_ids = [1] + [10] * 48 + [2]
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=flat_embedding)

        call_args = voice.session.run.call_args[0][1]
        emb_tensor = call_args["speaker_embedding"]
        assert emb_tensor.shape == (1, 192), (
            f"Expected shape (1, 192) after reshape of 1D array, got {emb_tensor.shape}"
        )

    @pytest.mark.unit
    def test_zero_vector_fallback_when_no_embedding(self):
        """
        When model expects 'speaker_embedding' but none is provided,
        a zero vector of shape (1, 192) is passed to the session.
        """
        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        )

        long_ids = [1] + [10] * 48 + [2]
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=None)

        call_args = voice.session.run.call_args[0][1]
        assert "speaker_embedding" in call_args
        emb_tensor = call_args["speaker_embedding"]
        assert emb_tensor.shape == (1, 192)
        assert emb_tensor.dtype == np.float32
        np.testing.assert_array_equal(emb_tensor, np.zeros((1, 192), dtype=np.float32))

    @pytest.mark.unit
    def test_zero_vector_fallback_logs_warning(self, caplog):
        """A warning is logged when the zero-vector fallback is used."""
        import logging

        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales", "speaker_embedding"],
        )
        long_ids = [1] + [10] * 48 + [2]

        with caplog.at_level(logging.WARNING):
            PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=None)

        assert any(
            "speaker_embedding" in record.message and "zero" in record.message.lower()
            for record in caplog.records
        ), "Expected a warning mentioning 'speaker_embedding' and 'zero'"

    @pytest.mark.unit
    def test_no_speaker_embedding_key_when_model_lacks_input(self):
        """When model has no 'speaker_embedding' input, the key is absent from session args."""
        voice = _make_voice(
            num_speakers=1,
            onnx_input_names=["input", "input_lengths", "scales"],
        )
        embedding = np.random.randn(192).astype(np.float32)

        long_ids = [1] + [10] * 48 + [2]
        PiperVoice.synthesize_ids_to_raw(voice, long_ids, speaker_embedding=embedding)

        call_args = voice.session.run.call_args[0][1]
        assert "speaker_embedding" not in call_args


# ---------------------------------------------------------------------------
# Test: synthesize_stream_raw — speaker_embedding passthrough
# ---------------------------------------------------------------------------
class TestSynthesizeStreamRaw:

    @pytest.mark.unit
    def test_speaker_embedding_forwarded_to_ids_to_raw(self):
        """synthesize_stream_raw passes speaker_embedding down to synthesize_ids_to_raw.

        Note: PR #569 refactored synthesize_stream_raw to a phase 2 G2P-ORT
        pipeline (_split_sentences + _phonemize_one_factory +
        _stream_phonemes_to_audio). This test mocks the new internal flow.
        """
        config = _make_config(num_speakers=1)
        voice = MagicMock(spec=PiperVoice)
        voice.config = config
        voice.session = MagicMock()
        voice._split_sentences = MagicMock(return_value=["hello world test text here"])
        voice._phonemize_one_factory = MagicMock(return_value=lambda s: ["a"] * 5)

        audio_bytes = b"\xab\xcd" * 200
        voice.synthesize_ids_to_raw = MagicMock(return_value=audio_bytes)

        def fake_stream(phonemes_iter, break_bytes, silence_bytes, **kwargs):
            for _ in phonemes_iter:
                voice.synthesize_ids_to_raw(
                    [1] + [10] * 48 + [2],
                    speaker_embedding=kwargs.get("speaker_embedding"),
                )
                yield audio_bytes

        voice._stream_phonemes_to_audio = fake_stream

        embedding = np.random.randn(192).astype(np.float32)
        results = list(
            PiperVoice.synthesize_stream_raw(voice, "hello world test text here", speaker_embedding=embedding)
        )

        assert len(results) >= 1
        voice.synthesize_ids_to_raw.assert_called_once()
        _, kwargs = voice.synthesize_ids_to_raw.call_args
        passed_embedding = kwargs.get("speaker_embedding")
        assert passed_embedding is not None
        np.testing.assert_array_equal(passed_embedding, embedding)

    @pytest.mark.unit
    def test_speaker_embedding_none_forwarded(self):
        """synthesize_stream_raw forwards speaker_embedding=None to synthesize_ids_to_raw."""
        config = _make_config(num_speakers=1)
        voice = MagicMock(spec=PiperVoice)
        voice.config = config
        voice.session = MagicMock()
        voice._split_sentences = MagicMock(return_value=["hello world test text here"])
        voice._phonemize_one_factory = MagicMock(return_value=lambda s: ["a"] * 5)

        audio_bytes = b"\x00\x01" * 200
        voice.synthesize_ids_to_raw = MagicMock(return_value=audio_bytes)

        def fake_stream(phonemes_iter, break_bytes, silence_bytes, **kwargs):
            for _ in phonemes_iter:
                voice.synthesize_ids_to_raw(
                    [1] + [10] * 48 + [2],
                    speaker_embedding=kwargs.get("speaker_embedding"),
                )
                yield audio_bytes

        voice._stream_phonemes_to_audio = fake_stream

        results = list(
            PiperVoice.synthesize_stream_raw(voice, "hello world test text here", speaker_embedding=None)
        )

        assert len(results) >= 1
        voice.synthesize_ids_to_raw.assert_called_once()
        _, kwargs = voice.synthesize_ids_to_raw.call_args
        assert kwargs.get("speaker_embedding") is None


# ---------------------------------------------------------------------------
# Test: synthesize — speaker_embedding passthrough
# ---------------------------------------------------------------------------
class TestSynthesize:

    @pytest.mark.unit
    def test_synthesize_passes_embedding_to_stream_raw(self):
        """synthesize() passes speaker_embedding to synthesize_stream_raw."""
        config = _make_config(num_speakers=1)
        voice = MagicMock(spec=PiperVoice)
        voice.config = config

        audio_bytes = b"\x00" * 4000  # 1000 int16 samples
        voice.synthesize_stream_raw = MagicMock(return_value=iter([audio_bytes]))

        embedding = np.random.randn(192).astype(np.float32)

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            PiperVoice.synthesize(voice, "test text for synthesis", wav_file, speaker_embedding=embedding)

        voice.synthesize_stream_raw.assert_called_once()
        _, kwargs = voice.synthesize_stream_raw.call_args
        passed_embedding = kwargs.get("speaker_embedding")
        assert passed_embedding is not None
        np.testing.assert_array_equal(passed_embedding, embedding)

    @pytest.mark.unit
    def test_synthesize_none_embedding_forwarded(self):
        """synthesize() forwards speaker_embedding=None to synthesize_stream_raw."""
        config = _make_config(num_speakers=1)
        voice = MagicMock(spec=PiperVoice)
        voice.config = config

        audio_bytes = b"\x00" * 4000
        voice.synthesize_stream_raw = MagicMock(return_value=iter([audio_bytes]))

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            PiperVoice.synthesize(voice, "test text for synthesis", wav_file, speaker_embedding=None)

        voice.synthesize_stream_raw.assert_called_once()
        _, kwargs = voice.synthesize_stream_raw.call_args
        assert kwargs.get("speaker_embedding") is None


# ---------------------------------------------------------------------------
# Test: InferenceConfig — speaker_embedding round-trip
# ---------------------------------------------------------------------------
class TestInferenceConfig:

    @pytest.mark.unit
    def test_speaker_embedding_field_exists(self):
        """InferenceConfig has a speaker_embedding field."""
        from piper.inference_config import InferenceConfig

        config = InferenceConfig(model_path="/tmp/model.onnx")
        assert hasattr(config, "speaker_embedding")
        assert config.speaker_embedding is None

    @pytest.mark.unit
    def test_speaker_embedding_round_trip(self):
        """speaker_embedding list is stored and retrieved unchanged."""
        from piper.inference_config import InferenceConfig

        emb_list = list(np.random.randn(192).astype(np.float64))
        config = InferenceConfig(
            model_path="/tmp/model.onnx",
            speaker_embedding=emb_list,
        )
        assert config.speaker_embedding == emb_list

    @pytest.mark.unit
    def test_to_synthesize_args_includes_embedding_as_ndarray(self):
        """to_synthesize_args() converts speaker_embedding list to np.ndarray."""
        from piper.inference_config import InferenceConfig

        emb_list = [float(i) for i in range(192)]
        config = InferenceConfig(
            model_path="/tmp/model.onnx",
            speaker_embedding=emb_list,
        )
        args = config.to_synthesize_args()

        assert "speaker_embedding" in args
        emb = args["speaker_embedding"]
        assert isinstance(emb, np.ndarray)
        assert emb.dtype == np.float32
        np.testing.assert_array_equal(emb.flatten(), np.array(emb_list, dtype=np.float32))

    @pytest.mark.unit
    def test_to_synthesize_args_omits_embedding_when_none(self):
        """to_synthesize_args() does not include speaker_embedding key when it is None."""
        from piper.inference_config import InferenceConfig

        config = InferenceConfig(model_path="/tmp/model.onnx")
        args = config.to_synthesize_args()
        assert "speaker_embedding" not in args

    @pytest.mark.unit
    def test_from_args_loads_embedding_from_npy(self, tmp_path):
        """from_args() loads a .npy file and stores it as a list."""
        from piper.inference_config import InferenceConfig

        embedding = np.random.randn(192).astype(np.float32)
        npy_path = tmp_path / "speaker.npy"
        np.save(str(npy_path), embedding)

        args = MagicMock()
        args.model = str(tmp_path / "model.onnx")
        args.config = None
        args.speaker = None
        args.noise_scale = None
        args.length_scale = 1.0
        args.noise_w = None
        args.volume = 1.0
        args.sentence_silence = 0.0
        args.output_raw = False
        args.output_file = None
        args.output_dir = None
        args.auto_play = False
        args.cuda = False
        args.input_file = []
        args.text = None
        args.speaker_embedding = str(npy_path)

        config = InferenceConfig.from_args(args)

        assert config.speaker_embedding is not None
        assert isinstance(config.speaker_embedding, list)
        assert len(config.speaker_embedding) == 192
        np.testing.assert_array_almost_equal(
            np.array(config.speaker_embedding, dtype=np.float32),
            embedding,
        )

    @pytest.mark.unit
    def test_from_args_no_embedding_when_none(self):
        """from_args() keeps speaker_embedding as None when arg is not provided."""
        from piper.inference_config import InferenceConfig

        args = MagicMock()
        args.model = "/tmp/model.onnx"
        args.config = None
        args.speaker = None
        args.noise_scale = None
        args.length_scale = None
        args.noise_w = None
        args.volume = 1.0
        args.sentence_silence = 0.0
        args.output_raw = False
        args.output_file = None
        args.output_dir = None
        args.auto_play = False
        args.cuda = False
        args.input_file = []
        args.text = None
        args.speaker_embedding = None

        config = InferenceConfig.from_args(args)
        assert config.speaker_embedding is None
