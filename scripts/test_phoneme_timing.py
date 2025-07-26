#!/usr/bin/env python3
"""Test phoneme timing functionality"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_duration_export():
    """Test exporting model with duration information"""
    print("Testing duration export...")

    # Find a test checkpoint
    checkpoint_path = Path("test_data_pl2/epoch=100-step=1000.ckpt")
    if not checkpoint_path.exists():
        print("Warning: Test checkpoint not found, skipping export test")
        return False

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tmp_model:
        try:
            # Export with durations
            cmd = [
                sys.executable, "-m", "piper_train.export_onnx",
                str(checkpoint_path),
                tmp_model.name,
                "--with-durations"
            ]

            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Export failed: {result.stderr}")
                return False

            print(f"Successfully exported model with durations to {tmp_model.name}")
            return True

        finally:
            if os.path.exists(tmp_model.name):
                os.unlink(tmp_model.name)

def test_timing_extraction():
    """Test extracting timing from synthesis"""
    print("\nTesting timing extraction...")

    # Check if piper binary exists
    piper_bin = Path("build/piper")
    if not piper_bin.exists():
        print("Warning: piper binary not found at build/piper")
        return False

    # Find test model
    test_models = list(Path("test/models").glob("*.onnx"))
    if not test_models:
        print("Warning: No test models found")
        return False

    model_path = test_models[0]
    config_path = model_path.with_suffix(".onnx.json")

    # Test texts for different languages
    test_texts = {
        "en": "Hello world, this is a test.",
        "ja": "こんにちは世界。これはテストです。",
    }

    for lang, text in test_texts.items():
        print(f"\nTesting {lang}: {text}")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.wav', delete=False) as audio_file:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as timing_file:
                try:
                    # Run piper with timing output
                    cmd = [
                        str(piper_bin),
                        "--model", str(model_path),
                        "--config", str(config_path),
                        "--output-file", audio_file.name,
                        "--output-timing", timing_file.name,
                        "--timing-format", "json"
                    ]

                    result = subprocess.run(
                        cmd,
                        check=False, input=text,
                        text=True,
                        capture_output=True
                    )

                    if result.returncode != 0:
                        print(f"Synthesis failed: {result.stderr}")
                        continue

                    # Check if timing file was created
                    if not os.path.exists(timing_file.name):
                        print("Timing file was not created")
                        continue

                    # Read and validate timing data
                    with open(timing_file.name) as f:
                        timing_data = json.load(f)

                    if "phonemes" not in timing_data:
                        print("No phonemes in timing data")
                        continue

                    print(f"Found {len(timing_data['phonemes'])} phonemes")
                    print(f"Total duration: {timing_data.get('total_duration', 0):.3f}s")

                    # Show first few phonemes
                    for _i, phoneme in enumerate(timing_data['phonemes'][:5]):
                        print(f"  {phoneme['phoneme']}: "
                              f"{phoneme['start']:.3f} - {phoneme['end']:.3f}s")

                    if len(timing_data['phonemes']) > 5:
                        print("  ...")

                finally:
                    # Clean up
                    for f in [audio_file.name, timing_file.name]:
                        if os.path.exists(f):
                            os.unlink(f)

def test_tsv_format():
    """Test TSV output format"""
    print("\nTesting TSV format...")

    piper_bin = Path("build/piper")
    if not piper_bin.exists():
        return False

    test_models = list(Path("test/models").glob("*.onnx"))
    if not test_models:
        return False

    model_path = test_models[0]
    config_path = model_path.with_suffix(".onnx.json")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.wav', delete=False) as audio_file:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as timing_file:
            try:
                cmd = [
                    str(piper_bin),
                    "--model", str(model_path),
                    "--config", str(config_path),
                    "--output-file", audio_file.name,
                    "--output-timing", timing_file.name,
                    "--timing-format", "tsv"
                ]

                result = subprocess.run(
                    cmd,
                    check=False, input="Test TSV output",
                    text=True,
                    capture_output=True
                )

                if result.returncode == 0 and os.path.exists(timing_file.name):
                    with open(timing_file.name) as f:
                        lines = f.readlines()

                    if lines and lines[0].strip() == "phoneme\tstart\tend\tstart_frame\tend_frame":
                        print("TSV format test passed")
                        print(f"Generated {len(lines)-1} phoneme entries")
                        return True

            finally:
                for f in [audio_file.name, timing_file.name]:
                    if os.path.exists(f):
                        os.unlink(f)

    return False

def main():
    """Run all tests"""
    print("=== Phoneme Timing Test Suite ===\n")

    # Run tests
    test_duration_export()
    test_timing_extraction()
    test_tsv_format()

    print("\n=== Tests completed ===")

if __name__ == "__main__":
    main()
