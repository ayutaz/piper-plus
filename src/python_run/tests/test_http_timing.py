"""Tests for HTTP phoneme timing endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

flask = pytest.importorskip("flask")

from flask import Flask, jsonify, request  # noqa: E402

from piper.timing import (  # noqa: E402
    PhonemeTimingInfo,
    TimingResult,
    timing_to_json,
    timing_to_tsv,
)


@pytest.fixture
def mock_timing_result():
    """Sample TimingResult for testing."""
    return TimingResult(
        phonemes=[
            PhonemeTimingInfo(
                phoneme="^", start_ms=0.0, end_ms=58.0, duration_ms=58.0
            ),
            PhonemeTimingInfo(
                phoneme="k", start_ms=58.0, end_ms=150.8, duration_ms=92.8
            ),
            PhonemeTimingInfo(
                phoneme="o", start_ms=150.8, end_ms=290.0, duration_ms=139.2
            ),
        ],
        total_duration_ms=290.0,
        sample_rate=22050,
    )


def _create_app(mock_voice: MagicMock) -> Flask:
    """Build a Flask app wired to *mock_voice*."""
    app = Flask(__name__)

    @app.route("/api/phoneme-timing", methods=["GET", "POST"])
    def app_phoneme_timing():
        if request.method == "POST":
            text = request.data.decode("utf-8")
        else:
            text = request.args.get("text", "")

        text = text.strip()
        if not text:
            return jsonify({"error": "No text provided"}), 400

        fmt = request.args.get("format", "json")

        if fmt not in ("json", "tsv"):
            return jsonify({"error": f"Unsupported format: {fmt}"}), 400

        # Resolve language_id (mirrors http_server.py logic)
        language_id: int | None = None
        language_id_raw = request.args.get("language_id", None)
        language = request.args.get("language", None)

        if language_id_raw is not None:
            try:
                language_id = int(language_id_raw)
            except (ValueError, TypeError):
                language_id = None
        elif language is not None:
            language_id_map = mock_voice.config.language_id_map
            if language_id_map:
                language_id = language_id_map.get(language)

        _, timing_result = mock_voice.synthesize_with_timing(
            text, language_id=language_id
        )

        if timing_result is None:
            return (
                jsonify({"error": "Model does not support duration output"}),
                400,
            )

        if fmt == "tsv":
            return (
                timing_to_tsv(timing_result),
                200,
                {"Content-Type": "text/tab-separated-values"},
            )

        return (
            timing_to_json(timing_result),
            200,
            {"Content-Type": "application/json"},
        )

    return app


@pytest.fixture
def app(mock_timing_result):
    """Create Flask test app with mocked voice that returns timing."""
    mock_voice = MagicMock()
    mock_voice.synthesize_with_timing.return_value = (
        b"fake-wav",
        mock_timing_result,
    )
    mock_voice.config.language_id_map = None
    return _create_app(mock_voice)


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


class TestTimingEndpointJSON:
    """POST text -> JSON response with phonemes array."""

    def test_timing_endpoint_json(self, client, mock_timing_result):
        resp = client.post(
            "/api/phoneme-timing",
            data="konnichiwa",
        )
        assert resp.status_code == 200
        assert resp.content_type == "application/json"

        body = json.loads(resp.data)
        assert "phonemes" in body
        assert len(body["phonemes"]) == 3
        assert body["phonemes"][0]["phoneme"] == "^"
        assert body["phonemes"][1]["phoneme"] == "k"
        assert body["phonemes"][2]["phoneme"] == "o"
        assert body["total_duration_ms"] == pytest.approx(290.0)
        assert body["sample_rate"] == 22050

    def test_phoneme_timing_fields(self, client):
        """Each phoneme entry has start_ms, end_ms, duration_ms, phoneme."""
        resp = client.post("/api/phoneme-timing", data="hello")
        body = json.loads(resp.data)
        for entry in body["phonemes"]:
            assert "phoneme" in entry
            assert "start_ms" in entry
            assert "end_ms" in entry
            assert "duration_ms" in entry


class TestTimingEndpointTSV:
    """POST text with format=tsv -> TSV response."""

    def test_timing_endpoint_tsv(self, client):
        resp = client.post(
            "/api/phoneme-timing?format=tsv",
            data="konnichiwa",
        )
        assert resp.status_code == 200
        assert resp.content_type == "text/tab-separated-values"

        text = resp.data.decode("utf-8")
        lines = text.strip().split("\n")
        # Header + 3 data lines
        assert len(lines) == 4

        header = lines[0]
        assert header == "start_ms\tend_ms\tduration_ms\tphoneme"

        # First data line should be the "^" phoneme
        cols = lines[1].split("\t")
        assert len(cols) == 4
        assert cols[3] == "^"
        assert cols[0] == "0.000"


class TestTimingEndpointErrors:
    """Error cases for the phoneme-timing endpoint."""

    def test_timing_endpoint_no_text_post(self, client):
        """POST with empty body returns 400."""
        resp = client.post("/api/phoneme-timing", data="")
        assert resp.status_code == 400
        body = json.loads(resp.data)
        assert "error" in body

    def test_timing_endpoint_no_text_get(self, client):
        """GET without text param returns 400."""
        resp = client.get("/api/phoneme-timing")
        assert resp.status_code == 400
        body = json.loads(resp.data)
        assert "error" in body

    def test_timing_endpoint_whitespace_only(self, client):
        """POST with whitespace-only body returns 400."""
        resp = client.post("/api/phoneme-timing", data="   \n  ")
        assert resp.status_code == 400

    def test_timing_endpoint_no_duration_support(self):
        """When synthesize_with_timing returns None timing, respond 400."""
        mock_voice = MagicMock()
        mock_voice.synthesize_with_timing.return_value = (b"fake-wav", None)
        mock_voice.config.language_id_map = None

        none_app = _create_app(mock_voice)
        client = none_app.test_client()
        resp = client.post("/api/phoneme-timing", data="hello")
        assert resp.status_code == 400
        body = json.loads(resp.data)
        assert "duration" in body["error"].lower() or "support" in body["error"].lower()


class TestTimingEndpointGET:
    """GET requests with text query parameter."""

    def test_timing_endpoint_get(self, client):
        resp = client.get("/api/phoneme-timing?text=hello")
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert "phonemes" in body
        assert len(body["phonemes"]) == 3

    def test_timing_endpoint_get_tsv(self, client):
        resp = client.get("/api/phoneme-timing?text=hello&format=tsv")
        assert resp.status_code == 200
        assert resp.content_type == "text/tab-separated-values"


class TestTimingEndpointFormatValidation:
    """Tests for format parameter validation."""

    def test_invalid_format_returns_400(self, client):
        """Unsupported format (e.g., xml) should return 400."""
        resp = client.get("/api/phoneme-timing?text=hello&format=xml")
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data
        assert "xml" in data["error"].lower() or "unsupported" in data["error"].lower()


class TestTimingEndpointLanguageResolution:
    """Tests for language_id / language query parameter resolution.

    The endpoint supports two forms:
    - `?language_id=N` — use integer directly
    - `?language=<code>` — look up in voice.config.language_id_map
    """

    def test_language_id_numeric_parameter_accepted(self, mock_timing_result):
        """GET with ?language_id=3 succeeds and returns timing JSON."""
        from flask import Flask, jsonify, request

        from piper.timing import timing_to_json, timing_to_tsv

        captured = {}
        mock_voice = MagicMock()
        mock_voice.config.language_id_map = {"ja": 0, "en": 1}

        def _synth(text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            return (b"fake-wav", mock_timing_result)

        mock_voice.synthesize_with_timing.side_effect = _synth

        app = Flask(__name__)

        @app.route("/api/phoneme-timing", methods=["GET", "POST"])
        def handler():
            text = (
                request.data.decode("utf-8")
                if request.method == "POST"
                else request.args.get("text", "")
            )
            text = text.strip()
            if not text:
                return jsonify({"error": "No text provided"}), 400

            fmt = request.args.get("format", "json").lower()
            if fmt not in ("json", "tsv"):
                return jsonify({"error": f"Unsupported format: {fmt}"}), 400

            language_id = None
            language_id_raw = request.args.get("language_id", None)
            language = request.args.get("language", None)
            if language_id_raw is not None:
                try:
                    language_id = int(language_id_raw)
                except (ValueError, TypeError):
                    language_id = None
            elif language is not None:
                lmap = mock_voice.config.language_id_map
                if lmap:
                    language_id = lmap.get(language)

            _, timing = mock_voice.synthesize_with_timing(
                text, language_id=language_id
            )
            if timing is None:
                return jsonify({"error": "Model does not support duration output"}), 400
            if fmt == "tsv":
                return (
                    timing_to_tsv(timing),
                    200,
                    {"Content-Type": "text/tab-separated-values"},
                )
            return (
                timing_to_json(timing),
                200,
                {"Content-Type": "application/json"},
            )

        client = app.test_client()
        resp = client.get("/api/phoneme-timing?text=hello&language_id=3")
        assert resp.status_code == 200
        assert captured["language_id"] == 3

    def test_language_code_resolved_via_language_id_map(self, mock_timing_result):
        """GET with ?language=ja looks up language_id_map and passes 0."""
        from flask import Flask, jsonify, request

        from piper.timing import timing_to_json, timing_to_tsv

        captured = {}
        mock_voice = MagicMock()
        mock_voice.config.language_id_map = {"ja": 0, "en": 1, "zh": 2}

        def _synth(text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            return (b"fake-wav", mock_timing_result)

        mock_voice.synthesize_with_timing.side_effect = _synth

        app = Flask(__name__)

        @app.route("/api/phoneme-timing", methods=["GET", "POST"])
        def handler():
            text = request.args.get("text", "").strip()
            if not text:
                return jsonify({"error": "No text provided"}), 400
            fmt = request.args.get("format", "json").lower()
            if fmt not in ("json", "tsv"):
                return jsonify({"error": f"Unsupported format: {fmt}"}), 400

            language_id = None
            language = request.args.get("language", None)
            language_id_raw = request.args.get("language_id", None)
            if language_id_raw is not None:
                try:
                    language_id = int(language_id_raw)
                except (ValueError, TypeError):
                    language_id = None
            elif language is not None:
                lmap = mock_voice.config.language_id_map
                if lmap:
                    language_id = lmap.get(language)

            _, timing = mock_voice.synthesize_with_timing(
                text, language_id=language_id
            )
            if timing is None:
                return jsonify({"error": "no duration support"}), 400
            if fmt == "tsv":
                return timing_to_tsv(timing), 200, {"Content-Type": "text/tab-separated-values"}
            return timing_to_json(timing), 200, {"Content-Type": "application/json"}

        client = app.test_client()
        resp = client.get("/api/phoneme-timing?text=hello&language=zh")
        assert resp.status_code == 200
        assert captured["language_id"] == 2

    def test_invalid_language_id_falls_back_to_none(self, mock_timing_result):
        """Non-integer language_id falls back to None (gracefully)."""
        from flask import Flask, jsonify, request

        from piper.timing import timing_to_json

        captured = {}
        mock_voice = MagicMock()
        mock_voice.config.language_id_map = None

        def _synth(text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            return (b"fake-wav", mock_timing_result)

        mock_voice.synthesize_with_timing.side_effect = _synth

        app = Flask(__name__)

        @app.route("/api/phoneme-timing", methods=["GET", "POST"])
        def handler():
            text = request.args.get("text", "").strip()
            if not text:
                return jsonify({"error": "No text provided"}), 400
            fmt = request.args.get("format", "json").lower()
            if fmt not in ("json", "tsv"):
                return jsonify({"error": f"Unsupported format: {fmt}"}), 400

            language_id = None
            language_id_raw = request.args.get("language_id", None)
            if language_id_raw is not None:
                try:
                    language_id = int(language_id_raw)
                except (ValueError, TypeError):
                    language_id = None

            _, timing = mock_voice.synthesize_with_timing(
                text, language_id=language_id
            )
            return timing_to_json(timing), 200, {"Content-Type": "application/json"}

        client = app.test_client()
        resp = client.get("/api/phoneme-timing?text=hello&language_id=not-an-int")
        assert resp.status_code == 200
        assert captured["language_id"] is None

    def test_unknown_language_code_returns_none(self, mock_timing_result):
        """Unknown language code (not in language_id_map) resolves to None."""
        from flask import Flask, jsonify, request

        from piper.timing import timing_to_json

        captured = {}
        mock_voice = MagicMock()
        mock_voice.config.language_id_map = {"ja": 0, "en": 1}

        def _synth(text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            return (b"fake-wav", mock_timing_result)

        mock_voice.synthesize_with_timing.side_effect = _synth

        app = Flask(__name__)

        @app.route("/api/phoneme-timing", methods=["GET", "POST"])
        def handler():
            text = request.args.get("text", "").strip()
            if not text:
                return jsonify({"error": "No text provided"}), 400
            fmt = request.args.get("format", "json").lower()
            if fmt not in ("json", "tsv"):
                return jsonify({"error": f"Unsupported format: {fmt}"}), 400

            language_id = None
            language_id_raw = request.args.get("language_id", None)
            language = request.args.get("language", None)
            if language_id_raw is not None:
                try:
                    language_id = int(language_id_raw)
                except (ValueError, TypeError):
                    language_id = None
            elif language is not None:
                lmap = mock_voice.config.language_id_map
                if lmap:
                    language_id = lmap.get(language)

            _, timing = mock_voice.synthesize_with_timing(
                text, language_id=language_id
            )
            return timing_to_json(timing), 200, {"Content-Type": "application/json"}

        client = app.test_client()
        resp = client.get("/api/phoneme-timing?text=hello&language=fr")
        # Unknown language returns None (lmap.get returns None for missing keys)
        assert resp.status_code == 200
        assert captured["language_id"] is None
