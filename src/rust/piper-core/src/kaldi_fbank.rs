//! Kaldi-compatible filterbank features and Kaiser-windowed sinc resampling.
//!
//! Ports the speaker front end the public zs-v1 base was verified with
//! (`scripts/public_base_runtime.py`, the Hugging Face Space's
//! `zero_shot.py`, and the browser's `kaldi-fbank.js`):
//!
//! - [`resample_kaiser_best`]: `torchaudio.functional.resample` with
//!   `resampling_method="sinc_interp_kaiser"`, `lowpass_filter_width=64`,
//!   `rolloff=0.9475937167399596`, `beta=14.769656459379492` ("kaiser_best").
//! - [`kaldi_fbank`]: `torchaudio.compliance.kaldi.fbank` with its defaults at
//!   16 kHz, 80 mel bins, 25 ms / 10 ms frames and `dither=0` (povey window,
//!   DC removal, preemphasis 0.97, 512-point power spectrum, mel bins from
//!   20 Hz to Nyquist, log floored at float32 epsilon).
//!
//! Arithmetic is f64; `tests/test_kaldi_fbank_golden.rs` checks the result
//! against torchaudio (`test/fixtures/kaldi_fbank_golden.json`).

use std::f64::consts::PI;

/// Sample rate the features are computed at.
pub const KALDI_FBANK_SAMPLE_RATE: u32 = 16000;
/// Number of mel bins per frame.
pub const KALDI_FBANK_NUM_MEL_BINS: usize = 80;

const FRAME_LENGTH: usize = 400; // 25 ms at 16 kHz
const FRAME_SHIFT: usize = 160; // 10 ms at 16 kHz
const PADDED_LENGTH: usize = 512;
const NUM_FFT_BINS: usize = PADDED_LENGTH / 2;
const PREEMPHASIS: f64 = 0.97;
const LOW_FREQ: f64 = 20.0;
const FLOAT32_EPSILON: f64 = f32::EPSILON as f64;

const KAISER_LOWPASS_FILTER_WIDTH: f64 = 64.0;
const KAISER_ROLLOFF: f64 = 0.9475937167399596;
const KAISER_BETA: f64 = 14.769656459379492;

// ---------------------------------------------------------------------------
// Resampling
// ---------------------------------------------------------------------------

fn gcd(mut a: u32, mut b: u32) -> u32 {
    while b != 0 {
        (a, b) = (b, a % b);
    }
    a
}

/// Modified Bessel function of the first kind, order 0 (power series).
fn bessel_i0(x: f64) -> f64 {
    let q = x * x / 4.0;
    let mut term = 1.0;
    let mut sum = 1.0;
    let mut k = 1.0;
    while term > sum * 1e-17 {
        term *= q / (k * k);
        sum += term;
        k += 1.0;
    }
    sum
}

/// `torchaudio.functional._get_sinc_resample_kernel` for already
/// gcd-reduced rates. Returns `(kernel, width, taps)`, one row of `taps`
/// coefficients per output phase.
fn sinc_resample_kernel(orig: u32, target: u32) -> (Vec<f64>, usize, usize) {
    let base_freq = f64::from(orig.min(target)) * KAISER_ROLLOFF;
    let width = (KAISER_LOWPASS_FILTER_WIDTH * f64::from(orig) / base_freq).ceil() as usize;
    let taps = 2 * width + orig as usize;
    let scale = base_freq / f64::from(orig);
    let i0_beta = bessel_i0(KAISER_BETA);
    let mut kernel = vec![0.0; target as usize * taps];
    for phase in 0..target as usize {
        for k in 0..taps {
            let t = (-(phase as f64) / f64::from(target)
                + (k as f64 - width as f64) / f64::from(orig))
                * base_freq;
            let t = t.clamp(-KAISER_LOWPASS_FILTER_WIDTH, KAISER_LOWPASS_FILTER_WIDTH);
            let ratio = t / KAISER_LOWPASS_FILTER_WIDTH;
            let window = bessel_i0(KAISER_BETA * (1.0 - ratio * ratio).sqrt()) / i0_beta;
            let x = t * PI;
            let sinc = if x == 0.0 { 1.0 } else { x.sin() / x };
            kernel[phase * taps + k] = sinc * window * scale;
        }
    }
    (kernel, width, taps)
}

