"""Tests for the FastAPI HTTP server (synthesis + phoneme timing endpoints)."""

from __future__ import annotations

import io
import json
import struct
import wave
from unittest.mock import MagicMock

import pytest


pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from piper.http_server import create_app  # noqa: E402
from piper.timing import PhonemeTimingInfo, TimingResult  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_timing_result() -> TimingResult:
    """Sample TimingResult covering 3 phonemes."""
    return TimingResult(
        phonemes=[
            PhonemeTimingInfo(phoneme="^", start_ms=0.0, end_ms=58.0, duration_ms=58.0),
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


def _make_voice(
    timing_result: TimingResult | None,
    language_id_map: dict[str, int] | None = None,
    sample_rate: int = 22050,
) -> MagicMock:
    """Build a mock voice that mimics PiperVoice's relevant attributes."""
    mock_voice = MagicMock()
    mock_voice.config.language_id_map = language_id_map
    mock_voice.config.sample_rate = sample_rate
    mock_voice.synthesize_with_timing.return_value = (b"fake-wav", timing_result)

    def _fake_synth(text, wav_file, **_kwargs):
        wav_file.setframerate(sample_rate)
        wav_file.setsampwidth(2)
        wav_file.setnchannels(1)
        wav_file.writeframes(b"\x00\x00" * 100)

    mock_voice.synthesize.side_effect = _fake_synth

    def _fake_stream_raw(_text, **_kwargs):
        # Two PCM "sentences" of 100 samples (200 bytes) each.
        yield b"\x01\x00" * 100
        yield b"\x02\x00" * 100

    mock_voice.synthesize_stream_raw.side_effect = _fake_stream_raw
    return mock_voice


@pytest.fixture
def client(mock_timing_result) -> TestClient:
    voice = _make_voice(mock_timing_result)
    app = create_app(voice, synthesize_args={})
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/phoneme-timing — JSON / TSV happy paths
# ---------------------------------------------------------------------------


class TestTimingEndpointJSON:
    """POST text → JSON response with phonemes array."""

    def test_timing_endpoint_json(self, client, mock_timing_result):
        resp = client.post("/api/phoneme-timing", content="konnichiwa")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")

        body = resp.json()
        assert "phonemes" in body
        assert len(body["phonemes"]) == 3
        assert body["phonemes"][0]["phoneme"] == "^"
        assert body["phonemes"][1]["phoneme"] == "k"
        assert body["phonemes"][2]["phoneme"] == "o"
        assert body["total_duration_ms"] == pytest.approx(290.0)
        assert body["sample_rate"] == 22050

    def test_phoneme_timing_fields(self, client):
        resp = client.post("/api/phoneme-timing", content="hello")
        body = resp.json()
        for entry in body["phonemes"]:
            assert "phoneme" in entry
            assert "start_ms" in entry
            assert "end_ms" in entry
            assert "duration_ms" in entry


class TestTimingEndpointTSV:
    """POST text with format=tsv → TSV response."""

    def test_timing_endpoint_tsv(self, client):
        resp = client.post("/api/phoneme-timing?format=tsv", content="konnichiwa")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/tab-separated-values")

        text = resp.text
        lines = text.strip().split("\n")
        assert len(lines) == 4  # header + 3 data lines
        assert lines[0] == "start_ms\tend_ms\tduration_ms\tphoneme"

        cols = lines[1].split("\t")
        assert len(cols) == 4
        assert cols[3] == "^"
        assert cols[0] == "0.000"


# ---------------------------------------------------------------------------
# /api/phoneme-timing — error cases
# ---------------------------------------------------------------------------


class TestTimingEndpointErrors:
    def test_no_text_post(self, client):
        resp = client.post("/api/phoneme-timing", content="")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_no_text_get(self, client):
        resp = client.get("/api/phoneme-timing")
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_whitespace_only(self, client):
        resp = client.post("/api/phoneme-timing", content="   \n  ")
        assert resp.status_code == 400

    def test_no_duration_support(self):
        voice = _make_voice(timing_result=None)
        client = TestClient(create_app(voice, synthesize_args={}))
        resp = client.post("/api/phoneme-timing", content="hello")
        assert resp.status_code == 400
        body = resp.json()
        assert "duration" in body["error"].lower() or "support" in body["error"].lower()


class TestTimingEndpointGET:
    def test_get_json(self, client):
        resp = client.get("/api/phoneme-timing?text=hello")
        assert resp.status_code == 200
        body = resp.json()
        assert "phonemes" in body
        assert len(body["phonemes"]) == 3

    def test_get_tsv(self, client):
        resp = client.get("/api/phoneme-timing?text=hello&format=tsv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/tab-separated-values")


class TestTimingEndpointFormatValidation:
    def test_invalid_format_returns_400(self, client):
        resp = client.get("/api/phoneme-timing?text=hello&format=xml")
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "xml" in body["error"].lower() or "unsupported" in body["error"].lower()


# ---------------------------------------------------------------------------
# /api/phoneme-timing — language_id resolution
# ---------------------------------------------------------------------------


class TestTimingEndpointLanguageResolution:
    """Language resolution rules:

    - ``?language_id=N`` — use integer directly
    - ``?language=<code>`` — look up in ``voice.config.language_id_map``
    - Unparseable / unknown values fall back to ``None``
    """

    def _build(self, mock_timing_result, language_id_map):
        voice = _make_voice(mock_timing_result, language_id_map=language_id_map)
        captured: dict = {}

        def _synth(text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            return (b"fake-wav", mock_timing_result)

        voice.synthesize_with_timing.side_effect = _synth
        return TestClient(create_app(voice, synthesize_args={})), captured

    def test_numeric_language_id(self, mock_timing_result):
        # Use a map that includes id 3 so range validation accepts it
        client, captured = self._build(
            mock_timing_result, {"ja": 0, "en": 1, "zh": 2, "fr": 3}
        )
        resp = client.get("/api/phoneme-timing?text=hello&language_id=3")
        assert resp.status_code == 200
        assert captured["language_id"] == 3

    def test_numeric_language_id_with_no_map_passes_through(self, mock_timing_result):
        """Without a language_id_map, numeric ids are passed through unchanged."""
        client, captured = self._build(mock_timing_result, None)
        resp = client.get("/api/phoneme-timing?text=hello&language_id=5")
        assert resp.status_code == 200
        assert captured["language_id"] == 5

    def test_out_of_range_language_id_falls_back_to_none(self, mock_timing_result):
        """language_id outside the configured map falls back to None."""
        client, captured = self._build(mock_timing_result, {"ja": 0, "en": 1})
        resp = client.get("/api/phoneme-timing?text=hello&language_id=999")
        assert resp.status_code == 200
        assert captured["language_id"] is None

    def test_negative_language_id_falls_back_to_none(self, mock_timing_result):
        client, captured = self._build(mock_timing_result, {"ja": 0, "en": 1})
        resp = client.get("/api/phoneme-timing?text=hello&language_id=-1")
        assert resp.status_code == 200
        assert captured["language_id"] is None

    def test_language_code_resolved(self, mock_timing_result):
        client, captured = self._build(mock_timing_result, {"ja": 0, "en": 1, "zh": 2})
        resp = client.get("/api/phoneme-timing?text=hello&language=zh")
        assert resp.status_code == 200
        assert captured["language_id"] == 2

    def test_invalid_language_id_falls_back_to_none(self, mock_timing_result):
        client, captured = self._build(mock_timing_result, None)
        resp = client.get("/api/phoneme-timing?text=hello&language_id=not-an-int")
        assert resp.status_code == 200
        assert captured["language_id"] is None

    def test_unknown_language_code_returns_none(self, mock_timing_result):
        client, captured = self._build(mock_timing_result, {"ja": 0, "en": 1})
        resp = client.get("/api/phoneme-timing?text=hello&language=fr")
        assert resp.status_code == 200
        assert captured["language_id"] is None


# ---------------------------------------------------------------------------
# / synthesis endpoint — non-streaming + streaming
# ---------------------------------------------------------------------------


class TestSynthesizeEndpoint:
    """Tests for the root ``/`` synthesis endpoint."""

    def test_post_returns_wav(self, client):
        resp = client.post("/", content="hello")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")
        # Valid WAV header starts with "RIFF...WAVE"
        assert resp.content[:4] == b"RIFF"
        assert resp.content[8:12] == b"WAVE"

    def test_get_with_text_query(self, client):
        resp = client.get("/?text=hello")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")
        assert resp.content[:4] == b"RIFF"

    def test_empty_text_returns_400(self, client):
        resp = client.post("/", content="")
        assert resp.status_code == 400

    def test_whitespace_text_returns_400(self, client):
        resp = client.post("/", content="   \n  ")
        assert resp.status_code == 400


class TestStreamingEndpoint:
    """Tests for ``?streaming=true`` chunked WAV streaming on ``/``."""

    def test_streaming_returns_wav_with_placeholder_sizes(self, mock_timing_result):
        voice = _make_voice(mock_timing_result, sample_rate=22050)
        client = TestClient(create_app(voice, synthesize_args={}))

        with client.stream("POST", "/?streaming=true", content="hello") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("audio/wav")
            chunks = list(resp.iter_bytes())

        body = b"".join(chunks)
        # WAV header (44 bytes) + raw PCM
        assert body[:4] == b"RIFF"
        assert body[8:12] == b"WAVE"
        # Streaming uses placeholder sizes (0xFFFFFFFF) for RIFF + data
        riff_size = struct.unpack("<I", body[4:8])[0]
        data_size = struct.unpack("<I", body[40:44])[0]
        assert riff_size == 0xFFFFFFFF
        assert data_size == 0xFFFFFFFF
        # Should contain PCM payload from both yielded sentences (200B + 200B)
        assert len(body) >= 44 + 200 + 200

    def test_streaming_invokes_synthesize_stream_raw(self, mock_timing_result):
        voice = _make_voice(mock_timing_result)
        client = TestClient(create_app(voice, synthesize_args={}))
        client.post("/?streaming=true", content="hello")
        assert voice.synthesize_stream_raw.called
        # synthesize() (the non-streaming path) should NOT have been called
        assert not voice.synthesize.called

    def test_non_streaming_uses_synthesize(self, mock_timing_result):
        voice = _make_voice(mock_timing_result)
        client = TestClient(create_app(voice, synthesize_args={}))
        client.post("/", content="hello")
        assert voice.synthesize.called
        assert not voice.synthesize_stream_raw.called

    def test_streaming_flag_accepts_truthy_values(self, mock_timing_result):
        for flag in ("true", "1", "yes", "on", "TRUE"):
            voice = _make_voice(mock_timing_result)
            client = TestClient(create_app(voice, synthesize_args={}))
            client.post(f"/?streaming={flag}", content="hello")
            assert voice.synthesize_stream_raw.called, (
                f"streaming={flag} should enable streaming"
            )

    def test_streaming_flag_off_by_default(self, mock_timing_result):
        voice = _make_voice(mock_timing_result)
        client = TestClient(create_app(voice, synthesize_args={}))
        # No streaming param at all
        client.post("/", content="hello")
        assert voice.synthesize.called
        assert not voice.synthesize_stream_raw.called

    def test_streaming_wav_header_uses_voice_sample_rate(self, mock_timing_result):
        voice = _make_voice(mock_timing_result, sample_rate=16000)
        client = TestClient(create_app(voice, synthesize_args={}))
        with client.stream("POST", "/?streaming=true", content="hello") as resp:
            chunks = list(resp.iter_bytes())
        header = b"".join(chunks)[:44]
        # Sample rate is at offset 24 (4 bytes, little endian)
        assert struct.unpack("<I", header[24:28])[0] == 16000


# ---------------------------------------------------------------------------
# Smoke check: produced non-streaming WAV is parseable by `wave`
# ---------------------------------------------------------------------------


class TestNonStreamingWavValidity:
    def test_wav_response_is_valid_wave_file(self, client):
        resp = client.post("/", content="hello")
        assert resp.status_code == 200
        with wave.open(io.BytesIO(resp.content), "rb") as wav_in:
            assert wav_in.getnchannels() == 1
            assert wav_in.getsampwidth() == 2
            assert wav_in.getframerate() == 22050


# ---------------------------------------------------------------------------
# JSON content-type smoke (FastAPI returns JSON via Response/JSONResponse)
# ---------------------------------------------------------------------------


def test_timing_json_body_is_parseable(client):
    resp = client.get("/api/phoneme-timing?text=hello")
    assert resp.status_code == 200
    parsed = json.loads(resp.text)
    assert isinstance(parsed, dict)
    assert "phonemes" in parsed


# ---------------------------------------------------------------------------
# Body size limit (DoS guard)
# ---------------------------------------------------------------------------


class TestRequestBodySizeLimit:
    """POST bodies above the configured cap are rejected with 413."""

    def test_oversized_body_rejected(self, mock_timing_result):
        from piper.http_server import MAX_TEXT_BYTES

        voice = _make_voice(mock_timing_result)
        client = TestClient(create_app(voice, synthesize_args={}))
        oversized = b"a" * (MAX_TEXT_BYTES + 1)
        resp = client.post("/", content=oversized)
        assert resp.status_code == 413
        body = resp.json()
        assert "error" in body

    def test_oversized_body_rejected_for_timing(self, mock_timing_result):
        from piper.http_server import MAX_TEXT_BYTES

        voice = _make_voice(mock_timing_result)
        client = TestClient(create_app(voice, synthesize_args={}))
        oversized = b"a" * (MAX_TEXT_BYTES + 1)
        resp = client.post("/api/phoneme-timing", content=oversized)
        assert resp.status_code == 413

    def test_oversized_get_query_raises(self):
        """``_read_text`` rejects oversized GET ``?text=`` directly.

        We can't exercise this via ``TestClient`` because httpx refuses to
        build URLs over its own internal cap (``InvalidURL: query too long``)
        before the request reaches the server.
        """
        import asyncio

        from piper.http_server import MAX_TEXT_BYTES, _read_text, _RequestTooLarge

        request = MagicMock()
        request.method = "GET"
        oversized = "a" * (MAX_TEXT_BYTES + 1)

        with pytest.raises(_RequestTooLarge):
            asyncio.run(_read_text(request, oversized))

    def test_within_get_query_accepted(self):
        """Sanity check: GET ``?text=`` under the cap passes through."""
        import asyncio

        from piper.http_server import _read_text

        request = MagicMock()
        request.method = "GET"
        result = asyncio.run(_read_text(request, "hello"))
        assert result == "hello"


# ---------------------------------------------------------------------------
# Error response shape consistency
# ---------------------------------------------------------------------------


class TestErrorResponseShape:
    """All 4xx responses share the ``{"error": ...}`` body shape."""

    def test_synthesize_empty_text_uses_error_key(self, client):
        resp = client.post("/", content="")
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "detail" not in body  # Not FastAPI default shape

    def test_timing_empty_text_uses_error_key(self, client):
        resp = client.post("/api/phoneme-timing", content="")
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert "detail" not in body


# ---------------------------------------------------------------------------
# Streaming exception handling
# ---------------------------------------------------------------------------


class TestStreamingExceptionHandling:
    """Generators that raise mid-stream are logged (no silent failures)."""

    def test_streaming_exception_is_logged(self, mock_timing_result, caplog):
        import logging

        voice = _make_voice(mock_timing_result)

        def _broken_stream(_text, **_kwargs):
            yield b"\x00\x00" * 50
            raise RuntimeError("boom")

        voice.synthesize_stream_raw.side_effect = _broken_stream
        client = TestClient(create_app(voice, synthesize_args={}))

        with caplog.at_level(logging.ERROR, logger="piper.http_server"):
            with pytest.raises(RuntimeError):
                with client.stream("POST", "/?streaming=true", content="hello") as resp:
                    list(resp.iter_bytes())
        assert any("Streaming synthesis failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Streaming additional contract: passes language_id through to voice
# ---------------------------------------------------------------------------


class TestStreamingLanguageIdPassthrough:
    def test_streaming_passes_language_id(self, mock_timing_result):
        voice = _make_voice(mock_timing_result, language_id_map={"ja": 0, "en": 1})
        captured: dict = {}

        def _stream(_text, **kwargs):
            captured["language_id"] = kwargs.get("language_id")
            yield b"\x00\x00" * 100

        voice.synthesize_stream_raw.side_effect = _stream
        client = TestClient(create_app(voice, synthesize_args={}))
        with client.stream(
            "POST", "/?streaming=true&language=en", content="hello"
        ) as resp:
            list(resp.iter_bytes())
        assert captured["language_id"] == 1


# ---------------------------------------------------------------------------
# _warn_if_public_bind helper
# ---------------------------------------------------------------------------


class TestPublicBindWarning:
    def test_warns_for_wildcard_address(self, caplog):
        import logging

        from piper.http_server import _warn_if_public_bind

        with caplog.at_level(logging.WARNING, logger="piper.http_server"):
            _warn_if_public_bind("0.0.0.0")
        assert any("authentication" in r.message for r in caplog.records)

    def test_no_warning_for_loopback(self, caplog):
        import logging

        from piper.http_server import _warn_if_public_bind

        with caplog.at_level(logging.WARNING, logger="piper.http_server"):
            _warn_if_public_bind("127.0.0.1")
        assert not any("authentication" in r.message for r in caplog.records)
