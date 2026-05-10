#!/usr/bin/env python3
"""Benchmark suite for piper-g2p.

Usage:
    uv run python benchmarks/bench_g2p.py

Measures per-language phonemization latency, throughput, and memory.
"""

import statistics
import sys
import time

TEXTS = {
    "short": {
        "en": "Hello world",
        "es": "Hola mundo",
        "fr": "Bonjour le monde",
        "pt": "Olá mundo",
        "sv": "Hej världen",
    },
    "medium": {
        "en": "The quick brown fox jumps over the lazy dog. " * 3,
        "es": "El rápido zorro marrón salta sobre el perro perezoso. " * 3,
        "fr": "Le renard brun rapide saute par-dessus le chien paresseux. " * 3,
        "pt": "A rápida raposa marrom pula sobre o cachorro preguiçoso. " * 3,
        "sv": "Den snabba bruna räven hoppar över den lata hunden. " * 3,
    },
    "long": {
        "en": "The quick brown fox " * 50,
        "es": "El rápido zorro marrón " * 50,
        "fr": "Le renard brun rapide " * 50,
        "pt": "A rápida raposa marrom " * 50,
        "sv": "Den snabba bruna räven " * 50,
    },
}


def benchmark_phonemize():
    """Measure phonemization latency and throughput."""
    from piper_plus_g2p import available_languages, get_phonemizer

    langs = sorted(available_languages())
    print(f"Available languages: {', '.join(langs)}\n")

    for size_name in ["short", "medium", "long"]:
        texts = TEXTS[size_name]
        print(f"--- {size_name.upper()} ---")

        for lang in langs:
            if lang not in texts:
                continue

            text = texts[lang]
            p = get_phonemizer(lang)

            # Warmup
            for _ in range(10):
                p.phonemize(text)

            iters = {"short": 1000, "medium": 100, "long": 10}[size_name]
            times = []
            for _ in range(iters):
                t0 = time.perf_counter()
                p.phonemize(text)
                times.append(time.perf_counter() - t0)

            med_ms = statistics.median(times) * 1000
            cps = len(text) / statistics.median(times)
            print(
                f"  {lang}: {med_ms:.2f} ms/call,"
                f" {cps:.0f} chars/sec ({len(text)} chars)"
            )

        print()


def benchmark_memory():
    """Measure peak memory usage."""
    try:
        import resource
    except ImportError:
        print("(memory benchmark skipped: resource module unavailable)\n")
        return

    from piper_plus_g2p import available_languages, get_phonemizer

    baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for lang in available_languages():
        get_phonemizer(lang)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    scale = (1024 * 1024) if sys.platform == "darwin" else 1024
    print(
        f"Memory: baseline={baseline / scale:.1f} MB, peak={peak / scale:.1f} MB, "
        f"G2P overhead={(peak - baseline) / scale:.1f} MB\n"
    )


def main():
    print("piper-g2p Benchmark Suite")
    print("=" * 40 + "\n")
    benchmark_memory()
    benchmark_phonemize()
    print("Done.")


if __name__ == "__main__":
    main()
