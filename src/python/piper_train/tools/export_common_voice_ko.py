#!/usr/bin/env python3
"""Common Voice ko (HF: fsicoli/common_voice_22_0 の ko subset、CC0) から
UTMOS + 話者フィルタで選別し、prepare_multilingual_dataset.py の
`parse_common_voice_ko` が読める CML-TTS 形式 (`cv.csv` + `utmos.tsv` +
`audios/cv_<client_prefix>/*.wav`) として出力する。

v8 dataset scaling plan §2.2 参照 — Korean は Zeroth-Korean (~181 spk) が主力で、
CV ko は追加話者多様性目的 (~30-50 spk 想定)。KsponSpeech (AI-Hub、
research-only ライセンス) は v8 から除外確定 (2026-08-02)。

選別:
  1. validated.tsv のみ (コミュニティ検証済み)
  2. clip_durations.tsv で duration 1-15s (デコード不要)
  3. 話者 (client_id) あたり >= --min-clips、 duration 中央値近傍を --cap 件
  4. UTMOS スコアを別途 `utmos.tsv` に落とす (話者ごとの中央値)
  5. mp3 -> wav 変換は ffmpeg (24kHz mono、prepare 側で 22.05kHz にリサンプル)

Usage:
  python -m piper_train.tools.export_common_voice_ko \\
      --cv-dir /data/downloads/cv22-ko \\
      --output-dir /data/downloads/common_voice_ko_v22 \\
      --min-clips 20 --cap 60

このスクリプトは export_common_voice_pt.py と対称的で、`utmos.tsv` を追加で
書き出す点だけが異なる (Korean は CV スコアの分布が言語混在で pt より
低く、話者フィルタの精度を上げるため)。
"""

import argparse
import csv
import logging
import statistics
import subprocess
import sys
import tarfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


_LOGGER = logging.getLogger("export_common_voice_ko")

# CV の validated.tsv は 128KB 超のフィールドを含むことがある (csv 既定上限で落ちる)
csv.field_size_limit(sys.maxsize)


def load_durations(tsv: Path) -> dict[str, float]:
    """clip_durations.tsv (path\tduration_ms) -> {path: duration_seconds}."""
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


def load_utmos(tsv: Path | None) -> dict[str, float]:
    """Optional per-clip UTMOS tsv (path\tutmos) -> {path: score}.

    Common Voice does not ship UTMOS scores. If the user has pre-computed
    scores (e.g. via https://github.com/tarepan/SpeechMOS on a mp3 stream),
    pass the resulting tsv via ``--utmos-tsv``. Missing file → per-speaker
    UTMOS = None and the UTMOS floor is disabled in downstream selection.
    """
    if tsv is None or not tsv.exists():
        return {}
    utmos: dict[str, float] = {}
    with open(tsv, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        mos_key = next(
            (
                k
                for k in reader.fieldnames
                if "mos" in k.lower() or "score" in k.lower()
            ),
            reader.fieldnames[-1],
        )
        clip_key = reader.fieldnames[0]
        for row in reader:
            try:
                utmos[row[clip_key]] = float(row[mos_key])
            except (ValueError, TypeError):
                continue
    return utmos


def select_speakers(
    args, durations: dict[str, float], utmos: dict[str, float]
) -> dict[str, list[dict]]:
    """validated.tsv から話者 -> 採用 clip rows。"""
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    with open(
        args.cv_dir / "transcript" / "ko" / "validated.tsv", encoding="utf-8"
    ) as f:
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
            row["_utmos"] = utmos.get(clip)
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
    """既に変換済みならスキップ (再実行を高速化)。ffmpeg は GIL 外なのでスレッド並列可。"""
    if dst.exists() and dst.stat().st_size > 44:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-y",
            str(dst),
        ],
        input=raw,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0 and dst.exists()


