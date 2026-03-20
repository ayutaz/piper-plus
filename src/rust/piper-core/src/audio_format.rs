//! Audio format conversion and resampling utilities.
//!
//! Provides sample rate conversion, format conversion, and audio processing.
//! Resampling uses the `rubato` crate (feature-gated behind "resample").

#[cfg(feature = "resample")]
use crate::error::PiperError;

/// Audio format specification
#[derive(Debug, Clone, PartialEq)]
pub struct AudioFormat {
    pub sample_rate: u32,
    pub channels: u16,
    pub bits_per_sample: u16,
}

impl AudioFormat {
    pub fn mono_16bit(sample_rate: u32) -> Self {
        Self {
            sample_rate,
            channels: 1,
            bits_per_sample: 16,
        }
    }

    /// Piper default: 22050 Hz, mono, 16-bit
    pub fn piper_default() -> Self {
        Self::mono_16bit(22050)
    }
}

/// Resample audio from one sample rate to another.
/// Uses linear interpolation (always available, no external deps).
pub fn resample_linear(samples: &[i16], from_rate: u32, to_rate: u32) -> Vec<i16> {
    if samples.is_empty() || from_rate == 0 || to_rate == 0 {
        return Vec::new();
    }

    if from_rate == to_rate {
        return samples.to_vec();
    }

    let ratio = to_rate as f64 / from_rate as f64;
    let out_len = (samples.len() as f64 * ratio).ceil() as usize;
    let mut output = Vec::with_capacity(out_len);

    let step = from_rate as f64 / to_rate as f64; // pre-computed inverse ratio
    let mut src_pos = 0.0_f64;
    for _i in 0..out_len {
        let src_idx = src_pos as usize;
        let frac = src_pos - src_idx as f64;

        let sample = if src_idx + 1 < samples.len() {
            let a = samples[src_idx] as f64;
            let b = samples[src_idx + 1] as f64;
            (a + (b - a) * frac) as i16
        } else {
            // Last sample: no interpolation partner, use as-is
            samples[samples.len() - 1]
        };

        output.push(sample);
        src_pos += step; // addition instead of division per sample
    }

    output
}

/// High-quality resampling using rubato (feature-gated).
/// Uses sinc interpolation for better quality.
#[cfg(feature = "resample")]
pub fn resample_sinc(
    samples: &[i16],
    from_rate: u32,
    to_rate: u32,
) -> Result<Vec<i16>, PiperError> {
    use rubato::{
        Resampler, SincFixedIn, SincInterpolationParameters, SincInterpolationType, WindowFunction,
    };

    if samples.is_empty() || from_rate == 0 || to_rate == 0 {
        return Ok(Vec::new());
    }

    if from_rate == to_rate {
        return Ok(samples.to_vec());
    }

    let params = SincInterpolationParameters {
        sinc_len: 256,
        f_cutoff: 0.95,
        interpolation: SincInterpolationType::Linear,
        oversampling_factor: 256,
        window: WindowFunction::BlackmanHarris2,
    };

    let ratio = to_rate as f64 / from_rate as f64;
    let chunk_size = 1024;

    let mut resampler = SincFixedIn::<f64>::new(
        ratio, 2.0, params, chunk_size, 1, // mono
    )
    .map_err(|e| PiperError::Inference(format!("resample init failed: {e}")))?;

    // Convert i16 -> f64
    let input_f64: Vec<f64> = samples.iter().map(|&s| s as f64 / 32768.0).collect();

    let mut output_f64 = Vec::new();

    // Process in chunks
    let mut pos = 0;
    while pos + chunk_size <= input_f64.len() {
        let chunk = &input_f64[pos..pos + chunk_size];
        let result = resampler
            .process(&[chunk], None)
            .map_err(|e| PiperError::Inference(format!("resample failed: {e}")))?;
        output_f64.extend_from_slice(&result[0]);
        pos += chunk_size;
    }

    // Process remaining samples (pad with zeros if needed)
    if pos < input_f64.len() {
        let remaining = &input_f64[pos..];
        let mut padded = remaining.to_vec();
        padded.resize(chunk_size, 0.0);
        let result = resampler
            .process(&[&padded], None)
            .map_err(|e| PiperError::Inference(format!("resample failed: {e}")))?;
        // Only take proportional output
        let expected = ((input_f64.len() - pos) as f64 * ratio).ceil() as usize;
        let take = expected.min(result[0].len());
        output_f64.extend_from_slice(&result[0][..take]);
    }

    // Convert f64 -> i16
    let output: Vec<i16> = output_f64
        .iter()
        .map(|&s| (s * 32767.0).clamp(-32768.0, 32767.0) as i16)
        .collect();

    Ok(output)
}

