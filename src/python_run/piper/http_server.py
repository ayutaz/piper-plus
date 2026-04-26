#!/usr/bin/env python3
"""FastAPI HTTP server for Piper TTS.

Endpoints
---------
- ``GET/POST /`` — synthesize text, return ``audio/wav`` (optional streaming).
- ``GET/POST /api/phoneme-timing`` — return phoneme timing as JSON or TSV.

Streaming
---------
Pass ``?streaming=true`` (or ``true|1|yes``) on ``/`` to receive a chunked
WAV response. The server emits a WAV header with placeholder sizes
(``0xFFFFFFFF``) followed by raw PCM frames per sentence — compatible with
browsers, ``ffmpeg`` and most media players.
"""

from __future__ import annotations

import argparse
import io
import logging
import struct
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from . import PiperVoice
from .download import ensure_voice_exists, find_voice, get_voices
from .timing import timing_to_json, timing_to_tsv

_LOGGER = logging.getLogger(__name__)


def _build_streaming_wav_header(
    sample_rate: int, channels: int = 1, bit_depth: int = 16
) -> bytes:
    """Build a WAV header with placeholder sizes for chunked streaming.

    Uses ``0xFFFFFFFF`` for the RIFF and data chunk sizes — the conventional
    "unknown length" sentinel accepted by browsers and ``ffmpeg``.
    """
    byte_rate = sample_rate * channels * bit_depth // 8
    block_align = channels * bit_depth // 8
    return (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + struct.pack("<H", 1)
        + struct.pack("<H", channels)
        + struct.pack("<I", sample_rate)
        + struct.pack("<I", byte_rate)
        + struct.pack("<H", block_align)
        + struct.pack("<H", bit_depth)
        + b"data"
        + struct.pack("<I", 0xFFFFFFFF)
    )


def _resolve_language_id(
    voice: PiperVoice,
    language_id_raw: str | None,
    language: str | None,
) -> int | None:
    if language_id_raw is not None:
        try:
            return int(language_id_raw)
        except (ValueError, TypeError):
            return None
    if language is not None:
        lmap = voice.config.language_id_map
        if lmap:
            return lmap.get(language)
    return None


async def _read_text(request: Request, query_text: str | None) -> str:
    if request.method == "POST":
        body = await request.body()
        text = body.decode("utf-8")
    else:
        text = query_text or ""
    return text.strip()


def _parse_bool_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


def create_app(voice: Any, synthesize_args: dict[str, Any]) -> FastAPI:
    """Build a FastAPI app wired to the loaded voice."""
    app = FastAPI(
        title="Piper TTS HTTP Server",
        description="Synthesize speech and return WAV audio.",
    )

    @app.api_route("/", methods=["GET", "POST"])
    async def app_synthesize(
        request: Request,
        text: str | None = Query(None),
        language: str | None = Query(None),
        language_id: str | None = Query(None),
        streaming: str | None = Query(None),
    ) -> Response:
        body_text = await _read_text(request, text)
        if not body_text:
            raise HTTPException(status_code=400, detail="No text provided")

        resolved_language_id = _resolve_language_id(voice, language_id, language)
        is_streaming = _parse_bool_flag(streaming)
        _LOGGER.debug(
            "Synthesizing text: %s (language_id=%s, streaming=%s)",
            body_text,
            resolved_language_id,
            is_streaming,
        )

        if is_streaming:
            sample_rate = voice.config.sample_rate

            def _iter_wav():
                yield _build_streaming_wav_header(sample_rate)
                for audio_bytes in voice.synthesize_stream_raw(
                    body_text,
                    **synthesize_args,
                    language_id=resolved_language_id,
                ):
                    yield audio_bytes

            return StreamingResponse(_iter_wav(), media_type="audio/wav")

        with io.BytesIO() as wav_io:
            with wave.open(wav_io, "wb") as wav_file:
                voice.synthesize(
                    body_text,
                    wav_file,
                    **synthesize_args,
                    language_id=resolved_language_id,
                )
            return Response(content=wav_io.getvalue(), media_type="audio/wav")

    @app.api_route("/api/phoneme-timing", methods=["GET", "POST"])
    async def app_phoneme_timing(
        request: Request,
        text: str | None = Query(None),
        format: str = Query("json"),
        language: str | None = Query(None),
        language_id: str | None = Query(None),
    ) -> Response:
        body_text = await _read_text(request, text)
        if not body_text:
            return JSONResponse(
                status_code=400, content={"error": "No text provided"}
            )

        fmt = format.lower()
        if fmt not in ("json", "tsv"):
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Unsupported format: {fmt}. Use 'json' or 'tsv'."
                },
            )

        resolved_language_id = _resolve_language_id(voice, language_id, language)
        _, timing_result = voice.synthesize_with_timing(
            body_text, **synthesize_args, language_id=resolved_language_id
        )

        if timing_result is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Model does not support duration output"},
            )

        if fmt == "tsv":
            return PlainTextResponse(
                content=timing_to_tsv(timing_result),
                media_type="text/tab-separated-values",
            )

        return Response(
            content=timing_to_json(timing_result),
            media_type="application/json",
        )

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="HTTP server host")
    parser.add_argument("--port", type=int, default=5000, help="HTTP server port")
    parser.add_argument(
        "-m", "--model", required=True, help="Path to Onnx model file"
    )
    parser.add_argument("-c", "--config", help="Path to model config file")
    parser.add_argument("-s", "--speaker", type=int, help="Id of speaker (default: 0)")
    parser.add_argument(
        "--length-scale", "--length_scale", type=float, help="Phoneme length"
    )
    parser.add_argument(
        "--noise-scale", "--noise_scale", type=float, help="Generator noise"
    )
    parser.add_argument(
        "--noise-w", "--noise_w", type=float, help="Phoneme width noise"
    )
    parser.add_argument("--cuda", action="store_true", help="Use GPU")
    parser.add_argument(
        "--sentence-silence",
        "--sentence_silence",
        type=float,
        default=0.0,
        help="Seconds of silence after each sentence",
    )
    parser.add_argument(
        "--data-dir",
        "--data_dir",
        action="append",
        default=[str(Path.cwd())],
        help="Data directory to check for downloaded models (default: current directory)",
    )
    parser.add_argument(
        "--download-dir",
        "--download_dir",
        help="Directory to download voices into (default: first data dir)",
    )
    parser.add_argument(
        "--update-voices",
        action="store_true",
        help="Download latest voices.json during startup",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print DEBUG messages to console"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    if not args.download_dir:
        args.download_dir = args.data_dir[0]

    model_path = Path(args.model)
    if not model_path.exists():
        voices_info = get_voices(args.download_dir, update_voices=args.update_voices)
        aliases_info: dict[str, Any] = {}
        for voice_info in voices_info.values():
            for voice_alias in voice_info.get("aliases", []):
                aliases_info[voice_alias] = {"_is_alias": True, **voice_info}
        voices_info.update(aliases_info)
        ensure_voice_exists(args.model, args.data_dir, args.download_dir, voices_info)
        args.model, args.config = find_voice(args.model, args.data_dir)

    voice = PiperVoice.load(args.model, config_path=args.config, use_cuda=args.cuda)
    synthesize_args: dict[str, Any] = {
        "speaker_id": args.speaker,
        "length_scale": args.length_scale,
        "noise_scale": args.noise_scale,
        "noise_w": args.noise_w,
        "sentence_silence": args.sentence_silence,
    }

    app = create_app(voice, synthesize_args)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
