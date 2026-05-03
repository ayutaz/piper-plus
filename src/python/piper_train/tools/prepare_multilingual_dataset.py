#!/usr/bin/env python3
"""Prepare multilingual (8-language G2P support) dataset for Piper TTS.

Merges existing JA+EN v4 dataset with new ZH (AISHELL-3), ES/FR/PT (CML-TTS)
corpora. The bilingual phoneme IDs (0-96) are 100% compatible with the
multilingual ID space, so JA+EN data is reused as-is.

Optimizations:
- Skip VAD for pre-cleaned corpora (AISHELL-3, CML-TTS) — ~30% faster audio
- GPU batch spectrogram — 250-500x faster STFT on idle V100s
- AISHELL-3 pre-computed pinyin shortcut — ~29x faster ZH phonemization
- Batched phonemization workers — 22x less IPC overhead
- soxr MQ quality — ~30-40% faster resampling

Usage:
    .venv/bin/python prepare_multilingual_dataset.py \
        --ja-en-dataset /data/piper/dataset-bilingual-ja-en-v4/dataset.jsonl \
        --zh-aishell3 /data/piper/downloads/aishell3 \
        --es-cml-tts /data/piper/downloads/cml_tts_dataset_spanish_v0.1 \
        --fr-cml-tts /data/piper/downloads/cml_tts_dataset_french_v0.1 \
        --pt-cml-tts /data/piper/downloads/cml_tts_dataset_portuguese_v0.1 \
        --output-dir /data/piper/dataset-multilingual-6lang \
        --sample-rate 22050 \
        --workers 30 \
        --gpu-spec-device cuda:0
"""

import argparse
import json
import logging
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256 as _sha256
from pathlib import Path

from piper_plus_g2p.encode.pua import map_token as _map_token


_LOGGER = logging.getLogger("prepare_multilingual")

# Language ID mapping (must match model config)
LANGUAGE_ID_MAP = {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5, "sv": 6}

# All languages in canonical order
ALL_LANGUAGES = ["ja", "en", "zh", "es", "fr", "pt", "sv"]

# Batch sizes for parallel processing
_RESAMPLE_BATCH_SIZE = 50
_PHONEMIZE_BATCH_SIZE = 100
_GPU_SPEC_BATCH_SIZE = 64


# ---------------------------------------------------------------------------
# 1. Load JA+EN from existing v4 dataset
# ---------------------------------------------------------------------------


def load_ja_en_dataset(
    jsonl_path: Path,
) -> tuple[list[dict], dict[str, int], int]:
    """Load JA+EN utterances from the existing bilingual v4 dataset.

    Returns:
        (utterances, speaker_id_map, max_speaker_id)
        utterances: list of dicts ready for dataset.jsonl
        speaker_id_map: {speaker_name: speaker_id}
        max_speaker_id: highest speaker_id seen (for offsetting new languages)
    """
    utterances: list[dict] = []
    speaker_id_map: dict[str, int] = {}
    max_speaker_id = -1
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

            phoneme_ids = utt.get("phoneme_ids", [])
            if not phoneme_ids:
                skipped += 1
                continue

            # Verify cached audio exists
            norm_path = utt.get("audio_norm_path", "")
            spec_path = utt.get("audio_spec_path", "")
            if not norm_path or not Path(norm_path).exists():
                skipped += 1
                continue
            if not spec_path or not Path(spec_path).exists():
                skipped += 1
                continue

            speaker = utt.get("speaker", "unknown")
            speaker_id = utt.get("speaker_id", 0)
            if speaker not in speaker_id_map:
                speaker_id_map[speaker] = speaker_id
            max_speaker_id = max(max_speaker_id, speaker_id)

            utterances.append(utt)

    ja_count = sum(1 for u in utterances if u.get("language_id", 0) == 0)
    en_count = sum(1 for u in utterances if u.get("language_id", 0) == 1)
    _LOGGER.info(
        "Loaded %d JA+EN utterances (JA=%d, EN=%d, %d skipped), "
        "%d speakers (max_id=%d)",
        len(utterances),
        ja_count,
        en_count,
        skipped,
        len(speaker_id_map),
        max_speaker_id,
    )
    return utterances, speaker_id_map, max_speaker_id


# ---------------------------------------------------------------------------
# 2. Parse AISHELL-3 data (with pre-computed pinyin extraction)
# ---------------------------------------------------------------------------


