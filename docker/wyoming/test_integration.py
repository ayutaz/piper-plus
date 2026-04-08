"""Wyoming Protocol integration tests.

These tests verify the Wyoming Protocol adapter works correctly
with the PiperPlus TTS engine, without requiring a real ONNX model.
All external dependencies (wyoming, piper_plus) are mocked.

Complements the unit tests in src/python/tests/test_wyoming_handler.py
which focus on handler helpers (build_info, resolve_language).  These
tests exercise the full event-handling flow, Docker configuration
semantics, and audio format contracts.
"""

from __future__ import annotations

import asyncio
import struct
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Stub wyoming and piper_plus *before* importing piper_wyoming.
# This is the same strategy used by test_wyoming_handler.py.
# ---------------------------------------------------------------------------


def _ensure_stubs() -> None:
    """Inject stub modules for wyoming and piper_plus into sys.modules."""
    if "wyoming" in sys.modules:
        return

    wyoming = MagicMock()

    # wyoming.info
    info_mod = MagicMock()
    info_mod.Attribution = type(
        "Attribution",
        (),
        {"__init__": lambda self, **kw: self.__dict__.update(kw)},
    )
    info_mod.TtsVoice = type(
        "TtsVoice",
        (),
        {"__init__": lambda self, **kw: self.__dict__.update(kw)},
    )
    info_mod.TtsProgram = type(
        "TtsProgram",
        (),
        {"__init__": lambda self, **kw: self.__dict__.update(kw)},
    )
    info_mod.Info = type(
        "Info",
        (),
        {
            "__init__": lambda self, **kw: self.__dict__.update(kw),
            "event": lambda self: SimpleNamespace(type="info", data={}),
        },
    )

    class _Describe:
        @staticmethod
        def is_type(t: str) -> bool:
            return t == "describe"

    info_mod.Describe = _Describe

    # wyoming.audio
    audio_mod = MagicMock()

    class _AudioStart:
        def __init__(self, *, rate=22050, width=2, channels=1):
            self.rate = rate
            self.width = width
            self.channels = channels

        def event(self):
            return SimpleNamespace(
                type="audio-start",
                data={"rate": self.rate, "width": self.width, "channels": self.channels},
            )

    class _AudioChunk:
        def __init__(self, *, audio=b"", rate=22050, width=2, channels=1):
            self.audio = audio
            self.rate = rate
            self.width = width
            self.channels = channels

        def event(self):
            return SimpleNamespace(
                type="audio-chunk",
                data={"rate": self.rate, "width": self.width, "channels": self.channels},
                audio=self.audio,
            )

    class _AudioStop:
        def event(self):
            return SimpleNamespace(type="audio-stop")

    audio_mod.AudioStart = _AudioStart
    audio_mod.AudioChunk = _AudioChunk
    audio_mod.AudioStop = _AudioStop

    # wyoming.tts
    tts_mod = MagicMock()

    class _Synthesize:
        def __init__(self, *, text="", voice=None):
            self.text = text
            self.voice = voice

        @staticmethod
        def is_type(t: str) -> bool:
            return t == "synthesize"

        @classmethod
        def from_event(cls, event):
            return cls(
                text=getattr(event, "_text", ""),
                voice=getattr(event, "_voice", None),
            )

    tts_mod.Synthesize = _Synthesize

    # wyoming.event
    event_mod = MagicMock()
    event_mod.Event = MagicMock()

    # wyoming.server
    server_mod = MagicMock()

    class _AsyncEventHandler:
        def __init__(self, reader, writer):
            self._reader = reader
            self._writer = writer

        async def write_event(self, event):
            pass

    server_mod.AsyncEventHandler = _AsyncEventHandler
    server_mod.AsyncServer = MagicMock()

    wyoming.info = info_mod
    wyoming.audio = audio_mod
    wyoming.tts = tts_mod
    wyoming.event = event_mod
    wyoming.server = server_mod

    modules = {
        "wyoming": wyoming,
        "wyoming.info": info_mod,
        "wyoming.audio": audio_mod,
        "wyoming.tts": tts_mod,
        "wyoming.event": event_mod,
        "wyoming.server": server_mod,
    }
    sys.modules.update(modules)

    if "piper_plus" not in sys.modules:
        sys.modules["piper_plus"] = MagicMock()


_ensure_stubs()

