#!/usr/bin/env python3
"""Cross-utterance SECS 評価ハーネス (dual-encoder + ceiling/floor 正規化転写率)。

Why this exists (docs/design/zero-shot-v10-roadmap.md A-1e):
same-utterance SECS は SCL の Goodhart で膨張する (0.775 誤報の既知事故) ため、
zero-shot の話者類似度は **cross-utterance SECS のみ**で判定する。さらに cosine
のスケールは encoder ごとに非互換なので、ceiling (同一話者の実発話同士) と
floor (近い声質の別話者) で正規化した転写率

    normalized_transfer = (cross_utt_secs - floor) / (ceiling - floor)

を主指標とする。CAM++ 単独での go/no-go を防ぐため、held-out の第 2 encoder
(ECAPA、``export_ecapa_onnx`` で作成) を ``--encoder2`` で並走できる。

定義:
- cross_utt_secs: synth 各ファイルの「speaker-utts (exclude-ref 除外後) との平均
  cosine」を synth 全体で平均
- same_utt_secs: synth 各ファイルと exclude-ref (条件付けに使った発話) の平均
  cosine。**判定使用禁止 (参考値)**
- ceiling: speaker-utts (exclude-ref 除外後) 同士の全ペア平均 cosine
- floor: speaker-utts (exclude-ref 除外後) と floor-refs の全ペア平均 cosine

Usage:
    python -m piper_train.tools.eval_zs_secs \\
        --synth-dir synth_wavs/ \\
        --speaker-utts speaker_wavs/ \\
        --exclude-ref speaker_wavs/ref_001.wav \\
        --floor-refs floor_wavs/ \\
        --encoder models/campplus.onnx \\
        --encoder2 models/ecapa.onnx \\
        --json-out report.json

備考: 両 encoder とも入力は ``extract_speaker_embedding.preprocess_audio`` の
Kaldi fbank [1, T, 80]。ECAPA 側の前処理差は exporter が graph 内で吸収済み
(export_ecapa_onnx docstring 参照)。推論は再現性優先で CPU 固定。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import onnxruntime

from piper_train.extract_speaker_embedding import extract_embedding, preprocess_audio


_LOGGER = logging.getLogger(__name__)


def collect_wavs(directory: str | Path) -> list[Path]:
    """ディレクトリ直下の wav ファイルを収集する (大文字拡張子も、重複除去)。"""
    d = Path(directory)
    if not d.is_dir():
        raise SystemExit(f"not a directory: {d}")
    found = {p.resolve() for p in list(d.glob("*.wav")) + list(d.glob("*.WAV"))}
    return sorted(found)


def _l2_normalize(embs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embs, axis=-1, keepdims=True)
    return embs / np.where(norms > 1e-8, norms, 1.0)


def compute_secs_report(
    synth_embs: np.ndarray,
    speaker_embs: np.ndarray,
    ref_emb: np.ndarray | None = None,
    floor_embs: np.ndarray | None = None,
) -> dict:
    """埋め込み群から SECS レポート (1 encoder ぶん) を計算する純関数。

    Args:
        synth_embs: [N, D] 合成音声の embedding。
        speaker_embs: [M, D] 同一話者の実発話 embedding (exclude-ref は除外済み)。
        ref_emb: [D] 条件付けに使った発話の embedding (same-utt SECS 用)。
        floor_embs: [K, D] 近い声質の別話者 embedding (floor 用)。

    Returns:
        dict: cross_utt_secs / same_utt_secs / ceiling / floor /
        normalized_transfer / n_synth / n_refs。該当データが無い指標は None。
        ceiling は speaker_embs が 2 発話未満だと計算不能で None になる
        (CLI 側は 2 発話以上を要求する)。
    """
    synth = _l2_normalize(np.asarray(synth_embs, dtype=np.float64))
    refs = _l2_normalize(np.asarray(speaker_embs, dtype=np.float64))
    if synth.ndim != 2 or refs.ndim != 2:
        raise ValueError("synth_embs / speaker_embs must be 2-D [N, D]")

    # cross-utt: synth ごとの refs 平均 cosine → synth 全体で平均 (= 全ペア平均)
    cross = float(np.mean(synth @ refs.T))

    same: float | None = None
    if ref_emb is not None:
        r = _l2_normalize(np.asarray(ref_emb, dtype=np.float64).reshape(1, -1))
        same = float(np.mean(synth @ r.T))

    ceiling: float | None = None
    if refs.shape[0] >= 2:
        sim = refs @ refs.T
        iu = np.triu_indices(refs.shape[0], k=1)
        ceiling = float(sim[iu].mean())

    floor: float | None = None
    if floor_embs is not None and len(floor_embs) > 0:
        fl = _l2_normalize(np.asarray(floor_embs, dtype=np.float64))
        floor = float(np.mean(refs @ fl.T))

    normalized_transfer: float | None = None
    if ceiling is not None and floor is not None:
        denom = ceiling - floor
        if abs(denom) > 1e-6:
            normalized_transfer = float((cross - floor) / denom)
        else:
            _LOGGER.warning(
                "ceiling (%.4f) and floor (%.4f) nearly equal; "
                "normalized_transfer is undefined",
                ceiling,
                floor,
            )

    return {
        "cross_utt_secs": cross,
        "same_utt_secs": same,
        "ceiling": ceiling,
        "floor": floor,
        "normalized_transfer": normalized_transfer,
        "n_synth": int(synth.shape[0]),
        "n_refs": int(refs.shape[0]),
    }


def _create_session(encoder_path: str | Path) -> onnxruntime.InferenceSession:
    """SECS 評価用 ONNX session。再現性優先で CPU 固定 (GPU 競合も回避)。"""
    return onnxruntime.InferenceSession(
        str(encoder_path), providers=["CPUExecutionProvider"]
    )


def _extract_embs(
    session: onnxruntime.InferenceSession,
    wav_paths: list[Path],
    fbank_cache: dict[Path, np.ndarray],
) -> np.ndarray:
    """wav 群から embedding を抽出する。fbank は encoder 間で共有キャッシュ。"""
    embs = []
    for p in wav_paths:
        if p not in fbank_cache:
            fbank_cache[p] = preprocess_audio(p)
        embs.append(extract_embedding(session, fbank_cache[p]))
    return np.stack(embs, axis=0)


def _fmt(value: float | None, width: int = 9) -> str:
    return f"{value:{width}.4f}" if value is not None else f"{'n/a':>{width}}"


def _print_report(report: dict, synth_dir: str, speaker_dir: str) -> None:
    print("=== zero-shot cross-utterance SECS report ===")
    print(f"synth dir  : {synth_dir}")
    print(f"speaker dir: {speaker_dir}")
    print()
    header = (
        f"{'encoder':<10} {'norm_transfer':>13} {'cross_utt':>9} "
        f"{'ceiling':>9} {'floor':>9} {'same_utt*':>9} {'n_synth':>7} {'n_refs':>6}"
    )
    print(header)
    print("-" * len(header))
    for name, r in report["encoders"].items():
        nt = r["normalized_transfer"]
        nt_str = f">>> {nt:.4f} <<<" if nt is not None else f"{'n/a':>13}"
        print(
            f"{name:<10} {nt_str:>13} {_fmt(r['cross_utt_secs'])} "
            f"{_fmt(r['ceiling'])} {_fmt(r['floor'])} {_fmt(r['same_utt_secs'])} "
            f"{r['n_synth']:>7} {r['n_refs']:>6}"
        )
    print()
    print(
        "判定は normalized_transfer (cross-utt ベース) で行うこと。\n"
        "* same_utt は SCL Goodhart で膨張するため判定使用禁止 (参考値のみ、\n"
        "  docs/design/zero-shot-v10-roadmap.md 運用原則 1)。"
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="piper_train.tools.eval_zs_secs",
        description="Cross-utterance SECS (dual-encoder, ceiling/floor 正規化転写率)",
    )
    parser.add_argument("--synth-dir", required=True, help="合成 wav 群のディレクトリ")
    parser.add_argument(
        "--speaker-utts",
        required=True,
        help="同一話者の実発話ディレクトリ (cross-utt 対象)",
    )
    parser.add_argument(
        "--exclude-ref",
        help=(
            "条件付けに使った発話 wav。speaker-utts 内なら cross 集合から除外し、"
            "same-utt SECS の参照として使用"
        ),
    )
    parser.add_argument(
        "--floor-refs", help="近い声質の別話者 wav 群のディレクトリ (optional)"
    )
    parser.add_argument("--encoder", required=True, help="CAM++ ONNX モデルパス")
    parser.add_argument(
        "--encoder2", help="第 2 encoder ONNX パス (ECAPA、optional、Goodhart 検知用)"
    )
    parser.add_argument("--json-out", help="レポート JSON の出力先パス")
    args = parser.parse_args(argv)

    synth_files = collect_wavs(args.synth_dir)
    if not synth_files:
        raise SystemExit(f"no wav files in --synth-dir: {args.synth_dir}")

    speaker_files = collect_wavs(args.speaker_utts)
    ref_path: Path | None = None
    if args.exclude_ref:
        ref_path = Path(args.exclude_ref).resolve()
        if not ref_path.is_file():
            raise SystemExit(f"--exclude-ref not found: {ref_path}")
    cross_files = [p for p in speaker_files if p != ref_path]
    if ref_path is not None and len(cross_files) < len(speaker_files):
        _LOGGER.info("excluded conditioning reference from cross set: %s", ref_path)
    if len(cross_files) < 2:
        raise SystemExit(
            "need >= 2 speaker utterances after --exclude-ref exclusion "
            f"(got {len(cross_files)}); ceiling requires pairwise cosine"
        )

    floor_files = collect_wavs(args.floor_refs) if args.floor_refs else []
    if args.floor_refs and not floor_files:
        raise SystemExit(f"no wav files in --floor-refs: {args.floor_refs}")

    encoders = [("campplus", args.encoder)]
    if args.encoder2:
        encoders.append(("encoder2", args.encoder2))

    fbank_cache: dict[Path, np.ndarray] = {}
    report: dict = {"encoders": {}}
    for name, encoder_path in encoders:
        _LOGGER.info("extracting embeddings with %s (%s)", name, encoder_path)
        session = _create_session(encoder_path)
        synth_embs = _extract_embs(session, synth_files, fbank_cache)
        speaker_embs = _extract_embs(session, cross_files, fbank_cache)
        ref_emb = (
            _extract_embs(session, [ref_path], fbank_cache)[0]
            if ref_path is not None
            else None
        )
        floor_embs = (
            _extract_embs(session, floor_files, fbank_cache) if floor_files else None
        )
        report["encoders"][name] = compute_secs_report(
            synth_embs, speaker_embs, ref_emb=ref_emb, floor_embs=floor_embs
        )

    _print_report(report, args.synth_dir, args.speaker_utts)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        _LOGGER.info("wrote %s", json_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
