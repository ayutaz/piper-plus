//! Cross-runtime golden tests for the Speaker Encoder mel spectrogram.
//!
//! Reads `test/fixtures/speaker_encoder_golden.json` and verifies that the
//! Rust implementation produces identical output to the reference (Python
//! manual DFT) for deterministic inputs (sine waves).
//!
//! Run: cargo test --test test_speaker_encoder_golden

use std::f32::consts::PI;
use std::path::PathBuf;

use serde::Deserialize;

// ---------------------------------------------------------------------------
// Re-export internal functions for testing.
//
// The speaker_encoder module keeps its helper functions private, so we
// duplicate the pure-computation parts here (identical algorithm) to test
// them against the golden data without making them `pub` in production.
// ---------------------------------------------------------------------------

const MEL_SAMPLE_RATE: u32 = 16000;
const MEL_N_FFT: usize = 512;
const MEL_HOP_LENGTH: usize = 160;
const MEL_N_MELS: usize = 80;
const MEL_FMIN: f32 = 20.0;
const MEL_FMAX: f32 = 7600.0;

fn hz_to_mel(hz: f32) -> f32 {
    2595.0 * (1.0 + hz / 700.0).log10()
}

fn mel_to_hz(mel: f32) -> f32 {
    700.0 * (10.0_f32.powf(mel / 2595.0) - 1.0)
}

fn hann_window(length: usize) -> Vec<f32> {
    (0..length)
        .map(|n| 0.5 * (1.0 - (2.0 * PI * n as f32 / length as f32).cos()))
        .collect()
}

fn create_mel_filterbank() -> Vec<f32> {
    let fft_bins = MEL_N_FFT / 2 + 1;
    let mut filterbank = vec![0.0f32; MEL_N_MELS * fft_bins];

    let mel_fmin = hz_to_mel(MEL_FMIN);
    let mel_fmax = hz_to_mel(MEL_FMAX);

    let mel_points: Vec<f32> = (0..=MEL_N_MELS + 1)
        .map(|i| mel_fmin + (mel_fmax - mel_fmin) * i as f32 / (MEL_N_MELS + 1) as f32)
        .collect();

    let hz_points: Vec<f32> = mel_points.iter().map(|&m| mel_to_hz(m)).collect();
    let bin_points: Vec<f32> = hz_points
        .iter()
        .map(|&hz| hz * MEL_N_FFT as f32 / MEL_SAMPLE_RATE as f32)
        .collect();

    for m in 0..MEL_N_MELS {
        let left = bin_points[m].floor() as usize;
        let mut center = bin_points[m + 1].floor() as usize;
        let mut right = bin_points[m + 2].floor() as usize;

        if left == center && center == right {
            center = (center + 1).min(fft_bins - 1);
            right = (right + 2).min(fft_bins - 1);
        } else if left == center {
            center = (center + 1).min(fft_bins - 1);
        }
        if center == right {
            right = (right + 1).min(fft_bins - 1);
        }

        for k in left..center {
            if center > left {
                filterbank[m * fft_bins + k] = (k - left) as f32 / (center - left) as f32;
            }
        }
        for k in center..right {
            if right > center {
                filterbank[m * fft_bins + k] = (right - k) as f32 / (right - center) as f32;
            }
        }
        if center < fft_bins {
            filterbank[m * fft_bins + center] = filterbank[m * fft_bins + center].max(1.0);
        }
    }

    filterbank
}

