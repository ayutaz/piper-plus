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
  pass2: audio 列を読み、予約済み発話のみ duration 検査 (1-15s) して 音声書出、
         cap で打ち切り

Output format (2026-07-09 v8 #4 で FLAC 直保存モード追加):
  * `--output-format flac` (default): parquet の audio.bytes は既に FLAC
    圧縮なので、 そのまま `write_bytes()` で `.flac` として書き出す。
    duration 検査は `sf.info()` (headers のみ) で済ませ、 decode/encode の
    2 段変換を丸ごと省略。 downstream (norm_audio) が再度 sf.read するため
    従来の wav 経由だと double-decode が発生していた。
    - LibriTTS-R export: 30-60min → 5-10min (2-6x)
  * `--output-format wav`: 従来通り sf.read(BytesIO) → sf.write(.wav)。
    parquet の bytes が FLAC 以外だった場合の safety fallback として保持。

metadata.csv には拡張子付きファイル名 (`utt_id.flac` / `utt_id.wav`) を記録し、
downstream の prepare_bilingual_dataset.process_en_dataset が両方を透過的に
resolve できるように依存側を拡張済 (soundfile が両フォーマットを透過対応)。

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

# FLAC magic bytes (first 4 bytes of a native FLAC stream).
# 参考: https://xiph.org/flac/format.html#stream — "fLaC" ASCII marker が
# 全 FLAC stream の先頭に必ず出現する contract。
_FLAC_MAGIC = b"fLaC"


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
            for utt_id, spk in zip(cols["id"], cols["speaker_id"], strict=False):
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


def _duration_seconds(raw: bytes) -> float | None:
    """audio bytes の duration を取得する。 flac/wav なら headers-only (~10-50x
    高速)、 それ以外は full decode に fallback。 None は解析失敗。"""
    try:
        info = sf.info(io.BytesIO(raw))
        return info.duration
    except (RuntimeError, sf.LibsndfileError):
        return None


def pass2_export(
    parquet_files: list[Path],
    reserved: dict[str, set[str]],
    args,
) -> tuple[int, int]:
    wav_dir = args.output_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = defaultdict(int)
    n_utts = 0
    # flac mode で source bytes が FLAC 以外だった件数を計測 (LibriTTS-R では
    # 常に 0 になる想定、 0 でなければ HF dataset の内訳が変わった signal)。
    non_flac_seen = 0
    with open(args.output_dir / "metadata.csv", "w", encoding="utf-8", newline="") as f:
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

                    # ---- flac 直保存 fast path ----
                    # parquet の audio.bytes が既に FLAC のとき decode/encode を
                    # 丸ごと skip して 30-60min → 5-10min の主要 lever を成立させる。
                    if args.output_format == "flac" and raw[:4] == _FLAC_MAGIC:
                        dur = _duration_seconds(raw)
                        if dur is None:
                            continue
                        if not (args.min_dur <= dur <= args.max_dur):
                            continue
                        dst_name = f"{utt_id}.flac"
                        (wav_dir / dst_name).write_bytes(raw)
                        writer.writerow((dst_name, spk, text.replace("|", " ")))
                        written[spk] += 1
                        n_utts += 1
                        continue

                    # ---- decode + encode 経路 (wav mode / non-FLAC bytes) ----
                    if args.output_format == "flac":
                        non_flac_seen += 1
                    try:
                        data, sr = sf.read(io.BytesIO(raw))
                    except (RuntimeError, sf.LibsndfileError):
                        continue
                    dur = len(data) / sr if sr else 0
                    if not (args.min_dur <= dur <= args.max_dur):
                        continue
                    if args.output_format == "flac":
                        dst_name = f"{utt_id}.flac"
                        sf.write(wav_dir / dst_name, data, sr, format="FLAC")
                    else:
                        dst_name = f"{utt_id}.wav"
                        sf.write(wav_dir / dst_name, data, sr)
                    writer.writerow((dst_name, spk, text.replace("|", " ")))
                    written[spk] += 1
                    n_utts += 1
    if non_flac_seen:
        _LOGGER.warning(
            "flac mode 中に FLAC 以外の audio.bytes を %d 件 fallback decode。 "
            "HF parquet の内訳が変わった可能性 (LibriTTS-R では 0 を想定)。",
            non_flac_seen,
        )
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
    parser.add_argument(
        "--output-format",
        choices=("flac", "wav"),
        default="flac",
        help=(
            "音声書き出しフォーマット。 flac (default) は parquet の FLAC bytes を "
            "そのまま write_bytes() で保存し decode/encode を skip する v8 高速化 "
            "path。 wav は decode + wav 再 encode の従来経路 (backward compat)。"
        ),
    )
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
