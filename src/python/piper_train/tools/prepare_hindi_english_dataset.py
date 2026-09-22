#!/usr/bin/env python3
"""
prepare_hindi_english_dataset.py

Phase 2 dataset preparation tool for piper-plus Hindi + English model base.
Ingests:
  - IndicVoices-R Hindi (Devanagari text + WAV or Parquet shards)
  - Common Voice Hindi (optional, validated TSV)
  - LibriTTS-R English (normalized text + WAV)

Outputs:
  - dataset.jsonl (training records with phoneme_ids and prosody)
  - config.json (frozen 202 symbols, language_id_map: {hi: 0, en: 1})
  - stats.json (human-readable metrics, hour counts, drop reasons)
  - RECIPE.md (licenses, HF revisions, filters)
  - cache/22050/ (normalized .pt audio and .spec.pt spectrogram tensors)
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import io
import json
import logging
from pathlib import Path
import sys
import time
import unicodedata

import numpy as np
import soundfile as sf
import torch

try:
    from piper_plus_g2p import get_phonemizer
    from piper_plus_g2p.encode.encoder import PiperEncoder
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
    from piper_plus_g2p.encode.pua import map_token
except ImportError as e:
    sys.exit(f"Error importing piper_plus_g2p: {e}. Ensure PYTHONPATH includes src/python/g2p.")

from piper_train.norm_audio import (
    _atomic_torch_save,
    cache_norm_audio_fast,
    energy_vad_numpy,
    resample_only_no_vad,
)
from piper_train.vits.mel_processing import spectrogram_torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("prepare_hi_en")

TARGET_SR = 22050
EXPECTED_SYMBOLS = 202
EXPECTED_SHA256 = "29a91cd810ca43f91c50defe58882d0dc31cee534385bf199cd5c1afd87ff056"
LANGUAGE_ID_MAP = {"hi": 0, "en": 1}

_PHONEMIZE_BATCH_SIZE = 100
_RESAMPLE_BATCH_SIZE = 50
_GPU_SPEC_BATCH_SIZE = 64

FILTER_LENGTH = 1024
HOP_LENGTH = 256
WIN_LENGTH = 1024


def verify_inventory(id_map: dict) -> None:
    """Verifies that the phoneme ID map matches the Phase 0 202-symbol contract."""
    if len(id_map) != EXPECTED_SYMBOLS:
        raise ValueError(
            f"Inventory mismatch: expected {EXPECTED_SYMBOLS} symbols, found {len(id_map)}"
        )

    ordered_keys = sorted(
        id_map.keys(),
        key=lambda k: id_map[k][0] if isinstance(id_map[k], list) else id_map[k]
    )
    computed_hash = hashlib.sha256(" ".join(ordered_keys).encode("utf-8")).hexdigest()
    if computed_hash != EXPECTED_SHA256:
        raise ValueError(
            f"Symbol list hash mismatch!\nExpected: {EXPECTED_SHA256}\nComputed: {computed_hash}\n"
            "Aborting: live inventory order has drifted from the frozen Phase 0 specification."
        )
    logger.info("Phoneme ID map verified: 202 symbols, SHA256 matches Phase 0 specification.")


def normalize_text(text: str, lang: str) -> str | None:
    """
    Normalizes text according to Phase 2 rules:
    - Unicode NFC normalization
    - Strip ZWJ (U+200D) and ZWNJ (U+200C)
    - Keep danda (। U+0964) and double danda (॥ U+0965)
    - Reject Hindi utterances with no Devanagari characters (U+0900-U+097F)
    """
    if not text:
        return None

    # NFC normalize
    text = unicodedata.normalize("NFC", text.strip())

    if lang == "hi":
        # Strip zero-width joiners
        text = text.replace("\u200c", "").replace("\u200d", "")
        # Require Devanagari characters
        if not any("\u0900" <= ch <= "\u097f" for ch in text):
            return None

    return text.strip() or None


# ---------------------------------------------------------------------------
# Multiprocessing Worker State & Functions
# ---------------------------------------------------------------------------

_worker_state: dict = {}


def _init_phonemize_worker(id_map: dict):
    """Initializes phonemizers and PiperEncoder per worker process."""
    _worker_state["id_map"] = id_map
    _worker_state["encoder"] = PiperEncoder(id_map, strict=False)
    _worker_state["hi_phonemizer"] = get_phonemizer("hi")
    _worker_state["en_phonemizer"] = get_phonemizer("en")


def _phonemize_single(
    text: str,
    wav_path: str,
    speaker_id_str: str,
    lang: str,
    lang_id: int
) -> dict:
    norm_text = normalize_text(text, lang)
    if not norm_text:
        return {"wav_path": wav_path, "error": "non_devanagari_or_empty"}

    phonemizer = (
        _worker_state["hi_phonemizer"] if lang == "hi"
        else _worker_state["en_phonemizer"]
    )
    encoder: PiperEncoder = _worker_state["encoder"]

    try:
        tokens, prosody_list = phonemizer.phonemize_with_prosody(norm_text)
        if not tokens:
            return {"wav_path": wav_path, "error": "empty_tokens"}

        # PiperEncoder converts tokens to PUA, looks up IDs,
        # inserts BOS (^), EOS ($), inter-phoneme pad (0),
        # and aligns prosody with padding.
        phoneme_ids, aligned_prosody = encoder.encode_with_prosody(tokens, prosody_list)
        prosody_features = PiperEncoder.prosody_to_dicts(aligned_prosody)

        if not phoneme_ids:
            return {"wav_path": wav_path, "error": "empty_phoneme_ids"}

        return {
            "text": norm_text,
            "wav_path": wav_path,
            "speaker_id_str": speaker_id_str,
            "language": lang,
            "language_id": lang_id,
            "phonemes": tokens,
            "phoneme_ids": phoneme_ids,
            "prosody_features": prosody_features,
            "missing": [],
        }
    except Exception as exc:
        return {"wav_path": wav_path, "error": f"g2p_error: {exc}"}


def _phonemize_batch_worker(
    batch: list[tuple[str, str, str, str, int]]
) -> list[dict]:
    results = []
    for text, wav_path, spk, lang, lang_id in batch:
        results.append(_phonemize_single(text, wav_path, spk, lang, lang_id))
    return results


def phonemize_dataset(
    entries: list[tuple[str, str, str]],
    lang: str,
    lang_id: int,
    id_map: dict,
    workers: int = 4
) -> tuple[list[dict], dict[str, int]]:
    """Phonemizes dataset entries using parallel workers."""
    logger.info(
        "Phonemizing %d %s utterances with %d workers...",
        len(entries), lang.upper(), workers
    )
    tasks = [(text, wav_path, spk, lang, lang_id) for text, wav_path, spk in entries]
    batches = [
        tasks[i: i + _PHONEMIZE_BATCH_SIZE]
        for i in range(0, len(tasks), _PHONEMIZE_BATCH_SIZE)
    ]

    phonemized = []
    drop_stats = Counter()

    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_phonemize_worker,
            initargs=(id_map,)
        ) as executor:
            futures = [executor.submit(_phonemize_batch_worker, b) for b in batches]
            done_count = 0
            for future in as_completed(futures):
                for res in future.result():
                    if "error" in res:
                        drop_stats[res["error"]] += 1
                    else:
                        phonemized.append(res)
                    done_count += 1
                if done_count % 5000 < _PHONEMIZE_BATCH_SIZE:
                    logger.info("Phonemized %d/%d %s", done_count, len(tasks), lang.upper())
    else:
        _init_phonemize_worker(id_map)
        for b in batches:
            for res in _phonemize_batch_worker(b):
                if "error" in res:
                    drop_stats[res["error"]] += 1
                else:
                    phonemized.append(res)

    logger.info(
        "Phonemization complete for %s: %d succeeded, %d dropped.",
        lang.upper(), len(phonemized), sum(drop_stats.values())
    )
    return phonemized, dict(drop_stats)


# ---------------------------------------------------------------------------
# Audio Caching & Spectrograms
# ---------------------------------------------------------------------------

def _resample_with_energy_vad(
    wav_path: str,
    cache_dir: Path,
    sample_rate: int = TARGET_SR,
    energy_vad_threshold: float = 0.02,
) -> tuple[str, str, float] | None:
    """Resamples audio to 22050 Hz and applies energy VAD trim."""
    import soxr

    try:
        audio_path = Path(wav_path).absolute()
        audio_cache_id = hashlib.sha256(str(audio_path).encode()).hexdigest()
        audio_norm_path = cache_dir / f"{audio_cache_id}.pt"

        if not audio_norm_path.exists():
            audio_data, src_sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
            if audio_data.ndim > 1:
                audio_data = audio_data.mean(axis=1)

            # Energy VAD on 16kHz
            audio_16k = (
                soxr.resample(audio_data, src_sr, 16000, quality="HQ")
                if src_sr != 16000
                else audio_data
            )
            offset_sec, duration_sec = energy_vad_numpy(
                audio_16k, threshold=energy_vad_threshold
            )

            offset_samples = int(offset_sec * src_sr)
            end_samples = (
                min(offset_samples + int(duration_sec * src_sr), len(audio_data))
                if duration_sec is not None
                else len(audio_data)
            )
            trimmed = audio_data[offset_samples:end_samples]

            if len(trimmed) == 0:
                trimmed = audio_data

            audio_rs = (
                soxr.resample(trimmed, src_sr, sample_rate, quality="MQ")
                if src_sr != sample_rate
                else trimmed
            )
            duration = len(audio_rs) / sample_rate
            if duration < 0.5 or duration > 20.0:
                return None

            audio_norm_tensor = torch.from_numpy(audio_rs).unsqueeze(0)
            _atomic_torch_save(audio_norm_tensor, audio_norm_path)
        else:
            t = torch.load(audio_norm_path, weights_only=True)
            duration = t.shape[-1] / sample_rate
            if duration < 0.5 or duration > 20.0:
                return None

        spec_path = cache_dir / f"{audio_cache_id}.spec.pt"
        return str(audio_norm_path), str(spec_path), duration
    except Exception as exc:
        logger.debug("Audio processing failed for %s: %exc", wav_path, exc)
        return None


def _cache_audio_batch_worker(args):
    wav_paths, cache_dir, sample_rate = args
    results = []
    for p in wav_paths:
        res = _resample_with_energy_vad(p, Path(cache_dir), sample_rate)
        results.append((p, res))
    return results


def _compute_specs_gpu_batch(
    items: list[tuple[str, str]],
    batch_size: int = _GPU_SPEC_BATCH_SIZE,
    device: str = "cuda:0",
    sample_rate: int = TARGET_SR,
) -> int:
    """Compute spectrograms on GPU in batches."""
    need_compute = [
        (norm_p, spec_p) for norm_p, spec_p in items if not Path(spec_p).exists()
    ]
    if not need_compute:
        return 0

    computed = 0
    n_batches = (len(need_compute) + batch_size - 1) // batch_size
    for b_idx in range(n_batches):
        batch = need_compute[b_idx * batch_size: (b_idx + 1) * batch_size]
        audios, lengths, valid_idx = [], [], []
        for j, (norm_p, _) in enumerate(batch):
            try:
                t = torch.load(norm_p, weights_only=True).squeeze(0)
                audios.append(t)
                lengths.append(t.shape[0])
                valid_idx.append(j)
            except Exception:
                pass

        if not audios:
            continue

        max_len = max(lengths)
        batch_tensor = torch.zeros(len(audios), max_len)
        for j, audio in enumerate(audios):
            batch_tensor[j, :lengths[j]] = audio

        batch_tensor = batch_tensor.to(device)
        try:
            specs = spectrogram_torch(
                y=batch_tensor,
                n_fft=FILTER_LENGTH,
                sampling_rate=sample_rate,
                hop_size=HOP_LENGTH,
                win_size=WIN_LENGTH,
                center=False,
            ).cpu()
            for j, v_idx in enumerate(valid_idx):
                _, spec_p = batch[v_idx]
                padded_len = lengths[j] + FILTER_LENGTH - HOP_LENGTH
                correct_frames = padded_len // HOP_LENGTH
                _atomic_torch_save(specs[j, :, :correct_frames].half(), spec_p)
                computed += 1
        except Exception as exc:
            logger.warning("GPU STFT batch %d failed: %s", b_idx, exc)

    return computed


def cache_audio_parallel(
    wav_paths: list[str],
    cache_dir: Path,
    sample_rate: int,
    workers: int,
    gpu_spec_device: str | None = None,
) -> dict[str, tuple[str, str, float]]:
    """Caches audio and computes spectrograms for all utterances."""
    logger.info("Caching audio for %d files...", len(wav_paths))
    batches = [
        wav_paths[i: i + _RESAMPLE_BATCH_SIZE]
        for i in range(0, len(wav_paths), _RESAMPLE_BATCH_SIZE)
    ]
    batch_args = [(b, str(cache_dir), sample_rate) for b in batches]

    audio_map = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_cache_audio_batch_worker, a) for a in batch_args]
        for future in as_completed(futures):
            for wav_p, res in future.result():
                if res is not None:
                    audio_map[wav_p] = res

    logger.info("Resampled %d/%d files successfully.", len(audio_map), len(wav_paths))

    spec_items = [(norm_p, spec_p) for norm_p, spec_p, _ in audio_map.values()]
    if gpu_spec_device and gpu_spec_device != "cpu":
        logger.info("Computing spectrograms on %s...", gpu_spec_device)
        computed = _compute_specs_gpu_batch(
            spec_items, batch_size=_GPU_SPEC_BATCH_SIZE, device=gpu_spec_device, sample_rate=sample_rate
        )
        logger.info("Computed %d spectrograms on GPU.", computed)
    else:
        logger.info("Computing spectrograms on CPU...")
        for norm_p, spec_p in spec_items:
            if not Path(spec_p).exists():
                try:
                    tensor = torch.load(norm_p, weights_only=True)
                    spec = spectrogram_torch(
                        y=tensor,
                        n_fft=FILTER_LENGTH,
                        sampling_rate=sample_rate,
                        hop_size=HOP_LENGTH,
                        win_size=WIN_LENGTH,
                        center=False,
                    ).squeeze(0)
                    _atomic_torch_save(spec.half(), spec_p)
                except Exception as exc:
                    logger.debug("CPU spec failed for %s: %s", norm_p, exc)

    # Filter audio_map to only those whose spec exists
    valid_map = {}
    for wav_p, (norm_p, spec_p, dur) in audio_map.items():
        if Path(norm_p).exists() and Path(spec_p).exists():
            valid_map[wav_p] = (norm_p, spec_p, dur)

    return valid_map


# ---------------------------------------------------------------------------
# Corpus Parsers
# ---------------------------------------------------------------------------

def parse_indicvoices_r(root_dir: Path, max_hours: float | None = None) -> list[tuple[str, str, str]]:
    """
    Parses IndicVoices-R Hindi folder.
    Supports:
      1. Loose CSV / TSV metadata files (metadata.csv, transcripts.txt, etc.)
      2. Parquet shards (train-*.parquet) containing audio and text
    """
    items = []
    root_dir = Path(root_dir)

    # 1. Check for existing CSV / TSV metadata first (e.g. metadata.tsv / metadata.csv)
    candidates = [
        root_dir / "metadata.tsv",
        root_dir / "metadata.csv",
        root_dir / "transcripts.txt"
    ]
    manifest = next((c for c in candidates if c.exists()), None)
    if not manifest:
        csvs = list(root_dir.glob("*.csv")) + list(root_dir.glob("*.tsv"))
        if csvs:
            manifest = csvs[0]

    if manifest and manifest.exists():
        logger.info("Found existing manifest at %s. Reading entries...", manifest)
        delimiter = "\t" if manifest.suffix == ".tsv" else "|"
        with open(manifest, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for row in reader:
                if not row or row[0].startswith("#") or len(row) < 2:
                    continue
                # Skip header
                if row[0].lower() in ("audio_filepath", "path", "wav_path", "audio", "file"):
                    continue
                wav_rel, text = row[0].strip(), row[1].strip()
                spk = row[2].strip() if len(row) > 2 else "ivr_spk"
                wav_path = root_dir / wav_rel
                if not wav_path.exists():
                    wav_path = root_dir / Path(wav_rel).name
                if wav_path.exists() and text:
                    items.append((text, str(wav_path), f"hi_ivr_{spk}"))

        if items:
            logger.info("Loaded %d utterances from manifest %s.", len(items), manifest.name)
            return items

    # 2. Check for Parquet shards if no manifest found
    parquet_files = sorted(root_dir.rglob("*.parquet"))
    if parquet_files:
        logger.info("Found %d Parquet shards in %s. Parsing with PyArrow...", len(parquet_files), root_dir)
        try:
            import pyarrow.parquet as pq
            extract_dir = root_dir / "extracted_wavs"
            extract_dir.mkdir(parents=True, exist_ok=True)

            total_sec = 0.0
            max_sec = (max_hours * 3600.0) if max_hours else float("inf")

            for p_file in parquet_files:
                pf = pq.ParquetFile(p_file)
                schema_names = pf.schema_arrow.names
                text_col = next((c for c in ["text", "normalized", "normalized_text", "transcription", "sentence"] if c in schema_names), None)
                spk_col = next((c for c in ["speaker_id", "speaker", "client_id"] if c in schema_names), None)
                audio_col = next((c for c in ["audio", "wav", "audio_filepath"] if c in schema_names), None)

                if not text_col or not audio_col:
                    continue

                needed_cols = [c for c in [text_col, spk_col, audio_col] if c]
                table = pf.read(columns=needed_cols)
                df = table.to_pydict()

                num_rows = len(df[text_col])
                for idx in range(num_rows):
                    text = str(df[text_col][idx] or "").strip()
                    spk = str(df[spk_col][idx] if spk_col else "ivr_spk").strip()
                    audio_entry = df[audio_col][idx]

                    if isinstance(audio_entry, dict) and "bytes" in audio_entry:
                        audio_bytes = audio_entry["bytes"]
                        audio_stem = hashlib.md5(f"{p_file.name}_{idx}_{text}".encode()).hexdigest()
                        wav_dest = extract_dir / f"{audio_stem}.wav"
                        if not wav_dest.exists():
                            with open(wav_dest, "wb") as wf:
                                wf.write(audio_bytes)
                        items.append((text, str(wav_dest), f"hi_ivr_{spk}"))
                    elif isinstance(audio_entry, str):
                        wav_p = root_dir / audio_entry
                        if wav_p.exists():
                            items.append((text, str(wav_p), f"hi_ivr_{spk}"))

                    total_sec += 4.5
                    if total_sec >= max_sec:
                        break
                if total_sec >= max_sec:
                    break

            if items:
                logger.info("Extracted/parsed %d utterances from Parquet.", len(items))
                return items
        except Exception as exc:
            logger.warning("Failed parsing Parquet directly: %s. Falling back...", exc)

    return items


def parse_common_voice_hindi(root_dir: Path) -> list[tuple[str, str, str]]:
    """Parses Common Voice validated.tsv with clips/ directory."""
    items = []
    root_dir = Path(root_dir)
    tsv_path = root_dir / "validated.tsv"
    clips_dir = root_dir / "clips"
    if not tsv_path.exists() or not clips_dir.exists():
        return items

    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            clip = row.get("path", "")
            text = row.get("sentence", "").strip()
            client_id = row.get("client_id", "cv_unknown")[:10]
            wav_path = clips_dir / clip
            if wav_path.exists() and text:
                items.append((text, str(wav_path), f"hi_cv_{client_id}"))

    return items


def parse_libritts_r(root_dir: Path, target_hours: float = 60.0) -> list[tuple[str, str, str]]:
    """
    Parses LibriTTS-R English directory (*.normalized.txt + *.wav).
    Subsamples up to target_hours.
    """
    items = []
    root_dir = Path(root_dir)
    max_sec = target_hours * 3600.0
    accumulated_sec = 0.0

    for txt_file in root_dir.rglob("*.normalized.txt"):
        wav_file = txt_file.with_name(txt_file.stem.replace(".normalized", "") + ".wav")
        if not wav_file.exists():
            continue

        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            speaker_id = txt_file.parent.parent.name
            items.append((text, str(wav_file), f"en_ltts_{speaker_id}"))
            accumulated_sec += 4.5
            if accumulated_sec >= max_sec:
                break
        except Exception:
            continue

    return items


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 2 dataset preparation for piper-plus (hi + en).")
    parser.add_argument("--indicvoices-r", type=Path, required=True, help="IndicVoices-R Hindi root directory")
    parser.add_argument("--cv-hi", type=Path, default=None, help="Optional Common Voice Hindi directory")
    parser.add_argument("--en-libritts", type=Path, required=True, help="LibriTTS-R English root directory")
    parser.add_argument("--output-dir", type=Path, required=True, help="Destination directory for Phase 2 outputs")
    parser.add_argument("--sample-rate", type=int, default=TARGET_SR, help="Target sample rate (default 22050)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel worker processes")
    parser.add_argument("--gpu-spec-device", type=str, default=None, help="Device for batch STFT (e.g. 'cuda:0' or 'cpu')")
    parser.add_argument("--en-hours", type=float, default=60.0, help="Max English hours to subsample")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.output_dir / "cache" / str(args.sample_rate)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1. Phoneme Map & Inventory Verification
    id_map = get_phoneme_id_map("hi")
    verify_inventory(id_map)

    # 2. Ingest Hindi
    logger.info("Discovering Hindi entries...")
    hi_entries = parse_indicvoices_r(args.indicvoices_r)
    if args.cv_hi and args.cv_hi.exists():
        cv_entries = parse_common_voice_hindi(args.cv_hi)
        hi_entries.extend(cv_entries)
        logger.info("Loaded Common Voice Hindi: %d clips", len(cv_entries))
    logger.info("Total Hindi candidate utterances: %d", len(hi_entries))

    # 3. Ingest English
    logger.info("Discovering English entries...")
    en_entries = parse_libritts_r(args.en_libritts, target_hours=args.en_hours)
    logger.info("Total English candidate utterances: %d", len(en_entries))

    # 4. Phonemization
    hi_phonemized, hi_drops = phonemize_dataset(
        hi_entries, "hi", LANGUAGE_ID_MAP["hi"], id_map, workers=args.workers
    )
    en_phonemized, en_drops = phonemize_dataset(
        en_entries, "en", LANGUAGE_ID_MAP["en"], id_map, workers=args.workers
    )

    all_phonemized = hi_phonemized + en_phonemized
    all_wavs = list({p["wav_path"] for p in all_phonemized})

    # 5. Audio Normalization & Spectrogram Generation
    audio_map = cache_audio_parallel(
        all_wavs,
        cache_dir=cache_dir,
        sample_rate=args.sample_rate,
        workers=args.workers,
        gpu_spec_device=args.gpu_spec_device,
    )

    # 6. Speaker ID Mapping (Dense integers starting at 0: Hindi first, then English)
    speaker_map: dict[str, int] = {}
    current_spk_id = 0

    hi_spks = sorted({p["speaker_id_str"] for p in hi_phonemized})
    for spk in hi_spks:
        speaker_map[spk] = current_spk_id
        current_spk_id += 1

    en_spks = sorted({p["speaker_id_str"] for p in en_phonemized})
    for spk in en_spks:
        if spk not in speaker_map:
            speaker_map[spk] = current_spk_id
            current_spk_id += 1

    # 7. Assemble Dataset Rows
    records = []
    hours = {"hi": 0.0, "en": 0.0}
    hi_rows_185_plus = 0
    max_id_overall = 0
    max_id_hi = 0

    for item in all_phonemized:
        wav_k = item["wav_path"]
        if wav_k not in audio_map:
            continue

        norm_p, spec_p, duration = audio_map[wav_k]
        spk_name = item["speaker_id_str"]
        spk_id = speaker_map[spk_name]
        lang = item["language"]
        p_ids = item["phoneme_ids"]

        max_in_utt = max(p_ids) if p_ids else 0
        max_id_overall = max(max_id_overall, max_in_utt)
        if lang == "hi":
            max_id_hi = max(max_id_hi, max_in_utt)
            if any(pid >= 185 for pid in p_ids):
                hi_rows_185_plus += 1

        hours[lang] += duration / 3600.0

        records.append({
            "text": item["text"],
            "audio_path": wav_k,
            "speaker": spk_name,
            "speaker_id": spk_id,
            "language": lang,
            "language_id": item["language_id"],
            "phonemes": item["phonemes"],
            "phoneme_ids": p_ids,
            "prosody_features": item["prosody_features"],
            "audio_norm_path": norm_p,
            "audio_spec_path": spec_p,
            "duration": duration,
        })

    # 8. Write dataset.jsonl
    jsonl_path = args.output_dir / "dataset.jsonl"
    logger.info("Writing %d records to %s...", len(records), jsonl_path)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 9. Write config.json
    config_path = args.output_dir / "config.json"
    config_payload = {
        "dataset": "hindi-english-hi-en",
        "audio": {"sample_rate": args.sample_rate, "quality": "medium"},
        "language": {"code": "hi-en"},
        "inference": {"noise_scale": 0.4, "length_scale": 1.0, "noise_w": 0.5},
        "num_symbols": EXPECTED_SYMBOLS,
        "num_speakers": len(speaker_map),
        "speaker_id_map": speaker_map,
        "num_languages": len(LANGUAGE_ID_MAP),
        "language_id_map": LANGUAGE_ID_MAP,
        "phoneme_type": "multilingual",
        "phoneme_map": {},
        "phoneme_id_map": id_map,
        "prosody_num_symbols": 11,
        "prosody_id_map": {str(i): [i] for i in range(11)},
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2, ensure_ascii=False)

    # 10. Write stats.json
    stats_path = args.output_dir / "stats.json"
    combined_drops = dict(Counter(hi_drops) + Counter(en_drops))
    stats_payload = {
        "hours": {
            "hi": round(hours["hi"], 2),
            "en": round(hours["en"], 2),
            "total": round(hours["hi"] + hours["en"], 2),
        },
        "utterance_counts": {
            "hi": sum(1 for r in records if r["language"] == "hi"),
            "en": sum(1 for r in records if r["language"] == "en"),
            "total": len(records),
        },
        "speaker_counts": {
            "hi": len(hi_spks),
            "en": len(en_spks),
            "total": len(speaker_map),
        },
        "max_phoneme_id_overall": max_id_overall,
        "max_phoneme_id_hi": max_id_hi,
        "hindi_rows_with_new_ids_185_plus": hi_rows_185_plus,
        "dropped_reasons": combined_drops,
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats_payload, f, indent=2)

    # 11. Write RECIPE.md
    recipe_path = args.output_dir / "RECIPE.md"
    recipe_content = f"""# Phase 2 Dataset Recipe: Hindi + English (hi-en)

Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Sources & Licenses
- **Hindi (Primary):** IndicVoices-R Hindi subset ([ai4bharat/indicvoices_r](https://huggingface.co/datasets/ai4bharat/indicvoices_r)) — **CC-BY-4.0**
- **Hindi (Secondary, optional):** Mozilla Common Voice Hindi — **CC0**
- **English:** LibriTTS-R English — **CC-BY-4.0 / Public Domain**
- **Commercial safety check:** No non-commercial datasets (e.g. OpenSLR 118 / IIT-M IndicTTS-R NC) were used.

## Specifications
- **Sample Rate:** {args.sample_rate} Hz (soxr MQ resampled)
- **Acoustic Spectrogram:** Linear STFT (n_fft={FILTER_LENGTH}, hop={HOP_LENGTH}, win={WIN_LENGTH})
- **Symbols Inventory:** {EXPECTED_SYMBOLS} symbols (SHA256: `{EXPECTED_SHA256}`)
- **Language IDs:** Hindi=0, English=1

## Dataset Statistics
- **Hindi Hours:** {hours['hi']:.2f} h across {len(hi_spks)} speakers
- **English Hours:** {hours['en']:.2f} h across {len(en_spks)} speakers
- **Total Utterances:** {len(records)}
- **Hindi Rows with IDs >= 185:** {hi_rows_185_plus}
- **Max Phoneme ID (Overall / Hindi):** {max_id_overall} / {max_id_hi}
"""
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(recipe_content)

    logger.info("Phase 2 dataset preparation finished successfully!")
    logger.info(
        "Summary: Hindi=%.2fh (%d utts), English=%.2fh (%d utts), Total Speakers=%d",
        hours["hi"], stats_payload["utterance_counts"]["hi"],
        hours["en"], stats_payload["utterance_counts"]["en"],
        len(speaker_map)
    )


if __name__ == "__main__":
    main()