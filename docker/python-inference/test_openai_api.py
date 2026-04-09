#!/usr/bin/env python3
"""
Tests for OpenAI-compatible API endpoints in inference.py.

Uses FastAPI TestClient with a mocked PiperInferenceEngine
so no ONNX model is required.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient


# Ensure inference.py can be imported from this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from inference import create_app  # noqa: E402


@pytest.fixture()
def mock_engine():
    """Create a mocked PiperInferenceEngine."""
    engine = MagicMock()
    engine.sample_rate = 22050
    engine.language_id_map = {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5}

    # synthesize returns 0.5s of silence as int16
    samples = int(engine.sample_rate * 0.5)
    engine.synthesize.return_value = np.zeros(samples, dtype=np.int16)
    return engine


@pytest.fixture()
def client(mock_engine):
    """Create a FastAPI TestClient backed by the mocked engine."""
    # Use this test file as a stand-in for stat().st_mtime
    app = create_app(mock_engine, __file__)
    return TestClient(app)


# ---- /v1/audio/speech ----


class TestOpenAISpeech:
    def test_basic_synthesis(self, client, mock_engine):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "こんにちは"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        assert len(resp.content) > 0
        mock_engine.synthesize.assert_called_once()

    def test_speed_to_length_scale(self, client, mock_engine):
        """speed=2.0 should become length_scale=0.5."""
        client.post(
            "/v1/audio/speech",
            json={"input": "test", "speed": 2.0},
        )
        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["length_scale"] == pytest.approx(0.5)

    def test_speed_half(self, client, mock_engine):
        """speed=0.5 should become length_scale=2.0."""
        client.post(
            "/v1/audio/speech",
            json={"input": "test", "speed": 0.5},
        )
        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["length_scale"] == pytest.approx(2.0)

    def test_custom_language(self, client, mock_engine):
        client.post(
            "/v1/audio/speech",
            json={"input": "hello", "language": "en"},
        )
        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["language"] == "en"

    def test_custom_speaker_id(self, client, mock_engine):
        client.post(
            "/v1/audio/speech",
            json={"input": "hello", "speaker_id": 5},
        )
        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["speaker_id"] == 5

    def test_custom_noise_params(self, client, mock_engine):
        client.post(
            "/v1/audio/speech",
            json={"input": "test", "noise_scale": 0.3, "noise_w": 0.5},
        )
        call_kwargs = mock_engine.synthesize.call_args
        assert call_kwargs.kwargs["noise_scale"] == pytest.approx(0.3)
        assert call_kwargs.kwargs["noise_scale_w"] == pytest.approx(0.5)

    def test_empty_input_returns_400(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": ""},
        )
        assert resp.status_code == 400

    def test_whitespace_input_returns_400(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "   "},
        )
        assert resp.status_code == 400

    def test_unsupported_format_returns_400(self, client):
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test", "response_format": "mp3"},
        )
        assert resp.status_code == 400
        assert "mp3" in resp.json()["detail"]

    def test_speed_zero_returns_422(self, client):
        """speed must be > 0."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test", "speed": 0.0},
        )
        assert resp.status_code == 422

    def test_speed_over_max_returns_422(self, client):
        """speed must be <= 4.0."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test", "speed": 5.0},
        )
        assert resp.status_code == 422

    def test_engine_error_returns_500(self, client, mock_engine):
        mock_engine.synthesize.side_effect = RuntimeError("ONNX error")
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test"},
        )
        assert resp.status_code == 500

    def test_model_and_voice_ignored(self, client, mock_engine):
        """model and voice fields are accepted but don't affect synthesis."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "test", "model": "tts-1", "voice": "alloy"},
        )
        assert resp.status_code == 200


# ---- /v1/models ----


class TestOpenAIModels:
    def test_models_list(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        model = data["data"][0]
        assert model["id"] == "piper-plus"
        assert model["object"] == "model"
        assert model["owned_by"] == "piper-plus"
        assert isinstance(model["created"], int)


# ---- /v1/audio/speech/languages ----


class TestLanguages:
    def test_languages_list(self, client):
        resp = client.get("/v1/audio/speech/languages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["languages"] == ["en", "es", "fr", "ja", "pt", "zh"]

    def test_languages_sorted(self, client):
        resp = client.get("/v1/audio/speech/languages")
        languages = resp.json()["languages"]
        assert languages == sorted(languages)


# ---- existing endpoints still work ----


class TestExistingEndpoints:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}

    def test_synthesize_get(self, client, mock_engine):
        resp = client.get("/synthesize", params={"text": "hello"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/wav"
        mock_engine.synthesize.assert_called_once()


# ---- short-text warning ----


class TestShortTextWarning:
    """Strategy E: X-Piper-Warning header for short text inputs."""

    def test_short_text_has_warning_header(self, client):
        """Text with <=10 non-space chars should get the warning header."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "hello"},  # 5 chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_short_text_ja_has_warning_header(self, client):
        """Japanese short text should also trigger the warning."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "こんにちは", "language": "ja"},  # 5 chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_long_text_no_warning_header(self, client):
        """Text with >10 non-space chars should NOT get the warning header."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "This is a sufficiently long sentence for testing."},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") is None

    def test_boundary_10_chars_has_warning(self, client):
        """Exactly 10 non-space chars should still trigger the warning."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "1234567890"},  # exactly 10 chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_boundary_11_chars_no_warning(self, client):
        """11 non-space chars should NOT trigger the warning."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "12345678901"},  # 11 chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") is None

    def test_spaces_excluded_from_count(self, client):
        """Spaces should not count toward the character threshold."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "a b c d e"},  # 5 non-space chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_fullwidth_spaces_excluded(self, client):
        """Full-width spaces (U+3000) should not count."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "あ\u3000い\u3000う"},  # 3 non-space chars
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_synthesize_get_short_text_warning(self, client):
        """GET /synthesize should also include the warning for short text."""
        resp = client.get("/synthesize", params={"text": "hi"})
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") == "short-text-input"

    def test_synthesize_get_long_text_no_warning(self, client):
        """GET /synthesize should NOT include the warning for long text."""
        resp = client.get(
            "/synthesize",
            params={"text": "This is a long enough sentence."},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") is None

    def test_ssml_short_text_no_warning(self, client):
        """SSML text starting with <speak> should NOT trigger short-text warning."""
        resp = client.post(
            "/v1/audio/speech",
            json={"input": "<speak>Hi</speak>"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") is None

    def test_ssml_synthesize_get_no_warning(self, client):
        """GET /synthesize with SSML should NOT trigger short-text warning."""
        resp = client.get(
            "/synthesize",
            params={"text": "<speak>Hi</speak>"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-piper-warning") is None


# ---- CORS ----


class TestCORS:
    def test_cors_headers(self, client):
        resp = client.options(
            "/v1/audio/speech",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.headers.get("access-control-allow-origin") is not None
