#!/usr/bin/env python3
"""Multi-runtime RTF / latency benchmark harness.

Drives an arbitrary piper-plus CLI (Python / Rust / Go / C# / C++ / WASM) by
launching it as a subprocess once per measurement run, measures wall-clock
synthesis time, decodes the resulting WAV header to recover audio duration,
and reports RTF, P50, P95 as JSON.

Wall-clock semantics: timing brackets the *entire subprocess lifetime*, so
the reported numbers include process startup, dynamic linker resolution,
CLI argument parsing, and ONNX session creation in addition to the actual
synthesis. This is **user-perceived latency** rather than **pure synthesis
time**; see ``_run_once`` for details. Use ``scripts/benchmark.py`` for an
in-process Python-only measurement that isolates ``session.run()``.

Why a separate script (vs ``scripts/benchmark.py``):
    ``scripts/benchmark.py`` is Python-only: it imports ``onnxruntime`` in
    process and times ``session.run()`` directly. Cross-runtime comparison
    needs a black-box harness that treats the runtime as opaque and only
    observes wall-clock + emitted WAV. This script is consumed by
    ``.github/workflows/multi-runtime-rtf.yml`` (one job per
    runtime x text-length matrix cell).

Usage:
    uv run python scripts/benchmark_runtime.py \\
        --runtime python \\
        --cli-cmd "uv run python -m piper" \\
        --model test/models/multilingual-test-medium.onnx \\
        --config test/models/multilingual-test-medium.onnx.json \\
        --text-file tests/fixtures/benchmark-texts.json \\
        --text-key short \\
        --runs 30 --warmup 5 \\
        --output benchmark_runtime_python_short.json

The ``--cli-cmd`` argument is a shell-tokenized command prefix; the harness
appends ``--model``, ``--output_file`` (or runtime-appropriate equivalent),
and feeds the text on stdin. See ``RUNTIME_PROFILES`` below for per-runtime
argument shape (each runtime has slightly different CLI flag spelling).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Runtime profiles
# ---------------------------------------------------------------------------
#
# Each runtime's CLI accepts ``--model`` and one of ``--output_file`` /
# ``--output-file`` / ``-f``, but there is no single spelling that works for
# all six. We declare per-runtime argv templates here so the workflow can pass
# a stable ``--runtime <name>`` axis and we resolve flag spellings centrally.
#
#   stdin_text: if True, the text body is piped on stdin (Python / Rust / Go /
#       C# / C++ all accept stdin-driven synthesis by default).
#   text_arg:   if set, pass the text via this flag instead (WASM Node harness
#       uses ``--text`` because there's no portable stdin pipe).
#   output_flag: flag name for the output WAV path.
#   extra_args: appended verbatim to the CLI invocation.

RUNTIME_PROFILES: dict[str, dict] = {
    "python": {
        "stdin_text": True,
        "output_flag": "--output_file",
        "extra_args": ["--quiet"],
    },
    "rust": {
        "stdin_text": True,
        "output_flag": "--output-file",
        "extra_args": ["--quiet"],
    },
    "go": {
        "stdin_text": True,
        "output_flag": "--output-file",
        "extra_args": ["--quiet"],
    },
    "csharp": {
        "stdin_text": True,
        "output_flag": "--output_file",
        "extra_args": ["--quiet"],
    },
    "cpp": {
        "stdin_text": True,
        "output_flag": "--output_file",
        "extra_args": ["--quiet"],
    },
    "wasm": {
        # Node entrypoint doesn't read stdin by default — pass text inline.
        "stdin_text": False,
        "text_arg": "--text",
        "output_flag": "--output-file",
        "extra_args": [],
    },
}


# ---------------------------------------------------------------------------
# WAV duration parser
# ---------------------------------------------------------------------------


def _wav_duration_seconds(wav_path: Path) -> float:
    """Read a RIFF/WAVE header and return audio duration in seconds.

    Supports both PCM (fmt code 1) and IEEE-float (fmt code 3). Streams the
    file rather than loading it, because the long-text benchmark can produce
    multi-MB output. Returns 0.0 if the file is missing or malformed (the
    caller treats that as a benchmark failure).
    """
    try:
        with open(wav_path, "rb") as f:
            riff = f.read(12)
            if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return 0.0

            sample_rate = 0
            num_channels = 0
            bits_per_sample = 0
            data_size = 0

            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                chunk_id = header[0:4]
                chunk_size = struct.unpack("<I", header[4:8])[0]
                if chunk_id == b"fmt ":
                    fmt = f.read(chunk_size)
                    if len(fmt) >= 16:
                        num_channels = struct.unpack("<H", fmt[2:4])[0]
                        sample_rate = struct.unpack("<I", fmt[4:8])[0]
                        bits_per_sample = struct.unpack("<H", fmt[14:16])[0]
                elif chunk_id == b"data":
                    data_size = chunk_size
                    break
                else:
                    f.seek(chunk_size, 1)

            if not sample_rate or not num_channels or not bits_per_sample:
                return 0.0
            bytes_per_sample = bits_per_sample // 8
            num_samples = data_size // (num_channels * bytes_per_sample)
            return num_samples / sample_rate
    except (OSError, struct.error):
        return 0.0


# ---------------------------------------------------------------------------
# Subprocess driver
# ---------------------------------------------------------------------------


def _build_cmd(
    cli_cmd: list[str],
    runtime: str,
    model: str,
    config: str | None,
    output_path: Path,
    text: str,
) -> tuple[list[str], str | None]:
    """Assemble argv and (optionally) stdin payload for a single synthesis."""
    profile = RUNTIME_PROFILES[runtime]
    argv = list(cli_cmd)
    argv.extend(["--model", model])
    if config:
        # Most runtimes auto-discover ``<model>.json`` next to ``<model>``;
        # only pass --config when explicitly provided so the harness doesn't
        # accidentally trip flag-name mismatches on runtimes that don't
        # accept --config (e.g. some WASM builds).
        argv.extend(["--config", config])
    argv.extend([profile["output_flag"], str(output_path)])
    argv.extend(profile.get("extra_args", []))

    stdin_payload: str | None = None
    if profile.get("stdin_text"):
        stdin_payload = text
    else:
        argv.extend([profile["text_arg"], text])

    return argv, stdin_payload


def _run_once(
    cli_cmd: list[str],
    runtime: str,
    model: str,
    config: str | None,
    text: str,
    timeout_s: float,
) -> tuple[float, float]:
    """Run the CLI once, return (wall_clock_seconds, audio_duration_seconds).

    Wall-clock scope: ``time.perf_counter()`` brackets the entire
    ``subprocess.run(...)`` call, which means the measurement *includes*
    process startup (Python interpreter / .NET runtime / Go binary load),
    dynamic linker resolution, CLI argument parsing, ONNX session creation,
    model file I/O, warm-up of any per-process caches, the actual synthesis,
    WAV header + sample writing, and process teardown.

    In other words: this is **user-perceived latency**, not **pure synthesis
    time**. Two consequences for callers comparing numbers:

    * Fast runtimes with heavy startup costs (e.g. .NET cold start, Python
      import time) will look slower than they actually are at steady state.
      That is intentional — RTF reported by this harness is what an end
      user shelling out to the CLI will feel.
    * For a pure ``session.run()`` measurement use
      ``scripts/benchmark.py`` instead (Python-only, in-process).

    Raises ``RuntimeError`` if the subprocess returns non-zero, times out, or
    produces a WAV with zero audio duration.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "out.wav"
        argv, stdin_payload = _build_cmd(
            cli_cmd, runtime, model, config, out_path, text
        )

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                argv,
                input=stdin_payload,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"CLI timed out after {timeout_s}s: {' '.join(argv)}"
            ) from exc
        elapsed = time.perf_counter() - t0

        if proc.returncode != 0:
            raise RuntimeError(
                f"CLI exited with code {proc.returncode}: "
                f"{' '.join(argv)}\nstderr={proc.stderr[-2000:]}"
            )

        duration = _wav_duration_seconds(out_path)
        if duration <= 0:
            raise RuntimeError(
                f"CLI produced no audio: {' '.join(argv)}\nstderr={proc.stderr[-2000:]}"
            )
        return elapsed, duration


