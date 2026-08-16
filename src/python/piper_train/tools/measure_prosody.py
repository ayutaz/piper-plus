#!/usr/bin/env python3
"""韻律 (F0 / energy / 話速) の記述統計 + synth−real の delta (E-3)。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。F0/エネルギー統計は
微分可能化が容易で韻律 loss への流用誘惑が最も強い — 恒久禁止 (契約 §2 禁止事項 4)。
**例外境界**: S-2 の GT frame-level F0 を教師とする pitch predictor 回帰 loss は
GT 参照 loss であり本禁止の対象外 (契約 §2 参照)。

本モジュールの出力は**類似スコアではなく記述統計の差分**である (plan E-3):
「synth の f0_std delta が負 = real より平板」のような診断のための差分値で、
単一スカラーの類似度に潰さない (潰すと Goodhart の対象になる)。

canonical: F0 推定は acoustic_frames の pyin (fmin=70 / fmax=600 /
frame_length=2048 / hop=256) を共用 — v10b plan §1 の baseline (GT std 47-74Hz /
r2 std 29-41Hz) はこの設定 (anatomy.py) で測られた。voiced 判定も同一
(energy gate 込み)。

話速 proxy ``syllable_nuclei_per_sec`` は de Jong & Wempe 型シラブル核検出の
簡易版 (平滑 rms_db の find_peaks) で、**テキスト非統制の proxy** — テキストが
異なるクリップ間の比較は参考値に留めること。

Usage:
    python -m piper_train.tools.measure_prosody --wav path.wav
    python -m piper_train.tools.measure_prosody --clips-dir DIR --json-out out.json
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np


if TYPE_CHECKING:
    from piper_train.tools.acoustic_frames import FrameAnalysis

_LOGGER = logging.getLogger(__name__)

MIN_VOICED_FRAMES = 10

# 話速 proxy のパラメータ (仕様 D10 で固定): 5 フレーム移動平均 (58ms 平滑) →
# find_peaks(distance=9 (最小間隔 104ms), prominence=2.0 (卓立 2dB))
SYLLABLE_SMOOTH_FRAMES = 5
SYLLABLE_MIN_DISTANCE_FRAMES = 9
SYLLABLE_PROMINENCE_DB = 2.0


def prosody_stats(fa: FrameAnalysis) -> dict | None:
    """per-clip の韻律記述統計。voiced フレーム 10 未満なら None。

    F0 統計は Hz (母標準偏差 np.std、anatomy と同じ) + 話者非依存の補助として
    semitone std。skew / kurtosis は Mega-TTS 2 系 moments (plan E-3)。
    """
    from scipy.signal import find_peaks
    from scipy.stats import kurtosis, skew

    fv = fa.f0[fa.voiced]
    n_voiced = int(fa.voiced.sum())
    if n_voiced < MIN_VOICED_FRAMES:
        return None

    n_frames = len(fa.voiced)
    f0_median = float(np.median(fv))
    semitone = 12.0 * np.log2(fv / f0_median)
    p5 = float(np.percentile(fv, 5))
    p95 = float(np.percentile(fv, 95))

    # 話速 proxy: 平滑 rms_db のピーク (シラブル核) のうち voiced 上のものを数える
    smooth = np.convolve(
        fa.rms_db,
        np.ones(SYLLABLE_SMOOTH_FRAMES) / SYLLABLE_SMOOTH_FRAMES,
        mode="same",
    )
    peaks, _ = find_peaks(
        smooth,
        distance=SYLLABLE_MIN_DISTANCE_FRAMES,
        prominence=SYLLABLE_PROMINENCE_DB,
    )
    n_nuclei = int(np.sum(fa.voiced[peaks])) if len(peaks) else 0

    return {
        "f0_mean_hz": float(np.mean(fv)),
        "f0_median_hz": f0_median,
        "f0_std_hz": float(np.std(fv)),
        "f0_std_semitone": float(np.std(semitone)),
        "f0_p5_hz": p5,
        "f0_p95_hz": p95,
        "f0_range_p5_p95_hz": p95 - p5,
        "f0_skew": float(skew(fv)),
        "f0_kurtosis_excess": float(kurtosis(fv, fisher=True)),
        "voiced_rate": n_voiced / n_frames,
        "voiced_seconds": n_voiced * fa.hop / fa.sr,
        "voiced_energy_std_db": float(np.std(fa.rms_db[fa.voiced])),
        "syllable_nuclei_per_sec": n_nuclei / fa.duration_sec,
    }


def prosody_group_summary(stats: list[dict]) -> dict | None:
    """グループ集計: 各統計の median across clips【決定 D12 — 外れ値耐性】。

    §4.3 の「f0_std ≥ 45Hz」判定は synth グループの median に適用される
    (判定自体は /eval-zs skill の責務 — 本関数は測るだけ)。
    """
    if not stats:
        return None
    out: dict = {}
    for key in stats[0]:
        values = [s[key] for s in stats if s.get(key) is not None]
        out[key] = float(np.median(values)) if values else None
    out["n_clips"] = len(stats)
    return out


def prosody_delta(synth: dict, real: dict) -> dict:
    """統計ごとの synth − real の単純差 (null-safe: どちらか None → None)。

    符号の向き: 負の f0_std delta = 「synth が real より平板」。"n_clips" は
    統計ではないため対象外。
    """
    out: dict = {}
    for key, synth_value in synth.items():
        if key == "n_clips" or key not in real:
            continue
        real_value = real[key]
        if synth_value is None or real_value is None:
            out[key] = None
        else:
            out[key] = float(synth_value - real_value)
    return out


def score_file(path: Path) -> dict | None:
    """wav を 22.05kHz mono で解析し per-clip 統計を返す (解析不能なら None)。"""
    from piper_train.tools.acoustic_frames import analyze_frames, load_wav

    wav = load_wav(path)
    fa = analyze_frames(wav, 22050)
    if fa is None:
        return None
    return prosody_stats(fa)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--clips-dir", help="wav ディレクトリを一括解析")
    src.add_argument("--wav", help="単一 wav を解析")
    ap.add_argument("--json-out", help="per-file 統計 + group median の JSON 出力先")
    args = ap.parse_args()

    paths = [Path(args.wav)] if args.wav else sorted(Path(args.clips_dir).glob("*.wav"))
    per_file: dict[str, dict | None] = {}
    for p in paths:
        stats = score_file(p)
        per_file[p.name] = stats
        if stats is None:
            _LOGGER.info("%s: n/a (too short or no voiced frames)", p.name)
        else:
            _LOGGER.info(
                "%s: f0 med=%.1fHz std=%.1fHz range(p5-p95)=%.1fHz nuclei/s=%.2f",
                p.name,
                stats["f0_median_hz"],
                stats["f0_std_hz"],
                stats["f0_range_p5_p95_hz"],
                stats["syllable_nuclei_per_sec"],
            )

    if args.wav and per_file[paths[0].name] is not None:
        stats = per_file[paths[0].name]
        print(f"{args.wav}\t" + "\t".join(f"{k}={v:.4f}" for k, v in stats.items()))

    if args.json_out:
        import json

        group = prosody_group_summary([s for s in per_file.values() if s is not None])
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(
                {"per_file": per_file, "group_median": group},
                f,
                ensure_ascii=False,
                indent=2,
            )
        _LOGGER.info("wrote %s", args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
