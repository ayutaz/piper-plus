"""CLI entry point for piper-plus Wyoming Protocol server.

Usage::

    uv run python -m piper_wyoming --model model.onnx --port 10200
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from functools import partial

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

from .handler import (
    CHANNELS,
    CHUNK_BYTES,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    SUPPORTED_LANGUAGES,
    PiperPlusSynthesizer,
    _resolve_language,
    get_info,
)

_LOGGER = logging.getLogger(__name__)


class PiperPlusEventHandler(AsyncEventHandler):
    """Wyoming AsyncEventHandler for piper-plus TTS.

    Handles ``Synthesize`` events by running ONNX inference and
    streaming back ``AudioStart`` / ``AudioChunk`` / ``AudioStop``.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        synthesizer: PiperPlusSynthesizer,
        speaker_id: int = 0,
        default_language: str = "ja",
    ) -> None:
        super().__init__(reader, writer)
        self.synthesizer = synthesizer
        self.speaker_id = speaker_id
        self.default_language = default_language

    async def handle_event(self, event: Event) -> bool:
        """Handle a Wyoming event.  Return True to keep connection open."""
        if Describe.is_type(event.type):
            await self.write_event(get_info().event())
            return True

        if not Synthesize.is_type(event.type):
            # Ignore unknown events, keep connection alive
            return True

        synthesize = Synthesize.from_event(event)
        text = synthesize.text
        language = _resolve_language(synthesize, self.default_language)

        _LOGGER.info(
            "Synthesize: text=%r, language=%s, speaker=%d",
            text[:80] if text else "",
            language,
            self.speaker_id,
        )

        if not text or not text.strip():
            _LOGGER.warning("Empty text in Synthesize event")
            await self.write_event(
                AudioStart(
                    rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS
                ).event()
            )
            await self.write_event(AudioStop().event())
            return True

        try:
            audio = self.synthesizer.synthesize(
                text, language=language, speaker_id=self.speaker_id
            )
        except Exception:
            _LOGGER.exception("Synthesis failed")
            await self.write_event(
                AudioStart(
                    rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS
                ).event()
            )
            await self.write_event(AudioStop().event())
            return True

        # Stream audio back as chunked events
        await self.write_event(
            AudioStart(
                rate=SAMPLE_RATE, width=SAMPLE_WIDTH, channels=CHANNELS
            ).event()
        )

        pcm_bytes = audio.tobytes()
        for offset in range(0, len(pcm_bytes), CHUNK_BYTES):
            chunk = pcm_bytes[offset : offset + CHUNK_BYTES]
            await self.write_event(
                AudioChunk(
                    audio=chunk,
                    rate=SAMPLE_RATE,
                    width=SAMPLE_WIDTH,
                    channels=CHANNELS,
                ).event()
            )

        await self.write_event(AudioStop().event())
        return True


def main() -> None:
    """Parse arguments and start the Wyoming server."""
    parser = argparse.ArgumentParser(
        description="piper-plus Wyoming Protocol TTS server"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Path to ONNX model file",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.json (default: auto-detect next to model)",
    )
    parser.add_argument(
        "--uri",
        default="tcp://0.0.0.0:10200",
        help="Server URI (default: tcp://0.0.0.0:10200)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (shorthand; overrides port in --uri)",
    )
    parser.add_argument(
        "--speaker-id",
        type=int,
        default=0,
        help="Default speaker ID (default: 0)",
    )
    parser.add_argument(
        "--language",
        default="ja",
        choices=list(SUPPORTED_LANGUAGES),
        help="Default language (default: ja)",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["auto", "cpu", "gpu"],
        help="Inference device (default: cpu)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )

    # Build URI
    uri = args.uri
    if args.port is not None:
        uri = f"tcp://0.0.0.0:{args.port}"

    _LOGGER.info("Loading model: %s", args.model)
    synthesizer = PiperPlusSynthesizer(
        args.model,
        config_path=args.config,
        device=args.device,
    )

    _LOGGER.info("Starting Wyoming server on %s", uri)
    server = AsyncServer.from_uri(uri)

    handler_kwargs = {
        "synthesizer": synthesizer,
        "speaker_id": args.speaker_id,
        "default_language": args.language,
    }

    try:
        asyncio.run(
            server.run(
                partial(PiperPlusEventHandler, **handler_kwargs)
            )
        )
    except KeyboardInterrupt:
        _LOGGER.info("Server stopped")


if __name__ == "__main__":
    main()
