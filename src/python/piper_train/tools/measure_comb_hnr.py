#!/usr/bin/env python3
"""comb-HNR@1-3kHz — A3 (調波間ノイズ充填 = がびがびの主犯) の直接測定。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

canonical: v10b 残存ノイズ診断 (docs/design/zero-shot-v10b-residual-noise-diagnosis.md
§1/§8) のインライン測定を数値固定で収載したもの (診断 doc §7 の移植予定の実施)。
定義: librosa.stft(2048/256) パワー + librosa.pyin(70-600Hz) voiced フレームで、
帯域 [1000, 3000]Hz 内の調波 bin (k·F0) と中間 bin ((k+0.5)·F0) の平均パワー比
10·log10 をフレームごとに取り、クリップ median を返す。

**測定プロトコル (変更禁止)**: F0 格子は**出力自身の F0 トラック** (pyin) で
張る。GT / 予測 F0 格子で測ると ±20 cent の系統誤差で 18.7dB → 0.7dB に崩壊
する (v11 harmonic head 設計 §5.3 deviation 4 の実測)。外部格子
(:func:`comb_hnr_at_reference`) はサブハーモニック / オクターブ下エラー診断
(:func:`detect_octave_down`) 専用で、gate への使用は禁止。

**exact-track fallback (carrier head 専用、2026-08-21)**: carrier head モデル
の f0_decoder track は oscillator がそのまま消費するため cent 誤差ゼロ
(±20 cent 罠は「推定」格子の話で適用外)。pyin が voicing を全滅判定した
クリップ (実例: v11 smoke arm H ns=0.0 — band0 carrier/noise ~-2dB で pyin
voiced 0、実際は decoder 格子 comb 5.9-6.1dB) では self-track が null になり
「完全非周期」と誤読される。:func:`comb_hnr_at_exact_track` は pyin 非依存
(voiced = track > 1Hz) の測定で、この誤判定を防ぐ。事前登録 gate (#2
ns=0.667 ≥10dB) は self-track のまま、ns 掃引 (#3) の測定不能点の補完に使い、
どちらの track かを必ず出力に明記する。

既知アンカー (22.05kHz / band 1-3kHz / クリップ median、診断 doc §1/§6 実測):

    GT (moe-speech 実音声)        : 13.2 dB
    v10b ep79 EMA ns=0.667        :  4.6 dB  (A3 残存 = がびがび、GT 比 -8.6dB)
    v10b ns=0.0 (deterministic)   : 12.3 dB  (GT 級 — H-A 構造限界説の棄却根拠)
    single-speaker FT (v7 系, n=3): 11.6 dB
    teacher-forced recon          :  6.7 dB  (§8 — 損失は見ていて ~6.7dB で平衡)

読み方: ≥10dB ≈ 調波ロック獲得 (GT 級)、~5dB = A3 残存。v11 Phase D smoke の
事前登録 gate は「出力自身の F0 トラックで ≥10dB」(head 設計 §7 #2)。

Usage:
    python -m piper_train.tools.measure_comb_hnr --wav path.wav
    python -m piper_train.tools.measure_comb_hnr --clips-dir DIR --json-out out.json
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger(__name__)

SR_ANALYSIS = 22050
N_FFT = 2048
HOP = 256
PYIN_FMIN = 70.0
PYIN_FMAX = 600.0
DEFAULT_BAND_HZ = (1000.0, 3000.0)
MIN_DURATION_SEC = 0.5

# oct↓ 判定の f0 比レンジ (自トラック F0 / 意図 F0)。period-doubling は比 ≈ 0.5。
# ±20 cent の系統誤差 (比 ≈ 1) を oct↓ と誤判定しないため、格子崩壊ではなく
# f0 比を主根拠にする【v11 head 設計 §5.3 #3】。
OCTAVE_DOWN_RATIO_RANGE = (0.4, 0.6)


def _frame_comb_ratio_db(
    power_col: np.ndarray,
    f0_hz: float,
    sr: int,
    n_fft: int,
    band: tuple[float, float],
) -> float | None:
    """1 フレームの調波 bin vs 中間 bin パワー比 [dB] (診断 doc canonical)。"""
    freq_per_bin = sr / n_fft
    k_lo = int(np.ceil(band[0] / f0_hz))
    k_hi = int(np.floor(band[1] / f0_hz))
    if k_hi < k_lo:
        return None
    harm_bins: list[int] = []
    mid_bins: list[int] = []
    n_bins = power_col.shape[0]
    for k in range(k_lo, k_hi + 1):
        hb = round(k * f0_hz / freq_per_bin)
        mb = round((k + 0.5) * f0_hz / freq_per_bin)
        if hb < n_bins:
            harm_bins.append(hb)
        if (k + 0.5) * f0_hz <= band[1] and mb < n_bins:
            mid_bins.append(mb)
    if not harm_bins or not mid_bins:
        return None
    hp = float(np.mean(power_col[harm_bins]))
    mp = float(np.mean(power_col[mid_bins]))
    if hp <= 0 or mp <= 0:
        return None
    return float(10.0 * np.log10(hp / mp))


def comb_hnr_frames(
    power: np.ndarray,
    f0: np.ndarray,
    voiced: np.ndarray,
    sr: int,
    n_fft: int = N_FFT,
    band: tuple[float, float] = DEFAULT_BAND_HZ,
) -> list[float]:
    """フレーム列の comb-HNR [dB] を返す純関数 (F0/voiced は呼び出し側が供給)。

    Args:
        power: [n_bins, T] パワースペクトログラム (|STFT|²)。
        f0: [T] Hz。NaN は unvoiced として skip。
        voiced: [T] bool。
        sr / n_fft / band: 格子計算のパラメータ。

    Returns:
        voiced かつ格子が張れたフレームの比 [dB] のリスト (順序保存)。
    """
    n_frames = min(power.shape[1], len(f0), len(voiced))
    ratios: list[float] = []
    for t in range(n_frames):
        if not voiced[t] or not np.isfinite(f0[t]):
            continue
        r = _frame_comb_ratio_db(power[:, t], float(f0[t]), sr, n_fft, band)
        if r is not None:
            ratios.append(r)
    return ratios


def _stft_power_and_pyin(
    y: np.ndarray, sr: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """|STFT|² + pyin (canonical パラメータ)。フレーム数は短い方へ揃える。"""
    import librosa  # noqa: PLC0415 — lazy import (import 時コストの回避、house style)

    power = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr, frame_length=N_FFT, hop_length=HOP
    )
    n = min(power.shape[1], len(f0))
    return (
        power[:, :n],
        np.asarray(f0, dtype=np.float64)[:n],
        np.asarray(voiced_flag, dtype=bool)[:n],
    )


def _validate_input(y: np.ndarray, sr: int) -> np.ndarray | None:
    if sr != SR_ANALYSIS:
        raise ValueError(
            f"comb_hnr requires sr={SR_ANALYSIS} (got {sr}); "
            "resample at load time (load_wav) instead"
        )
    y = np.asarray(y, dtype=np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if len(y) < MIN_DURATION_SEC * sr:
        _LOGGER.warning(
            "clip too short for comb-HNR (%.3fs < %.1fs)",
            len(y) / sr,
            MIN_DURATION_SEC,
        )
        return None
    return y


def comb_hnr(
    y: np.ndarray, sr: int, band: tuple[float, float] = DEFAULT_BAND_HZ
) -> float | None:
    """クリップの comb-HNR [dB] median — **出力自身の F0 トラック**で測る。

    アンカー値・測定プロトコルは module docstring 参照。voiced フレームが
    無い / 0.5 秒未満は None。sr != 22050 は ValueError (silent 二重
    resample 防止)。
    """
    y = _validate_input(y, sr)
    if y is None:
        return None
    power, f0, voiced = _stft_power_and_pyin(y, sr)
    ratios = comb_hnr_frames(power, f0, voiced, sr, band=band)
    if not ratios:
        return None
    return float(np.median(ratios))


def comb_hnr_at_reference(
    y: np.ndarray,
    sr: int,
    f0_ref_hz: float | np.ndarray,
    band: tuple[float, float] = DEFAULT_BAND_HZ,
) -> float | None:
    """外部 F0 格子 (GT / 予測) での comb-HNR [dB] median — **診断専用**。

    ±20 cent の系統誤差で崩壊する (18.7 → 0.7dB、v11 head 設計 §5.3) ため
    **gate / go-no-go への使用は禁止**。用途はサブハーモニック挿入 (oct↓
    エラー) の検出のみ (:func:`detect_octave_down`)。voiced 判定は出力自身の
    pyin を使い、格子 F0 だけを差し替える。
    """
    y = _validate_input(y, sr)
    if y is None:
        return None
    power, f0, voiced = _stft_power_and_pyin(y, sr)
    if np.isscalar(f0_ref_hz):
        f0_ext = np.full(len(f0), float(f0_ref_hz))
    else:
        f0_ext = np.asarray(f0_ref_hz, dtype=np.float64)
        n = min(len(f0), len(f0_ext))
        f0_ext, voiced, power = f0_ext[:n], voiced[:n], power[:, :n]
    ratios = comb_hnr_frames(power, f0_ext, voiced, sr, band=band)
    if not ratios:
        return None
    return float(np.median(ratios))


def comb_hnr_at_exact_track(
    y: np.ndarray,
    sr: int,
    f0_track_hz: np.ndarray,
    band: tuple[float, float] = DEFAULT_BAND_HZ,
) -> float | None:
    """decoder 消費 F0 track (cent 誤差ゼロ) での comb-HNR [dB] median。

    **carrier head モデル専用の pyin 非依存 fallback** (module docstring の
    exact-track fallback 節参照)。voiced 判定も track 自身 (f0 > 1Hz) から
    取るため、pyin の voicing 全滅 (band0 carrier/noise 悪化時) に影響され
    ない。track は frame 格子 (hop 256) の Hz 値、無声 = 0。[1, 1, T] 等の
    tensor dump 形状も受理する。

    :func:`comb_hnr_at_reference` (pyin voiced 依存、oct↓ 診断用) とは別物。
    非 carrier モデルの GT / 予測「推定」格子に使うと ±20 cent 罠で崩壊する
    ため、その用途は引き続き禁止。
    """
    y = _validate_input(y, sr)
    if y is None:
        return None
    import librosa  # noqa: PLC0415 — lazy import (import 時コストの回避、house style)

    power = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
    f0 = np.asarray(f0_track_hz, dtype=np.float64).reshape(-1)
    n = min(power.shape[1], len(f0))
    f0 = f0[:n]
    power = power[:, :n]
    voiced = f0 > 1.0
    ratios = comb_hnr_frames(power, f0, voiced, sr, band=band)
    if not ratios:
        return None
    return float(np.median(ratios))


def detect_octave_down(
    y: np.ndarray,
    sr: int,
    f0_ref_hz: float | np.ndarray,
    band: tuple[float, float] = DEFAULT_BAND_HZ,
) -> dict:
    """サブハーモニック挿入 (period-doubling = oct↓ エラー) の検出 — 診断専用。

    oct↓ の破綻モード (v11 head 設計 §5.3 #3): サブハーモニックが意図 F0 格子の
    中間 bin に落ち、GT 格子 comb は ~0.8dB に崩壊する。ただし ±20 cent の
    系統誤差でも GT 格子は崩壊するため、flag は**自トラック F0 と意図 F0 の比**
    (≈ 0.5 なら oct↓) を主根拠にし、格子値は証拠として併記する。

    Returns:
        dict: comb_hnr_self_db (自格子) / comb_hnr_ref_grid_db (意図格子) /
        f0_self_median_hz / f0_ref_median_hz / f0_ratio_median /
        octave_down_flag。測定不能な値は None (flag はその場合 None)。
    """
    y_val = _validate_input(y, sr)
    if y_val is None:
        return {
            "comb_hnr_self_db": None,
            "comb_hnr_ref_grid_db": None,
            "f0_self_median_hz": None,
            "f0_ref_median_hz": None,
            "f0_ratio_median": None,
            "octave_down_flag": None,
        }
    power, f0, voiced = _stft_power_and_pyin(y_val, sr)
    self_ratios = comb_hnr_frames(power, f0, voiced, sr, band=band)
    self_db = float(np.median(self_ratios)) if self_ratios else None

    f0_voiced = f0[voiced & np.isfinite(f0)]
    f0_self_median = float(np.median(f0_voiced)) if f0_voiced.size else None
    if np.isscalar(f0_ref_hz):
        f0_ref_median = float(f0_ref_hz)
    else:
        arr = np.asarray(f0_ref_hz, dtype=np.float64)
        arr = arr[np.isfinite(arr)]
        f0_ref_median = float(np.median(arr)) if arr.size else None

    ref_grid_db = comb_hnr_at_reference(y, sr, f0_ref_hz, band=band)

    ratio: float | None = None
    flag: bool | None = None
    if f0_self_median is not None and f0_ref_median:
        ratio = f0_self_median / f0_ref_median
        lo, hi = OCTAVE_DOWN_RATIO_RANGE
        flag = bool(lo <= ratio <= hi)

    return {
        "comb_hnr_self_db": self_db,
        "comb_hnr_ref_grid_db": ref_grid_db,
        "f0_self_median_hz": f0_self_median,
        "f0_ref_median_hz": f0_ref_median,
        "f0_ratio_median": ratio,
        "octave_down_flag": flag,
    }


def score_file(path: Path, band: tuple[float, float] = DEFAULT_BAND_HZ) -> float | None:
    """wav を 22.05kHz mono で読み込み comb_hnr を返す。"""
    from piper_train.tools.acoustic_frames import load_wav  # noqa: PLC0415

    return comb_hnr(load_wav(path, sr=SR_ANALYSIS), SR_ANALYSIS, band=band)


def score_file_exact(
    path: Path, track_path: Path, band: tuple[float, float] = DEFAULT_BAND_HZ
) -> float | None:
    """wav + `<stem>.f0.npy` (frame 格子 Hz、無声=0) で exact-track comb を返す。"""
    from piper_train.tools.acoustic_frames import load_wav  # noqa: PLC0415

    if not track_path.is_file():
        return None
    return comb_hnr_at_exact_track(
        load_wav(path, sr=SR_ANALYSIS), SR_ANALYSIS, np.load(track_path), band=band
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--clips-dir", help="wav ディレクトリを一括採点")
    src.add_argument("--wav", help="単一 wav を採点")
    ap.add_argument(
        "--band",
        nargs=2,
        type=float,
        default=list(DEFAULT_BAND_HZ),
        metavar=("FMIN", "FMAX"),
        help="測定帯域 Hz (default: 1000 3000 = A3 帯域。アンカー値は default 専用)",
    )
    ap.add_argument("--json-out", help="per-file + median/mean の JSON 出力先")
    ap.add_argument(
        "--f0-track-dir",
        help="decoder 消費 F0 track (`<stem>.f0.npy`, frame 格子 Hz, 無声=0) の"
        "ディレクトリ。carrier head モデル専用 — pyin voicing 全滅で self-track"
        " が null になるクリップの exact-track 補完 (per_file_exact /"
        " median_exact を追加、既存 self-track フィールドは不変)",
    )
    args = ap.parse_args()

    band = (float(args.band[0]), float(args.band[1]))
    paths = [Path(args.wav)] if args.wav else sorted(Path(args.clips_dir).glob("*.wav"))
    per_file: dict[str, float | None] = {}
    per_file_exact: dict[str, float | None] = {}
    for p in paths:
        v = score_file(p, band=band)
        per_file[p.name] = None if v is None else round(v, 3)
        _LOGGER.info("%s: comb_hnr=%s dB", p.name, "n/a" if v is None else f"{v:.3f}")
        if args.f0_track_dir:
            ve = score_file_exact(
                p, Path(args.f0_track_dir) / f"{p.stem}.f0.npy", band=band
            )
            per_file_exact[p.name] = None if ve is None else round(ve, 3)
            _LOGGER.info(
                "%s: comb_hnr_exact=%s dB",
                p.name,
                "n/a" if ve is None else f"{ve:.3f}",
            )

    vals = [v for v in per_file.values() if v is not None]
    summary = {
        "band_hz": list(band),
        "f0_track": "self",
        "per_file": per_file,
        "median": round(float(np.median(vals)), 3) if vals else None,
        "mean": round(float(np.mean(vals)), 3) if vals else None,
    }
    if args.f0_track_dir:
        vals_e = [v for v in per_file_exact.values() if v is not None]
        summary["f0_track_exact"] = "decoder-consumed (carrier head)"
        summary["per_file_exact"] = per_file_exact
        summary["median_exact"] = round(float(np.median(vals_e)), 3) if vals_e else None
        summary["mean_exact"] = round(float(np.mean(vals_e)), 3) if vals_e else None
    # ASCII-only (Windows cp932 console でも化けない)
    print(
        f"comb_hnr median: {summary['median']} dB "
        "(anchors: GT 13.2 / v10b ns0.667 4.6 / ns0.0 12.3)"
    )
    if args.json_out:
        import json  # noqa: PLC0415

        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        _LOGGER.info("wrote %s", args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
