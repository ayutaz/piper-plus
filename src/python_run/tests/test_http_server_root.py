"""Direct unit tests for `piper.http_server` helpers and the `/` route.

`test_http_timing.py` already covers `/api/phoneme-timing` end-to-end and the
happy path of `/`. This file fills the audit gaps:

- 413 size cap (MAX_TEXT_BYTES) on POST and GET
- `_resolve_language_id` corner cases (parse error, out-of-range, language map)
- `_parse_bool_flag` truthy/falsy/empty
- `_read_text` UTF-8 decoding fallback (errors=replace)
- `_warn_if_public_bind` triggers on 0.0.0.0 / :: / empty host
"""

from __future__ import annotations

import logging
import wave
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("uvicorn")

from fastapi.testclient import TestClient  # noqa: E402

from piper.http_server import (  # noqa: E402
    MAX_TEXT_BYTES,
    _parse_bool_flag,
    _resolve_language_id,
    _warn_if_public_bind,
    create_app,
)

pytestmark = pytest.mark.unit


def _make_voice(
    language_id_map: dict[str, int] | None = None,
    sample_rate: int = 22050,
) -> MagicMock:
    voice = MagicMock()
    voice.config.language_id_map = language_id_map
    voice.config.sample_rate = sample_rate

    def _fake_synth(text, wav_file, **_kwargs):
        wav_file.setframerate(sample_rate)
        wav_file.setsampwidth(2)
        wav_file.setnchannels(1)
        wav_file.writeframes(b"\x00\x00" * 100)

    voice.synthesize.side_effect = _fake_synth
    return voice


# ---------------------------------------------------------------------------
# `_resolve_language_id` (unit)
# ---------------------------------------------------------------------------


class TestResolveLanguageId:
    def test_returns_none_when_no_inputs(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, None, None) is None

    def test_parse_error_falls_back_to_none(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "abc", None) is None

    def test_out_of_range_falls_back_to_none(self, caplog):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        with caplog.at_level(logging.WARNING):
            assert _resolve_language_id(voice, "99", None) is None
        assert any("out of range" in r.message for r in caplog.records)

    def test_valid_int_passes_through(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "1", None) == 1

    def test_int_passes_when_map_is_none(self):
        # No language_id_map → no validation, accept any int
        voice = _make_voice(language_id_map=None)
        assert _resolve_language_id(voice, "42", None) == 42

    def test_language_string_lookup(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1, "zh": 2})
        assert _resolve_language_id(voice, None, "ja") == 1

    def test_unknown_language_string_returns_none(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, None, "ko") is None

    def test_language_id_takes_priority_over_language(self):
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        # Both supplied: language_id wins
        assert _resolve_language_id(voice, "0", "ja") == 0

    def test_float_string_rejected_as_unparseable(self):
        # `int("1.5")` raises ValueError (no implicit float coercion).
        # Production must fall back to None, not crash.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "1.5", None) is None

    def test_empty_string_rejected_as_unparseable(self):
        # `int("")` raises ValueError. Treat as no input -> None.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "", None) is None

    def test_whitespace_only_string_rejected(self):
        # `int(" ")` raises ValueError too.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "   ", None) is None

    def test_negative_int_treated_as_out_of_range_when_map_set(self, caplog):
        # Negative IDs are not in any map -> warn + None.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        with caplog.at_level(logging.WARNING):
            assert _resolve_language_id(voice, "-1", None) is None
        assert any("out of range" in r.message for r in caplog.records)

    def test_negative_int_passes_when_map_is_none(self):
        # Without a map, validation is skipped — even negatives pass through.
        # Pin this behaviour so a future "always validate" refactor is intentional.
        voice = _make_voice(language_id_map=None)
        assert _resolve_language_id(voice, "-1", None) == -1

    def test_empty_language_string_with_map_returns_none(self):
        # `lmap.get("")` -> None for normal maps; should not crash.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, None, "") is None

    def test_language_id_with_leading_plus_accepted(self):
        # `int("+1")` succeeds in Python, so positive-prefixed ids parse.
        # Pin this behaviour so any future stricter parser fail flags the
        # change explicitly.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "+1", None) == 1

    def test_language_id_with_extra_whitespace_accepted(self):
        # `int("  1  ")` strips whitespace and parses to 1.
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        assert _resolve_language_id(voice, "  1  ", None) == 1


# ---------------------------------------------------------------------------
# `_parse_bool_flag` (unit)
# ---------------------------------------------------------------------------


class TestParseBoolFlag:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (None, False),
            ("", False),
            ("false", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("FALSE", False),
            ("anything", False),
            ("true", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("TRUE", True),
            ("YES", True),
            ("  on  ", True),  # whitespace trimmed
        ],
    )
    def test_truthy_falsy_combinations(self, value, expected):
        assert _parse_bool_flag(value) is expected