/// Convert mono to stereo (duplicate channel)
pub fn mono_to_stereo(samples: &[i16]) -> Vec<i16> {
    let mut output = Vec::with_capacity(samples.len() * 2);
    for &s in samples {
        output.push(s);
        output.push(s);
    }
    output
}

/// Convert stereo to mono (average channels)
pub fn stereo_to_mono(samples: &[i16]) -> Vec<i16> {
    samples
        .chunks_exact(2)
        .map(|pair| {
            // Use i32 to avoid overflow when averaging
            ((pair[0] as i32 + pair[1] as i32) / 2) as i16
        })
        .collect()
}

/// Convert i16 samples to f32 (-1.0 to 1.0)
pub fn i16_to_f32(samples: &[i16]) -> Vec<f32> {
    samples.iter().map(|&s| s as f32 / 32768.0).collect()
}

/// Convert f32 samples to i16 (with clamping)
pub fn f32_to_i16(samples: &[f32]) -> Vec<i16> {
    samples
        .iter()
        .map(|&s| (s * 32768.0).clamp(-32768.0, 32767.0) as i16)
        .collect()
}

/// Normalize audio to a target peak level (in dB, e.g., -1.0 dB).
///
/// `target_db` is relative to full scale (0 dB = i16::MAX).
/// A value of -1.0 means the peak will be at ~91.2% of full scale.
pub fn normalize_peak(samples: &mut [i16], target_db: f32) {
    if samples.is_empty() {
        return;
    }

    // Find current peak
    let current_peak = samples
        .iter()
        .map(|&s| (s as i32).unsigned_abs())
        .max()
        .unwrap_or(0);

    if current_peak == 0 {
        return; // Silence -- nothing to normalize
    }

    // Target peak in linear scale (0 dB = 32767)
    let target_linear = 32767.0_f64 * 10.0_f64.powf(target_db as f64 / 20.0);
    let scale = target_linear / current_peak as f64;

    for s in samples.iter_mut() {
        *s = (*s as f64 * scale).clamp(-32768.0, 32767.0) as i16;
    }
}

/// Compute RMS level in dB.
///
/// Returns the RMS relative to full scale (0 dB = 32768).
/// Returns `f32::NEG_INFINITY` for silence (all zeros).
pub fn rms_db(samples: &[i16]) -> f32 {
    if samples.is_empty() {
        return f32::NEG_INFINITY;
    }

    let sum_sq: f64 = samples.iter().map(|&s| (s as f64) * (s as f64)).sum();
    let rms = (sum_sq / samples.len() as f64).sqrt();

    if rms == 0.0 {
        return f32::NEG_INFINITY;
    }

    (20.0 * (rms / 32768.0).log10()) as f32
}

/// Trim silence from the beginning and end of audio.
///
/// Removes leading and trailing samples whose absolute value falls below
/// the given threshold (in dB relative to full scale).
pub fn trim_silence(samples: &[i16], threshold_db: f32) -> &[i16] {
    if samples.is_empty() {
        return samples;
    }

    // Convert threshold from dB to linear amplitude
    let threshold_linear = (32768.0_f64 * 10.0_f64.powf(threshold_db as f64 / 20.0)) as i32;

    // Find first sample above threshold
    let start = samples
        .iter()
        .position(|&s| (s as i32).abs() >= threshold_linear)
        .unwrap_or(0);

    // Find last sample above threshold
    let end = samples
        .iter()
        .rposition(|&s| (s as i32).abs() >= threshold_linear)
        .map(|p| p + 1)
        .unwrap_or(0);

    if start >= end {
        return &samples[0..0];
    }

    &samples[start..end]
}

