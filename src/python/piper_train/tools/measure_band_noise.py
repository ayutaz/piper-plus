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

Usage:
    python -m piper_train.tools.measure_band_noise --clips-dir DIR --output out.tsv
    python -m piper_train.tools.measure_band_noise --wav path.wav
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np


_LOGGER = logging.getLogger(__name__)

DEFAULT_HI_BAND = (5000.0, 9000.0)
DEFAULT_REF_BAND = (1000.0, 3000.0)


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


def score_file(
    path: Path,
    hi_band: tuple[float, float] = DEFAULT_HI_BAND,
    ref_band: tuple[float, float] = DEFAULT_REF_BAND,
) -> float | None:
    import soundfile as sf

    wav, sr = sf.read(str(path), dtype="float32")
    return voiced_high_band_excess(np.asarray(wav), sr, hi_band=hi_band, ref_band=ref_band)


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
