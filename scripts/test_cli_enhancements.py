#!/usr/bin/env python3
"""Test script for Piper CLI enhancements."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run_piper(args, input_text=None):
    """Run piper with given arguments."""
    cmd = [sys.executable, "-m", "piper"] + args

    if input_text:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=input_text)
    else:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        stdout, stderr = proc.stdout, proc.stderr

    return proc.returncode, stdout, stderr


def test_volume_adjustment():
    """Test volume adjustment feature."""
    print("Testing volume adjustment...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name

    # Test different volume levels
    for volume in [0.5, 1.0, 1.5]:
        print(f"  Testing volume={volume}")
        args = [
            "--model",
            "en_US-lessac-medium.onnx",
            "-f",
            output_file,
            "--volume",
            str(volume),
        ]

        code, _, stderr = run_piper(args, "Testing volume")
        if code != 0:
            print(f"    ❌ Failed: {stderr}")
        else:
            print("    ✅ Success")

    # Cleanup
    try:
        os.unlink(output_file)
    except Exception:
        pass


def test_direct_text_input():
    """Test direct text input feature."""
    print("\nTesting direct text input...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name

    args = [
        "Hello from direct input",
        "--model",
        "en_US-lessac-medium.onnx",
        "-f",
        output_file,
    ]

    code, _, stderr = run_piper(args)
    if code != 0:
        print(f"  ❌ Failed: {stderr}")
    else:
        print("  ✅ Success")

    # Cleanup
    try:
        os.unlink(output_file)
    except Exception:
        pass


def test_file_input():
    """Test file input feature."""
    print("\nTesting file input...")

    # Create test files
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        test_file1 = f.name
        f.write("First line from file.\n")
        f.write("Second line from file.\n")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        test_file2 = f.name
        f.write("Content from second file.\n")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name

    # Test single file
    print("  Testing single file input")
    args = [
        "--model",
        "en_US-lessac-medium.onnx",
        "--input-file",
        test_file1,
        "-f",
        output_file,
    ]

    code, _, stderr = run_piper(args)
    if code != 0:
        print(f"    ❌ Failed: {stderr}")
    else:
        print("    ✅ Success")

    # Test multiple files
    print("  Testing multiple file input")
    args = [
        "--model",
        "en_US-lessac-medium.onnx",
        "--input-file",
        test_file1,
        "--input-file",
        test_file2,
        "-f",
        output_file,
    ]

    code, _, stderr = run_piper(args)
    if code != 0:
        print(f"    ❌ Failed: {stderr}")
    else:
        print("    ✅ Success")

    # Cleanup
    for f in [test_file1, test_file2, output_file]:
        try:
            os.unlink(f)
        except Exception:
            pass


def test_inference_config():
    """Test InferenceConfig integration."""
    print("\nTesting InferenceConfig...")

    # This tests that the config is properly created and used
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name

    args = [
        "Testing config",
        "--model",
        "en_US-lessac-medium.onnx",
        "-f",
        output_file,
        "--volume",
        "1.2",
        "--length-scale",
        "1.1",
        "--noise-scale",
        "0.7",
    ]

    code, _, stderr = run_piper(args)
    if code != 0:
        print(f"  ❌ Failed: {stderr}")
    else:
        print("  ✅ Success - InferenceConfig properly integrated")

    # Cleanup
    try:
        os.unlink(output_file)
    except Exception:
        pass


def main():
    """Run all tests."""
    print("Piper CLI Enhancement Tests")
    print("=" * 40)

    # Check if model exists
    if not Path("en_US-lessac-medium.onnx").exists():
        print("⚠️  Warning: en_US-lessac-medium.onnx not found")
        print("   Tests will fail without a model file")
        print("   Download a model first or update the test to use an existing model")
        print()

    test_volume_adjustment()
    test_direct_text_input()
    test_file_input()
    test_inference_config()

    print("\n" + "=" * 40)
    print("Tests completed!")
    print("\nNote: Auto-play feature should be tested manually")
    print("Example: piper 'Hello world' --model your_model.onnx --auto-play")


if __name__ == "__main__":
    main()
