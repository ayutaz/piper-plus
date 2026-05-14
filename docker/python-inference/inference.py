#!/usr/bin/env python3
"""
Inference script for piper-plus.
CLI and FastAPI server modes supported.

Server mode exposes:
- Native endpoint: ``GET /synthesize`` for direct piper-plus usage
- OpenAI-compatible endpoints (PR #321): ``POST /v1/audio/speech``,
    ``GET /v1/models``, ``GET /v1/audio/speech/languages`` so existing OpenAI
    clients can drop in unchanged
- ``POST /api/phoneme-timing`` — phoneme timing JSON output (parity with
    ``piper.http_server``; available when the ONNX model exposes a
    ``durations`` output tensor)
- ``GET /health`` for orchestrator health checks

Streaming
---------
``POST /v1/audio/speech`` accepts ``stream=true`` (request body) to receive a
chunked WAV response: a streaming-WAV header (placeholder ``0xFFFFFFFF`` for
RIFF/data sizes) followed by per-sentence PCM frames. ``stream=false`` (the
default) preserves the original behaviour of buffering the full WAV in a
single response — keeps existing OpenAI SDK clients working unchanged.

Uses ``piper_plus_g2p.registry`` for text-to-phoneme conversion (8 languages:
JA/EN/ZH/KO/ES/FR/PT/SV) and ONNX Runtime for inference (CPU, no PyTorch
required).
"""

import argparse
import io
import json
import logging
import os
import struct
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import soundfile as sf
from piper_plus_g2p.registry import get_phonemizer

from piper_train.ort_utils import create_session_with_cache, warmup_onnx_session


_LOGGER = logging.getLogger(__name__)


def _sanitize_for_log(value: str) -> str:
    # Strip CR/LF from user-controlled values before logging to prevent
    # log forging via line-break injection (CWE-117). Used at the HTTP
    # request boundaries `/synthesize` and `/v1/audio/speech`.
    return value.replace("\r", "").replace("\n", " ")


# Sentence terminators / closers mirror
# ``src/python_run/piper/text_splitter.py`` and the spec at
# ``docs/spec/text-splitter-contract.toml``. Kept inline here because the
# docker image installs ``piper_train`` + ``piper_plus_g2p`` only — not the
# ``piper`` runtime package — so we can't import ``piper.text_splitter``.
_SENTENCE_TERMINATORS: frozenset[str] = frozenset(
    {".", "!", "?", "。", "！", "？", "．"}
)
_CLOSING_PUNCTUATION: frozenset[str] = frozenset(
    {")", "]", "}", '"', "'", "」", "』", "）", "］", "】", "｣", "”", "’", "»"}
)


def _split_sentences(text: str) -> list[str]:
    """Sentence-level split for streaming synthesis.

    Mirrors ``piper.text_splitter.split_sentences``. SSML (``<speak>...``) is
    treated as a single unit — the SSML parser is invoked downstream by the
    phonemizer and must not be torn across chunk boundaries.
    """
    if not text:
        return []
    stripped = text.lstrip()
    if stripped.startswith(("<speak>", "<speak ")):
        return [text.strip()]

    sentences: list[str] = []
    current: list[str] = []
    chars = list(text)
    n = len(chars)
    i = 0
    while i < n:
        ch = chars[i]
        current.append(ch)
        i += 1
        if ch in _SENTENCE_TERMINATORS:
            while i < n and chars[i] in _CLOSING_PUNCTUATION:
                current.append(chars[i])
                i += 1
            trimmed = "".join(current).strip()
            if trimmed:
                sentences.append(trimmed)
            current.clear()
            while i < n and chars[i].isspace():
                i += 1
    trimmed = "".join(current).strip()
    if trimmed:
        sentences.append(trimmed)
    return sentences


# Streaming WAV constants (mirrors piper.http_server).
_WAV_CHANNELS = 1
_WAV_BIT_DEPTH = 16


