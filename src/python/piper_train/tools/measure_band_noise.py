#!/usr/bin/env python3
"""Voiced high-band excess — がびがび (高域エイリアス/平均化ノイズ) の追跡指標。

Why this exists (docs/design/zero-shot-noise-root-cause-pqmf.md 症状 7):
UTMOS / HNR / jitter / shimmer / CPPS / 変調 roughness / inter-harmonic SNR の
いずれも、zero-shot 合成の 5-9kHz に乗る非構造ノイズを検出できなかった
(実音声の当該帯域は本物でも倍音構造がほぼ無く、倍音ベースの指標は機能しない)。

調査 (2026-08-10) で唯一頑健だった信号差は「**有声フレームの平均スペクトルに
おける高域帯 (5-9kHz) の相対レベル**」: がびがび音声は有声音 (母音) でも高域が
ノイズで埋まり、参照帯 (1-3kHz) に対する高域比が клean 音声より数 dB 高くなる。

    metric = 10·log10( Σ_voiced E[5-9kHz] / Σ_voiced E[1-3kHz] )   [dB]

- 値が高い = 有声部の高域エネルギー過多 = がびがび疑い
- 有声フレーム限定 (簡易 YIN) にすることで、無声摩擦音の正当な高域を除外
- **同一テキスト・同一話者の A/B 比較用** (学習改善の前後比較、モデル間比較)。
  絶対値は話者・テキストに依存するため、単独の合否閾値には使わないこと

2026-08 Phase A (v10b plan §2 E-1/E-2/E-5(iv)) での拡張:

- **DEFAULT_HI_BAND を (5000, 9000) → (4000, 9000) に統一** (契約 §1 の
  「4-9kHz 帯域」・本走 harness (HF diag-phase0) と一致)。旧 TSV (v9 期) と
  直接比較する場合は ``--hi-lo 5000`` を明示すること。
- ``band_profile()`` (E-1): voiced/unvoiced/silence 別の 500Hz/1kHz 帯域ベクトル
  + per-frame 高域比の分布統計 (E-2、時間局在バーストの平均への希釈を防ぐ)。
  canonical は ``scripts/zs-quality-anatomy/anatomy.py`` の (a)/(e) — 5.5-8.5kHz
  照準値の事前登録 (plan §4.3) はその正規化 (dB rel 0-4k voiced power) で
  測られたため、定義変更は事前登録を無効化する。
- 既存 ``voiced_high_band_excess`` の関数本体は**無変更** (歴史的 TSV との
  A/B 継続性の契約)。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

Usage:
    python -m piper_train.tools.measure_band_noise --clips-dir DIR --output out.tsv
    python -m piper_train.tools.measure_band_noise --wav path.wav
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np


if TYPE_CHECKING:
    from piper_train.tools.acoustic_frames import FrameAnalysis


_LOGGER = logging.getLogger(__name__)

# E-5(iv): 2026-08 Phase A で (5000, 9000) → (4000, 9000) に統一 (契約 §1 /
# 本走 harness と一致)。旧 TSV (v9 期) と比較する場合は --hi-lo 5000 を明示。
DEFAULT_HI_BAND = (4000.0, 9000.0)
DEFAULT_REF_BAND = (1000.0, 3000.0)

# --- band_profile (E-1/E-2) の数値固定 (anatomy.py canonical) ---
BAND_EDGES_HZ = tuple(range(0, 11001, 500))  # 22 bands
SHELF_BAND_HZ = (5500.0, 8500.0)  # E-4 の再照準帯域 (500Hz bin 6 本)
PROFILE_REF_BAND_HZ = (1000.0, 3000.0)  # 1kHz ベクトルの基準 (plan E-1)
SHELF_REF_BAND_HZ = (0.0, 4000.0)  # 500Hz テーブル/照準値/無声/無音の基準 (anatomy)

# SHELF_BAND_HZ に完全包含される 500Hz band の index (11..16 の 6 bands)
_SHELF_BAND_IDX = tuple(
    b
    for b in range(len(BAND_EDGES_HZ) - 1)
    if BAND_EDGES_HZ[b] >= SHELF_BAND_HZ[0] and BAND_EDGES_HZ[b + 1] <= SHELF_BAND_HZ[1]
)
assert _SHELF_BAND_IDX == (11, 12, 13, 14, 15, 16)


def _yin_f0_track(
    wav: np.ndarray,
    sr: int,
    frame_length: int = 1024,
    hop: int = 256,
    fmin: float = 70.0,
    fmax: float = 400.0,
    voicing_threshold: float = 0.3,
) -> np.ndarray:
    """Simplified-YIN F0 tracker (per STFT frame, 0 = unvoiced).

    We only need a voiced/unvoiced decision plus rough F0; tracker error is
    irrelevant to the band-energy metric itself.
    """
    n_frames = max(0, (len(wav) - frame_length) // hop + 1)
    f0 = np.zeros(n_frames, dtype=np.float64)
    tau_min = int(sr / fmax)
    tau_max = int(sr / fmin)
    for i in range(n_frames):
        frame = wav[i * hop : i * hop + frame_length].astype(np.float64)
        frame = frame - frame.mean()
        if float(np.sum(frame**2)) < 1e-6:
            continue
        ac = np.correlate(frame, frame, mode="full")[frame_length - 1 :]
        d = 2 * ac[0] - 2 * ac
        d[0] = 0.0
        denom = np.cumsum(d[1:]) / np.arange(1, len(d))
        cmnd = np.ones_like(d)
        cmnd[1:] = d[1:] / np.maximum(denom, 1e-12)
        search = cmnd[tau_min:tau_max]
        if len(search) == 0:
            continue
        tau = int(np.argmin(search)) + tau_min
        if cmnd[tau] < voicing_threshold:
            f0[i] = sr / tau
    return f0


def voiced_high_band_excess(
    wav: np.ndarray,
    sr: int,
    hi_band: tuple[float, float] = DEFAULT_HI_BAND,
    ref_band: tuple[float, float] = DEFAULT_REF_BAND,
    n_fft: int = 1024,
    hop: int = 256,
) -> float | None:
    """Voiced-frame high-band vs reference-band energy ratio in dB.

    Returns None when the clip has no voiced frames (silence, noise-only).
    """
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    f0_track = _yin_f0_track(wav, sr, frame_length=n_fft, hop=hop)
    win = np.hanning(n_fft)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    hi_mask = (freqs >= hi_band[0]) & (freqs < hi_band[1])
    ref_mask = (freqs >= ref_band[0]) & (freqs < ref_band[1])
    if not hi_mask.any() or not ref_mask.any():
        return None

    e_hi = 0.0
    e_ref = 0.0
    n_voiced = 0
    for i, f0 in enumerate(f0_track):
        if f0 <= 0:
            continue
        start = i * hop
        frame = wav[start : start + n_fft]
        if len(frame) < n_fft:
            break
        spec = np.abs(np.fft.rfft(frame * win)) ** 2
        e_hi += float(spec[hi_mask].sum())
        e_ref += float(spec[ref_mask].sum())
        n_voiced += 1

    if n_voiced == 0 or e_ref <= 0:
        return None
    return float(10.0 * np.log10(e_hi / e_ref))


# ---------------------------------------------------------------------------
# E-1 / E-2: 帯域プロファイル (anatomy.py canonical、Phase A で契約化)
# ---------------------------------------------------------------------------


def _band_power_sums(
    mean_power: np.ndarray, freqs: np.ndarray, edges: Sequence[float]
) -> np.ndarray:
    """各 band [edges[i], edges[i+1]) の bin パワー和。最終 edge 以上の bin は除外。

    anatomy.py の band_index (searchsorted right - 1、f >= edges[-1] は -1)
    に基づく band 割当と同一。
    """
    mean_power = np.asarray(mean_power, dtype=np.float64)
    freqs = np.asarray(freqs, dtype=np.float64)
    out = np.empty(len(edges) - 1, dtype=np.float64)
    for i in range(len(edges) - 1):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        out[i] = mean_power[mask].sum()
    return out


def _ref_power(
    mean_power: np.ndarray, freqs: np.ndarray, ref_band: tuple[float, float]
) -> float:
    mask = (freqs >= ref_band[0]) & (freqs < ref_band[1])
    return float(np.asarray(mean_power, dtype=np.float64)[mask].sum()) + 1e-12


def band_vector_db(
    mean_power: np.ndarray,
    freqs: np.ndarray,
    edges: Sequence[float],
    ref_band: tuple[float, float],
) -> np.ndarray:
    """純関数: 各 band のパワー和 / ref 帯パワー和 [dB] (合成スペクトルで数学を pin する用)。

    epsilon は anatomy.py と同一 (ref に +1e-12、比に +1e-15) — 比率指標なので
    入力の任意ゲインに不変。
    """
    band_pow = _band_power_sums(mean_power, freqs, edges)
    ref = _ref_power(mean_power, freqs, ref_band)
    return 10.0 * np.log10(band_pow / ref + 1e-15)


def band_profile(fa: FrameAnalysis) -> dict | None:
    """voiced/unvoiced/silence 別の帯域ベクトル + per-frame 高域比の分布統計。

    voiced フレームが 10 未満なら None。正規化は 2 本立て【決定 D6】:

    - ``band_db_1khz``: rel 1-3kHz voiced power (plan E-1 の比較プロファイル)
    - ``band_db_500hz`` / unvoiced / silence: rel 0-4kHz voiced power
      (anatomy 互換 — §4.3 の事前登録値はこの正規化で測られた)

    1kHz ベクトルは 500Hz 分解能の隣接 2 band のパワー和から導出 (anatomy parity
    と E-1 の 1kHz 刻みの両立)。``hi_ref_frame_db`` (E-2) は voiced フレームごとの
    10·log10(Σ P[hi] / Σ P[ref]) の分布統計 — ``frac_above_median_plus_6db`` は
    clip 自身の median +6dB を超えるフレーム率 (時間局在バーストの検出、実音声
    アンカーなしで自己完結)。
    """
    n_voiced = int(fa.voiced.sum())
    if n_voiced < 10:
        return None

    freqs = fa.freqs
    pm_voiced = fa.power[:, fa.voiced].mean(axis=1)
    ref_shelf = _ref_power(pm_voiced, freqs, SHELF_REF_BAND_HZ)
    ref_profile = _ref_power(pm_voiced, freqs, PROFILE_REF_BAND_HZ)

    band_pow_500 = _band_power_sums(pm_voiced, freqs, BAND_EDGES_HZ)
    band_db_500 = 10.0 * np.log10(band_pow_500 / ref_shelf + 1e-15)
    band_pow_1k = band_pow_500[0::2] + band_pow_500[1::2]  # 隣接 2 band のパワー和
    band_db_1k = 10.0 * np.log10(band_pow_1k / ref_profile + 1e-15)

    def _masked_band_db(mask: np.ndarray, min_frames: int = 5) -> list[float] | None:
        if int(mask.sum()) < min_frames:
            return None
        pm = fa.power[:, mask].mean(axis=1)
        bp = _band_power_sums(pm, freqs, BAND_EDGES_HZ)
        return [float(v) for v in 10.0 * np.log10(bp / ref_shelf + 1e-15)]

    # E-2: per-frame 高域比の分布 (帯域は E-5(iv) 統一後の DEFAULT_HI/REF_BAND)
    hi_mask = (freqs >= DEFAULT_HI_BAND[0]) & (freqs < DEFAULT_HI_BAND[1])
    ref_mask = (freqs >= DEFAULT_REF_BAND[0]) & (freqs < DEFAULT_REF_BAND[1])
    pv = fa.power[:, fa.voiced]
    frame_db = 10.0 * np.log10(
        (pv[hi_mask].sum(axis=0) + 1e-15) / (pv[ref_mask].sum(axis=0) + 1e-15)
    )
    frame_median = float(np.median(frame_db))
    hi_ref_frame_db = {
        "median": frame_median,
        "p90": float(np.percentile(frame_db, 90)),
        "p99": float(np.percentile(frame_db, 99)),
        "frac_above_median_plus_6db": float(np.mean(frame_db > frame_median + 6.0)),
    }

    return {
        "band_db_500hz": [float(v) for v in band_db_500],
        "band_db_1khz": [float(v) for v in band_db_1k],
        "unvoiced_band_db_500hz": _masked_band_db(fa.unvoiced),
        "silence_band_db_500hz": _masked_band_db(fa.silence),  # 診断用 (gate なし)
        "hi_ref_frame_db": hi_ref_frame_db,
        "n_voiced": n_voiced,
        "n_unvoiced": int(fa.unvoiced.sum()),
        "n_silence": int(fa.silence.sum()),
    }


def _nanmean_vectors(rows: list[list[float] | None], width: int) -> list[float] | None:
    """None 行を all-NaN として nanmean (anatomy の agg と同一)。全滅なら None。"""
    stacked = np.array(
        [row if row is not None else [np.nan] * width for row in rows], dtype=float
    )
    if np.isnan(stacked).all():
        return None
    with np.errstate(all="ignore"):
        return [float(v) for v in np.nanmean(stacked, axis=0)]


def band_group_summary(profiles: list[dict]) -> dict | None:
    """band_profile のグループ集計。ベクトル類は nanmean across files
    (anatomy parity)、hi_ref_frame_db は各統計の median across files【決定 D12】。
    """
    if not profiles:
        return None
    n_500 = len(BAND_EDGES_HZ) - 1
    frame_stats = {
        key: float(np.median([p["hi_ref_frame_db"][key] for p in profiles]))
        for key in ("median", "p90", "p99", "frac_above_median_plus_6db")
    }
    return {
        "band_db_500hz": _nanmean_vectors(
            [p["band_db_500hz"] for p in profiles], n_500
        ),
        "band_db_1khz": _nanmean_vectors(
            [p["band_db_1khz"] for p in profiles], n_500 // 2
        ),
        "unvoiced_band_db_500hz": _nanmean_vectors(
            [p["unvoiced_band_db_500hz"] for p in profiles], n_500
        ),
        "silence_band_db_500hz": _nanmean_vectors(
            [p["silence_band_db_500hz"] for p in profiles], n_500
        ),
        "hi_ref_frame_db": frame_stats,
        "n_files": len(profiles),
        "n_voiced_total": int(sum(p["n_voiced"] for p in profiles)),
        "n_unvoiced_total": int(sum(p["n_unvoiced"] for p in profiles)),
        "n_silence_total": int(sum(p["n_silence"] for p in profiles)),
    }


def band_delta_vs_real(synth_summary: dict, real_summary: dict) -> dict:
    """帯域プロファイルのグループ平均差 (synth − real)。

    ``shelf_voiced_max_delta_db`` は 5.5-8.5kHz の 500Hz bin 6 本の delta の
    **max**【決定 D7】 — mean だと 5-6kHz 集中が希釈される (E-1 の趣旨)。§4.3 の
    gate (≤ +2.0dB) の対象。mean は参考値として併記。無声は別枠 (≤ +3.0dB)。
    """

    def _delta_vec(key: str) -> np.ndarray | None:
        a, b = synth_summary.get(key), real_summary.get(key)
        if a is None or b is None:
            return None
        return np.asarray(a, dtype=float) - np.asarray(b, dtype=float)

    delta_1k = _delta_vec("band_db_1khz")
    delta_500 = _delta_vec("band_db_500hz")
    shelf_idx = list(_SHELF_BAND_IDX)
    shelf_voiced = delta_500[shelf_idx] if delta_500 is not None else None
    delta_unv = _delta_vec("unvoiced_band_db_500hz")
    shelf_unvoiced = delta_unv[shelf_idx] if delta_unv is not None else None

    def _nan_reduce(vec: np.ndarray | None, fn) -> float | None:
        if vec is None or np.isnan(vec).all():
            return None
        with np.errstate(all="ignore"):
            return float(fn(vec))

    return {
        "band_delta_vs_real_1khz": (
            None if delta_1k is None else [float(v) for v in delta_1k]
        ),
        "shelf_voiced_delta_db_per_bin": (
            None if shelf_voiced is None else [float(v) for v in shelf_voiced]
        ),
        "shelf_voiced_max_delta_db": _nan_reduce(shelf_voiced, np.nanmax),
        "shelf_voiced_mean_delta_db": _nan_reduce(shelf_voiced, np.nanmean),
        "shelf_unvoiced_max_delta_db": _nan_reduce(shelf_unvoiced, np.nanmax),
    }


def score_file(
    path: Path,
    hi_band: tuple[float, float] = DEFAULT_HI_BAND,
    ref_band: tuple[float, float] = DEFAULT_REF_BAND,
) -> float | None:
    import soundfile as sf

    wav, sr = sf.read(str(path), dtype="float32")
    return voiced_high_band_excess(
        np.asarray(wav), sr, hi_band=hi_band, ref_band=ref_band
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--clips-dir", help="wav ディレクトリを一括採点")
    src.add_argument("--wav", help="単一 wav を採点")
    ap.add_argument("--output", help="tsv 出力先 (path\\tvoiced_hi_excess_db)")
    ap.add_argument("--hi-lo", type=float, default=DEFAULT_HI_BAND[0])
    ap.add_argument("--hi-hi", type=float, default=DEFAULT_HI_BAND[1])
    ap.add_argument("--ref-lo", type=float, default=DEFAULT_REF_BAND[0])
    ap.add_argument("--ref-hi", type=float, default=DEFAULT_REF_BAND[1])
    args = ap.parse_args()

    hi_band = (args.hi_lo, args.hi_hi)
    ref_band = (args.ref_lo, args.ref_hi)
    if args.wav:
        v = score_file(Path(args.wav), hi_band, ref_band)
        print(f"{args.wav}\t{v if v is None else round(v, 3)}")
        return 0

    rows = []
    for p in sorted(Path(args.clips_dir).glob("*.wav")):
        v = score_file(p, hi_band, ref_band)
        rows.append((p.name, v))
        _LOGGER.info("%s: %s", p.name, "n/a" if v is None else f"{v:.3f} dB")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("path\tvoiced_hi_excess_db\n")
            for name, v in rows:
                f.write(f"{name}\t{'' if v is None else round(v, 3)}\n")
        _LOGGER.info("wrote %s (%d rows)", args.output, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