# ---------------------------------------------------------------------------
# `_warn_if_public_bind` (unit)
# ---------------------------------------------------------------------------


class TestWarnIfPublicBind:
    @pytest.mark.parametrize("host", ["0.0.0.0", "::", ""])
    def test_public_addresses_warn(self, host, caplog):
        with caplog.at_level(logging.WARNING):
            _warn_if_public_bind(host)
        assert any(
            "no authentication" in r.message.lower() for r in caplog.records
        ), f"expected warning for host={host!r}, got {caplog.records}"

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "10.0.0.1"])
    def test_local_addresses_do_not_warn(self, host, caplog):
        with caplog.at_level(logging.WARNING):
            _warn_if_public_bind(host)
        assert not any(
            "no authentication" in r.message.lower() for r in caplog.records
        )


# ---------------------------------------------------------------------------
# `/` route — 413 size cap + `_read_text` paths
# ---------------------------------------------------------------------------


class TestRequestSizeCap:
    """`MAX_TEXT_BYTES` enforcement on `/` (POST + GET)."""

    @pytest.fixture
    def client(self) -> TestClient:
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        return TestClient(create_app(voice, synthesize_args={}))

    def test_post_body_over_limit_returns_413(self, client):
        body = b"a" * (MAX_TEXT_BYTES + 1)
        resp = client.post("/", content=body)
        assert resp.status_code == 413
        assert "exceeds" in resp.json()["error"].lower()

    def test_post_body_at_limit_does_not_413(self, client):
        # MAX_TEXT_BYTES exactly. The synth step is mocked; just expect != 413.
        body = b"a" * MAX_TEXT_BYTES
        resp = client.post("/", content=body)
        assert resp.status_code != 413

    def test_get_text_over_limit_returns_413(self, monkeypatch):
        # Why monkeypatch instead of using the real MAX_TEXT_BYTES (1 MiB):
        # newer httpx (≥ 0.27) and starlette TestClient validate URL length
        # client-side and raise `httpx.InvalidURL: URL too long` before the
        # request ever reaches our server. That client-side limit is far
        # below 1 MiB on Windows. Lowering MAX_TEXT_BYTES to 256 bytes for
        # this single test pins the *server-side* 413 logic without hitting
        # the client-side URL length cap, while the canonical 1 MiB limit
        # remains pinned by the POST tests above (where body length is not
        # subject to URL parsing).
        from piper import http_server

        monkeypatch.setattr(http_server, "MAX_TEXT_BYTES", 256)
        voice = _make_voice(language_id_map={"en": 0, "ja": 1})
        client = TestClient(create_app(voice, synthesize_args={}))

        text = "a" * (256 + 1)  # 1 byte over the patched limit
        resp = client.get(f"/?text={text}")
        assert resp.status_code == 413

    def test_post_with_oversized_content_length_header_returns_413(self, client):
        # When CL header explicitly oversized, server should reject without
        # waiting for the full body.
        big = MAX_TEXT_BYTES + 100
        resp = client.post(
            "/",
            content=b"a" * 10,  # actual body small, but CL overstates
            headers={"Content-Length": str(big)},
        )
        # FastAPI/httpx may either honor the header or read actual chunks first.
        # Either path must return 413 (header-based 413 is preferred).
        assert resp.status_code == 413


# ---------------------------------------------------------------------------
# `/` route — `_read_text` UTF-8 decoding
# ---------------------------------------------------------------------------


class TestReadTextEncoding:
    @pytest.fixture
    def client(self) -> TestClient:
        voice = _make_voice(language_id_map=None)
        return TestClient(create_app(voice, synthesize_args={}))

    def test_post_utf8_japanese_text(self, client):
        text = "こんにちは"
        resp = client.post("/", content=text.encode("utf-8"))
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")

    def test_post_invalid_utf8_uses_replace(self, client):
        # 0xff is invalid as standalone UTF-8 byte. errors='replace' should
        # not raise; server should still return 200 (or 400 for empty after
        # strip, but 0xff decodes to U+FFFD which is non-empty).
        resp = client.post("/", content=b"hello \xff world")
        assert resp.status_code == 200

    def test_get_query_text_decoded_as_utf8(self, client):
        # FastAPI handles URL decoding; we just verify 200 path.
        resp = client.get("/?text=hello")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# `/` route — non-streaming WAV header / body sanity
# ---------------------------------------------------------------------------


