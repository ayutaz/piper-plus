#!/usr/bin/env python3
"""Test Japanese TTS on Windows with OpenJTalk support."""

import subprocess
import sys
import os
import tempfile
import wave

def test_japanese_tts():
    """Test Japanese text-to-speech generation."""
    
    # Test texts
    test_texts = [
        "こんにちは、世界。",
        "今日は良い天気ですね。",
        "日本語の音声合成をテストしています。"
    ]
    
    # Find piper executable
    piper_exe = None
    possible_paths = [
        "piper.exe",
        "./piper.exe", 
        "../piper.exe",
        "./build/Release/piper.exe",
        "./build/piper.exe"
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            piper_exe = path
            break
    
    if not piper_exe:
        print("Error: Could not find piper.exe")
        return False
    
    print(f"Found piper.exe at: {piper_exe}")
    
    # Check if Japanese model exists
    model_path = "test/models/ja_JP-test-medium.onnx"
    if not os.path.exists(model_path):
        print(f"Error: Japanese model not found at {model_path}")
        return False
    
    success = True
    
    for i, text in enumerate(test_texts):
        print(f"\nTest {i+1}: {text}")
        
        # Create temporary output file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            output_path = tmp_file.name
        
        try:
            # Run piper
            cmd = [piper_exe, "--model", model_path, "--output_file", output_path]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(input=text)
            
            if process.returncode != 0:
                print(f"  Failed with return code: {process.returncode}")
                print(f"  stderr: {stderr}")
                success = False
                continue
            
            # Check if output file exists and has content
            if not os.path.exists(output_path):
                print("  Error: No output file generated")
                success = False
                continue
            
            file_size = os.path.getsize(output_path)
            if file_size < 1000:
                print(f"  Error: Output file too small ({file_size} bytes)")
                success = False
                continue
            
            # Try to read WAV file to verify format
            try:
                with wave.open(output_path, 'rb') as wav_file:
                    frames = wav_file.getnframes()
                    rate = wav_file.getframerate()
                    duration = frames / float(rate)
                    print(f"  Success: Generated {duration:.2f} seconds of audio")
            except Exception as e:
                print(f"  Error reading WAV file: {e}")
                success = False
            
        finally:
            # Clean up
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    return success

if __name__ == "__main__":
    print("Testing Japanese TTS on Windows...")
    print("=" * 50)
    
    if test_japanese_tts():
        print("\nAll tests passed!")
        sys.exit(0)
    else:
        print("\nSome tests failed!")
        sys.exit(1)