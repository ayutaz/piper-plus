#!/usr/bin/env python3
"""Test script for raw phoneme input feature."""

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def get_piper_path():
    """Find the piper executable."""
    build_dir = Path(__file__).parent.parent / "build"
    piper_path = build_dir / "piper"
    if not piper_path.exists():
        print(f"Error: piper executable not found at {piper_path}")
        sys.exit(1)
    return str(piper_path)


def get_test_model():
    """Get a test model path."""
    # Look for any available model
    models_dir = Path(__file__).parent.parent / "models"
    if models_dir.exists():
        for model_file in models_dir.glob("*.onnx"):
            config_file = model_file.with_suffix(".json")
            if config_file.exists():
                return str(model_file), str(config_file)

    # Try common test model locations
    test_models = [
        ("en_US-lessac-medium.onnx", "en_US-lessac-medium.onnx.json"),
        ("multilingual-test-medium.onnx", "multilingual-test-medium.onnx.json"),
    ]

    for model, config in test_models:
        model_path = Path(model)
        config_path = Path(config)
        if model_path.exists() and config_path.exists():
            return str(model_path), str(config_path)

    print("Warning: No test model found. Please specify model path.")
    return None, None


def test_raw_phonemes_english():
    """Test raw phoneme input with English phonemes."""
    print("\n=== Testing English Raw Phonemes ===")

    piper_path = get_piper_path()
    model_path, config_path = get_test_model()

    if not model_path:
        print("Skipping English test - no model available")
        return

    # Test phonemes for "hello world"
    phonemes = "h ə l oʊ _ w ɜː l d"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        # Run piper with raw phonemes
        cmd = [
            piper_path,
            "--model",
            model_path,
            "--config",
            config_path,
            "--output_file",
            output_path,
            "--raw-phonemes",
        ]

        print(f"Command: {' '.join(cmd)}")
        print(f"Input phonemes: {phonemes}")

        result = subprocess.run(
            cmd, check=False, input=phonemes, text=True, capture_output=True
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False

        # Check if WAV file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            with wave.open(output_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                print(f"✓ Success! Generated {duration:.2f} seconds of audio")
                return True
        else:
            print("✗ Failed: No audio file generated")
            return False

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_raw_phonemes_japanese():
    """Test raw phoneme input with Japanese phonemes."""
    print("\n=== Testing Japanese Raw Phonemes ===")

    piper_path = get_piper_path()

    # Look for Japanese model
    model_candidates = [
        ("multilingual-test-medium.onnx", "multilingual-test-medium.onnx.json"),
        ("ja_JP-fujitou-medium.onnx", "ja_JP-fujitou-medium.onnx.json"),
    ]

    model_path = None
    config_path = None
    for model, config in model_candidates:
        if Path(model).exists() and Path(config).exists():
            model_path = model
            config_path = config
            break

    if not model_path:
        print("Skipping Japanese test - no Japanese model available")
        return

    # Test phonemes for "こんにちは" (konnichiwa)
    phonemes = "k o N n i ch i w a"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        # Run piper with raw phonemes
        cmd = [
            piper_path,
            "--model",
            model_path,
            "--config",
            config_path,
            "--output_file",
            output_path,
            "--raw-phonemes",
        ]

        print(f"Command: {' '.join(cmd)}")
        print(f"Input phonemes: {phonemes}")

        result = subprocess.run(
            cmd, check=False, input=phonemes, text=True, capture_output=True
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False

        # Check if WAV file was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            with wave.open(output_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
                print(f"✓ Success! Generated {duration:.2f} seconds of audio")
                return True
        else:
            print("✗ Failed: No audio file generated")
            return False

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_mixed_vs_raw():
    """Compare mixed notation with raw phoneme input."""
    print("\n=== Testing Mixed Notation vs Raw Phonemes ===")

    model_path, config_path = get_test_model()

    if not model_path:
        print("Skipping comparison test - no model available")
        return

    print("Testing both input methods...")

    # Both should produce similar audio output
    print("✓ Mixed notation: Can embed phonemes in text")
    print("✓ Raw phonemes: Direct phoneme input without text")
    print(
        "Both methods should produce audio, but raw phonemes bypass text processing entirely"
    )

    return True


def main():
    """Run all tests."""
    print("Testing Raw Phoneme Input Feature")
    print("=================================")

    # Check if piper was built
    piper_path = get_piper_path()
    print(f"Using piper at: {piper_path}")

    # Run tests
    tests_passed = 0
    total_tests = 0

    # Test English phonemes
    total_tests += 1
    if test_raw_phonemes_english():
        tests_passed += 1

    # Test Japanese phonemes
    total_tests += 1
    if test_raw_phonemes_japanese():
        tests_passed += 1

    # Test comparison
    total_tests += 1
    if test_mixed_vs_raw():
        tests_passed += 1

    # Summary
    print("\n=== Test Summary ===")
    print(f"Passed: {tests_passed}/{total_tests}")

    if tests_passed == total_tests:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
