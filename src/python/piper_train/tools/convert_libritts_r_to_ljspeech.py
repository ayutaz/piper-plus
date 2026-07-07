#!/usr/bin/env python3
"""LibriTTS-R を prepare_bilingual_dataset.py の --en-libritts 入力用の
LJSpeech 形式 (wavs/ + metadata.csv) に変換する。

v7 は発話数上位 310 話者のサブセットを使用していたが、zero-shot の話者多様性
確保のため全 2,456 話者を対象に、話者あたり発話を cap して変換する
(docs/design/zero-shot-v8-dataset-scaling-plan.md §2)。

入力構造 (OpenSLR 141 の tar 展開後):
  LibriTTS_R/train-clean-100/<speaker>/<chapter>/<spk>_<ch>_<seg>_<utt>.wav
  同名の .normalized.txt にテキスト

出力 (LJSpeech 形式、prepare_bilingual_dataset の 3 列 metadata.csv):
  <output>/wavs/<basename>.wav   (hardlink、失敗時 copy)
  <output>/metadata.csv          (filename|speaker|text)

Usage:
  python -m piper_train.tools.convert_libritts_r_to_ljspeech \
      --input-dir /data/downloads/LibriTTS_R/train-clean-100 \
      --input-dir /data/downloads/LibriTTS_R/train-clean-360 \
      --input-dir /data/downloads/LibriTTS_R/train-other-500 \
      --output-dir /data/piper/libritts-r-ljspeech-v8 \
      --max-utterances-per-speaker 50 --min-utterances-per-speaker 20
"""

import argparse
import csv
import hashlib
import logging
import os
import shutil
import wave
from collections import defaultdict
from pathlib import Path

_LOGGER = logging.getLogger("convert_libritts_r_to_ljspeech")


def wav_duration_sec(path: Path) -> float | None:
    """wav ヘッダから長さを取得 (デコードなし、高速)。失敗時 None。"""
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate()
            return w.getnframes() / rate if rate else None
    except (wave.Error, OSError):
        return None


def collect_utterances(
    input_dirs: list[Path], min_dur: float, max_dur: float
) -> dict[str, list[tuple[Path, str]]]:
    """話者 -> [(wav_path, text)] を収集。duration 範囲外・テキスト欠落は除外。"""
    by_speaker: dict[str, list[tuple[Path, str]]] = defaultdict(list)
    n_seen = n_no_text = n_bad_dur = 0
    for root in input_dirs:
        for wav_path in root.rglob("*.wav"):
            n_seen += 1
            txt_path = wav_path.with_suffix(".normalized.txt")
            if not txt_path.exists():
                n_no_text += 1
                continue
            text = txt_path.read_text(encoding="utf-8").strip()
            if not text:
                n_no_text += 1
                continue
            dur = wav_duration_sec(wav_path)
            if dur is None or not (min_dur <= dur <= max_dur):
                n_bad_dur += 1
                continue
            speaker = wav_path.name.split("_", 1)[0]
            by_speaker[speaker].append((wav_path, text))
    _LOGGER.info(
        "走査 %d wav: text 欠落 %d / duration 範囲外 %d / 有効 %d (話者 %d)",
        n_seen,
        n_no_text,
        n_bad_dur,
        sum(len(v) for v in by_speaker.values()),
        len(by_speaker),
    )
    return by_speaker


def stable_sample(items: list, cap: int) -> list:
    """ファイル名 sha1 順の決定的疑似シャッフルで cap 件選ぶ (章の偏り回避)。"""
    if len(items) <= cap:
        return items
    keyed = sorted(
        items, key=lambda it: hashlib.sha1(it[0].name.encode()).hexdigest()
    )
    return keyed[:cap]


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        action="append",
        type=Path,
        required=True,
        help="LibriTTS-R の subset ディレクトリ (複数指定可)",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-utterances-per-speaker", type=int, default=50)
    parser.add_argument("--min-utterances-per-speaker", type=int, default=20)
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    by_speaker = collect_utterances(args.input_dir, args.min_dur, args.max_dur)

    wav_dir = args.output_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    n_speakers = n_utts = 0
    with open(
        args.output_dir / "metadata.csv", "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\")
        for speaker in sorted(by_speaker):
            utts = by_speaker[speaker]
            if len(utts) < args.min_utterances_per_speaker:
                continue
            n_speakers += 1
            for wav_path, text in stable_sample(
                utts, args.max_utterances_per_speaker
            ):
                link_or_copy(wav_path, wav_dir / wav_path.name)
                writer.writerow((wav_path.stem, speaker, text))
                n_utts += 1

    _LOGGER.info(
        "=== 完了: 話者 %d / 発話 %d → %s ===", n_speakers, n_utts, args.output_dir
    )


if __name__ == "__main__":
    main()
