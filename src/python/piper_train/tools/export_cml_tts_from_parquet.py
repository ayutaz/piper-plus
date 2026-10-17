#!/usr/bin/env python3
"""HF `ylacombe/cml-tts` の parquet shards から CML-TTS オリジナル構造を復元する。

OpenSLR 146 のミラー回線が実用に耐えないため (実測 0.1-0.4MB/s、2026-07-07)、
HF parquet (~10MB/s+) を取得して prepare_multilingual_dataset.parse_cml_tts が
期待する構造 (audios/<speaker>/<name>.{wav,flac} + {train,dev,test}.csv 8列 pipe
区切り) に書き戻す。parquet カラムは 8 列 csv と 1:1 対応:
  audio / wav_filesize / text / transcript_wav2vec / levenshtein / duration /
  num_words / speaker_id

Output format (2026-07-09 v8 #4 で FLAC 直保存モード追加):
  * `--output-format flac` (default): parquet の audio.bytes が FLAC magic
    (`fLaC`) を持つ場合 write_bytes() で `.flac` として直接保存し decode/encode
    を丸ごと省略。 downstream (norm_audio) が再度 sf.read するため、 従来の
    WAV 経由だと double-decode が発生していた。 wav_filename 列も対応する
    拡張子で記録し、 parse_cml_tts の存在チェックが透過的に通る (soundfile
    は FLAC/WAV 両対応)。
  * `--output-format wav`: 従来通り (WAV bytes は zero-copy、 それ以外は
    decode + wav 再 encode)。 backward compat 用。

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

# Container magic bytes — 参考: WAV は RIFF ヘッダ (`RIFF....WAVE`)、 FLAC は
# native stream marker `fLaC` (https://xiph.org/flac/format.html#stream)。
_WAV_MAGIC = b"RIFF"
_FLAC_MAGIC = b"fLaC"


def _detect_container(raw: bytes, src_name: str) -> str:
    """audio bytes のコンテナを "wav" / "flac" / "other" で返す。 magic 優先、
    fallback で path の拡張子を見る (HF Audio struct では path が空のときが
    あるため magic を先に判定する)。"""
    if raw[:4] == _WAV_MAGIC:
        return "wav"
    if raw[:4] == _FLAC_MAGIC:
        return "flac"
    if src_name.endswith(".wav"):
        return "wav"
    if src_name.endswith(".flac"):
        return "flac"
    return "other"


def write_audio(
    audio: dict, dst_dir: Path, base_stem: str, output_format: str
) -> tuple[Path, int] | None:
    """HF Audio struct {bytes, path} を書き出す。

    output_format:
      * "flac": FLAC bytes は write_bytes() で直接保存 (double-decode 排除)。
        WAV bytes は decode + FLAC 再 encode (依然として 1 段変換が発生する
        が、 downstream の decode + encode = 2 段の想定より軽い)。
      * "wav": 既存挙動 (WAV は zero-copy、 それ以外は decode + wav 再 encode)。

    Returns:
      (書き出し先 Path, サイズ bytes) or None (失敗)。
    """
    raw = audio.get("bytes")
    if raw is None:
        return None
    src_name = (audio.get("path") or "").lower()
    container = _detect_container(raw, src_name)
    dst_dir.mkdir(parents=True, exist_ok=True)

    if output_format == "flac":
        if container == "flac":
            dst = dst_dir / f"{base_stem}.flac"
            dst.write_bytes(raw)
            return dst, len(raw)
        # FLAC 以外 → decode + FLAC encode で downstream に .flac を提供。
        try:
            data, sr = sf.read(io.BytesIO(raw))
        except (RuntimeError, sf.LibsndfileError):
            return None
        dst = dst_dir / f"{base_stem}.flac"
        sf.write(dst, data, sr, format="FLAC")
        return dst, dst.stat().st_size

    # output_format == "wav": 既存挙動を保持。
    if container == "wav":
        dst = dst_dir / f"{base_stem}.wav"
        dst.write_bytes(raw)
        return dst, len(raw)
    try:
        data, sr = sf.read(io.BytesIO(raw))
    except (RuntimeError, sf.LibsndfileError):
        return None
    dst = dst_dir / f"{base_stem}.wav"
    sf.write(dst, data, sr)
    return dst, dst.stat().st_size


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
                        and speaker_counts.get(speaker, 0) >= args.max_utts_per_speaker
                    ):
                        skipped_cap += 1
                        continue
                    audio = cols["audio"][i]
                    # 拡張子は write_audio 側 (output_format) が決めるため stem のみ渡す。
                    src_base = Path(audio.get("path") or f"{split}_{rows:08d}").name
                    base_stem = Path(src_base).stem
                    dst_subdir = out_dir / "audios" / speaker
                    written = write_audio(
                        audio, dst_subdir, base_stem, args.output_format
                    )
                    if written is None:
                        continue
                    dst_path, dst_size = written
                    # csv の wav_filename 列は実際に書き出したファイル名を反映する。
                    # parse_cml_tts は base_dir / wav_filename の存在確認で resolve する
                    # ため、 拡張子が .flac のときも透過的に通る (soundfile が 両対応)。
                    rel = Path("audios") / speaker / dst_path.name
                    csv_f.write(
                        "|".join(
                            (
                                str(rel).replace("\\", "/"),
                                str(dst_size),
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
    parser.add_argument(
        "--output-format",
        choices=("flac", "wav"),
        default="flac",
        help=(
            "音声書き出しフォーマット。 flac (default) は parquet の FLAC bytes を "
            "そのまま write_bytes() で保存し decode/encode を skip する v8 高速化 "
            "path (double-decode 排除)。 wav は decode + wav 再 encode の従来経路 "
            "(backward compat)。 wav_filename csv 列は実際の拡張子を反映する。"
        ),
    )
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
