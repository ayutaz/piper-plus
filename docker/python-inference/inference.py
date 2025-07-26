#!/usr/bin/env python3
"""
Simple inference script for Piper TTS
Can be used standalone or as a FastAPI service
"""

import argparse
import os
import sys

import numpy as np
import soundfile as sf

# Optional: FastAPI support
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class TTSRequest(BaseModel):
    text: str
    speaker_id: int | None = 0
    output_file: str | None = None
    noise_scale: float | None = 0.667
    length_scale: float | None = 1.0
    noise_w: float | None = 0.8


def synthesize_text(
    text: str,
    model_path: str,
    output_path: str,
    speaker_id: int = 0,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_w: float = 0.8,
) -> str:
    """
    Synthesize text to speech using Piper TTS

    Args:
        text: Input text to synthesize
        model_path: Path to the ONNX model file
        output_path: Path for output WAV file
        speaker_id: Speaker ID for multi-speaker models
        noise_scale: Generator noise scale
        length_scale: Phoneme length scale
        noise_w: Phoneme width noise scale

    Returns:
        Path to the generated audio file
    """
    try:
        # Import here to allow script to show help without loading heavy libraries
        import piper  # noqa: PLC0415

        # Load voice
        voice = piper.PiperVoice.load(model_path)

        # Synthesize audio
        audio = voice.synthesize(
            text,
            speaker_id=speaker_id,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w=noise_w,
        )

        # Convert generator to numpy array
        audio_data = np.array(list(audio), dtype=np.int16)

        # Save audio
        sf.write(output_path, audio_data, voice.config.sample_rate)

        return output_path

    except Exception as e:
        raise RuntimeError(f"Synthesis failed: {str(e)}") from e


def main():
    parser = argparse.ArgumentParser(description="Piper TTS Inference Script")
    parser.add_argument("--text", type=str, help="Text to synthesize")
    parser.add_argument("--input-file", type=str, help="Text file to read from")
    parser.add_argument("--model", type=str, required=True, help="Path to ONNX model")
    parser.add_argument(
        "--output", type=str, default="output.wav", help="Output WAV file"
    )
    parser.add_argument("--speaker", type=int, default=0, help="Speaker ID")
    parser.add_argument("--noise-scale", type=float, default=0.667, help="Noise scale")
    parser.add_argument("--length-scale", type=float, default=1.0, help="Length scale")
    parser.add_argument("--noise-w", type=float, default=0.8, help="Noise W")
    parser.add_argument("--server", action="store_true", help="Run as API server")
    parser.add_argument("--port", type=int, default=8000, help="API server port")

    args = parser.parse_args()

    # Run as API server
    if args.server:
        if not FASTAPI_AVAILABLE:
            print("FastAPI not available. Install with: pip install fastapi uvicorn")
            sys.exit(1)

        app = FastAPI(title="Piper TTS API")

        @app.get("/health")
        def health_check():
            return {"status": "healthy"}

        @app.post("/synthesize")
        async def synthesize(request: TTSRequest):
            try:
                output_file = request.output_file or f"output_{hash(request.text)}.wav"
                output_path = os.path.join("/app/output", output_file)

                synthesize_text(
                    request.text,
                    args.model,
                    output_path,
                    request.speaker_id,
                    request.noise_scale,
                    request.length_scale,
                    request.noise_w,
                )

                return FileResponse(output_path, media_type="audio/wav")

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

        uvicorn.run(app, host="0.0.0.0", port=args.port)

    # Run as CLI tool
    else:
        if args.text:
            text = args.text
        elif args.input_file:
            with open(args.input_file, encoding="utf-8") as f:
                text = f.read()
        else:
            print("Reading from stdin...")
            text = sys.stdin.read()

        if not text.strip():
            print("No text provided")
            sys.exit(1)

        print(f"Synthesizing: {text[:50]}...")
        output_path = synthesize_text(
            text,
            args.model,
            args.output,
            args.speaker,
            args.noise_scale,
            args.length_scale,
            args.noise_w,
        )
        print(f"Audio saved to: {output_path}")


if __name__ == "__main__":
    main()
