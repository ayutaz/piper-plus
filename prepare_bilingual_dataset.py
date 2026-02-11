#!/usr/bin/env python3
"""Prepare bilingual (JA+EN) dataset by merging existing JA dataset with LJSpeech EN data.

Usage:
    uv run python prepare_bilingual_dataset.py \
        --ja-dataset /data/piper/dataset-moe-speech-20speakers-v2/dataset.jsonl \
        --en-input-dir /data/piper/ljspeech/LJSpeech-1.1 \
        --output-dir /data/piper/dataset-bilingual-ja-en \
        --sample-rate 22050 \
        --max-en-utterances 13000 \
        --workers 8
"""

import argparse
import csv
import json
import logging
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

_LOGGER = logging.getLogger("prepare_bilingual")


def get_bilingual_id_map():
    from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map as _get
    return _get()


def get_japanese_id_map():
    from piper_train.phonemize.jp_id_map import get_japanese_id_map as _get
    return _get()


def remap_ja_phoneme_ids(
    old_ids: list[int],
    old_id_map: dict[str, list[int]],
    new_id_map: dict[str, list[int]],
) -> list[int]:
    """Remap phoneme IDs from old JA id_map to unified bilingual id_map."""
    # Build reverse map: old_id -> symbol
    old_id_to_symbol: dict[int, str] = {}
    for symbol, ids in old_id_map.items():
        for id_ in ids:
            old_id_to_symbol[id_] = symbol

    new_ids = []
    for old_id in old_ids:
        symbol = old_id_to_symbol.get(old_id)
        if symbol is None:
            _LOGGER.warning("Unknown old ID: %d, keeping as-is", old_id)
            new_ids.append(old_id)
            continue
        if symbol in new_id_map:
            new_ids.extend(new_id_map[symbol])
        else:
            _LOGGER.warning("Symbol '%s' not in bilingual map", symbol)
            new_ids.append(0)  # pad
    return new_ids


def _add_inter_phoneme_padding(
    phoneme_ids: list[int],
    prosody_features: list[dict | None],
    bilingual_id_map: dict[str, list[int]],
) -> tuple[list[int], list[dict | None]]:
    """Add inter-phoneme padding and BOS/EOS to match inference-time pattern.

    The original JA data has BOS (^=1) at start and EOS ($=2 or ?=3) at end,
    but no inter-phoneme padding (ID 0). This function:
    1. Strips existing BOS/EOS
    2. Inserts pad (ID 0) between every phoneme
    3. Wraps with BOS + pad + ... + EOS (matching BilingualPhonemizer.post_process_ids)
    """
    pad_id = bilingual_id_map.get("_", [0])[0]
    bos_ids = bilingual_id_map.get("^", [1])
    eos_ids_dollar = bilingual_id_map.get("$", [2])
    eos_ids_question = bilingual_id_map.get("?", [3])
    eos_id_set = set(eos_ids_dollar + eos_ids_question)

    if not phoneme_ids:
        return phoneme_ids, prosody_features

    # Strip existing BOS (first element if it matches ^)
    start = 0
    if phoneme_ids[0] in bos_ids:
        start = 1

    # Strip existing EOS (last element if it matches $ or ?)
    end = len(phoneme_ids)
    eos_symbol_ids = []
    if phoneme_ids[-1] in eos_id_set:
        eos_symbol_ids = [phoneme_ids[-1]]
        end -= 1

    core_ids = phoneme_ids[start:end]
    core_prosody = prosody_features[start:end]

    # Insert pad between every phoneme ID, skipping existing padding
    padded_ids: list[int] = []
    padded_prosody: list[dict | None] = []
    for pid, pf in zip(core_ids, core_prosody):
        padded_ids.append(pid)
        padded_prosody.append(pf)
        if pid != pad_id:  # Don't add padding after existing padding
            padded_ids.append(pad_id)
            padded_prosody.append(None)

    # Wrap with BOS + pad + ... + EOS
    final_ids = bos_ids + [pad_id] + padded_ids
    final_prosody = [None] * (len(bos_ids) + 1) + padded_prosody
    if eos_symbol_ids:
        final_ids.extend(eos_symbol_ids)
        final_prosody.extend([None] * len(eos_symbol_ids))
    else:
        final_ids.extend(eos_ids_dollar)
        final_prosody.extend([None] * len(eos_ids_dollar))

    return final_ids, final_prosody


