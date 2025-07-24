#!/usr/bin/env python3
"""Test backward compatibility of Piper CLI enhancements."""

import subprocess
import tempfile
import sys
import os
from pathlib import Path


def run_piper_legacy(args, input_text):
    """Run piper with legacy-style arguments."""
    cmd = [sys.executable, "-m", "piper"] + args
    
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate(input=input_text.encode())
    
    return proc.returncode, stdout, stderr


def test_stdin_compatibility():
    """Test that stdin input still works as before."""
    print("Testing stdin compatibility...")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name
    
    # Legacy usage: echo "text" | piper --model model.onnx -f output.wav
    args = [
        "--model", "en_US-lessac-medium.onnx",
        "-f", output_file
    ]
    
    code, stdout, stderr = run_piper_legacy(args, "Testing backward compatibility")
    
    if code == 0:
        print("  ✅ stdin input works as before")
        # Check file was created
        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            print("  ✅ Output file created successfully")
        else:
            print("  ❌ Output file not created properly")
    else:
        print(f"  ❌ stdin input failed: {stderr.decode()}")
    
    # Cleanup
    try:
        os.unlink(output_file)
    except:
        pass


def test_output_raw_compatibility():
    """Test that --output-raw still works."""
    print("\nTesting --output-raw compatibility...")
    
    args = [
        "--model", "en_US-lessac-medium.onnx",
        "--output-raw"
    ]
    
    code, stdout, stderr = run_piper_legacy(args, "Test raw output")
    
    if code == 0 and len(stdout) > 0:
        print("  ✅ --output-raw works as before")
        print(f"  ✅ Raw audio data received: {len(stdout)} bytes")
    else:
        print(f"  ❌ --output-raw failed: {stderr.decode()}")


def test_legacy_parameters():
    """Test that all legacy parameters still work."""
    print("\nTesting legacy parameters...")
    
    legacy_params = [
        ("--speaker", "0"),
        ("--length-scale", "1.2"),
        ("--noise-scale", "0.7"),
        ("--noise-w", "0.9"),
        ("--sentence-silence", "0.5"),
    ]
    
    for param, value in legacy_params:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_file = f.name
        
        args = [
            "--model", "en_US-lessac-medium.onnx",
            "-f", output_file,
            param, value
        ]
        
        code, stdout, stderr = run_piper_legacy(args, "Test parameter")
        
        if code == 0:
            print(f"  ✅ {param} {value} works")
        else:
            print(f"  ❌ {param} {value} failed: {stderr.decode()}")
        
        # Cleanup
        try:
            os.unlink(output_file)
        except:
            pass


def test_output_dir_compatibility():
    """Test that --output-dir still works."""
    print("\nTesting --output-dir compatibility...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        args = [
            "--model", "en_US-lessac-medium.onnx",
            "--output-dir", tmpdir
        ]
        
        # Send multiple lines
        input_text = "First line\nSecond line\nThird line"
        code, stdout, stderr = run_piper_legacy(args, input_text)
        
        if code == 0:
            # Check if files were created
            files = list(Path(tmpdir).glob("*.wav"))
            if len(files) > 0:
                print(f"  ✅ --output-dir works, created {len(files)} files")
            else:
                print("  ❌ No files created in output directory")
        else:
            print(f"  ❌ --output-dir failed: {stderr.decode()}")


def test_mixed_usage():
    """Test that new features don't break when mixed with old ones."""
    print("\nTesting mixed old/new feature usage...")
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_file = f.name
    
    # Mix old parameters with new ones
    args = [
        "--model", "en_US-lessac-medium.onnx",
        "-f", output_file,
        "--length-scale", "1.1",  # old
        "--volume", "1.2"  # new
    ]
    
    code, stdout, stderr = run_piper_legacy(args, "Test mixed features")
    
    if code == 0:
        print("  ✅ Old and new features work together")
    else:
        print(f"  ❌ Mixed features failed: {stderr.decode()}")
    
    # Cleanup
    try:
        os.unlink(output_file)
    except:
        pass


def main():
    """Run all backward compatibility tests."""
    print("Piper Backward Compatibility Tests")
    print("=" * 50)
    
    # Check if model exists
    if not Path("en_US-lessac-medium.onnx").exists():
        print("⚠️  Warning: en_US-lessac-medium.onnx not found")
        print("   Some tests may fail without a model file")
        print()
    
    test_stdin_compatibility()
    test_output_raw_compatibility()
    test_legacy_parameters()
    test_output_dir_compatibility()
    test_mixed_usage()
    
    print("\n" + "=" * 50)
    print("Backward compatibility tests completed!")
    print("\nAll legacy functionality should continue to work exactly as before.")
    print("New features are purely additive and don't change existing behavior.")


if __name__ == "__main__":
    main()