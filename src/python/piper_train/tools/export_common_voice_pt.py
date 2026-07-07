#!/usr/bin/env python3
"""Common Voice pt (HF: fsicoli/common_voice_22_0、CC0) から話者を選別し、
CML-TTS pt ディレクトリに `cv.csv` split として追記出力する。

pt はコーパス話者が 30 名 (CML) しかなく 6 言語中最薄のため、CV pt (3,817 話者
母集団) から品質条件を満たす話者を追加する (design doc §2.2)。出力は
prepare_multilingual_dataset.parse_cml_tts が読める 8 列 csv + wav 群なので、
`--pt-cml-tts <dir> --cml-splits train,dev,test,cv` でそのまま合流する
(cv.csv は pt ディレクトリにのみ存在し、es/fr は missing ログの上スキップされる)。

選別:
  1. validated.tsv のみ (コミュニティ検証済み)
  2. clip_durations.tsv で duration 1-15s (デコード不要)
  3. 話者 (client_id) あたり >= --min-clips、 duration 中央値近傍を --cap 件
  4. mp3 -> wav 変換は ffmpeg (24kHz mono)

Usage:
  python -m piper_train.tools.export_common_voice_pt \
      --cv-dir /data/downloads/cv22-pt \
      --output-dir /data/downloads/cml_tts_dataset_portuguese_v0.1 \
      --min-clips 20 --cap 60
"""

import argparse
import csv
import logging
import subprocess
import tarfile
from collections import defaultdict
from pathlib import Path

_LOGGER = logging.getLogger("export_common_voice_pt")


def load_durations(tsv: Path) -> dict[str, float]:
    durations: dict[str, float] = {}
    with open(tsv, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        dur_key = next(k for k in reader.fieldnames if "duration" in k.lower())
        clip_key = reader.fieldnames[0]
        for row in reader:
            try:
                durations[row[clip_key]] = float(row[dur_key]) / 1000.0
            except (ValueError, TypeError):
                continue
    return durations


def select_speakers(args, durations: dict[str, float]) -> dict[str, list[dict]]:
    """validated.tsv から話者 -> 採用 clip rows。"""
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    with open(args.cv_dir / "transcript" / "pt" / "validated.tsv", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            clip = row.get("path", "")
            text = (row.get("sentence") or "").strip()
            if not clip or not text or "|" in text:
                continue
            dur = durations.get(clip)
            if dur is None or not (args.min_dur <= dur <= args.max_dur):
                continue
            row["_dur"] = dur
            by_speaker[row["client_id"]].append(row)

    selected: dict[str, list[dict]] = {}
    for client, rows in by_speaker.items():
        if len(rows) < args.min_clips:
            continue
        # duration 中央値に近い順 (極端に短い/長いクリップを避ける)
        rows.sort(key=lambda r: abs(r["_dur"] - 6.0))
        selected[client] = rows[: args.cap]
    _LOGGER.info(
        "話者選別: %d/%d (min_clips=%d)、発話 %d",
        len(selected),
        len(by_speaker),
        args.min_clips,
        sum(len(v) for v in selected.values()),
    )
    return selected


def mp3_bytes_to_wav(raw: bytes, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ar", "24000", "-ac", "1", "-y", str(dst)],
        input=raw,
        capture_output=True,
    )
    return proc.returncode == 0 and dst.exists()


def export(args, selected: dict[str, list[dict]]) -> None:
    wanted: dict[str, tuple[str, dict]] = {}
    for client, rows in selected.items():
        spk = f"cv_{client[:12]}"
        for row in rows:
            wanted[row["path"]] = (spk, row)

    audio_root = args.cv_dir / "audio" / "pt"
    tars = sorted(audio_root.rglob("*.tar"))
    _LOGGER.info("tar shards: %d、対象 clip: %d", len(tars), len(wanted))

    n = 0
    csv_path = args.output_dir / "cv.csv"
    with open(csv_path, "w", encoding="utf-8") as csv_f:
        csv_f.write(
            "wav_filename|wav_filesize|transcript|transcript_wav2vec|"
            "levenshtein|duration|num_words|client_id\n"
        )
        for tar_path in tars:
            with tarfile.open(tar_path) as tf:
                for member in tf:
                    base = Path(member.name).name
                    if base not in wanted:
                        continue
                    spk, row = wanted.pop(base)
                    raw = tf.extractfile(member).read()
                    rel = Path("audios") / spk / (Path(base).stem + ".wav")
                    if not mp3_bytes_to_wav(raw, args.output_dir / rel):
                        continue
                    text = row["sentence"].replace("\n", " ").strip()
                    csv_f.write(
                        f"{str(rel).replace(chr(92), '/')}|0|{text}|{text}|0|"
                        f"{row['_dur']:.2f}|{len(text.split())}|{spk}\n"
                    )
                    n += 1
                    if n % 2000 == 0:
                        _LOGGER.info("  %d clips 変換済み (残 %d)", n, len(wanted))
    _LOGGER.info("=== 完了: %d clips -> %s ===", n, csv_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cv-dir",
        type=Path,
        required=True,
        help="fsicoli/common_voice_22_0 の local-dir (audio/pt + transcript/pt)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="CML-TTS pt ディレクトリ (cv.csv と audios/cv_* を追記)",
    )
    parser.add_argument("--min-clips", type=int, default=20)
    parser.add_argument("--cap", type=int, default=60)
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    durations = load_durations(
        args.cv_dir / "transcript" / "pt" / "clip_durations.tsv"
    )
    _LOGGER.info("clip_durations: %d clips", len(durations))
    selected = select_speakers(args, durations)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    export(args, selected)


if __name__ == "__main__":
    main()
