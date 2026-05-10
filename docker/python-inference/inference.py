#!/usr/bin/env python3
"""
Inference script for piper-plus.
CLI and FastAPI server modes supported.

Server mode exposes:
- Native endpoint: ``GET /synthesize`` for direct piper-plus usage
- OpenAI-compatible endpoints (PR #321): ``POST /v1/audio/speech``,
  ``GET /v1/models``, ``GET /v1/audio/speech/languages`` so existing OpenAI
  clients can drop in unchanged
- ``GET /health`` for orchestrator health checks

Note: phoneme-timing JSON/TSV/SRT output is exposed by the separate
``piper.http_server`` (in ``src/python_run/``) under
``POST/GET /api/phoneme-timing``, not by this script.

Uses ``piper_plus_g2p.registry`` for text-to-phoneme conversion (8 languages:
JA/EN/ZH/KO/ES/FR/PT/SV) and ONNX Runtime for inference (CPU, no PyTorch
required).
"""

import argparse
import io
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from piper_plus_g2p.registry import get_phonemizer

from piper_train.ort_utils import create_session_with_cache, warmup_onnx_session


_LOGGER = logging.getLogger(__name__)

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
        self.language_id_map = config.get("language_id_map", {})

        _LOGGER.info(
            "Model loaded: %s (prosody=%s, sid=%s, lid=%s)",
            model_path,
            self.has_prosody,
            self.has_sid,
            self.has_lid,
        )

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

        text_input = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
        text_lengths = np.array([text_input.shape[1]], dtype=np.int64)
        scales = np.array([noise_scale, length_scale, noise_scale_w], dtype=np.float32)

        inputs = {
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


def create_app(engine: PiperInferenceEngine, model_path: str):
    """Create the FastAPI application with all endpoints."""
    from fastapi import FastAPI, HTTPException, Query  # noqa: PLC0415
    from fastapi.middleware.cors import CORSMiddleware  # noqa: PLC0415
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from pydantic import BaseModel, Field  # noqa: PLC0415

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

    app = FastAPI(title="piper-plus API")

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

    @app.get("/health")
    def health_check():
        return {"status": "healthy"}

    def _is_short_text(text: str, threshold: int = 10) -> bool:
        """Check if text is short (excluding whitespace)."""
        if text.lstrip().startswith(("<speak>", "<speak ")):
            return False
        return sum(1 for c in text if not c.isspace()) <= threshold

    @app.get("/synthesize")
    def synthesize(
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
                    text,
                )
            return StreamingResponse(buf, media_type="audio/wav", headers=headers)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    # --- OpenAI-compatible endpoints ---

    @app.post("/v1/audio/speech")
    def openai_speech(req: SpeechRequest):
        if not req.input or not req.input.strip():
            raise HTTPException(status_code=400, detail="input is required")
        if req.response_format != "wav":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported response_format: {req.response_format}. Only 'wav' is supported.",
            )

        length_scale = 1.0 / req.speed

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
            headers = {}
            if _is_short_text(req.input):
                headers["X-Piper-Warning"] = "short-text-input"
                _LOGGER.warning(
                    "Short text input detected (%d chars excl. spaces): %r",
                    len(req.input.replace(" ", "").replace("\u3000", "").strip()),
                    req.input,
                )
            return StreamingResponse(buf, media_type="audio/wav", headers=headers)
        except Exception:
            _LOGGER.exception("Synthesis failed for /v1/audio/speech")
            raise HTTPException(status_code=500, detail="Synthesis failed") from None

    @app.get("/v1/models")
    def openai_models():
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

    @app.get("/v1/audio/speech/languages")
    def speech_languages():
        languages = (
            sorted(engine.language_id_map.keys()) if engine.language_id_map else []
        )
        return {"languages": languages}

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
