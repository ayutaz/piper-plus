"""Extract speaker embeddings using CAM++ ONNX model.

Usage:
    # Single WAV file
    uv run python -m piper_train.extract_speaker_embedding \
        --encoder models/campplus.onnx --audio ref.wav --output speaker.npy

    # Directory of WAV files (average embedding)
    uv run python -m piper_train.extract_speaker_embedding \
        --encoder models/campplus.onnx --audio-dir wavs/ --output speaker.npy

    # Per-utterance (recommended for zero-shot training)
    uv run python -m piper_train.extract_speaker_embedding \
        --encoder models/campplus.onnx \
        --dataset-dir /data/piper/dataset-moe-speech-20speakers \
        --per-utterance --batch-size 64 --num-workers 12

    # Per-speaker (for inference reference)
    uv run python -m piper_train.extract_speaker_embedding \
        --encoder models/campplus.onnx \
        --dataset-dir /data/piper/dataset-moe-speech-20speakers \
        --output-dir /path/to/embeddings
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import numpy as np
import onnxruntime
import soundfile as sf
import soxr
import torch
import torchaudio


_LOGGER = logging.getLogger(__name__)

_RESAMPLER_CACHE: dict[tuple[int, int], torchaudio.transforms.Resample] = {}


def _get_resampler(source_sr: int, target_sr: int) -> torchaudio.transforms.Resample:
    """キャッシュ済みResamplerを取得する。毎回フィルタ再計算を避ける。"""
    key = (source_sr, target_sr)
    if key not in _RESAMPLER_CACHE:
        _RESAMPLER_CACHE[key] = torchaudio.transforms.Resample(source_sr, target_sr)
    return _RESAMPLER_CACHE[key]


def preprocess_audio(wav_path: str | Path, target_sr: int = 16000) -> np.ndarray:
    """WAVファイルを読み込み、Fbank特徴量に変換する。

    Args:
        wav_path: Path to WAV file.
        target_sr: Target sample rate.

    Returns:
        fbank: np.ndarray, shape [T, 80], float32
    """
    audio_data, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    # Resample to target_sr
    if sr != target_sr:
        audio_data = soxr.resample(audio_data, sr, target_sr, quality="HQ")

    waveform = torch.from_numpy(audio_data).unsqueeze(0)

    # Compute 80-dim Fbank
    fbank = torchaudio.compliance.kaldi.fbank(
        waveform,
        num_mel_bins=80,
        frame_length=25.0,
        frame_shift=10.0,
        sample_frequency=target_sr,
    )

    # Mean subtraction (CMVN)
    fbank = fbank - fbank.mean(dim=0, keepdim=True)

    return fbank.numpy()


def _load_audio_from_pt(
    pt_path: str | Path, source_sr: int, target_sr: int = 16000
) -> np.ndarray:
    """PTファイルから音声を読み込み、Fbank特徴量に変換する。

    Args:
        pt_path: Path to .pt audio tensor file.
        source_sr: Sample rate of the stored audio tensor.
        target_sr: Target sample rate for Fbank extraction.

    Returns:
        fbank: np.ndarray, shape [T, 80], float32
    """
    audio_tensor = torch.load(pt_path, weights_only=True, map_location="cpu", mmap=True)
    if audio_tensor.dim() == 1:
        audio_tensor = audio_tensor.unsqueeze(0)

    # Resample
    resampler = _get_resampler(source_sr, target_sr)
    audio_tensor = resampler(audio_tensor)

    # Compute 80-dim Fbank
    fbank = torchaudio.compliance.kaldi.fbank(
        audio_tensor,
        num_mel_bins=80,
        frame_length=25.0,
        frame_shift=10.0,
        sample_frequency=target_sr,
    )

    # Mean subtraction (CMVN)
    fbank = fbank - fbank.mean(dim=0, keepdim=True)

    return fbank.numpy()


def extract_embedding(
    session: onnxruntime.InferenceSession, fbank: np.ndarray
) -> np.ndarray:
    """Fbank特徴量からspeaker embeddingを抽出する。

    Args:
        session: ONNX Runtime session.
        fbank: shape [T, 80], float32.

    Returns:
        embedding: shape [192], float32, L2正規化済み
    """
    fbank_input = np.expand_dims(fbank, axis=0).astype(np.float32)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: fbank_input})
    embedding = np.squeeze(outputs[0])
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    return embedding


def extract_from_files(
    session: onnxruntime.InferenceSession, wav_paths: list[str | Path]
) -> np.ndarray:
    """複数WAVファイルからembeddingを抽出し、平均化する。

    Args:
        session: ONNX Runtime session.
        wav_paths: List of WAV file paths.

    Returns:
        embedding: shape [192], float32, L2正規化済み
    """
    embeddings = []
    for wav_path in wav_paths:
        fbank = preprocess_audio(wav_path)
        emb = extract_embedding(session, fbank)
        embeddings.append(emb)
    avg_embedding = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(avg_embedding)
    if norm > 0:
        avg_embedding = avg_embedding / norm
    return avg_embedding


def extract_from_dataset(
    session: onnxruntime.InferenceSession,
    dataset_dir: str | Path,
    output_dir: str | Path,
    max_utterances: int = 10,
    min_duration: float = 3.0,
    source_sr: int = 22050,
    workers: int = 4,
) -> None:
    """dataset.jsonl から話者ごとにembeddingを一括抽出する（平均化モード）。"""
    jsonl_path = Path(dataset_dir) / "dataset.jsonl"
    if not jsonl_path.exists():
        msg = "dataset.jsonl not found in " + str(dataset_dir)
        raise FileNotFoundError(msg)

    # Parse dataset
    speaker_utterances: dict[int, list[str]] = {}
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            utt = json.loads(line)
            speaker_id = utt.get("speaker_id", 0)
            audio_path = utt.get("audio_norm_path")
            if audio_path:
                speaker_utterances.setdefault(speaker_id, []).append(audio_path)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for speaker_id, audio_paths in sorted(speaker_utterances.items()):
        # Filter by duration
        valid_paths = []
        for pt_path in audio_paths:
            try:
                audio_tensor = torch.load(
                    pt_path, weights_only=True, map_location="cpu"
                )
                num_samples = audio_tensor.shape[-1]
                duration = num_samples / source_sr
                if duration >= min_duration:
                    valid_paths.append(pt_path)
            except Exception:
                _LOGGER.warning("Failed to load, skipping: %s", pt_path)

        if not valid_paths:
            _LOGGER.warning(
                "Speaker %d: no valid utterances (>= %.1fs), skipping",
                speaker_id,
                min_duration,
            )
            continue

        selected = valid_paths[:max_utterances]
        _LOGGER.info(
            "Speaker %d: %d utterances (selected %d of %d valid, %d total)",
            speaker_id,
            len(audio_paths),
            len(selected),
            len(valid_paths),
            len(audio_paths),
        )

        # Extract embeddings
        embeddings = []
        for pt_path in selected:
            fbank = _load_audio_from_pt(pt_path, source_sr=source_sr)
            emb = extract_embedding(session, fbank)
            embeddings.append(emb)

        avg_embedding = np.mean(embeddings, axis=0)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm

        output_path = output_dir / f"speaker_{speaker_id}.npy"
        np.save(str(output_path), avg_embedding)
        _LOGGER.info(
            "Saved: %s (norm=%.4f)", output_path, np.linalg.norm(avg_embedding)
        )


class _FbankDataset(torch.utils.data.Dataset):
    """DataLoader用Dataset: PTファイルからFbank特徴量を並列抽出する。

    各ワーカープロセスで独立にCPU前処理（torch.load → resample → fbank）を実行し、
    メインプロセスでONNX推論に個別に渡す（ゼロパディング回避）。
    """

    def __init__(
        self, items: list[tuple[int, Path, str]], source_sr: int, target_sr: int = 16000
    ):
        self.items = items
        self.source_sr = source_sr
        self.target_sr = target_sr
        self.resampler = torchaudio.transforms.Resample(source_sr, target_sr)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> tuple[int, torch.Tensor, str, bool]:
        entry_idx, pt_path, stem = self.items[idx]
        try:
            audio_tensor = torch.load(
                pt_path, weights_only=True, map_location="cpu", mmap=True
            )
            if audio_tensor.dim() == 1:
                audio_tensor = audio_tensor.unsqueeze(0)
            audio_tensor = self.resampler(audio_tensor)

            fbank = torchaudio.compliance.kaldi.fbank(
                audio_tensor,
                num_mel_bins=80,
                frame_length=25.0,
                frame_shift=10.0,
                sample_frequency=self.target_sr,
            )
            fbank = fbank - fbank.mean(dim=0, keepdim=True)
            return (entry_idx, fbank, stem, True)
        except Exception as e:
            _LOGGER.warning("Worker failed to load %s: %s", pt_path, e)
            return (entry_idx, torch.zeros(1, 80), stem, False)


def _collate_fbanks(
    batch: list[tuple[int, torch.Tensor, str, bool]],
) -> tuple[list[int], list[np.ndarray], list[str], list[bool]]:
    """Fbank特徴量をリストのまま返す（ゼロパディングなし）。

    以前はゼロパディングしてバッチテンソルを作成していたが、
    CAM++が零埋めフレームを実データとして処理するため、
    speaker embeddingが破損する問題があった。
    各発話を個別にONNX推論することで正確なembeddingを保証する。
    """
    indices, fbanks, stems, valids = zip(*batch, strict=False)
    fbank_list = [f.numpy().astype(np.float32) for f in fbanks]
    return (list(indices), fbank_list, list(stems), list(valids))


def _filter_for_shard(items: list, shard: int, num_shards: int) -> list:
    """Filter a list by modulo index for parallel multi-shard processing.

    Returns ``items[i]`` for which ``i % num_shards == shard``. The filtered
    sub-lists across ``shard in range(num_shards)`` form a disjoint partition
    whose union equals ``items``.

    When ``num_shards <= 1`` returns the original list unchanged.
    """
    if num_shards <= 1:
        return list(items)
    if not 0 <= shard < num_shards:
        msg = f"shard must be in [0, {num_shards}), got {shard}"
        raise ValueError(msg)
    return [item for i, item in enumerate(items) if i % num_shards == shard]


def _write_updated_jsonl(dataset_dir: Path, entries: list[dict]) -> None:
    """dataset.jsonlをバックアップして更新する。"""
    output_jsonl = dataset_dir / "dataset.jsonl"
    backup_path = dataset_dir / "dataset.jsonl.bak"
    shutil.copy2(output_jsonl, backup_path)
    _LOGGER.info("Backed up original to: %s", backup_path)

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for entry in entries:
            json.dump(entry, f, ensure_ascii=True)
            f.write("\n")

    _LOGGER.info(
        "Updated dataset.jsonl with speaker_embedding_path (%d entries)", len(entries)
    )


def extract_per_utterance(
    session: onnxruntime.InferenceSession,
    dataset_dir: str | Path,
    output_dir: str | Path | None = None,
    source_sr: int = 22050,
    batch_size: int = 64,
    num_workers: int = 12,
    shard: int = 0,
    num_shards: int = 1,
    update_jsonl: bool = True,
) -> None:
    """dataset.jsonl の各発話ごとにembeddingを抽出し、dataset.jsonlを更新する。

    各発話を個別にONNX推論する（ゼロパディングによるembedding破損を回避）。
    DataLoaderの並列CPU前処理（fbank抽出）はbatch_size単位で維持するため、
    CPU前処理のスループットは変わらない。

    最適化:
    1. DataLoader (num_workers) でCPU前処理を並列化 (GIL回避)
    2. 個別ONNX推論でゼロパディングによるembedding破損を回避
    3. 既存embedding事前キャッシュでファイルI/O削減
    4. Resamplerキャッシュでフィルタ再計算を回避

    Args:
        session: ONNX Runtime session.
        dataset_dir: Dataset directory containing dataset.jsonl.
        output_dir: Output directory for speaker embedding .npy files.
        source_sr: Sample rate of .pt audio files in the dataset.
        batch_size: Batch size for DataLoader CPU preprocessing.
        num_workers: Number of DataLoader workers for CPU preprocessing.
    """
    dataset_dir = Path(dataset_dir)
    jsonl_path = dataset_dir / "dataset.jsonl"
    if not jsonl_path.exists():
        msg = "dataset.jsonl not found in " + str(dataset_dir)
        raise FileNotFoundError(msg)

    emb_dir = dataset_dir / "speaker_embeddings"
    emb_dir.mkdir(parents=True, exist_ok=True)

    # Load all entries
    entries: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            p = line.strip()
            if p:
                entries.append(json.loads(p))

    _LOGGER.info("Total utterances: %d", len(entries))

    # Pre-cache existing embeddings
    existing_stems = {p.stem for p in emb_dir.glob("*.npy")}
    _LOGGER.info("Already extracted: %d embeddings (pre-cached)", len(existing_stems))

    # Build items to extract
    items_to_extract: list[tuple[int, Path, str]] = []
    skipped = 0
    fail = 0
    for i, utt in enumerate(entries):
        audio_norm_path = utt.get("audio_norm_path")
        if not audio_norm_path:
            fail += 1
            continue
        pt_path = Path(audio_norm_path)
        stem = pt_path.stem
        npy_rel = "speaker_embeddings/" + stem + ".npy"
        utt["speaker_embedding_path"] = npy_rel

        if stem in existing_stems:
            skipped += 1
            continue

        if not pt_path.is_absolute():
            pt_path = dataset_dir / pt_path

        if not pt_path.exists():
            _LOGGER.warning("File not found, skipping: %s", pt_path)
            fail += 1
            continue

        items_to_extract.append((i, pt_path, stem))

    _LOGGER.info(
        "To extract: %d, skipped (existing): %d, failed: %d",
        len(items_to_extract),
        skipped,
        fail,
    )

    if num_shards > 1:
        before = len(items_to_extract)
        items_to_extract = _filter_for_shard(items_to_extract, shard, num_shards)
        _LOGGER.info(
            "Shard %d/%d: filtered %d -> %d items",
            shard, num_shards, before, len(items_to_extract),
        )

    if not items_to_extract:
        _LOGGER.info("All embeddings already extracted (or shard empty)")
        if update_jsonl:
            _write_updated_jsonl(dataset_dir, entries)
        return

    # Create dataset and dataloader
    dataset = _FbankDataset(items_to_extract, source_sr=source_sr)
    loader_kwargs: dict = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "collate_fn": _collate_fbanks,
        "pin_memory": False,
    }
    if num_workers > 0:
        loader_kwargs["prefetch_factor"] = 4
        loader_kwargs["persistent_workers"] = False

    loader = torch.utils.data.DataLoader(dataset, **loader_kwargs)

    input_name = session.get_inputs()[0].name
    success = 0
    total_batches = len(loader)

    _LOGGER.info(
        "Starting batch extraction: %d batches (batch_size=%d, workers=%d)",
        total_batches,
        batch_size,
        num_workers,
    )

    for batch_idx, (indices, fbank_list, stems, valids) in enumerate(loader):
        for _j, (_entry_idx, fbank, stem, valid) in enumerate(
            zip(indices, fbank_list, stems, valids, strict=False)
        ):
            if not valid:
                fail += 1
                continue

            fbank_input = np.expand_dims(fbank, axis=0)
            embedding = session.run(None, {input_name: fbank_input})[0]
            embedding = np.squeeze(embedding)
            norm = np.linalg.norm(embedding)
            if norm > 1e-8:
                embedding = embedding / norm
            npy_path = emb_dir / (stem + ".npy")
            np.save(str(npy_path), embedding)
            success += 1

        if (batch_idx + 1) % 50 == 0:
            _LOGGER.info(
                "Batch %d/%d (success=%d, fail=%d)",
                batch_idx + 1,
                total_batches,
                success,
                fail,
            )

    _LOGGER.info(
        "Extraction complete: %d success, %d failed out of %d total",
        success,
        fail,
        len(entries),
    )

    if update_jsonl:
        _write_updated_jsonl(dataset_dir, entries)
    else:
        _LOGGER.info("Skipping dataset.jsonl update (--no-update-jsonl)")


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        prog="piper_train.extract_speaker_embedding",
        description="Extract speaker embeddings using CAM++ ONNX model",
    )
    parser.add_argument("--encoder", required=True, help="Path to CAM++ ONNX model")
    parser.add_argument("--audio", help="Single WAV file to process")
    parser.add_argument(
        "--audio-dir", help="Directory of WAV files (average embedding)"
    )
    parser.add_argument("--dataset-dir", help="Dataset directory with dataset.jsonl")
    parser.add_argument(
        "--output", help="Output .npy file path (for --audio / --audio-dir)"
    )
    parser.add_argument("--output-dir", help="Output directory (for --dataset-dir)")
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel workers"
    )
    parser.add_argument(
        "--max-utterances",
        type=int,
        default=10,
        help="Max utterances per speaker in dataset mode",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=3.0,
        help="Min duration in seconds for dataset mode",
    )
    parser.add_argument(
        "--source-sample-rate",
        type=int,
        default=22050,
        help="Source sample rate for .pt files in dataset mode",
    )
    parser.add_argument(
        "--per-utterance",
        action="store_true",
        help="Extract per-utterance embeddings (recommended for zero-shot TTS training). Updates dataset.jsonl in-place with speaker_embedding_path.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Batch size for per-utterance ONNX inference (default: 64)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=12,
        help="Number of DataLoader workers for CPU preprocessing (default: 12)",
    )
    parser.add_argument(
        "--shard",
        type=int,
        default=0,
        help="Shard index (0-based) for parallel processing across multiple GPUs",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=1,
        help="Total number of shards (1 = no sharding)",
    )
    parser.add_argument(
        "--no-update-jsonl",
        action="store_true",
        help="Skip in-place dataset.jsonl update. Use for sharded runs; run a final pass without this flag to update jsonl",
    )

    args = parser.parse_args()

    # Validate arguments
    modes = sum(
        [
            args.audio is not None,
            args.audio_dir is not None,
            args.dataset_dir is not None,
        ]
    )
    if modes == 0:
        parser.error("One of --audio, --audio-dir, or --dataset-dir is required")
    if modes > 1:
        parser.error(
            "Only one of --audio, --audio-dir, or --dataset-dir can be specified"
        )

    if (args.audio or args.audio_dir) and not args.output:
        parser.error("--output is required with --audio or --audio-dir")

    if args.dataset_dir and not args.per_utterance and not args.output_dir:
        parser.error(
            "--output-dir is required with --dataset-dir (unless --per-utterance)"
        )

    # Create ONNX session
    sess_options = onnxruntime.SessionOptions()
    sess_options.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    )
    sess_options.enable_mem_reuse = True
    sess_options.enable_mem_pattern = True

    cuda_provider_options = {
        "arena_extend_strategy": "kSameAsRequested",
        "do_copy_in_default_stream": False,
    }

    if "CUDAExecutionProvider" in onnxruntime.get_available_providers():
        providers = [
            ("CUDAExecutionProvider", cuda_provider_options),
            "CPUExecutionProvider",
        ]
        _LOGGER.info("Using GPU (CUDAExecutionProvider)")
    else:
        providers = ["CPUExecutionProvider"]
        _LOGGER.info("Using CPU (CUDAExecutionProvider not available)")

    session = onnxruntime.InferenceSession(
        args.encoder, sess_options, providers=providers
    )
    _LOGGER.info("Loaded speaker encoder: %s", args.encoder)

    if args.audio:
        fbank = preprocess_audio(args.audio)
        embedding = extract_embedding(session, fbank)
        np.save(args.output, embedding)
        _LOGGER.info(
            "Saved: %s (shape=%s, norm=%.4f)",
            args.output,
            embedding.shape,
            np.linalg.norm(embedding),
        )
    elif args.audio_dir:
        audio_dir = Path(args.audio_dir)
        wav_files = sorted(
            list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.WAV"))
        )
        if not wav_files:
            _LOGGER.error("No WAV files found in %s", audio_dir)
            return
        _LOGGER.info("Found %d WAV files in %s", len(wav_files), audio_dir)
        embedding = extract_from_files(session, wav_files)
        np.save(args.output, embedding)
        _LOGGER.info(
            "Saved: %s (shape=%s, norm=%.4f)",
            args.output,
            embedding.shape,
            np.linalg.norm(embedding),
        )
    elif args.dataset_dir:
        dataset_dir = Path(args.dataset_dir)
        if args.per_utterance:
            extract_per_utterance(
                session,
                dataset_dir=dataset_dir,
                output_dir=args.output_dir,
                source_sr=args.source_sample_rate,
                batch_size=args.batch_size,
                num_workers=args.num_workers,
                shard=args.shard,
                num_shards=args.num_shards,
                update_jsonl=not args.no_update_jsonl,
            )
        else:
            extract_from_dataset(
                session,
                dataset_dir=dataset_dir,
                output_dir=args.output_dir,
                max_utterances=args.max_utterances,
                min_duration=args.min_duration,
                source_sr=args.source_sample_rate,
            )


if __name__ == "__main__":
    main()