def export(args, selected: dict[str, list[dict]]) -> None:
    wanted: dict[str, tuple[str, dict]] = {}
    for client, rows in selected.items():
        spk = client  # keep the full client_id — parse_common_voice_ko prefixes "cv-"
        for row in rows:
            wanted[row["path"]] = (spk, row)

    audio_root = args.cv_dir / "audio" / "ko"
    tars = sorted(audio_root.rglob("*.tar"))
    _LOGGER.info("tar shards: %d、対象 clip: %d", len(tars), len(wanted))

    def convert(job):
        base, spk, row, raw = job
        # Use "cv_<12-char client prefix>" for the on-disk directory (short
        # deterministic path); the csv keeps the full client_id in column 8.
        subdir = f"cv_{spk[:12]}"
        rel = Path("audios") / subdir / (Path(base).stem + ".wav")
        if not mp3_bytes_to_wav(raw, args.output_dir / rel):
            return None
        text = row["sentence"].replace("\n", " ").strip()
        return (
            f"{str(rel).replace(chr(92), '/')}|0|{text}|{text}|0|"
            f"{row['_dur']:.2f}|{len(text.split())}|{spk}\n"
        )

    n = 0
    csv_path = args.output_dir / "cv.csv"
    with (
        open(csv_path, "w", encoding="utf-8") as csv_f,
        ThreadPoolExecutor(max_workers=args.ffmpeg_workers) as pool,
    ):
        csv_f.write(
            "wav_filename|wav_filesize|transcript|transcript_wav2vec|"
            "levenshtein|duration|num_words|client_id\n"
        )
        for tar_path in tars:
            with tarfile.open(tar_path) as tf:
                jobs = []
                for member in tf:
                    base = Path(member.name).name
                    if base not in wanted:
                        continue
                    spk, row = wanted.pop(base)
                    jobs.append((base, spk, row, tf.extractfile(member).read()))
                    if len(jobs) >= 512:
                        for line in pool.map(convert, jobs):
                            if line:
                                csv_f.write(line)
                                n += 1
                        jobs = []
                        if n % 2048 < 512:
                            _LOGGER.info("  %d clips 変換済み (残 %d)", n, len(wanted))
                for line in pool.map(convert, jobs):
                    if line:
                        csv_f.write(line)
                        n += 1
    _LOGGER.info("=== 完了: %d clips -> %s ===", n, csv_path)

    # Write utmos.tsv: per-speaker median UTMOS across the selected clips.
    # parse_common_voice_ko(min_utmos=...) uses this to gate speakers.
    utmos_path = args.output_dir / "utmos.tsv"
    with utmos_path.open("w", encoding="utf-8") as f:
        f.write("client_id\tutmos\n")
        wrote_any = False
        for client, rows in selected.items():
            scores = [r["_utmos"] for r in rows if r.get("_utmos") is not None]
            if not scores:
                continue
            median = statistics.median(scores)
            f.write(f"{client}\t{median:.3f}\n")
            wrote_any = True
    if wrote_any:
        _LOGGER.info("=== utmos.tsv 書き出し: %s ===", utmos_path)
    else:
        # Remove empty utmos.tsv so parse_common_voice_ko treats it as "no
        # UTMOS available" (== skip filter) rather than "empty index" (==
        # drop everything).
        utmos_path.unlink()
        _LOGGER.info("utmos.tsv には有効スコアなし → 削除 (parse 側で filter 無効化)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cv-dir",
        type=Path,
        required=True,
        help="fsicoli/common_voice_22_0 の local-dir (audio/ko + transcript/ko)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="出力先ディレクトリ (cv.csv + utmos.tsv + audios/cv_* を書き出す)",
    )
    parser.add_argument(
        "--utmos-tsv",
        type=Path,
        default=None,
        help="オプション: pre-computed per-clip UTMOS の tsv (path\\tutmos)。 "
        "不在なら utmos.tsv は書き出さず、parse 側の filter は自動無効化。",
    )
    parser.add_argument("--min-clips", type=int, default=20)
    parser.add_argument("--cap", type=int, default=60)
    parser.add_argument("--ffmpeg-workers", type=int, default=16)
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    durations = load_durations(args.cv_dir / "transcript" / "ko" / "clip_durations.tsv")
    _LOGGER.info("clip_durations: %d clips", len(durations))
    utmos = load_utmos(args.utmos_tsv)
    if utmos:
        _LOGGER.info("utmos scores: %d clips", len(utmos))
    else:
        _LOGGER.info(
            "utmos tsv 未指定または空 — utmos.tsv は書き出さない (filter 無効化)"
        )
    selected = select_speakers(args, durations, utmos)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    export(args, selected)


if __name__ == "__main__":
    main()
