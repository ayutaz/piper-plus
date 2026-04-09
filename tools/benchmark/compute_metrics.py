#!/usr/bin/env python3
"""Compute automatic metrics for benchmark audio samples.

Reads WAV files from the samples directory and computes:
- Audio duration (seconds)
- File size (bytes)
- Sample rate verification (22050 Hz expected)
- RTF from generation_results.json (if available)
- UTMOS automatic quality score (optional, requires --utmos)

Usage:
    uv run python tools/benchmark/compute_metrics.py \
        --samples-dir /tmp/mos_samples/ \
        --output metrics.json

    # With UTMOS automatic quality score
    uv run python tools/benchmark/compute_metrics.py \
        --samples-dir /tmp/mos_samples/ \
        --output metrics.json \
        --utmos
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger("benchmark.compute_metrics")

EXPECTED_SAMPLE_RATE = 22050


# ---------------------------------------------------------------------------
# Audio analysis utilities
# ---------------------------------------------------------------------------


def _read_wav_info(wav_path: Path) -> dict:
    """Read WAV file and return metadata + raw audio data."""
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    duration_sec = n_frames / frame_rate if frame_rate > 0 else 0.0
    file_size = wav_path.stat().st_size

    # Convert to float32 for analysis
    if sample_width == 2:
        audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = (
            np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
        )
    else:
        audio = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

    # Handle multi-channel: take first channel
    if n_channels > 1:
        audio = audio[::n_channels]

    return {
        "duration_sec": round(duration_sec, 4),
        "file_size_bytes": file_size,
        "sample_rate": frame_rate,
        "n_channels": n_channels,
        "sample_width": sample_width,
        "n_frames": n_frames,
        "audio_float32": audio,
        "sample_rate_ok": frame_rate == EXPECTED_SAMPLE_RATE,
    }


def _compute_rms_db(audio: np.ndarray) -> float:
    """Compute RMS level in dB."""
    rms = np.sqrt(np.mean(audio**2))
    if rms < 1e-10:
        return -100.0
    return round(20.0 * np.log10(rms), 2)


def _compute_peak_db(audio: np.ndarray) -> float:
    """Compute peak level in dB."""
    peak = np.max(np.abs(audio))
    if peak < 1e-10:
        return -100.0
    return round(20.0 * np.log10(peak), 2)


def _compute_silence_ratio(audio: np.ndarray, threshold_db: float = -40.0) -> float:
    """Compute the ratio of silent frames (below threshold) to total frames.

    Uses 10ms frame analysis.
    """
    if len(audio) == 0:
        return 0.0

    frame_size = int(EXPECTED_SAMPLE_RATE * 0.01)  # 10ms frames
    n_frames = len(audio) // frame_size
    if n_frames == 0:
        return 0.0

    threshold_linear = 10.0 ** (threshold_db / 20.0)
    silent_frames = 0
    for i in range(n_frames):
        frame = audio[i * frame_size : (i + 1) * frame_size]
        rms = np.sqrt(np.mean(frame**2))
        if rms < threshold_linear:
            silent_frames += 1

    return round(silent_frames / n_frames, 4)


# ---------------------------------------------------------------------------
# UTMOS (optional)
# ---------------------------------------------------------------------------


def _compute_utmos_scores(
    wav_paths: list[Path],
) -> dict[str, float]:
    """Compute UTMOS scores for a list of WAV files.

    Requires torch and the UTMOS model (downloaded on first use).
    Returns {str(wav_path): utmos_score}.
    """
    try:
        import torch  # noqa: PLC0415
        import torchaudio  # noqa: PLC0415
    except ImportError:
        _LOGGER.error(
            "UTMOS requires torch and torchaudio. "
            "Install with: pip install torch torchaudio"
        )
        return {}

    _LOGGER.info("Loading UTMOS model...")
    try:
        predictor = torch.hub.load(
            "tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True
        )
    except Exception as e:
        _LOGGER.error("Failed to load UTMOS model: %s", e)
        return {}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictor = predictor.to(device)
    predictor.eval()

    results: dict[str, float] = {}
    for i, wav_path in enumerate(wav_paths):
        try:
            waveform, sr = torchaudio.load(str(wav_path))
            # Resample to 16kHz if needed (UTMOS expects 16kHz)
            if sr != 16000:
                resampler = torchaudio.transforms.Resample(sr, 16000)
                waveform = resampler(waveform)
            # Take first channel, add batch dim
            waveform = waveform[0:1].to(device)
            with torch.no_grad():
                score = predictor(waveform, sr=16000)
            results[str(wav_path)] = round(score.item(), 4)
            if (i + 1) % 10 == 0:
                _LOGGER.info("UTMOS progress: %d / %d", i + 1, len(wav_paths))
        except Exception as e:
            _LOGGER.warning("UTMOS failed for %s: %s", wav_path, e)
            results[str(wav_path)] = -1.0

    _LOGGER.info(
        "UTMOS computation complete: %d / %d files", len(results), len(wav_paths)
    )
    return results


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------


def _scan_samples_dir(samples_dir: Path) -> list[dict]:
    """Scan samples directory for WAV files.

    Expected structure: {samples_dir}/{model_name}/{lang}/{text_id}.wav
    """
    samples = []
    if not samples_dir.exists():
        _LOGGER.error("Samples directory does not exist: %s", samples_dir)
        return samples

    for model_dir in sorted(samples_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        for lang_dir in sorted(model_dir.iterdir()):
            if not lang_dir.is_dir():
                continue
            lang = lang_dir.name
            for wav_file in sorted(lang_dir.glob("*.wav")):
                text_id = wav_file.stem
                samples.append(
                    {
                        "model": model_name,
                        "language": lang,
                        "text_id": text_id,
                        "wav_path": wav_file,
                    }
                )

    return samples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute automatic metrics for benchmark audio samples.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    uv run python tools/benchmark/compute_metrics.py \\
        --samples-dir /tmp/mos_samples/ \\
        --output metrics.json

    # With UTMOS automatic quality score
    uv run python tools/benchmark/compute_metrics.py \\
        --samples-dir /tmp/mos_samples/ \\
        --output metrics.json \\
        --utmos
""",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        required=True,
        help="Directory containing generated WAV samples",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("metrics.json"),
        help="Output path for metrics JSON (default: metrics.json)",
    )
    parser.add_argument(
        "--utmos",
        action="store_true",
        help="Compute UTMOS automatic quality scores (requires torch, torchaudio)",
    )
    parser.add_argument(
        "--generation-results",
        type=Path,
        default=None,
        help="Path to generation_results.json for RTF data (default: auto-detect in samples-dir)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Scan for samples
    samples = _scan_samples_dir(args.samples_dir)
    if not samples:
        _LOGGER.error("No WAV files found in %s", args.samples_dir)
        sys.exit(1)

    _LOGGER.info("Found %d WAV samples", len(samples))

    # Load generation results for RTF data
    gen_results_path = args.generation_results
    if gen_results_path is None:
        gen_results_path = args.samples_dir / "generation_results.json"
    rtf_lookup: dict[str, float] = {}
    if gen_results_path.exists():
        with open(gen_results_path, encoding="utf-8") as f:
            gen_data = json.load(f)
        for r in gen_data.get("results", []):
            key = f"{r['model']}/{r['language']}/{r['text_id']}"
            rtf_lookup[key] = r.get("rtf", -1.0)
        _LOGGER.info("Loaded RTF data for %d samples", len(rtf_lookup))

    # Compute UTMOS if requested
    utmos_scores: dict[str, float] = {}
    if args.utmos:
        wav_paths = [s["wav_path"] for s in samples]
        utmos_scores = _compute_utmos_scores(wav_paths)

    # Compute metrics for each sample
    per_sample_metrics: list[dict] = []
    sample_rate_issues: list[str] = []

    for sample in samples:
        wav_path = sample["wav_path"]
        wav_info = _read_wav_info(wav_path)
        audio = wav_info.pop("audio_float32")

        # Audio analysis
        rms_db = _compute_rms_db(audio)
        peak_db = _compute_peak_db(audio)
        silence_ratio = _compute_silence_ratio(audio)

        # Sample rate check
        if not wav_info["sample_rate_ok"]:
            sample_rate_issues.append(
                f"{wav_path}: expected {EXPECTED_SAMPLE_RATE}Hz, got {wav_info['sample_rate']}Hz"
            )

        # RTF from generation results
        rtf_key = f"{sample['model']}/{sample['language']}/{sample['text_id']}"
        rtf = rtf_lookup.get(rtf_key, None)

        # UTMOS
        utmos = utmos_scores.get(str(wav_path), None)

        metric = {
            "model": sample["model"],
            "language": sample["language"],
            "text_id": sample["text_id"],
            "wav_path": str(wav_path),
            "duration_sec": wav_info["duration_sec"],
            "file_size_bytes": wav_info["file_size_bytes"],
            "sample_rate": wav_info["sample_rate"],
            "sample_rate_ok": wav_info["sample_rate_ok"],
            "rms_db": rms_db,
            "peak_db": peak_db,
            "silence_ratio": silence_ratio,
        }
        if rtf is not None:
            metric["rtf"] = rtf
        if utmos is not None:
            metric["utmos"] = utmos

        per_sample_metrics.append(metric)

    # Compute aggregate metrics by model x language
    aggregates: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for m in per_sample_metrics:
        key = (m["model"], m["language"])
        aggregates[key]["duration_sec"].append(m["duration_sec"])
        aggregates[key]["file_size_bytes"].append(m["file_size_bytes"])
        aggregates[key]["rms_db"].append(m["rms_db"])
        aggregates[key]["peak_db"].append(m["peak_db"])
        aggregates[key]["silence_ratio"].append(m["silence_ratio"])
        if "rtf" in m:
            aggregates[key]["rtf"].append(m["rtf"])
        if "utmos" in m and m["utmos"] >= 0:
            aggregates[key]["utmos"].append(m["utmos"])

    aggregate_metrics: list[dict] = []
    for (model, lang), data in sorted(aggregates.items()):
        agg: dict = {
            "model": model,
            "language": lang,
            "n_samples": len(data["duration_sec"]),
        }
        for metric_name in (
            "duration_sec",
            "file_size_bytes",
            "rms_db",
            "peak_db",
            "silence_ratio",
            "rtf",
            "utmos",
        ):
            values = data.get(metric_name, [])
            if values:
                agg[f"{metric_name}_mean"] = round(np.mean(values).item(), 4)
                agg[f"{metric_name}_std"] = round(np.std(values).item(), 4)
                agg[f"{metric_name}_min"] = round(min(values), 4)
                agg[f"{metric_name}_max"] = round(max(values), 4)
        aggregate_metrics.append(agg)

    # Build output report
    report = {
        "samples_dir": str(args.samples_dir),
        "total_samples": len(per_sample_metrics),
        "expected_sample_rate": EXPECTED_SAMPLE_RATE,
        "sample_rate_issues": sample_rate_issues,
        "utmos_enabled": args.utmos,
        "aggregate_metrics": aggregate_metrics,
        "per_sample_metrics": per_sample_metrics,
    }

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    _LOGGER.info("Metrics written to %s", args.output)

    # Print summary
    print("\n=== Metrics Summary ===")
    header = f"{'Model':<30} {'Lang':<6} {'N':<5} {'Dur(s)':<10} {'Size(KB)':<10}"
    if any("rtf_mean" in a for a in aggregate_metrics):
        header += f" {'RTF':<10}"
    if any("utmos_mean" in a for a in aggregate_metrics):
        header += f" {'UTMOS':<10}"
    print(header)
    print("-" * len(header))

    for agg in aggregate_metrics:
        line = (
            f"{agg['model']:<30} "
            f"{agg['language']:<6} "
            f"{agg['n_samples']:<5} "
            f"{agg.get('duration_sec_mean', 0):<10.2f} "
            f"{agg.get('file_size_bytes_mean', 0) / 1024:<10.1f}"
        )
        if "rtf_mean" in agg:
            line += f" {agg['rtf_mean']:<10.4f}"
        if "utmos_mean" in agg:
            line += f" {agg['utmos_mean']:<10.2f}"
        print(line)

    # Warnings
    if sample_rate_issues:
        print(
            f"\nWARNING: {len(sample_rate_issues)} files have unexpected sample rates:"
        )
        for issue in sample_rate_issues[:5]:
            print(f"  {issue}")
        if len(sample_rate_issues) > 5:
            print(f"  ... and {len(sample_rate_issues) - 5} more")


if __name__ == "__main__":
    main()
