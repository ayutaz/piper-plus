#!/usr/bin/env python3
"""seen 話者 N 択識別 top-1 (raw + centered) — アーキ診断の追跡専用ツール。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

**診断専用 / go/no-go 不使用**: 本指標を go/no-go 判定・モデル比較の headline に
使うことは禁止 (判定は従来の 4 点セット: cross-utt SECS dual-encoder + 帯域 +
聴感 — /eval-zs skill)。用途は「条件付け経路は話者情報を運べているか」の
アーキ診断の追跡のみ (docs/design/zero-shot-v11-conditioning-design.md §6。
学習 loss への流用は frozen encoder 狙い撃ちの gaming 事例 4 件により恒久禁止)。

背景 (v10b oracle 診断 §8): SECS の絶対値は (a) 話者同一性の誤差 と (b) 合成音
vs 実音声のドメイン差の両方で下がる。両者を分離するため:

    raw     : cos(synth, real centroid) の argmax が正解話者か (N 択)
    centered: 合成クラウド平均 / 実クラウド平均をそれぞれ除去してから同じ判定
              (= 共通の「合成っぽさ」成分を落とす)

centered で精度が跳ね上がるなら、SECS の目減りの主因はドメイン差であり、
条件付け経路は話者同一性を運べている、という解釈になる。

参考ベースライン【実測、20 話者 (moe-speech seen)】:
    実音声       : raw top-1 98.5%
    v10a-r2 ep69 : raw 43% / centered 73% (アーキ律速の直接証拠)
逆方向の早期シグナル (設計 doc §6): 「ep20 時点で raw top-1 が v10b 系 (43%)
から +10pt 動いていなければ条件付け改修は効いていない」の補助に使える。

Usage:
    python -m piper_train.tools.eval_seen_speaker_id \\
        --synth-dir synth/            # <synth-dir>/<speaker>/*.wav \\
        --ref-emb-dir ref_embs/       # <speaker>.npy ([D] or [N, D]) \\
        --encoder models/campplus.onnx \\
        --json-out seen_id.json

推論は再現性優先で CPU 固定 (eval_zs_secs と同じ)。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = "zs-seen-id-v1"


def l2_normalize(v: np.ndarray) -> np.ndarray:
    """L2 正規化 (1D / 2D 両対応、ゼロベクトルはそのまま)。"""
    v = np.asarray(v, dtype=np.float64)
    if v.ndim == 1:
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v
    norms = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(norms > 1e-12, norms, 1.0)


def _evaluate(
    synth: np.ndarray, labels: np.ndarray, refs: np.ndarray, tag: str
) -> dict:
    """N 択識別の指標一式 (oracle 診断 identify_test.py と同一定義)。"""
    n_spk = refs.shape[0]
    sim = synth @ refs.T
    pred = sim.argmax(axis=1)
    order = np.argsort(-sim, axis=1)
    rank = np.array(
        [int(np.where(order[i] == labels[i])[0][0]) + 1 for i in range(len(labels))]
    )
    pos = sim[np.arange(len(labels)), labels]
    return {
        "label": tag,
        "top1_acc": float((pred == labels).mean()),
        "top3_acc": float((rank <= 3).mean()),
        "mean_rank": float(rank.mean()),
        "median_rank": float(np.median(rank)),
        "chance_top1": 1.0 / n_spk,
        "mean_cos_correct": float(pos.mean()),
        "mean_cos_wrong": float((sim.sum(axis=1) - pos).mean() / (n_spk - 1))
        if n_spk > 1
        else None,
    }


def _separation(synth: np.ndarray, labels: np.ndarray, refs: np.ndarray) -> float:
    """同一話者 cos − 別話者 cos の平均分離度。"""
    sim = synth @ refs.T
    pos = sim[np.arange(len(labels)), labels]
    if refs.shape[0] <= 1:
        return float(pos.mean())
    neg = (sim.sum(axis=1) - pos) / (refs.shape[0] - 1)
    return float((pos - neg).mean())


def identification_report(
    synth_embs: np.ndarray, labels: np.ndarray, ref_embs: np.ndarray
) -> dict:
    """raw + centered の N 択識別レポートを計算する純関数 (診断専用)。

    Args:
        synth_embs: [N, D] 合成音声の embedding (未正規化可)。
        labels: [N] 正解話者 index (ref_embs の行 index)。
        ref_embs: [S, D] 話者ごとの実音声 centroid embedding (未正規化可)。

    Returns:
        dict: raw / centered (top1_acc ほか) + shared_component +
        separation_raw / separation_centered + diagnostic_only。
    """
    synth = l2_normalize(np.asarray(synth_embs, dtype=np.float64))
    refs = l2_normalize(np.asarray(ref_embs, dtype=np.float64))
    labels = np.asarray(labels, dtype=np.int64)
    if synth.ndim != 2 or refs.ndim != 2:
        raise ValueError("synth_embs / ref_embs must be 2-D [N, D]")
    if len(labels) != synth.shape[0]:
        raise ValueError("labels length must match synth_embs rows")

    raw = _evaluate(synth, labels, refs, "raw")

    # 中心化: 合成クラウド / 実クラウドそれぞれの平均を除去 (ドメイン差の除去)
    s_mean = synth.mean(axis=0)
    r_mean = refs.mean(axis=0)
    synth_c = l2_normalize(synth - s_mean)
    refs_c = l2_normalize(refs - r_mean)
    centered = _evaluate(synth_c, labels, refs_c, "centered")

    shared = {
        "norm_of_synth_cloud_mean": float(np.linalg.norm(s_mean)),
        "norm_of_real_cloud_mean": float(np.linalg.norm(r_mean)),
        "cos_synth_mean_vs_real_mean": float(
            l2_normalize(s_mean) @ l2_normalize(r_mean)
        ),
        "mean_cos_each_synth_to_synth_mean": float(
            np.mean(synth @ l2_normalize(s_mean))
        ),
        "mean_cos_each_real_to_real_mean": float(np.mean(refs @ l2_normalize(r_mean))),
    }

    return {
        "schema": SCHEMA_VERSION,
        "diagnostic_only": True,
        "n_speakers": int(refs.shape[0]),
        "n_synth": int(synth.shape[0]),
        "raw": raw,
        "centered": centered,
        "shared_component": shared,
        "separation_raw": _separation(synth, labels, refs),
        "separation_centered": _separation(synth_c, labels, refs_c),
        "interpretation_note": (
            "top1_acc が chance を大きく超えるなら条件付け経路は話者情報を"
            "運んでいる。centered で大きく改善するなら SECS の目減りの主因は"
            "合成音の共通ドメイン差。診断専用 — go/no-go 判定への使用禁止 "
            "(docs/design/zero-shot-v11-conditioning-design.md §6)。"
        ),
    }


def load_reference_embeddings(ref_dir: str | Path) -> tuple[list[str], np.ndarray]:
    """<speaker>.npy 群を読み込み (話者名リスト, [S, D] centroid) を返す。

    npy は [D] (centroid そのまま) または [N, D] (発話群 → 行ごと L2 正規化 →
    平均 → 再 L2 正規化。oracle 診断と同じ centroid 定義)。
    """
    d = Path(ref_dir)
    files = sorted(d.glob("*.npy"))
    if not files:
        raise SystemExit(f"no .npy reference embeddings in: {d}")
    speakers: list[str] = []
    rows: list[np.ndarray] = []
    for f in files:
        arr = np.load(f, allow_pickle=False)
        if arr.ndim == 1:
            emb = l2_normalize(arr)
        elif arr.ndim == 2:
            emb = l2_normalize(np.mean(l2_normalize(arr), axis=0))
        else:
            raise SystemExit(f"reference embedding must be 1-D or 2-D: {f}")
        speakers.append(f.stem)
        rows.append(np.asarray(emb, dtype=np.float64).reshape(-1))
    dims = {r.shape[0] for r in rows}
    if len(dims) != 1:
        raise SystemExit(f"inconsistent embedding dims across speakers: {dims}")
    return speakers, np.stack(rows, axis=0)


def collect_synth_wavs(
    synth_dir: str | Path, speakers: list[str]
) -> tuple[list[Path], np.ndarray]:
    """<synth-dir>/<speaker>/*.wav を収集し (paths, labels) を返す。

    synth 側に参照 embedding のない話者ディレクトリがあれば SystemExit
    (取り違え防止)。
    """
    d = Path(synth_dir)
    if not d.is_dir():
        raise SystemExit(f"not a directory: {d}")
    index = {name: i for i, name in enumerate(speakers)}
    paths: list[Path] = []
    labels: list[int] = []
    for sub in sorted(p for p in d.iterdir() if p.is_dir()):
        if sub.name not in index:
            raise SystemExit(
                f"synth speaker dir '{sub.name}' has no reference embedding "
                f"({sub.name}.npy) in --ref-emb-dir"
            )
        wavs = sorted(sub.glob("*.wav"))
        if not wavs:
            _LOGGER.warning("no wav files under %s — skipped", sub)
            continue
        paths.extend(wavs)
        labels.extend([index[sub.name]] * len(wavs))
    if not paths:
        raise SystemExit(f"no <speaker>/*.wav found under --synth-dir: {d}")
    return paths, np.asarray(labels, dtype=np.int64)


def _embed_wavs(encoder_path: str | Path, wav_paths: list[Path]) -> np.ndarray:
    """CAM++ ONNX (CPU 固定) で wav 群を embedding 化する。

    NOTE: extract_speaker_embedding は前処理 (kaldi fbank) に torch を使うが、
    本モジュール自身は torch を import しない (zs-metric isolation Rule B と
    同じ規約 — eval_zs_secs の house style)。lazy import で純関数部
    (identification_report) は torch なしでもテスト可能に保つ。
    """
    import onnxruntime  # noqa: PLC0415 — lazy import (torch 間接依存の隔離)

    from piper_train.extract_speaker_embedding import (  # noqa: PLC0415
        extract_embedding,
        preprocess_audio,
    )

    session = onnxruntime.InferenceSession(
        str(encoder_path), providers=["CPUExecutionProvider"]
    )
    embs = []
    for p in wav_paths:
        embs.append(extract_embedding(session, preprocess_audio(p)))
    return np.stack(embs, axis=0)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="piper_train.tools.eval_seen_speaker_id",
        description=(
            "seen 話者 N 択識別 top-1 (raw + centered) — 診断専用、go/no-go 不使用"
        ),
    )
    parser.add_argument(
        "--synth-dir",
        required=True,
        help="合成 wav のルート (<synth-dir>/<speaker>/*.wav)",
    )
    parser.add_argument(
        "--ref-emb-dir",
        required=True,
        help="話者別参照 embedding の dir (<speaker>.npy、[D] or [N, D])",
    )
    parser.add_argument("--encoder", required=True, help="CAM++ ONNX モデルパス")
    parser.add_argument("--json-out", help="レポート JSON の出力先パス")
    args = parser.parse_args(argv)

    speakers, refs = load_reference_embeddings(args.ref_emb_dir)
    paths, labels = collect_synth_wavs(args.synth_dir, speakers)
    _LOGGER.info(
        "identifying %d synth wavs against %d speakers", len(paths), len(speakers)
    )
    synth_embs = _embed_wavs(args.encoder, paths)

    report = identification_report(synth_embs, labels, refs)
    report["speakers"] = speakers
    report["files"] = [str(p) for p in paths]

    print(
        f"=== seen-speaker {len(speakers)}-way identification (診断専用) ===\n"
        f"raw      top-1: {report['raw']['top1_acc']:.3f} "
        f"(chance {report['raw']['chance_top1']:.3f})\n"
        f"centered top-1: {report['centered']['top1_acc']:.3f}\n"
        f"参考: 実音声 raw 0.985 / v10a-r2 ep69 raw 0.43 / centered 0.73\n"
        "go/no-go には使わない (4 点セットは /eval-zs skill)。"
    )

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _LOGGER.info("wrote %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