fn compute_mel_spectrogram(samples: &[f32]) -> Vec<f32> {
    let mel_filters = create_mel_filterbank();
    let window = hann_window(MEL_N_FFT);

    let n_frames = if samples.len() >= MEL_N_FFT {
        (samples.len() - MEL_N_FFT) / MEL_HOP_LENGTH + 1
    } else {
        0
    };

    let fft_bins = MEL_N_FFT / 2 + 1;
    let mut mel_spec = vec![0.0f32; MEL_N_MELS * n_frames];

    for frame_idx in 0..n_frames {
        let start = frame_idx * MEL_HOP_LENGTH;

        let mut power_spec = vec![0.0f32; fft_bins];
        for (k, ps) in power_spec.iter_mut().enumerate() {
            let mut real = 0.0f32;
            let mut imag = 0.0f32;
            let freq = -2.0 * PI * k as f32 / MEL_N_FFT as f32;
            for n in 0..MEL_N_FFT {
                let sample = if start + n < samples.len() {
                    samples[start + n] * window[n]
                } else {
                    0.0
                };
                let angle = freq * n as f32;
                real += sample * angle.cos();
                imag += sample * angle.sin();
            }
            *ps = real * real + imag * imag;
        }

        for mel_idx in 0..MEL_N_MELS {
            let mut energy = 0.0f32;
            for k in 0..fft_bins {
                energy += mel_filters[mel_idx * fft_bins + k] * power_spec[k];
            }
            mel_spec[mel_idx * n_frames + frame_idx] = energy.max(1e-10).ln();
        }
    }

    mel_spec
}

fn resample_linear(samples: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    if from_rate == to_rate || samples.is_empty() {
        return samples.to_vec();
    }

    let ratio = from_rate as f64 / to_rate as f64;
    let output_len = ((samples.len() as f64) / ratio).ceil() as usize;
    let mut output = Vec::with_capacity(output_len);

    for i in 0..output_len {
        let src_pos = i as f64 * ratio;
        let idx = src_pos as usize;
        let frac = (src_pos - idx as f64) as f32;

        let sample = if idx + 1 < samples.len() {
            samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        } else if idx < samples.len() {
            samples[idx]
        } else {
            0.0
        };
        output.push(sample);
    }

    output
}

// ---------------------------------------------------------------------------
// Golden file deserialization
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct GoldenData {
    mel_params: MelParams,
    hann_window: HannWindowGolden,
    mel_filterbank: FilterbankGolden,
    test_cases: Vec<TestCase>,
}

#[derive(Debug, Deserialize)]
struct MelParams {
    sr: u32,
    n_fft: usize,
    hop_length: usize,
    n_mels: usize,
    fmin: f32,
    fmax: f32,
}

#[derive(Debug, Deserialize)]
struct HannWindowGolden {
    length: usize,
    first_5: Vec<f64>,
    last_5: Vec<f64>,
    mid_value: f64,
    #[serde(rename = "checksum")]
    _checksum: String,
}

#[derive(Debug, Deserialize)]
struct FilterbankGolden {
    shape: Vec<usize>,
    band_sums: Vec<f64>,
    total_sum: f64,
    #[serde(rename = "checksum")]
    _checksum: String,
}

#[derive(Debug, Deserialize)]
struct TestCase {
    id: String,
    #[serde(default, rename = "audio_params")]
    _audio_params: serde_json::Value,
    #[serde(default)]
    audio_samples_count: usize,
    #[serde(default)]
    expected_mel_shape: Vec<usize>,
    #[serde(default)]
    #[serde(rename = "expected_mel_checksum")]
    _expected_mel_checksum: String,
    #[serde(default)]
    mel_corner_values: Option<CornerValues>,
    #[serde(default)]
    mel_sampled_every_10: Option<Vec<f64>>,
    #[serde(default)]
    input_samples_count: usize,
    #[serde(default)]
    expected_output_count: usize,
    #[serde(default)]
    output_first_10: Option<Vec<f64>>,
    #[serde(default)]
    output_last_10: Option<Vec<f64>>,
}

#[derive(Debug, Deserialize)]
struct CornerValues {
    top_left: f64,
    top_right: f64,
    bottom_left: f64,
    bottom_right: f64,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn fixture_path() -> PathBuf {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap() // piper-core -> src/rust
        .parent()
        .unwrap() // src/rust -> src
        .parent()
        .unwrap() // src -> project root
        .to_path_buf();
    repo_root
        .join("test")
        .join("fixtures")
        .join("speaker_encoder_golden.json")
}

fn load_golden() -> GoldenData {
    let path = fixture_path();
    let data = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("Failed to read golden file {}: {e}", path.display()));
    serde_json::from_str(&data).unwrap_or_else(|e| panic!("Failed to parse golden file: {e}"))
}

fn generate_sine(freq_hz: f32, duration_s: f32, sr: u32) -> Vec<f32> {
    let n = (duration_s * sr as f32) as usize;
    (0..n)
        .map(|i| (2.0 * PI * freq_hz * i as f32 / sr as f32).sin())
        .collect()
}

