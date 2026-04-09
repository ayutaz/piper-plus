//! Integration tests for the audio_format module.
//!
//! Covers AudioFormat construction, resampling, channel conversion,
//! sample format conversion, normalization, RMS measurement, silence
//! trimming, fade effects, and audio concatenation with crossfade.

use piper_plus::audio_format::*;

// =========================================================================
// AudioFormat struct
// =========================================================================

#[test]
fn test_audio_format_mono_16bit_construction() {
    let fmt = AudioFormat::mono_16bit(44100);
    assert_eq!(fmt.sample_rate, 44100);
    assert_eq!(fmt.channels, 1);
    assert_eq!(fmt.bits_per_sample, 16);
}

#[test]
fn test_audio_format_piper_default_values() {
    let fmt = AudioFormat::piper_default();
    assert_eq!(fmt.sample_rate, 22050);
    assert_eq!(fmt.channels, 1);
    assert_eq!(fmt.bits_per_sample, 16);
}

#[test]
fn test_audio_format_partial_eq() {
    let a = AudioFormat::mono_16bit(16000);
    let b = AudioFormat::mono_16bit(16000);
    let c = AudioFormat::mono_16bit(22050);
    assert_eq!(a, b);
    assert_ne!(a, c);
}

// =========================================================================
// resample_linear
// =========================================================================

#[test]
fn test_resample_linear_same_rate_identity() {
    let input: Vec<i16> = (0..100).map(|i| (i * 100) as i16).collect();
    let output = resample_linear(&input, 22050, 22050);
    assert_eq!(input, output);
}

#[test]
fn test_resample_linear_double_rate_length() {
    let input: Vec<i16> = vec![0; 1000];
    let output = resample_linear(&input, 22050, 44100);
    // Length should approximately double
    let expected = 2000.0;
    assert!(
        (output.len() as f64 - expected).abs() < 3.0,
        "expected ~{expected}, got {}",
        output.len()
    );
}

#[test]
fn test_resample_linear_half_rate_length() {
    let input: Vec<i16> = vec![0; 1000];
    let output = resample_linear(&input, 44100, 22050);
    // Length should approximately halve
    let expected = 500.0;
    assert!(
        (output.len() as f64 - expected).abs() < 3.0,
        "expected ~{expected}, got {}",
        output.len()
    );
}

#[test]
fn test_resample_linear_empty_input() {
    let output = resample_linear(&[], 22050, 44100);
    assert!(output.is_empty());
}

#[test]
fn test_resample_linear_preserves_dc_signal() {
    // A constant (DC) signal should remain constant after resampling
    let input: Vec<i16> = vec![5000; 200];
    let output = resample_linear(&input, 22050, 44100);
    for &s in &output {
        assert_eq!(s, 5000, "DC signal should be preserved through resampling");
    }
}

#[test]
fn test_resample_linear_sine_wave_frequency() {
    // Generate a 440 Hz sine wave at 22050 Hz for 0.1 seconds
    let from_rate = 22050u32;
    let to_rate = 44100u32;
    let duration_samples = (from_rate as f64 * 0.1) as usize; // 2205 samples
    let freq = 440.0;

    let input: Vec<i16> = (0..duration_samples)
        .map(|i| {
            let t = i as f64 / from_rate as f64;
            (20000.0 * (2.0 * std::f64::consts::PI * freq * t).sin()) as i16
        })
        .collect();

    let output = resample_linear(&input, from_rate, to_rate);

    // Count zero crossings in the output to verify frequency is preserved.
    // A 440 Hz sine at 44100 Hz should have ~440 zero crossings per second.
    let mut crossings = 0u32;
    for i in 1..output.len() {
        if (output[i - 1] >= 0 && output[i] < 0) || (output[i - 1] < 0 && output[i] >= 0) {
            crossings += 1;
        }
    }
    // 0.1 seconds of 440 Hz should produce ~88 crossings (2 per cycle * 44 cycles)
    let expected_crossings = (440.0 * 2.0 * 0.1) as u32; // 88
    assert!(
        (crossings as i32 - expected_crossings as i32).unsigned_abs() <= 4,
        "expected ~{expected_crossings} zero crossings, got {crossings}"
    );
}