def _build_streaming_wav_header(
    sample_rate: int,
    channels: int = _WAV_CHANNELS,
    bit_depth: int = _WAV_BIT_DEPTH,
) -> bytes:
    """Build a WAV header with placeholder sizes (``0xFFFFFFFF``).

    Browsers, ``ffmpeg``, and ``soundfile`` accept ``0xFFFFFFFF`` as the
    conventional "unknown length" sentinel for chunked WAV streams.
    Mirrors ``piper.http_server._build_streaming_wav_header``.
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


# FastAPI (optional)
try:
    import uvicorn  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def text_to_phoneme_ids_and_prosody(
    text: str,
    phoneme_id_map: dict[str, list[int]],
    language: str = "ja",
) -> tuple[list[int], list[dict | None]]:
    """Convert text to phoneme IDs and prosody features."""
    phonemizer = get_phonemizer(language)
    phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

    phoneme_ids: list[int] = []
    prosody_features: list[dict | None] = []

    for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
        if phoneme in phoneme_id_map:
            ids = phoneme_id_map[phoneme]
            phoneme_ids.extend(ids)
            for _ in ids:
                if prosody_info is not None:
                    prosody_features.append(
                        {
                            "a1": prosody_info.a1,
                            "a2": prosody_info.a2,
                            "a3": prosody_info.a3,
                        }
                    )
                else:
                    prosody_features.append(None)
        else:
            _LOGGER.warning("Unknown phoneme: %s", phoneme)

    return phoneme_ids, prosody_features


def audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range."""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    return audio_norm.astype("int16")


