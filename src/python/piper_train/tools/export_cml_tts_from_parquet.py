#!/usr/bin/env python3
"""HF `ylacombe/cml-tts` の parquet shards から CML-TTS オリジナル構造を復元する。

OpenSLR 146 のミラー回線が実用に耐えないため (実測 0.1-0.4MB/s、2026-07-07)、
HF parquet (~10MB/s+) を取得して prepare_multilingual_dataset.parse_cml_tts が
期待する構造 (audios/<speaker>/<name>.wav + {train,dev,test}.csv 8列 pipe 区切り)
に書き戻す。parquet カラムは 8 列 csv と 1:1 対応:
  audio / wav_filesize / text / transcript_wav2vec / levenshtein / duration /
  num_words / speaker_id

Usage:
  python -m piper_train.tools.export_cml_tts_from_parquet \
      --parquet-dir /data/downloads/cml-tts-parquet/spanish \
      --output-dir /data/downloads/cml_tts_dataset_spanish_v0.1
"""

import argparse
import io
import logging
from pathlib import Path

import pyarrow.parquet as pq
import soundfile as sf

_LOGGER = logging.getLogger("export_cml_tts_from_parquet")

CSV_HEADER = (
    "wav_filename|wav_filesize|transcript|transcript_wav2vec|"
    "levenshtein|duration|num_words|client_id"
)


def write_audio(audio: dict, dst: Path) -> bool:
    """HF Audio struct {bytes, path} を wav で書き出す。wav 以外はデコードして変換。"""
    raw = audio.get("bytes")
    if raw is None:
        return False
    src_name = (audio.get("path") or "").lower()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src_name.endswith(".wav") or raw[:4] == b"RIFF":
        dst.write_bytes(raw)
        return True
    try:
        data, sr = sf.read(io.BytesIO(raw))
    except (RuntimeError, sf.LibsndfileError):
        return False
    sf.write(dst, data, sr)
    return True


def sanitize(text: str) -> str:
    """csv の pipe 区切りを壊す文字を除去。"""
    return text.replace("|", " ").replace("\n", " ").replace("\r", " ").strip()


def export_split(
    parquet_files: list[Path],
    split: str,
    out_dir: Path,
    speaker_counts: dict,
    args,
) -> int:
    rows = 0
    skipped_cap = skipped_dur = 0
    csv_path = out_dir / f"{split}.csv"
    with open(csv_path, "w", encoding="utf-8") as csv_f:
        csv_f.write(CSV_HEADER + "\n")
        for pf_path in parquet_files:
            pf = pq.ParquetFile(pf_path)
            for batch in pf.iter_batches(batch_size=64):
                cols = batch.to_pydict()
                for i in range(len(cols["speaker_id"])):
                    speaker = str(cols["speaker_id"][i])
                    dur = cols["duration"][i]
                    if dur is not None and not (args.min_dur <= dur <= args.max_dur):
                        skipped_dur += 1
                        continue
                    if (
                        args.max_utts_per_speaker
                        and speaker_counts.get(speaker, 0)
                        >= args.max_utts_per_speaker
                    ):
                        skipped_cap += 1
                        continue
                    audio = cols["audio"][i]
                    base = Path(audio.get("path") or f"{split}_{rows:08d}.wav").name
                    if not base.endswith(".wav"):
                        base = Path(base).stem + ".wav"
                    rel = Path("audios") / speaker / base
                    if not write_audio(audio, out_dir / rel):
                        continue
                    csv_f.write(
                        "|".join(
                            (
                                str(rel).replace("\\", "/"),
                                str(cols["wav_filesize"][i]),
                                sanitize(str(cols["text"][i])),
                                sanitize(str(cols["transcript_wav2vec"][i])),
                                str(cols["levenshtein"][i]),
                                str(cols["duration"][i]),
                                str(cols["num_words"][i]),
                                speaker,
                            )
                        )
                        + "\n"
                    )
                    speaker_counts[speaker] = speaker_counts.get(speaker, 0) + 1
                    rows += 1
    _LOGGER.info(
        "%s: %d rows -> %s (cap skip %d / dur skip %d)",
        split,
        rows,
        csv_path,
        skipped_cap,
        skipped_dur,
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        required=True,
        help="言語ディレクトリ (例: .../cml-tts-parquet/spanish)",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--splits", default="train,dev,test", help="comma 区切り (default: 全 split)"
    )
    parser.add_argument(
        "--max-utts-per-speaker",
        type=int,
        default=0,
        help="話者あたり発話 cap (0 = 無制限)。split 横断で集計。"
        "es/fr の縮小 (v8 §2) と disk/変換時間の節約用",
    )
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    speaker_counts: dict[str, int] = {}
    for split in (s.strip() for s in args.splits.split(",") if s.strip()):
        files = sorted(args.parquet_dir.glob(f"{split}-*.parquet"))
        if not files:
            _LOGGER.warning("%s: parquet が見つからない (%s)", split, args.parquet_dir)
            continue
        total += export_split(files, split, args.output_dir, speaker_counts, args)
    _LOGGER.info(
        "=== 完了: %d rows / 話者 %d -> %s ===",
        total,
        len(speaker_counts),
        args.output_dir,
    )


if __name__ == "__main__":
    main()
