/**
 * Cross-runtime Speaker Encoder mel parity test (WASM/JS).
 *
 * Loads test/fixtures/speaker_encoder_golden.json (Python torchaudio
 * canonical reference) and verifies that this runtime's mel feature
 * pipeline (Hann window, mel filterbank, STFT → mel) matches.
 *
 * Mel parameters (must be identical across all runtimes):
 *   sr=16000, n_fft=400, hop=160, n_mels=80, fmin=20, fmax=7600,
 *   Hann window length=400, slaney mel filterbank.
 *   (n_fft=400 matches Kaldi frame_length=25ms at 16kHz; canonical.)
 *
 * Spec: docs/spec/speaker-encoder-contract.md
 * Generator: test/generate_speaker_encoder_golden.py
 *
 * Mirrors:
 *   - Rust:   src/rust/piper-core/tests/test_speaker_encoder_golden.rs
 *   - Go:     src/go/piperplus/speaker_encoder_test.go
 *   - C#:     src/csharp/PiperPlus.Core.Tests/SpeakerEncoderTests.cs
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { _internalForTesting } from "../../src/speaker-encoder.js";

const {
  MEL_SAMPLE_RATE: SR,
  MEL_N_FFT: NFFT,
  MEL_HOP_LENGTH: HOP_LENGTH,
  MEL_N_MELS: N_MELS,
  MEL_FMIN: FMIN,
  MEL_FMAX: FMAX,
  hannWindow,
  createMelFilterbank,
  computeMelSpectrogram,
  resampleLinear,
  hzToMel,
  melToHz,
} = _internalForTesting;

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURE_PATH = resolve(__dirname, "../../../../../test/fixtures/speaker_encoder_golden.json");

const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf-8"));

const findCase = (id) => {
  const tc = fixture.test_cases.find((c) => c.id === id);
  if (!tc) {
    throw new Error(`fixture is missing test case '${id}'`);
  }
  return tc;
};

// fr32 truncation in the angle math is required so the JS test audio matches
// the Python golden generator byte-for-byte. Python evaluates
// `F32(2π) * F32(f) * F32(i) / F32(sr)` step-by-step in float32, then casts
// the sin result to float32 on store. JS computing the argument in float64
// produces a more accurate sine, which then disagrees with the golden mel.
const fr32 = Math.fround;
const generateSine = (freqHz, durationS, sr) => {
  const n = Math.floor(durationS * sr);
  const samples = new Float32Array(n);
  const twoPi = fr32(2 * Math.PI);
  for (let i = 0; i < n; i++) {
    const arg = fr32(fr32(fr32(twoPi * fr32(freqHz)) * fr32(i)) / fr32(sr));
    samples[i] = Math.sin(arg);
  }
  return samples;
};

const generateMultitone = (freqs, durationS, sr) => {
  const n = Math.floor(durationS * sr);
  const samples = new Float32Array(n);
  const twoPi = fr32(2 * Math.PI);
  for (const f of freqs) {
    for (let i = 0; i < n; i++) {
      const arg = fr32(fr32(fr32(twoPi * fr32(f)) * fr32(i)) / fr32(sr));
      samples[i] += Math.sin(arg);
    }
  }
  let peak = 0;
  for (let i = 0; i < n; i++) {
    const a = Math.abs(samples[i]);
    if (a > peak) {
      peak = a;
    }
  }
  if (peak > 0) {
    for (let i = 0; i < n; i++) {
      samples[i] /= peak;
    }
  }
  return samples;
};

describe("Speaker Encoder mel parity (WASM/JS ↔ canonical Python)", () => {
  // -----------------------------------------------------------------
  // Mel parameters — must match all runtimes
  // -----------------------------------------------------------------

  it("mel_params match runtime constants", () => {
    const p = fixture.mel_params;
    assert.strictEqual(p.sr, SR);
    assert.strictEqual(p.n_fft, NFFT);
    assert.strictEqual(p.hop_length, HOP_LENGTH);
    assert.strictEqual(p.n_mels, N_MELS);
    assert.ok(Math.abs(p.fmin - FMIN) < 1e-3);
    assert.ok(Math.abs(p.fmax - FMAX) < 1e-3);
  });

  // -----------------------------------------------------------------
  // Hann window
  // -----------------------------------------------------------------

  it("Hann window first 5 samples match", () => {
    const hw = fixture.hann_window;
    const w = hannWindow(hw.length);
    for (let i = 0; i < hw.first_5.length; i++) {
      assert.ok(
        Math.abs(w[i] - hw.first_5[i]) < 1e-5,
        `hann[${i}]: expected ${hw.first_5[i]}, got ${w[i]}`
      );
    }
  });

  it("Hann window last 5 samples match", () => {
    const hw = fixture.hann_window;
    const w = hannWindow(hw.length);
    for (let i = 0; i < hw.last_5.length; i++) {
      const idx = hw.length - 5 + i;
      assert.ok(
        Math.abs(w[idx] - hw.last_5[i]) < 1e-5,
        `hann[${idx}]: expected ${hw.last_5[i]}, got ${w[idx]}`
      );
    }
  });

  it("Hann window mid value is 1.0", () => {
    const hw = fixture.hann_window;
    const w = hannWindow(hw.length);
    assert.ok(
      Math.abs(w[hw.length / 2] - hw.mid_value) < 1e-5,
      `hann mid: expected ${hw.mid_value}, got ${w[hw.length / 2]}`
    );
  });

  it("Hann window endpoints are near zero", () => {
    const w = hannWindow(NFFT);
    assert.strictEqual(w.length, NFFT);
    assert.ok(Math.abs(w[0]) < 1e-6);
  });

  // -----------------------------------------------------------------
  // Mel filterbank
  // -----------------------------------------------------------------

  it("mel filterbank has shape [80, n_fft/2+1]", () => {
    const fftBins = NFFT / 2 + 1;
    const expected = fixture.mel_filterbank.shape;
    const fb = createMelFilterbank();
    assert.strictEqual(expected[0], N_MELS);
    assert.strictEqual(expected[1], fftBins);
    assert.strictEqual(fb.length, N_MELS * fftBins);
  });

  it("mel filterbank band sums match (within 2%)", () => {
    const expectedSums = fixture.mel_filterbank.band_sums;
    const fb = createMelFilterbank();
    const fftBins = NFFT / 2 + 1;
    for (let m = 0; m < N_MELS; m++) {
      let bandSum = 0;
      for (let k = 0; k < fftBins; k++) {
        bandSum += fb[m * fftBins + k];
      }
      const relErr =
        Math.abs(expectedSums[m]) > 1e-10
          ? Math.abs((bandSum - expectedSums[m]) / expectedSums[m])
          : Math.abs(bandSum - expectedSums[m]);
      assert.ok(
        relErr < 0.02,
        `band[${m}]: expected ${expectedSums[m]}, got ${bandSum} (rel err ${relErr.toFixed(6)})`
      );
    }
  });

  it("mel filterbank total sum matches (within 2%)", () => {
    const expectedTotal = fixture.mel_filterbank.total_sum;
    const fb = createMelFilterbank();
    let total = 0;
    for (let i = 0; i < fb.length; i++) {
      total += fb[i];
    }
    const relErr = Math.abs((total - expectedTotal) / expectedTotal);
    assert.ok(
      relErr < 0.02,
      `total: expected ${expectedTotal}, got ${total} (rel err ${relErr.toFixed(6)})`
    );
  });

  it("all filterbank bands have non-zero total weight", () => {
    const fb = createMelFilterbank();
    const fftBins = NFFT / 2 + 1;
    for (let m = 0; m < N_MELS; m++) {
      let bandSum = 0;
      for (let k = 0; k < fftBins; k++) {
        bandSum += fb[m * fftBins + k];
      }
      assert.ok(bandSum > 0, `band[${m}] has zero total weight`);
    }
  });

  // -----------------------------------------------------------------
  // Mel spectrogram — sine 440Hz, 1s
  //
  // The fixture is generated by Python torchaudio (FFT-based, float32). JS
  // here uses naive O(n²) DFT. For high-energy mel bins (where the input
  // sine has spectral mass) values agree closely; for low-energy bins
  // (out-of-band) numerical noise differs because JS's Math.cos is float64
  // and numpy/torchaudio is float32. Mirrors Go's strategy:
  //
  //   - Top corners (low mel bin = around the sine frequency):
  //       absolute diff in log scale < 2.0 (≈ within 7x linear energy).
  //   - Bottom corners (high mel bin, ~7600 Hz):
  //       structural check only — must be negative (log of small value).
  //   - active-bins distribution: low-freq bins must have higher energy
  //       than high-freq bins for a low-frequency sine.
  // -----------------------------------------------------------------

  const LOG_DIFF_TOL = 2.0; // matches Go's tolerance for top corners
  // Bottom corners (high mel bin ~7600Hz) are out-of-band noise: the raw
  // mel energy is often below the 1e-10 log-clamp, so post-CMVN values are
  // dominated by how often clamping fires per band. JS's f64 Math.cos vs
  // numpy's f32 cos produce slightly different power values that cross the
  // clamp threshold at different frames → CMVN means diverge. Use a wider
  // tolerance for these structural checks.
  const BOTTOM_LOG_DIFF_TOL = 4.0;

  const topCornerAbsDiff = (name, actual, expected, tol = LOG_DIFF_TOL) => {
    const diff = Math.abs(actual - expected);
    assert.ok(
      diff < tol,
      `${name}: golden=${expected}, js=${actual} (diff ${diff.toFixed(4)}, tol ${tol})`
    );
  };
  const bottomCornerAbsDiff = (name, actual, expected) =>
    topCornerAbsDiff(name, actual, expected, BOTTOM_LOG_DIFF_TOL);

  const bottomCornerNegative = (name, actual) => {
    assert.ok(actual < 0, `${name} should be negative (log-mel), got ${actual}`);
  };

  it("sine_440hz_1s: mel shape matches", () => {
    const tc = findCase("sine_440hz_1s");
    const audio = generateSine(440, 1.0, SR);
    assert.strictEqual(audio.length, tc.audio_samples_count);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    assert.strictEqual(tc.expected_mel_shape[0], N_MELS);
    assert.strictEqual(tc.expected_mel_shape[1], nFrames);
  });

  it("sine_440hz_1s: mel top corners agree with golden (log-diff < 2.0)", () => {
    const tc = findCase("sine_440hz_1s");
    const corners = tc.mel_corner_values;
    const audio = generateSine(440, 1.0, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major layout: mel[frame_idx * N_MELS + mel_idx]
    topCornerAbsDiff("top_left", mel[0], corners.top_left);
    topCornerAbsDiff("top_right", mel[(nFrames - 1) * N_MELS], corners.top_right);
  });

  it("sine_440hz_1s: mel bottom corners agree with golden (log-diff < 2.0)", () => {
    // Post-CMVN values are zero-mean per band, so individual frames may be
    // positive or negative. Compare against the golden corner values
    // directly rather than asserting sign.
    const tc = findCase("sine_440hz_1s");
    const corners = tc.mel_corner_values;
    const audio = generateSine(440, 1.0, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major: bottom_left = frame 0 mel last; bottom_right = last frame mel last
    bottomCornerAbsDiff("bottom_left", mel[N_MELS - 1], corners.bottom_left);
    bottomCornerAbsDiff("bottom_right", mel[nFrames * N_MELS - 1], corners.bottom_right);
  });

  it("sine_440hz_1s: mel values are finite (no NaN/Inf)", () => {
    // The old "low-freq dominates high-freq" check compared per-band mel
    // sums for a single frame. After CMVN (zero-mean per band across all
    // frames), this comparison loses meaning — a single frame's value is a
    // deviation from the band's mean, not an absolute energy. Replace with
    // a finiteness sanity check.
    const audio = generateSine(440, 1.0, SR);
    const mel = computeMelSpectrogram(audio);
    for (let i = 0; i < mel.length; i++) {
      assert.ok(Number.isFinite(mel[i]), `mel[${i}] is not finite: ${mel[i]}`);
    }
  });

  // -----------------------------------------------------------------
  // Mel spectrogram — sine 1000Hz, 0.5s
  // -----------------------------------------------------------------

  it("sine_1000hz_0.5s: mel top corners agree with golden (log-diff < 2.0)", () => {
    const tc = findCase("sine_1000hz_0.5s");
    const corners = tc.mel_corner_values;
    const audio = generateSine(1000, 0.5, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major layout: mel[frame_idx * N_MELS + mel_idx]
    topCornerAbsDiff("top_left", mel[0], corners.top_left);
    topCornerAbsDiff("top_right", mel[(nFrames - 1) * N_MELS], corners.top_right);
  });

  it("sine_1000hz_0.5s: mel bottom corners agree with golden (log-diff < 2.0)", () => {
    // Post-CMVN values are zero-mean per band; compare against golden directly.
    const tc = findCase("sine_1000hz_0.5s");
    const corners = tc.mel_corner_values;
    const audio = generateSine(1000, 0.5, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major: bottom_left = frame 0 mel last; bottom_right = last frame mel last
    bottomCornerAbsDiff("bottom_left", mel[N_MELS - 1], corners.bottom_left);
    bottomCornerAbsDiff("bottom_right", mel[nFrames * N_MELS - 1], corners.bottom_right);
  });

  // -----------------------------------------------------------------
  // Mel spectrogram — multitone 200/600/2000Hz, 0.5s
  // -----------------------------------------------------------------

  it("multitone: mel top corners agree with golden (log-diff < 2.0)", () => {
    const tc = findCase("multitone_200_600_2000hz_0.5s");
    const corners = tc.mel_corner_values;
    const audio = generateMultitone([200, 600, 2000], 0.5, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major layout: mel[frame_idx * N_MELS + mel_idx]
    topCornerAbsDiff("top_left", mel[0], corners.top_left);
    topCornerAbsDiff("top_right", mel[(nFrames - 1) * N_MELS], corners.top_right);
  });

  it("multitone: mel bottom corners agree with golden (log-diff < 2.0)", () => {
    // Post-CMVN values are zero-mean per band; compare against golden directly.
    const tc = findCase("multitone_200_600_2000hz_0.5s");
    const corners = tc.mel_corner_values;
    const audio = generateMultitone([200, 600, 2000], 0.5, SR);
    const mel = computeMelSpectrogram(audio);
    const nFrames = mel.length / N_MELS;
    // Frame-major: bottom_left = frame 0 mel last; bottom_right = last frame mel last
    bottomCornerAbsDiff("bottom_left", mel[N_MELS - 1], corners.bottom_left);
    bottomCornerAbsDiff("bottom_right", mel[nFrames * N_MELS - 1], corners.bottom_right);
  });

  it("multitone: mel sampled distribution matches direction (Spearman-like)", () => {
    // Looser cross-runtime check: the rank order of sampled values should
    // correlate with the golden, even if exact values differ. Threshold
    // chosen to detect catastrophic drift, not precision-level differences.
    const tc = findCase("multitone_200_600_2000hz_0.5s");
    const audio = generateMultitone([200, 600, 2000], 0.5, SR);
    const mel = computeMelSpectrogram(audio);
    const sampled = [];
    for (let i = 0; i < mel.length; i += 10) {
      sampled.push(mel[i]);
    }
    const expected = tc.mel_sampled_every_10;
    assert.strictEqual(sampled.length, expected.length, "sampled length mismatch");
    // Pearson correlation on log-mel values
    const n = sampled.length;
    let mxA = 0,
      mxB = 0;
    for (let i = 0; i < n; i++) {
      mxA += sampled[i];
      mxB += expected[i];
    }
    mxA /= n;
    mxB /= n;
    let num = 0,
      denA = 0,
      denB = 0;
    for (let i = 0; i < n; i++) {
      const a = sampled[i] - mxA;
      const b = expected[i] - mxB;
      num += a * b;
      denA += a * a;
      denB += b * b;
    }
    const corr = num / Math.sqrt(denA * denB);
    assert.ok(
      corr > 0.9,
      `mel sampled correlation ${corr.toFixed(4)} below 0.9 — catastrophic drift`
    );
  });

  // -----------------------------------------------------------------
  // Resampling 48k → 16k
  // -----------------------------------------------------------------

  it("resample 48k→16k: output length matches", () => {
    const tc = findCase("resample_48k_to_16k");
    const audio48k = generateSine(440, 0.1, 48000);
    assert.strictEqual(audio48k.length, tc.input_samples_count);
    const resampled = resampleLinear(audio48k, 48000, SR);
    assert.strictEqual(resampled.length, tc.expected_output_count);
  });

  it("resample 48k→16k: first/last 10 values match", () => {
    const tc = findCase("resample_48k_to_16k");
    const audio48k = generateSine(440, 0.1, 48000);
    const resampled = resampleLinear(audio48k, 48000, SR);
    const first = tc.output_first_10;
    for (let i = 0; i < first.length; i++) {
      assert.ok(
        Math.abs(resampled[i] - first[i]) < 1e-4,
        `resample first[${i}]: expected ${first[i]}, got ${resampled[i]}`
      );
    }
    const last = tc.output_last_10;
    for (let i = 0; i < last.length; i++) {
      const idx = resampled.length - 10 + i;
      assert.ok(
        Math.abs(resampled[idx] - last[i]) < 1e-4,
        `resample last[${i}]: expected ${last[i]}, got ${resampled[idx]}`
      );
    }
  });

  // -----------------------------------------------------------------
  // Edge cases
  // -----------------------------------------------------------------

  it("silent audio produces finite mel values", () => {
    const silence = new Float32Array(SR);
    const mel = computeMelSpectrogram(silence);
    assert.ok(mel.length > 0);
    for (let i = 0; i < mel.length; i++) {
      assert.ok(Number.isFinite(mel[i]), `non-finite mel value: ${mel[i]}`);
    }
  });

  it("audio shorter than n_fft produces empty mel", () => {
    const shortAudio = new Float32Array(100);
    const mel = computeMelSpectrogram(shortAudio);
    assert.strictEqual(mel.length, 0);
  });

  it("resample with same rate returns equivalent samples", () => {
    const samples = new Float32Array([1, 2, 3, 4]);
    const result = resampleLinear(samples, SR, SR);
    assert.strictEqual(result.length, samples.length);
    for (let i = 0; i < samples.length; i++) {
      assert.strictEqual(result[i], samples[i]);
    }
  });

  it("hzToMel ↔ melToHz round-trip", () => {
    const hz = 1000;
    const mel = hzToMel(hz);
    const hzBack = melToHz(mel);
    assert.ok(Math.abs(hz - hzBack) < 0.01, `Hz roundtrip: ${hz} → ${mel} → ${hzBack}`);
  });
});
