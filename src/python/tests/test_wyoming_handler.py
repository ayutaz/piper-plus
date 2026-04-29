"""Tests for Wyoming Protocol TTS handler.

Tests the handler and helper functions in piper_wyoming without
requiring a real ONNX model or the wyoming package -- all external
dependencies are mocked.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Mock the wyoming package before importing piper_wyoming modules.
# The handler and __main__ import from wyoming at module level,
# so we inject stub modules into sys.modules first.
# ---------------------------------------------------------------------------

_wyoming_stubs: dict[str, MagicMock] = {}


def _ensure_wyoming_stubs() -> None:
    """Inject minimal wyoming stub modules into sys.modules if needed."""
    if "wyoming" in sys.modules:
        # Already available (either real or previously stubbed)
        return

    # Build a hierarchy of mock modules
    wyoming = MagicMock()

    # wyoming.info -- used by handler.py
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
        {"__init__": lambda self, **kw: self.__dict__.update(kw)},
    )
    info_mod.Describe = MagicMock()

    # wyoming.audio
    audio_mod = MagicMock()

    class _AudioStart:
        def __init__(self, *, rate=22050, width=2, channels=1):
            self.rate = rate
            self.width = width
            self.channels = channels

        def event(self):
            return SimpleNamespace(type="audio-start")

    class _AudioChunk:
        def __init__(self, *, audio=b"", rate=22050, width=2, channels=1):
            self.audio = audio
            self.rate = rate

        def event(self):
            return SimpleNamespace(type="audio-chunk")

    class _AudioStop:
        def event(self):
            return SimpleNamespace(type="audio-stop")

    audio_mod.AudioStart = _AudioStart
    audio_mod.AudioChunk = _AudioChunk
    audio_mod.AudioStop = _AudioStop

    # wyoming.tts
    tts_mod = MagicMock()

    class _SynthesizeVoice:
        def __init__(self, *, name=None, language=None):
            self.name = name
            self.language = language

    class _Synthesize:
        def __init__(self, *, text="", voice=None):
            self.text = text
            self.voice = voice

        def event(self):
            return SimpleNamespace(
                type="synthesize",
                data={"text": self.text},
                payload=b"",
            )

        @staticmethod
        def is_type(t):
            return t == "synthesize"

        @classmethod
        def from_event(cls, event):
            text = getattr(event, "data", {}).get("text", "")
            return cls(text=text)

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

        async def write_event(self, event):  # pragma: no cover
            pass

    server_mod.AsyncEventHandler = _AsyncEventHandler
    server_mod.AsyncServer = MagicMock()

    # Wire up the module hierarchy
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
    _wyoming_stubs.update(modules)
    sys.modules.update(modules)


# Also stub piper_plus if not installed (only PiperPlus class is used)
def _ensure_piper_plus_stub() -> None:
    if "piper_plus" in sys.modules:
        return
    pp = MagicMock()
    sys.modules["piper_plus"] = pp


# Install stubs before any piper_wyoming import
_ensure_wyoming_stubs()
_ensure_piper_plus_stub()


# Now safe to import piper_wyoming
from piper_wyoming.handler import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    build_info,
    resolve_language,
)
from piper_wyoming.__main__ import PiperPlusEventHandler  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_piper_plus():
    """Create a mock PiperPlus instance."""
    tts = MagicMock()
    tts.sample_rate = 22050
    tts.languages = ["ja", "en", "zh", "es", "fr", "pt"]

    # Default synthesize() returns a plausible AudioResult
    result = MagicMock()
    result.sample_rate = 22050
    result.audio = np.zeros(4410, dtype=np.int16)  # ~0.2s silence
    tts.synthesize.return_value = result

    return tts


@pytest.fixture()
def make_handler(mock_piper_plus):
    """Factory for PiperPlusEventHandler instances with mock streams."""

    def _factory(*, default_language: str = "ja", speaker_id: int = 0):
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        handler = PiperPlusEventHandler(
            reader,
            writer,
            tts=mock_piper_plus,
            default_language=default_language,
            speaker_id=speaker_id,
        )
        handler.write_event = AsyncMock()
        return handler

    return _factory


# ---------------------------------------------------------------------------
# TestWyomingHandler
# ---------------------------------------------------------------------------


class TestWyomingHandler:
    """Wyoming TTS handler behaviour."""

    @pytest.mark.unit
    def test_handler_creates_with_piper_plus(self, mock_piper_plus):
        """PiperPlusインスタンスで初期化されるべき."""
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        handler = PiperPlusEventHandler(
            reader,
            writer,
            tts=mock_piper_plus,
            default_language="ja",
            speaker_id=0,
        )
        assert handler.tts is mock_piper_plus
        assert handler.default_language == "ja"
        assert handler.speaker_id == 0

    @pytest.mark.unit
    def test_resolve_language_returns_valid_code(self):
        """既知の言語コードで正しい値を返すべき."""
        # voice.language is set to a supported language
        event = SimpleNamespace(
            voice=SimpleNamespace(language="en", name=None)
        )
        assert resolve_language(event) == "en"

        # voice.name is a bare language code
        event = SimpleNamespace(
            voice=SimpleNamespace(language=None, name="fr")
        )
        assert resolve_language(event) == "fr"

        # voice.name is "piper-plus-zh"
        event = SimpleNamespace(
            voice=SimpleNamespace(language=None, name="piper-plus-zh")
        )
        assert resolve_language(event) == "zh"

    @pytest.mark.unit
    def test_resolve_language_unknown_returns_none(self):
        """未知の言語コードでデフォルト値を返すべき."""
        # Unknown language code -> falls back to default
        event = SimpleNamespace(
            voice=SimpleNamespace(language="xx", name=None)
        )
        assert resolve_language(event) == "ja"  # default

        # No voice at all
        event = SimpleNamespace(voice=None)
        assert resolve_language(event) == "ja"

        # Explicit default override
        event = SimpleNamespace(voice=None)
        assert resolve_language(event, default="en") == "en"

    @pytest.mark.unit
    def test_handler_processes_text(self, make_handler, mock_piper_plus):
        """テキスト入力でPCMバイト列を返すべき."""
        handler = make_handler()

        # Build a Synthesize-like event manually
        synth_obj = SimpleNamespace(
            text="Hello world",
            voice=SimpleNamespace(language="en", name=None),
        )
        event = SimpleNamespace(
            type="synthesize",
            data={"text": "Hello world"},
            payload=b"",
        )

        # Patch Synthesize.is_type and from_event on the handler's module
        from piper_wyoming import __main__ as wyoming_main

        orig_synthesize_cls = wyoming_main.Synthesize

        class _MockSynthesize:
            @staticmethod
            def is_type(t):
                return t == "synthesize"

            @classmethod
            def from_event(cls, ev):
                return synth_obj

        wyoming_main.Synthesize = _MockSynthesize
        wyoming_main.Describe = MagicMock()
        wyoming_main.Describe.is_type = MagicMock(return_value=False)

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(handler.handle_event(event))
            loop.close()
        finally:
            wyoming_main.Synthesize = orig_synthesize_cls

        assert result is True
        mock_piper_plus.synthesize.assert_called_once()
        call_args = mock_piper_plus.synthesize.call_args
        assert call_args[0][0] == "Hello world"

        # Should have written AudioStart, at least one AudioChunk, AudioStop
        event_types = [
            call.args[0].type for call in handler.write_event.call_args_list
        ]
        assert "audio-start" in event_types
        assert "audio-stop" in event_types

    @pytest.mark.unit
    def test_handler_empty_text(self, make_handler, mock_piper_plus):
        """空テキストで空の応答を返すべき."""
        handler = make_handler()

        synth_obj = SimpleNamespace(
            text="",
            voice=SimpleNamespace(language="ja", name=None),
        )
        event = SimpleNamespace(
            type="synthesize",
            data={"text": ""},
            payload=b"",
        )

        from piper_wyoming import __main__ as wyoming_main

        orig_synthesize_cls = wyoming_main.Synthesize

        class _MockSynthesize:
            @staticmethod
            def is_type(t):
                return t == "synthesize"

            @classmethod
            def from_event(cls, ev):
                return synth_obj

        wyoming_main.Synthesize = _MockSynthesize
        wyoming_main.Describe = MagicMock()
        wyoming_main.Describe.is_type = MagicMock(return_value=False)

        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(handler.handle_event(event))
            loop.close()
        finally:
            wyoming_main.Synthesize = orig_synthesize_cls

        assert result is True
        # synthesize should NOT be called for empty text
        mock_piper_plus.synthesize.assert_not_called()

        # Should still write AudioStart + AudioStop (empty audio)
        event_types = [
            call.args[0].type for call in handler.write_event.call_args_list
        ]
        assert "audio-start" in event_types
        assert "audio-stop" in event_types


# ---------------------------------------------------------------------------
# TestBuildInfo
# ---------------------------------------------------------------------------


class TestBuildInfo:
    """Tests for build_info() helper."""

    @pytest.mark.unit
    def test_build_info_default_languages(self):
        """デフォルトで6言語のvoiceが生成されるべき."""
        info = build_info()
        assert hasattr(info, "tts")
        program = info.tts[0]
        assert program.name == "piper-plus"
        assert len(program.voices) == 6

        voice_langs = {v.languages[0] for v in program.voices}
        assert voice_langs == {"ja", "en", "zh", "es", "fr", "pt"}

    @pytest.mark.unit
    def test_build_info_custom_languages(self):
        """カスタム言語リストで正しいvoice数になるべき."""
        info = build_info(languages=["ja", "en"])
        assert len(info.tts[0].voices) == 2

    @pytest.mark.unit
    def test_build_info_attribution(self):
        """attribution情報が正しく設定されるべき."""
        info = build_info()
        attr = info.tts[0].attribution
        assert attr.name == "piper-plus"
        assert "github.com" in attr.url

    @pytest.mark.unit
    def test_build_info_version_semantics(self):
        """TtsProgram.version はパッケージ __version__、TtsVoice.version は None であるべき.

        Wyoming 1.5.1 で Artifact.version (Optional[str]) が追加されたが、
        default 値を持たないため引数指定が実質必須。version 引数を渡さないと
        TypeError で Home Assistant 統合が停止する。

        version の意味論:
        - TtsProgram.version: サービスソフトウェアのバージョン → piper_wyoming.__version__
        - TtsVoice.version: voice モデル自身のバージョン → モデル管理していないため None

        rhasspy/wyoming-piper の慣習に準拠。HA UI で voice 一覧に同一値が
        並ぶ冗長表示を避ける目的もある。
        """
        from piper_wyoming import __version__

        info = build_info()
        program = info.tts[0]
        # TtsProgram はサービス software のバージョン
        assert program.version == __version__
        # TtsVoice は voice モデル自身のバージョン (管理外のため None)
        for voice in program.voices:
            assert voice.version is None


# ---------------------------------------------------------------------------
# TestResolveLanguageEdgeCases
# ---------------------------------------------------------------------------


class TestResolveLanguageEdgeCases:
    """Edge cases for resolve_language()."""

    @pytest.mark.unit
    def test_voice_language_takes_priority_over_name(self):
        """voice.language が voice.name より優先されるべき."""
        event = SimpleNamespace(
            voice=SimpleNamespace(language="es", name="piper-plus-fr")
        )
        assert resolve_language(event) == "es"

    @pytest.mark.unit
    def test_unsupported_language_in_name_falls_to_default(self):
        """voice.name に未サポート言語がある場合デフォルトを返すべき."""
        event = SimpleNamespace(
            voice=SimpleNamespace(language=None, name="piper-plus-de")
        )
        assert resolve_language(event) == "ja"

    @pytest.mark.unit
    def test_empty_voice_name(self):
        """空のvoice.nameでデフォルトを返すべき."""
        event = SimpleNamespace(
            voice=SimpleNamespace(language=None, name="")
        )
        assert resolve_language(event) == "ja"
