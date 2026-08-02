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
        --dataset-dir "${DATASET_DIR}" \
        --per-utterance --batch-size 64 --num-workers 12

    # Per-speaker (for inference reference)
    uv run python -m piper_train.extract_speaker_embedding \
        --encoder models/campplus.onnx \
        --dataset-dir "${DATASET_DIR}" \
        --output-dir /path/to/embeddings
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from pathlib import Path

import numpy as np
import onnxruntime
import soundfile as sf
import torch
import torchaudio

from piper_train.norm_audio import load_audio_norm_tensor


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
        import soxr  # noqa: PLC0415 — lazy import (optional runtime dependency)

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
    audio_tensor = load_audio_norm_tensor(Path(pt_path))
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
                audio_tensor = load_audio_norm_tensor(Path(pt_path))
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

    PIPER_PLUS_EMB_FIXED_FRAMES=N (default 0=off) で固定フレーム長にクロップ/pad する。
    N=400 (4秒 @ 16kHz, 10ms hop) が VoxCeleb 系の標準値。**A' 案**:
    - 発話 <= N frames: 全体を 1 chunk として reflect pad
    - 発話 > N frames: 重複ありで N frames の chunks に分割 (hop=N//2 = 2秒)
      → 全 chunk の embedding を後段で L2 正規化平均、話者情報の全体を保持
    (A 案の中央 crop 単発は cosine 0.97 に劣化するため、A' で情報損失を防ぐ)
    """

    def __init__(
        self,
        items: list[tuple[int, Path, str]],
        source_sr: int,
        target_sr: int = 16000,
        fixed_frames: int = 0,
        chunk_hop_ratio: float = 0.5,
    ):
        self.items = items
        self.source_sr = source_sr
        self.target_sr = target_sr
        self.resampler = torchaudio.transforms.Resample(source_sr, target_sr)
        self.fixed_frames = fixed_frames
        # chunk hop: fixed_frames の何分の何ずつずらして chunk を刻むか (0.5 = 50% overlap)
        self.chunk_hop = (
            max(1, int(fixed_frames * chunk_hop_ratio)) if fixed_frames > 0 else 0
        )

    def __len__(self) -> int:
        return len(self.items)

    def _reflect_pad_to(self, fbank: torch.Tensor, target: int) -> torch.Tensor:
        T = fbank.shape[0]
        if T == target:
            return fbank
        if T > target:
            return fbank[:target]
        fb_t = fbank.transpose(0, 1).unsqueeze(0)  # [1, mel, T]
        pad_amount = target - T
        if pad_amount < T:
            fb_padded = torch.nn.functional.pad(fb_t, (0, pad_amount), mode="reflect")
        else:
            repeat = (target // T) + 1
            fb_padded = fb_t.repeat(1, 1, repeat)[:, :, :target]
        return fb_padded.squeeze(0).transpose(0, 1)  # [target, mel]

    def _to_chunks(self, fbank: torch.Tensor) -> torch.Tensor:
        """全 fbank を [n_chunks, fixed_frames, mel] に分割 (overlap 50%、reflect pad)。

        **A'' 案**: 2-4s 発話 (T < target で 1 chunk しか作れない) は精度落ちる (cosine 0.98)
        ため、min_chunks=2 を強制。 T < target なら reflect pad で target まで拡張しつつ、
        オリジナルの pad 位置をずらして 2 chunks 生成することで情報冗長性を確保。
        """
        target = self.fixed_frames
        T = fbank.shape[0]
        if T <= target:
            # T <= target: 情報が少ないので同じ fbank を先頭寄せ・末尾寄せの 2 chunk に
            padded = self._reflect_pad_to(fbank, target)  # [target, mel]
            if T <= target // 2:
                # 極端に短い発話は 1 chunk で十分 (情報の冗長性を上げる意味がない)
                return padded.unsqueeze(0)
            # 2 chunk: (a) 先頭寄せ (original+reflect後半) (b) 末尾寄せ (reflect前半+original)
            # padded の中で original が異なる位置を占める 2 バリアントを作る
            # variant a: 先頭に original、末尾を reflect (現行 _reflect_pad_to の挙動)
            variant_a = padded
            # variant b: 末尾に original、先頭を reflect (T frames を末尾に配置)
            fb_t = fbank.transpose(0, 1).unsqueeze(0)
            pad_amount = target - T
            if pad_amount < T:
                b_padded = torch.nn.functional.pad(
                    fb_t, (pad_amount, 0), mode="reflect"
                )
            else:
                rep = (target // T) + 1
                b_padded = fb_t.repeat(1, 1, rep)[:, :, -target:]
            variant_b = b_padded.squeeze(0).transpose(0, 1)
            return torch.stack([variant_a, variant_b], dim=0)  # [2, target, mel]
        # T > target: 50% overlap で chunk 化
        starts = list(range(0, T - target + 1, self.chunk_hop))
        # 末尾の余り frames をカバー: 最後の start が T - target まで届かないなら追加
        if starts[-1] + target < T:
            starts.append(T - target)
        chunks = torch.stack([fbank[s : s + target] for s in starts], dim=0)
        return chunks  # [n_chunks, target, mel]

    def __getitem__(self, idx: int) -> tuple[int, torch.Tensor, str, bool]:
        entry_idx, pt_path, stem = self.items[idx]
        try:
            audio_tensor = load_audio_norm_tensor(Path(pt_path))
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
            if self.fixed_frames > 0:
                fbank = self._to_chunks(fbank)  # [n_chunks, target, mel]
            return (entry_idx, fbank, stem, True)
        except Exception as e:
            _LOGGER.warning("Worker failed to load %s: %s", pt_path, e)
            if self.fixed_frames > 0:
                zero = torch.zeros(1, self.fixed_frames, 80)
            else:
                zero = torch.zeros(1, 80)
            return (entry_idx, zero, stem, False)


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


def _collate_fbanks_chunked(
    batch: list[tuple[int, torch.Tensor, str, bool]],
) -> tuple[list[int], np.ndarray, list[int], list[str], list[bool]]:
    """A'案: 各発話の chunks [n_chunks_i, T, mel] を batch flatten して [Σn, T, mel] に。

    後段で chunks_per_utt を使って各発話ぶんの embedding を分離・平均する。
    """
    indices, fbank_chunks, stems, valids = zip(*batch, strict=False)
    chunks_per_utt = [f.shape[0] for f in fbank_chunks]
    # 各 chunk は同一 shape [T, mel] なので concat
    flat = torch.cat([f for f in fbank_chunks], dim=0).numpy().astype(np.float32)
    # 形状: [Σn_chunks, T, mel]
    return (list(indices), flat, chunks_per_utt, list(stems), list(valids))


def _collate_fbanks_padded(
    batch: list[tuple[int, torch.Tensor, str, bool]],
) -> tuple[list[int], np.ndarray, np.ndarray, list[str], list[bool]]:
    """Fbank をバッチ内最大長にゼロパディングして真の GPU バッチ推論を可能にする。

    パディング分は L2 正規化前の embedding 出力を有効フレーム数で補正する仕組みは
    持たない (CAM++ の statistical pooling は 0-frame で mean が薄まるが、items を
    fbank 長 ~= audio_norm ファイルサイズ順に事前ソートしてあるので、バッチ内の
    長さ差は <5% に抑えられ実質破損なし。--per-utterance-nopad との精度差は
    以前の cosine similarity 計測で 0.9995 以上を確認)。
    """
    indices, fbanks, stems, valids = zip(*batch, strict=False)
    max_frames = max(f.shape[0] for f in fbanks)
    n_mels = fbanks[0].shape[1]
    padded = np.zeros((len(fbanks), max_frames, n_mels), dtype=np.float32)
    lengths = np.zeros(len(fbanks), dtype=np.int32)
    for i, f in enumerate(fbanks):
        t = f.shape[0]
        padded[i, :t] = f.numpy().astype(np.float32)
        lengths[i] = t
    return (list(indices), padded, lengths, list(stems), list(valids))


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
    fixed_frames: int = 400,
    chunk_batch: int = 128,
    use_batch_infer: bool = False,
    use_length_sort: bool | None = None,
) -> None:
    """dataset.jsonl の各発話ごとにembeddingを抽出し、dataset.jsonlを更新する。

    **v2 (2026-07-09) 以降のデフォルト**: A'' 案 (chunked mean pooling) を default 有効化。
    ``fixed_frames=400`` (4s @16kHz、VoxCeleb 標準) + ``chunk_batch=128`` (GPU batched
    inference) で 9-12x 高速化 (500k 発話で 9h → 45-60min)。 精度は A''案で cosine
    similarity 0.995+ を維持済み (単発話 embedding が per-utt 経路と一致することを
    test_extract_speaker_embedding.py で検証)。

    経路の選び方:
    - **デフォルト (fixed_frames=400)**: A'' chunked、 GPU batched inference (最速、 推奨)
    - ``fixed_frames=0``: legacy per-utterance 経路 (IO binding、 個別推論、 backward compat)
    - ``use_batch_infer=True``: padded batch 推論 (fixed_frames=0 前提、 精度リスクあり)

    Backward compat: 環境変数 ``PIPER_PLUS_EMB_FIXED_FRAMES`` / ``PIPER_PLUS_EMB_BATCH_INFER`` /
    ``PIPER_PLUS_EMB_LENGTH_SORT`` が set されていれば CLI 引数を上書きする (v1 挙動保持)。

    最適化:
    1. DataLoader (num_workers) でCPU前処理を並列化 (GIL回避)
    2. GPU batched inference で chunk 単位に ONNX 推論をまとめる (fixed_frames > 0 時)
    3. 既存embedding事前キャッシュでファイルI/O削減
    4. Resamplerキャッシュでフィルタ再計算を回避
    5. 長さソート (bucket) でバッチ内 pad 差を最小化 (fixed_frames > 0 で自動有効)

    Args:
        session: ONNX Runtime session.
        dataset_dir: Dataset directory containing dataset.jsonl.
        output_dir: Output directory for speaker embedding .npy files.
        source_sr: Sample rate of .pt audio files in the dataset.
        batch_size: Batch size for DataLoader CPU preprocessing.
        num_workers: Number of DataLoader workers for CPU preprocessing.
        fixed_frames: Fixed frame length (400 = 4s @16kHz, default). Set 0 to disable
            (fall back to legacy per-utt inference).
        chunk_batch: Chunk batch size for GPU inference (default 128, A100/A6000 safe).
        use_batch_infer: Force legacy padded batch inference (only when fixed_frames=0).
        use_length_sort: Force length-based bucket sorting. None=auto (True if
            ``fixed_frames > 0`` or ``use_batch_infer=True``).
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
            shard,
            num_shards,
            before,
            len(items_to_extract),
        )

    if not items_to_extract:
        _LOGGER.info("All embeddings already extracted (or shard empty)")
        if update_jsonl:
            _write_updated_jsonl(dataset_dir, entries)
        return

    # items を fbank 長 (audio_norm .pt サイズ) でソートしてバッチ内の pad 差を最小化
    # v2 default: fixed_frames=400 (A''案) + chunk_batch=128 で GPU batched inference
    # 環境変数は backward compat のため CLI 引数を上書きする (v1 挙動保持)
    #   PIPER_PLUS_EMB_FIXED_FRAMES=N     -- CLI --fixed-frames を上書き
    #   PIPER_PLUS_EMB_BATCH_INFER=1      -- CLI --batch-infer-padded を上書き
    #   PIPER_PLUS_EMB_LENGTH_SORT=1      -- CLI --length-sort を強制有効化
    env_fixed_frames = os.environ.get("PIPER_PLUS_EMB_FIXED_FRAMES")
    if env_fixed_frames is not None:
        fixed_frames = int(env_fixed_frames)
    env_batch_infer = os.environ.get("PIPER_PLUS_EMB_BATCH_INFER")
    if env_batch_infer is not None:
        use_batch_infer = env_batch_infer == "1"
    env_length_sort = os.environ.get("PIPER_PLUS_EMB_LENGTH_SORT")
    if use_length_sort is None:
        # auto: fixed_frames > 0 なら bucket sort (chunk 化と直交だが数値的に無害)
        use_length_sort = fixed_frames > 0 or use_batch_infer
    if env_length_sort == "1":
        use_length_sort = True
    if use_batch_infer or use_length_sort:
        items_to_extract.sort(key=lambda it: it[1].stat().st_size)
        _LOGGER.info(
            "Sorted %d items by audio length (bucket=%s, fixed=%s)",
            len(items_to_extract),
            use_length_sort,
            fixed_frames,
        )

    # Create dataset and dataloader
    dataset = _FbankDataset(
        items_to_extract, source_sr=source_sr, fixed_frames=fixed_frames
    )
    # 固定長 A'案 (fixed_frames > 0): chunk 分割済みなので chunked collate
    # batch_infer のみ: padded collate (zero pad で pool 破損リスクあり)
    # それ以外: list を保つ per-utt collate
    if fixed_frames > 0:
        _collate_choice = _collate_fbanks_chunked
    elif use_batch_infer:
        _collate_choice = _collate_fbanks_padded
    else:
        _collate_choice = _collate_fbanks
    loader_kwargs: dict = {
        "batch_size": batch_size,
        "num_workers": num_workers,
        "collate_fn": _collate_choice,
        "pin_memory": False,
    }
    if num_workers > 0:
        loader_kwargs["prefetch_factor"] = 4
        loader_kwargs["persistent_workers"] = False

    loader = torch.utils.data.DataLoader(dataset, **loader_kwargs)

    input_name = session.get_inputs()[0].name
    success = 0
    total_batches = len(loader)

    mode_label = "per-utt"
    if fixed_frames > 0:
        mode_label = f"chunked-{fixed_frames} (A'案 overlap 50%)"
    elif use_batch_infer:
        mode_label = "batch (pad, 精度リスクあり)"
    _LOGGER.info(
        "Starting %s extraction: %d batches (batch_size=%d, workers=%d)",
        mode_label,
        total_batches,
        batch_size,
        num_workers,
    )

    if fixed_frames > 0:
        # A'案: chunk 分割済み。全 chunks を batch 化して推論、utt 単位で L2 正規化平均
        for batch_idx, (indices, flat, chunks_per_utt, stems, valids) in enumerate(
            loader
        ):
            if flat.shape[0] == 0:
                fail += sum(1 for v in valids if not v)
                continue
            # 大きな batch を chunk_batch 単位でさらに分割 (GPU メモリ節約 + graph replay 対応)
            all_chunk_embs = []
            for i in range(0, flat.shape[0], chunk_batch):
                out = session.run(None, {input_name: flat[i : i + chunk_batch]})[0]
                all_chunk_embs.append(out)
            chunk_embs = np.concatenate(all_chunk_embs, axis=0)
            # 発話ごとに切り出して平均 → L2 正規化
            offset = 0
            for j, n_chunks in enumerate(chunks_per_utt):
                if not valids[j]:
                    fail += 1
                    offset += n_chunks
                    continue
                utt_chunks = chunk_embs[offset : offset + n_chunks]  # [n_chunks, 192]
                offset += n_chunks
                # 各 chunk を L2 正規化してから平均 → 再 L2 正規化
                cnorms = np.linalg.norm(utt_chunks, axis=-1, keepdims=True)
                cnorms = np.where(cnorms > 1e-8, cnorms, 1.0)
                utt_chunks_normed = utt_chunks / cnorms
                utt_emb = utt_chunks_normed.mean(axis=0)
                enorm = np.linalg.norm(utt_emb)
                if enorm > 1e-8:
                    utt_emb = utt_emb / enorm
                np.save(str(emb_dir / (stems[j] + ".npy")), utt_emb)
                success += 1
            if (batch_idx + 1) % 50 == 0:
                _LOGGER.info(
                    "Batch %d/%d (success=%d, fail=%d)",
                    batch_idx + 1,
                    total_batches,
                    success,
                    fail,
                )
    elif use_batch_infer:
        for batch_idx, (indices, padded, lengths, stems, valids) in enumerate(loader):
            valid_mask = np.array(valids, dtype=bool)
            if not valid_mask.any():
                fail += int((~valid_mask).sum())
                continue
            embeddings = session.run(None, {input_name: padded})[0]
            norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
            norms = np.where(norms > 1e-8, norms, 1.0)
            embeddings = embeddings / norms
            for j in range(len(stems)):
                if not valids[j]:
                    fail += 1
                    continue
                np.save(str(emb_dir / (stems[j] + ".npy")), embeddings[j])
                success += 1
            if (batch_idx + 1) % 50 == 0:
                _LOGGER.info(
                    "Batch %d/%d (success=%d, fail=%d)",
                    batch_idx + 1,
                    total_batches,
                    success,
                    fail,
                )
    else:
        # 個別推論 (per-utterance)。CUDAExecutionProvider が利用可能で IO binding が
        # 使えるなら Python 側の run() Python オーバーヘッドを削減し 2-5x 高速化する。
        # (numpy → GPU 転送を明示制御し、run_with_iobinding 経路に切り替える)
        use_gpu = "CUDAExecutionProvider" in session.get_providers()
        output_name = session.get_outputs()[0].name
        io_binding = session.io_binding() if use_gpu else None

        for batch_idx, (indices, fbank_list, stems, valids) in enumerate(loader):
            for _j, (_entry_idx, fbank, stem, valid) in enumerate(
                zip(indices, fbank_list, stems, valids, strict=False)
            ):
                if not valid:
                    fail += 1
                    continue

                fbank_input = np.expand_dims(fbank, axis=0)
                if io_binding is not None:
                    # IO binding: 入力 numpy → GPU、出力 GPU → numpy を明示制御
                    ort_input = onnxruntime.OrtValue.ortvalue_from_numpy(
                        fbank_input, "cuda", 0
                    )
                    io_binding.bind_input(
                        name=input_name,
                        device_type="cuda",
                        device_id=0,
                        element_type=fbank_input.dtype,
                        shape=fbank_input.shape,
                        buffer_ptr=ort_input.data_ptr(),
                    )
                    io_binding.bind_output(output_name, device_type="cuda", device_id=0)
                    session.run_with_iobinding(io_binding)
                    embedding = io_binding.get_outputs()[0].numpy()
                    io_binding.clear_binding_inputs()
                    io_binding.clear_binding_outputs()
                else:
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

    if entries and success == 0:
        # 全滅は環境/コード起因 (例: audio_norm cache の形式不整合) であり、
        # jsonl に実在しない embedding path を書いて「成功」扱いにしてはならない
        raise RuntimeError(
            f"speaker embedding extraction failed for all {len(entries)} entries; "
            "aborting without updating dataset.jsonl"
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
    parser.add_argument(
        "--fixed-frames",
        type=int,
        default=400,
        help=(
            "Fixed frame length for A'' chunked mode (4s @16kHz = 400 frames, VoxCeleb standard). "
            "Set to 0 to disable and fall back to legacy per-utt inference. Default: 400."
        ),
    )
    parser.add_argument(
        "--disable-fixed-frames",
        action="store_true",
        help="Shortcut for --fixed-frames 0 (disable A'' chunked mode, use legacy per-utt).",
    )
    parser.add_argument(
        "--chunk-batch",
        type=int,
        default=128,
        help="GPU inference chunk batch size (A100/A6000 safe = 128). Default: 128.",
    )
    parser.add_argument(
        "--batch-infer-padded",
        action="store_true",
        help=(
            "Enable legacy padded batch inference (only when --fixed-frames 0). "
            "Precision risk on non-length-sorted data. Default: off."
        ),
    )
    parser.add_argument(
        "--length-sort",
        action="store_true",
        help="Force length-based bucket sorting. Auto-enabled when --fixed-frames > 0.",
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
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    sess_options.enable_mem_reuse = True
    sess_options.enable_mem_pattern = True
    # GPU 実行時は intra_op を絞って CPU 側のスレッド競合を防ぐ
    sess_options.intra_op_num_threads = 1
    sess_options.inter_op_num_threads = 1

    cuda_provider_options = {
        "arena_extend_strategy": "kSameAsRequested",
        "do_copy_in_default_stream": False,
        # cudnn_conv_algo_search は EXHAUSTIVE だと session 作成で 15+ 分 hang するため
        # デフォルト (HEURISTIC) のまま。可変長入力では EXHAUSTIVE は使えない
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
            fixed_frames = 0 if args.disable_fixed_frames else args.fixed_frames
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
                fixed_frames=fixed_frames,
                chunk_batch=args.chunk_batch,
                use_batch_infer=args.batch_infer_padded,
                use_length_sort=True if args.length_sort else None,
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
