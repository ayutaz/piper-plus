#!/usr/bin/env python3
"""Benchmark script for piper-plus ONNX TTS inference performance.

Measures RTF (Real-Time Factor), model size, peak memory, cold/warm latency,
language count, and parameter count for one or more ONNX models.

Usage:
    # Single model (JSON output to stdout)
    uv run python scripts/benchmark.py --model model.onnx --config config.json

    # Markdown output
    uv run python scripts/benchmark.py --model model.onnx --config config.json --format markdown

    # Compare multiple models
    uv run python scripts/benchmark.py \\
        --models m1.onnx m2.onnx \\
        --configs c1.json c2.json \\
        --labels "piper-plus" "piper-original" \\
        --format markdown

    # Custom text / language
    uv run python scripts/benchmark.py --model model.onnx --config config.json \\
        --language en --text "Hello, world!"
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050

TEST_SENTENCES = {
    "ja": "\u3053\u3093\u306b\u3061\u306f\u3001\u4eca\u65e5\u306f\u826f\u3044\u5929\u6c17\u3067\u3059\u306d\u3002",
    "en": "Hello, how are you doing today?",
    "zh": "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u5f88\u597d\u3002",
    "es": "Hola, \u00bfc\u00f3mo est\u00e1s hoy?",
    "fr": "Bonjour, comment allez-vous?",
    "pt": "Ol\u00e1, como voc\u00ea est\u00e1 hoje?",
}

# Dummy phoneme IDs: BOS(1) + 20 dummy phonemes(8) + EOS(2)
DUMMY_PHONEME_IDS = [1] + [8] * 20 + [2]

# Default inference scales: [noise_scale, length_scale, noise_w]
DEFAULT_SCALES = [0.667, 1.0, 0.8]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_model_size_mb(model_path: str) -> float:
    """Return ONNX file size in MB."""
    return os.path.getsize(model_path) / (1024 * 1024)


def _count_parameters_millions(model_path: str) -> float | None:
    """Count total parameters (millions) by summing ONNX initializer elements.

    Returns None if the ``onnx`` package is not installed.
    """
    try:
        import onnx  # noqa: PLC0415
    except ImportError:
        return None

    model = onnx.load(model_path, load_external_data=False)
    total = 0
    for init in model.graph.initializer:
        count = 1
        for d in init.dims:
            count *= d
        total += count
    return total / 1e6


def _load_config(config_path: str) -> dict:
    """Load and return the model config.json."""
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _get_language_count(config: dict) -> int:
    """Return number of languages from config."""
    lid_map = config.get("language_id_map")
    if lid_map:
        return len(lid_map)
    # Infer from language field
    lang = config.get("language", "")
    if "-" in lang:
        return len(lang.split("-"))
    return 1 if lang else 0


def _get_peak_memory_mb() -> float:
    """Return peak RSS in MB for the current process.

    Uses ``resource`` on Unix. On macOS ``ru_maxrss`` is in bytes; on Linux
    it is in KB.  Falls back to ``psutil`` on Windows / when resource is
    unavailable.
    """
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss = usage.ru_maxrss
        if sys.platform == "darwin":
            return max_rss / (1024 * 1024)  # bytes -> MB
        else:
            return max_rss / 1024  # KB -> MB
    except Exception:
        pass

    # Fallback: psutil
    try:
        import psutil  # noqa: PLC0415

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        return -1.0


def _get_system_info() -> dict:
    """Collect system information."""
    info: dict[str, str] = {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "python": platform.python_version(),
        "onnxruntime": ort.__version__,
    }
    return info


def _build_inputs(
    session: ort.InferenceSession,
    phoneme_ids: list[int],
    speaker_id: int = 0,
    language_id: int = 0,
) -> dict[str, np.ndarray]:
    """Build the feed dict for an ONNX inference session."""
    input_names = {inp.name for inp in session.get_inputs()}

    ids = np.array([phoneme_ids], dtype=np.int64)
    lengths = np.array([len(phoneme_ids)], dtype=np.int64)
    scales = np.array(DEFAULT_SCALES, dtype=np.float32)

    feeds: dict[str, np.ndarray] = {
        "input": ids,
        "input_lengths": lengths,
        "scales": scales,
    }

    if "sid" in input_names:
        feeds["sid"] = np.array([speaker_id], dtype=np.int64)

    if "lid" in input_names:
        feeds["lid"] = np.array([language_id], dtype=np.int64)

    if "prosody_features" in input_names:
        # ONNX export stores prosody_features as int64 (A1/A2/A3 raw values).
        seq_len = len(phoneme_ids)
        feeds["prosody_features"] = np.zeros((1, seq_len, 3), dtype=np.int64)

    # Optional Voice Cloning inputs introduced for MB-iSTFT-VITS2 ONNX models.
    # Pass zero vectors with mask=0 so they remain disabled during the benchmark.
    if "speaker_embedding" in input_names:
        emb_dim = 256
        for inp in session.get_inputs():
            if inp.name == "speaker_embedding" and isinstance(inp.shape[1], int):
                emb_dim = inp.shape[1]
                break
        feeds["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
    if "speaker_embedding_mask" in input_names:
        feeds["speaker_embedding_mask"] = np.zeros((1, 1), dtype=np.int64)

    return feeds


def _run_inference(
    session: ort.InferenceSession,
    feeds: dict[str, np.ndarray],
) -> np.ndarray:
    """Run inference and return audio samples."""
    results = session.run(None, feeds)
    # Output shape is typically [1, 1, num_samples]
    audio = results[0].squeeze()
    return audio


# ---------------------------------------------------------------------------
# Core benchmark
# ---------------------------------------------------------------------------


def benchmark_model(
    model_path: str,
    config_path: str,
    *,
    language: str = "ja",
    text: str | None = None,
    n_warmup: int = 2,
    n_runs: int = 10,
    speaker_id: int = 0,
    threads: int | None = None,
) -> dict:
    """Benchmark a single ONNX model and return a metrics dict."""

    model_path = str(Path(model_path).resolve())
    config_path = str(Path(config_path).resolve())

    if not os.path.isfile(model_path):
        print(f"Error: model not found: {model_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(config_path):
        print(f"Error: config not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    config = _load_config(config_path)

    # Resolve language_id
    lid_map = config.get("language_id_map")
    language_id = 0
    if lid_map and language in lid_map:
        language_id = lid_map[language]

    # Model size & parameters
    model_size_mb = _get_model_size_mb(model_path)
    params_m = _count_parameters_millions(model_path)

    # Language count
    lang_count = _get_language_count(config)

    # Phoneme IDs — use dummy array (avoids heavy G2P dependencies)
    phoneme_ids = DUMMY_PHONEME_IDS

    # ---- Cold start: session creation + first inference ----
    cold_start = time.perf_counter()
    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    sess_opts.inter_op_num_threads = 1
    sess_opts.intra_op_num_threads = (
        threads if threads is not None else min(os.cpu_count() or 4, 4)
    )
    sess_opts.enable_cpu_mem_arena = True
    sess_opts.enable_mem_pattern = True

    session = ort.InferenceSession(
        model_path, sess_opts, providers=["CPUExecutionProvider"]
    )
    feeds = _build_inputs(
        session, phoneme_ids, speaker_id=speaker_id, language_id=language_id
    )
    _run_inference(session, feeds)
    cold_start_ms = (time.perf_counter() - cold_start) * 1000.0

    # ---- Warmup ----
    for _ in range(n_warmup):
        _run_inference(session, feeds)

    # ---- Timed runs ----
    latencies: list[float] = []
    audio_samples_count = 0

    for _ in range(n_runs):
        t0 = time.perf_counter()
        audio = _run_inference(session, feeds)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)
        audio_samples_count = len(audio)

    audio_duration_s = audio_samples_count / SAMPLE_RATE
    avg_inference_s = statistics.mean(latencies) / 1000.0
    rtf = avg_inference_s / audio_duration_s if audio_duration_s > 0 else float("inf")

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted) // 2]
    p95_idx = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)
    p95 = latencies_sorted[p95_idx]

    peak_mem_mb = _get_peak_memory_mb()

    result: dict = {
        "model": os.path.basename(model_path),
        "model_size_mb": round(model_size_mb, 1),
        "languages": lang_count,
        "rtf": round(rtf, 4),
        "cold_start_ms": round(cold_start_ms, 1),
        "latency_p50_ms": round(p50, 1),
        "latency_p95_ms": round(p95, 1),
        "peak_memory_mb": round(peak_mem_mb, 1),
        "sample_rate": SAMPLE_RATE,
        "audio_duration_s": round(audio_duration_s, 3),
        "test_language": language,
        "test_text": text or TEST_SENTENCES.get(language, ""),
        "phoneme_ids_length": len(phoneme_ids),
        "n_warmup": n_warmup,
        "n_runs": n_runs,
        "system": _get_system_info(),
    }

    if params_m is not None:
        result["parameters_m"] = round(params_m, 1)

    return result


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_METRIC_LABELS = [
    ("model", "Model"),
    ("model_size_mb", "Model Size"),
    ("parameters_m", "Parameters"),
    ("languages", "Languages"),
    ("rtf", "RTF"),
    ("cold_start_ms", "Cold Start"),
    ("latency_p50_ms", "Latency P50"),
    ("latency_p95_ms", "Latency P95"),
    ("peak_memory_mb", "Peak Memory"),
    ("audio_duration_s", "Audio Duration"),
    ("sample_rate", "Sample Rate"),
]

_METRIC_UNITS = {
    "model_size_mb": "MB",
    "parameters_m": "M",
    "cold_start_ms": "ms",
    "latency_p50_ms": "ms",
    "latency_p95_ms": "ms",
    "peak_memory_mb": "MB",
    "audio_duration_s": "s",
    "sample_rate": "Hz",
}


def _format_value(key: str, value) -> str:
    """Format a single metric value with its unit."""
    if value is None:
        return "N/A"
    unit = _METRIC_UNITS.get(key, "")
    if isinstance(value, float):
        formatted = f"{value:,.1f}" if abs(value) >= 10 else f"{value}"
    else:
        formatted = str(value)
    if unit:
        return f"{formatted} {unit}"
    return formatted


def format_json(results: list[dict]) -> str:
    """Format results as JSON."""
    if len(results) == 1:
        return json.dumps(results[0], indent=2, ensure_ascii=False)
    return json.dumps(results, indent=2, ensure_ascii=False)


def format_markdown_single(result: dict) -> str:
    """Format a single result as a Markdown table."""
    lines = ["| Metric | Value |", "|--------|-------|"]
    for key, label in _METRIC_LABELS:
        if key in result:
            lines.append(f"| {label} | {_format_value(key, result[key])} |")
    return "\n".join(lines)


def format_markdown_comparison(results: list[dict], labels: list[str]) -> str:
    """Format multiple results as a Markdown comparison table."""
    header = "| Metric | " + " | ".join(labels) + " |"
    sep = "|--------" + "|-------" * len(labels) + "|"
    lines = [header, sep]
    for key, label in _METRIC_LABELS:
        values = []
        for r in results:
            values.append(_format_value(key, r.get(key)))
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def format_markdown(results: list[dict], labels: list[str] | None = None) -> str:
    """Format results as Markdown."""
    if len(results) == 1:
        return format_markdown_single(results[0])
    effective_labels = labels or [
        r.get("model", f"Model {i + 1}") for i, r in enumerate(results)
    ]
    return format_markdown_comparison(results, effective_labels)


def format_csv(results: list[dict]) -> str:
    """Format results as CSV."""
    keys = [k for k, _ in _METRIC_LABELS if any(k in r for r in results)]
    lines = [",".join(keys)]
    for r in results:
        row = []
        for k in keys:
            v = r.get(k)
            row.append(str(v) if v is not None else "")
        lines.append(",".join(row))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark piper-plus ONNX TTS inference performance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Single model
    parser.add_argument("--model", type=str, help="Path to a single ONNX model")
    parser.add_argument("--config", type=str, help="Path to config.json for --model")

    # Multi-model comparison
    parser.add_argument(
        "--models", nargs="+", type=str, help="Paths to ONNX models (comparison mode)"
    )
    parser.add_argument(
        "--configs",
        nargs="+",
        type=str,
        help="Paths to config.json files (comparison mode)",
    )
    parser.add_argument(
        "--labels", nargs="+", type=str, help="Labels for each model in comparison mode"
    )

    # Benchmark parameters
    parser.add_argument(
        "--n-warmup", type=int, default=2, help="Warmup iterations (default: 2)"
    )
    parser.add_argument(
        "--n-runs", type=int, default=10, help="Measurement iterations (default: 10)"
    )
    parser.add_argument(
        "--language", type=str, default="ja", help="Test language (default: ja)"
    )
    parser.add_argument(
        "--text", type=str, help="Custom test text (overrides default for language)"
    )
    parser.add_argument(
        "--speaker-id", type=int, default=0, help="Speaker ID (default: 0)"
    )
    parser.add_argument(
        "--threads", type=int, default=None, help="ORT intra_op threads (default: auto)"
    )

    # Output
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "markdown", "csv"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument("--output", type=str, help="Output file path (default: stdout)")

    args = parser.parse_args(argv)

    # Validate: must specify either --model or --models
    if args.model and args.models:
        parser.error("Use either --model or --models, not both.")
    if not args.model and not args.models:
        parser.error("Specify --model (single) or --models (comparison).")

    if args.model and not args.config:
        parser.error("--config is required when using --model.")
    if args.models:
        if not args.configs:
            parser.error("--configs is required when using --models.")
        if len(args.models) != len(args.configs):
            parser.error("--models and --configs must have the same number of entries.")
        if args.labels and len(args.labels) != len(args.models):
            parser.error("--labels must have the same number of entries as --models.")

    return args


def main(argv: list[str] | None = None) -> None:
    """Entry point."""
    args = parse_args(argv)

    # Collect model/config pairs
    if args.model:
        pairs = [(args.model, args.config)]
        _labels = [os.path.basename(args.model)]
    else:
        pairs = list(zip(args.models, args.configs, strict=False))
        _labels = args.labels or [os.path.basename(m) for m in args.models]

    results: list[dict] = []
    for model_path, config_path in pairs:
        print(f"Benchmarking: {model_path} ...", file=sys.stderr)
        result = benchmark_model(
            model_path,
            config_path,
            language=args.language,
            text=args.text,
            n_warmup=args.n_warmup,
            n_runs=args.n_runs,
            speaker_id=args.speaker_id,
            threads=args.threads,
        )
        results.append(result)

    # Format output
    if args.format == "json":
        output = format_json(results)
    elif args.format == "markdown":
        output = format_markdown(results, labels=args.labels)
    elif args.format == "csv":
        output = format_csv(results)
    else:
        output = format_json(results)

    # Write output
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
