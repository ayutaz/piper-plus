"""Tests for PiperPlus -- high-level Python API for multilingual neural TTS.

Verifies initialization, synthesize() behaviour, parameter validation,
streaming, and the list_models() class method.
Uses mocks for ORT sessions and model resolution to keep tests fast and unit-level.
Follows t-wada TDD principles: behaviour-driven naming, Arrange-Act-Assert,
triangulation, and DAMP (descriptive and meaningful phrases).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from piper_plus.api import PiperPlus, _split_sentences
from piper_plus.audio import AudioResult


# ===================================================================
# Helper: build a minimal config dict
# ===================================================================


def _make_config(
    *,
    sample_rate: int = 22050,
    language_id_map: dict | None = None,
    speaker_id_map: dict | None = None,
) -> dict:
    config = {
        "audio": {"sample_rate": sample_rate},
        "phoneme_id_map": {"a": [1], "b": [2], "_": [0]},
    }
    if language_id_map is not None:
        config["language_id_map"] = language_id_map
    if speaker_id_map is not None:
        config["speaker_id_map"] = speaker_id_map
    return config


def _write_config(tmp_path: Path, config: dict | None = None) -> tuple[Path, Path]:
    """Write a dummy ONNX + config and return (onnx_path, config_path)."""
    config = config or _make_config()
    onnx = tmp_path / "model.onnx"
    cfg = tmp_path / "config.json"
    onnx.write_bytes(b"fake-onnx-model")
    cfg.write_text(json.dumps(config), encoding="utf-8")
    return onnx, cfg


def _make_mock_session(
    *, has_sid: bool = False, has_lid: bool = False, has_prosody: bool = False
) -> MagicMock:
    """Create a mock ORT InferenceSession."""
    session = MagicMock()
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
    session.get_providers.return_value = ["CPUExecutionProvider"]
    out = MagicMock()
    out.name = "output"
    session.get_outputs.return_value = [out]
    session.run.return_value = [np.random.randn(1, 1, 500).astype(np.float32)]
    return session


# ===================================================================
# _split_sentences (internal helper exposed for testing)
# ===================================================================


@pytest.mark.unit
class TestSplitSentences:
    """_split_sentences divides text at sentence boundaries."""

    def test_splits_at_period(self):
        result = _split_sentences("Hello. World.")
        assert result == ["Hello.", "World."]

    def test_splits_at_exclamation_mark(self):
        result = _split_sentences("Hello! World!")
        assert result == ["Hello!", "World!"]

    def test_splits_at_question_mark(self):
        result = _split_sentences("Hello? World?")
        assert result == ["Hello?", "World?"]

    def test_returns_single_sentence_without_boundary(self):
        result = _split_sentences("Hello World")
        assert result == ["Hello World"]

    def test_returns_empty_for_empty_string(self):
        result = _split_sentences("")
        assert result == []

    def test_strips_whitespace_from_segments(self):
        result = _split_sentences("Hello.   World.")
        assert all(s == s.strip() for s in result)

    def test_handles_cjk_period(self):
        result = _split_sentences("hello\u3002world\u3002")
        assert len(result) >= 1


# ===================================================================
# PiperPlus.__init__
# ===================================================================


@pytest.mark.unit
class TestPiperPlusInit:
    """PiperPlus initialization loads model, config, and creates ORT session."""

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_init_with_direct_path(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config()
        mock_session = _make_mock_session()
        mock_create.return_value = mock_session

        tts = PiperPlus(str(onnx), device="cpu")

        mock_resolve.assert_called_once()
        mock_load_config.assert_called_once_with(cfg)
        mock_create.assert_called_once()
        mock_warmup.assert_called_once_with(mock_session, mock_load_config.return_value)

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_sample_rate_from_config(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config(sample_rate=44100)
        mock_create.return_value = _make_mock_session()

        tts = PiperPlus(str(onnx), device="cpu")

        assert tts.sample_rate == 44100

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_languages_from_language_id_map(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config(
            language_id_map={"ja": 0, "en": 1, "zh": 2}
        )
        mock_create.return_value = _make_mock_session(has_lid=True)

        tts = PiperPlus(str(onnx), device="cpu")

        assert sorted(tts.languages) == ["en", "ja", "zh"]

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_speakers_from_speaker_id_map(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config(
            speaker_id_map={"alice": 0, "bob": 1}
        )
        mock_create.return_value = _make_mock_session()

        tts = PiperPlus(str(onnx), device="cpu")

        assert tts.speakers == {"alice": 0, "bob": 1}

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_speakers_empty_for_single_speaker_model(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config()
        mock_create.return_value = _make_mock_session()

        tts = PiperPlus(str(onnx), device="cpu")

        assert tts.speakers == {}

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_default_scales(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config()
        mock_create.return_value = _make_mock_session()

        tts = PiperPlus(str(onnx), device="cpu")

        assert tts.noise_scale == pytest.approx(0.667)
        assert tts.length_scale == pytest.approx(1.0)
        assert tts.noise_scale_w == pytest.approx(0.8)

    @patch("piper_plus.api.warmup_session")
    @patch("piper_plus.api.create_ort_session")
    @patch("piper_plus.api.load_config")
    @patch("piper_plus.api.resolve_model")
    def test_custom_scales(
        self, mock_resolve, mock_load_config, mock_create, mock_warmup, tmp_path
    ):
        onnx, cfg = _write_config(tmp_path)
        mock_resolve.return_value = (onnx, cfg)
        mock_load_config.return_value = _make_config()
        mock_create.return_value = _make_mock_session()

        tts = PiperPlus(
            str(onnx), device="cpu",
            noise_scale=0.5, length_scale=1.5, noise_scale_w=0.3,
        )

        assert tts.noise_scale == pytest.approx(0.5)
        assert tts.length_scale == pytest.approx(1.5)
        assert tts.noise_scale_w == pytest.approx(0.3)


# ===================================================================
# PiperPlus.synthesize -- normal cases
# ===================================================================


def _build_tts(tmp_path, *, config=None, session=None):
    """Construct a PiperPlus instance with all external deps mocked."""
    onnx, cfg = _write_config(tmp_path, config)
    config = config or _make_config()
    session = session or _make_mock_session()
    with (
        patch("piper_plus.api.resolve_model", return_value=(onnx, cfg)),
        patch("piper_plus.api.load_config", return_value=config),
        patch("piper_plus.api.create_ort_session", return_value=session),
        patch("piper_plus.api.warmup_session"),
    ):
        return PiperPlus(str(onnx), device="cpu")


@pytest.mark.unit
class TestPiperPlusSynthesize:
    """PiperPlus.synthesize() returns AudioResult from text input."""

    def test_synthesize_returns_audio_result(self, tmp_path):
        tts = _build_tts(tmp_path)
        # Mock _phonemize to return deterministic data
        tts._phonemize = MagicMock(return_value=([1, 8, 5, 2], [None, None, None, None], None))

        result = tts.synthesize("test text")

        assert isinstance(result, AudioResult)

    def test_synthesize_returns_int16_audio(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts._phonemize = MagicMock(return_value=([1, 8, 2], [None, None, None], None))

        result = tts.synthesize("test")

        assert result.audio.dtype == np.int16

    def test_synthesize_audio_result_has_correct_sample_rate(self, tmp_path):
        config = _make_config(sample_rate=44100)
        tts = _build_tts(tmp_path, config=config)
        tts._phonemize = MagicMock(return_value=([1, 8, 2], [None, None, None], None))

        result = tts.synthesize("test")

        assert result.sample_rate == 44100

    def test_synthesize_empty_text_returns_empty_audio(self, tmp_path):
        tts = _build_tts(tmp_path)

        result = tts.synthesize("")

        assert len(result.audio) == 0
        assert result.duration == 0.0

    def test_synthesize_whitespace_only_returns_empty_audio(self, tmp_path):
        tts = _build_tts(tmp_path)

        result = tts.synthesize("   ")

        assert len(result.audio) == 0

    def test_synthesize_returns_empty_when_phonemize_yields_nothing(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts._phonemize = MagicMock(return_value=([], [], None))

        result = tts.synthesize("test")

        assert len(result.audio) == 0


# ===================================================================
# PiperPlus.synthesize -- parameter validation
# ===================================================================


@pytest.mark.unit
class TestPiperPlusSynthesizeValidation:
    """PiperPlus.synthesize raises ValueError for invalid scale parameters."""

    def test_raises_when_noise_scale_is_zero(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.noise_scale = 0.0

        with pytest.raises(ValueError, match="noise_scale"):
            tts.synthesize("hello")

    def test_raises_when_noise_scale_exceeds_upper_bound(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.noise_scale = 2.1

        with pytest.raises(ValueError, match="noise_scale"):
            tts.synthesize("hello")

    def test_raises_when_length_scale_below_lower_bound(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.length_scale = 0.05

        with pytest.raises(ValueError, match="length_scale"):
            tts.synthesize("hello")

    def test_raises_when_length_scale_exceeds_upper_bound(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.length_scale = 5.1

        with pytest.raises(ValueError, match="length_scale"):
            tts.synthesize("hello")

    def test_raises_when_noise_w_is_negative(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.noise_scale_w = -0.1

        with pytest.raises(ValueError, match="noise_w"):
            tts.synthesize("hello")

    def test_raises_when_noise_w_exceeds_upper_bound(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts.noise_scale_w = 2.1

        with pytest.raises(ValueError, match="noise_w"):
            tts.synthesize("hello")

    def test_valid_boundary_noise_scale_does_not_raise(self, tmp_path):
        """noise_scale=2.0 (upper boundary) should not raise."""
        tts = _build_tts(tmp_path)
        tts.noise_scale = 2.0
        tts._phonemize = MagicMock(return_value=([1, 2], [None, None], None))

        # Should not raise
        result = tts.synthesize("test")
        assert isinstance(result, AudioResult)

    def test_valid_boundary_length_scale_lower(self, tmp_path):
        """length_scale=0.1 (lower boundary) should not raise."""
        tts = _build_tts(tmp_path)
        tts.length_scale = 0.1
        tts._phonemize = MagicMock(return_value=([1, 2], [None, None], None))

        result = tts.synthesize("test")
        assert isinstance(result, AudioResult)

    def test_valid_boundary_noise_w_zero(self, tmp_path):
        """noise_scale_w=0.0 (lower boundary) should not raise."""
        tts = _build_tts(tmp_path)
        tts.noise_scale_w = 0.0
        tts._phonemize = MagicMock(return_value=([1, 2], [None, None], None))

        result = tts.synthesize("test")
        assert isinstance(result, AudioResult)


# ===================================================================
# PiperPlus.synthesize_stream
# ===================================================================


@pytest.mark.unit
class TestPiperPlusSynthesizeStream:
    """synthesize_stream yields AudioResult per sentence."""

    def test_yields_one_result_per_sentence(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts._phonemize = MagicMock(return_value=([1, 8, 2], [None, None, None], None))

        results = list(tts.synthesize_stream("Hello. World."))

        assert len(results) == 2
        assert all(isinstance(r, AudioResult) for r in results)

    def test_yields_nothing_for_empty_text(self, tmp_path):
        tts = _build_tts(tmp_path)

        results = list(tts.synthesize_stream(""))

        assert results == []

    def test_yields_single_result_for_single_sentence(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts._phonemize = MagicMock(return_value=([1, 8, 2], [None, None, None], None))

        results = list(tts.synthesize_stream("Hello World"))

        assert len(results) == 1


# ===================================================================
# PiperPlus.tts_to_file
# ===================================================================


@pytest.mark.unit
class TestPiperPlusTtsToFile:
    """tts_to_file synthesizes and saves to WAV."""

    def test_creates_wav_file(self, tmp_path):
        tts = _build_tts(tmp_path)
        tts._phonemize = MagicMock(return_value=([1, 8, 2], [None, None, None], None))
        out = tmp_path / "output.wav"

        result = tts.tts_to_file("test", out)

        assert out.exists()
        assert isinstance(result, AudioResult)


# ===================================================================
# PiperPlus.list_models
# ===================================================================


@pytest.mark.unit
class TestPiperPlusListModels:
    """PiperPlus.list_models() returns available model aliases."""

    def test_returns_dict(self):
        models = PiperPlus.list_models()
        assert isinstance(models, dict)

    def test_contains_known_aliases(self):
        models = PiperPlus.list_models()
        assert "tsukuyomi" in models
        assert "base" in models

    def test_returns_copy_not_reference(self):
        """Mutating the returned dict does not affect internal state."""
        models_a = PiperPlus.list_models()
        models_a["fake"] = {"repo_id": "test"}
        models_b = PiperPlus.list_models()
        assert "fake" not in models_b


# ===================================================================
# PiperPlus.config property
# ===================================================================


@pytest.mark.unit
class TestPiperPlusConfigProperty:
    """PiperPlus.config returns a copy of the model config."""

    def test_config_returns_dict(self, tmp_path):
        tts = _build_tts(tmp_path)

        assert isinstance(tts.config, dict)

    def test_config_returns_copy(self, tmp_path):
        tts = _build_tts(tmp_path)

        cfg1 = tts.config
        cfg1["injected_key"] = True
        cfg2 = tts.config

        assert "injected_key" not in cfg2