class PiperInferenceEngine:
    """Wraps ONNX model loading and synthesis."""

    def __init__(
        self,
        model_path: str,
        config_path: str,
        sample_rate: int = 22050,
        device: str = "auto",
    ):
        self.sample_rate = sample_rate

        # Load config
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        self.phoneme_id_map = config["phoneme_id_map"]

        # Load ONNX model with optimized session options + cache
        self.model = create_session_with_cache(model_path, device=device)
        warmup_onnx_session(self.model)

        active_providers = self.model.get_providers()
        _LOGGER.info("ONNX Runtime providers: %s", active_providers)

        input_names = [inp.name for inp in self.model.get_inputs()]
        self.has_prosody = "prosody_features" in input_names
        self.has_sid = "sid" in input_names
        self.has_lid = "lid" in input_names
        # PR #320 declares speaker_embedding AND speaker_embedding_mask as a
        # pair. Feeding only one to ORT would either raise "Required inputs
        # missing" (if mask is undeclared) or "Unexpected input" (if mask is
        # extra). Require both to be declared together — fail loud at load
        # time on a malformed export rather than silently at first request.
        has_speaker_embedding = "speaker_embedding" in input_names
        has_speaker_embedding_mask = "speaker_embedding_mask" in input_names
        if has_speaker_embedding != has_speaker_embedding_mask:
            raise RuntimeError(
                f"Malformed ONNX export: speaker_embedding="
                f"{has_speaker_embedding} but speaker_embedding_mask="
                f"{has_speaker_embedding_mask}. PR #320 contract requires "
                "both inputs to be declared together."
            )
        self.has_speaker_embedding = has_speaker_embedding
        self.speaker_emb_dim: int | None = None
        if self.has_speaker_embedding:
            for inp in self.model.get_inputs():
                if inp.name == "speaker_embedding":
                    # Shape: (batch, emb_dim) — emb_dim is the second axis.
                    # export_onnx.py emits it as a fixed int, but stay
                    # defensive in case a future model uses a dynamic axis.
                    try:
                        self.speaker_emb_dim = int(inp.shape[1])
                    except (TypeError, ValueError):
                        self.speaker_emb_dim = None
                    break
        self.language_id_map = config.get("language_id_map", {})

        # Detect whether the ONNX graph exposes a ``durations`` output tensor.
        # MB-iSTFT-VITS2 exports emit it by default (PR #320); older HiFi-GAN
        # exports do not. Required for /api/phoneme-timing — when absent the
        # endpoint returns 400 instead of synthesizing pointlessly.
        output_names = [o.name for o in self.model.get_outputs()]
        self.has_durations: bool = "durations" in output_names
        # hop_length used to convert durations → milliseconds. Matches the
        # canonical 256 used across all 7 runtimes (see
        # ``docs/spec/phoneme-timing-contract.toml``). Config may override.
        self.hop_length: int = int(config.get("audio", {}).get("hop_length", 256))

        _LOGGER.info(
            "Model loaded: %s (prosody=%s, sid=%s, lid=%s, speaker_embedding=%s, durations=%s)",
            model_path,
            self.has_prosody,
            self.has_sid,
            self.has_lid,
            f"dim={self.speaker_emb_dim}" if self.has_speaker_embedding else False,
            self.has_durations,
        )

    def _build_inputs(
        self,
        phoneme_ids: list[int],
        prosody_features_data: list[dict | None],
        language: str,
        speaker_id: int,
        noise_scale: float,
        length_scale: float,
        noise_scale_w: float,
    ) -> dict[str, np.ndarray]:
        """Pack ORT input feed dict. Extracted so both ``synthesize`` and the
        timing path share the exact same input contract (single source of truth
        for the PR #320 ``speaker_embedding`` fallback rules)."""
        text_input = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text_input.shape[1]], dtype=np.int64)
        scales = np.array([noise_scale, length_scale, noise_scale_w], dtype=np.float32)

        inputs: dict[str, np.ndarray] = {
            "input": text_input,
            "input_lengths": text_lengths,
            "scales": scales,
        }

        if self.has_sid:
            inputs["sid"] = np.array([speaker_id], dtype=np.int64)

        if self.has_prosody:
            if prosody_features_data:
                prosody_array = []
                for pf in prosody_features_data:
                    if pf is None:
                        prosody_array.append([0, 0, 0])
                    else:
                        prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
                prosody_np = np.expand_dims(np.array(prosody_array, dtype=np.int64), 0)
            else:
                prosody_np = np.zeros((1, text_input.shape[1], 3), dtype=np.int64)
            inputs["prosody_features"] = prosody_np

        if self.has_lid:
            language_id = self.language_id_map.get(language, 0)
            inputs["lid"] = np.array([language_id], dtype=np.int64)

        if self.has_speaker_embedding:
            # MB-iSTFT-VITS2 + Voice Cloning support exposes these inputs
            # unconditionally (PR #320). Feed a zero vector with mask=0 so
            # the model falls back to emb_g(sid) — see
            # `src/python/piper_train/vits/models.py` (`use_se = mask >= 1`)
            # and the matching runtime path in
            # `src/python_run/piper/voice.py`.
            emb_dim = self.speaker_emb_dim or 256
            inputs["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
            inputs["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)

        return inputs

    def synthesize(
        self,
        text: str,
        language: str = "ja",
        speaker_id: int = 0,
        noise_scale: float = 0.667,
        length_scale: float = 1.0,
        noise_scale_w: float = 0.8,
    ) -> np.ndarray:
        """Synthesize text to int16 audio array."""
        phoneme_ids, prosody_features_data = text_to_phoneme_ids_and_prosody(
            text,
            self.phoneme_id_map,
            language=language,
        )

        inputs = self._build_inputs(
            phoneme_ids,
            prosody_features_data,
            language,
            speaker_id,
            noise_scale,
            length_scale,
            noise_scale_w,
        )

        start = time.perf_counter()
        outputs = self.model.run(None, inputs)
        audio = outputs[0].squeeze(0)
        audio = audio_float_to_int16(audio.squeeze())
        elapsed = time.perf_counter() - start

        duration_sec = len(audio) / self.sample_rate
        rtf = elapsed / duration_sec if duration_sec > 0 else 0.0
        _LOGGER.info(
            "Synthesized %.2fs audio in %.2fs (RTF=%.2f)", duration_sec, elapsed, rtf
        )

        return audio

    def synthesize_with_timing(
        self,
        text: str,
        language: str = "ja",
        speaker_id: int = 0,
        noise_scale: float = 0.667,
        length_scale: float = 1.0,
        noise_scale_w: float = 0.8,
    ) -> dict | None:
        """Synthesize and return phoneme timing metadata.

        Returns ``None`` when the model has no ``durations`` output (so the
        caller can map that to HTTP 400). The returned dict matches the
        cross-runtime ``TimingResult`` shape: ``{phonemes, total_duration_ms,
        sample_rate}`` with millisecond timestamps computed from
        ``hop_length / sample_rate * 1000``. Byte-for-byte compatible with
        the Rust/Go/C++/C#/Python piper.timing implementations
        (see ``docs/spec/phoneme-timing-contract.toml``).
        """
        if not self.has_durations:
            return None

        phonemizer = get_phonemizer(language)
        phonemes, prosody_info_list = phonemizer.phonemize_with_prosody(text)

        # Build phoneme_ids while remembering the source token for each ID so
        # we can attach human-readable names to the timing entries.
        phoneme_ids: list[int] = []
        prosody_features: list[dict | None] = []
        token_for_id: list[str] = []
        for phoneme, prosody_info in zip(phonemes, prosody_info_list, strict=True):
            if phoneme in self.phoneme_id_map:
                ids = self.phoneme_id_map[phoneme]
                phoneme_ids.extend(ids)
                token_for_id.extend([phoneme] * len(ids))
                for _ in ids:
                    if prosody_info is not None:
                        prosody_features.append(
                            {
                                "a1": prosody_info.a1,
                                "a2": prosody_info.a2,
                                "a3": prosody_info.a3,
                            }
                        )
                    else:
                        prosody_features.append(None)
            else:
                _LOGGER.warning("Unknown phoneme: %s", phoneme)

        inputs = self._build_inputs(
            phoneme_ids,
            prosody_features,
            language,
            speaker_id,
            noise_scale,
            length_scale,
            noise_scale_w,
        )
        output_names = [o.name for o in self.model.get_outputs()]
        outputs = self.model.run(output_names, inputs)

        if "durations" not in output_names:
            return None
        durations = np.asarray(outputs[output_names.index("durations")]).reshape(-1)

        # If durations length disagrees with phoneme_ids (unusual but possible
        # with non-conventional exports), fall back to the shorter length.
        n = min(len(durations), len(token_for_id))
        frame_time_ms = (self.hop_length / self.sample_rate) * 1000.0

        phonemes_out: list[dict] = []
        cursor_ms = 0.0
        for i in range(n):
            dur_frames = max(float(durations[i]), 0.0)
            duration_ms = dur_frames * frame_time_ms
            start_ms = cursor_ms
            end_ms = cursor_ms + duration_ms
            phonemes_out.append(
                {
                    "phoneme": token_for_id[i],
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "duration_ms": duration_ms,
                }
            )
            cursor_ms = end_ms

        return {
            "phonemes": phonemes_out,
            "total_duration_ms": cursor_ms,
            "sample_rate": self.sample_rate,
        }

    def synthesize_stream_pcm(
        self,
        text: str,
        language: str = "ja",
        speaker_id: int = 0,
        noise_scale: float = 0.667,
        length_scale: float = 1.0,
        noise_scale_w: float = 0.8,
    ) -> Iterator[bytes]:
        """Yield raw PCM (int16, little-endian) per sentence.

        Splits *text* via ``_split_sentences`` and runs one ONNX inference per
        sentence, emitting PCM bytes immediately. The caller prepends a WAV
        header so the wire format is ``header + concat(pcm_chunks)``.

        SSML is treated as a single chunk (the phonemizer parses it
        end-to-end), so callers that pass ``<speak>...</speak>`` still get a
        valid response, just not a low-latency one.
        """
        sentences = _split_sentences(text)
        if not sentences:
            return
        for sentence in sentences:
            audio = self.synthesize(
                sentence,
                language=language,
                speaker_id=speaker_id,
                noise_scale=noise_scale,
                length_scale=length_scale,
                noise_scale_w=noise_scale_w,
            )
            # int16 little-endian — matches WAV PCM format declared by the
            # header. ``.tobytes()`` is contiguous in C order, which is LE on
            # all platforms we ship to (x86_64 / arm64).
            yield audio.astype("<i2", copy=False).tobytes()


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="piper-plus Inference")
    parser.add_argument(
        "--model", help="Path to ONNX model (required for CLI/server mode)"
    )
    parser.add_argument("--config", help="Path to config.json (default: next to model)")
    parser.add_argument("--text", help="Text to synthesize")
    parser.add_argument("--output", default="output.wav", help="Output WAV path")
    parser.add_argument("--speaker-id", type=int, default=0, help="Speaker ID")
    parser.add_argument(
        "--language",
        default="ja",
        choices=["ja", "en", "zh", "es", "fr", "pt"],
        help="Language",
    )
    parser.add_argument("--noise-scale", type=float, default=0.667)
    parser.add_argument("--length-scale", type=float, default=1.0)
    parser.add_argument("--noise-w", type=float, default=0.8)
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "gpu"],
        help="Device for inference (default: auto)",
    )
    parser.add_argument("--server", action="store_true", help="Run as FastAPI server")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument(
        "--webui",
        action="store_true",
        help="Run Gradio WebUI (also enabled by PIPER_WEBUI=1 env var)",
    )
    parser.add_argument(
        "--model-dir",
        default="/app/models",
        help="Directory containing ONNX models (WebUI mode)",
    )
    parser.add_argument(
        "--output-dir",
        default="/app/output",
        help="Directory for output files (WebUI mode)",
    )
    parser.add_argument(
        "--webui-port", type=int, default=7860, help="Gradio WebUI port"
    )
    args = parser.parse_args()

    # Check for WebUI mode (flag or env var)
    webui_mode = args.webui or os.environ.get("PIPER_WEBUI", "").strip() in (
        "1",
        "true",
    )
    if webui_mode:
        _run_webui(args)
        return

    # --model is required for CLI and server modes
    if not args.model:
        parser.error("--model is required for CLI and server modes")

    # Resolve config path: {model}.json -> {dir}/config.json
    if args.config:
        config_path = args.config
    else:
        candidate = Path(f"{args.model}.json")
        if candidate.exists():
            config_path = str(candidate)
        else:
            config_path = str(Path(args.model).parent / "config.json")

    engine = PiperInferenceEngine(
        args.model, config_path, sample_rate=args.sample_rate, device=args.device
    )

    if args.server:
        if not FASTAPI_AVAILABLE:
            print("FastAPI not installed. Install with: pip install fastapi uvicorn")
            sys.exit(1)
        _run_server(engine, args)
    else:
        if not args.text:
            print("--text is required in CLI mode")
            sys.exit(1)
        audio = engine.synthesize(
            args.text,
            language=args.language,
            speaker_id=args.speaker_id,
            noise_scale=args.noise_scale,
            length_scale=args.length_scale,
            noise_scale_w=args.noise_w,
        )
        sf.write(args.output, audio, args.sample_rate)
        print(f"Audio saved to: {args.output}")