def parse_aishell3(
    base_dir: Path,
) -> tuple[list[tuple[str, str, str, list[str]]], dict[str, int]]:
    """Parse AISHELL-3 dataset with pre-computed pinyin extraction.

    Returns:
        (entries, speaker_counts)
        entries: list of (text, wav_path, speaker_id_str, pinyin_syllables) tuples
        speaker_counts: {speaker_id_str: utterance_count}
    """
    content_path = base_dir / "train" / "content.txt"
    wav_dir = base_dir / "train" / "wav"

    if not content_path.exists():
        _LOGGER.error("AISHELL-3 content.txt not found: %s", content_path)
        return [], {}

    entries: list[tuple[str, str, str, list[str]]] = []
    speaker_counts: dict[str, int] = Counter()
    skipped = 0

    with open(content_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Format: SSB00050001.wav\t广 guang3 州 zhou1 ...
            parts = line.split("\t", maxsplit=1)
            if len(parts) < 2:
                skipped += 1
                continue

            utterance_file = parts[0].strip()
            pinyin_text = parts[1].strip()

            # Split: alternating characters and pinyin
            tokens = pinyin_text.split()
            chinese_chars = [tokens[i] for i in range(0, len(tokens), 2)]
            pinyin_syllables = [tokens[i] for i in range(1, len(tokens), 2)]
            text = "".join(chinese_chars)

            if not text or not pinyin_syllables:
                skipped += 1
                continue

            # Speaker ID from filename: SSB0005XXXX.wav -> SSB0005
            utterance_id = utterance_file.replace(".wav", "")
            speaker_id_str = utterance_id[:7]

            wav_path = wav_dir / speaker_id_str / utterance_file
            if not wav_path.exists():
                skipped += 1
                continue

            entries.append((text, str(wav_path), speaker_id_str, pinyin_syllables))
            speaker_counts[speaker_id_str] += 1

    _LOGGER.info(
        "Parsed %d AISHELL-3 utterances (%d speakers, %d skipped) "
        "[pinyin shortcut enabled]",
        len(entries),
        len(speaker_counts),
        skipped,
    )
    return entries, dict(speaker_counts)


# ---------------------------------------------------------------------------
# 3. Parse CML-TTS data (shared for ES/FR/PT)
# ---------------------------------------------------------------------------


def parse_cml_tts(
    base_dir: Path,
    language: str,
) -> tuple[list[tuple[str, str, str]], dict[str, int]]:
    """Parse CML-TTS dataset (ES, FR, or PT).

    Returns:
        (entries, speaker_counts)
        entries: list of (text, wav_path, speaker_id_str) tuples
        speaker_counts: {client_id: utterance_count}
    """
    train_csv = base_dir / "train.csv"
    if not train_csv.exists():
        _LOGGER.error("CML-TTS train.csv not found: %s", train_csv)
        return [], {}

    entries: list[tuple[str, str, str]] = []
    speaker_counts: dict[str, int] = Counter()
    skipped = 0

    with open(train_csv, encoding="utf-8") as f:
        # Skip header line
        header = f.readline()
        if not header:
            return [], {}

        for _line_no, line in enumerate(f, start=2):
            line = line.strip()
            if not line:
                continue

            # Pipe-delimited:
            # wav_filename|wav_filesize|transcript|transcript_wav2vec|
            # levenshtein|duration|num_words|client_id
            parts = line.split("|")
            if len(parts) < 8:
                skipped += 1
                continue

            wav_filename = parts[0].strip()
            transcript = parts[2].strip()
            client_id = parts[7].strip()

            if not transcript:
                skipped += 1
                continue

            wav_path = base_dir / wav_filename
            if not wav_path.exists():
                skipped += 1
                continue

            entries.append((transcript, str(wav_path), client_id))
            speaker_counts[client_id] += 1

    _LOGGER.info(
        "Parsed %d %s utterances (%d speakers, %d skipped)",
        len(entries),
        language.upper(),
        len(speaker_counts),
        skipped,
    )
    return entries, dict(speaker_counts)


# ---------------------------------------------------------------------------
# 4. Phonemization workers (batched for reduced IPC overhead)
# ---------------------------------------------------------------------------

# Per-worker state (initialized once per worker process)
_phonemize_worker_state: dict = {}


def _init_phonemize_worker(
    languages: list[str],
    ml_id_map: dict[str, list[int]],
):
    """Initialize MultilingualPhonemizer once per worker process."""
    from piper_plus_g2p import get_phonemizer  # noqa: PLC0415
    from piper_plus_g2p.multilingual import MultilingualPhonemizer  # noqa: PLC0415

    _phonemize_worker_state["ml_phonemizer"] = MultilingualPhonemizer(languages)
    _phonemize_worker_state["id_map"] = ml_id_map
    # Cache per-language phonemizers
    for lang in languages:
        try:
            _phonemize_worker_state[f"phonemizer_{lang}"] = get_phonemizer(lang)
        except Exception:
            pass


def _post_process_ids(
    phoneme_ids: list[int],
    prosody_features: list,
    id_map: dict[str, list[int]],
) -> tuple[list[int], list]:
    """Insert BOS/EOS and inter-phoneme padding.

    Mirrors ``PiperEncoder._post_process()`` from piper_plus_g2p.
    """
    pad_ids = id_map.get("_", [0])
    bos_ids = id_map.get("^")
    eos_ids = id_map.get("$")

    # Insert pad between every phoneme ID, skip after existing pad tokens
    padded_ids: list[int] = []
    padded_prosody: list = []
    for phoneme_id, prosody_feature in zip(phoneme_ids, prosody_features, strict=True):
        padded_ids.append(phoneme_id)
        padded_prosody.append(prosody_feature)
        if phoneme_id not in pad_ids:
            padded_ids.extend(pad_ids)
            padded_prosody.extend([None] * len(pad_ids))

    phoneme_ids = padded_ids
    prosody_features = padded_prosody

    # Wrap with BOS / EOS
    if bos_ids:
        phoneme_ids = bos_ids + [pad_ids[0]] + phoneme_ids
        prosody_features = [None] * (len(bos_ids) + 1) + prosody_features
    if eos_ids:
        phoneme_ids = phoneme_ids + eos_ids
        prosody_features = prosody_features + [None] * len(eos_ids)

    return phoneme_ids, prosody_features


def _phonemize_single(
    text: str,
    wav_path: str,
    speaker_id_str: str,
    language: str,
    language_id: int,
) -> dict:
    """Phonemize a single utterance using cached worker state."""
    id_map = _phonemize_worker_state["id_map"]
    lang_phonemizer = _phonemize_worker_state.get(f"phonemizer_{language}")

    try:
        if lang_phonemizer is None:
            return {"wav_path": wav_path, "error": f"No phonemizer for '{language}'"}

        phonemes, prosody_list = lang_phonemizer.phonemize_with_prosody(text)

        phoneme_ids = []
        prosody_features = []
        missing = []
        for ph, pr in zip(phonemes, prosody_list, strict=True):
            mapped_ph = _map_token(ph)
            if mapped_ph in id_map:
                ids = id_map[mapped_ph]
                phoneme_ids.extend(ids)
                for _ in ids:
                    if pr is not None:
                        prosody_features.append({"a1": pr.a1, "a2": pr.a2, "a3": pr.a3})
                    else:
                        prosody_features.append(None)
            else:
                missing.append(ph)

        phoneme_ids, prosody_features = _post_process_ids(
            phoneme_ids, prosody_features, id_map
        )

        if not phoneme_ids:
            return {"wav_path": wav_path, "error": "Empty phoneme_ids"}

        return {
            "text": text,
            "wav_path": wav_path,
            "speaker_id_str": speaker_id_str,
            "language": language,
            "language_id": language_id,
            "phonemes": phonemes,
            "phoneme_ids": phoneme_ids,
            "prosody_features": prosody_features,
            "missing": missing,
        }
    except Exception as e:
        return {"wav_path": wav_path, "error": str(e)}


def _phonemize_batch_worker(
    batch: list[tuple[str, str, str, str, int]],
) -> list[dict]:
    """Phonemize a batch of utterances in a single worker call.

    Reduces IPC overhead by ~22x compared to per-utterance submission.
    """
    results = []
    for text, wav_path, speaker_id_str, language, language_id in batch:
        results.append(
            _phonemize_single(text, wav_path, speaker_id_str, language, language_id)
        )
    return results


# ---------------------------------------------------------------------------
# 4b. AISHELL-3 pinyin shortcut phonemization (bypasses pypinyin, ~29x faster)
# ---------------------------------------------------------------------------


def _init_zh_pinyin_worker(
    languages: list[str],
    ml_id_map: dict[str, list[int]],
):
    """Initialize worker state for ZH pinyin shortcut."""
    from piper_plus_g2p.multilingual import MultilingualPhonemizer  # noqa: PLC0415

    _phonemize_worker_state["ml_phonemizer"] = MultilingualPhonemizer(languages)
    _phonemize_worker_state["id_map"] = ml_id_map


def _phonemize_zh_pinyin_single(
    text: str,
    wav_path: str,
    speaker_id_str: str,
    language_id: int,
    pinyin_syllables: list[str],
) -> dict:
    """Phonemize Chinese from pre-computed pinyin (bypasses pypinyin)."""
    from piper_plus_g2p.chinese import (  # noqa: PLC0415
        phonemize_from_pinyin_syllables,
    )

    id_map = _phonemize_worker_state["id_map"]

    try:
        phonemes, prosody_list = phonemize_from_pinyin_syllables(
            pinyin_syllables, chinese_text=text
        )

        phoneme_ids = []
        prosody_features = []
        missing = []
        for ph, pr in zip(phonemes, prosody_list, strict=True):
            mapped_ph = _map_token(ph)
            if mapped_ph in id_map:
                ids = id_map[mapped_ph]
                phoneme_ids.extend(ids)
                for _ in ids:
                    if pr is not None:
                        prosody_features.append({"a1": pr.a1, "a2": pr.a2, "a3": pr.a3})
                    else:
                        prosody_features.append(None)
            else:
                missing.append(ph)

        phoneme_ids, prosody_features = _post_process_ids(
            phoneme_ids, prosody_features, id_map
        )

        if not phoneme_ids:
            return {"wav_path": wav_path, "error": "Empty phoneme_ids"}

        return {
            "text": text,
            "wav_path": wav_path,
            "speaker_id_str": speaker_id_str,
            "language": "zh",
            "language_id": language_id,
            "phonemes": phonemes,
            "phoneme_ids": phoneme_ids,
            "prosody_features": prosody_features,
            "missing": missing,
        }
    except Exception as e:
        return {"wav_path": wav_path, "error": str(e)}


def _phonemize_zh_pinyin_batch_worker(
    batch: list[tuple[str, str, str, int, list[str]]],
) -> list[dict]:
    """Batch worker for ZH pinyin shortcut phonemization."""
    results = []
    for text, wav_path, speaker_id_str, language_id, pinyin_syllables in batch:
        results.append(
            _phonemize_zh_pinyin_single(
                text, wav_path, speaker_id_str, language_id, pinyin_syllables
            )
        )
    return results


# ---------------------------------------------------------------------------
# 5. Audio caching: Phase A = resample (CPU parallel), Phase B = GPU spec
# ---------------------------------------------------------------------------


def _resample_batch_worker_no_vad(args):
    """Resample a batch of audio files without VAD (CPU worker).

    Skips 16kHz resampling and energy VAD entirely.
    Uses soxr MQ for ~30-40% faster resampling.
    """
    wav_paths, cache_dir, sample_rate, resample_quality = args
    from piper_train.norm_audio import resample_only_no_vad  # noqa: PLC0415

    results = []
    for wav_path in wav_paths:
        try:
            norm_path, cache_id = resample_only_no_vad(
                wav_path,
                cache_dir,
                sample_rate,
                resample_quality=resample_quality,
            )
            spec_path = Path(cache_dir) / f"{cache_id}.spec.pt"
            results.append((str(wav_path), str(norm_path), str(spec_path)))
        except Exception as e:
            results.append((str(wav_path), None, str(e)))
    return results


def _cache_audio_batch_worker_no_vad(args):
    """Cache audio without VAD (resample + spectrogram, CPU worker).

    Fallback for when no GPU is available.
    """
    wav_paths, cache_dir, sample_rate, resample_quality = args
    from piper_train.norm_audio import cache_norm_audio_no_vad  # noqa: PLC0415

    results = []
    for wav_path in wav_paths:
        try:
            norm_path, spec_path = cache_norm_audio_no_vad(
                wav_path,
                cache_dir,
                sample_rate,
                resample_quality=resample_quality,
            )
            results.append((str(wav_path), str(norm_path), str(spec_path)))
        except Exception as e:
            results.append((str(wav_path), None, str(e)))
    return results


def _compute_specs_gpu_batch(
    items: list[tuple[str, str]],
    batch_size: int = _GPU_SPEC_BATCH_SIZE,
    device: str = "cuda:0",
    filter_length: int = 1024,
    window_length: int = 1024,
    hop_length: int = 256,
    sample_rate: int = 22050,
) -> int:
    """Compute spectrograms on GPU in batches.

    Loads .pt files, pads to uniform length, runs batched torch.stft on GPU,
    then saves individual .spec.pt files.

    Returns:
        Number of specs computed.
    """
    import torch  # noqa: PLC0415

    from piper_train.norm_audio import _atomic_torch_save  # noqa: PLC0415
    from piper_train.vits.mel_processing import spectrogram_torch  # noqa: PLC0415

    # Filter to only items needing spec computation
    need_compute = [
        (norm_p, spec_p) for norm_p, spec_p in items if not Path(spec_p).exists()
    ]
    if not need_compute:
        return 0

    _LOGGER.info(
        "GPU batch spec: %d specs to compute on %s (batch=%d)",
        len(need_compute),
        device,
        batch_size,
    )

    computed = 0
    n_batches = (len(need_compute) + batch_size - 1) // batch_size

    for batch_idx in range(n_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(need_compute))
        batch = need_compute[start:end]

        # Load audio tensors and track lengths
        audios = []
        lengths = []
        valid_indices = []
        for j, (norm_p, _spec_p) in enumerate(batch):
            try:
                t = torch.load(norm_p, weights_only=True)  # (1, T)
                audio_1d = t.squeeze(0)
                audios.append(audio_1d)
                lengths.append(audio_1d.shape[0])
                valid_indices.append(j)
            except Exception as e:
                _LOGGER.debug("Failed to load %s: %s", norm_p, e)

        if not audios:
            continue

        max_len = max(lengths)

        # Pad to uniform length and stack
        batch_tensor = torch.zeros(len(audios), max_len)
        for j, audio in enumerate(audios):
            batch_tensor[j, : lengths[j]] = audio

        # Compute spectrograms on GPU
        batch_tensor = batch_tensor.to(device)
        try:
            specs = spectrogram_torch(
                y=batch_tensor,
                n_fft=filter_length,
                sampling_rate=sample_rate,
                hop_size=hop_length,
                win_size=window_length,
                center=False,
            )  # (N, freq_bins, time_frames)
        except Exception as e:
            _LOGGER.warning("GPU batch STFT failed (batch %d): %s", batch_idx, e)
            continue

        # Save individual specs, trimmed to correct length
        specs_cpu = specs.cpu()
        for j, valid_j in enumerate(valid_indices):
            _norm_p, spec_p = batch[valid_j]
            orig_len = lengths[j]
            # Correct frame count for this audio
            padded_len = orig_len + filter_length - hop_length
            correct_frames = padded_len // hop_length
            trimmed_spec = specs_cpu[j, :, :correct_frames]
            try:
                _atomic_torch_save(trimmed_spec.half(), spec_p)
                computed += 1
            except Exception as e:
                _LOGGER.debug("Failed to save spec %s: %s", spec_p, e)

        if (batch_idx + 1) % 100 == 0 or (batch_idx + 1) == n_batches:
            _LOGGER.info(
                "GPU spec progress: %d/%d batches (%d specs computed)",
                batch_idx + 1,
                n_batches,
                computed,
            )

    return computed


# ---------------------------------------------------------------------------
# 6. Phonemize new language entries (parallel, batched)
# ---------------------------------------------------------------------------


def phonemize_new_language(
    entries,
    language: str,
    language_id: int,
    ml_id_map: dict[str, list[int]],
    workers: int,
    use_pinyin_shortcut: bool = False,
) -> tuple[list[dict], Counter]:
    """Phonemize entries for a new language.

    Args:
        entries: For ZH pinyin shortcut: list of (text, wav_path, spk, pinyin)
                 For others: list of (text, wav_path, spk)
        language: language code
        language_id: language ID integer
        ml_id_map: multilingual phoneme ID map
        workers: number of parallel workers
        use_pinyin_shortcut: if True, use AISHELL-3 pinyin shortcut for ZH

    Returns:
        (phonemized, missing_phonemes)
    """
    _LOGGER.info(
        "Phonemizing %d %s utterances with %d workers%s...",
        len(entries),
        language.upper(),
        workers,
        " [pinyin shortcut]" if use_pinyin_shortcut else "",
    )

    phonemized: list[dict] = []
    missing_phonemes: Counter = Counter()
    skipped = 0
    t0 = time.monotonic()

    if use_pinyin_shortcut and language == "zh":
        # AISHELL-3 pinyin shortcut: bypass pypinyin entirely (~29x faster)
        tasks = [
            (text, wav_path, spk, language_id, pinyin)
            for text, wav_path, spk, pinyin in entries
        ]
        batches = [
            tasks[i : i + _PHONEMIZE_BATCH_SIZE]
            for i in range(0, len(tasks), _PHONEMIZE_BATCH_SIZE)
        ]

        if workers > 1:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_zh_pinyin_worker,
                initargs=(ALL_LANGUAGES, ml_id_map),
            ) as executor:
                futures = {
                    executor.submit(_phonemize_zh_pinyin_batch_worker, b): i
                    for i, b in enumerate(batches)
                }
                done_utts = 0
                for future in as_completed(futures):
                    for result in future.result():
                        if "error" in result:
                            skipped += 1
                        else:
                            if result["missing"]:
                                for ph in result["missing"]:
                                    missing_phonemes[ph] += 1
                            phonemized.append(result)
                        done_utts += 1
                    if done_utts % 5000 < _PHONEMIZE_BATCH_SIZE:
                        _LOGGER.info("Phonemized %d/%d %s", done_utts, len(tasks), "ZH")
        else:
            _init_zh_pinyin_worker(ALL_LANGUAGES, ml_id_map)
            for batch in batches:
                for result in _phonemize_zh_pinyin_batch_worker(batch):
                    if "error" in result:
                        skipped += 1
                    else:
                        if result["missing"]:
                            for ph in result["missing"]:
                                missing_phonemes[ph] += 1
                        phonemized.append(result)
    else:
        # Standard phonemization (batched workers)
        tasks = [
            (text, wav_path, spk, language, language_id)
            for text, wav_path, spk in entries
        ]
        batches = [
            tasks[i : i + _PHONEMIZE_BATCH_SIZE]
            for i in range(0, len(tasks), _PHONEMIZE_BATCH_SIZE)
        ]

        if workers > 1:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_phonemize_worker,
                initargs=(ALL_LANGUAGES, ml_id_map),
            ) as executor:
                futures = {
                    executor.submit(_phonemize_batch_worker, b): i
                    for i, b in enumerate(batches)
                }
                done_utts = 0
                for future in as_completed(futures):
                    for result in future.result():
                        if "error" in result:
                            skipped += 1
                        else:
                            if result["missing"]:
                                for ph in result["missing"]:
                                    missing_phonemes[ph] += 1
                            phonemized.append(result)
                        done_utts += 1
                    if done_utts % 5000 < _PHONEMIZE_BATCH_SIZE:
                        _LOGGER.info(
                            "Phonemized %d/%d %s",
                            done_utts,
                            len(tasks),
                            language.upper(),
                        )
        else:
            _init_phonemize_worker(ALL_LANGUAGES, ml_id_map)
            for batch in batches:
                for result in _phonemize_batch_worker(batch):
                    if "error" in result:
                        skipped += 1
                    else:
                        if result["missing"]:
                            for ph in result["missing"]:
                                missing_phonemes[ph] += 1
                        phonemized.append(result)

    elapsed = time.monotonic() - t0

    if missing_phonemes:
        _LOGGER.warning(
            "%s: %d missing phoneme types (top 10):",
            language.upper(),
            len(missing_phonemes),
        )
        for ph, count in missing_phonemes.most_common(10):
            _LOGGER.warning("  '%s' (%d occurrences)", ph, count)

    _LOGGER.info(
        "Phonemized %d %s utterances (%d skipped) in %.1fs (%.0f utt/s)",
        len(phonemized),
        language.upper(),
        skipped,
        elapsed,
        len(phonemized) / max(elapsed, 0.001),
    )
    return phonemized, missing_phonemes


