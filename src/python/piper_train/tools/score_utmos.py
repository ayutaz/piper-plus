#!/usr/bin/env python3
"""Common Voice クリップの per-clip UTMOS スコアリング (SpeechMOS / UTMOS22)。

`export_common_voice_ko.py --utmos-tsv` が要求する pre-computed per-clip
UTMOS tsv (`path\tutmos`) を生成する。スコアラーは torch.hub 経由の
https://github.com/tarepan/SpeechMOS (`utmos22_strong`) — moe-speech-plus の
speechMOS 付与と同系列のモデルで、v8 design doc §2.4 の CV ko UTMOS ≥ 2.5
フィルタの入力を作る。

入力は 2 モード:
  1. `--cv-dir`: fsicoli/common_voice_22_0 の local-dir。`audio/<lang>/**/*.tar`
     の member を展開せず bytes 直読でスコアし、`transcript/<lang>/validated.tsv`
     に載っている clip のみ対象 (invalidated/other のデコードを省略)。
  2. `--clips-dir`: ディレクトリ内の音声ファイル (*.mp3 / *.wav / *.flac) を
     全件スコア (デバッグ / 非 CV データ用)。

出力 tsv は追記型で resume 可能 — 既存 `--output` があればスコア済み clip を
skip する (30 分級ジョブの中断復帰用)。キーは clip の basename
(validated.tsv の `path` 列と同一) で、`export_common_voice_ko.load_utmos`
がそのまま読める。

Usage:
  python -m piper_train.tools.score_utmos \\
      --cv-dir /data/downloads/cv22-ko --lang ko \\
      --output /data/downloads/cv22-ko/utmos_ko.tsv
"""

import argparse
import csv
import io
import logging
import sys
import tarfile
from collections.abc import Iterator
from pathlib import Path

_LOGGER = logging.getLogger("score_utmos")

# CV の validated.tsv は 128KB 超のフィールドを含むことがある (csv 既定上限で落ちる)
csv.field_size_limit(sys.maxsize)

_AUDIO_SUFFIXES = (".mp3", ".wav", ".flac")


def load_validated_clips(cv_dir: Path, lang: str) -> set[str]:
    """`transcript/<lang>/validated.tsv` の path 列 (clip basename) 集合。"""
    tsv = cv_dir / "transcript" / lang / "validated.tsv"
    clips: set[str] = set()
    with open(tsv, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            clip = (row.get("path") or "").strip()
            if clip:
                clips.add(clip)
    return clips


def load_existing_scores(output: Path) -> set[str]:
    """resume 用: 既存 output tsv のスコア済み clip 集合 (ヘッダ許容)。"""
    if not output.exists():
        return set()
    done: set[str] = set()
    with open(output, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0] and parts[0] != "path":
                done.add(parts[0])
    return done


def iter_cv_tar_audio(
    cv_dir: Path, lang: str, wanted: set[str]
) -> Iterator[tuple[str, bytes]]:
    """`audio/<lang>/**/*.tar` から wanted に載る member を bytes で yield。"""
    audio_root = cv_dir / "audio" / lang
    tars = sorted(audio_root.rglob("*.tar"))
    if not tars:
        raise FileNotFoundError(f"no .tar under {audio_root}")
    for tar_path in tars:
        with tarfile.open(tar_path) as tf:
            for member in tf:
                if not member.isfile():
                    continue
                base = Path(member.name).name
                if base not in wanted:
                    continue
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue
                yield base, fobj.read()


def iter_dir_audio(clips_dir: Path) -> Iterator[tuple[str, bytes]]:
    """ディレクトリ内の音声ファイルを bytes で yield (非再帰ではなく rglob)。"""
    for p in sorted(clips_dir.rglob("*")):
        if p.suffix.lower() in _AUDIO_SUFFIXES and p.is_file():
            yield p.name, p.read_bytes()


def _load_predictor(device: str):
    """torch.hub 経由で utmos22_strong をロード (テストでは monkeypatch 差替)。"""
    import torch

    predictor = torch.hub.load(
        "tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True
    )
    return predictor.to(device).eval()


def score_stream(
    audio_iter: Iterator[tuple[str, bytes]],
    predictor,
    device: str,
    output: Path,
    done: set[str],
    flush_every: int = 50,
) -> tuple[int, int]:
    """audio bytes を逐次スコアし tsv に追記。(scored, failed) を返す。"""
    import soundfile as sf
    import torch

    write_header = not output.exists() or output.stat().st_size == 0
    scored = failed = 0
    with open(output, "a", encoding="utf-8", newline="\n") as f:
        if write_header:
            f.write("path\tutmos\n")
        for name, raw in audio_iter:
            if name in done:
                continue
            try:
                data, sr = sf.read(io.BytesIO(raw), dtype="float32")
            except (RuntimeError, sf.LibsndfileError) as exc:
                _LOGGER.warning("decode 失敗 %s: %s", name, exc)
                failed += 1
                continue
            if data.ndim > 1:
                data = data.mean(axis=1)
            wave = torch.from_numpy(data).unsqueeze(0).to(device)
            with torch.inference_mode():
                score = float(predictor(wave, sr).squeeze().item())
            f.write(f"{name}\t{score:.4f}\n")
            scored += 1
            if scored % flush_every == 0:
                f.flush()
                _LOGGER.info("scored %d clips...", scored)
    return scored, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--cv-dir",
        type=Path,
        help="fsicoli/common_voice_22_0 の local-dir (audio/<lang> + transcript/<lang>)",
    )
    src.add_argument(
        "--clips-dir",
        type=Path,
        help="音声ファイルのディレクトリを全件スコア (デバッグ / 非 CV データ用)",
    )
    parser.add_argument("--lang", default="ko", help="--cv-dir 時の言語 (default: ko)")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="出力 tsv (path\\tutmos)。既存なら resume (スコア済み clip を skip)",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="cuda / cpu (default: cuda が使えれば cuda)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    import torch

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    _LOGGER.info("device: %s", device)

    done = load_existing_scores(args.output)
    if done:
        _LOGGER.info("resume: %d clips スコア済み、skip します", len(done))

    if args.cv_dir:
        wanted = load_validated_clips(args.cv_dir, args.lang)
        _LOGGER.info("validated clips: %d", len(wanted))
        audio_iter = iter_cv_tar_audio(args.cv_dir, args.lang, wanted)
    else:
        audio_iter = iter_dir_audio(args.clips_dir)

    predictor = _load_predictor(device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scored, failed = score_stream(audio_iter, predictor, device, args.output, done)
    _LOGGER.info("完了: scored=%d failed=%d output=%s", scored, failed, args.output)


if __name__ == "__main__":
    main()
