#!/usr/bin/env python3
"""Test script for streaming mode functionality."""

import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


def get_piper_path():
    """Find the piper executable."""
    build_dir = Path(__file__).parent.parent / "build"
    piper_path = build_dir / "piper"
    if not piper_path.exists():
        print(f"Error: piper executable not found at {piper_path}")
        sys.exit(1)
    return str(piper_path)


def test_streaming_latency(piper_path: str, model_path: str, text: str):
    """Test streaming mode latency by measuring time to first audio chunk."""
    cmd = [
        piper_path,
        "--model",
        model_path,
        "--output-raw",
        "--streaming",  # New streaming flag
    ]

    # Queue for capturing output chunks
    audio_queue = queue.Queue()
    first_chunk_time = None
    start_time = time.perf_counter()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,  # Unbuffered
    )

    # Thread to capture stderr
    stderr_output = []

    def read_stderr():
        for line in proc.stderr:
            stderr_output.append(line.decode())

    stderr_thread = threading.Thread(target=read_stderr)
    stderr_thread.start()

    def read_output():
        nonlocal first_chunk_time
        chunk_count = 0
        total_bytes = 0

        while True:
            # Read in small chunks (e.g., 1024 bytes = 512 samples)
            chunk = proc.stdout.read(1024)
            if not chunk:
                break

            if first_chunk_time is None:
                first_chunk_time = time.perf_counter()
                print(
                    f"First chunk received after: {(first_chunk_time - start_time) * 1000:.1f}ms"
                )

            chunk_count += 1
            total_bytes += len(chunk)
            audio_queue.put(chunk)

        print(f"Total chunks: {chunk_count}, Total bytes: {total_bytes}")

    # Start reader thread
    reader_thread = threading.Thread(target=read_output)
    reader_thread.start()

    # Send text
    proc.stdin.write(text.encode())
    proc.stdin.close()

    # Wait for completion
    reader_thread.join()
    stderr_thread.join()
    proc.wait()

    # Print stderr if no audio received
    if first_chunk_time is None and stderr_output:
        print("\nError output:")
        print("".join(stderr_output))

    end_time = time.perf_counter()
    total_time = end_time - start_time

    if first_chunk_time:
        latency = (first_chunk_time - start_time) * 1000
        print(f"Streaming latency: {latency:.1f}ms")
        print(f"Total time: {total_time * 1000:.1f}ms")
        return latency
    else:
        print("No audio received!")
        return None


def main():
    piper_path = get_piper_path()

    # Check if streaming mode is available
    help_output = subprocess.check_output(
        [piper_path, "--help"], stderr=subprocess.STDOUT, text=True
    )
    has_streaming = "--streaming" in help_output

    print(f"Piper executable: {piper_path}")
    print(f"Streaming mode available: {has_streaming}")

    if not has_streaming:
        print("\nStreaming mode not yet implemented in piper executable.")
        print("This test will be useful once the --streaming flag is added.")
        return

    # Test with different models and texts
    test_cases = [
        ("test/models/multilingual-test-medium.onnx", "Hello world."),
        ("test/models/multilingual-test-medium.onnx", "The quick brown fox jumps over the lazy dog."),
        ("test/models/multilingual-test-medium.onnx", "こんにちは世界。"),
        ("test/models/multilingual-test-medium.onnx", "今日はとてもいい天気ですね。"),
    ]

    for model_path, text in test_cases:
        model_full_path = Path(__file__).parent.parent / model_path
        if not model_full_path.exists():
            print(f"\nSkipping {model_path} (not found)")
            continue

        print(f"\n{'=' * 60}")
        print(f"Model: {model_path}")
        print(f"Text: {text}")
        print(f"{'=' * 60}")

        test_streaming_latency(piper_path, str(model_full_path), text)


if __name__ == "__main__":
    main()