/// Resample mono PCM with torchaudio's "kaiser_best" sinc interpolation.
///
/// Returns a copy of the input when the rates are equal.
///
/// # Panics
///
/// Panics if either rate is zero.
pub fn resample_kaiser_best(samples: &[f32], from_rate: u32, to_rate: u32) -> Vec<f32> {
    assert!(
        from_rate > 0 && to_rate > 0,
        "sample rate must be positive, got {from_rate} -> {to_rate}"
    );
    if from_rate == to_rate {
        return samples.to_vec();
    }
    let g = gcd(from_rate, to_rate);
    let orig = (from_rate / g) as usize;
    let target = (to_rate / g) as usize;
    let (kernel, width, taps) = sinc_resample_kernel(orig as u32, target as u32);

    // Input is zero-padded by `width` on the left (F.pad in torchaudio);
    // reads outside the signal contribute nothing.
    let length = samples.len() as i64;
    let out_length = (target * samples.len()).div_ceil(orig);
    let mut out = vec![0.0f32; out_length];
    for (i, value) in out.iter_mut().enumerate() {
        let frame = i / target;
        let phase = i - frame * target;
        let start = (frame * orig) as i64 - width as i64;
        let row = &kernel[phase * taps..(phase + 1) * taps];
        let k_from = (-start).max(0) as usize;
        let k_to = (length - start).clamp(0, taps as i64) as usize;
        let mut acc = 0.0;
        for k in k_from..k_to {
            acc += f64::from(samples[(start + k as i64) as usize]) * row[k];
        }
        *value = acc as f32;
    }
    out
}

// ---------------------------------------------------------------------------
// Filterbank
// ---------------------------------------------------------------------------

fn mel_scale(freq: f64) -> f64 {
    1127.0 * (1.0 + freq / 700.0).ln()
}

/// `torch.hann_window(400, periodic=False).pow(0.85)`
fn povey_window() -> Vec<f64> {
    (0..FRAME_LENGTH)
        .map(|n| {
            let hann = 0.5 - 0.5 * (2.0 * PI * n as f64 / (FRAME_LENGTH - 1) as f64).cos();
            hann.powf(0.85)
        })
        .collect()
}

/// `torchaudio.compliance.kaldi.get_mel_banks` without VTLN warping; the
/// Nyquist bin (index 256) gets zero weight, as torchaudio pads it.
fn mel_filterbank() -> Vec<f64> {
    let bin_width = f64::from(KALDI_FBANK_SAMPLE_RATE) / PADDED_LENGTH as f64;
    let mel_low = mel_scale(LOW_FREQ);
    let mel_high = mel_scale(f64::from(KALDI_FBANK_SAMPLE_RATE) / 2.0);
    let delta = (mel_high - mel_low) / (KALDI_FBANK_NUM_MEL_BINS + 1) as f64;
    let mut banks = vec![0.0; KALDI_FBANK_NUM_MEL_BINS * NUM_FFT_BINS];
    for m in 0..KALDI_FBANK_NUM_MEL_BINS {
        let left = mel_low + m as f64 * delta;
        let center = mel_low + (m + 1) as f64 * delta;
        let right = mel_low + (m + 2) as f64 * delta;
        for k in 0..NUM_FFT_BINS {
            let mel = mel_scale(bin_width * k as f64);
            let up = (mel - left) / (center - left);
            let down = (right - mel) / (right - center);
            banks[m * NUM_FFT_BINS + k] = up.min(down).max(0.0);
        }
    }
    banks
}

/// Twiddle factors and bit-reversal table for a radix-2 FFT of
/// `PADDED_LENGTH` points.
struct Fft {
    reverse: Vec<usize>,
    cos: Vec<f64>,
    sin: Vec<f64>,
}

impl Fft {
    fn new() -> Self {
        let n = PADDED_LENGTH;
        let bits = n.trailing_zeros();
        let reverse = (0..n)
            .map(|i| i.reverse_bits() >> (usize::BITS - bits))
            .collect();
        let cos = (0..n / 2)
            .map(|i| (2.0 * PI * i as f64 / n as f64).cos())
            .collect();
        let sin = (0..n / 2)
            .map(|i| -(2.0 * PI * i as f64 / n as f64).sin())
            .collect();
        Self { reverse, cos, sin }
    }

    /// In-place iterative radix-2 FFT.
    fn run(&self, re: &mut [f64], im: &mut [f64]) {
        let n = PADDED_LENGTH;
        for i in 0..n {
            let j = self.reverse[i];
            if j > i {
                re.swap(i, j);
                im.swap(i, j);
            }
        }
        let mut size = 2;
        while size <= n {
            let half = size / 2;
            let step = n / size;
            for start in (0..n).step_by(size) {
                for k in 0..half {
                    let wr = self.cos[k * step];
                    let wi = self.sin[k * step];
                    let a = start + k;
                    let b = a + half;
                    let tr = re[b] * wr - im[b] * wi;
                    let ti = re[b] * wi + im[b] * wr;
                    re[b] = re[a] - tr;
                    im[b] = im[a] - ti;
                    re[a] += tr;
                    im[a] += ti;
                }
            }
            size <<= 1;
        }
    }
}

