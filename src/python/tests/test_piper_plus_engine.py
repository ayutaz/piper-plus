"""Tests for piper_plus.engine -- standalone ONNX inference engine.

Verifies session creation, audio conversion, config loading, warmup,
and the synthesize() entry point using mock ORT sessions.
Follows t-wada TDD principles: behaviour-driven naming, Arrange-Act-Assert,
triangulation across boundary values.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import onnxruntime
import pytest

from piper_plus.engine import (
    MAX_INTRA_THREADS,
    WARMUP_PHONEME_LENGTH,
    _get_logical_core_count,
    _get_providers,
    audio_float_to_int16,
    create_ort_session,
    get_language_id_map,
    get_sample_rate,
    get_speaker_id_map,
    load_config,
    synthesize,
    synthesize_float,
    warmup_session,
)


# ===================================================================
# Helper: mock ORT session
# ===================================================================


def _make_mock_session(
    *, has_sid: bool = False, has_lid: bool = False, has_prosody: bool = False
) -> MagicMock:
    """Create a mock InferenceSession with configurable inputs."""
    session = MagicMock(spec=onnxruntime.InferenceSession)
    inputs = []
    for name in ("input", "input_lengths", "scales"):
        inp = MagicMock()
        inp.name = name
        inputs.append(inp)
    if has_sid:
        inp = MagicMock()
        inp.name = "sid"
        inputs.append(inp)
    if has_lid:
        inp = MagicMock()
        inp.name = "lid"
        inputs.append(inp)
    if has_prosody:
        inp = MagicMock()
        inp.name = "prosody_features"
        inputs.append(inp)
    session.get_inputs.return_value = inputs

    out = MagicMock()
    out.name = "output"
    session.get_outputs.return_value = [out]

    # Default: return a 3-D float array (batch=1, channels=1, time=100)
    session.run.return_value = [np.random.randn(1, 1, 100).astype(np.float32)]
    return session


# ===================================================================
# audio_float_to_int16
# ===================================================================


@pytest.mark.unit
class TestAudioFloatToInt16:
    """audio_float_to_int16 clips and converts float32 to int16 PCM."""

    def test_converts_zero_array(self):
        audio = np.zeros(10, dtype=np.float32)
        result = audio_float_to_int16(audio)
        assert result.dtype == np.int16
        np.testing.assert_array_equal(result, np.zeros(10, dtype=np.int16))

    def test_clips_values_above_one(self):
        audio = np.array([2.0, 3.0], dtype=np.float32)
        result = audio_float_to_int16(audio)
        expected = np.array([32767, 32767], dtype=np.int16)
        np.testing.assert_array_equal(result, expected)

    def test_clips_values_below_negative_one(self):
        audio = np.array([-2.0, -5.0], dtype=np.float32)
        result = audio_float_to_int16(audio)
        expected = np.array([-32767, -32767], dtype=np.int16)
        np.testing.assert_array_equal(result, expected)

    def test_preserves_values_within_range(self):
        audio = np.array([0.5, -0.5], dtype=np.float32)
        result = audio_float_to_int16(audio)
        expected = np.array([16383, -16383], dtype=np.int16)
        np.testing.assert_array_equal(result, expected)

    def test_boundary_value_positive_one(self):
        audio = np.array([1.0], dtype=np.float32)
        result = audio_float_to_int16(audio)
        assert result[0] == 32767

    def test_boundary_value_negative_one(self):
        audio = np.array([-1.0], dtype=np.float32)
        result = audio_float_to_int16(audio)
        assert result[0] == -32767

    def test_empty_array(self):
        audio = np.array([], dtype=np.float32)
        result = audio_float_to_int16(audio)
        assert result.dtype == np.int16
        assert len(result) == 0


# ===================================================================
# load_config / get_sample_rate / get_*_id_map
# ===================================================================


@pytest.mark.unit
class TestLoadConfig:
    """load_config reads JSON and returns a dict."""

    def test_loads_valid_json(self, tmp_path):
        config = {"audio": {"sample_rate": 22050}, "phoneme_id_map": {}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        loaded = load_config(path)

        assert loaded == config

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json }", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            load_config(path)

    def test_accepts_path_object(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text('{"key": "value"}', encoding="utf-8")

        result = load_config(Path(path))
        assert result == {"key": "value"}


@pytest.mark.unit
class TestConfigHelpers:
    """get_sample_rate / get_language_id_map / get_speaker_id_map."""

    def test_get_sample_rate_from_config(self):
        config = {"audio": {"sample_rate": 44100}}
        assert get_sample_rate(config) == 44100

    def test_get_sample_rate_default_when_missing(self):
        assert get_sample_rate({}) == 22050

    def test_get_sample_rate_default_when_audio_key_missing_sample_rate(self):
        assert get_sample_rate({"audio": {}}) == 22050

    def test_get_language_id_map_returns_map(self):
        config = {"language_id_map": {"ja": 0, "en": 1}}
        assert get_language_id_map(config) == {"ja": 0, "en": 1}

    def test_get_language_id_map_empty_when_missing(self):
        assert get_language_id_map({}) == {}

    def test_get_speaker_id_map_returns_map(self):
        config = {"speaker_id_map": {"alice": 0, "bob": 1}}
        assert get_speaker_id_map(config) == {"alice": 0, "bob": 1}

    def test_get_speaker_id_map_empty_when_missing(self):
        assert get_speaker_id_map({}) == {}


# ===================================================================
# _get_logical_core_count
# ===================================================================


@pytest.mark.unit
class TestGetLogicalCoreCount:
    """_get_logical_core_count respects cgroup/affinity limits."""

    @patch("os.sched_getaffinity", create=True, return_value={0, 1})
    def test_uses_sched_getaffinity_when_available(self, _mock):
        assert _get_logical_core_count() == 2

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=16)
    def test_falls_back_to_cpu_count(self, _mock_cpu, _mock_affinity):
        assert _get_logical_core_count() == 16

    @patch("os.sched_getaffinity", create=True, side_effect=AttributeError)
    @patch("os.cpu_count", return_value=None)
    def test_returns_2_when_cpu_count_is_none(self, _mock_cpu, _mock_affinity):
        assert _get_logical_core_count() == 2


# ===================================================================
# _get_providers
# ===================================================================


@pytest.mark.unit
class TestGetProviders:
    """_get_providers returns execution providers for the requested device."""

    def test_cpu_returns_cpu_provider_only(self):
        providers = _get_providers("cpu")
        assert providers == ["CPUExecutionProvider"]

    @patch(
        "piper_plus.engine.ort.get_available_providers",
        return_value=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    def test_gpu_with_cuda_available(self, _mock):
        providers = _get_providers("gpu")
        assert "CUDAExecutionProvider" in providers
        assert "CPUExecutionProvider" in providers

    @patch(
        "piper_plus.engine.ort.get_available_providers",
        return_value=["CPUExecutionProvider"],
    )
    def test_gpu_without_cuda_falls_back_to_cpu(self, _mock):
        providers = _get_providers("gpu")
        assert providers == ["CPUExecutionProvider"]

    def test_cuda_device_with_id(self):
        providers = _get_providers("cuda:1")
        assert ("CUDAExecutionProvider", {"device_id": "1"}) in providers
        assert "CPUExecutionProvider" in providers


# ===================================================================
# create_ort_session
# ===================================================================


@pytest.mark.unit
class TestCreateOrtSession:
    """create_ort_session configures ORT options per the contract spec."""

    @patch("piper_plus.engine.ort.InferenceSession")
    def test_sets_graph_optimization_to_enable_all(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu")

        call_args = mock_cls.call_args
        opts = call_args[0][1]
        assert opts.graph_optimization_level == onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

    @patch("piper_plus.engine.ort.InferenceSession")
    def test_sets_sequential_execution_mode(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu")

        opts = mock_cls.call_args[0][1]
        assert opts.execution_mode == onnxruntime.ExecutionMode.ORT_SEQUENTIAL

    @patch("piper_plus.engine.ort.InferenceSession")
    def test_inter_op_threads_is_one(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu")

        opts = mock_cls.call_args[0][1]
        assert opts.inter_op_num_threads == 1

    @patch("piper_plus.engine.ort.InferenceSession")
    def test_explicit_intra_threads_override(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu", intra_threads=3)

        opts = mock_cls.call_args[0][1]
        assert opts.intra_op_num_threads == 3

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "2"})
    @patch("piper_plus.engine.ort.InferenceSession")
    def test_env_piper_intra_threads_overrides_arg(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu", intra_threads=4)

        opts = mock_cls.call_args[0][1]
        assert opts.intra_op_num_threads == 2

    @patch.dict("os.environ", {"PIPER_INTRA_THREADS": "invalid"})
    @patch("piper_plus.engine.ort.InferenceSession")
    def test_env_invalid_piper_intra_threads_falls_through(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu")

        opts = mock_cls.call_args[0][1]
        assert opts.intra_op_num_threads >= 1

    @patch("piper_plus.engine.ort.InferenceSession")
    def test_memory_arena_and_pattern_enabled(self, mock_cls, tmp_path):
        model = tmp_path / "model.onnx"
        model.write_bytes(b"dummy")

        create_ort_session(str(model), device="cpu")

        opts = mock_cls.call_args[0][1]
        assert opts.enable_cpu_mem_arena is True
        assert opts.enable_mem_pattern is True


# ===================================================================
# warmup_session
# ===================================================================


@pytest.mark.unit
class TestWarmupSession:
    """warmup_session runs dummy inferences to eliminate JIT cold start."""

    def test_warmup_runs_default_two_times(self):
        session = _make_mock_session()

        warmup_session(session)

        assert session.run.call_count == 2

    def test_warmup_with_custom_runs(self):
        session = _make_mock_session()

        warmup_session(session, runs=5)

        assert session.run.call_count == 5

    def test_warmup_zero_runs_does_nothing(self):
        session = _make_mock_session()

        warmup_session(session, runs=0)

        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "1"})
    def test_warmup_skipped_when_env_disable(self):
        session = _make_mock_session()

        warmup_session(session)

        session.run.assert_not_called()

    @patch.dict("os.environ", {"PIPER_DISABLE_WARMUP": "true"})
    def test_warmup_skipped_with_env_true(self):
        session = _make_mock_session()

        warmup_session(session)

        session.run.assert_not_called()

    def test_warmup_failure_is_non_fatal(self, caplog):
        session = _make_mock_session()
        session.run.side_effect = RuntimeError("ort error")

        with caplog.at_level(logging.WARNING):
            warmup_session(session)

        assert "Warmup failed (non-fatal)" in caplog.text

    def test_warmup_feed_contains_correct_dummy_ids(self):
        session = _make_mock_session()

        warmup_session(session)

        feed = session.run.call_args[0][1]
        ids = feed["input"]
        assert ids.shape == (1, WARMUP_PHONEME_LENGTH)
        assert ids[0, 0] == 1   # BOS
        assert ids[0, -1] == 2  # EOS
        assert ids[0, 1] == 8   # filler

    def test_warmup_includes_sid_when_session_has_sid_input(self):
        session = _make_mock_session(has_sid=True)

        warmup_session(session)

        feed = session.run.call_args[0][1]
        assert "sid" in feed

    def test_warmup_includes_prosody_when_session_has_prosody_input(self):
        session = _make_mock_session(has_prosody=True)

        warmup_session(session)

        feed = session.run.call_args[0][1]
        assert "prosody_features" in feed
        assert feed["prosody_features"].shape == (1, WARMUP_PHONEME_LENGTH, 3)


# ===================================================================
# synthesize
# ===================================================================


@pytest.mark.unit
class TestSynthesize:
    """synthesize() builds feed dict and returns int16 audio."""

    def test_returns_int16_array(self):
        session = _make_mock_session()

        result = synthesize(session, [1, 8, 5, 2])

        assert result.dtype == np.int16

    def test_returns_1d_array(self):
        session = _make_mock_session()

        result = synthesize(session, [1, 8, 5, 2])

        assert result.ndim == 1

    def test_returns_empty_for_empty_phoneme_ids(self):
        session = _make_mock_session()

        result = synthesize(session, [])

        assert len(result) == 0
        assert result.dtype == np.int16

    def test_passes_speaker_id_when_session_has_sid(self):
        session = _make_mock_session(has_sid=True)

        synthesize(session, [1, 8, 2], speaker_id=5)

        feed = session.run.call_args[0][1]
        np.testing.assert_array_equal(feed["sid"], np.array([5], dtype=np.int64))

    def test_passes_language_id_when_session_has_lid(self):
        session = _make_mock_session(has_lid=True)

        synthesize(session, [1, 8, 2], language_id=3)

        feed = session.run.call_args[0][1]
        np.testing.assert_array_equal(feed["lid"], np.array([3], dtype=np.int64))

    def test_does_not_pass_lid_when_language_id_is_none(self):
        session = _make_mock_session(has_lid=True)

        synthesize(session, [1, 8, 2], language_id=None)

        feed = session.run.call_args[0][1]
        assert "lid" not in feed

    def test_passes_scales_correctly(self):
        session = _make_mock_session()

        synthesize(
            session, [1, 8, 2],
            noise_scale=0.5, length_scale=1.2, noise_w=0.3,
        )

        feed = session.run.call_args[0][1]
        scales = feed["scales"]
        np.testing.assert_allclose(scales, [0.5, 1.2, 0.3], atol=1e-6)

    def test_prosody_features_padded_when_shorter(self):
        session = _make_mock_session(has_prosody=True)
        phoneme_ids = [1, 8, 5, 2]  # length 4
        prosody = [{"a1": 1, "a2": 2, "a3": 3}]  # length 1

        synthesize(session, phoneme_ids, prosody_features=prosody)

        feed = session.run.call_args[0][1]
        pf = feed["prosody_features"]
        assert pf.shape == (1, 4, 3)

    def test_prosody_features_truncated_when_longer(self):
        session = _make_mock_session(has_prosody=True)
        phoneme_ids = [1, 2]  # length 2
        prosody = [
            {"a1": 1, "a2": 2, "a3": 3},
            {"a1": 4, "a2": 5, "a3": 6},
            {"a1": 7, "a2": 8, "a3": 9},
        ]  # length 3

        synthesize(session, phoneme_ids, prosody_features=prosody)

        feed = session.run.call_args[0][1]
        pf = feed["prosody_features"]
        assert pf.shape == (1, 2, 3)

    def test_prosody_features_none_entries_become_zeros(self):
        session = _make_mock_session(has_prosody=True)

        synthesize(
            session, [1, 8, 2],
            prosody_features=[None, {"a1": 1, "a2": 2, "a3": 3}, None],
        )

        feed = session.run.call_args[0][1]
        pf = feed["prosody_features"]
        np.testing.assert_array_equal(pf[0, 0], [0, 0, 0])
        np.testing.assert_array_equal(pf[0, 1], [1, 2, 3])
        np.testing.assert_array_equal(pf[0, 2], [0, 0, 0])

    def test_prosody_features_zero_filled_when_none_list(self):
        session = _make_mock_session(has_prosody=True)

        synthesize(session, [1, 8, 2], prosody_features=None)

        feed = session.run.call_args[0][1]
        pf = feed["prosody_features"]
        assert pf.shape == (1, 3, 3)
        np.testing.assert_array_equal(pf, np.zeros((1, 3, 3), dtype=np.int64))


# ===================================================================
# synthesize_float
# ===================================================================


@pytest.mark.unit
class TestSynthesizeFloat:
    """synthesize_float returns float32 audio in [-1, 1]."""

    def test_returns_float32_array(self):
        session = _make_mock_session()

        result = synthesize_float(session, [1, 8, 2])

        assert result.dtype == np.float32

    def test_returns_empty_for_empty_ids(self):
        session = _make_mock_session()

        result = synthesize_float(session, [])

        assert len(result) == 0
        assert result.dtype == np.float32

    def test_output_clipped_to_valid_range(self):
        session = _make_mock_session()
        # Simulate out-of-range output
        session.run.return_value = [np.array([[[2.0, -2.0, 0.5]]], dtype=np.float32)]

        result = synthesize_float(session, [1, 8, 2])

        assert result.max() <= 1.0
        assert result.min() >= -1.0