/// Apply a simple fade-in effect (linear amplitude ramp).
pub fn fade_in(samples: &mut [i16], fade_samples: usize) {
    let fade_len = fade_samples.min(samples.len());
    if fade_len == 0 {
        return;
    }
    let inv_len = 1.0_f64 / fade_len as f64; // compute once
    let mut gain = 0.0_f64;
    for s in samples[..fade_len].iter_mut() {
        *s = (*s as f64 * gain) as i16;
        gain += inv_len; // addition per sample instead of division
    }
}

/// Apply a simple fade-out effect (linear amplitude ramp).
pub fn fade_out(samples: &mut [i16], fade_samples: usize) {
    let len = samples.len();
    let fade_len = fade_samples.min(len);
    if fade_len == 0 {
        return;
    }
    let fade_start = len - fade_len;
    let inv_len = 1.0_f64 / fade_len as f64; // compute once
    let mut gain = 1.0_f64;
    for s in samples[fade_start..].iter_mut() {
        *s = (*s as f64 * gain) as i16;
        gain -= inv_len; // addition per sample instead of division
    }
}

/// Concatenate multiple audio chunks with optional crossfade.
///
/// When `crossfade_samples` is 0, performs simple concatenation.
/// When > 0, applies linear crossfade overlap between adjacent chunks.
pub fn concat_audio(chunks: &[&[i16]], crossfade_samples: usize) -> Vec<i16> {
    if chunks.is_empty() {
        return Vec::new();
    }

    if chunks.len() == 1 {
        return chunks[0].to_vec();
    }

    if crossfade_samples == 0 {
        // Simple concatenation
        let total_len: usize = chunks.iter().map(|c| c.len()).sum();
        let mut output = Vec::with_capacity(total_len);
        for chunk in chunks {
            output.extend_from_slice(chunk);
        }
        return output;
    }

    // Crossfade concatenation using overlap-add
    let mut output = chunks[0].to_vec();

    for chunk in &chunks[1..] {
        let xfade = crossfade_samples.min(output.len()).min(chunk.len());

        if xfade == 0 {
            output.extend_from_slice(chunk);
            continue;
        }

        // Apply crossfade to the overlap region
        let out_start = output.len() - xfade;
        let slope = 1.0_f64 / (xfade + 1) as f64; // pre-computed step
        let mut t = slope;
        for i in 0..xfade {
            let a = output[out_start + i] as f64 * (1.0 - t);
            let b = chunk[i] as f64 * t;
            output[out_start + i] = (a + b).clamp(-32768.0, 32767.0) as i16;
            t += slope; // addition instead of division per sample
        }

        // Append the rest of the chunk after the crossfade region
        if xfade < chunk.len() {
            output.extend_from_slice(&chunk[xfade..]);
        }
    }

    output
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- AudioFormat tests ---

    #[test]
    fn test_audio_format_mono_16bit() {
        let fmt = AudioFormat::mono_16bit(44100);
        assert_eq!(fmt.sample_rate, 44100);
        assert_eq!(fmt.channels, 1);
        assert_eq!(fmt.bits_per_sample, 16);
    }

    #[test]
    fn test_audio_format_piper_default() {
        let fmt = AudioFormat::piper_default();
        assert_eq!(fmt.sample_rate, 22050);
        assert_eq!(fmt.channels, 1);
        assert_eq!(fmt.bits_per_sample, 16);
    }

    #[test]
    fn test_audio_format_equality() {
        let a = AudioFormat::mono_16bit(16000);
        let b = AudioFormat::mono_16bit(16000);
        let c = AudioFormat::mono_16bit(22050);
        assert_eq!(a, b);
        assert_ne!(a, c);
    }

    // --- resample_linear tests ---

    #[test]
    fn test_resample_linear_identity() {
        let input: Vec<i16> = (0..100).map(|i| (i * 100) as i16).collect();
        let output = resample_linear(&input, 22050, 22050);
        assert_eq!(input, output);
    }

    #[test]
    fn test_resample_linear_empty() {
        let output = resample_linear(&[], 22050, 44100);
        assert!(output.is_empty());
    }

    #[test]
    fn test_resample_linear_upsample_length() {
        let input: Vec<i16> = vec![0; 100];
        let output = resample_linear(&input, 22050, 44100);
        // Expect roughly 2x the number of samples
        assert!((output.len() as f64 - 200.0).abs() < 2.0);
    }

    #[test]
    fn test_resample_linear_downsample_length() {
        let input: Vec<i16> = vec![0; 200];
        let output = resample_linear(&input, 44100, 22050);
        // Expect roughly half the number of samples
        assert!((output.len() as f64 - 100.0).abs() < 2.0);
    }

    #[test]
    fn test_resample_linear_preserves_dc() {
        // A constant signal should remain constant after resampling
        let input: Vec<i16> = vec![1000; 100];
        let output = resample_linear(&input, 22050, 44100);
        for &s in &output {
            assert_eq!(s, 1000);
        }
    }

    #[test]
    fn test_resample_linear_zero_rate() {
        let input: Vec<i16> = vec![100; 10];
        assert!(resample_linear(&input, 0, 44100).is_empty());
        assert!(resample_linear(&input, 44100, 0).is_empty());
    }

    // --- mono_to_stereo / stereo_to_mono tests ---

    #[test]
    fn test_mono_to_stereo() {
        let mono = vec![100i16, 200, 300];
        let stereo = mono_to_stereo(&mono);
        assert_eq!(stereo, vec![100, 100, 200, 200, 300, 300]);
    }

    #[test]
    fn test_stereo_to_mono() {
        let stereo = vec![100i16, 200, 300, 400];
        let mono = stereo_to_mono(&stereo);
        assert_eq!(mono, vec![150, 350]);
    }

    #[test]
    fn test_mono_stereo_roundtrip() {
        let original = vec![100i16, -200, 300, -400, 500];
        let stereo = mono_to_stereo(&original);
        let back = stereo_to_mono(&stereo);
        assert_eq!(original, back);
    }

    #[test]
    fn test_stereo_to_mono_empty() {
        let result = stereo_to_mono(&[]);
        assert!(result.is_empty());
    }

    // --- i16_to_f32 / f32_to_i16 tests ---

    #[test]
    fn test_i16_to_f32_range() {
        let samples = vec![0i16, 32767, -32768];
        let floats = i16_to_f32(&samples);
        assert!((floats[0]).abs() < 1e-6);
        assert!((floats[1] - 32767.0 / 32768.0).abs() < 1e-5);
        assert!((floats[2] - (-1.0)).abs() < 1e-5);
    }

    #[test]
    fn test_f32_to_i16_clamping() {
        let samples = vec![2.0f32, -2.0, 0.5];
        let ints = f32_to_i16(&samples);
        assert_eq!(ints[0], 32767); // clamped
        assert_eq!(ints[1], -32768); // clamped
        // 0.5 * 32768 = 16384
        assert_eq!(ints[2], 16384);
    }

    #[test]
    fn test_i16_f32_roundtrip() {
        let original = vec![0i16, 1000, -1000, 16384, -16384];
        let floats = i16_to_f32(&original);
        let back = f32_to_i16(&floats);
        // Allow +/- 1 LSB due to rounding
        for (a, b) in original.iter().zip(back.iter()) {
            assert!(
                (*a as i32 - *b as i32).abs() <= 1,
                "roundtrip mismatch: {a} vs {b}"
            );
        }
    }

    #[test]
    fn test_i16_to_f32_empty() {
        assert!(i16_to_f32(&[]).is_empty());
    }

    // --- normalize_peak tests ---

    #[test]
    fn test_normalize_peak_to_full_scale() {
        let mut samples = vec![1000i16, -1000, 500, -500];
        normalize_peak(&mut samples, 0.0);
        // Peak should now be at 32767
        let peak = samples.iter().map(|&s| (s as i32).abs()).max().unwrap();
        assert!((peak - 32767).abs() <= 1);
    }

    #[test]
    fn test_normalize_peak_minus_6db() {
        let mut samples = vec![32767i16, -32767];
        normalize_peak(&mut samples, -6.0);
        // -6 dB ~ 0.5012, peak should be ~16422
        let peak = samples.iter().map(|&s| (s as i32).abs()).max().unwrap();
        let expected = (32767.0 * 10.0_f64.powf(-6.0 / 20.0)) as i32;
        assert!(
            (peak - expected).abs() <= 1,
            "peak={peak}, expected={expected}"
        );
    }

    #[test]
    fn test_normalize_peak_silence() {
        let mut samples = vec![0i16; 100];
        normalize_peak(&mut samples, -1.0);
        // Should remain silence
        assert!(samples.iter().all(|&s| s == 0));
    }

    #[test]
    fn test_normalize_peak_empty() {
        let mut samples: Vec<i16> = Vec::new();
        normalize_peak(&mut samples, -1.0);
        assert!(samples.is_empty());
    }

    // --- rms_db tests ---

    #[test]
    fn test_rms_db_silence() {
        let samples = vec![0i16; 100];
        assert_eq!(rms_db(&samples), f32::NEG_INFINITY);
    }

    #[test]
    fn test_rms_db_full_scale_square() {
        // Full-scale square wave: RMS = 32767, dB = 20*log10(32767/32768) ~ -0.0003 dB
        let samples = vec![32767i16; 1000];
        let db = rms_db(&samples);
        assert!(
            (db - 0.0).abs() < 0.01,
            "expected ~0 dB for full-scale, got {db}"
        );
    }

    #[test]
    fn test_rms_db_known_signal() {
        // A constant signal at half amplitude: ~-6.02 dB
        let half = (32768.0 / 2.0) as i16; // 16384
        let samples = vec![half; 1000];
        let db = rms_db(&samples);
        assert!((db - (-6.02)).abs() < 0.1, "expected ~-6 dB, got {db}");
    }

    #[test]
    fn test_rms_db_empty() {
        assert_eq!(rms_db(&[]), f32::NEG_INFINITY);
    }

    // --- trim_silence tests ---

    #[test]
    fn test_trim_silence_basic() {
        // Build: [0, 0, 1000, 2000, 3000, 0, 0]
        let samples = vec![0i16, 0, 1000, 2000, 3000, 0, 0];
        // Threshold at -30 dB ~ 32768 * 10^(-30/20) ~ 1036
        let trimmed = trim_silence(&samples, -30.0);
        // Should keep samples >= 1036 in absolute value: 2000 and 3000
        assert_eq!(trimmed, &[2000, 3000]);
    }

    #[test]
    fn test_trim_silence_all_silence() {
        let samples = vec![0i16; 100];
        let trimmed = trim_silence(&samples, -60.0);
        assert!(trimmed.is_empty());
    }

    #[test]
    fn test_trim_silence_no_silence() {
        let samples = vec![10000i16, 20000, 30000];
        // Very low threshold so nothing is trimmed
        let trimmed = trim_silence(&samples, -96.0);
        assert_eq!(trimmed, &[10000, 20000, 30000]);
    }

    #[test]
    fn test_trim_silence_empty() {
        let trimmed = trim_silence(&[], -30.0);
        assert!(trimmed.is_empty());
    }

    // --- fade_in / fade_out tests ---

    #[test]
    fn test_fade_in() {
        let mut samples = vec![10000i16; 10];
        fade_in(&mut samples, 5);
        // First sample should be 0 (gain = 0/5 = 0)
        assert_eq!(samples[0], 0);
        // Samples after fade region should be unchanged
        assert_eq!(samples[5], 10000);
        assert_eq!(samples[9], 10000);
        // Fade should be monotonically increasing
        for i in 0..4 {
            assert!(samples[i] <= samples[i + 1]);
        }
    }

    #[test]
    fn test_fade_out() {
        let mut samples = vec![10000i16; 10];
        fade_out(&mut samples, 5);
        // Samples before fade region should be unchanged
        assert_eq!(samples[0], 10000);
        assert_eq!(samples[4], 10000);
        // Last sample: i=4, gain = 1.0 - 4.0/5.0 = 0.2, 10000 * 0.2 ≈ 1999..2000
        assert!(
            (samples[9] - 2000).abs() <= 1,
            "expected ~2000, got {}",
            samples[9]
        );
        // Fade should be monotonically decreasing
        for i in 5..9 {
            assert!(samples[i] >= samples[i + 1]);
        }
    }

    #[test]
    fn test_fade_in_larger_than_length() {
        let mut samples = vec![10000i16; 3];
        fade_in(&mut samples, 100); // fade_samples > len
        assert_eq!(samples[0], 0);
        // Should not panic, fade is clamped to length
    }

    #[test]
    fn test_fade_out_larger_than_length() {
        let mut samples = vec![10000i16; 3];
        fade_out(&mut samples, 100); // fade_samples > len
        // Should not panic, fade is clamped to length
        // First sample: i=0, gain = 1.0 - 0/3 = 1.0 (unchanged)
        assert_eq!(samples[0], 10000);
        // Last sample: i=2, gain = 1.0 - 2/3 ≈ 0.333
        assert!(samples[2] < samples[0], "last should be smaller than first");
    }

    // --- concat_audio tests ---

    #[test]
    fn test_concat_audio_simple() {
        let a: Vec<i16> = vec![1, 2, 3];
        let b: Vec<i16> = vec![4, 5, 6];
        let result = concat_audio(&[&a, &b], 0);
        assert_eq!(result, vec![1, 2, 3, 4, 5, 6]);
    }

    #[test]
    fn test_concat_audio_single_chunk() {
        let a: Vec<i16> = vec![1, 2, 3];
        let result = concat_audio(&[&a], 0);
        assert_eq!(result, vec![1, 2, 3]);
    }

    #[test]
    fn test_concat_audio_empty() {
        let result = concat_audio(&[], 0);
        assert!(result.is_empty());
    }

    #[test]
    fn test_concat_audio_with_crossfade_length() {
        let a: Vec<i16> = vec![10000; 10];
        let b: Vec<i16> = vec![10000; 10];
        // With crossfade of 3, output should be 10+10-3 = 17 samples
        let result = concat_audio(&[&a, &b], 3);
        assert_eq!(result.len(), 17);
    }

    #[test]
    fn test_concat_audio_crossfade_values() {
        // Crossfade between constant-value chunks should stay constant
        let a: Vec<i16> = vec![5000; 10];
        let b: Vec<i16> = vec![5000; 10];
        let result = concat_audio(&[&a, &b], 4);
        // All samples should be 5000 (crossfade of equal values = same value)
        for &s in &result {
            assert!((s - 5000).abs() <= 1, "expected ~5000, got {s}");
        }
    }

    #[test]
    fn test_concat_audio_three_chunks() {
        let a: Vec<i16> = vec![1, 2, 3];
        let b: Vec<i16> = vec![4, 5, 6];
        let c: Vec<i16> = vec![7, 8, 9];
        let result = concat_audio(&[&a, &b, &c], 0);
        assert_eq!(result, vec![1, 2, 3, 4, 5, 6, 7, 8, 9]);
    }

    // --- Edge case tests ---

    #[test]
    fn test_f32_to_i16_nan() {
        // NaN should not panic; clamping NaN is implementation-defined but
        // Rust's f32::clamp returns NaN, which `as i16` casts to 0.
        let result = f32_to_i16(&[f32::NAN]);
        assert_eq!(result.len(), 1);
        // The important thing is no panic. Rust `as` cast of NaN to i16 yields 0.
        assert_eq!(result[0], 0);
    }

    #[test]
    fn test_f32_to_i16_positive_infinity() {
        let result = f32_to_i16(&[f32::INFINITY]);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], i16::MAX);
    }

    #[test]
    fn test_f32_to_i16_negative_infinity() {
        let result = f32_to_i16(&[f32::NEG_INFINITY]);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], i16::MIN);
    }

    #[test]
    fn test_resample_linear_single_sample() {
        // A single sample should not panic and should produce output
        let input = vec![12345i16];
        let output = resample_linear(&input, 22050, 44100);
        assert!(!output.is_empty());
        // The output should contain the original value (possibly repeated)
        assert_eq!(output[0], 12345);
    }

    #[test]
    fn test_resample_linear_zero_from_rate() {
        let input = vec![100i16; 10];
        let output = resample_linear(&input, 0, 44100);
        assert!(output.is_empty());
    }

    #[test]
    fn test_resample_linear_zero_to_rate() {
        let input = vec![100i16; 10];
        let output = resample_linear(&input, 44100, 0);
        assert!(output.is_empty());
    }

    #[test]
    fn test_fade_in_zero_fade_samples() {
        // Zero fade_samples should be a no-op
        let mut samples = vec![1000i16, 2000, 3000];
        let original = samples.clone();
        fade_in(&mut samples, 0);
        assert_eq!(samples, original);
    }

    #[test]
    fn test_fade_out_zero_fade_samples() {
        // Zero fade_samples should be a no-op
        let mut samples = vec![1000i16, 2000, 3000];
        let original = samples.clone();
        fade_out(&mut samples, 0);
        assert_eq!(samples, original);
    }

    #[test]
    fn test_stereo_to_mono_odd_length() {
        // Odd-length input: chunks_exact(2) should drop the last sample
        let stereo = vec![100i16, 200, 300, 400, 500];
        let mono = stereo_to_mono(&stereo);
        // Only two complete pairs: (100,200) and (300,400); 500 is dropped
        assert_eq!(mono.len(), 2);
        assert_eq!(mono[0], 150);
        assert_eq!(mono[1], 350);
    }

    #[test]
    fn test_normalize_peak_single_sample() {
        let mut samples = vec![1000i16];
        normalize_peak(&mut samples, 0.0);
        // Single-sample peak should be scaled to 32767
        assert!((samples[0] as i32 - 32767).abs() <= 1);
    }

    #[test]
    fn test_trim_silence_very_low_threshold() {
        // At -90 dB, threshold_linear ~ 32768 * 10^(-90/20) ~ 1.036,
        // which truncates to 1 as i32, so any sample with abs >= 1 is kept.
        let samples = vec![0i16, 1, 2, 3, 0];
        let trimmed = trim_silence(&samples, -90.0);
        assert_eq!(trimmed, &[1, 2, 3]);
    }

    #[test]
    fn test_concat_audio_crossfade_exceeds_chunk_length() {
        // crossfade_samples > chunk lengths; should clamp and not panic
        let a: Vec<i16> = vec![5000; 3];
        let b: Vec<i16> = vec![5000; 2];
        let result = concat_audio(&[&a, &b], 100);
        // crossfade is clamped to min(100, 3, 2) = 2
        // output = 3 + 2 - 2 = 3 samples
        assert_eq!(result.len(), 3);
        // Since both chunks have the same constant value, all samples should
        // be approximately 5000
        for &s in &result {
            assert!((s - 5000).abs() <= 1, "expected ~5000, got {s}");
        }
    }
}
