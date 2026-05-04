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

import uvicorn
from fastapi import FastAPI, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from . import PiperVoice
from .download import ensure_voice_exists, find_voice, get_voices
from .timing import timing_to_json, timing_to_tsv


_LOGGER = logging.getLogger(__name__)

# Default channel/bit-depth assumptions match `PiperVoice.synthesize` output.
_WAV_CHANNELS = 1
_WAV_BIT_DEPTH = 16

# Generous text body cap. Practical Piper utterances are well under 10 KiB;
# 1 MiB stays out of the way of legitimate batched requests while preventing
# memory blow-up from a single client.
MAX_TEXT_BYTES = 1 * 1024 * 1024


def _build_streaming_wav_header(
    sample_rate: int,
    channels: int = _WAV_CHANNELS,
    bit_depth: int = _WAV_BIT_DEPTH,
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
    voice: Any,
    language_id_raw: str | None,
    language: str | None,
) -> int | None:
    """Resolve query parameters to an integer language id.

    Falls back to ``None`` for unparseable / unknown / out-of-range values to
    preserve the silent-fallback behavior of the FastAPI server (compatible
    with the previous Flask implementation). Out-of-range values are logged so
    operators can spot misconfigured clients.
    """
    lmap = getattr(voice.config, "language_id_map", None) or None

    if language_id_raw is not None:
        try:
            language_id = int(language_id_raw)
        except (ValueError, TypeError):
            return None
        if lmap is not None:
            valid_ids = set(lmap.values())
            if language_id not in valid_ids:
                _LOGGER.warning(
                    "language_id=%s out of range (valid: %s); falling back to None",
                    language_id,
                    sorted(valid_ids),
                )
                return None
        return language_id

    if language is not None and lmap is not None:
        return lmap.get(language)

    return None


async def _read_text(request: Request, query_text: str | None) -> str:
    """Read text from POST body or GET ``?text=`` query, with a size cap.

    POST bodies are read as a stream and aborted once ``MAX_TEXT_BYTES`` is
    exceeded, so chunked / Content-Length-less uploads cannot blow up memory.
    The same cap is applied to GET ``?text=`` (UTF-8 byte length).
    """
    if request.method == "POST":
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > MAX_TEXT_BYTES:
                    raise _RequestTooLarge()
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_TEXT_BYTES:
                raise _RequestTooLarge()
            chunks.append(chunk)
        text = b"".join(chunks).decode("utf-8", errors="replace")
    else:
        text = query_text or ""
        if len(text.encode("utf-8", errors="replace")) > MAX_TEXT_BYTES:
            raise _RequestTooLarge()
    return text.strip()


class _RequestTooLarge(Exception):
    """Internal sentinel for body-size enforcement."""


def _parse_bool_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on")


def _error_response(status_code: int, message: str) -> JSONResponse:
    """FastAPI compatible ``{"error": ...}`` JSON error body (matches the legacy Flask shape)."""
    return JSONResponse(status_code=status_code, content={"error": message})


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
        """Synthesize speech and return ``audio/wav``.

        Text comes from the POST body or ``?text=`` query (cap: ``MAX_TEXT_BYTES``).
        Pass ``?streaming=true`` to receive a chunked WAV (placeholder header +
        per-sentence PCM frames via ``synthesize_stream_raw``); otherwise the
        full WAV is buffered and returned in one response. ``?language=`` /
        ``?language_id=`` route through the loaded voice's language map.
        """
        try:
            body_text = await _read_text(request, text)
        except _RequestTooLarge:
            return _error_response(413, f"Request body exceeds {MAX_TEXT_BYTES} bytes")

        if not body_text:
            return _error_response(400, "No text provided")

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
                try:
                    yield _build_streaming_wav_header(sample_rate)
                    yield from voice.synthesize_stream_raw(
                        body_text,
                        **synthesize_args,
                        language_id=resolved_language_id,
                    )
                except Exception:
                    # Headers have already been sent — we cannot return 500.
                    # Log so operators can diagnose silent client truncation.
                    _LOGGER.exception("Streaming synthesis failed")
                    raise

            return StreamingResponse(_iter_wav(), media_type="audio/wav")

        def _do_synth() -> bytes:
            with io.BytesIO() as wav_io:
                with wave.open(wav_io, "wb") as wav_file:
                    voice.synthesize(
                        body_text,
                        wav_file,
                        **synthesize_args,
                        language_id=resolved_language_id,
                    )
                return wav_io.getvalue()

        wav_bytes = await run_in_threadpool(_do_synth)
        return Response(content=wav_bytes, media_type="audio/wav")

    @app.api_route("/api/phoneme-timing", methods=["GET", "POST"])
    async def app_phoneme_timing(
        request: Request,
        text: str | None = Query(None),
        fmt: str = Query("json", alias="format"),
        language: str | None = Query(None),
        language_id: str | None = Query(None),
    ) -> Response:
        """Return phoneme timing as JSON or TSV.

        Calls ``PiperVoice.synthesize_with_timing`` (audio is discarded; only
        timing metadata is returned). ``?format=json`` (default) or ``tsv``.
        Returns 400 if the model lacks ``durations`` output. Compatible with
        Rust/Go/C++/C# implementations (byte-for-byte timing values).
        """
        try:
            body_text = await _read_text(request, text)
        except _RequestTooLarge:
            return _error_response(413, f"Request body exceeds {MAX_TEXT_BYTES} bytes")

        if not body_text:
            return _error_response(400, "No text provided")

        fmt_lower = fmt.lower()
        if fmt_lower not in ("json", "tsv"):
            return _error_response(
                400, f"Unsupported format: {fmt_lower}. Use 'json' or 'tsv'."
            )

        resolved_language_id = _resolve_language_id(voice, language_id, language)

        def _do_timing():
            return voice.synthesize_with_timing(
                body_text,
                **synthesize_args,
                language_id=resolved_language_id,
            )

        _, timing_result = await run_in_threadpool(_do_timing)

        if timing_result is None:
            return _error_response(400, "Model does not support duration output")

        if fmt_lower == "tsv":
            return PlainTextResponse(
                content=timing_to_tsv(timing_result),
                media_type="text/tab-separated-values",
            )

        return Response(
            content=timing_to_json(timing_result),
            media_type="application/json",
        )

    return app


def _warn_if_public_bind(host: str) -> None:
    """Log a startup warning when binding to a non-loopback address."""
    if host in ("0.0.0.0", "::", ""):
        _LOGGER.warning(
            "Binding to %s with no authentication. "
            "Anyone able to reach this port can synthesize audio. "
            "Pass --host 127.0.0.1 to restrict to localhost.",
            host or "0.0.0.0",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="HTTP server host")
    parser.add_argument("--port", type=int, default=5000, help="HTTP server port")
    parser.add_argument("-m", "--model", required=True, help="Path to Onnx model file")
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

    _warn_if_public_bind(args.host)

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