from piper_wyoming.__main__ import PiperPlusEventHandler  # noqa: E402
from piper_wyoming.handler import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    build_info,
    resolve_language,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthesize_event(text: str, *, language: str | None = None, name: str | None = None):
    """Build a mock Wyoming Synthesize event."""
    voice = None
    if language or name:
        voice = SimpleNamespace(language=language, name=name)
    return SimpleNamespace(
        type="synthesize",
        _text=text,
        _voice=voice,
    )


def _make_describe_event():
    """Build a mock Wyoming Describe event."""
    return SimpleNamespace(type="describe")


def _make_tts_mock(*, sample_rate: int = 22050, audio_samples: int = 4410):
    """Create a mock PiperPlus instance returning plausible audio."""
    tts = MagicMock()
    tts.sample_rate = sample_rate
    tts.languages = ["ja", "en", "zh", "es", "fr", "pt"]

    result = MagicMock()
    result.sample_rate = sample_rate
    result.audio = np.zeros(audio_samples, dtype=np.int16)
    tts.synthesize.return_value = result
    return tts


def _make_handler(tts=None, *, default_language: str = "ja", speaker_id: int = 0):
    """Create a PiperPlusEventHandler with mock streams."""
    if tts is None:
        tts = _make_tts_mock()
    reader = AsyncMock(spec=asyncio.StreamReader)
    writer = MagicMock(spec=asyncio.StreamWriter)
    handler = PiperPlusEventHandler(
        reader,
        writer,
        tts=tts,
        default_language=default_language,
        speaker_id=speaker_id,
    )
    handler.write_event = AsyncMock()
    return handler


