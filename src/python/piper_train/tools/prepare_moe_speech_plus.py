#!/usr/bin/env python3
"""moe-speech-plus (HF: ayousanz/moe-speech-plus) から v8 学習用 ja データを選別する。

473 キャラ分の zip (キャラごとに wav + per-utterance JSON) を展開せずに
zipfile ストリームで読み、フィルタ通過した発話だけをマージ済み multi-speaker
LJSpeech 形式 (<output>/wavs/*.wav + metadata.csv 3 列 `filename|speaker|text`)
に抽出する。出力は `piper_train.preprocess --dataset-format ljspeech`
(multi-speaker 自動判定) にそのまま渡せる。

フィルタ (docs/design/zero-shot-v8-dataset-scaling-plan.md §2.3):
  1. duration 1.0-15.0s
  2. speechMOS >= --min-mos (default 0.0 = floor なし。moe-speech は高品質のため
     MOS フィルタ不要 [2026-07-07 決定]。MOS は cap 選抜の順位付けにのみ使用)
  3. anime-whisper vs parakeet の CER <= --max-cer (二重転写一致 = 転写信頼性)
  4. 話者あたり --min-utts 以上残らなければ話者ごと除外 / MOS 上位 --cap 発話に cap

Usage:
  python -m piper_train.tools.prepare_moe_speech_plus \
      --input-dir /data/downloads/moe-speech-plus \
      --output-dir /data/piper/moe-speech-plus-selected \
      --stats-only            # まず分布レポートのみ
"""

import argparse
import csv
import json
import logging
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

_LOGGER = logging.getLogger("prepare_moe_speech_plus")

_PUNCT_TABLE = str.maketrans(
    "", "", "、。，．・！？!?…‥「」『』（）()[]｛｝{}<>〈〉《》―ー~〜・ 　\t\n\r'\"”“’‘"
)


def normalize_for_cer(text: str) -> str:
    """CER 計算用の正規化: NFKC + 記号/空白除去。"""
    return unicodedata.normalize("NFKC", text).translate(_PUNCT_TABLE)


def char_error_rate(ref: str, hyp: str) -> float:
    """文字レベル Levenshtein 距離 / max(len)。空文字同士は 0.0、片方空は 1.0。"""
    ref_n, hyp_n = normalize_for_cer(ref), normalize_for_cer(hyp)
    if not ref_n and not hyp_n:
        return 0.0
    if not ref_n or not hyp_n:
        return 1.0
    prev = list(range(len(hyp_n) + 1))
    for i, rc in enumerate(ref_n, 1):
        cur = [i] + [0] * len(hyp_n)
        for j, hc in enumerate(hyp_n, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc))
        prev = cur
    return prev[-1] / max(len(ref_n), len(hyp_n))


def iter_zip_utterances(zip_path: Path):
    """zip 内の (stem, meta_dict, wav_member_name) を yield する。wav 欠落はスキップ。"""
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            wav_name = name[: -len(".json")] + ".wav"
            if wav_name not in names:
                continue
            try:
                meta = json.loads(zf.read(name))
            except (json.JSONDecodeError, KeyError) as err:
                _LOGGER.warning("%s: %s の JSON 読込失敗: %s", zip_path.name, name, err)
                continue
            yield Path(name).stem, meta, wav_name


def select_utterances(zip_path: Path, args) -> tuple[list[tuple[str, str, str]], Counter]:
    """1 キャラ分の zip から選別。(選抜リスト [(stem, wav_member, text)], 統計) を返す。"""
    stats: Counter = Counter()
    candidates = []
    for stem, meta, wav_name in iter_zip_utterances(zip_path):
        stats["total"] += 1
        dur = meta.get("duration")
        mos = meta.get("speechMOS")
        text_aw = (meta.get("anime_whisper_transcription") or "").strip()
        text_pk = (meta.get("parakeet_jp_transcription") or "").strip()
        if dur is None or not (args.min_dur <= dur <= args.max_dur):
            stats["reject_duration"] += 1
            continue
        if mos is None or mos < args.min_mos:
            stats["reject_mos"] += 1
            continue
        if not text_aw or not normalize_for_cer(text_aw):
            stats["reject_empty_text"] += 1
            continue
        cer = char_error_rate(text_aw, text_pk)
        if cer > args.max_cer:
            stats["reject_cer"] += 1
            continue
        candidates.append((mos, stem, wav_name, text_aw))
        stats["pass"] += 1
    # speechMOS 上位から cap 件
    candidates.sort(reverse=True)
    selected = [(stem, wav, text) for _, stem, wav, text in candidates[: args.cap]]
    if len(selected) < args.min_utts:
        stats["speaker_rejected"] = 1
        return [], stats
    return selected, stats