def _parse_api_keys(raw: str | None) -> set[str]:
    """Parse PIPER_API_KEYS env var (comma-separated).

    Empty / unset → empty set (auth disabled). Whitespace and empty entries
    are stripped so trailing commas don't accidentally allow blank tokens.
    """
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


def _env_flag(name: str, default: bool) -> bool:
    """Parse a boolean env var. Accepts 1/true/yes/on (case-insensitive)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def create_app(engine: PiperInferenceEngine, model_path: str):
    """Create the FastAPI application with all endpoints.

    Auth (optional bearer token):
        Set ``PIPER_API_KEYS`` to a comma-separated list of accepted tokens.
        If unset/empty, auth is disabled and all requests pass (backward
        compatible). ``/health`` is always exempt for load-balancer probes.

    Rate limiting (slowapi, per-IP):
        ``PIPER_RATE_LIMIT_ENABLED`` (default ``true``) — master switch.
        ``PIPER_RATE_LIMIT_SPEECH`` (default ``30/minute``) — heavy synth
        endpoints.
        ``PIPER_RATE_LIMIT_LIGHT`` (default ``600/minute``) — metadata
        endpoints (``/v1/models``, ``/v1/audio/speech/languages``).
        ``/health`` is never rate-limited.

    Note: CORS is intentionally untouched in this PR; tightening allow-origins
    is tracked separately so we don't accidentally break embedded browser
    clients that depend on ``*``.
    """
    from fastapi import (  # noqa: PLC0415
        Depends,
        FastAPI,
        Header,
        HTTPException,
        Query,
        Request,
        status,
    )
    from fastapi.middleware.cors import CORSMiddleware  # noqa: PLC0415
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from pydantic import BaseModel, Field  # noqa: PLC0415
    from slowapi import Limiter  # noqa: PLC0415
    from slowapi.errors import RateLimitExceeded  # noqa: PLC0415
    from slowapi.util import get_remote_address  # noqa: PLC0415
    from starlette.responses import JSONResponse  # noqa: PLC0415

    class SpeechRequest(BaseModel):
        """OpenAI-compatible TTS request schema."""

        model: str = "piper-plus"
        input: str
        voice: str = "default"
        response_format: str = "wav"
        speed: float = Field(default=1.0, gt=0.0, le=4.0)
        # piper-plus extensions
        speaker_id: int = 0
        language: str = "ja"
        noise_scale: float = 0.667
        noise_w: float = 0.8
        # ``stream=true`` (piper-plus extension) → chunked WAV response: a
        # streaming WAV header followed by per-sentence PCM frames. Defaults
        # to ``false`` so the response is a buffered WAV (original behaviour),
        # which keeps existing OpenAI SDK clients working unchanged.
        stream: bool = False

    class PhonemeTimingRequest(BaseModel):
        """Phoneme-timing request schema (parity with ``piper.http_server``).

        ``voice`` is accepted for OpenAI-style symmetry but currently ignored:
        the server is bound to a single model at startup, so cross-voice
        timing is out of scope until multi-model wiring lands.
        """

        text: str
        language: str = "ja"
        voice: str = "default"
        speaker_id: int = 0
        noise_scale: float = 0.667
        length_scale: float = 1.0
        noise_w: float = 0.8

    # --- Auth / rate-limit configuration (resolved at app-build time) ---
    api_keys: set[str] = _parse_api_keys(os.environ.get("PIPER_API_KEYS"))
    auth_enabled: bool = bool(api_keys)
    rate_limit_enabled: bool = _env_flag("PIPER_RATE_LIMIT_ENABLED", default=True)
    speech_limit: str = os.environ.get("PIPER_RATE_LIMIT_SPEECH", "30/minute")
    light_limit: str = os.environ.get("PIPER_RATE_LIMIT_LIGHT", "600/minute")

    if auth_enabled:
        _LOGGER.info("Bearer auth enabled (%d key(s) configured)", len(api_keys))
    else:
        _LOGGER.info(
            "Bearer auth disabled (PIPER_API_KEYS unset). Set the env var to "
            "enable per-key authentication."
        )

    # slowapi: when rate_limit_enabled=False we still construct the Limiter
    # but pass `enabled=False` so the decorators become no-ops. This keeps a
    # single code path and lets tests flip the switch via env vars.
    limiter = Limiter(key_func=get_remote_address, enabled=rate_limit_enabled)
    if rate_limit_enabled:
        _LOGGER.info(
            "Rate limit enabled (speech=%s, light=%s, per-IP via slowapi)",
            speech_limit,
            light_limit,
        )
    else:
        _LOGGER.info("Rate limit disabled (PIPER_RATE_LIMIT_ENABLED=false)")

    def verify_api_key(
        authorization: str | None = Header(default=None),
    ) -> None:
        """FastAPI dependency: enforce Bearer auth when PIPER_API_KEYS is set.

        - No keys configured: no-op (backward compatible).
        - Keys configured: require ``Authorization: Bearer <key>``;
            401 on missing / malformed header or unknown key.
        """
        if not auth_enabled:
            return
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header (expected 'Bearer <key>')",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if token not in api_keys:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )

    app = FastAPI(title="piper-plus API")
    app.state.limiter = limiter

    def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
        # slowapi's default handler returns plain text; emit JSON with a
        # Retry-After header so OpenAI-compatible clients can back off
        # automatically.
        retry_after = getattr(exc, "retry_after", None) or 60
        headers = {"Retry-After": str(int(retry_after))}
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": f"Rate limit exceeded: {exc.detail}",
            },
            headers=headers,
        )

    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    try:
        model_created = int(Path(model_path).stat().st_mtime)
    except OSError:
        model_created = int(time.time())

    # /health is intentionally outside auth + rate limit so external load
    # balancers and k8s liveness probes never get 401/429 (would mark the
    # container unhealthy and trigger a restart loop).
    @app.get("/health")
    def health_check():
        return {"status": "healthy"}

    def _is_short_text(text: str, threshold: int = 10) -> bool:
        """Check if text is short (excluding whitespace)."""
        if text.lstrip().startswith(("<speak>", "<speak ")):
            return False
        return sum(1 for c in text if not c.isspace()) <= threshold

    @app.get("/synthesize", dependencies=[Depends(verify_api_key)])
    @limiter.limit(speech_limit)
    def synthesize(
        request: Request,
        text: str = Query(...),
        speaker_id: int = Query(0),
        language: str = Query("ja"),
        noise_scale: float = Query(0.667),
        length_scale: float = Query(1.0),
        noise_w: float = Query(0.8),
    ):
        try:
            audio = engine.synthesize(
                text,
                language=language,
                speaker_id=speaker_id,
                noise_scale=noise_scale,
                length_scale=length_scale,
                noise_scale_w=noise_w,
            )
            buf = io.BytesIO()
            sf.write(buf, audio, engine.sample_rate, format="WAV")
            buf.seek(0)
            headers = {}
            if _is_short_text(text):
                headers["X-Piper-Warning"] = "short-text-input"
                _LOGGER.warning(
                    "Short text input detected (%d chars excl. spaces): %r",
                    len(text.replace(" ", "").replace("\u3000", "").strip()),
                    _sanitize_for_log(text),
                )
            return StreamingResponse(buf, media_type="audio/wav", headers=headers)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    # --- OpenAI-compatible endpoints ---

    @app.post("/v1/audio/speech", dependencies=[Depends(verify_api_key)])
    @limiter.limit(speech_limit)
    def openai_speech(request: Request, req: SpeechRequest):
        if not req.input or not req.input.strip():
            raise HTTPException(status_code=400, detail="input is required")
        if req.response_format != "wav":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported response_format: {req.response_format}. Only 'wav' is supported.",
            )

        length_scale = 1.0 / req.speed

        headers: dict[str, str] = {}
        if _is_short_text(req.input):
            headers["X-Piper-Warning"] = "short-text-input"
            _LOGGER.warning(
                "Short text input detected (%d chars excl. spaces): %r",
                len(req.input.replace(" ", "").replace("\u3000", "").strip()),
                _sanitize_for_log(req.input),
            )

        if req.stream:
            # True streaming: emit a streaming-WAV header (placeholder sizes)
            # followed by per-sentence PCM frames. Clients that concatenate
            # the chunks get a valid WAV with ``0xFFFFFFFF`` size fields,
            # accepted by browsers / ffmpeg / soundfile.
            sample_rate = engine.sample_rate

            def _iter_chunks() -> Iterator[bytes]:
                try:
                    yield _build_streaming_wav_header(sample_rate)
                    yield from engine.synthesize_stream_pcm(
                        req.input,
                        language=req.language,
                        speaker_id=req.speaker_id,
                        noise_scale=req.noise_scale,
                        length_scale=length_scale,
                        noise_scale_w=req.noise_w,
                    )
                except Exception:
                    # Headers have already been sent \u2014 we can no longer return
                    # 500. Log so operators can diagnose client truncation.
                    _LOGGER.exception("Streaming synthesis failed for /v1/audio/speech")
                    raise

            return StreamingResponse(
                _iter_chunks(), media_type="audio/wav", headers=headers
            )

        try:
            audio = engine.synthesize(
                req.input,
                language=req.language,
                speaker_id=req.speaker_id,
                noise_scale=req.noise_scale,
                length_scale=length_scale,
                noise_scale_w=req.noise_w,
            )
            buf = io.BytesIO()
            sf.write(buf, audio, engine.sample_rate, format="WAV")
            buf.seek(0)
            return StreamingResponse(buf, media_type="audio/wav", headers=headers)
        except Exception:
            _LOGGER.exception("Synthesis failed for /v1/audio/speech")
            raise HTTPException(status_code=500, detail="Synthesis failed") from None

    @app.get("/v1/models", dependencies=[Depends(verify_api_key)])
    @limiter.limit(light_limit)
    def openai_models(request: Request):
        return {
            "object": "list",
            "data": [
                {
                    "id": "piper-plus",
                    "object": "model",
                    "created": model_created,
                    "owned_by": "piper-plus",
                }
            ],
        }

    @app.get("/v1/audio/speech/languages", dependencies=[Depends(verify_api_key)])
    @limiter.limit(light_limit)
    def speech_languages(request: Request):
        languages = (
            sorted(engine.language_id_map.keys()) if engine.language_id_map else []
        )
        return {"languages": languages}

    # --- Phoneme timing endpoint ---
    #
    # Parity with the ``piper.http_server`` endpoint of the same name (see
    # ``src/python_run/piper/http_server.py``). Returns the
    # cross-runtime-canonical TimingResult shape (matches Rust / Go / C++ /
    # C# byte-for-byte: ``(hop_length / sample_rate) * 1000`` ms per frame).
    # Falls back to 400 when the model has no ``durations`` output — older
    # HiFi-GAN exports — so callers don't silently get zeros.

    @app.post("/api/phoneme-timing")
    def phoneme_timing(req: PhonemeTimingRequest):
        if not req.text or not req.text.strip():
            raise HTTPException(status_code=400, detail="text is required")

        try:
            result = engine.synthesize_with_timing(
                req.text,
                language=req.language,
                speaker_id=req.speaker_id,
                noise_scale=req.noise_scale,
                length_scale=req.length_scale,
                noise_scale_w=req.noise_w,
            )
        except Exception:
            _LOGGER.exception("Phoneme timing failed for /api/phoneme-timing")
            raise HTTPException(
                status_code=500, detail="Phoneme timing failed"
            ) from None

        if result is None:
            # 400 (not 500) — the model is just missing the optional
            # ``durations`` output. The endpoint contract documents this.
            raise HTTPException(
                status_code=400,
                detail="Model does not support duration output",
            )
        return result

    return app


def _run_server(engine: PiperInferenceEngine, args):
    """Run FastAPI server."""
    import uvicorn  # noqa: PLC0415

    app = create_app(engine, args.model)
    uvicorn.run(app, host="0.0.0.0", port=args.port)


def _run_webui(args):
    """Launch the Gradio WebUI."""
    try:
        from webui import create_ui  # noqa: PLC0415
    except ImportError:
        try:
            # Fallback: try absolute import path
            import importlib.util  # noqa: PLC0415

            script_dir = Path(__file__).resolve().parent
            webui_path = script_dir / "webui.py"
            if webui_path.exists():
                spec = importlib.util.spec_from_file_location("webui", webui_path)
                webui_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(webui_mod)
                create_ui = webui_mod.create_ui
            else:
                print("WebUI not available. Ensure webui.py is in the same directory.")
                sys.exit(1)
        except Exception as e:
            print(f"Failed to import WebUI: {e}")
            sys.exit(1)

    host = "0.0.0.0"
    port = args.webui_port
    model_dir = args.model_dir
    output_dir = args.output_dir

    _LOGGER.info("Starting Gradio WebUI on %s:%d (model_dir=%s)", host, port, model_dir)
    demo = create_ui(model_dir, output_dir)
    demo.launch(server_name=host, server_port=port)


if __name__ == "__main__":
    main()