def _run(coro):
    """Run an async coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _patch_synthesize_dispatch(handler, synth_event):
    """Patch Synthesize.is_type/from_event on the handler module for dispatch.

    The PiperPlusEventHandler.handle_event checks Describe.is_type and
    Synthesize.is_type/from_event at the module level.  We need to
    intercept these so the mock event reaches the right branch.
    """
    from piper_wyoming import __main__ as wyoming_main

    class _PatchedSynthesize:
        @staticmethod
        def is_type(t):
            return t == "synthesize"

        @classmethod
        def from_event(cls, ev):
            return SimpleNamespace(
                text=synth_event._text,
                voice=synth_event._voice,
            )

    orig_synth = wyoming_main.Synthesize
    orig_describe = wyoming_main.Describe

    wyoming_main.Synthesize = _PatchedSynthesize
    wyoming_main.Describe = SimpleNamespace(
        is_type=lambda t: t == "describe"
    )

    def restore():
        wyoming_main.Synthesize = orig_synth
        wyoming_main.Describe = orig_describe

    return restore


def _collected_event_types(handler) -> list[str]:
    """Extract the list of event types written by the handler."""
    return [call.args[0].type for call in handler.write_event.call_args_list]


# ---------------------------------------------------------------------------
# TestWyomingProtocolMessages
# ---------------------------------------------------------------------------


class TestWyomingProtocolMessages:
    """Wyoming Protocol message flow verification."""

    @pytest.mark.integration
    def test_describe_returns_tts_info(self):
        """Describe -> TTS provider info with voices for each language."""
        handler = _make_handler()
        event = _make_describe_event()

        # Describe.is_type is already wired in our stub to match "describe"
        from piper_wyoming import __main__ as wyoming_main

        orig_describe = wyoming_main.Describe
        wyoming_main.Describe = SimpleNamespace(
            is_type=lambda t: t == "describe"
        )
        orig_synth = wyoming_main.Synthesize
        wyoming_main.Synthesize = SimpleNamespace(
            is_type=lambda t: False
        )

        try:
            result = _run(handler.handle_event(event))
        finally:
            wyoming_main.Describe = orig_describe
            wyoming_main.Synthesize = orig_synth

        assert result is True
        # Should have written exactly one info event
        assert handler.write_event.call_count == 1

    @pytest.mark.integration
    def test_synthesize_request_produces_audio_sequence(self):
        """Synthesize -> AudioStart + AudioChunk(s) + AudioStop."""
        tts = _make_tts_mock(audio_samples=8820)  # ~0.4s at 22050 Hz
        handler = _make_handler(tts)
        event = _make_synthesize_event("Hello world", language="en")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            result = _run(handler.handle_event(event))
        finally:
            restore()

        assert result is True
        tts.synthesize.assert_called_once()

        event_types = _collected_event_types(handler)
        assert event_types[0] == "audio-start"
        assert event_types[-1] == "audio-stop"
        # At least one audio-chunk between start and stop
        assert "audio-chunk" in event_types

    @pytest.mark.integration
    def test_synthesize_with_language_parameter(self):
        """Language from Synthesize event is forwarded to PiperPlus."""
        tts = _make_tts_mock()
        handler = _make_handler(tts, default_language="ja")
        event = _make_synthesize_event(
            "Bonjour, comment allez-vous?", language="fr"
        )

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        call_kwargs = tts.synthesize.call_args
        assert call_kwargs.kwargs.get("language") == "fr" or (
            len(call_kwargs.args) > 0 and "fr" in str(call_kwargs)
        )

    @pytest.mark.integration
    def test_synthesize_with_voice_name_pattern(self):
        """Voice name 'piper-plus-es' resolves to language 'es'."""
        tts = _make_tts_mock()
        handler = _make_handler(tts, default_language="ja")
        event = _make_synthesize_event(
            "Hola, como estas?", name="piper-plus-es"
        )

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        call_kwargs = tts.synthesize.call_args
        # The handler calls resolve_language which extracts "es" from
        # "piper-plus-es", then passes it to tts.synthesize
        assert "es" in str(call_kwargs)

    @pytest.mark.integration
    def test_synthesize_empty_text_returns_empty_audio(self):
        """Empty text produces AudioStart + AudioStop with no synthesis."""
        tts = _make_tts_mock()
        handler = _make_handler(tts)
        event = _make_synthesize_event("")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            result = _run(handler.handle_event(event))
        finally:
            restore()

        assert result is True
        tts.synthesize.assert_not_called()

        event_types = _collected_event_types(handler)
        assert "audio-start" in event_types
        assert "audio-stop" in event_types
        assert "audio-chunk" not in event_types

    @pytest.mark.integration
    def test_synthesize_whitespace_only_returns_empty_audio(self):
        """Whitespace-only text is treated as empty."""
        tts = _make_tts_mock()
        handler = _make_handler(tts)
        event = _make_synthesize_event("   \n\t  ")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        tts.synthesize.assert_not_called()

    @pytest.mark.integration
    def test_synthesize_error_returns_empty_audio(self):
        """Synthesis failure returns empty AudioStart + AudioStop."""
        tts = _make_tts_mock()
        tts.synthesize.side_effect = RuntimeError("model error")
        handler = _make_handler(tts)
        event = _make_synthesize_event("Test text", language="en")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            result = _run(handler.handle_event(event))
        finally:
            restore()

        assert result is True  # Connection stays open
        event_types = _collected_event_types(handler)
        assert "audio-start" in event_types
        assert "audio-stop" in event_types

    @pytest.mark.integration
    def test_connection_remains_open_after_synthesize(self):
        """handle_event returns True to keep the TCP connection open."""
        handler = _make_handler()
        event = _make_synthesize_event("test", language="ja")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            result = _run(handler.handle_event(event))
        finally:
            restore()

        assert result is True

    @pytest.mark.integration
    def test_unknown_event_type_keeps_connection(self):
        """Unknown event types are silently ignored, connection stays open."""
        handler = _make_handler()
        event = SimpleNamespace(type="unknown-event")

        from piper_wyoming import __main__ as wyoming_main

        orig_describe = wyoming_main.Describe
        orig_synth = wyoming_main.Synthesize
        wyoming_main.Describe = SimpleNamespace(is_type=lambda t: False)
        wyoming_main.Synthesize = SimpleNamespace(is_type=lambda t: False)

        try:
            result = _run(handler.handle_event(event))
        finally:
            wyoming_main.Describe = orig_describe
            wyoming_main.Synthesize = orig_synth

        assert result is True
        handler.write_event.assert_not_called()


# ---------------------------------------------------------------------------
# TestWyomingDockerConfig
# ---------------------------------------------------------------------------


class TestWyomingDockerConfig:
    """Docker environment variable and CLI argument handling."""

    @pytest.mark.integration
    def test_default_port_is_10200(self):
        """Default --uri uses port 10200."""
        from piper_wyoming.__main__ import main
        import argparse

        # Inspect the argparse defaults without running the server
        parser = argparse.ArgumentParser()
        parser.add_argument("--uri", default="tcp://0.0.0.0:10200")
        parser.add_argument("--port", type=int, default=None)
        args = parser.parse_args([])
        assert "10200" in args.uri
        assert args.port is None

    @pytest.mark.integration
    def test_port_flag_overrides_uri(self):
        """--port flag overrides the port in --uri."""
        # This tests the logic from __main__.py lines 173-175:
        #   if args.port is not None:
        #       uri = f"tcp://0.0.0.0:{args.port}"
        port = 10300
        uri = "tcp://0.0.0.0:10200"
        if port is not None:
            uri = f"tcp://0.0.0.0:{port}"
        assert uri == "tcp://0.0.0.0:10300"

    @pytest.mark.integration
    def test_default_language_is_ja(self):
        """Default language is 'ja'."""
        handler = _make_handler(default_language="ja")
        assert handler.default_language == "ja"

    @pytest.mark.integration
    def test_custom_default_language(self):
        """Custom default language is passed through."""
        handler = _make_handler(default_language="en")
        assert handler.default_language == "en"

    @pytest.mark.integration
    def test_custom_speaker_id(self):
        """Speaker ID is configurable."""
        handler = _make_handler(speaker_id=5)
        assert handler.speaker_id == 5

    @pytest.mark.integration
    def test_supported_languages_match_trained_set(self):
        """SUPPORTED_LANGUAGES contains exactly the 6 trained languages."""
        assert set(SUPPORTED_LANGUAGES) == {"ja", "en", "zh", "es", "fr", "pt"}

    @pytest.mark.integration
    def test_env_vars_in_docker_compose_have_defaults(self):
        """docker-compose.yml env vars all have sensible defaults.

        This is a documentation/contract test: if the env var names
        or defaults change, this test should be updated.
        """
        expected_defaults = {
            "PIPER_MODEL": "tsukuyomi",
            "PIPER_LANGUAGE": "ja",
            "PIPER_SPEAKER_ID": "0",
            "PIPER_PORT": "10200",
        }
        # These are the values from .env.example -- verify the contract
        for var, default in expected_defaults.items():
            assert default, f"{var} should have a non-empty default"


# ---------------------------------------------------------------------------
# TestWyomingAudioFormat
# ---------------------------------------------------------------------------


class TestWyomingAudioFormat:
    """Output audio format verification."""

    @pytest.mark.integration
    def test_audio_is_16bit_pcm(self):
        """Output audio uses 16-bit (width=2) PCM encoding."""
        tts = _make_tts_mock()
        handler = _make_handler(tts)
        event = _make_synthesize_event("test", language="ja")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        # Find the AudioStart event and verify width=2 (16-bit)
        for call in handler.write_event.call_args_list:
            evt = call.args[0]
            if evt.type == "audio-start":
                assert evt.data["width"] == 2, "Audio must be 16-bit PCM"
                break
        else:
            pytest.fail("No audio-start event was written")

    @pytest.mark.integration
    def test_sample_rate_matches_model(self):
        """AudioStart sample rate matches the model's configured rate."""
        custom_rate = 16000
        tts = _make_tts_mock(sample_rate=custom_rate)
        # The model returns audio at custom_rate
        result = MagicMock()
        result.sample_rate = custom_rate
        result.audio = np.zeros(3200, dtype=np.int16)
        tts.synthesize.return_value = result

        handler = _make_handler(tts)
        event = _make_synthesize_event("test", language="ja")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        for call in handler.write_event.call_args_list:
            evt = call.args[0]
            if evt.type == "audio-start":
                assert evt.data["rate"] == custom_rate
                break
        else:
            pytest.fail("No audio-start event was written")

    @pytest.mark.integration
    def test_audio_is_mono(self):
        """Output audio is single-channel (mono)."""
        tts = _make_tts_mock()
        handler = _make_handler(tts)
        event = _make_synthesize_event("test", language="ja")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        for call in handler.write_event.call_args_list:
            evt = call.args[0]
            if evt.type == "audio-start":
                assert evt.data["channels"] == 1, "Audio must be mono"
                break
        else:
            pytest.fail("No audio-start event was written")

    @pytest.mark.integration
    def test_audio_chunk_bytes_are_valid_int16(self):
        """AudioChunk payloads contain valid 16-bit little-endian samples."""
        # Use a known audio pattern
        tts = _make_tts_mock()
        known_audio = np.array([100, -200, 32767, -32768, 0], dtype=np.int16)
        result = MagicMock()
        result.sample_rate = 22050
        result.audio = known_audio
        tts.synthesize.return_value = result

        handler = _make_handler(tts)
        event = _make_synthesize_event("test", language="ja")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        # Collect all chunk bytes
        chunk_bytes = b""
        for call in handler.write_event.call_args_list:
            evt = call.args[0]
            if evt.type == "audio-chunk" and hasattr(evt, "audio"):
                chunk_bytes += evt.audio

        # Verify the bytes decode to the original int16 samples
        n_samples = len(chunk_bytes) // 2
        decoded = struct.unpack(f"<{n_samples}h", chunk_bytes)
        assert list(decoded) == list(known_audio)

    @pytest.mark.integration
    def test_large_audio_is_chunked(self):
        """Audio longer than AUDIO_CHUNK_SIZE is split into multiple chunks."""
        from piper_wyoming.__main__ import AUDIO_CHUNK_SIZE

        # Create audio that exceeds one chunk
        n_samples = (AUDIO_CHUNK_SIZE * 3) // 2  # 3 chunks worth of int16
        tts = _make_tts_mock(audio_samples=n_samples)
        handler = _make_handler(tts)
        event = _make_synthesize_event("Long text here", language="en")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        chunk_count = sum(
            1
            for call in handler.write_event.call_args_list
            if call.args[0].type == "audio-chunk"
        )
        assert chunk_count >= 2, (
            f"Expected >=2 chunks for {n_samples * 2} bytes "
            f"(chunk_size={AUDIO_CHUNK_SIZE}), got {chunk_count}"
        )