# ---------------------------------------------------------------------------
# 7. Cache audio files (two-phase: CPU resample → GPU batch spectrogram)
# ---------------------------------------------------------------------------


def cache_audio_parallel(
    phonemized: list[dict],
    cache_dir: Path,
    sample_rate: int,
    workers: int,
    language: str,
    gpu_spec_device: str | None = None,
    resample_quality: str = "MQ",
) -> dict[str, tuple[str, str]]:
    """Cache audio files for phonemized utterances.

    Two-phase pipeline:
      Phase A: Resample audio (CPU parallel, no VAD) → save .pt
      Phase B: Compute spectrograms (GPU batch or CPU fallback) → save .spec.pt

    Returns:
        audio_map: {wav_path: (norm_path, spec_path)}
    """
    # Build set of already-cached spec files for O(1) lookup
    existing_specs: set[str] = set()
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.name.endswith(".spec.pt"):
                existing_specs.add(f.name[: -len(".spec.pt")])

    _LOGGER.info("Found %d existing spec caches in %s", len(existing_specs), cache_dir)

    audio_map: dict[str, tuple[str, str]] = {}
    need_caching: list[str] = []

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
            need_caching.append(wav_path_str)

    _LOGGER.info(
        "%s audio cache: %d already cached, %d need processing",
        language.upper(),
        len(audio_map),
        len(need_caching),
    )

    if not need_caching:
        return audio_map

    t0 = time.monotonic()

    if gpu_spec_device:
        # ============================================================
        # Two-phase: CPU resample → GPU batch spectrogram
        # ============================================================
        _LOGGER.info(
            "Phase A: Resampling %d %s files (no VAD, soxr %s, %d workers)...",
            len(need_caching),
            language.upper(),
            resample_quality,
            workers,
        )

        # Phase A: Resample only (parallel CPU workers)
        batches = [
            need_caching[i : i + _RESAMPLE_BATCH_SIZE]
            for i in range(0, len(need_caching), _RESAMPLE_BATCH_SIZE)
        ]
        batch_args = [
            (batch, str(cache_dir), sample_rate, resample_quality) for batch in batches
        ]

        resample_results: list[tuple[str, str, str]] = []  # (wav, norm, spec)
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_resample_batch_worker_no_vad, a): i
                for i, a in enumerate(batch_args)
            }
            done = 0
            for future in as_completed(futures):
                try:
                    for wav_str, norm_str, spec_str in future.result():
                        if norm_str is not None:
                            resample_results.append((wav_str, norm_str, spec_str))
                        else:
                            _LOGGER.warning(
                                "Resample failed for %s: %s", wav_str, spec_str
                            )
                        done += 1
                        if done % 5000 == 0:
                            _LOGGER.info(
                                "Resampled %d/%d %s",
                                min(done, len(need_caching)),
                                len(need_caching),
                                language.upper(),
                            )
                except Exception as e:
                    _LOGGER.warning("Resample batch failed: %s", e)

        t_resample = time.monotonic() - t0
        _LOGGER.info(
            "Phase A complete: %d files resampled in %.1fs (%.0f files/s)",
            len(resample_results),
            t_resample,
            len(resample_results) / max(t_resample, 0.001),
        )

        # Phase B: GPU batch spectrogram
        t1 = time.monotonic()
        _LOGGER.info(
            "Phase B: GPU batch spectrogram on %s (%d files)...",
            gpu_spec_device,
            len(resample_results),
        )

        spec_items = [
            (norm_str, spec_str) for _, norm_str, spec_str in resample_results
        ]
        computed = _compute_specs_gpu_batch(
            spec_items,
            batch_size=_GPU_SPEC_BATCH_SIZE,
            device=gpu_spec_device,
            sample_rate=sample_rate,
        )

        t_spec = time.monotonic() - t1
        _LOGGER.info(
            "Phase B complete: %d specs computed in %.1fs (%.0f specs/s)",
            computed,
            t_spec,
            computed / max(t_spec, 0.001),
        )

        # Build audio_map from results
        for wav_str, norm_str, spec_str in resample_results:
            if Path(spec_str).exists():
                audio_map[wav_str] = (norm_str, spec_str)
            else:
                _LOGGER.debug("Spec missing after GPU pass: %s", spec_str)
    else:
        # ============================================================
        # Fallback: CPU-only (no VAD, resample+spec in one pass)
        # ============================================================
        _LOGGER.info(
            "Caching %d %s files (CPU, no VAD, soxr %s, %d workers)...",
            len(need_caching),
            language.upper(),
            resample_quality,
            workers,
        )

        batches = [
            need_caching[i : i + _RESAMPLE_BATCH_SIZE]
            for i in range(0, len(need_caching), _RESAMPLE_BATCH_SIZE)
        ]
        batch_args = [
            (batch, str(cache_dir), sample_rate, resample_quality) for batch in batches
        ]

        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(_cache_audio_batch_worker_no_vad, a): i
                    for i, a in enumerate(batch_args)
                }
                done = 0
                for future in as_completed(futures):
                    try:
                        for wav_str, norm_str, spec_str in future.result():
                            if norm_str is not None:
                                audio_map[wav_str] = (norm_str, spec_str)
                            else:
                                _LOGGER.warning(
                                    "Audio cache failed: %s: %s", wav_str, spec_str
                                )
                            done += 1
                            if done % 5000 == 0:
                                _LOGGER.info(
                                    "Cached %d/%d %s",
                                    min(done, len(need_caching)),
                                    len(need_caching),
                                    language.upper(),
                                )
                    except Exception as e:
                        _LOGGER.warning("Audio cache batch failed: %s", e)
        else:
            from piper_train.norm_audio import (  # noqa: PLC0415
                cache_norm_audio_no_vad,
            )

            for i, wav_path_str in enumerate(need_caching):
                try:
                    norm_path, spec_path = cache_norm_audio_no_vad(
                        wav_path_str,
                        cache_dir,
                        sample_rate,
                        resample_quality=resample_quality,
                    )
                    audio_map[wav_path_str] = (str(norm_path), str(spec_path))
                except Exception as e:
                    _LOGGER.warning("Audio cache failed: %s: %s", wav_path_str, e)
                if (i + 1) % 1000 == 0:
                    _LOGGER.info(
                        "Cached %d/%d %s", i + 1, len(need_caching), language.upper()
                    )

    elapsed = time.monotonic() - t0
    _LOGGER.info(
        "Audio caching complete for %s: %d/%d succeeded in %.1fs (%.0f files/s)",
        language.upper(),
        len(audio_map) - (len(phonemized) - len(need_caching)),
        len(need_caching),
        elapsed,
        len(need_caching) / max(elapsed, 0.001),
    )
    return audio_map


