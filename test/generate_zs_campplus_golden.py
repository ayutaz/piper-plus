#!/usr/bin/env python3
"""Generate golden CAM++ embeddings for the runtimes' zero-shot speaker encoders.

Runs the zs-v1 embedding recipe of the Hugging Face Space
(huggingface-space/zero_shot.py: kaiser_best resample to 16 kHz -> Kaldi
fbank -> mean subtraction -> CAM++ -> L2 normalization) on the pinned
campplus.onnx. test/js/test-zs-campplus-parity.js runs the browser
SpeakerEncoder (frontEnd "kaldi-fbank") on the same model and inputs, and the
Rust (test_campplus_parity.rs), Go (campplus_parity_test.go) and C#
(CampplusParityTests.cs) SpeakerEncoders do the same.

The inputs are closed-form voiced tones, rebuilt by `voicedSignal()` in each
test, so the fixture stores only parameters and embeddings.

Usage (downloads the pinned model first):
    node src/wasm/openjtalk-web/test/browser/prepare-models.mjs
    uv run --no-project --python 3.13 \\
        --extra-index-url https://download.pytorch.org/whl/cpu \\
        --index-strategy unsafe-best-match \\
        --with torch==2.11.0 --with torchaudio==2.11.0 \\
        --with onnxruntime --with numpy \\
        python test/generate_zs_campplus_golden.py
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import onnxruntime
import torch
import torchaudio


REPO_ROOT = Path(__file__).resolve().parent.parent
BROWSER_DIR = REPO_ROOT / "src" / "wasm" / "openjtalk-web" / "test" / "browser"
OUTPUT = Path(__file__).parent / "fixtures" / "zs_campplus_golden.json"

ENCODER_SAMPLE_RATE = 16000
KAISER_BEST = {
    "lowpass_filter_width": 64,
    "rolloff": 0.9475937167399596,
    "resampling_method": "sinc_interp_kaiser",
    "beta": 14.769656459379492,
}

SYLLABLE_HZ = 3.0
AMPLITUDE = 0.3
MAX_HARMONICS = 20
# Fricative-like partials near and above the 16 kHz Nyquist, gated opposite
# to the voiced envelope; without them the resampler cutoff goes untested.
NOISE_PARTIALS = [
    (0.05, 5500.0),
    (0.04, 7000.0),
    (0.04, 7750.0),
    (0.03, 9500.0),
    (0.02, 14000.0),
]
CASES = [
    # name, sample_rate, seconds, f0, vibrato_hz, vibrato_depth_hz
    ("low_voice_16k", 16000, 2.0, 120.0, 5.0, 8.0),
    ("low_voice_22k", 22050, 2.0, 120.0, 5.0, 8.0),
    ("low_voice_48k", 48000, 2.0, 120.0, 5.0, 8.0),
    ("high_voice_44k", 44100, 2.0, 230.0, 6.0, 15.0),
]
# A weak white floor keeps every mel bin well above the log floor, as in real
# recordings; pure tones leave bins near it, where float32 (torchaudio) and
# float64 (JS) logs disagree by more than any real front-end difference.
NOISE_FLOOR = 0.01
NOISE_SEED = 2463534242
DISTINCT_PAIR = ["low_voice_22k", "high_voice_44k"]


def voiced_signal(rate: int, seconds: float, f0: float, vib_hz: float, depth: float):
    t = np.arange(round(rate * seconds), dtype=np.float64) / rate
    phase = 2 * math.pi * f0 * t - (depth / vib_hz) * np.cos(2 * math.pi * vib_hz * t)
    envelope = 0.5 * (1 - np.cos(2 * math.pi * SYLLABLE_HZ * t))
    x = np.zeros_like(t)
    k = 1
    while k * (f0 + depth) < rate / 2 and k <= MAX_HARMONICS:
        x += (AMPLITUDE / k) * np.sin(k * phase)
        k += 1
    noise = np.zeros_like(t)
    for amplitude, freq in NOISE_PARTIALS:
        if freq < rate / 2:
            noise += amplitude * np.sin(2 * math.pi * freq * t)
    floor = NOISE_FLOOR * white_noise(t.size)
    return (envelope * x + (1 - envelope) * noise + floor).astype(np.float32)


def white_noise(n: int) -> np.ndarray:
    """xorshift32 in [-0.5, 0.5), bit-identical to `whiteNoise()` in the JS test."""
    out = np.empty(n, dtype=np.float64)
    x = NOISE_SEED
    for i in range(n):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        out[i] = x / 2**32 - 0.5
    return out


def embed(
    session: onnxruntime.InferenceSession, audio: np.ndarray, rate: int
) -> np.ndarray:
    waveform = torch.from_numpy(audio)
    if rate != ENCODER_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(
            waveform, rate, ENCODER_SAMPLE_RATE, **KAISER_BEST
        )
    features = torchaudio.compliance.kaldi.fbank(
        waveform.unsqueeze(0),
        sample_frequency=ENCODER_SAMPLE_RATE,
        num_mel_bins=80,
        frame_length=25,
        frame_shift=10,
        dither=0.0,
    )
    features -= features.mean(dim=0, keepdim=True)
    name = session.get_inputs()[0].name
    embedding = session.run(None, {name: features.unsqueeze(0).numpy()})[0]
    embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
    return embedding / np.linalg.norm(embedding)


def main() -> None:
    manifest = json.loads((BROWSER_DIR / "zero-shot-models.json").read_text("utf-8"))
    pinned = next(f for f in manifest["files"] if f["local"] == "campplus.onnx")
    model = BROWSER_DIR / "models" / manifest["key"] / "campplus.onnx"
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != pinned["sha256"]:
        raise SystemExit(f"{model}: SHA-256 {digest} != pinned {pinned['sha256']}")
    # ONNX Runtime 1.24-1.28 graph optimizations (any level) change the CAM++
    # output (cosine 0.998-0.9998 against 1.29+); the runtimes disable them
    # for this model too.
    options = onnxruntime.SessionOptions()
    options.graph_optimization_level = (
        onnxruntime.GraphOptimizationLevel.ORT_DISABLE_ALL
    )
    session = onnxruntime.InferenceSession(
        str(model), options, providers=["CPUExecutionProvider"]
    )

    cases = []
    for name, rate, seconds, f0, vib_hz, depth in CASES:
        embedding = embed(
            session, voiced_signal(rate, seconds, f0, vib_hz, depth), rate
        )
        cases.append(
            {
                "name": name,
                "sample_rate": rate,
                "seconds": seconds,
                "f0": f0,
                "vibrato_hz": vib_hz,
                "vibrato_depth_hz": depth,
                "embedding": [round(float(v), 7) for v in embedding],
            }
        )

    fixture = {
        "description": "zs-v1 CAM++ embeddings from the Python recipe (huggingface-space/zero_shot.py)",
        "generator": "test/generate_zs_campplus_golden.py",
        "torch": torch.__version__,
        "torchaudio": torchaudio.__version__,
        "onnxruntime": onnxruntime.__version__,
        "campplus_sha256": digest,
        "syllable_hz": SYLLABLE_HZ,
        "amplitude": AMPLITUDE,
        "max_harmonics": MAX_HARMONICS,
        "noise_partials": NOISE_PARTIALS,
        "noise_floor": NOISE_FLOOR,
        "noise_seed": NOISE_SEED,
        "distinct_pair": DISTINCT_PAIR,
        "cases": cases,
    }
    OUTPUT.write_text(
        json.dumps(fixture, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