def process_ja_dataset(
    ja_jsonl_path: Path,
    bilingual_id_map: dict[str, list[int]],
    ja_speaker_offset: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    """Read existing JA dataset and remap to bilingual ID space."""
    ja_id_map = get_japanese_id_map()

    utterances = []
    speaker_ids_seen: dict[str, int] = {}
    skipped = 0

    with open(ja_jsonl_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                utt = json.loads(line)
            except json.JSONDecodeError:
                _LOGGER.warning("Skipping invalid JSON at line %d", line_no + 1)
                skipped += 1
                continue

            # Remap phoneme_ids
            old_ids = utt.get("phoneme_ids", [])
            if not old_ids:
                skipped += 1
                continue
            new_ids = remap_ja_phoneme_ids(old_ids, ja_id_map, bilingual_id_map)

            # Add inter-phoneme padding to match inference-time pattern
            prosody = utt.get("prosody_features", [None] * len(new_ids))
            new_ids, prosody = _add_inter_phoneme_padding(
                new_ids, prosody, bilingual_id_map
            )

            # Track speaker
            speaker = utt.get("speaker", "unknown")
            if speaker not in speaker_ids_seen:
                speaker_ids_seen[speaker] = len(speaker_ids_seen) + ja_speaker_offset

            utt["phoneme_ids"] = new_ids
            utt["prosody_features"] = prosody
            utt["speaker_id"] = speaker_ids_seen[speaker]
            utt["language_id"] = 0  # Japanese
            utterances.append(utt)

    _LOGGER.info(
        "Loaded %d JA utterances (%d skipped), %d speakers",
        len(utterances), skipped, len(speaker_ids_seen),
    )
    return utterances, speaker_ids_seen


def _cache_audio_worker(args):
    """Worker function for parallel audio caching."""
    wav_path, cache_dir, sample_rate = args
    from piper_train.norm_audio import cache_norm_audio, make_silence_detector
    detector = make_silence_detector()
    audio_norm_path, audio_spec_path = cache_norm_audio(
        wav_path, cache_dir, detector, sample_rate
    )
    return str(wav_path), str(audio_norm_path), str(audio_spec_path)


# -- Parallel EN phonemization worker --

_phonemize_worker_state: dict = {}


def _init_phonemize_worker(bilingual_id_map: dict[str, list[int]]):
    """Initialize BilingualPhonemizer once per worker process."""
    from piper_train.phonemize.bilingual import BilingualPhonemizer
    _phonemize_worker_state["phonemizer"] = BilingualPhonemizer(["ja", "en"])
    _phonemize_worker_state["id_map"] = bilingual_id_map


def _phonemize_en_worker(args: tuple[str, str, str]) -> dict:
    """Phonemize a single EN utterance in a worker process."""
    filename, text, wav_path_str = args
    phonemizer = _phonemize_worker_state["phonemizer"]
    id_map = _phonemize_worker_state["id_map"]

    try:
        phonemes, prosody_list = phonemizer.phonemize_with_prosody(text)

        phoneme_ids = []
        prosody_features = []
        missing = []
        for ph, pr in zip(phonemes, prosody_list, strict=True):
            if ph in id_map:
                ids = id_map[ph]
                phoneme_ids.extend(ids)
                for _ in ids:
                    if pr is not None:
                        prosody_features.append({"a1": pr.a1, "a2": pr.a2, "a3": pr.a3})
                    else:
                        prosody_features.append(None)
            else:
                missing.append(ph)

        phoneme_ids, prosody_features = phonemizer.post_process_ids(
            phoneme_ids, prosody_features, id_map
        )

        return {
            "filename": filename,
            "text": text,
            "wav_path": wav_path_str,
            "phonemes": phonemes,
            "phoneme_ids": phoneme_ids,
            "prosody_features": prosody_features,
            "missing": missing,
        }
    except Exception as e:
        return {"filename": filename, "error": str(e)}


def process_en_dataset(
    en_input_dir: Path,
    bilingual_id_map: dict[str, list[int]],
    sample_rate: int,
    cache_dir: Path,
    en_speaker_id: int,
    max_utterances: int | None = None,
    workers: int = 1,
) -> list[dict]:
    """Process LJSpeech English dataset with bilingual phonemizer."""
    metadata_path = en_input_dir / "metadata.csv"
    wav_dir = en_input_dir / "wavs"

    if not metadata_path.exists():
        _LOGGER.error("metadata.csv not found at %s", metadata_path)
        return []

    # Phase 1: Parse metadata and phonemize (parallel)
    missing_phonemes: Counter[str] = Counter()
    phonemized: list[dict] = []
    skipped_parse = 0

    with open(metadata_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        rows = list(reader)

    if max_utterances and max_utterances < len(rows):
        rows = rows[:max_utterances]

    # Parse rows and filter missing wavs
    tasks: list[tuple[str, str, str]] = []
    for row in rows:
        if len(row) < 3:
            if len(row) >= 2:
                filename, text = row[0], row[-1]
            else:
                skipped_parse += 1
                continue
        else:
            filename, _, text = row[0], row[1], row[2]

        wav_path = wav_dir / f"{filename}.wav"
        if not wav_path.exists():
            skipped_parse += 1
            continue
        tasks.append((filename, text, str(wav_path)))

    _LOGGER.info("Phonemizing %d EN utterances with %d workers...", len(tasks), workers)

    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_phonemize_worker,
            initargs=(bilingual_id_map,),
        ) as executor:
            futures = {executor.submit(_phonemize_en_worker, t): t[0] for t in tasks}
            done = 0
            for future in as_completed(futures):
                result = future.result()
                done += 1
                if "error" in result:
                    _LOGGER.warning("Failed to phonemize %s: %s", result["filename"], result["error"])
                    skipped_parse += 1
                else:
                    if result["missing"]:
                        for ph in result["missing"]:
                            missing_phonemes[ph] += 1
                    if len(result["phoneme_ids"]) == 0:
                        skipped_parse += 1
                    else:
                        phonemized.append({
                            "text": result["text"],
                            "wav_path": result["wav_path"],
                            "phonemes": result["phonemes"],
                            "phoneme_ids": result["phoneme_ids"],
                            "prosody_features": result["prosody_features"],
                        })
                if done % 1000 == 0:
                    _LOGGER.info("Phonemized %d/%d EN utterances", done, len(tasks))
    else:
        from piper_train.phonemize.bilingual import BilingualPhonemizer
        phonemizer = BilingualPhonemizer(["ja", "en"])
        for task_idx, (filename, text, wav_path_str) in enumerate(tasks):
            try:
                phonemes, prosody_list = phonemizer.phonemize_with_prosody(text)
                phoneme_ids = []
                prosody_features = []
                for ph, pr in zip(phonemes, prosody_list, strict=True):
                    if ph in bilingual_id_map:
                        ids = bilingual_id_map[ph]
                        phoneme_ids.extend(ids)
                        for _ in ids:
                            if pr is not None:
                                prosody_features.append({"a1": pr.a1, "a2": pr.a2, "a3": pr.a3})
                            else:
                                prosody_features.append(None)
                    else:
                        missing_phonemes[ph] += 1
                phoneme_ids, prosody_features = phonemizer.post_process_ids(
                    phoneme_ids, prosody_features, bilingual_id_map
                )
                if len(phoneme_ids) == 0:
                    skipped_parse += 1
                    continue
                phonemized.append({
                    "text": text,
                    "wav_path": wav_path_str,
                    "phonemes": phonemes,
                    "phoneme_ids": phoneme_ids,
                    "prosody_features": prosody_features,
                })
            except Exception as e:
                _LOGGER.warning("Failed to phonemize %s: %s", filename, e)
                skipped_parse += 1
            if (task_idx + 1) % 1000 == 0:
                _LOGGER.info("Phonemized %d/%d EN utterances", task_idx + 1, len(tasks))

    if missing_phonemes:
        for ph, count in missing_phonemes.most_common(10):
            _LOGGER.warning("Missing EN phoneme: '%s' (%d times)", ph, count)

    _LOGGER.info("Phonemized %d EN utterances (%d skipped)", len(phonemized), skipped_parse)

    # Phase 2: Audio normalization (slow, parallel)
    # First, check which files already have cached audio
    from hashlib import sha256 as _sha256

    audio_map: dict[str, tuple[str, str]] = {}
    need_caching: list[tuple[str, str, int]] = []

    for p in phonemized:
        wav_path_str = p["wav_path"]
        audio_cache_id = _sha256(str(Path(wav_path_str).absolute()).encode()).hexdigest()
        norm_path = cache_dir / f"{audio_cache_id}.pt"
        spec_path = cache_dir / f"{audio_cache_id}.spec.pt"
        if norm_path.exists() and spec_path.exists():
            audio_map[wav_path_str] = (str(norm_path), str(spec_path))
        else:
            need_caching.append((wav_path_str, str(cache_dir), sample_rate))

    _LOGGER.info(
        "Audio cache: %d already cached, %d need processing",
        len(audio_map), len(need_caching),
    )

    if need_caching:
        _LOGGER.info("Caching audio for %d EN utterances with %d workers...", len(need_caching), workers)
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_cache_audio_worker, a): i for i, a in enumerate(need_caching)}
                done = 0
                for future in as_completed(futures):
                    try:
                        wav_str, norm_str, spec_str = future.result()
                        audio_map[wav_str] = (norm_str, spec_str)
                    except Exception as e:
                        _LOGGER.warning("Audio cache failed: %s", e)
                    done += 1
                    if done % 1000 == 0:
                        _LOGGER.info("Cached audio %d/%d", done, len(need_caching))
        else:
            from piper_train.norm_audio import cache_norm_audio, make_silence_detector
            detector = make_silence_detector()
            for i, (wav_path_str, _, sr) in enumerate(need_caching):
                try:
                    norm_path, spec_path = cache_norm_audio(wav_path_str, cache_dir, detector, sr)
                    audio_map[wav_path_str] = (str(norm_path), str(spec_path))
                except Exception as e:
                    _LOGGER.warning("Audio cache failed for %s: %s", wav_path_str, e)
                if (i + 1) % 1000 == 0:
                    _LOGGER.info("Cached audio %d/%d", i + 1, len(need_caching))

    # Phase 3: Assemble utterances
    utterances = []
    skipped_audio = 0
    for p in phonemized:
        wav_key = p["wav_path"]
        if wav_key not in audio_map:
            skipped_audio += 1
            continue
        norm_path, spec_path = audio_map[wav_key]
        utterances.append({
            "text": p["text"],
            "audio_path": wav_key,
            "speaker": "ljspeech",
            "speaker_id": en_speaker_id,
            "language_id": 1,
            "phonemes": p["phonemes"],
            "phoneme_ids": p["phoneme_ids"],
            "prosody_ids": [],
            "prosody_features": p["prosody_features"],
            "audio_norm_path": norm_path,
            "audio_spec_path": spec_path,
            "f0_path": None,
        })

    _LOGGER.info(
        "Loaded %d EN utterances (%d parse-skipped, %d audio-skipped)",
        len(utterances), skipped_parse, skipped_audio,
    )
    return utterances


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Prepare bilingual JA+EN dataset")
    parser.add_argument("--ja-dataset", required=True, help="Path to JA dataset.jsonl")
    parser.add_argument("--en-input-dir", required=True, help="Path to LJSpeech-1.1 directory")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument("--max-en-utterances", type=int, default=13000,
                        help="Max EN utterances (default: 13000, ~24h of LJSpeech)")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache" / str(args.sample_rate)
    cache_dir.mkdir(parents=True, exist_ok=True)

    bilingual_id_map = get_bilingual_id_map()
    _LOGGER.info("Bilingual ID map: %d symbols", len(bilingual_id_map))

    # Process JA
    ja_utts, ja_speakers = process_ja_dataset(
        Path(args.ja_dataset), bilingual_id_map, ja_speaker_offset=0
    )

    # EN speaker ID = next after JA speakers
    en_speaker_id = len(ja_speakers)
    _LOGGER.info("EN speaker ID: %d", en_speaker_id)

    # Process EN
    en_utts = process_en_dataset(
        Path(args.en_input_dir),
        bilingual_id_map,
        args.sample_rate,
        cache_dir,
        en_speaker_id,
        max_utterances=args.max_en_utterances,
        workers=args.workers,
    )

    # Merge and write
    all_utts = ja_utts + en_utts
    _LOGGER.info("Total utterances: %d (JA=%d, EN=%d)", len(all_utts), len(ja_utts), len(en_utts))

    # Write dataset.jsonl
    dataset_path = output_dir / "dataset.jsonl"
    with open(dataset_path, "w", encoding="utf-8") as f:
        for utt in all_utts:
            json.dump(utt, f, ensure_ascii=True)
            f.write("\n")
    _LOGGER.info("Wrote %s", dataset_path)

    # Write config.json
    num_speakers = len(ja_speakers) + 1  # +1 for LJSpeech
    speaker_id_map = {**{s: sid for s, sid in ja_speakers.items()}, "ljspeech": en_speaker_id}

    config = {
        "dataset": "bilingual-ja-en",
        "audio": {"sample_rate": args.sample_rate, "quality": "medium"},
        "language": {"code": "ja-en"},
        "inference": {"noise_scale": 0.667, "length_scale": 1, "noise_w": 0.8},
        "phoneme_type": "bilingual",
        "phoneme_map": {},
        "phoneme_id_map": bilingual_id_map,
        "num_symbols": len(bilingual_id_map),
        "num_speakers": num_speakers,
        "speaker_id_map": speaker_id_map,
        "num_languages": 2,
        "language_id_map": {"ja": 0, "en": 1},
        "prosody_num_symbols": 11,
        "prosody_id_map": {str(i): [i] for i in range(11)},
    }

    config_path = output_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=True, indent=4)
    _LOGGER.info("Wrote %s (speakers=%d, symbols=%d, languages=2)", config_path, num_speakers, len(bilingual_id_map))


if __name__ == "__main__":
    main()
