#!/usr/bin/env python3
"""Benchmark script for measuring streaming performance and latency."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
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


def measure_first_byte_latency(
    piper_path: str, model_path: str, text: str, use_raw: bool = False
) -> float:
    """Measure time until first audio byte is output."""
    cmd = [
        piper_path,
        "--model",
        model_path,
    ]

    if use_raw:
        cmd.extend(["--output-raw"])
    else:
        cmd.extend(["--output_file", "-"])

    start_time = time.perf_counter()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True if not use_raw else None,
    )

    # Send text
    if use_raw:
        proc.stdin.write(text.encode())
    else:
        proc.stdin.write(text)
    proc.stdin.close()

    # Wait for first byte
    proc.stdout.read(1)
    first_byte_time = time.perf_counter()

    # Let process complete
    proc.stdout.read()
    proc.wait()

    latency = first_byte_time - start_time
    return latency


def measure_total_synthesis_time(
    piper_path: str, model_path: str, text: str
) -> tuple[float, float]:
    """Measure total synthesis time and extract real-time factor."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        output_path = tmp_file.name

    try:
        cmd = [
            piper_path,
            "--model",
            model_path,
            "--output_file",
            output_path,
            "--debug",
        ]

        start_time = time.perf_counter()

        result = subprocess.run(cmd, check=False, input=text, text=True, capture_output=True)

        end_time = time.perf_counter()
        total_time = end_time - start_time

        # Extract real-time factor from debug output
        rtf = None
        for line in result.stderr.split("\n"):
            if "Real-time factor:" in line:
                try:
                    rtf = float(line.split("Real-time factor:")[-1].strip().rstrip("x"))
                except Exception:
                    pass

        return total_time, rtf

    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def benchmark_texts(piper_path: str, model_path: str, texts: list[str]) -> dict:
    """Run benchmarks on a list of texts."""
    results = []

    for i, text in enumerate(texts):
        print(f"\nBenchmarking text {i + 1}/{len(texts)}: '{text[:50]}...'")

        # Measure first byte latency (raw mode)
        raw_latencies = []
        for _ in range(3):  # Average of 3 runs
            latency = measure_first_byte_latency(
                piper_path, model_path, text, use_raw=True
            )
            raw_latencies.append(latency)

        # Measure first byte latency (WAV mode)
        wav_latencies = []
        for _ in range(3):
            latency = measure_first_byte_latency(
                piper_path, model_path, text, use_raw=False
            )
            wav_latencies.append(latency)

        # Measure total synthesis time
        total_time, rtf = measure_total_synthesis_time(piper_path, model_path, text)

        result = {
            "text": text,
            "text_length": len(text),
            "raw_latency_avg": statistics.mean(raw_latencies),
            "raw_latency_std": statistics.stdev(raw_latencies)
            if len(raw_latencies) > 1
            else 0,
            "wav_latency_avg": statistics.mean(wav_latencies),
            "wav_latency_std": statistics.stdev(wav_latencies)
            if len(wav_latencies) > 1
            else 0,
            "total_synthesis_time": total_time,
            "real_time_factor": rtf,
        }

        results.append(result)

        print(
            f"  Raw mode latency: {result['raw_latency_avg'] * 1000:.1f} ± {result['raw_latency_std'] * 1000:.1f} ms"
        )
        print(
            f"  WAV mode latency: {result['wav_latency_avg'] * 1000:.1f} ± {result['wav_latency_std'] * 1000:.1f} ms"
        )
        print(f"  Total synthesis: {result['total_synthesis_time'] * 1000:.1f} ms")
        if rtf:
            print(f"  Real-time factor: {rtf:.2f}x")

    return {
        "model": model_path,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Piper streaming performance"
    )
    parser.add_argument("--model", required=True, help="Path to ONNX model")
    parser.add_argument("--output", help="Output JSON file for results")
    parser.add_argument(
        "--japanese", action="store_true", help="Include Japanese test texts"
    )
    args = parser.parse_args()

    piper_path = get_piper_path()

    # Test texts of varying lengths
    test_texts = [
        # Short
        "Hello world.",
        "This is a test.",
        # Medium
        "The quick brown fox jumps over the lazy dog.",
        "Artificial intelligence is transforming the world in unprecedented ways.",
        # Long
        "In recent years, text-to-speech technology has advanced significantly, enabling more natural and expressive synthetic voices that can be used in various applications.",
        "The development of neural network-based speech synthesis has revolutionized how we interact with computers, making it possible to create voices that are nearly indistinguishable from human speech.",
    ]

    if args.japanese:
        test_texts.extend(
            [
                # Japanese texts
                "こんにちは。",
                "今日はとてもいい天気ですね。",
                "人工知能技術の発展により、音声合成の品質が大幅に向上しました。",
                "日本語の音声合成においては、アクセントやイントネーションの正確な再現が重要な課題となっています。",
            ]
        )

    print(f"Piper executable: {piper_path}")
    print(f"Model: {args.model}")
    print(f"Running benchmarks on {len(test_texts)} texts...")

    results = benchmark_texts(piper_path, args.model, test_texts)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_raw_latencies = [r["raw_latency_avg"] for r in results["results"]]
    all_wav_latencies = [r["wav_latency_avg"] for r in results["results"]]

    print("\nAverage first-byte latency:")
    print(f"  Raw mode: {statistics.mean(all_raw_latencies) * 1000:.1f} ms")
    print(f"  WAV mode: {statistics.mean(all_wav_latencies) * 1000:.1f} ms")

    print("\nLatency range:")
    print(
        f"  Raw mode: {min(all_raw_latencies) * 1000:.1f} - {max(all_raw_latencies) * 1000:.1f} ms"
    )
    print(
        f"  WAV mode: {min(all_wav_latencies) * 1000:.1f} - {max(all_wav_latencies) * 1000:.1f} ms"
    )

    # Correlation with text length
    text_lengths = [r["text_length"] for r in results["results"]]
    print(f"\nText length range: {min(text_lengths)} - {max(text_lengths)} characters")

    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