/// Compute Kaldi log mel filterbank features of mono 16 kHz PCM.
///
/// Returns a frame-major `[frames * 80]` array; empty when the input is
/// shorter than one 25 ms window (frames at the edges are not padded).
pub fn kaldi_fbank(samples: &[f32]) -> Vec<f32> {
    let num_frames = if samples.len() >= FRAME_LENGTH {
        1 + (samples.len() - FRAME_LENGTH) / FRAME_SHIFT
    } else {
        0
    };
    let window = povey_window();
    let banks = mel_filterbank();
    let fft = Fft::new();
    let mut out = vec![0.0f32; num_frames * KALDI_FBANK_NUM_MEL_BINS];
    let mut frame = [0.0f64; FRAME_LENGTH];
    let mut re = [0.0f64; PADDED_LENGTH];
    let mut im = [0.0f64; PADDED_LENGTH];
    let mut power = [0.0f64; NUM_FFT_BINS];

    for f in 0..num_frames {
        let start = f * FRAME_SHIFT;
        for (n, x) in frame.iter_mut().enumerate() {
            *x = f64::from(samples[start + n]);
        }
        let mean = frame.iter().sum::<f64>() / FRAME_LENGTH as f64;
        for x in frame.iter_mut() {
            *x -= mean;
        }
        // Preemphasis; the first sample uses itself as its predecessor.
        re.fill(0.0);
        im.fill(0.0);
        for n in 0..FRAME_LENGTH {
            let prev = if n > 0 { frame[n - 1] } else { frame[0] };
            re[n] = (frame[n] - PREEMPHASIS * prev) * window[n];
        }
        fft.run(&mut re, &mut im);
        for (k, p) in power.iter_mut().enumerate() {
            *p = re[k] * re[k] + im[k] * im[k];
        }
        for m in 0..KALDI_FBANK_NUM_MEL_BINS {
            let row = &banks[m * NUM_FFT_BINS..(m + 1) * NUM_FFT_BINS];
            let energy: f64 = row.iter().zip(power.iter()).map(|(b, p)| b * p).sum();
            out[f * KALDI_FBANK_NUM_MEL_BINS + m] = energy.max(FLOAT32_EPSILON).ln() as f32;
        }
    }
    out
}

/// Subtract each mel bin's mean over time from a frame-major `[frames * 80]`
/// array (`features -= features.mean(dim=0)` in the Python recipe).
pub fn subtract_band_means(features: &mut [f32]) {
    let frames = features.len() / KALDI_FBANK_NUM_MEL_BINS;
    if frames == 0 {
        return;
    }
    for m in 0..KALDI_FBANK_NUM_MEL_BINS {
        let sum: f64 = (0..frames)
            .map(|f| f64::from(features[f * KALDI_FBANK_NUM_MEL_BINS + m]))
            .sum();
        let mean = sum / frames as f64;
        for f in 0..frames {
            let v = &mut features[f * KALDI_FBANK_NUM_MEL_BINS + m];
            *v = (f64::from(*v) - mean) as f32;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frames_need_one_full_window() {
        assert!(kaldi_fbank(&[0.0; 399]).is_empty());
        assert_eq!(kaldi_fbank(&[0.0; 400]).len(), KALDI_FBANK_NUM_MEL_BINS);
        assert_eq!(kaldi_fbank(&[0.0; 560]).len(), 2 * KALDI_FBANK_NUM_MEL_BINS);
    }

    #[test]
    fn same_rate_returns_input() {
        let x = [0.1f32, -0.2, 0.3];
        assert_eq!(resample_kaiser_best(&x, 16000, 16000), x);
    }

    #[test]
    fn subtract_band_means_zeroes_each_bin_mean() {
        let mut feats: Vec<f32> = (0..3 * KALDI_FBANK_NUM_MEL_BINS)
            .map(|i| i as f32)
            .collect();
        subtract_band_means(&mut feats);
        for m in 0..KALDI_FBANK_NUM_MEL_BINS {
            let sum: f32 = (0..3)
                .map(|f| feats[f * KALDI_FBANK_NUM_MEL_BINS + m])
                .sum();
            assert!(sum.abs() < 1e-3, "bin {m} mean {sum}");
        }
    }
}
