#!/usr/bin/env python3
"""Compare streaming vs non-streaming performance."""

import json
import statistics
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


def measure_streaming_latency(piper_path: str, model_path: str, text: str):
    """Measure time to first audio chunk in streaming mode."""
    cmd = [piper_path, "--model", model_path, "--output-raw", "--streaming"]

    start_time = time.perf_counter()
    first_chunk_time = None
    total_bytes = 0

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )

    def read_output():
        nonlocal first_chunk_time, total_bytes

        while True:
            # Read in small chunks
            chunk = proc.stdout.read(1024)
            if not chunk:
                break

            if first_chunk_time is None:
                first_chunk_time = time.perf_counter()

            total_bytes += len(chunk)

    # Start reader thread
    reader_thread = threading.Thread(target=read_output)
    reader_thread.start()

    # Send text
    proc.stdin.write(text.encode())
    proc.stdin.close()

    # Wait for completion
    reader_thread.join()
    proc.wait()

    end_time = time.perf_counter()

    if first_chunk_time:
        latency = first_chunk_time - start_time
        total_time = end_time - start_time
        return latency, total_time, total_bytes
    else:
        return None, None, 0


def measure_regular_latency(piper_path: str, model_path: str, text: str):
    """Measure time to first audio byte in regular mode."""
    cmd = [piper_path, "--model", model_path, "--output-raw"]

    start_time = time.perf_counter()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )

    # Send text
    proc.stdin.write(text.encode())
    proc.stdin.close()

    # Wait for first byte
    first_byte = proc.stdout.read(1)
    first_byte_time = time.perf_counter()

    # Read rest
    rest = proc.stdout.read()
    end_time = time.perf_counter()

    proc.wait()

    latency = first_byte_time - start_time
    total_time = end_time - start_time
    total_bytes = len(first_byte) + len(rest)

    return latency, total_time, total_bytes


def main():
    piper_path = get_piper_path()

    # Test cases
    test_cases = [
        ("Short text", "Hello world."),
        ("Medium text", "The quick brown fox jumps over the lazy dog."),
        (
            "Long text",
            "In recent years, text-to-speech technology has advanced significantly, enabling more natural and expressive synthetic voices that can be used in various applications.",
        ),
    ]

    # Models to test
    models = [
        ("Text phonemes", "test/models/text_voice.onnx"),
        # ("Japanese", "test/models/multilingual-test-medium.onnx"),  # Skip if espeak issues
    ]

    results = []

    for model_name, model_path in models:
        model_full_path = Path(__file__).parent.parent / model_path
        if not model_full_path.exists():
            print(f"Skipping {model_name} (model not found)")
            continue

        print(f"\n{'=' * 60}")
        print(f"Model: {model_name}")
        print(f"{'=' * 60}")

        for text_name, text in test_cases:
            print(f"\n{text_name}: '{text[:50]}...'")

            # Regular mode (3 runs)
            regular_latencies = []
            for _ in range(3):
                latency, total_time, bytes_count = measure_regular_latency(
                    piper_path, str(model_full_path), text
                )
                if latency:
                    regular_latencies.append(latency * 1000)  # Convert to ms

            # Streaming mode (3 runs)
            streaming_latencies = []
            for _ in range(3):
                latency, total_time, bytes_count = measure_streaming_latency(
                    piper_path, str(model_full_path), text
                )
                if latency:
                    streaming_latencies.append(latency * 1000)  # Convert to ms

            if regular_latencies and streaming_latencies:
                reg_avg = statistics.mean(regular_latencies)
                reg_std = (
                    statistics.stdev(regular_latencies)
                    if len(regular_latencies) > 1
                    else 0
                )
                stream_avg = statistics.mean(streaming_latencies)
                stream_std = (
                    statistics.stdev(streaming_latencies)
                    if len(streaming_latencies) > 1
                    else 0
                )

                improvement = ((reg_avg - stream_avg) / reg_avg) * 100

                print(f"  Regular mode:   {reg_avg:.1f} ± {reg_std:.1f} ms")
                print(f"  Streaming mode: {stream_avg:.1f} ± {stream_std:.1f} ms")
                print(f"  Improvement:    {improvement:.1f}%")

                results.append(
                    {
                        "model": model_name,
                        "text": text_name,
                        "text_length": len(text),
                        "regular_latency_ms": reg_avg,
                        "streaming_latency_ms": stream_avg,
                        "improvement_percent": improvement,
                    }
                )

    # Summary
    if results:
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")

        avg_improvement = statistics.mean([r["improvement_percent"] for r in results])
        print(f"\nAverage latency improvement: {avg_improvement:.1f}%")

        # Save results
        with open("streaming_comparison_results.json", "w") as f:
            json.dump(
                {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "results": results},
                f,
                indent=2,
            )
        print("\nResults saved to: streaming_comparison_results.json")


if __name__ == "__main__":
    main()