# ---------------------------------------------------------------------------
# Core benchmark loop
# ---------------------------------------------------------------------------


def benchmark_runtime(
    cli_cmd: list[str],
    runtime: str,
    model: str,
    config: str | None,
    text: str,
    *,
    warmup: int,
    runs: int,
    timeout_s: float,
) -> dict:
    """Run warmup + timed iterations, return aggregated metrics dict."""
    if runtime not in RUNTIME_PROFILES:
        raise ValueError(
            f"unknown runtime {runtime!r} (valid: {sorted(RUNTIME_PROFILES)})"
        )

    # ---- Warmup ----
    for i in range(warmup):
        print(f"[warmup {i + 1}/{warmup}]", file=sys.stderr, flush=True)
        _run_once(cli_cmd, runtime, model, config, text, timeout_s)

    # ---- Timed ----
    wall_clocks: list[float] = []
    audio_durations: list[float] = []
    for i in range(runs):
        wall, audio = _run_once(cli_cmd, runtime, model, config, text, timeout_s)
        wall_clocks.append(wall)
        audio_durations.append(audio)
        print(
            f"[run {i + 1}/{runs}] wall={wall * 1000:.1f}ms "
            f"audio={audio:.3f}s rtf={wall / audio:.4f}",
            file=sys.stderr,
            flush=True,
        )

    wall_ms_sorted = sorted(w * 1000 for w in wall_clocks)
    p50_ms = wall_ms_sorted[len(wall_ms_sorted) // 2]
    p95_idx = min(int(len(wall_ms_sorted) * 0.95), len(wall_ms_sorted) - 1)
    p95_ms = wall_ms_sorted[p95_idx]
    mean_wall = statistics.mean(wall_clocks)
    mean_audio = statistics.mean(audio_durations)
    rtf = mean_wall / mean_audio if mean_audio > 0 else float("inf")

    return {
        "runtime": runtime,
        "model": os.path.basename(model),
        "cli_cmd": " ".join(cli_cmd),
        "n_warmup": warmup,
        "n_runs": runs,
        "rtf": round(rtf, 4),
        "latency_p50_ms": round(p50_ms, 1),
        "latency_p95_ms": round(p95_ms, 1),
        "wall_mean_ms": round(mean_wall * 1000, 1),
        "audio_mean_s": round(mean_audio, 3),
        "system": {
            "os": f"{platform.system()} {platform.release()}",
            "cpu": platform.processor() or platform.machine(),
            "python": platform.python_version(),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_text(text_file: Path, text_key: str | None, inline_text: str | None) -> str:
    """Resolve the synthesis text from --text-file/--text-key or --text."""
    if inline_text is not None:
        return inline_text
    if text_file is None:
        raise SystemExit("--text or --text-file is required")
    with open(text_file, encoding="utf-8") as f:
        data = json.load(f)
    texts = data.get("texts", {})
    if text_key is None:
        raise SystemExit("--text-key is required when --text-file is set")
    if text_key not in texts:
        raise SystemExit(
            f"--text-key {text_key!r} not found in {text_file} "
            f"(available: {sorted(texts)})"
        )
    entry = texts[text_key]
    if isinstance(entry, str):
        return entry
    return entry["text"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Multi-runtime RTF/latency benchmark for piper-plus CLIs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--runtime",
        required=True,
        choices=sorted(RUNTIME_PROFILES),
        help="Runtime profile (selects per-runtime CLI flag spelling).",
    )
    p.add_argument(
        "--cli-cmd",
        required=True,
        help=(
            "CLI command prefix (shell-tokenized). "
            "Example: 'uv run python -m piper' or "
            "'./target/release/piper-plus'."
        ),
    )
    p.add_argument("--model", required=True, help="Path to ONNX model file.")
    p.add_argument("--config", help="Path to model config.json (optional).")
    p.add_argument("--text-file", type=Path, help="Path to benchmark-texts.json.")
    p.add_argument("--text-key", help="Key under 'texts' (short/medium/long).")
    p.add_argument(
        "--text",
        help="Inline text (overrides --text-file/--text-key).",
    )
    p.add_argument("--runs", type=int, default=30, help="Timed iterations.")
    p.add_argument("--warmup", type=int, default=5, help="Warmup iterations.")
    p.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="Per-run subprocess timeout in seconds.",
    )
    p.add_argument("--output", required=True, help="Output JSON path.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point."""
    args = parse_args(argv)
    text = _load_text(args.text_file, args.text_key, args.text)
    cli_cmd = shlex.split(args.cli_cmd)
    result = benchmark_runtime(
        cli_cmd,
        args.runtime,
        args.model,
        args.config,
        text,
        warmup=args.warmup,
        runs=args.runs,
        timeout_s=args.timeout_s,
    )
    # Tag the text-key so the workflow aggregator can group by it without
    # having to re-parse the input fixture.
    result["text_key"] = args.text_key or "inline"
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
