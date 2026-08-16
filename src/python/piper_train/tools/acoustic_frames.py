#!/usr/bin/env python3
"""共有フレーム解析 — 帯域/韻律メトリクスの土台 (STFT + pyin voiced 判定)。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

canonical: ``scripts/zs-quality-anatomy/anatomy.py`` の analyze() 前段
(RMS 正規化 ×0.1 → STFT 2048/256 → pyin(70-600Hz) → energy gate 付き
voiced/unvoiced/silence 分類) を数値固定で移植したもの。v10b plan §1 の実測
baseline (帯域テーブル / F0 統計) は全てこの判定で測られたため、パラメータの
変更は事前登録 (plan §4.3) を無効化する — 変更禁止。

``band_profile`` (measure_band_noise) と ``prosody_stats`` (measure_prosody) は
同一の :class:`FrameAnalysis` を受け取る — pyin (支配的コスト) を 1 ファイル
1 回に抑えるための共有構造体。

内部演算は float64。解析 SR は 22050 固定 (他 SR は load_wav() で resample。
analyze_frames に 22050 以外を渡すと ValueError — silent 二重 resample 防止)。
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np


SR_ANALYSIS = 22050
N_FFT = 2048
HOP = 256
PYIN_FMIN = 70.0
PYIN_FMAX = 600.0
MIN_DURATION_SEC = 0.5

# anatomy.py L72-73 の energy gate (rms_db の p95 基準)
VOICED_ENERGY_GATE_DB = 30.0
SILENCE_GATE_DB = 45.0


@dataclasses.dataclass
class FrameAnalysis:
    """1 クリップのフレーム解析結果 (anatomy.py analyze() 前段と同一定義)。"""

    power: np.ndarray  # [1025, T] float64 (|STFT|², RMS 正規化 ×0.1 後)
    freqs: np.ndarray  # [1025] Hz
    f0: np.ndarray  # [T] Hz、NaN = unvoiced (pyin fill_na)
    voiced: np.ndarray  # [T] bool: pyin voiced & energy gate & ~isnan(f0)
    unvoiced: np.ndarray  # [T] bool: ~voiced & ~silence
    silence: np.ndarray  # [T] bool: rms_db < p95 - 45
    rms_db: np.ndarray  # [T] 10·log10(per-frame total power)
    sr: int
    hop: int
    duration_sec: float


def load_wav(path: str | Path, sr: int = SR_ANALYSIS) -> np.ndarray:
    """wav を mono float で読み込み (必要なら sr へ resample)。"""
    import librosa

    wav, _ = librosa.load(str(path), sr=sr, mono=True)
    return np.asarray(wav)


def analyze_frames(wav: np.ndarray, sr: int) -> FrameAnalysis | None:
    """anatomy.py canonical のフレーム解析。0.5 秒未満は None。

    sr != 22050 は ValueError (resample は load_wav() 側の責務)。
    """
    if sr != SR_ANALYSIS:
        raise ValueError(
            f"analyze_frames requires sr={SR_ANALYSIS} (got {sr}); "
            "resample via load_wav() first"
        )
    import librosa

    y = np.asarray(wav, dtype=np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if len(y) < MIN_DURATION_SEC * sr:
        return None

    # anatomy.py L63: RMS 正規化 (×0.1 スケール込み)
    y = y / (np.sqrt(np.mean(y**2)) + 1e-9) * 0.1
    power = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    f0, vflag, _ = librosa.pyin(
        y, fmin=PYIN_FMIN, fmax=PYIN_FMAX, sr=sr, frame_length=N_FFT, hop_length=HOP
    )

    # anatomy.py L68-69: STFT / pyin のフレーム数を短い方へ切り詰め
    n_frames = min(power.shape[1], len(f0))
    power = power[:, :n_frames]
    f0 = np.asarray(f0, dtype=np.float64)[:n_frames]
    vflag = np.asarray(vflag, dtype=bool)[:n_frames]

    rms_db = 10.0 * np.log10(power.sum(axis=0) + 1e-12)
    p95 = np.percentile(rms_db, 95)
    voiced = vflag & (rms_db > p95 - VOICED_ENERGY_GATE_DB) & ~np.isnan(f0)
    silence = rms_db < p95 - SILENCE_GATE_DB
    unvoiced = ~voiced & ~silence

    return FrameAnalysis(
        power=power,
        freqs=freqs,
        f0=f0,
        voiced=voiced,
        unvoiced=unvoiced,
        silence=silence,
        rms_db=rms_db,
        sr=sr,
        hop=HOP,
        duration_sec=len(y) / sr,
    )