# ---------------------------------------------------------------------------
# 8. Assemble utterances for a new language
# ---------------------------------------------------------------------------


def assemble_utterances(
    phonemized: list[dict],
    audio_map: dict[str, tuple[str, str]],
    speaker_id_map: dict[str, int],
    language: str,
    language_id: int,
) -> list[dict]:
    """Assemble final utterance dicts from phonemized data and audio cache."""
    utterances: list[dict] = []
    skipped_audio = 0

    for p in phonemized:
        wav_key = p["wav_path"]
        if wav_key not in audio_map:
            skipped_audio += 1
            continue

        speaker_id_str = p["speaker_id_str"]
        if speaker_id_str not in speaker_id_map:
            skipped_audio += 1
            continue

        norm_path, spec_path = audio_map[wav_key]

        utterances.append(
            {
                "text": p["text"],
                "audio_path": wav_key,
                "speaker": f"{language}_{speaker_id_str}",
                "speaker_id": speaker_id_map[speaker_id_str],
                "language_id": language_id,
                "phonemes": p.get("phonemes", []),
                "phoneme_ids": p["phoneme_ids"],
                "prosody_ids": [],
                "prosody_features": p["prosody_features"],
                "audio_norm_path": norm_path,
                "audio_spec_path": spec_path,
                "f0_path": None,
            }
        )

    _LOGGER.info(
        "Assembled %d %s utterances (%d skipped for missing audio/speaker)",
        len(utterances),
        language.upper(),
        skipped_audio,
    )
    return utterances


