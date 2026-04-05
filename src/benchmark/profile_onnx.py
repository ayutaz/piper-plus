#!/usr/bin/env python3
"""Profile ONNX Runtime inference and report per-operator execution time.

Usage:
    python src/benchmark/profile_onnx.py -m test/models/multilingual-test-medium.onnx
    python src/benchmark/profile_onnx.py -m test/models/multilingual-test-medium.onnx --warmup 3 --runs 5
    python src/benchmark/profile_onnx.py --analyze profile_result.json

The script has two modes:

1. **Profile mode** (default): Runs inference with ONNX Runtime profiling enabled,
   saves the raw JSON profile, and prints an operator summary table.

2. **Analyze mode** (``--analyze``): Reads an existing ORT profile JSON
   (Chrome Trace Event format) and prints the summary table without re-running
   inference.

Output table columns:
    Operator        – ONNX operator type (Conv, MatMul, ...)
    Total Time (ms) – Cumulative kernel time across all nodes of this type
    Count           – Number of kernel invocations
    Avg (ms)        – Average per-invocation time
    % of Total      – Percentage of combined kernel time
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile analysis
# ---------------------------------------------------------------------------

_TABLE_HEADER = (
    f"{'Operator':<24} | {'Total Time (ms)':>16} | {'Count':>6} | "
    f"{'Avg (ms)':>10} | {'% of Total':>10}"
)
_TABLE_SEP = "-" * len(_TABLE_HEADER)


def _parse_kernel_events(profile_data: list[dict]) -> list[dict]:
    """Extract kernel-time events from ORT Chrome Trace Event JSON."""
    return [
        ev
        for ev in profile_data
        if ev.get("cat") == "Node" and ev.get("name", "").endswith("_kernel_time")
    ]


def _build_operator_stats(
    kernel_events: list[dict],
) -> dict[str, dict[str, float | int]]:
    """Aggregate kernel events by operator type.

    Returns a dict mapping operator name to
    ``{"total_us": float, "count": int}``.
    """
    stats: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"total_us": 0.0, "count": 0}
    )
    for ev in kernel_events:
        op_name = ev.get("args", {}).get("op_name", "Unknown")
        dur_us = ev.get("dur", 0)
        stats[op_name]["total_us"] += dur_us
        stats[op_name]["count"] += 1
    return dict(stats)


def print_operator_table(
    stats: dict[str, dict[str, float | int]],
    *,
    top_n: int = 0,
) -> None:
    """Print a formatted table of operator statistics.

    Args:
        stats: Operator name -> {"total_us", "count"}.
        top_n: If > 0, only show the top N operators by total time.
    """
    if not stats:
        print("No kernel events found in the profile data.")
        return

    grand_total_us = sum(s["total_us"] for s in stats.values())
    sorted_ops = sorted(stats.items(), key=lambda kv: kv[1]["total_us"], reverse=True)

    if top_n > 0:
        sorted_ops = sorted_ops[:top_n]

    print()
    print(_TABLE_SEP)
    print(_TABLE_HEADER)
    print(_TABLE_SEP)

    for op_name, s in sorted_ops:
        total_ms = s["total_us"] / 1000.0
        count = int(s["count"])
        avg_ms = total_ms / count if count > 0 else 0.0
        pct = (s["total_us"] / grand_total_us * 100.0) if grand_total_us > 0 else 0.0
        print(
            f"{op_name:<24} | {total_ms:>16.2f} | {count:>6} | "
            f"{avg_ms:>10.3f} | {pct:>9.1f}%"
        )

    print(_TABLE_SEP)
    print(
        f"{'TOTAL':<24} | {grand_total_us / 1000.0:>16.2f} | "
        f"{sum(int(s['count']) for s in stats.values()):>6} | "
        f"{'':>10} | {'100.0%':>10}"
    )
    print()


def print_session_summary(profile_data: list[dict]) -> None:
    """Print session-level timing (model loading, initialization)."""
    session_events = [ev for ev in profile_data if ev.get("cat") == "Session"]
    if not session_events:
        return
    print("Session timing:")
    for ev in session_events:
        dur_ms = ev.get("dur", 0) / 1000.0
        print(f"  {ev['name']}: {dur_ms:.2f} ms")
    print()


def analyze_profile(profile_path: str, *, top_n: int = 0) -> None:
    """Load a saved ORT profile JSON and print the summary."""
    with open(profile_path, encoding="utf-8") as f:
        profile_data = json.load(f)

    print(f"Profile: {profile_path}")
    print(f"Total events: {len(profile_data)}")

    print_session_summary(profile_data)

    kernel_events = _parse_kernel_events(profile_data)
    print(f"Kernel events: {len(kernel_events)}")

    stats = _build_operator_stats(kernel_events)
    print_operator_table(stats, top_n=top_n)


# ---------------------------------------------------------------------------
# Inference + profiling
# ---------------------------------------------------------------------------


def _load_config(config_path: str) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_config(model_path: str, config_arg: str | None) -> str:
    """Resolve config path: explicit arg > {model}.json > {model_dir}/config.json."""
    if config_arg:
        return config_arg
    p = Path(model_path)
    onnx_json = p.with_suffix(p.suffix + ".json")
    if onnx_json.exists():
        return str(onnx_json)
    dir_config = p.parent / "config.json"
    if dir_config.exists():
        return str(dir_config)
    print(
        f"Error: Cannot find config.json for {model_path}. Use --config.",
        file=sys.stderr,
    )
    sys.exit(1)


def _build_dummy_inputs(
    config: dict,
    *,
    input_names: list[str],
    num_phonemes: int = 40,
    speaker_id: int = 0,
    language_id: int = 0,
) -> dict[str, np.ndarray]:
    """Build plausible dummy inputs from config metadata."""
    # Build a phoneme sequence: BOS + alternating vowel/padding + EOS
    phoneme_id_map = config.get("phoneme_id_map", {})
    bos_id = phoneme_id_map.get("^", [1])[0]
    eos_id = phoneme_id_map.get("$", [2])[0]
    pad_id = phoneme_id_map.get("_", [0])[0]
    vowel_id = phoneme_id_map.get("a", [10])[0]

    ids = [bos_id]
    for _ in range(num_phonemes):
        ids.append(vowel_id)
        ids.append(pad_id)
    ids.append(eos_id)

    phoneme_ids = np.array([ids], dtype=np.int64)
    seq_len = phoneme_ids.shape[1]

    inputs: dict[str, np.ndarray] = {
        "input": phoneme_ids,
        "input_lengths": np.array([seq_len], dtype=np.int64),
        "scales": np.array([0.667, 1.0, 0.8], dtype=np.float32),
    }

    if "sid" in input_names:
        inputs["sid"] = np.array([speaker_id], dtype=np.int64)
    if "lid" in input_names:
        inputs["lid"] = np.array([language_id], dtype=np.int64)
    if "prosody_features" in input_names:
        inputs["prosody_features"] = np.zeros((1, seq_len, 3), dtype=np.int64)

    return inputs


def run_profiling(
    model_path: str,
    config_path: str,
    *,
    warmup: int = 2,
    runs: int = 3,
    output_dir: str = ".",
    top_n: int = 0,
    num_phonemes: int = 40,
) -> str:
    """Run inference with ORT profiling and return the profile JSON path.

    Args:
        model_path: Path to .onnx model.
        config_path: Path to config JSON.
        warmup: Number of warmup runs (no profiling).
        runs: Number of profiled runs (profile is from the last run).
        output_dir: Directory to save profile JSON.
        top_n: If > 0, only show top N operators.
        num_phonemes: Number of phonemes in dummy input.

    Returns:
        Path to the saved profile JSON file.
    """
    import onnxruntime  # noqa: PLC0415

    config = _load_config(config_path)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Model: {model_path}")
    print(f"Config: {config_path}")
    print(f"Warmup runs: {warmup}, Profiled runs: {runs}")
    print(f"Input phonemes: {num_phonemes}")
    print()

    # --- Warmup (no profiling, separate session) ---
    if warmup > 0:
        print(f"Running {warmup} warmup iteration(s)...")
        from piper_train.ort_utils import create_session_options  # noqa: PLC0415

        warmup_opts = create_session_options()
        warmup_session = onnxruntime.InferenceSession(
            model_path, sess_options=warmup_opts, providers=["CPUExecutionProvider"]
        )
        warmup_input_names = [inp.name for inp in warmup_session.get_inputs()]
        warmup_inputs = _build_dummy_inputs(
            config, input_names=warmup_input_names, num_phonemes=num_phonemes
        )
        for i in range(warmup):
            t0 = time.perf_counter()
            warmup_session.run(None, warmup_inputs)
            t1 = time.perf_counter()
            print(f"  warmup {i + 1}: {(t1 - t0) * 1000:.1f} ms")
        del warmup_session
        print()

    # --- Profiled runs ---
    profile_prefix = os.path.join(output_dir, "piper_profile")
    profile_file = None
    run_times: list[float] = []

    for run_idx in range(runs):
        sess_options = onnxruntime.SessionOptions()
        sess_options.enable_profiling = True
        sess_options.profile_file_prefix = profile_prefix
        # Keep the same optimization settings as production
        sess_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        sess_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        sess_options.enable_cpu_mem_arena = True
        sess_options.enable_mem_pattern = True
        sess_options.enable_mem_reuse = True

        session = onnxruntime.InferenceSession(
            model_path, sess_options=sess_options, providers=["CPUExecutionProvider"]
        )
        input_names = [inp.name for inp in session.get_inputs()]
        inputs = _build_dummy_inputs(
            config, input_names=input_names, num_phonemes=num_phonemes
        )

        t0 = time.perf_counter()
        outputs = session.run(None, inputs)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0
        run_times.append(elapsed_ms)

        audio = outputs[0].squeeze()
        sample_rate = config.get("audio", {}).get("sample_rate", 22050)
        audio_dur_sec = len(audio) / sample_rate
        rtf = (elapsed_ms / 1000.0) / audio_dur_sec if audio_dur_sec > 0 else 0.0

        # End profiling and get the file path
        profile_file = session.end_profiling()
        print(
            f"  run {run_idx + 1}: {elapsed_ms:.1f} ms "
            f"(audio: {audio_dur_sec:.2f}s, RTF: {rtf:.3f})"
        )
        del session

    print()
    if run_times:
        avg_ms = sum(run_times) / len(run_times)
        min_ms = min(run_times)
        max_ms = max(run_times)
        print(
            f"Inference time: avg={avg_ms:.1f} ms, "
            f"min={min_ms:.1f} ms, max={max_ms:.1f} ms"
        )
        print()

    # --- Analyze last profile ---
    if profile_file and os.path.exists(profile_file):
        print(f"Profile saved to: {profile_file}")
        analyze_profile(profile_file, top_n=top_n)
        return profile_file

    print("Warning: No profile file was generated.", file=sys.stderr)
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="profile_onnx",
        description="Profile ONNX Runtime inference per-operator execution time.",
    )
    # Mode selection
    parser.add_argument(
        "--analyze",
        metavar="JSON",
        help="Analyze an existing ORT profile JSON (skip inference).",
    )

    # Inference mode options
    parser.add_argument(
        "-m", "--model", help="Path to ONNX model file (.onnx)"
    )
    parser.add_argument(
        "-c", "--config", help="Path to model config JSON (auto-resolved if omitted)."
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=2,
        help="Number of warmup runs before profiling (default: 2).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of profiled inference runs (default: 3).",
    )
    parser.add_argument(
        "--num-phonemes",
        type=int,
        default=40,
        help="Number of phonemes in dummy input (default: 40).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save profile JSON (default: current directory).",
    )

    # Display options
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        metavar="N",
        help="Show only top N operators by total time (default: all).",
    )

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s"
    )

    if args.analyze:
        analyze_profile(args.analyze, top_n=args.top)
        return

    if not args.model:
        parser.error("-m/--model is required unless --analyze is used.")

    config_path = _resolve_config(args.model, args.config)
    run_profiling(
        args.model,
        config_path,
        warmup=args.warmup,
        runs=args.runs,
        output_dir=args.output_dir,
        top_n=args.top,
        num_phonemes=args.num_phonemes,
    )


if __name__ == "__main__":
    main()
