"""High-band energy deviation of generated audio from real audio of the same voice.

The audible roughness of v10b lives above 2.8 kHz (plan
docs/design/zero-shot-speaker-identity-plan-2026-10-29.md §7.9). Of the
metrics checked there, only "the share of the total energy in each band above
2.8 kHz, compared with real recordings of the same voice" agreed with every
listening judgement; comb-HNR moved the other way.

For each voice: Welch spectrum (nperseg 1024) of every file, the share of the
total power in each 500 Hz band from 2750 Hz to 10250 Hz in dB, averaged over
the files in dB; the test mean minus the real mean gives one value per band.

    abs_mean_db     mean |difference| over the bands (the P2-d / P1 metric:
                    a muffled sound that lacks high band energy also scores badly)
    signed_mean_db  mean difference (> 0: more high-band energy than real)

Evaluation only — never use it as a training loss (zs-eval-contract §2).

Usage::

    python -m piper_train.tools.measure_highband_deviation \\
        --test <dir>/<voice>/*.wav --real <dir>/<voice>/*.wav [--out report.json]
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np


LOW_EDGE_HZ = 2750
# Above this the resampler that made the training data (soxr HQ, 44.1 kHz ->
# 22.05 kHz) rolls off: a 22.05 -> 44.1 -> 22.05 kHz round trip measured -5 dB
# at 10.25-10.75 kHz and -62 dB at 10.75-11.03 kHz. Real recordings carry no
# reference energy there, so those bands are left out.
HIGH_EDGE_HZ = 10250
BAND_HZ = 500


def high_band_edges(sample_rate: int) -> list[int]:
    top = min(HIGH_EDGE_HZ, int(sample_rate / 2))
    return list(range(LOW_EDGE_HZ, top + 1, BAND_HZ))


def band_shares_db(wav: np.ndarray, sample_rate: int) -> np.ndarray:
    """dB share of the total power in each high band of ``high_band_edges``."""
    from scipy.signal import welch  # noqa: PLC0415

    f, p = welch(np.asarray(wav, dtype=np.float64), sample_rate, nperseg=1024)
    total = p.sum()
    edges = high_band_edges(sample_rate)
    shares = []
    for lo, hi in itertools.pairwise(edges):
        shares.append(p[(f >= lo) & (f < hi)].sum() / total)
    return 10 * np.log10(np.maximum(np.asarray(shares), 1e-20))


def voice_deviation(test_wavs, real_wavs, sample_rate: int) -> dict:
    test = np.mean([band_shares_db(w, sample_rate) for w in test_wavs], axis=0)
    real = np.mean([band_shares_db(w, sample_rate) for w in real_wavs], axis=0)
    diff = test - real
    return {
        "abs_mean_db": float(np.abs(diff).mean()),
        "signed_mean_db": float(diff.mean()),
        "per_band_db": [float(v) for v in diff],
        "n_test": len(test_wavs),
        "n_real": len(real_wavs),
    }


def _load_dir(directory: Path, sample_rate: int | None = None):
    """Mono float32 wavs of ``directory``; resampled to ``sample_rate`` if given.

    Real recordings come straight from the corpus (e.g. 44.1 kHz) while the
    model writes 22.05 kHz; comparing them unresampled maps the bands wrongly.
    """
    import soundfile as sf  # noqa: PLC0415
    import soxr  # noqa: PLC0415

    wavs, rates = [], set()
    for path in sorted(directory.glob("*.wav")):
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        data = data.mean(axis=1)
        if sample_rate is not None and sr != sample_rate:
            data = soxr.resample(data, sr, sample_rate, quality="HQ")
            sr = sample_rate
        wavs.append(data)
        rates.add(sr)
    if len(rates) != 1:
        raise ValueError(f"{directory}: expected one sample rate, got {sorted(rates)}")
    return wavs, rates.pop()


def directory_report(test_root: Path, real_root: Path) -> dict:
    groups = sorted(
        d.name
        for d in Path(test_root).iterdir()
        if d.is_dir() and (Path(real_root) / d.name).is_dir()
    )
    if not groups:
        raise ValueError("no voice directory present under both roots")
    per_group = {}
    sample_rate = None
    for group in groups:
        test, sr_t = _load_dir(Path(test_root) / group)
        real, _ = _load_dir(Path(real_root) / group, sample_rate=sr_t)
        sample_rate = sr_t
        per_group[group] = voice_deviation(test, real, sr_t)
    return {
        "abs_mean_db": float(np.mean([g["abs_mean_db"] for g in per_group.values()])),
        "signed_mean_db": float(
            np.mean([g["signed_mean_db"] for g in per_group.values()])
        ),
        "band_edges_hz": high_band_edges(sample_rate),
        "groups": per_group,
        "method": "welch nperseg=1024; dB share of total power per 500 Hz band "
        "from 2750 to 10250 Hz, test mean minus real mean of the same voice "
        "(real resampled to the test rate with soxr HQ)",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--real", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = directory_report(args.test, args.real)
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    for group, r in report["groups"].items():
        print(
            f"{group:16s} abs {r['abs_mean_db']:5.2f} dB  signed {r['signed_mean_db']:+5.2f} dB"
        )
    print(
        f"{'mean':16s} abs {report['abs_mean_db']:5.2f} dB  signed {report['signed_mean_db']:+5.2f} dB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
