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
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256 as _sha256
from pathlib import Path

from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
from piper_plus_g2p.multilingual import MultilingualPhonemizer

from piper_train.norm_audio import cache_norm_audio, make_silence_detector


_LOGGER = logging.getLogger("prepare_bilingual")


def get_bilingual_id_map():
    return get_phoneme_id_map("ja-en")


def get_japanese_id_map():
    return get_phoneme_id_map("ja")


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
    3. Wraps with BOS + pad + ... + EOS (matching MultilingualPhonemizer.post_process_ids)
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
    for pid, pf in zip(core_ids, core_prosody, strict=True):
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
    sample_rate: int,
    cache_dir: Path,
    ja_speaker_offset: int = 0,
    workers: int = 1,
    already_bilingual: bool = False,
) -> tuple[list[dict], dict[str, int]]:
    """Process JA dataset with bilingual phonemizer and cache generation.

    Args:
        already_bilingual: If True, the input dataset is already a bilingual dataset
            (e.g., dataset-bilingual-ja-en-enhanced-fixed). In this mode:
            - Only language_id==0 (JA) entries are processed
            - Phoneme IDs are used as-is (already in bilingual space, already padded)
            - audio_norm_path / audio_spec_path are read directly from the entry
    """
    if already_bilingual:
        return _process_ja_from_bilingual_dataset(ja_jsonl_path, ja_speaker_offset)

    ja_id_map = get_japanese_id_map()

    # ===== Phase 1: Phoneme remapping =====
    phonemized: list[dict] = []
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

            # Remap phoneme_ids to bilingual space
            old_ids = utt.get("phoneme_ids", [])
            if not old_ids:
                skipped += 1
                continue
            new_ids = remap_ja_phoneme_ids(old_ids, ja_id_map, bilingual_id_map)

            # Add inter-phoneme padding
            prosody = utt.get("prosody_features", [None] * len(new_ids))
            new_ids, prosody = _add_inter_phoneme_padding(
                new_ids, prosody, bilingual_id_map
            )

            # Track speaker
            speaker = utt.get("speaker", "unknown")
            if speaker not in speaker_ids_seen:
                speaker_ids_seen[speaker] = len(speaker_ids_seen) + ja_speaker_offset

            # Store intermediate result
            phonemized.append(
                {
                    "text": utt.get("text", ""),
                    "wav_path": utt.get("audio_path", ""),
                    "speaker": speaker,
                    "speaker_id": speaker_ids_seen[speaker],
                    "phoneme_ids": new_ids,
                    "prosody_features": prosody,
                }
            )

    _LOGGER.info(
        "Remapped %d JA utterances (%d skipped), %d speakers",
        len(phonemized),
        skipped,
        len(speaker_ids_seen),
    )

    # ===== Phase 2: Audio normalization (parallel) =====
    audio_map: dict[str, tuple[str, str]] = {}
    need_caching: list[tuple[str, str, int]] = []

    for p in phonemized:
        wav_path_str = p["wav_path"]
        if not wav_path_str or not Path(wav_path_str).exists():
            _LOGGER.warning("Missing wav file: %s", wav_path_str)
            continue

        audio_cache_id = _sha256(
            str(Path(wav_path_str).absolute()).encode()
        ).hexdigest()
        norm_path = cache_dir / f"{audio_cache_id}.pt"
        spec_path = cache_dir / f"{audio_cache_id}.spec.pt"

        if norm_path.exists() and spec_path.exists():
            audio_map[wav_path_str] = (str(norm_path), str(spec_path))
        else:
            need_caching.append((wav_path_str, str(cache_dir), sample_rate))

    _LOGGER.info(
        "Audio cache: %d already cached, %d need processing",
        len(audio_map),
        len(need_caching),
    )

    if need_caching:
        _LOGGER.info(
            "Caching audio for %d JA utterances with %d workers...",
            len(need_caching),
            workers,
        )
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_cache_audio_worker, a): i
                    for i, a in enumerate(need_caching)
                }
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
            detector = make_silence_detector()
            for i, (wav_path_str, _, sr) in enumerate(need_caching):
                try:
                    norm_path, spec_path = cache_norm_audio(
                        wav_path_str, cache_dir, detector, sr
                    )
                    audio_map[wav_path_str] = (str(norm_path), str(spec_path))
                except Exception as e:
                    _LOGGER.warning("Audio cache failed for %s: %s", wav_path_str, e)
                if (i + 1) % 1000 == 0:
                    _LOGGER.info("Cached audio %d/%d", i + 1, len(need_caching))

    # ===== Phase 3: Assemble utterances =====
    utterances = []
    skipped_audio = 0
    for p in phonemized:
        wav_key = p["wav_path"]
        if wav_key not in audio_map:
            skipped_audio += 1
            continue
        norm_path, spec_path = audio_map[wav_key]
        utterances.append(
            {
                "text": p["text"],
                "audio_path": wav_key,
                "speaker": p["speaker"],
                "speaker_id": p["speaker_id"],
                "language_id": 0,  # Japanese
                "phonemes": [],
                "phoneme_ids": p["phoneme_ids"],
                "prosody_ids": [],
                "prosody_features": p["prosody_features"],
                "audio_norm_path": norm_path,
                "audio_spec_path": spec_path,
                "f0_path": None,
            }
        )

    _LOGGER.info(
        "Loaded %d JA utterances (%d audio-skipped), %d speakers",
        len(utterances),
        skipped_audio,
        len(speaker_ids_seen),
    )
    return utterances, speaker_ids_seen