// =========================================================================
// mono_to_stereo / stereo_to_mono
// =========================================================================

#[test]
fn test_mono_to_stereo_roundtrip() {
    let original = vec![100i16, -200, 300, -400, 500];
    let stereo = mono_to_stereo(&original);
    let back = stereo_to_mono(&stereo);
    assert_eq!(original, back);
}

#[test]
fn test_stereo_output_length_is_double_mono() {
    let mono = vec![1i16, 2, 3, 4, 5];
    let stereo = mono_to_stereo(&mono);
    assert_eq!(stereo.len(), mono.len() * 2);
}

#[test]
fn test_mono_output_length_is_half_stereo() {
    let stereo = vec![1i16, 2, 3, 4, 5, 6, 7, 8];
    let mono = stereo_to_mono(&stereo);
    assert_eq!(mono.len(), stereo.len() / 2);
}

#[test]
fn test_mono_to_stereo_empty() {
    let result = mono_to_stereo(&[]);
    assert!(result.is_empty());
}

#[test]
fn test_stereo_to_mono_empty() {
    let result = stereo_to_mono(&[]);
    assert!(result.is_empty());
}

// =========================================================================
// i16_to_f32 / f32_to_i16
// =========================================================================

#[test]
fn test_i16_f32_roundtrip_approximate() {
    let original = vec![0i16, 1000, -1000, 16384, -16384, 32767, -32768];
    let floats = i16_to_f32(&original);
    let back = f32_to_i16(&floats);
    // Allow +/- 1 LSB due to quantization rounding
    for (a, b) in original.iter().zip(back.iter()) {
        assert!(
            (*a as i32 - *b as i32).abs() <= 1,
            "roundtrip mismatch: {a} vs {b}"
        );
    }
}

#[test]
fn test_i16_to_f32_boundary_values() {
    let samples = vec![32767i16, -32768, 0];
    let floats = i16_to_f32(&samples);
    // 32767 / 32768 is very close to 1.0
    assert!(
        (floats[0] - 32767.0 / 32768.0).abs() < 1e-5,
        "32767 should map to ~1.0, got {}",
        floats[0]
    );
    // -32768 / 32768 = -1.0
    assert!(
        (floats[1] - (-1.0)).abs() < 1e-5,
        "-32768 should map to -1.0, got {}",
        floats[1]
    );
    // 0 -> 0.0
    assert!(
        floats[2].abs() < 1e-6,
        "0 should map to 0.0, got {}",
        floats[2]
    );
}

#[test]
fn test_f32_to_i16_clamping() {
    let samples = vec![2.0f32, -2.0];
    let ints = f32_to_i16(&samples);
    assert_eq!(ints[0], 32767, "values > 1.0 should clamp to 32767");
    assert_eq!(ints[1], -32768, "values < -1.0 should clamp to -32768");
}

#[test]
fn test_i16_to_f32_empty() {
    assert!(i16_to_f32(&[]).is_empty());
}

#[test]
fn test_f32_to_i16_empty() {
    assert!(f32_to_i16(&[]).is_empty());
}

// =========================================================================
// normalize_peak
// =========================================================================

#[test]
fn test_normalize_peak_reaches_target() {
    let mut samples = vec![1000i16, -500, 750, -250];
    normalize_peak(&mut samples, 0.0);
    // Peak should now be at i16::MAX (32767)
    let peak = samples.iter().map(|&s| (s as i32).abs()).max().unwrap();
    assert!(
        (peak - 32767).abs() <= 1,
        "peak should be 32767 after 0 dB normalization, got {peak}"
    );
}

#[test]
fn test_normalize_peak_silent_audio_stays_silent() {
    let mut samples = vec![0i16; 100];
    normalize_peak(&mut samples, -1.0);
    assert!(samples.iter().all(|&s| s == 0));
}