class TestNonStreamingWavOutput:
    """Non-streaming `/` returns full WAV body; check structural correctness."""

    @pytest.fixture
    def client(self) -> TestClient:
        voice = _make_voice(sample_rate=16000)
        return TestClient(create_app(voice, synthesize_args={}))

    def test_response_starts_with_riff_header(self, client):
        resp = client.post("/", content="hello")
        assert resp.status_code == 200
        # Standard RIFF/WAVE header
        assert resp.content[:4] == b"RIFF"
        assert resp.content[8:12] == b"WAVE"

    def test_response_uses_voice_sample_rate(self, client):
        import io

        resp = client.post("/", content="hello")
        with wave.open(io.BytesIO(resp.content), "rb") as wav_in:
            assert wav_in.getframerate() == 16000
            assert wav_in.getnchannels() == 1
            assert wav_in.getsampwidth() == 2


# ---------------------------------------------------------------------------
# `/` route — speaker_embedding forwarding (zero-shot voice cloning)
# ---------------------------------------------------------------------------


class TestSynthesizeEndpointSpeakerEmbedding:
    """`/` must forward per-request ``speaker_embedding`` to ``voice.synthesize``.

    Mirrors the timing-endpoint contract: zero-shot callers POST a JSON body
    containing a ``speaker_embedding`` vector; the server must pass it through
    as a NumPy array so the underlying ONNX session can bind the
    ``speaker_embedding`` input. Without this, every zero-shot request silently
    falls back to the zero-vector default declared by ``voice.py`` (l.1056) —
    i.e. the wrong speaker.
    """

    @pytest.mark.xfail(
        reason=(
            "http_server.py does not yet parse JSON POST bodies nor forward "
            "speaker_embedding to voice.synthesize. Tracked as production bug "
            "by the parent task; voice.py already accepts the kwarg (l.717)."
        ),
        strict=False,
    )
    def test_root_endpoint_accepts_speaker_embedding_post_field(self):
        import numpy as np

        voice = _make_voice(language_id_map=None)
        client = TestClient(create_app(voice, synthesize_args={}))

        emb = [0.1] * 192
        resp = client.post("/", json={"text": "hi", "speaker_embedding": emb})

        assert resp.status_code == 200
        assert voice.synthesize.called
        _, kwargs = voice.synthesize.call_args
        assert "speaker_embedding" in kwargs, (
            "expected /` to forward speaker_embedding to voice.synthesize, "
            f"got kwargs={list(kwargs)}"
        )
        forwarded = kwargs["speaker_embedding"]
        assert isinstance(forwarded, np.ndarray), (
            f"speaker_embedding should be np.ndarray, got {type(forwarded)}"
        )
        assert forwarded.shape[-1] == 192
        np.testing.assert_allclose(forwarded.reshape(-1), emb)


# ---------------------------------------------------------------------------
# `main()` synthesize_args wiring — per-request override semantics
# ---------------------------------------------------------------------------


class TestHttpServerStartup:
    """`main()` constructs ``synthesize_args`` once at startup; per-request
    overrides (notably ``speaker_embedding`` for zero-shot) must take
    precedence so a single server instance can serve many cloned voices."""

    @pytest.mark.xfail(
        reason=(
            "synthesize_args is built once in main() (l.372) without a "
            "speaker_embedding slot, and the route handler does not splice "
            "per-request speaker_embedding into the kwargs forwarded to "
            "voice.synthesize. Same root cause as the POST-field test above."
        ),
        strict=False,
    )
    def test_synthesize_args_includes_speaker_embedding_support(self):
        import numpy as np

        voice = _make_voice(language_id_map=None)
        # Simulate CLI-built synthesize_args (no per-request speaker_embedding
        # at startup time — the request must inject it).
        synthesize_args = {
            "speaker_id": 0,
            "length_scale": None,
            "noise_scale": None,
            "noise_w": None,
            "sentence_silence": 0.0,
        }
        client = TestClient(create_app(voice, synthesize_args=synthesize_args))

        per_request_emb = [0.5] * 192
        resp = client.post(
            "/", json={"text": "hello", "speaker_embedding": per_request_emb}
        )

        assert resp.status_code == 200
        assert voice.synthesize.called
        _, kwargs = voice.synthesize.call_args
        # Per-request override must reach voice.synthesize — the CLI-time
        # default of None (implicit) must not win over the request body.
        assert kwargs.get("speaker_embedding") is not None, (
            "per-request speaker_embedding must override the CLI-time default; "
            f"got kwargs={list(kwargs)}"
        )
        forwarded = kwargs["speaker_embedding"]
        if isinstance(forwarded, np.ndarray):
            np.testing.assert_allclose(forwarded.reshape(-1), per_request_emb)
        else:
            assert list(forwarded) == per_request_emb
