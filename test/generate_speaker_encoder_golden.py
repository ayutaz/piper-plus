#!/usr/bin/env python3
"""Generate golden test data for cross-runtime Speaker Encoder validation.

Produces deterministic mel spectrogram data from known input signals (sine
waves) so that Rust, C#, and Go implementations can compare their output
against a shared baseline.

The reference implementation uses the **manual DFT** algorithm shared by
Rust/C#/Go with **float32 arithmetic** (via numpy), so that the golden
values are directly comparable across all runtimes.

Usage:
    uv run python test/generate_speaker_encoder_golden.py
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np


# Mel parameters -- must match all runtimes
SR = 16000
N_FFT = 512
HOP_LENGTH = 160
N_MELS = 80
FMIN = 20.0
FMAX = 7600.0

OUTPUT_PATH = Path(__file__).parent / "fixtures" / "speaker_encoder_golden.json"

# Type alias for float32
F32 = np.float32


# ---------------------------------------------------------------------------
# Reference implementation (manual DFT in float32, matching Rust/C#/Go)
# ---------------------------------------------------------------------------


def hz_to_mel(hz: F32) -> F32:
    return F32(2595.0) * np.log10(F32(1.0) + hz / F32(700.0))


def mel_to_hz(mel: F32) -> F32:
    return F32(700.0) * (np.float32(10.0) ** (mel / F32(2595.0)) - F32(1.0))


def hann_window(length: int) -> np.ndarray:
    """Hann window in float32."""
    n = np.arange(length, dtype=F32)
    return F32(0.5) * (F32(1.0) - np.cos(F32(2.0) * F32(np.pi) * n / F32(length)))


def create_mel_filterbank() -> np.ndarray:
    """Create mel filterbank (Rust/C#/Go algorithm -- floor + widening + center=1.0).

    Uses float32 for bin point computation, then integer indices for the
    triangle slopes (matching the integer division in Rust/C#/Go).
    """
    fft_bins = N_FFT // 2 + 1
    filterbank = np.zeros(N_MELS * fft_bins, dtype=F32)

    mel_fmin = hz_to_mel(F32(FMIN))
    mel_fmax = hz_to_mel(F32(FMAX))

    mel_points = np.array(
        [
            mel_fmin + (mel_fmax - mel_fmin) * F32(i) / F32(N_MELS + 1)
            for i in range(N_MELS + 2)
        ],
        dtype=F32,
    )
    hz_points = np.array([mel_to_hz(m) for m in mel_points], dtype=F32)
    bin_points_f = hz_points * F32(N_FFT) / F32(SR)

    for m in range(N_MELS):
        left = int(np.floor(bin_points_f[m]))
        center = int(np.floor(bin_points_f[m + 1]))
        right = int(np.floor(bin_points_f[m + 2]))

        # Edge case: widen collapsed triangles
        if left == center and center == right:
            center = min(center + 1, fft_bins - 1)
            right = min(right + 2, fft_bins - 1)
        elif left == center:
            center = min(center + 1, fft_bins - 1)
        if center == right:
            right = min(right + 1, fft_bins - 1)

        # Rising slope (integer division like Rust/C#/Go)
        for k in range(left, center):
            if center > left:
                filterbank[m * fft_bins + k] = F32(k - left) / F32(center - left)

        # Falling slope
        for k in range(center, right):
            if right > center:
                filterbank[m * fft_bins + k] = F32(right - k) / F32(right - center)

        # Ensure center bin always has weight >= 1.0
        if center < fft_bins:
            filterbank[m * fft_bins + center] = max(
                float(filterbank[m * fft_bins + center]), 1.0
            )

    return filterbank


def compute_mel_spectrogram(samples: np.ndarray) -> np.ndarray:
    """Compute log mel spectrogram using manual DFT in float32."""
    samples = np.asarray(samples, dtype=F32)
    mel_filters = create_mel_filterbank()
    window = hann_window(N_FFT)

    n_frames = 0
    if len(samples) >= N_FFT:
        n_frames = (len(samples) - N_FFT) // HOP_LENGTH + 1

    fft_bins = N_FFT // 2 + 1
    mel_spec = np.zeros(N_MELS * n_frames, dtype=F32)

    for frame_idx in range(n_frames):
        start = frame_idx * HOP_LENGTH

        # Power spectrum via DFT in float32
        power_spec = np.zeros(fft_bins, dtype=F32)
        for k in range(fft_bins):
            real = F32(0.0)
            imag = F32(0.0)
            freq = F32(-2.0) * F32(np.pi) * F32(k) / F32(N_FFT)
            for n in range(N_FFT):
                sample = F32(0.0)
                if start + n < len(samples):
                    sample = samples[start + n] * window[n]
                angle = freq * F32(n)
                real += sample * np.cos(angle)
                imag += sample * np.sin(angle)
            power_spec[k] = real * real + imag * imag

        # Apply mel filterbank
        for mel_idx in range(N_MELS):
            energy = F32(0.0)
            for k_idx in range(fft_bins):
                energy += mel_filters[mel_idx * fft_bins + k_idx] * power_spec[k_idx]
            mel_spec[mel_idx * n_frames + frame_idx] = np.log(max(float(energy), 1e-10))

    return mel_spec


def resample_linear(samples: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """Linear interpolation resampling in float32."""
    samples = np.asarray(samples, dtype=F32)
    if from_rate == to_rate or len(samples) == 0:
        return samples.copy()

    ratio = float(from_rate) / float(to_rate)
    output_len = math.ceil(len(samples) / ratio)
    output = np.zeros(output_len, dtype=F32)

    for i in range(output_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = F32(src_pos - idx)

        if idx + 1 < len(samples):
            output[i] = samples[idx] * (F32(1.0) - frac) + samples[idx + 1] * frac
        elif idx < len(samples):
            output[i] = samples[idx]

    return output


# ---------------------------------------------------------------------------
# Deterministic test signal generators
# ---------------------------------------------------------------------------


def generate_sine(freq_hz: float, duration_s: float, sr: int) -> np.ndarray:
    """Generate a deterministic sine wave in float32."""
    n_samples = int(duration_s * sr)
    i = np.arange(n_samples, dtype=F32)
    return np.sin(F32(2.0) * F32(np.pi) * F32(freq_hz) * i / F32(sr))


def generate_multitone(freqs: list[float], duration_s: float, sr: int) -> np.ndarray:
    """Generate a sum-of-sines signal in float32."""
    n_samples = int(duration_s * sr)
    samples = np.zeros(n_samples, dtype=F32)
    i = np.arange(n_samples, dtype=F32)
    for f in freqs:
        samples += np.sin(F32(2.0) * F32(np.pi) * F32(f) * i / F32(sr))
    peak = np.abs(samples).max()
    if peak > 0:
        samples = samples / peak
    return samples


def checksum_floats(values, precision: int = 6) -> str:
    """SHA-256 checksum of float values rounded to given precision."""
    vals = [round(float(v), precision) for v in values]
    data = json.dumps(vals, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def to_list(arr) -> list:
    """Convert numpy array to plain Python list of floats."""
    if hasattr(arr, "tolist"):
        return arr.tolist()
    return [float(x) for x in arr]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    test_cases = []

    # --- Case 1: 440Hz sine, 1s, 16kHz ---
    audio_440 = generate_sine(440.0, 1.0, SR)
    mel_440 = compute_mel_spectrogram(audio_440)
    n_frames_440 = len(mel_440) // N_MELS

    mel_440_sampled = mel_440[::10]
    test_cases.append(
        {
            "id": "sine_440hz_1s",
            "description": "440Hz sine wave, 1 second, 16kHz",
            "audio_params": {"freq_hz": 440.0, "duration_s": 1.0, "sr": SR},
            "audio_samples_count": len(audio_440),
            "expected_mel_shape": [N_MELS, n_frames_440],
            "expected_mel_checksum": checksum_floats(mel_440),
            "mel_sampled_every_10": to_list(mel_440_sampled),
            "mel_corner_values": {
                "top_left": float(mel_440[0]),
                "top_right": float(mel_440[n_frames_440 - 1]),
                "bottom_left": float(mel_440[(N_MELS - 1) * n_frames_440]),
                "bottom_right": float(mel_440[N_MELS * n_frames_440 - 1]),
            },
            "notes": "deterministic input for cross-runtime comparison",
        }
    )

    # --- Case 2: 1000Hz sine, 0.5s, 16kHz ---
    audio_1k = generate_sine(1000.0, 0.5, SR)
    mel_1k = compute_mel_spectrogram(audio_1k)
    n_frames_1k = len(mel_1k) // N_MELS

    mel_1k_sampled = mel_1k[::10]
    test_cases.append(
        {
            "id": "sine_1000hz_0.5s",
            "description": "1000Hz sine wave, 0.5 seconds, 16kHz",
            "audio_params": {"freq_hz": 1000.0, "duration_s": 0.5, "sr": SR},
            "audio_samples_count": len(audio_1k),
            "expected_mel_shape": [N_MELS, n_frames_1k],
            "expected_mel_checksum": checksum_floats(mel_1k),
            "mel_sampled_every_10": to_list(mel_1k_sampled),
            "mel_corner_values": {
                "top_left": float(mel_1k[0]),
                "top_right": float(mel_1k[n_frames_1k - 1]),
                "bottom_left": float(mel_1k[(N_MELS - 1) * n_frames_1k]),
                "bottom_right": float(mel_1k[N_MELS * n_frames_1k - 1]),
            },
            "notes": "mid-frequency test",
        }
    )

    # --- Case 3: multitone (200+600+2000 Hz), 0.5s ---
    audio_multi = generate_multitone([200.0, 600.0, 2000.0], 0.5, SR)
    mel_multi = compute_mel_spectrogram(audio_multi)
    n_frames_multi = len(mel_multi) // N_MELS

    mel_multi_sampled = mel_multi[::10]
    test_cases.append(
        {
            "id": "multitone_200_600_2000hz_0.5s",
            "description": "Multitone (200+600+2000 Hz), 0.5 seconds, 16kHz",
            "audio_params": {
                "freqs_hz": [200.0, 600.0, 2000.0],
                "duration_s": 0.5,
                "sr": SR,
            },
            "audio_samples_count": len(audio_multi),
            "expected_mel_shape": [N_MELS, n_frames_multi],
            "expected_mel_checksum": checksum_floats(mel_multi),
            "mel_sampled_every_10": to_list(mel_multi_sampled),
            "mel_corner_values": {
                "top_left": float(mel_multi[0]),
                "top_right": float(mel_multi[n_frames_multi - 1]),
                "bottom_left": float(mel_multi[(N_MELS - 1) * n_frames_multi]),
                "bottom_right": float(mel_multi[N_MELS * n_frames_multi - 1]),
            },
            "notes": "multi-frequency content exercises more mel bins",
        }
    )

    # --- Case 4: resample test (48kHz -> 16kHz) ---
    audio_48k = generate_sine(440.0, 0.1, 48000)
    resampled = resample_linear(audio_48k, 48000, 16000)

    test_cases.append(
        {
            "id": "resample_48k_to_16k",
            "description": "Resample 440Hz sine from 48kHz to 16kHz",
            "audio_params": {
                "freq_hz": 440.0,
                "duration_s": 0.1,
                "original_sr": 48000,
                "target_sr": 16000,
            },
            "input_samples_count": len(audio_48k),
            "expected_output_count": len(resampled),
            "output_checksum": checksum_floats(resampled),
            "output_first_10": to_list(resampled[:10]),
            "output_last_10": to_list(resampled[-10:]),
            "notes": "linear interpolation resampling test",
        }
    )

    # --- Hann window reference ---
    window = hann_window(N_FFT)

    # --- Mel filterbank reference ---
    fb = create_mel_filterbank()
    fft_bins = N_FFT // 2 + 1
    fb_band_sums = []
    for m in range(N_MELS):
        band_sum = float(np.sum(fb[m * fft_bins : (m + 1) * fft_bins]))
        fb_band_sums.append(band_sum)

    golden = {
        "description": "Speaker Encoder cross-runtime golden test data",
        "generator": "test/generate_speaker_encoder_golden.py",
        "mel_params": {
            "sr": SR,
            "n_fft": N_FFT,
            "hop_length": HOP_LENGTH,
            "n_mels": N_MELS,
            "fmin": FMIN,
            "fmax": FMAX,
        },
        "hann_window": {
            "length": N_FFT,
            "first_5": to_list(window[:5]),
            "last_5": to_list(window[-5:]),
            "mid_value": float(window[N_FFT // 2]),
            "checksum": checksum_floats(window),
        },
        "mel_filterbank": {
            "shape": [N_MELS, fft_bins],
            "band_sums": fb_band_sums,
            "total_sum": float(np.sum(fb)),
            "checksum": checksum_floats(fb),
        },
        "test_cases": test_cases,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(golden, f, indent=2, ensure_ascii=False)

    print(f"Golden data written to {OUTPUT_PATH}")
    print(f"  Test cases: {len(test_cases)}")
    print(f"  Hann window checksum: {golden['hann_window']['checksum']}")
    print(f"  Filterbank checksum: {golden['mel_filterbank']['checksum']}")
    for tc in test_cases:
        if "expected_mel_checksum" in tc:
            print(f"  {tc['id']}: mel checksum = {tc['expected_mel_checksum']}")
        elif "output_checksum" in tc:
            print(f"  {tc['id']}: output checksum = {tc['output_checksum']}")


if __name__ == "__main__":
    main()