# ---------------------------------------------------------------------------
# 9. Process a single new language end-to-end
# ---------------------------------------------------------------------------


def process_new_language(
    entries,
    speaker_counts: dict[str, int],
    language: str,
    language_id: int,
    speaker_id_offset: int,
    ml_id_map: dict[str, list[int]],
    cache_dir: Path,
    sample_rate: int,
    workers: int,
    gpu_spec_device: str | None = None,
    resample_quality: str = "MQ",
    use_pinyin_shortcut: bool = False,
) -> tuple[list[dict], dict[str, int]]:
    """Process a new language: phonemize, cache audio, assemble."""
    if not entries:
        return [], {}

    # Assign speaker IDs
    sorted_speakers = sorted(speaker_counts.items(), key=lambda x: x[1], reverse=True)
    speaker_id_map: dict[str, int] = {}
    for i, (spk, _count) in enumerate(sorted_speakers):
        speaker_id_map[spk] = speaker_id_offset + i

    _LOGGER.info(
        "%s: %d speakers, speaker_id range %d-%d",
        language.upper(),
        len(speaker_id_map),
        speaker_id_offset,
        speaker_id_offset + len(speaker_id_map) - 1,
    )

    # Phase 1: Phonemize
    phonemized, _missing = phonemize_new_language(
        entries,
        language,
        language_id,
        ml_id_map,
        workers,
        use_pinyin_shortcut=use_pinyin_shortcut,
    )
    if not phonemized:
        _LOGGER.warning("No %s utterances phonemized successfully", language.upper())
        return [], speaker_id_map

    # Phase 2: Cache audio (two-phase if GPU available)
    audio_map = cache_audio_parallel(
        phonemized,
        cache_dir,
        sample_rate,
        workers,
        language,
        gpu_spec_device=gpu_spec_device,
        resample_quality=resample_quality,
    )

    # Phase 3: Assemble
    utterances = assemble_utterances(
        phonemized, audio_map, speaker_id_map, language, language_id
    )

    return utterances, speaker_id_map


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Prepare multilingual (6-language) dataset for Piper TTS"
    )
    parser.add_argument(
        "--ja-en-dataset",
        required=True,
        help="Path to existing JA+EN v4 dataset.jsonl",
    )
    parser.add_argument(
        "--zh-aishell3",
        help="Path to AISHELL-3 base directory",
    )
    parser.add_argument(
        "--es-cml-tts",
        help="Path to CML-TTS Spanish base directory",
    )
    parser.add_argument(
        "--fr-cml-tts",
        help="Path to CML-TTS French base directory",
    )
    parser.add_argument(
        "--pt-cml-tts",
        help="Path to CML-TTS Portuguese base directory",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for the merged dataset",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=22050,
        help="Target audio sample rate (default: 22050)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=30,
        help="Number of parallel workers (default: 30)",
    )
    parser.add_argument(
        "--gpu-spec-device",
        default=None,
        help="GPU device for batch spectrogram (e.g. 'cuda:0'). "
        "If not set, uses CPU fallback.",
    )
    parser.add_argument(
        "--resample-quality",
        default="MQ",
        choices=["VHQ", "HQ", "MQ", "LQ"],
        help="soxr resample quality (default: MQ, ~30-40%% faster than HQ)",
    )
    parser.add_argument(
        "--no-pinyin-shortcut",
        action="store_true",
        help="Disable AISHELL-3 pinyin shortcut (use pypinyin instead)",
    )
    args = parser.parse_args()

    # Check that at least one new language is provided
    new_langs = {
        "zh": args.zh_aishell3,
        "es": args.es_cml_tts,
        "fr": args.fr_cml_tts,
        "pt": args.pt_cml_tts,
    }
    active_new_langs = {k: v for k, v in new_langs.items() if v}
    if not active_new_langs:
        _LOGGER.warning("No new language sources provided. Will only copy JA+EN data.")

    # Setup output
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = output_dir / "cache" / str(args.sample_rate)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Get multilingual phoneme ID map
    _LOGGER.info("Building multilingual phoneme ID map for %s...", ALL_LANGUAGES)
    from piper_plus_g2p.encode.id_maps import get_phoneme_id_map  # noqa: PLC0415

    ml_id_map = get_phoneme_id_map("-".join(sorted(ALL_LANGUAGES)))
    _LOGGER.info("Multilingual ID map: %d symbols", len(ml_id_map))

    # Log optimization settings
    _LOGGER.info("=" * 60)
    _LOGGER.info("OPTIMIZATION SETTINGS")
    _LOGGER.info("  Workers: %d", args.workers)
    _LOGGER.info("  GPU spec device: %s", args.gpu_spec_device or "disabled (CPU)")
    _LOGGER.info("  Resample quality: soxr %s", args.resample_quality)
    _LOGGER.info(
        "  ZH pinyin shortcut: %s",
        "disabled" if args.no_pinyin_shortcut else "enabled",
    )
    _LOGGER.info("  VAD: disabled (pre-cleaned corpora)")
    _LOGGER.info("  Phonemize batch size: %d", _PHONEMIZE_BATCH_SIZE)
    _LOGGER.info("=" * 60)

    total_t0 = time.monotonic()

    # ===================================================================
    # Phase 1: Load existing JA+EN data
    # ===================================================================
    _LOGGER.info("=" * 60)
    _LOGGER.info("Loading JA+EN from %s", args.ja_en_dataset)
    ja_en_utts, ja_en_speakers, max_ja_en_speaker_id = load_ja_en_dataset(
        Path(args.ja_en_dataset)
    )

    all_utterances = list(ja_en_utts)
    all_speaker_map: dict[str, int] = dict(ja_en_speakers)
    next_speaker_id = max_ja_en_speaker_id + 1

    lang_stats: dict[str, int] = {
        "ja": sum(1 for u in ja_en_utts if u.get("language_id", 0) == 0),
        "en": sum(1 for u in ja_en_utts if u.get("language_id", 0) == 1),
    }
    lang_speaker_counts: dict[str, int] = {
        "ja": sum(
            1
            for _spk, sid in ja_en_speakers.items()
            if sid < 20  # JA speakers are 0-19 in v4
        ),
        "en": sum(1 for _spk, sid in ja_en_speakers.items() if sid >= 20),
    }

    # ===================================================================
    # Phase 2: Process new languages
    # ===================================================================

    # ZH: AISHELL-3
    if args.zh_aishell3:
        _LOGGER.info("=" * 60)
        _LOGGER.info("Processing ZH (AISHELL-3) from %s", args.zh_aishell3)
        zh_entries, zh_speaker_counts = parse_aishell3(Path(args.zh_aishell3))
        zh_utts, zh_speakers = process_new_language(
            zh_entries,
            zh_speaker_counts,
            language="zh",
            language_id=LANGUAGE_ID_MAP["zh"],
            speaker_id_offset=next_speaker_id,
            ml_id_map=ml_id_map,
            cache_dir=cache_dir,
            sample_rate=args.sample_rate,
            workers=args.workers,
            gpu_spec_device=args.gpu_spec_device,
            resample_quality=args.resample_quality,
            use_pinyin_shortcut=not args.no_pinyin_shortcut,
        )
        all_utterances.extend(zh_utts)
        all_speaker_map.update({f"zh_{k}": v for k, v in zh_speakers.items()})
        if zh_speakers:
            next_speaker_id = max(zh_speakers.values()) + 1
        lang_stats["zh"] = len(zh_utts)
        lang_speaker_counts["zh"] = len(zh_speakers)

    # ES: CML-TTS Spanish
    if args.es_cml_tts:
        _LOGGER.info("=" * 60)
        _LOGGER.info("Processing ES (CML-TTS) from %s", args.es_cml_tts)
        es_entries, es_speaker_counts = parse_cml_tts(Path(args.es_cml_tts), "es")
        es_utts, es_speakers = process_new_language(
            es_entries,
            es_speaker_counts,
            language="es",
            language_id=LANGUAGE_ID_MAP["es"],
            speaker_id_offset=next_speaker_id,
            ml_id_map=ml_id_map,
            cache_dir=cache_dir,
            sample_rate=args.sample_rate,
            workers=args.workers,
            gpu_spec_device=args.gpu_spec_device,
            resample_quality=args.resample_quality,
        )
        all_utterances.extend(es_utts)
        all_speaker_map.update({f"es_{k}": v for k, v in es_speakers.items()})
        if es_speakers:
            next_speaker_id = max(es_speakers.values()) + 1
        lang_stats["es"] = len(es_utts)
        lang_speaker_counts["es"] = len(es_speakers)

    # FR: CML-TTS French
    if args.fr_cml_tts:
        _LOGGER.info("=" * 60)
        _LOGGER.info("Processing FR (CML-TTS) from %s", args.fr_cml_tts)
        fr_entries, fr_speaker_counts = parse_cml_tts(Path(args.fr_cml_tts), "fr")
        fr_utts, fr_speakers = process_new_language(
            fr_entries,
            fr_speaker_counts,
            language="fr",
            language_id=LANGUAGE_ID_MAP["fr"],
            speaker_id_offset=next_speaker_id,
            ml_id_map=ml_id_map,
            cache_dir=cache_dir,
            sample_rate=args.sample_rate,
            workers=args.workers,
            gpu_spec_device=args.gpu_spec_device,
            resample_quality=args.resample_quality,
        )
        all_utterances.extend(fr_utts)
        all_speaker_map.update({f"fr_{k}": v for k, v in fr_speakers.items()})
        if fr_speakers:
            next_speaker_id = max(fr_speakers.values()) + 1
        lang_stats["fr"] = len(fr_utts)
        lang_speaker_counts["fr"] = len(fr_speakers)

    # PT: CML-TTS Portuguese
    if args.pt_cml_tts:
        _LOGGER.info("=" * 60)
        _LOGGER.info("Processing PT (CML-TTS) from %s", args.pt_cml_tts)
        pt_entries, pt_speaker_counts = parse_cml_tts(Path(args.pt_cml_tts), "pt")
        pt_utts, pt_speakers = process_new_language(
            pt_entries,
            pt_speaker_counts,
            language="pt",
            language_id=LANGUAGE_ID_MAP["pt"],
            speaker_id_offset=next_speaker_id,
            ml_id_map=ml_id_map,
            cache_dir=cache_dir,
            sample_rate=args.sample_rate,
            workers=args.workers,
            gpu_spec_device=args.gpu_spec_device,
            resample_quality=args.resample_quality,
        )
        all_utterances.extend(pt_utts)
        all_speaker_map.update({f"pt_{k}": v for k, v in pt_speakers.items()})
        if pt_speakers:
            next_speaker_id = max(pt_speakers.values()) + 1
        lang_stats["pt"] = len(pt_utts)
        lang_speaker_counts["pt"] = len(pt_speakers)

    # ===================================================================
    # Phase 3: Write merged dataset
    # ===================================================================
    _LOGGER.info("=" * 60)
    _LOGGER.info("Writing merged dataset...")

    num_speakers = len(all_speaker_map)

    # Write dataset.jsonl
    dataset_path = output_dir / "dataset.jsonl"
    with open(dataset_path, "w", encoding="utf-8") as f:
        for utt in all_utterances:
            json.dump(utt, f, ensure_ascii=True)
            f.write("\n")
    _LOGGER.info("Wrote %s (%d utterances)", dataset_path, len(all_utterances))

    # Build speaker_id_map for config
    config_speaker_map: dict[str, int] = {}
    for name, sid in all_speaker_map.items():
        config_speaker_map[name] = sid

    # Determine active languages
    active_languages = [lang for lang in ALL_LANGUAGES if lang_stats.get(lang, 0) > 0]

    # Build language_id_map
    config_language_id_map = {lang: LANGUAGE_ID_MAP[lang] for lang in active_languages}

    # Write config.json
    config = {
        "dataset": "multilingual-6lang",
        "audio": {"sample_rate": args.sample_rate, "quality": "medium"},
        "language": {"code": "-".join(active_languages)},
        "inference": {"noise_scale": 0.667, "length_scale": 1, "noise_w": 0.8},
        "phoneme_type": "multilingual",
        "phoneme_map": {},
        "phoneme_id_map": ml_id_map,
        "num_symbols": len(ml_id_map),
        "num_speakers": num_speakers,
        "speaker_id_map": config_speaker_map,
        "num_languages": len(active_languages),
        "language_id_map": config_language_id_map,
        "prosody_num_symbols": 11,
        "prosody_id_map": {str(i): [i] for i in range(11)},
    }

    config_path = output_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=True, indent=4)

    # ===================================================================
    # Summary
    # ===================================================================
    total_elapsed = time.monotonic() - total_t0
    _LOGGER.info("=" * 60)
    _LOGGER.info("DATASET SUMMARY")
    _LOGGER.info("=" * 60)
    _LOGGER.info("Output: %s", output_dir)
    _LOGGER.info("Total utterances: %d", len(all_utterances))
    _LOGGER.info("Total speakers: %d", num_speakers)
    _LOGGER.info("Total symbols: %d", len(ml_id_map))
    _LOGGER.info(
        "Languages: %d (%s)", len(active_languages), ", ".join(active_languages)
    )
    _LOGGER.info("")
    _LOGGER.info("Per-language breakdown:")
    _LOGGER.info("  %-4s  %8s  %8s", "Lang", "Utts", "Speakers")
    _LOGGER.info("  %-4s  %8s  %8s", "----", "--------", "--------")
    for lang in ALL_LANGUAGES:
        utt_count = lang_stats.get(lang, 0)
        spk_count = lang_speaker_counts.get(lang, 0)
        if utt_count > 0:
            _LOGGER.info("  %-4s  %8d  %8d", lang.upper(), utt_count, spk_count)
    _LOGGER.info("")
    _LOGGER.info(
        "Config: %s (speakers=%d, symbols=%d, languages=%d)",
        config_path,
        num_speakers,
        len(ml_id_map),
        len(active_languages),
    )
    _LOGGER.info("Total processing time: %.1f minutes", total_elapsed / 60)


if __name__ == "__main__":
    main()
