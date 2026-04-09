"""Run piper-plus as a Wyoming TTS server.

Usage::

    uv run python -m piper_wyoming --model tsukuyomi --port 10200
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from functools import partial

from piper_plus import PiperPlus
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.event import Event
from wyoming.info import Describe
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.tts import Synthesize

from piper_wyoming.handler import SUPPORTED_LANGUAGES, build_info, resolve_language


logger = logging.getLogger(__name__)

AUDIO_CHUNK_SIZE = 4096  # bytes per chunk


class PiperPlusEventHandler(AsyncEventHandler):
    """Wyoming event handler using PiperPlus for synthesis."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        tts: PiperPlus,
        default_language: str = "ja",
        speaker_id: int = 0,
    ) -> None:
        super().__init__(reader, writer)
        self.tts = tts
        self.default_language = default_language
        self.speaker_id = speaker_id

    async def handle_event(self, event: Event) -> bool:
        """Handle a Wyoming event.  Return True to keep connection open."""
        if Describe.is_type(event.type):
            info = build_info(
                languages=[
                    lang
                    for lang in self.tts.languages
                    if lang in set(SUPPORTED_LANGUAGES)
                ]
            )
            await self.write_event(info.event())
            return True

        if not Synthesize.is_type(event.type):
            return True

        synthesize = Synthesize.from_event(event)
        text = synthesize.text or ""
        if not text.strip():
            # Send empty audio for empty text
            await self.write_event(
                AudioStart(rate=self.tts.sample_rate, width=2, channels=1).event()
            )
            await self.write_event(AudioStop().event())
            return True

        language = resolve_language(synthesize, self.default_language)
        logger.info("Synthesizing: '%s' (lang=%s)", text[:80], language)

        try:
            # Run synthesis in a thread to avoid blocking the event loop
            result = await asyncio.to_thread(
                self.tts.synthesize,
                text,
                speaker_id=self.speaker_id,
                language=language,
            )
        except Exception:
            logger.exception("Synthesis failed")
            await self.write_event(
                AudioStart(rate=self.tts.sample_rate, width=2, channels=1).event()
            )
            await self.write_event(AudioStop().event())
            return True

        # Stream audio back
        await self.write_event(
            AudioStart(rate=result.sample_rate, width=2, channels=1).event()
        )

        audio_bytes = result.audio.tobytes()
        for i in range(0, len(audio_bytes), AUDIO_CHUNK_SIZE):
            chunk = audio_bytes[i : i + AUDIO_CHUNK_SIZE]
            await self.write_event(
                AudioChunk(
                    audio=chunk,
                    rate=result.sample_rate,
                    width=2,
                    channels=1,
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
        default="tsukuyomi",
        help="Model name, alias, or path (default: tsukuyomi)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Config file path (auto-detected if omitted)",
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
        help="Speaker ID (default: 0)",
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
        help="Device: cpu, gpu, auto (default: cpu)",
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

    logger.info("Loading model: %s (device=%s)", args.model, args.device)
    tts = PiperPlus(args.model, config=args.config, device=args.device)
    logger.info("Model loaded. Languages: %s", tts.languages)

    logger.info("Starting Wyoming TTS server: %s", uri)
    server = AsyncServer.from_uri(uri)

    handler_kwargs = {
        "tts": tts,
        "speaker_id": args.speaker_id,
        "default_language": args.language,
    }

    try:
        asyncio.run(server.run(partial(PiperPlusEventHandler, **handler_kwargs)))
    except KeyboardInterrupt:
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