fn generate_multitone(freqs: &[f32], duration_s: f32, sr: u32) -> Vec<f32> {
    let n = (duration_s * sr as f32) as usize;
    let mut samples = vec![0.0f32; n];
    for &f in freqs {
        for (i, s) in samples.iter_mut().enumerate() {
            *s += (2.0 * PI * f * i as f32 / sr as f32).sin();
        }
    }
    let peak = samples.iter().map(|s| s.abs()).fold(0.0f32, f32::max);
    if peak > 0.0 {
        for s in &mut samples {
            *s /= peak;
        }
    }
    samples
}

/// Relative L2 distance between two slices.
fn relative_l2(a: &[f32], b: &[f64]) -> f64 {
    assert_eq!(a.len(), b.len(), "array length mismatch");
    let mut diff_sq = 0.0f64;
    let mut ref_sq = 0.0f64;
    for (x, y) in a.iter().zip(b.iter()) {
        let d = *x as f64 - y;
        diff_sq += d * d;
        ref_sq += y * y;
    }
    if ref_sq < 1e-20 {
        return diff_sq.sqrt();
    }
    (diff_sq / ref_sq).sqrt()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[test]
fn golden_mel_params_match() {
    let g = load_golden();
    assert_eq!(g.mel_params.sr, MEL_SAMPLE_RATE);
    assert_eq!(g.mel_params.n_fft, MEL_N_FFT);
    assert_eq!(g.mel_params.hop_length, MEL_HOP_LENGTH);
    assert_eq!(g.mel_params.n_mels, MEL_N_MELS);
    assert!((g.mel_params.fmin - MEL_FMIN).abs() < 1e-3);
    assert!((g.mel_params.fmax - MEL_FMAX).abs() < 1e-3);
}

#[test]
fn golden_hann_window() {
    let g = load_golden();
    let w = hann_window(g.hann_window.length);

    // Check first 5
    for (i, expected) in g.hann_window.first_5.iter().enumerate() {
        assert!(
            (w[i] as f64 - expected).abs() < 1e-6,
            "hann_window[{i}]: expected {expected}, got {}",
            w[i]
        );
    }

    // Check last 5
    let n = w.len();
    for (i, expected) in g.hann_window.last_5.iter().enumerate() {
        let idx = n - 5 + i;
        assert!(
            (w[idx] as f64 - expected).abs() < 1e-6,
            "hann_window[{idx}]: expected {expected}, got {}",
            w[idx]
        );
    }

    // Check mid value
    assert!(
        (w[n / 2] as f64 - g.hann_window.mid_value).abs() < 1e-6,
        "hann_window mid: expected {}, got {}",
        g.hann_window.mid_value,
        w[n / 2]
    );
}

#[test]
fn golden_mel_filterbank_shape() {
    let g = load_golden();
    let fb = create_mel_filterbank();
    let fft_bins = MEL_N_FFT / 2 + 1;

    assert_eq!(g.mel_filterbank.shape, vec![MEL_N_MELS, fft_bins]);
    assert_eq!(fb.len(), MEL_N_MELS * fft_bins);
}

#[test]
fn golden_mel_filterbank_band_sums() {
    let g = load_golden();
    let fb = create_mel_filterbank();
    let fft_bins = MEL_N_FFT / 2 + 1;

    for m in 0..MEL_N_MELS {
        let band_sum: f32 = (0..fft_bins).map(|k| fb[m * fft_bins + k]).sum();
        let expected = g.mel_filterbank.band_sums[m];
        let rel_err = if expected.abs() > 1e-10 {
            ((band_sum as f64 - expected) / expected).abs()
        } else {
            (band_sum as f64 - expected).abs()
        };
        assert!(
            rel_err < 0.02,
            "filterbank band[{m}] sum: expected {expected}, got {band_sum} (rel err {rel_err:.6})"
        );
    }
}

#[test]
fn golden_mel_filterbank_total_sum() {
    let g = load_golden();
    let fb = create_mel_filterbank();
    let total: f32 = fb.iter().sum();
    let rel_err = ((total as f64 - g.mel_filterbank.total_sum) / g.mel_filterbank.total_sum).abs();
    assert!(
        rel_err < 0.02,
        "filterbank total: expected {}, got {total} (rel err {rel_err:.6})",
        g.mel_filterbank.total_sum,
    );
}

#[test]
fn golden_sine_440hz_mel_shape() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "sine_440hz_1s")
        .unwrap();

    let audio = generate_sine(440.0, 1.0, MEL_SAMPLE_RATE);
    assert_eq!(audio.len(), tc.audio_samples_count);

    let mel = compute_mel_spectrogram(&audio);
    let n_frames = mel.len() / MEL_N_MELS;

    assert_eq!(tc.expected_mel_shape[0], MEL_N_MELS);
    assert_eq!(tc.expected_mel_shape[1], n_frames);
    assert_eq!(mel.len(), MEL_N_MELS * n_frames);
}