#[test]
fn test_normalize_peak_already_normalized() {
    let mut samples = vec![32767i16, -32767, 16384, -16384];
    let original = samples.clone();
    normalize_peak(&mut samples, 0.0);
    // Should be essentially unchanged (peak was already at full scale)
    for (a, b) in original.iter().zip(samples.iter()) {
        assert!(
            (*a as i32 - *b as i32).abs() <= 1,
            "already-normalized audio should not change: {a} vs {b}"
        );
    }
}

#[test]
fn test_normalize_peak_minus_6db_level() {
    let mut samples = vec![32767i16, -32767];
    normalize_peak(&mut samples, -6.0);
    let peak = samples.iter().map(|&s| (s as i32).abs()).max().unwrap();
    // -6 dB from full scale: 32767 * 10^(-6/20) ~ 16422
    let expected = (32767.0 * 10.0_f64.powf(-6.0 / 20.0)) as i32;
    assert!(
        (peak - expected).abs() <= 1,
        "peak={peak}, expected ~{expected} for -6 dB"
    );
}

// =========================================================================
// rms_db
// =========================================================================

#[test]
fn test_rms_db_full_scale_square_wave() {
    // Full-scale constant signal: RMS = 32767, dB ~ 0 dB
    let samples = vec![32767i16; 1000];
    let db = rms_db(&samples);
    assert!(
        (db - 0.0).abs() < 0.01,
        "full-scale square wave should be ~0 dB, got {db}"
    );
}

#[test]
fn test_rms_db_silence_is_neg_infinity() {
    let samples = vec![0i16; 100];
    assert_eq!(rms_db(&samples), f32::NEG_INFINITY);
}

#[test]
fn test_rms_db_empty_is_neg_infinity() {
    assert_eq!(rms_db(&[]), f32::NEG_INFINITY);
}

#[test]
fn test_rms_db_half_amplitude_approx_minus_6db() {
    // Constant signal at half amplitude: 16384 ~ -6.02 dB
    let half = (32768.0 / 2.0) as i16;
    let samples = vec![half; 1000];
    let db = rms_db(&samples);
    assert!(
        (db - (-6.02)).abs() < 0.1,
        "half-amplitude constant should be ~-6 dB, got {db}"
    );
}

// =========================================================================
// trim_silence
// =========================================================================

#[test]
fn test_trim_silence_removes_leading_and_trailing() {
    // [silence, silence, loud, louder, silence, silence]
    let samples = vec![0i16, 0, 10000, 20000, 0, 0];
    // -40 dB threshold ~ 32768 * 10^(-40/20) ~ 328
    let trimmed = trim_silence(&samples, -40.0);
    assert_eq!(trimmed, &[10000, 20000]);
}

#[test]
fn test_trim_silence_all_silent_returns_empty() {
    let samples = vec![0i16; 50];
    let trimmed = trim_silence(&samples, -60.0);
    assert!(trimmed.is_empty());
}

#[test]
fn test_trim_silence_no_silence_returns_original() {
    let samples = vec![10000i16, 20000, 30000];
    // Very low threshold so nothing is considered silence
    let trimmed = trim_silence(&samples, -96.0);
    assert_eq!(trimmed.len(), samples.len());
    assert_eq!(trimmed, samples.as_slice());
}

#[test]
fn test_trim_silence_empty_input() {
    let trimmed = trim_silence(&[], -30.0);
    assert!(trimmed.is_empty());
}

// =========================================================================
// fade_in / fade_out
// =========================================================================

#[test]
fn test_fade_in_first_sample_is_zero() {
    let mut samples = vec![10000i16; 20];
    fade_in(&mut samples, 10);
    assert_eq!(samples[0], 0, "first sample after fade_in should be 0");
}

#[test]
fn test_fade_in_preserves_samples_after_fade_region() {
    let mut samples = vec![10000i16; 20];
    fade_in(&mut samples, 5);
    // Samples after the fade region should be unchanged
    for (i, &s) in samples.iter().enumerate().skip(5) {
        assert_eq!(s, 10000, "sample[{i}] should be unchanged");
    }
}

