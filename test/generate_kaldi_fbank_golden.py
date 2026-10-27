#!/usr/bin/env python3
"""Generate golden data for the runtimes' zero-shot speaker front end.

The public zs-v1 base is conditioned on CAM++ embeddings computed as
resample to 16 kHz -> torchaudio Kaldi fbank -> mean subtraction -> CAM++ ->
L2 normalization (scripts/public_base_runtime.py, the Hugging Face Space's
zero_shot.py). The ports in src/wasm/openjtalk-web/src/kaldi-fbank.js,
src/rust/piper-core/src/kaldi_fbank.rs, src/go/piperplus/kaldi_fbank.go and
src/csharp/PiperPlus.Core/Inference/KaldiFbank.cs are checked against this
fixture.

Resampling uses torchaudio's Kaiser-windowed sinc with the "kaiser_best"
parameters, as the Space does (soxr, used by the CI recipe, is LGPL).

The input signals are closed-form sums of sines, rebuilt by each runtime's
test (`testSignal()` in test/js/test-kaldi-fbank-golden.js), so the fixture
stores only outputs.

Usage:
    uv run --no-project --python 3.13 \\
        --extra-index-url https://download.pytorch.org/whl/cpu \\
        --index-strategy unsafe-best-match \\
        --with torch==2.11.0 --with torchaudio==2.11.0 --with numpy \\
        python test/generate_kaldi_fbank_golden.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import torch
import torchaudio


OUTPUT = Path(__file__).parent / "fixtures" / "kaldi_fbank_golden.json"

KAISER_BEST = {
    "lowpass_filter_width": 64,
    "rolloff": 0.9475937167399596,
    "resampling_method": "sinc_interp_kaiser",
    "beta": 14.769656459379492,
}
FBANK = {
    "sample_frequency": 16000,
    "num_mel_bins": 80,
    "frame_length": 25,
    "frame_shift": 10,
    "dither": 0.0,
}
# (amplitude, frequency Hz, phase) — the last partial sits above 8 kHz so the
# resampler's low-pass filter is exercised.
PARTIALS = [(0.5, 440.0, 0.0), (0.3, 3000.0, 0.5), (0.1, 9500.0, 1.0)]
DC_OFFSET = 0.05


def test_signal(sample_rate: int, seconds: float) -> np.ndarray:
    n = np.arange(round(sample_rate * seconds), dtype=np.float64)
    x = np.full_like(n, DC_OFFSET)
    for amplitude, freq, phase in PARTIALS:
        if freq < sample_rate / 2:
            x += amplitude * np.sin(2 * math.pi * freq * n / sample_rate + phase)
    return x.astype(np.float32)


def resample(x: np.ndarray, rate: int) -> np.ndarray:
    return torchaudio.functional.resample(
        torch.from_numpy(x), rate, 16000, **KAISER_BEST
    ).numpy()


def fbank(x: np.ndarray) -> np.ndarray:
    return torchaudio.compliance.kaldi.fbank(
        torch.from_numpy(x).unsqueeze(0), **FBANK
    ).numpy()


def floats(a: np.ndarray) -> list[float]:
    return [float(v) for v in a.reshape(-1)]


def main() -> None:
    resample_cases = []
    for rate in (48000, 44100, 22050):
        out = resample(test_signal(rate, 0.1), rate)
        resample_cases.append(
            {"input_rate": rate, "seconds": 0.1, "output": floats(out)}
        )

    signal_16k = test_signal(16000, 0.25)
    feats = fbank(signal_16k)
    pipeline_feats = fbank(resample(test_signal(48000, 0.1), 48000))

    fixture = {
        "description": "Kaldi fbank + kaiser_best resample golden data (zs-v1 speaker front end)",
        "generator": "test/generate_kaldi_fbank_golden.py",
        "torch": torch.__version__,
        "torchaudio": torchaudio.__version__,
        "signal": {"dc_offset": DC_OFFSET, "partials": PARTIALS},
        "resample_params": KAISER_BEST,
        "fbank_params": FBANK,
        "resample_cases": resample_cases,
        "fbank_case": {
            "input_rate": 16000,
            "seconds": 0.25,
            "frames": int(feats.shape[0]),
            "values": floats(feats),
        },
        "pipeline_case": {
            "input_rate": 48000,
            "seconds": 0.1,
            "frames": int(pipeline_feats.shape[0]),
            "values": floats(pipeline_feats),
        },
    }
    OUTPUT.write_text(
        json.dumps(fixture, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