#[test]
fn golden_sine_440hz_mel_corners() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "sine_440hz_1s")
        .unwrap();
    let corners = tc.mel_corner_values.as_ref().unwrap();

    let audio = generate_sine(440.0, 1.0, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);
    let n_frames = mel.len() / MEL_N_MELS;

    let tol = 0.02; // 2% relative tolerance
    let check = |name: &str, actual: f32, expected: f64| {
        let rel = if expected.abs() > 1e-10 {
            ((actual as f64 - expected) / expected).abs()
        } else {
            (actual as f64 - expected).abs()
        };
        assert!(
            rel < tol,
            "{name}: expected {expected}, got {actual} (rel err {rel:.6})"
        );
    };

    check("top_left", mel[0], corners.top_left);
    check("top_right", mel[n_frames - 1], corners.top_right);
    check(
        "bottom_left",
        mel[(MEL_N_MELS - 1) * n_frames],
        corners.bottom_left,
    );
    check(
        "bottom_right",
        mel[MEL_N_MELS * n_frames - 1],
        corners.bottom_right,
    );
}

#[test]
fn golden_sine_440hz_mel_sampled() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "sine_440hz_1s")
        .unwrap();

    let audio = generate_sine(440.0, 1.0, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);

    let sampled: Vec<f32> = mel.iter().step_by(10).copied().collect();
    let expected = tc.mel_sampled_every_10.as_ref().unwrap();

    let l2 = relative_l2(&sampled, expected);
    assert!(
        l2 < 0.02,
        "sine_440hz sampled L2 distance {l2:.6} exceeds 2% tolerance"
    );
}

#[test]
fn golden_sine_1000hz_mel_corners() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "sine_1000hz_0.5s")
        .unwrap();
    let corners = tc.mel_corner_values.as_ref().unwrap();

    let audio = generate_sine(1000.0, 0.5, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);
    let n_frames = mel.len() / MEL_N_MELS;

    let tol = 0.02;
    let check = |name: &str, actual: f32, expected: f64| {
        let rel = if expected.abs() > 1e-10 {
            ((actual as f64 - expected) / expected).abs()
        } else {
            (actual as f64 - expected).abs()
        };
        assert!(
            rel < tol,
            "{name}: expected {expected}, got {actual} (rel err {rel:.6})"
        );
    };

    check("top_left", mel[0], corners.top_left);
    check("top_right", mel[n_frames - 1], corners.top_right);
    check(
        "bottom_left",
        mel[(MEL_N_MELS - 1) * n_frames],
        corners.bottom_left,
    );
    check(
        "bottom_right",
        mel[MEL_N_MELS * n_frames - 1],
        corners.bottom_right,
    );
}

#[test]
fn golden_sine_1000hz_mel_sampled() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "sine_1000hz_0.5s")
        .unwrap();

    let audio = generate_sine(1000.0, 0.5, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);

    let sampled: Vec<f32> = mel.iter().step_by(10).copied().collect();
    let expected = tc.mel_sampled_every_10.as_ref().unwrap();

    let l2 = relative_l2(&sampled, expected);
    assert!(
        l2 < 0.02,
        "sine_1000hz sampled L2 distance {l2:.6} exceeds 2% tolerance"
    );
}