#[test]
fn test_fade_in_monotonically_increasing() {
    let mut samples = vec![10000i16; 20];
    fade_in(&mut samples, 10);
    for i in 0..9 {
        assert!(
            samples[i] <= samples[i + 1],
            "fade_in should be monotonically increasing: sample[{i}]={} > sample[{}]={}",
            samples[i],
            i + 1,
            samples[i + 1]
        );
    }
}

#[test]
fn test_fade_out_last_sample_near_zero() {
    let mut samples = vec![10000i16; 20];
    fade_out(&mut samples, 10);
    // The last sample has gain = 1 - (9/10) = 0.1, so 10000 * 0.1 = 1000
    // The second-to-last iteration at i=9: gain = 1 - 9/10 = 0.1
    let last = samples[samples.len() - 1];
    assert!(
        last.abs() <= 1500,
        "last sample after fade_out should be near zero, got {last}"
    );
}

#[test]
fn test_fade_out_preserves_samples_before_fade_region() {
    let mut samples = vec![10000i16; 20];
    fade_out(&mut samples, 5);
    // Samples before the fade region should be unchanged
    for (i, &s) in samples.iter().enumerate().take(15) {
        assert_eq!(s, 10000, "sample[{i}] should be unchanged");
    }
}

#[test]
fn test_fade_in_longer_than_audio_clamps() {
    let mut samples = vec![10000i16; 3];
    fade_in(&mut samples, 100);
    // Should not panic; fade is clamped to audio length
    assert_eq!(samples[0], 0);
}

#[test]
fn test_fade_out_longer_than_audio_clamps() {
    let mut samples = vec![10000i16; 3];
    fade_out(&mut samples, 100);
    // Should not panic; fade is clamped to audio length
    // First sample: i=0, gain = 1.0 (full volume)
    assert_eq!(samples[0], 10000);
    // Last sample should be reduced
    assert!(samples[2] < samples[0], "fade should reduce amplitude");
}

// =========================================================================
// concat_audio
// =========================================================================

#[test]
fn test_concat_audio_no_crossfade_total_length() {
    let a: Vec<i16> = vec![1, 2, 3, 4, 5];
    let b: Vec<i16> = vec![6, 7, 8];
    let c: Vec<i16> = vec![9, 10];
    let result = concat_audio(&[&a, &b, &c], 0);
    assert_eq!(result.len(), 5 + 3 + 2);
    assert_eq!(result, vec![1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
}

#[test]
fn test_concat_audio_with_crossfade_total_length() {
    let a: Vec<i16> = vec![1000; 20];
    let b: Vec<i16> = vec![1000; 20];
    let c: Vec<i16> = vec![1000; 20];
    let crossfade = 5;
    let result = concat_audio(&[&a, &b, &c], crossfade);
    // Total length = sum of chunks - (n_chunks - 1) * crossfade
    let expected_len = 20 + 20 + 20 - 2 * crossfade;
    assert_eq!(
        result.len(),
        expected_len,
        "with crossfade={crossfade} and 3 chunks of 20, expected {expected_len}"
    );
}

#[test]
fn test_concat_audio_single_chunk_returns_copy() {
    let a: Vec<i16> = vec![42, 43, 44];
    let result = concat_audio(&[&a], 10);
    assert_eq!(result, vec![42, 43, 44]);
}

#[test]
fn test_concat_audio_empty_chunks_list() {
    let result = concat_audio(&[], 0);
    assert!(result.is_empty());
}

#[test]
fn test_concat_audio_crossfade_equal_values_stable() {
    // Crossfading between chunks of the same constant value should
    // produce the same constant value throughout.
    let a: Vec<i16> = vec![8000; 20];
    let b: Vec<i16> = vec![8000; 20];
    let result = concat_audio(&[&a, &b], 5);
    for (i, &s) in result.iter().enumerate() {
        assert!(
            (s - 8000).abs() <= 1,
            "sample[{i}] should be ~8000 after crossfading equal values, got {s}"
        );
    }
}