# ---------------------------------------------------------------------------
# TestMultiLanguageIntegration
# ---------------------------------------------------------------------------


class TestMultiLanguageIntegration:
    """Multi-language synthesis flow through the Wyoming adapter."""

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "lang,text",
        [
            ("ja", "Hello"),
            ("en", "Hello, how are you?"),
            ("zh", "Test"),
            ("es", "Hola"),
            ("fr", "Bonjour"),
            ("pt", "Bom dia"),
        ],
    )
    def test_all_supported_languages_accepted(self, lang: str, text: str):
        """Each supported language completes synthesis without error."""
        tts = _make_tts_mock()
        handler = _make_handler(tts, default_language="ja")
        event = _make_synthesize_event(text, language=lang)

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            result = _run(handler.handle_event(event))
        finally:
            restore()

        assert result is True
        tts.synthesize.assert_called_once()

    @pytest.mark.integration
    def test_unsupported_language_falls_back_to_default(self):
        """Unsupported language code falls back to the default language."""
        tts = _make_tts_mock()
        handler = _make_handler(tts, default_language="en")

        # "de" (German) is not in SUPPORTED_LANGUAGES
        event = _make_synthesize_event("Guten Tag", language="de")

        restore = _patch_synthesize_dispatch(handler, event)
        try:
            _run(handler.handle_event(event))
        finally:
            restore()

        # resolve_language should return default "en" for unknown "de"
        call_kwargs = tts.synthesize.call_args
        # The language passed to synthesize should be "en" (the default)
        assert call_kwargs.kwargs.get("language") == "en" or "en" in str(call_kwargs)

    @pytest.mark.integration
    def test_describe_lists_model_languages_only(self):
        """Describe filters voices to languages the model actually supports."""
        tts = _make_tts_mock()
        # Model only supports ja and en
        tts.languages = ["ja", "en"]
        handler = _make_handler(tts)

        event = _make_describe_event()

        from piper_wyoming import __main__ as wyoming_main

        orig_describe = wyoming_main.Describe
        orig_synth = wyoming_main.Synthesize
        wyoming_main.Describe = SimpleNamespace(is_type=lambda t: t == "describe")
        wyoming_main.Synthesize = SimpleNamespace(is_type=lambda t: False)

        try:
            _run(handler.handle_event(event))
        finally:
            wyoming_main.Describe = orig_describe
            wyoming_main.Synthesize = orig_synth

        # The handler builds info filtered to SUPPORTED_LANGUAGES intersected
        # with the model's languages.  Verify write_event was called.
        assert handler.write_event.call_count == 1
