#!/usr/bin/env python3
"""HF `mythicinfinity/libritts_r` の parquet shards から LJSpeech 形式を生成する。

OpenSLR 141 の回線が実用に耐えないため (実測 0.3MB/s、2026-07-07)、HF parquet を
取得して prepare_bilingual_dataset.py の --en-libritts 入力用 LJSpeech 形式
(wavs/ + metadata.csv `filename|speaker|text`) に直接書き出す。話者選別ポリシーは
convert_libritts_r_to_ljspeech.py と同一 (全話者 + 話者あたり cap、zero-shot 話者
多様性優先。docs/design/zero-shot-v8-dataset-scaling-plan.md §2)。

2 パス構成:
  pass1: メタ列のみ読み (audio 列スキップで高速)、話者ごとに cap×1.3 件を
         決定的疑似シャッフル (sha1) で予約
  pass2: audio 列を読み、予約済み発話のみ duration 検査 (1-15s) して wav 書出、
         cap で打ち切り

Usage:
  python -m piper_train.tools.export_libritts_r_from_parquet \
      --parquet-dir /data/downloads/libritts-r-parquet/data \
      --output-dir /data/piper/libritts-r-ljspeech-v8 \
      --max-utterances-per-speaker 50 --min-utterances-per-speaker 20
"""

import argparse
import csv
import hashlib
import io
import logging
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

_LOGGER = logging.getLogger("export_libritts_r_from_parquet")

OVERSELECT = 1.3  # pass2 の duration 除外分を見込んだ予約倍率


def sha1_key(utt_id: str) -> str:
    return hashlib.sha1(utt_id.encode()).hexdigest()


def pass1_reserve(
    parquet_files: list[Path], cap: int, min_utts: int
) -> dict[str, set[str]]:
    """話者 -> 予約 utt_id 集合。"""
    by_speaker: dict[str, list[str]] = defaultdict(list)
    for pf_path in parquet_files:
        pf = pq.ParquetFile(pf_path)
        for batch in pf.iter_batches(batch_size=2048, columns=["id", "speaker_id"]):
            cols = batch.to_pydict()
            for utt_id, spk in zip(cols["id"], cols["speaker_id"]):
                by_speaker[str(spk)].append(str(utt_id))
    reserved: dict[str, set[str]] = {}
    for spk, ids in by_speaker.items():
        if len(ids) < min_utts:
            continue
        quota = int(cap * OVERSELECT)
        reserved[spk] = set(sorted(ids, key=sha1_key)[:quota])
    _LOGGER.info(
        "pass1: 話者 %d/%d (min_utts=%d 未満を除外)、予約 %d 発話",
        len(reserved),
        len(by_speaker),
        min_utts,
        sum(len(v) for v in reserved.values()),
    )
    return reserved


def pass2_export(
    parquet_files: list[Path],
    reserved: dict[str, set[str]],
    args,
) -> tuple[int, int]:
    wav_dir = args.output_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = defaultdict(int)
    n_utts = 0
    with open(
        args.output_dir / "metadata.csv", "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\")
        for pf_path in parquet_files:
            pf = pq.ParquetFile(pf_path)
            for batch in pf.iter_batches(batch_size=64):
                cols = batch.to_pydict()
                for i in range(len(cols["id"])):
                    spk = str(cols["speaker_id"][i])
                    utt_id = str(cols["id"][i])
                    if spk not in reserved or utt_id not in reserved[spk]:
                        continue
                    if written[spk] >= args.max_utterances_per_speaker:
                        continue
                    text = str(cols["text_normalized"][i]).strip()
                    if not text:
                        continue
                    raw = cols["audio"][i].get("bytes")
                    if raw is None:
                        continue
                    try:
                        data, sr = sf.read(io.BytesIO(raw))
                    except (RuntimeError, sf.LibsndfileError):
                        continue
                    dur = len(data) / sr if sr else 0
                    if not (args.min_dur <= dur <= args.max_dur):
                        continue
                    sf.write(wav_dir / f"{utt_id}.wav", data, sr)
                    writer.writerow((utt_id, spk, text.replace("|", " ")))
                    written[spk] += 1
                    n_utts += 1
    n_speakers = sum(
        1 for c in written.values() if c >= args.min_utterances_per_speaker
    )
    return n_speakers, n_utts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        required=True,
        help="mythicinfinity/libritts_r の data/ ディレクトリ",
    )
    parser.add_argument(
        "--subsets",
        default="train.clean.100,train.clean.360,train.other.500",
        help="comma 区切り subset 名",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-utterances-per-speaker", type=int, default=50)
    parser.add_argument("--min-utterances-per-speaker", type=int, default=20)
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parquet_files: list[Path] = []
    for subset in (s.strip() for s in args.subsets.split(",") if s.strip()):
        found = sorted((args.parquet_dir / subset).glob("*.parquet"))
        if not found:
            _LOGGER.warning("%s: parquet が見つからない", subset)
        parquet_files.extend(found)
    _LOGGER.info("parquet %d files", len(parquet_files))

    reserved = pass1_reserve(
        parquet_files, args.max_utterances_per_speaker, args.min_utterances_per_speaker
    )
    n_speakers, n_utts = pass2_export(parquet_files, reserved, args)
    _LOGGER.info(
        "=== 完了: 話者 %d / 発話 %d -> %s ===", n_speakers, n_utts, args.output_dir
    )


if __name__ == "__main__":
    main()
