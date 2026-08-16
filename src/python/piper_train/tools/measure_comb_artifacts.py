#!/usr/bin/env python3
"""SR/128 格子コム超過 + >4kHz 残差 autocorr — がびがびコムのゲーム不能量 (E-4)。

EVAL-ONLY: 本モジュールの全指標は評価専用。学習 loss / reward / 動的サンプル選別への
流用を恒久禁止 (docs/spec/zs-eval-contract.md §2 禁止事項 4)。

canonical: ``scripts/zs-quality-anatomy/comb_check.py`` の計算を数値固定で移植
(v10b plan §1 の実測 baseline — comb 超過 r2 +4.1〜4.7dB / GT 0.65-0.76dB、
autocorr r2 0.10-0.24 / GT 0.006-0.13 — と §4.3 の事前登録 gate <1.5dB / <0.05
はこの定義に対して登録されている。定義変更は事前登録を無効化する)。

指標 2 本:

1. **comb_excess_db** — highpass(4kHz) 後の平均パワースペクトルで、フレーム格子
   周波数 (SR/128 = 172.266Hz の整数倍 = n_fft 2048 の bin index 16k) 上の peak
   (中心 ±1 bin) が近傍 (±4〜8 bin) の median をどれだけ超えるか [dB]。
   4-8.5kHz の 26 格子点の算術平均。
2. **hf_autocorr_lag128 / lag256** — highpass(4kHz) 後信号の全長正規化
   autocorrelation の |ac[128]| / |ac[256]| (lag = hop//2, hop)。フレーム単位で
   タイル化された残差 (がびがびの機序) は HP 後も周期を保ち ac→1 に漸近する。

**voiced ゲートは掛けない** (全フレーム平均): コムは定常アーティファクトで
無音部にも現れ、baseline 値もゲートなしで測定された (v10b plan §1.3)。

測定は export 済みモデルの素の出力 wav に対して行うこと (EQ / デノイズ等の
後処理は契約 §2 禁止事項 5 で禁止 — 内部 RMS 正規化と 22.05kHz resample のみ許可)。
本モジュールは測るだけで pass/fail 判定はしない (判定は /eval-zs skill の責務)。

Usage:
    python -m piper_train.tools.measure_comb_artifacts --wav path.wav
    python -m piper_train.tools.measure_comb_artifacts --clips-dir DIR \
        --output out.tsv --json-out out.json
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
GRID_STEP_BINS = 16  # 16 bins = 172.265625 Hz = SR/128
COMB_BAND_HZ = (4000.0, 8500.0)
HIGHPASS_HZ = 4000.0
AUTOCORR_LAGS = (HOP // 2, HOP)  # (128, 256)
MIN_DURATION_SEC = 0.5

_BIN_HZ = SR_ANALYSIS / N_FFT  # 10.7666015625 Hz/bin

# 測定格子: COMB_BAND_HZ 内の GRID_STEP_BINS 倍数 bin (26 bins)。
# comb_check.py L42-45 は `g in arange(16, 1024, 16) if 372 <= g <= 790` —
# 16 の倍数で切ると同一集合になることを固定 (canonical 同一性の pin)。
GRID_BINS = tuple(
    g
    for g in range(GRID_STEP_BINS, N_FFT // 2, GRID_STEP_BINS)
    if COMB_BAND_HZ[0] <= g * _BIN_HZ <= COMB_BAND_HZ[1]
)
_CANONICAL_GRID_BINS = tuple(
    g for g in range(GRID_STEP_BINS, N_FFT // 2, GRID_STEP_BINS) if 372 <= g <= 790
)
assert _CANONICAL_GRID_BINS == GRID_BINS, (
    "grid bins diverged from comb_check.py canonical set"
)
assert len(GRID_BINS) == 26 and GRID_BINS[0] == 384 and GRID_BINS[-1] == 784


def comb_metrics(wav: np.ndarray, sr: int) -> dict | None:
    """SR/128 格子コム超過 + >4kHz 残差 autocorr (EVAL-ONLY、学習 loss 流用禁止)。

    sr != 22050 は ValueError (silent 二重 resample 防止。resample は
    score_file 側の librosa.load で行う)。0.5 秒未満は None (警告)。

    戻り値:
      {"comb_excess_db": float,             # 26 格子点の超過 [dB] の算術平均
       "hf_autocorr_lag128": float,         # abs(ac[hop//2])
       "hf_autocorr_lag256": float,         # abs(ac[hop])
       "hf_autocorr_max_lag16_512": float,  # 診断付録: max(abs(ac[16:513]))
       "hf_autocorr_argmax_lag": int}       # ↑の argmax lag

    abs() は【決定】事項: 事前登録 gate「<0.05」は大きさの制約であり、負の
    周期相関も同罪のため (comb_check.py は生値 print だった)。
    """
    if sr != SR_ANALYSIS:
        raise ValueError(
            f"comb_metrics requires sr={SR_ANALYSIS} (got {sr}); "
            "resample at load time (score_file) instead"
        )
    import librosa
    from scipy.signal import butter, sosfilt

    y = np.asarray(wav, dtype=np.float64)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if len(y) < MIN_DURATION_SEC * sr:
        _LOGGER.warning(
            "clip too short for comb metrics (%.3fs < %.1fs)",
            len(y) / sr,
            MIN_DURATION_SEC,
        )
        return None

    # comb_check.py L30: RMS 正規化 (×0.1 スケールなし — 比率指標なので結果不変)
    y = y / (np.sqrt(np.mean(y**2)) + 1e-9)
    sos = butter(6, HIGHPASS_HZ, btype="highpass", fs=sr, output="sos")
    hp = sosfilt(sos, y)  # 片方向 (filtfilt にしない — canonical 一致)

    # --- comb excess (comb_check.py L40-50) ---
    spec = np.abs(librosa.stft(hp, n_fft=N_FFT, hop_length=HOP)) ** 2
    mean_power = spec.mean(axis=1)  # 全フレーム平均、voiced ゲートなし
    excesses = []
    for g in GRID_BINS:
        peak = mean_power[g - 1 : g + 2].max()
        neighbors = np.concatenate(
            [mean_power[g - 8 : g - 3], mean_power[g + 4 : g + 9]]
        )
        excesses.append(
            10.0 * np.log10((peak + 1e-15) / (np.median(neighbors) + 1e-15))
        )
    comb_excess_db = float(np.mean(excesses))

    # --- >4kHz 残差 autocorr (comb_check.py L33-38) ---
    n = len(hp)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    freq = np.fft.rfft(hp, nfft)
    ac = np.fft.irfft(freq * np.conj(freq))[:601]
    # 縮退 (全ゼロ入力) の nan 化のみ回避 — 非縮退入力では canonical と同一
    ac = ac / ac[0] if ac[0] > 0 else np.zeros_like(ac)
    abs_tail = np.abs(ac[16:513])
    argmax_lag = int(np.argmax(abs_tail)) + 16

    return {
        "comb_excess_db": comb_excess_db,
        "hf_autocorr_lag128": float(abs(ac[AUTOCORR_LAGS[0]])),
        "hf_autocorr_lag256": float(abs(ac[AUTOCORR_LAGS[1]])),
        "hf_autocorr_max_lag16_512": float(abs_tail.max()),
        "hf_autocorr_argmax_lag": argmax_lag,
    }


def score_file(path: Path) -> dict | None:
    """wav を 22.05kHz mono で読み込み comb_metrics を返す。"""
    import librosa

    wav, _ = librosa.load(str(path), sr=SR_ANALYSIS, mono=True)
    return comb_metrics(np.asarray(wav), SR_ANALYSIS)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--clips-dir", help="wav ディレクトリを一括採点")
    src.add_argument("--wav", help="単一 wav を採点")
    ap.add_argument(
        "--output",
        help="tsv 出力先 (path\\tcomb_excess_db\\thf_autocorr_lag128\\thf_autocorr_lag256)",
    )
    ap.add_argument("--json-out", help="per-file dict の JSON 出力先")
    args = ap.parse_args()

    paths = [Path(args.wav)] if args.wav else sorted(Path(args.clips_dir).glob("*.wav"))
    rows: list[tuple[str, dict | None]] = []
    for p in paths:
        m = score_file(p)
        rows.append((p.name, m))
        if m is None:
            _LOGGER.info("%s: n/a (too short)", p.name)
        else:
            _LOGGER.info(
                "%s: comb_excess=%.3f dB  ac@128=%.4f  ac@256=%.4f",
                p.name,
                m["comb_excess_db"],
                m["hf_autocorr_lag128"],
                m["hf_autocorr_lag256"],
            )

    if args.wav:
        m = rows[0][1]
        if m is None:
            print(f"{args.wav}\tn/a")
        else:
            print(
                f"{args.wav}\t{m['comb_excess_db']:.3f}"
                f"\t{m['hf_autocorr_lag128']:.4f}\t{m['hf_autocorr_lag256']:.4f}"
            )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("path\tcomb_excess_db\thf_autocorr_lag128\thf_autocorr_lag256\n")
            for name, m in rows:
                if m is None:
                    f.write(f"{name}\t\t\t\n")
                else:
                    f.write(
                        f"{name}\t{round(m['comb_excess_db'], 3)}"
                        f"\t{round(m['hf_autocorr_lag128'], 4)}"
                        f"\t{round(m['hf_autocorr_lag256'], 4)}\n"
                    )
        _LOGGER.info("wrote %s (%d rows)", args.output, len(rows))
    if args.json_out:
        import json

        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(dict(rows), f, ensure_ascii=False, indent=2)
        _LOGGER.info("wrote %s", args.json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