def _process_ja_from_bilingual_dataset(
    jsonl_path: Path,
    ja_speaker_offset: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    """Read JA entries directly from an already-processed bilingual dataset.

    Used when --ja-already-bilingual is specified. Phoneme IDs and audio caches
    are already in the correct format; only language_id==0 entries are kept.
    Speaker IDs are reassigned starting from ja_speaker_offset.
    """
    utterances: list[dict] = []
    speaker_ids_seen: dict[str, int] = {}
    skipped = 0

    with open(jsonl_path, encoding="utf-8") as f:
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

            # Only JA entries
            if utt.get("language_id", 0) != 0:
                continue

            phoneme_ids = utt.get("phoneme_ids", [])
            if not phoneme_ids:
                skipped += 1
                continue

            norm_path = utt.get("audio_norm_path", "")
            spec_path = utt.get("audio_spec_path", "")
            if not norm_path or not Path(norm_path).exists():
                skipped += 1
                continue
            if not spec_path or not Path(spec_path).exists():
                skipped += 1
                continue

            speaker = utt.get("speaker", "unknown")
            if speaker not in speaker_ids_seen:
                speaker_ids_seen[speaker] = len(speaker_ids_seen) + ja_speaker_offset

            utterances.append(
                {
                    "text": utt.get("text", ""),
                    "audio_path": utt.get("audio_path", ""),
                    "speaker": speaker,
                    "speaker_id": speaker_ids_seen[speaker],
                    "language_id": 0,
                    "phonemes": utt.get("phonemes", []),
                    "phoneme_ids": phoneme_ids,
                    "prosody_ids": utt.get("prosody_ids", []),
                    "prosody_features": utt.get("prosody_features", []),
                    "audio_norm_path": norm_path,
                    "audio_spec_path": spec_path,
                    "f0_path": utt.get("f0_path"),
                }
            )

    _LOGGER.info(
        "Loaded %d JA utterances from bilingual dataset (%d skipped), %d speakers",
        len(utterances),
        skipped,
        len(speaker_ids_seen),
    )
    return utterances, speaker_ids_seen


def _cache_audio_worker(args):
    """Worker function for parallel audio caching."""
    wav_path, cache_dir, sample_rate = args
    from piper_train.norm_audio import (  # noqa: PLC0415
        cache_norm_audio,
        make_silence_detector,
    )

    detector = make_silence_detector()
    audio_norm_path, audio_spec_path = cache_norm_audio(
        wav_path, cache_dir, detector, sample_rate
    )
    return str(wav_path), str(audio_norm_path), str(audio_spec_path)


_CACHE_BATCH_SIZE = 10
_CACHE_BATCH_SIZE_FAST = 50  # Larger batches for energy VAD (CPU compute is negligible)


def _cache_audio_batch_worker(args):
    """Worker function for parallel audio caching - processes a batch of files.

    Initializes the VAD detector once per worker instead of once per file,
    reducing ONNX model loading overhead.
    """
    wav_paths, cache_dir, sample_rate = args
    from piper_train.norm_audio import (  # noqa: PLC0415
        cache_norm_audio,
        make_silence_detector,
    )

    detector = make_silence_detector()
    results = []
    for wav_path in wav_paths:
        try:
            audio_norm_path, audio_spec_path = cache_norm_audio(
                wav_path, cache_dir, detector, sample_rate
            )
            results.append((str(wav_path), str(audio_norm_path), str(audio_spec_path)))
        except Exception as e:
            results.append((str(wav_path), None, str(e)))
    return results


def _cache_audio_batch_worker_fast(args):
    """Fast worker using energy VAD + soxr (no Silero ONNX init overhead).

    ~7.7x faster than _cache_audio_batch_worker in parallel on NFS.
    Suitable for LibriTTS-R (pre-cleaned audio with virtually no silence).
    """
    wav_paths, cache_dir, sample_rate = args
    from piper_train.norm_audio import cache_norm_audio_fast  # noqa: PLC0415

    results = []
    for wav_path in wav_paths:
        try:
            norm_path, spec_path = cache_norm_audio_fast(
                wav_path, cache_dir, sample_rate
            )
            results.append((str(wav_path), str(norm_path), str(spec_path)))
        except Exception as e:
            results.append((str(wav_path), None, str(e)))
    return results


# -- Parallel EN phonemization worker --

_phonemize_worker_state: dict = {}


def _init_phonemize_worker(bilingual_id_map: dict[str, list[int]]):
    """Initialize MultilingualPhonemizer once per worker process."""
    from piper_plus_g2p.multilingual import MultilingualPhonemizer  # noqa: PLC0415

    _phonemize_worker_state["phonemizer"] = MultilingualPhonemizer(["ja", "en"])
    _phonemize_worker_state["id_map"] = bilingual_id_map


def _phonemize_en_worker(args: tuple[str, str, str, int]) -> dict:
    """Phonemize a single EN utterance in a worker process."""
    filename, text, wav_path_str, speaker_id = args
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
            "speaker_id": speaker_id,  # NEW
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
    en_speaker_id_offset: int,  # Changed: offset instead of fixed ID
    max_utterances: int | None = None,
    workers: int = 1,
    max_speakers: int | None = None,  # NEW: speaker count limit
    multi_speaker: bool = True,  # NEW: multi-speaker mode
    min_utterances_per_speaker: int = 0,  # NEW: minimum utterances per speaker filter
) -> tuple[list[dict], dict[str, int]]:  # Changed: also return speaker_id_map
    """Process English dataset with optional multi-speaker support.

    Args:
        en_input_dir: Path to LibriTTS-R directory (converted to LJSpeech format)
        bilingual_id_map: Unified bilingual phoneme ID map
        sample_rate: Audio sample rate
        cache_dir: Audio cache directory
        en_speaker_id_offset: Starting speaker ID (offset from JA speakers)
        max_utterances: Maximum utterances to process (None = all)
        workers: Number of parallel workers
        max_speakers: Maximum speakers to include (top N by utterance count)
        multi_speaker: Enable multi-speaker mode (extract speaker IDs from filenames)
        min_utterances_per_speaker: Minimum utterances per speaker (speakers below this are excluded)

    Returns:
        Tuple of (utterances list, speaker_id_map dict)
    """
    metadata_path = en_input_dir / "metadata.csv"
    wav_dir = en_input_dir / "wavs"

    if not metadata_path.exists():
        _LOGGER.error("metadata.csv not found at %s", metadata_path)
        return [], {}

    # ===== Phase 0: Speaker analysis (multi_speaker mode) =====
    speaker_counts: dict[str, int] = {}
    selected_speakers: set[str] = set()
    speaker_id_map: dict[str, int] = {}

    if multi_speaker:
        _LOGGER.info("Analyzing speakers in LibriTTS-R...")
        with open(metadata_path, encoding="utf-8") as f:
            f.readline()  # Skip header
            for line in f:
                parts = line.strip().split("|")
                if len(parts) < 2:
                    continue
                audio_filename = parts[0]
                # Extract speaker ID from filename: "{speaker_id}_{utterance_id}_...wav"
                speaker_id = audio_filename.split("_")[0]
                speaker_counts[speaker_id] = speaker_counts.get(speaker_id, 0) + 1

        # Sort speakers by utterance count (descending)
        sorted_speakers = sorted(
            speaker_counts.items(), key=lambda x: x[1], reverse=True
        )

        # Filter speakers with minimum utterance count
        if min_utterances_per_speaker > 0:
            before_filter = len(sorted_speakers)
            sorted_speakers = [
                (spk, cnt)
                for spk, cnt in sorted_speakers
                if cnt >= min_utterances_per_speaker
            ]
            _LOGGER.info(
                "Filtered speakers with < %d utterances: %d → %d speakers",
                min_utterances_per_speaker,
                before_filter,
                len(sorted_speakers),
            )

        # Select top N speakers
        n_speakers = max_speakers if max_speakers else len(sorted_speakers)
        n_speakers = min(n_speakers, len(sorted_speakers))
        selected_speakers = {spk for spk, _ in sorted_speakers[:n_speakers]}

        # Create speaker ID mapping: original_speaker → sequential_id
        for i, (spk, _count) in enumerate(sorted_speakers[:n_speakers]):
            speaker_id_map[spk] = en_speaker_id_offset + i

        _LOGGER.info(
            "Selected top %d speakers (total available: %d)",
            len(selected_speakers),
            len(speaker_counts),
        )
        _LOGGER.info(
            "Speaker utterance range: %d-%d",
            sorted_speakers[n_speakers - 1][1]
            if n_speakers <= len(sorted_speakers)
            else 0,
            sorted_speakers[0][1],
        )
    else:
        # Single speaker mode (backward compatibility)
        speaker_id_map["ljspeech"] = en_speaker_id_offset

    # ===== Phase 1: Parse metadata and phonemize (parallel) =====
    missing_phonemes: Counter[str] = Counter()
    phonemized: list[dict] = []
    skipped_parse = 0
    skipped_speaker = 0  # NEW

    with open(metadata_path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="|")
        rows = list(reader)

    # Parse rows and filter by speaker + missing wavs
    tasks: list[
        tuple[str, str, str, int]
    ] = []  # (filename, text, wav_path, speaker_id)
    for row in rows:
        if max_utterances and len(tasks) >= max_utterances:
            break

        if len(row) < 3:
            if len(row) >= 2:
                filename, text = row[0], row[-1]
            else:
                skipped_parse += 1
                continue
        else:
            filename, _, text = row[0], row[1], row[2]

        # Multi-speaker filtering
        if multi_speaker:
            speaker_id_str = filename.split("_")[0]
            if speaker_id_str not in selected_speakers:
                skipped_speaker += 1
                continue
            speaker_id = speaker_id_map[speaker_id_str]
        else:
            speaker_id = en_speaker_id_offset

        # Handle both formats: with and without .wav extension
        if filename.endswith(".wav"):
            wav_path = wav_dir / filename
        else:
            wav_path = wav_dir / f"{filename}.wav"

        if not wav_path.exists():
            skipped_parse += 1
            continue
        tasks.append((filename, text, str(wav_path), speaker_id))

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
                    _LOGGER.warning(
                        "Failed to phonemize %s: %s",
                        result["filename"],
                        result["error"],
                    )
                    skipped_parse += 1
                else:
                    if result["missing"]:
                        for ph in result["missing"]:
                            missing_phonemes[ph] += 1
                    if len(result["phoneme_ids"]) == 0:
                        skipped_parse += 1
                    else:
                        phonemized.append(
                            {
                                "text": result["text"],
                                "wav_path": result["wav_path"],
                                "speaker_id": result["speaker_id"],  # NEW
                                "phonemes": result["phonemes"],
                                "phoneme_ids": result["phoneme_ids"],
                                "prosody_features": result["prosody_features"],
                            }
                        )
                if done % 1000 == 0:
                    _LOGGER.info("Phonemized %d/%d EN utterances", done, len(tasks))
    else:
        phonemizer = MultilingualPhonemizer(["ja", "en"])
        for task_idx, (filename, text, wav_path_str, speaker_id) in enumerate(tasks):
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
                                prosody_features.append(
                                    {"a1": pr.a1, "a2": pr.a2, "a3": pr.a3}
                                )
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
                phonemized.append(
                    {
                        "text": text,
                        "wav_path": wav_path_str,
                        "speaker_id": speaker_id,  # NEW
                        "phonemes": phonemes,
                        "phoneme_ids": phoneme_ids,
                        "prosody_features": prosody_features,
                    }
                )
            except Exception as e:
                _LOGGER.warning("Failed to phonemize %s: %s", filename, e)
                skipped_parse += 1
            if (task_idx + 1) % 1000 == 0:
                _LOGGER.info("Phonemized %d/%d EN utterances", task_idx + 1, len(tasks))

    if missing_phonemes:
        for ph, count in missing_phonemes.most_common(10):
            _LOGGER.warning("Missing EN phoneme: '%s' (%d times)", ph, count)

    _LOGGER.info(
        "Phonemized %d EN utterances (%d parse-skipped, %d speaker-filtered)",
        len(phonemized),
        skipped_parse,
        skipped_speaker,
    )

    # Phase 2: Audio normalization (slow, parallel)
    # Build a set of already-cached spec files for O(1) lookup instead of
    # per-file stat() calls (avoids N*2 syscalls on NFS).
    existing_specs: set[str] = set()
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.name.endswith(".spec.pt"):
                existing_specs.add(f.name[: -len(".spec.pt")])

    _LOGGER.info("Found %d existing spec caches in %s", len(existing_specs), cache_dir)

    audio_map: dict[str, tuple[str, str]] = {}
    need_caching: list[tuple[str, str, int]] = []

    for p in phonemized:
        wav_path_str = p["wav_path"]
        audio_cache_id = _sha256(
            str(Path(wav_path_str).absolute()).encode()
        ).hexdigest()
        norm_path = cache_dir / f"{audio_cache_id}.pt"
        spec_path = cache_dir / f"{audio_cache_id}.spec.pt"
        if audio_cache_id in existing_specs:
            audio_map[wav_path_str] = (str(norm_path), str(spec_path))
        else:
            need_caching.append((wav_path_str, str(cache_dir), sample_rate))

    _LOGGER.info(
        "Audio cache: %d already cached, %d need processing",
        len(audio_map),
        len(need_caching),
    )

    if need_caching:
        _LOGGER.info(
            "Caching audio for %d EN utterances with %d workers (energy VAD fast path)...",
            len(need_caching),
            workers,
        )
        if workers > 1:
            batches = [
                need_caching[i : i + _CACHE_BATCH_SIZE_FAST]
                for i in range(0, len(need_caching), _CACHE_BATCH_SIZE_FAST)
            ]
            batch_args = [
                ([item[0] for item in batch], batch[0][1], batch[0][2])
                for batch in batches
            ]
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_cache_audio_batch_worker_fast, a): i
                    for i, a in enumerate(batch_args)
                }
                done = 0
                next_log = 1000
                for future in as_completed(futures):
                    try:
                        batch_results = future.result()
                        for wav_str, norm_str, spec_str in batch_results:
                            if norm_str is not None:
                                audio_map[wav_str] = (norm_str, spec_str)
                            else:
                                _LOGGER.warning(
                                    "Audio cache failed for %s: %s", wav_str, spec_str
                                )
                            done += 1
                            if done >= next_log:
                                _LOGGER.info(
                                    "Cached audio %d/%d",
                                    min(done, len(need_caching)),
                                    len(need_caching),
                                )
                                next_log += 1000
                    except Exception as e:
                        _LOGGER.warning("Audio cache batch failed: %s", e)
                        done += _CACHE_BATCH_SIZE
        else:
            detector = make_silence_detector()
            for i, (wav_path_str, _, sr) in enumerate(need_caching):
                try:
                    norm_path, spec_path = cache_norm_audio(
                        wav_path_str, cache_dir, detector, sr
                    )
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

        # Determine speaker name from speaker_id
        speaker_name = "ljspeech"  # default for backward compatibility
        if multi_speaker:
            # Find speaker name from speaker_id_map (reverse lookup)
            for spk_name, spk_id in speaker_id_map.items():
                if spk_id == p["speaker_id"]:
                    speaker_name = spk_name
                    break

        utterances.append(
            {
                "text": p["text"],
                "audio_path": wav_key,
                "speaker": speaker_name,
                "speaker_id": p["speaker_id"],  # Use dynamic speaker_id
                "language_id": 1,
                "phonemes": p["phonemes"],
                "phoneme_ids": p["phoneme_ids"],
                "prosody_ids": [],
                "prosody_features": p["prosody_features"],
                "audio_norm_path": norm_path,
                "audio_spec_path": spec_path,
                "f0_path": None,
            }
        )

    _LOGGER.info(
        "Loaded %d EN utterances (%d speakers)",
        len(utterances),
        len(speaker_id_map),
    )
    return utterances, speaker_id_map  # Return speaker_id_map


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s"
    )

    parser = argparse.ArgumentParser(description="Prepare bilingual JA+EN dataset")
    parser.add_argument("--ja-dataset", required=True, help="Path to JA dataset.jsonl")
    parser.add_argument(
        "--ja-already-bilingual",
        action="store_true",
        help="Input JA dataset is already a bilingual dataset (e.g., enhanced-fixed). "
        "Skips phoneme ID remapping and padding; reads audio caches directly.",
    )
    parser.add_argument("--en-input-dir", help="Path to LJSpeech-1.1 directory")
    parser.add_argument(
        "--en-libritts",
        help="Path to LibriTTS-R directory (converted to LJSpeech format)",
    )
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--sample-rate", type=int, default=22050)
    parser.add_argument(
        "--max-en-utterances",
        type=int,
        default=None,
        help="Max EN utterances per source (default: None = use all)",
    )
    parser.add_argument(
        "--max-en-speakers",
        type=int,
        default=60,
        help="Maximum number of EN speakers to include (top N by utterance count, default: 60)",
    )
    parser.add_argument(
        "--min-en-utterances-per-speaker",
        type=int,
        default=0,
        help="Minimum utterances per EN speaker; speakers below this are excluded (default: 0 = no filter). "
        "Recommended: 30 to prevent very short speakers from limiting epoch length.",
    )
    parser.add_argument(
        "--en-single-speaker",
        action="store_true",
        help="Force single-speaker EN mode (combine all EN data into one speaker)",
    )
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    if not args.en_input_dir and not args.en_libritts:
        parser.error(
            "At least one of --en-input-dir or --en-libritts must be specified"
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache" / str(args.sample_rate)
    cache_dir.mkdir(parents=True, exist_ok=True)

    bilingual_id_map = get_bilingual_id_map()
    _LOGGER.info("Bilingual ID map: %d symbols", len(bilingual_id_map))

    # Process JA
    ja_utts, ja_speakers = process_ja_dataset(
        Path(args.ja_dataset),
        bilingual_id_map,
        args.sample_rate,
        cache_dir,
        ja_speaker_offset=0,
        workers=args.workers,
        already_bilingual=args.ja_already_bilingual,
    )

    # EN speaker ID offset = next after JA speakers
    en_speaker_id_offset = len(ja_speakers)
    _LOGGER.info("EN speaker ID offset: %d", en_speaker_id_offset)

    # Process EN datasets (LJSpeech and/or LibriTTS-R)
    en_utts = []
    en_speaker_id_map = {}

    if args.en_input_dir:
        _LOGGER.info("Processing LJSpeech from %s", args.en_input_dir)
        ljspeech_utts, ljspeech_speakers = process_en_dataset(
            Path(args.en_input_dir),
            bilingual_id_map,
            args.sample_rate,
            cache_dir,
            en_speaker_id_offset=en_speaker_id_offset,
            max_utterances=args.max_en_utterances,
            workers=args.workers,
            max_speakers=args.max_en_speakers,
            multi_speaker=not args.en_single_speaker,
            min_utterances_per_speaker=args.min_en_utterances_per_speaker,
        )
        en_utts.extend(ljspeech_utts)
        en_speaker_id_map.update(ljspeech_speakers)
        en_speaker_id_offset = max(en_speaker_id_map.values()) + 1  # Update offset

    if args.en_libritts:
        _LOGGER.info("Processing LibriTTS-R from %s", args.en_libritts)
        # Determine multi-speaker mode
        multi_speaker_mode = not args.en_single_speaker
        max_speakers_arg = None if args.en_single_speaker else args.max_en_speakers

        libritts_utts, libritts_speakers = process_en_dataset(
            Path(args.en_libritts),
            bilingual_id_map,
            args.sample_rate,
            cache_dir,
            en_speaker_id_offset=en_speaker_id_offset,
            max_utterances=args.max_en_utterances,
            workers=args.workers,
            max_speakers=max_speakers_arg,
            multi_speaker=multi_speaker_mode,
            min_utterances_per_speaker=args.min_en_utterances_per_speaker,
        )
        en_utts.extend(libritts_utts)
        en_speaker_id_map.update(libritts_speakers)

    # Merge and write
    all_utts = ja_utts + en_utts
    _LOGGER.info(
        "Total utterances: %d (JA=%d, EN=%d)", len(all_utts), len(ja_utts), len(en_utts)
    )

    # Write dataset.jsonl
    dataset_path = output_dir / "dataset.jsonl"
    with open(dataset_path, "w", encoding="utf-8") as f:
        for utt in all_utts:
            json.dump(utt, f, ensure_ascii=True)
            f.write("\n")
    _LOGGER.info("Wrote %s", dataset_path)

    # Merge JA and EN speaker maps
    speaker_id_map = {**ja_speakers, **en_speaker_id_map}
    num_speakers = len(speaker_id_map)

    _LOGGER.info(
        "Total speakers: %d (JA=%d, EN=%d)",
        num_speakers,
        len(ja_speakers),
        len(en_speaker_id_map),
    )

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
    _LOGGER.info(
        "Wrote %s (speakers=%d, symbols=%d, languages=2)",
        config_path,
        num_speakers,
        len(bilingual_id_map),
    )


if __name__ == "__main__":
    main()