def extract_speaker(
    zip_path: Path, selected, wav_dir: Path
) -> list[tuple[str, str, str]]:
    """選抜発話の wav を共有 wavs/ に書き出し、metadata 行を返す。"""
    speaker = zip_path.stem
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        for stem, wav_member, text in selected:
            (wav_dir / f"{stem}.wav").write_bytes(zf.read(wav_member))
            rows.append((stem, speaker, text.replace("|", " ")))
    return rows


def collect_mos_histogram(zip_paths, sample_per_zip: int = 200) -> Counter:
    """--stats-only 用: speechMOS 分布 (0.25 刻み) を集計。"""
    hist: Counter = Counter()
    for zp in zip_paths:
        for i, (_, meta, _) in enumerate(iter_zip_utterances(zp)):
            if i >= sample_per_zip:
                break
            mos = meta.get("speechMOS")
            if mos is not None:
                hist[round(mos * 4) / 4] += 1
    return hist


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    # 0.0 = MOS floor なし (2026-07-07 ユーザー決定: moe-speech は高品質なため
    # MOS フィルタ不要)。MOS は cap 選抜の順位付けにのみ使用
    parser.add_argument("--min-mos", type=float, default=0.0)
    parser.add_argument("--max-cer", type=float, default=0.15)
    parser.add_argument("--min-dur", type=float, default=1.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    parser.add_argument("--min-utts", type=int, default=20)
    parser.add_argument("--cap", type=int, default=120)
    parser.add_argument(
        "--stats-only", action="store_true", help="抽出せず分布レポートのみ"
    )
    parser.add_argument("--limit-speakers", type=int, default=0, help="デバッグ用")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    zip_paths = sorted(args.input_dir.glob("*.zip"))
    if args.limit_speakers:
        zip_paths = zip_paths[: args.limit_speakers]
    _LOGGER.info("入力 zip: %d 個", len(zip_paths))

    if args.stats_only:
        hist = collect_mos_histogram(zip_paths)
        total = sum(hist.values())
        _LOGGER.info("speechMOS 分布 (サンプル %d 発話、0.25 刻み):", total)
        acc = 0
        for mos in sorted(hist, reverse=True):
            acc += hist[mos]
            _LOGGER.info(
                "  >= %.2f: %6d (累積 %5.1f%%)", mos, hist[mos], 100 * acc / total
            )
        return

    grand: Counter = Counter()
    kept_speakers = 0
    wav_dir = args.output_dir / "wavs"
    wav_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = args.output_dir / "metadata.csv"
    with open(metadata_path, "w", encoding="utf-8", newline="") as meta_f:
        writer = csv.writer(
            meta_f, delimiter="|", quoting=csv.QUOTE_NONE, escapechar="\\"
        )
        for zp in zip_paths:
            selected, stats = select_utterances(zp, args)
            grand.update(stats)
            if selected:
                kept_speakers += 1
                for row in extract_speaker(zp, selected, wav_dir):
                    writer.writerow(row)
                grand["selected_utts"] += len(selected)
            _LOGGER.info(
                "%s: %d/%d 選抜 %s",
                zp.stem,
                len(selected),
                stats["total"],
                "(話者除外)" if not selected else "",
            )
    _LOGGER.info("=== 完了: 話者 %d/%d、発話 %d ===", kept_speakers, len(zip_paths), grand["selected_utts"])
    for key in sorted(grand):
        _LOGGER.info("  %s: %d", key, grand[key])


if __name__ == "__main__":
    main()
