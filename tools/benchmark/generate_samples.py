#!/usr/bin/env python3
"""Generate benchmark audio samples from multiple TTS models.

Reads model definitions from models.yaml, generates audio for each
model x language x test sentence combination, and records RTF metrics.

Usage:
    uv run python tools/benchmark/generate_samples.py \
        --models-config tools/benchmark/models.yaml \
        --texts-dir tools/benchmark/texts/ \
        --output-dir /tmp/mos_samples/ \
        --languages ja,en \
        --speaker-ids "0,20"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml


# ---------------------------------------------------------------------------
# piper-plus inference helpers (standalone, no piper_train import)
# ---------------------------------------------------------------------------

_LOGGER = logging.getLogger("benchmark.generate_samples")

SAMPLE_RATE = 22050


def _expand_env(value: str) -> str:
    """Expand ${VAR} references in a string using os.environ."""
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        value,
    )


def _load_models_config(path: Path) -> list[dict]:
    """Load and validate models.yaml, expanding environment variables."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    models = raw.get("models", [])
    expanded = []
    for model in models:
        m = dict(model)
        for key in ("path", "config", "command"):
            if key in m and isinstance(m[key], str):
                m[key] = _expand_env(m[key])
        expanded.append(m)
    return expanded


def _load_texts(texts_dir: Path, languages: list[str]) -> dict[str, list[str]]:
    """Load test sentences for each language.

    Returns:
        {lang_code: [sentence1, sentence2, ...]}
    """
    result: dict[str, list[str]] = {}
    for lang in languages:
        txt_path = texts_dir / f"{lang}.txt"
        if not txt_path.exists():
            _LOGGER.warning(
                "Text file not found: %s (skipping language %s)", txt_path, lang
            )
            continue
        lines = [
            line.strip()
            for line in txt_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not lines:
            _LOGGER.warning("Empty text file: %s", txt_path)
            continue
        result[lang] = lines
        _LOGGER.info("Loaded %d sentences for %s", len(lines), lang)
    return result


# ---------------------------------------------------------------------------
# Audio utilities (standalone)
# ---------------------------------------------------------------------------


def _audio_float_to_int16(
    audio: np.ndarray, max_wav_value: float = 32767.0
) -> np.ndarray:
    """Normalize audio and convert to int16 range."""
    audio_norm = audio * (max_wav_value / max(0.01, np.max(np.abs(audio))))
    audio_norm = np.clip(audio_norm, -max_wav_value, max_wav_value)
    return audio_norm.astype("int16")


def _write_wav(path: str, sample_rate: int, data: np.ndarray) -> None:
    """Write a WAV file using scipy or the built-in wavfile module."""
    try:
        from piper_train.vits.wavfile import write as _wav_write  # noqa: PLC0415

        _wav_write(path, sample_rate, data)
    except ImportError:
        import wave  # noqa: PLC0415

        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16
            wf.setframerate(sample_rate)
            wf.writeframes(data.tobytes())


def _read_wav_duration(path: str) -> float:
    """Read a WAV file and return its duration in seconds."""
    import wave  # noqa: PLC0415

    with wave.open(path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if rate == 0:
            return 0.0
        return frames / rate


# ---------------------------------------------------------------------------
# piper-plus ONNX inference
# ---------------------------------------------------------------------------


def _create_onnx_session(model_path: str, device: str = "cpu"):
    """Create an ONNX Runtime InferenceSession."""
    try:
        from piper_train.ort_utils import (  # noqa: PLC0415
            create_session_with_cache,
            warmup_onnx_session,
        )

        session = create_session_with_cache(model_path, device=device)
        warmup_onnx_session(session)
        return session
    except ImportError:
        import onnxruntime  # noqa: PLC0415

        _LOGGER.warning(
            "piper_train.ort_utils not available; using default session options"
        )
        session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        return session


def _get_session_info(session) -> dict[str, bool]:
    """Detect optional inputs supported by the ONNX model."""
    input_names = {inp.name for inp in session.get_inputs()}
    return {
        "has_prosody": "prosody_features" in input_names,
        "has_sid": "sid" in input_names,
        "has_lid": "lid" in input_names,
    }


def _text_to_phoneme_ids(
    text: str,
    phoneme_id_map: dict[str, list[int]],
    language: str,
    language_id_map: dict[str, int] | None = None,
) -> tuple[list[int], list[dict | None]]:
    """Convert text to phoneme IDs and prosody features.

    Delegates to piper_train.infer_onnx.text_to_phoneme_ids_and_prosody.
    """
    from piper_train.infer_onnx import text_to_phoneme_ids_and_prosody  # noqa: PLC0415

    return text_to_phoneme_ids_and_prosody(
        text, phoneme_id_map, language=language, language_id_map=language_id_map
    )


def _detect_language_id(
    text: str, language_id_map: dict[str, int], lang_hint: str
) -> int:
    """Detect the language ID for a given text."""
    if lang_hint in language_id_map:
        return language_id_map[lang_hint]
    # For multilingual keys, detect dominant language
    from piper_train.infer_onnx import _detect_dominant_language  # noqa: PLC0415

    return _detect_dominant_language(text, language_id_map)


def _synthesize_piper_plus(
    session,
    session_info: dict[str, bool],
    phoneme_ids: list[int],
    prosody_features: list[dict | None],
    speaker_id: int = 0,
    language_id: int = 0,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_scale_w: float = 0.8,
) -> tuple[np.ndarray, float]:
    """Run ONNX inference and return (int16_audio, inference_seconds)."""
    text = np.expand_dims(np.array(phoneme_ids, dtype=np.int64), 0)
    text_lengths = np.array([text.shape[1]], dtype=np.int64)
    scales = np.array([noise_scale, length_scale, noise_scale_w], dtype=np.float32)

    inputs: dict[str, np.ndarray] = {
        "input": text,
        "input_lengths": text_lengths,
        "scales": scales,
    }

    if session_info["has_sid"]:
        inputs["sid"] = np.array([speaker_id], dtype=np.int64)
    if session_info["has_lid"]:
        inputs["lid"] = np.array([language_id], dtype=np.int64)
    if session_info["has_prosody"]:
        if prosody_features:
            prosody_array = []
            for pf in prosody_features:
                if pf is None:
                    prosody_array.append([0, 0, 0])
                else:
                    prosody_array.append([pf["a1"], pf["a2"], pf["a3"]])
            inputs["prosody_features"] = np.expand_dims(
                np.array(prosody_array, dtype=np.int64), 0
            )
        else:
            inputs["prosody_features"] = np.zeros((1, text.shape[1], 3), dtype=np.int64)

    start = time.perf_counter()
    outputs = session.run(None, inputs)
    elapsed = time.perf_counter() - start

    audio = outputs[0].squeeze(0)
    audio_int16 = _audio_float_to_int16(audio.squeeze())
    return audio_int16, elapsed


# ---------------------------------------------------------------------------
# External TTS command
# ---------------------------------------------------------------------------


def _synthesize_external(
    command_template: str,
    text: str,
    lang: str,
    voice: str | None,
    output_path: str,
) -> float:
    """Invoke an external TTS command and return wall-clock seconds."""
    # Escape single quotes in text for shell safety
    escaped_text = text.replace("'", "'\\''")
    cmd = command_template.format(
        text=escaped_text,
        lang=lang,
        voice=voice or "",
        output=output_path,
    )
    _LOGGER.debug("External command: %s", cmd)
    start = time.perf_counter()
    try:
        subprocess.run(
            cmd,
            shell=True,
            check=True,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError as e:
        _LOGGER.error("Command not found: %s", e)
        return -1.0
    except subprocess.CalledProcessError as e:
        _LOGGER.error(
            "External command failed (rc=%d): %s\nstderr: %s",
            e.returncode,
            cmd,
            e.stderr.decode(errors="replace")[:500],
        )
        return -1.0
    except subprocess.TimeoutExpired:
        _LOGGER.error("External command timed out (60s): %s", cmd)
        return -1.0
    elapsed = time.perf_counter() - start
    return elapsed


# ---------------------------------------------------------------------------
# Main generation pipeline
# ---------------------------------------------------------------------------


def _generate_for_piper_model(
    model_def: dict,
    texts: dict[str, list[str]],
    output_dir: Path,
    languages: list[str],
    speaker_id_overrides: list[int] | None,
    device: str,
) -> list[dict]:
    """Generate samples for a piper-plus ONNX model."""
    model_name = model_def["name"]
    model_path = model_def["path"]
    config_path = model_def.get("config", "")

    if not Path(model_path).exists():
        _LOGGER.error("Model not found: %s (skipping %s)", model_path, model_name)
        return []

    # Load config
    if not config_path:
        config_path = str(Path(model_path).parent / "config.json")
    if not Path(config_path).exists():
        _LOGGER.error("Config not found: %s (skipping %s)", config_path, model_name)
        return []

    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    phoneme_id_map = config.get("phoneme_id_map", {})
    language_id_map = config.get("language_id_map", {})

    # Determine multilingual language key
    if len(language_id_map) > 1:
        ml_language = "-".join(sorted(language_id_map.keys()))
    else:
        ml_language = next(iter(language_id_map.keys()), "ja")

    # Create session
    _LOGGER.info("Loading model: %s (%s)", model_name, model_path)
    session = _create_onnx_session(model_path, device=device)
    session_info = _get_session_info(session)

    # Per-language speaker IDs from model definition
    model_speaker_ids = model_def.get("speaker_ids", {})

    results = []
    for lang in languages:
        if lang not in texts:
            continue

        lang_dir = output_dir / model_name / lang
        lang_dir.mkdir(parents=True, exist_ok=True)

        # Determine speaker ID
        if speaker_id_overrides:
            sid_list = speaker_id_overrides
        elif lang in model_speaker_ids:
            sid_list = [model_speaker_ids[lang]]
        else:
            sid_list = [0]

        # Determine language ID
        if lang in language_id_map:
            language_id = language_id_map[lang]
        else:
            language_id = 0

        for sid in sid_list:
            for text_idx, text in enumerate(texts[lang]):
                text_id = f"{text_idx:03d}"
                if len(sid_list) > 1:
                    out_path = lang_dir / f"{text_id}_sid{sid}.wav"
                else:
                    out_path = lang_dir / f"{text_id}.wav"

                try:
                    phoneme_ids, prosody = _text_to_phoneme_ids(
                        text,
                        phoneme_id_map,
                        language=ml_language,
                        language_id_map=language_id_map
                        if len(language_id_map) > 1
                        else None,
                    )
                except Exception as e:
                    _LOGGER.error(
                        "Phonemization failed for %s/%s/%s: %s",
                        model_name,
                        lang,
                        text_id,
                        e,
                    )
                    continue

                # Override language_id based on text content for multilingual
                if len(language_id_map) > 1:
                    language_id = _detect_language_id(text, language_id_map, lang)

                audio, infer_sec = _synthesize_piper_plus(
                    session,
                    session_info,
                    phoneme_ids,
                    prosody,
                    speaker_id=sid,
                    language_id=language_id,
                )

                _write_wav(str(out_path), SAMPLE_RATE, audio)
                audio_duration = audio.shape[0] / SAMPLE_RATE
                rtf = infer_sec / audio_duration if audio_duration > 0 else 0.0

                result = {
                    "model": model_name,
                    "language": lang,
                    "text_id": text_id,
                    "text": text,
                    "speaker_id": sid,
                    "output_path": str(out_path),
                    "audio_duration_sec": round(audio_duration, 4),
                    "inference_sec": round(infer_sec, 4),
                    "rtf": round(rtf, 4),
                    "sample_rate": SAMPLE_RATE,
                }
                results.append(result)
                _LOGGER.info(
                    "[%s/%s/%s] RTF=%.3f (infer=%.3fs, audio=%.3fs)",
                    model_name,
                    lang,
                    text_id,
                    rtf,
                    infer_sec,
                    audio_duration,
                )

    return results


def _generate_for_external_model(
    model_def: dict,
    texts: dict[str, list[str]],
    output_dir: Path,
    languages: list[str],
) -> list[dict]:
    """Generate samples for an external TTS model."""
    model_name = model_def["name"]
    command_template = model_def.get("command", "")
    voices = model_def.get("voices", {})

    if not command_template:
        _LOGGER.error("No command defined for external model: %s", model_name)
        return []

    results = []
    for lang in languages:
        if lang not in texts:
            continue

        lang_dir = output_dir / model_name / lang
        lang_dir.mkdir(parents=True, exist_ok=True)

        voice = voices.get(lang)
        if not voice and "{voice}" in command_template:
            _LOGGER.warning("No voice mapping for %s/%s (skipping)", model_name, lang)
            continue

        for text_idx, text in enumerate(texts[lang]):
            text_id = f"{text_idx:03d}"
            out_path = lang_dir / f"{text_id}.wav"

            infer_sec = _synthesize_external(
                command_template, text, lang, voice, str(out_path)
            )

            if infer_sec < 0 or not out_path.exists():
                _LOGGER.warning(
                    "Failed to generate %s/%s/%s", model_name, lang, text_id
                )
                continue

            audio_duration = _read_wav_duration(str(out_path))
            rtf = infer_sec / audio_duration if audio_duration > 0 else 0.0

            result = {
                "model": model_name,
                "language": lang,
                "text_id": text_id,
                "text": text,
                "output_path": str(out_path),
                "audio_duration_sec": round(audio_duration, 4),
                "inference_sec": round(infer_sec, 4),
                "rtf": round(rtf, 4),
            }
            results.append(result)
            _LOGGER.info(
                "[%s/%s/%s] RTF=%.3f (infer=%.3fs, audio=%.3fs)",
                model_name,
                lang,
                text_id,
                rtf,
                infer_sec,
                audio_duration,
            )

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate benchmark audio samples from multiple TTS models.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    # Generate samples for Japanese and English
    uv run python tools/benchmark/generate_samples.py \\
        --models-config tools/benchmark/models.yaml \\
        --texts-dir tools/benchmark/texts/ \\
        --output-dir /tmp/mos_samples/ \\
        --languages ja,en

    # Specify speaker IDs and use GPU
    uv run python tools/benchmark/generate_samples.py \\
        --models-config tools/benchmark/models.yaml \\
        --texts-dir tools/benchmark/texts/ \\
        --output-dir /tmp/mos_samples/ \\
        --languages ja,en,zh \\
        --speaker-ids "0,20" \\
        --device gpu
""",
    )
    parser.add_argument(
        "--models-config",
        type=Path,
        default=Path("tools/benchmark/models.yaml"),
        help="Path to models.yaml (default: tools/benchmark/models.yaml)",
    )
    parser.add_argument(
        "--texts-dir",
        type=Path,
        default=Path("tools/benchmark/texts"),
        help="Directory containing {lang}.txt files (default: tools/benchmark/texts)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for generated WAV files",
    )
    parser.add_argument(
        "--languages",
        default="ja,en,zh,es,fr,pt",
        help="Comma-separated language codes (default: ja,en,zh,es,fr,pt)",
    )
    parser.add_argument(
        "--speaker-ids",
        default=None,
        help="Comma-separated speaker IDs to override model defaults (e.g. '0,20')",
    )
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model names to run (default: all models in config)",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        default="cpu",
        help="Device for piper-plus models (default: cpu)",
    )
    parser.add_argument(
        "--skip-external",
        action="store_true",
        help="Skip external (non-piper-plus) models",
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

    # Parse arguments
    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    speaker_id_overrides = None
    if args.speaker_ids:
        speaker_id_overrides = [int(s.strip()) for s in args.speaker_ids.split(",")]

    model_filter = None
    if args.models:
        model_filter = {m.strip() for m in args.models.split(",")}

    # Load configs
    models = _load_models_config(args.models_config)
    texts = _load_texts(args.texts_dir, languages)

    if not texts:
        _LOGGER.error("No text files loaded. Check --texts-dir and --languages.")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate samples
    all_results: list[dict] = []
    for model_def in models:
        model_name = model_def["name"]
        model_type = model_def.get("type", "piper-plus")

        if model_filter and model_name not in model_filter:
            _LOGGER.info("Skipping model %s (not in --models filter)", model_name)
            continue

        if model_type == "external" and args.skip_external:
            _LOGGER.info("Skipping external model %s (--skip-external)", model_name)
            continue

        _LOGGER.info("=== Generating samples for: %s (%s) ===", model_name, model_type)

        if model_type == "piper-plus":
            results = _generate_for_piper_model(
                model_def,
                texts,
                args.output_dir,
                languages,
                speaker_id_overrides,
                args.device,
            )
        elif model_type == "external":
            results = _generate_for_external_model(
                model_def,
                texts,
                args.output_dir,
                languages,
            )
        else:
            _LOGGER.warning(
                "Unknown model type: %s (skipping %s)", model_type, model_name
            )
            continue

        all_results.extend(results)

    # Save results
    results_path = args.output_dir / "generation_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "languages": languages,
                "total_samples": len(all_results),
                "results": all_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    _LOGGER.info(
        "Generation complete: %d samples written to %s",
        len(all_results),
        args.output_dir,
    )
    _LOGGER.info("Results saved to %s", results_path)

    # Print summary table
    print("\n=== Generation Summary ===")
    print(f"{'Model':<30} {'Lang':<6} {'Samples':<10} {'Avg RTF':<10}")
    print("-" * 60)

    from collections import defaultdict  # noqa: PLC0415

    summary: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in all_results:
        key = (r["model"], r["language"])
        summary[key].append(r["rtf"])

    for (model, lang), rtfs in sorted(summary.items()):
        avg_rtf = sum(rtfs) / len(rtfs) if rtfs else 0.0
        print(f"{model:<30} {lang:<6} {len(rtfs):<10} {avg_rtf:<10.4f}")


if __name__ == "__main__":
    main()