#[test]
fn golden_multitone_mel_corners() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "multitone_200_600_2000hz_0.5s")
        .unwrap();
    let corners = tc.mel_corner_values.as_ref().unwrap();

    let audio = generate_multitone(&[200.0, 600.0, 2000.0], 0.5, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);
    let n_frames = mel.len() / MEL_N_MELS;

    let tol = 0.02;
    let check = |name: &str, actual: f32, expected: f64| {
        let rel = if expected.abs() > 1e-10 {
            ((actual as f64 - expected) / expected).abs()
        } else {
            (actual as f64 - expected).abs()
        };
        assert!(
            rel < tol,
            "{name}: expected {expected}, got {actual} (rel err {rel:.6})"
        );
    };

    check("top_left", mel[0], corners.top_left);
    check("top_right", mel[n_frames - 1], corners.top_right);
    check(
        "bottom_left",
        mel[(MEL_N_MELS - 1) * n_frames],
        corners.bottom_left,
    );
    check(
        "bottom_right",
        mel[MEL_N_MELS * n_frames - 1],
        corners.bottom_right,
    );
}

#[test]
fn golden_multitone_mel_sampled() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "multitone_200_600_2000hz_0.5s")
        .unwrap();

    let audio = generate_multitone(&[200.0, 600.0, 2000.0], 0.5, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);

    let sampled: Vec<f32> = mel.iter().step_by(10).copied().collect();
    let expected = tc.mel_sampled_every_10.as_ref().unwrap();

    let l2 = relative_l2(&sampled, expected);
    assert!(
        l2 < 0.02,
        "multitone sampled L2 distance {l2:.6} exceeds 2% tolerance"
    );
}

#[test]
fn golden_resample_48k_to_16k() {
    let g = load_golden();
    let tc = g
        .test_cases
        .iter()
        .find(|t| t.id == "resample_48k_to_16k")
        .unwrap();

    let audio_48k = generate_sine(440.0, 0.1, 48000);
    assert_eq!(audio_48k.len(), tc.input_samples_count);

    let resampled = resample_linear(&audio_48k, 48000, MEL_SAMPLE_RATE);
    assert_eq!(resampled.len(), tc.expected_output_count);

    // Check first 10 samples
    let expected_first = tc.output_first_10.as_ref().unwrap();
    for (i, expected) in expected_first.iter().enumerate() {
        assert!(
            (resampled[i] as f64 - expected).abs() < 1e-4,
            "resample first[{i}]: expected {expected}, got {}",
            resampled[i]
        );
    }

    // Check last 10 samples
    let expected_last = tc.output_last_10.as_ref().unwrap();
    let n = resampled.len();
    for (i, expected) in expected_last.iter().enumerate() {
        let idx = n - 10 + i;
        assert!(
            (resampled[idx] as f64 - expected).abs() < 1e-4,
            "resample last[{i}]: expected {expected}, got {}",
            resampled[idx]
        );
    }
}

#[test]
fn golden_all_mel_values_finite() {
    // Verify all mel values are finite for each test signal
    for (freq, dur) in [(440.0, 1.0), (1000.0, 0.5)] {
        let audio = generate_sine(freq, dur, MEL_SAMPLE_RATE);
        let mel = compute_mel_spectrogram(&audio);
        assert!(
            mel.iter().all(|v| v.is_finite()),
            "non-finite mel value for {freq}Hz {dur}s sine"
        );
    }

    let audio = generate_multitone(&[200.0, 600.0, 2000.0], 0.5, MEL_SAMPLE_RATE);
    let mel = compute_mel_spectrogram(&audio);
    assert!(
        mel.iter().all(|v| v.is_finite()),
        "non-finite mel value for multitone"
    );
}

#[test]
fn golden_silent_audio_produces_finite_mel() {
    let silence = vec![0.0f32; 16000];
    let mel = compute_mel_spectrogram(&silence);
    assert!(!mel.is_empty());
    assert!(
        mel.iter().all(|v| v.is_finite()),
        "non-finite mel value for silent audio"
    );
}

#[test]
fn golden_short_audio_empty_mel() {
    let short = vec![0.0f32; 100];
    let mel = compute_mel_spectrogram(&short);
    assert!(mel.is_empty(), "short audio should produce empty mel");
}
