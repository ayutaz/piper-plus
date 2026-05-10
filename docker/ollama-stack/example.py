#!/usr/bin/env python3
"""Ollama + piper-plus integration demo.

Usage:
    pip install requests
    python example.py "日本の首都について教えてください"
    python example.py "Tell me about Tokyo" --language en
"""

import argparse

import requests


def generate_text(
    prompt: str, model: str = "llama3.2", base_url: str = "http://localhost:11434"
) -> str:
    """Generate text using Ollama API."""
    resp = requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def synthesize_speech(
    text: str,
    output_path: str = "output.wav",
    language: str = "ja",
    base_url: str = "http://localhost:8000",
) -> None:
    """Synthesize speech using piper-plus OpenAI-compatible API."""
    resp = requests.post(
        f"{base_url}/v1/audio/speech",
        json={
            "input": text,
            "model": "piper-plus",
            "voice": "default",
            "language": language,
        },
        timeout=60,
    )
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)
    print(f"Audio saved to {output_path} ({len(resp.content)} bytes)")


def main():
    parser = argparse.ArgumentParser(description="Ollama + piper-plus integration demo")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="こんにちは、自己紹介をしてください。",
        help="Prompt for LLM",
    )
    parser.add_argument(
        "--language", "-l", default="ja", help="Language for TTS (default: ja)"
    )
    parser.add_argument(
        "--model",
        "-m",
        default="llama3.2",
        help="Ollama model name (default: llama3.2)",
    )
    parser.add_argument(
        "--output", "-o", default="output.wav", help="Output WAV file path"
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434", help="Ollama API URL"
    )
    parser.add_argument(
        "--piper-url", default="http://localhost:8000", help="piper-plus API URL"
    )
    args = parser.parse_args()

    print(f"Generating text for: {args.prompt}")
    text = generate_text(args.prompt, model=args.model, base_url=args.ollama_url)
    print(f"Generated ({len(text)} chars): {text[:200]}...")
    print()
    synthesize_speech(
        text, output_path=args.output, language=args.language, base_url=args.piper_url
    )


if __name__ == "__main__":
    main()
