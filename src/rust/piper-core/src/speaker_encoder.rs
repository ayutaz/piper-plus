//! Speaker Encoder for Voice Cloning
//!
//! Loads an ECAPA-TDNN speaker encoder ONNX model and extracts speaker
//! embeddings from audio samples. The embedding can then be passed to
//! `SynthesisRequest::speaker_embedding` for voice cloning synthesis.
//!
//! # Mel spectrogram parameters (unified across all runtimes):
//! - sample_rate: 16000
//! - n_fft: 512
//! - hop_length: 160
//! - n_mels: 80
//! - fmin: 20
//! - fmax: 7600

use std::path::Path;

use ort::session::Session;
use ort::session::builder::GraphOptimizationLevel;
use ort::value::Tensor;

use crate::error::PiperError;

/// Mel spectrogram parameters — must match across all runtimes.
const MEL_SAMPLE_RATE: u32 = 16000;
const MEL_N_FFT: usize = 512;
const MEL_HOP_LENGTH: usize = 160;
const MEL_N_MELS: usize = 80;
const MEL_FMIN: f32 = 20.0;
const MEL_FMAX: f32 = 7600.0;

/// Speaker encoder wrapping an ECAPA-TDNN ONNX model.
pub struct SpeakerEncoder {
    session: Session,
}

impl SpeakerEncoder {
    /// Load a speaker encoder model from the given ONNX file path.
    pub fn new(model_path: &Path) -> Result<Self, PiperError> {
        let session = Session::builder()
            .map_err(|e| PiperError::ModelLoad(format!("speaker encoder session builder: {e}")))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| PiperError::ModelLoad(format!("speaker encoder opt level: {e}")))?
            .with_intra_threads(2)
            .map_err(|e| PiperError::ModelLoad(format!("speaker encoder threads: {e}")))?
            .commit_from_file(model_path)
            .map_err(|e| {
                PiperError::ModelLoad(format!(
                    "speaker encoder load {}: {e}",
                    model_path.display()
                ))
            })?;

        tracing::info!("Speaker encoder loaded: {}", model_path.display());
        Ok(Self { session })
    }

    /// Encode audio samples into a speaker embedding vector.
    ///
    /// `audio_samples` should be mono float32 PCM. If `sample_rate` is not
    /// 16000, the audio will be resampled using linear interpolation.
    ///
    /// Returns a Vec<f32> containing the speaker embedding (typically 256-d).
    pub fn encode(
        &mut self,
        audio_samples: &[f32],
        sample_rate: u32,
    ) -> Result<Vec<f32>, PiperError> {
        if audio_samples.is_empty() {
            return Err(PiperError::Inference(
                "speaker encoder: empty audio input".to_string(),
            ));
        }

        // Resample to 16kHz if needed
        let resampled = if sample_rate != MEL_SAMPLE_RATE {
            resample_linear(audio_samples, sample_rate, MEL_SAMPLE_RATE)
        } else {
            audio_samples.to_vec()
        };

        // Compute mel spectrogram
        let mel = compute_mel_spectrogram(&resampled);
        let n_frames = mel.len() / MEL_N_MELS;

        if n_frames == 0 {
            return Err(PiperError::Inference(
                "speaker encoder: audio too short for mel spectrogram".to_string(),
            ));
        }

        // Create input tensor: [1, n_mels, n_frames]
        let mel_tensor =
            Tensor::from_array(([1_usize, MEL_N_MELS, n_frames], mel.into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("speaker encoder mel tensor: {e}")))?;

        // Run inference
        let inputs: Vec<(std::borrow::Cow<str>, ort::session::SessionInputValue<'_>)> =
            vec![("input".into(), (&mel_tensor).into())];
        let outputs = self
            .session
            .run(inputs)
            .map_err(|e| PiperError::Inference(format!("speaker encoder inference: {e}")))?;

        // Extract embedding from output
        let (_shape, emb_data) = outputs[0]
            .try_extract_tensor::<f32>()
            .map_err(|e| PiperError::Inference(format!("speaker encoder output: {e}")))?;

        let embedding = emb_data.to_vec();
        tracing::debug!(
            "Speaker embedding extracted: {} dimensions",
            embedding.len()
        );

        Ok(embedding)
    }

    /// Encode audio from a WAV file.
    pub fn encode_file(&mut self, path: &Path) -> Result<Vec<f32>, PiperError> {
        let (samples, sample_rate) = read_wav_file(path)?;
        self.encode(&samples, sample_rate)
    }
}

/// Read a WAV file and return (samples_f32, sample_rate).
fn read_wav_file(path: &Path) -> Result<(Vec<f32>, u32), PiperError> {
    use std::fs::File;
    use std::io::BufReader;

    let file = File::open(path).map_err(PiperError::AudioOutput)?;
    let reader = BufReader::new(file);
    let wav_reader = hound::WavReader::new(reader)
        .map_err(|e| PiperError::Inference(format!("WAV read error {}: {e}", path.display())))?;

    let spec = wav_reader.spec();
    let sample_rate = spec.sample_rate;

    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => wav_reader
            .into_samples::<f32>()
            .map(|s| s.unwrap_or(0.0))
            .collect(),
        hound::SampleFormat::Int => {
            let max_val = (1i64 << (spec.bits_per_sample - 1)) as f32;
            wav_reader
                .into_samples::<i32>()
                .map(|s| s.unwrap_or(0) as f32 / max_val)
                .collect()
        }
    };

    // Convert to mono if stereo
    let mono = if spec.channels > 1 {
        let ch = spec.channels as usize;
        samples
            .chunks(ch)
            .map(|frame| frame.iter().sum::<f32>() / ch as f32)
            .collect()
    } else {
        samples
    };

    Ok((mono, sample_rate))
}

/// Linear interpolation resampling.
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

/// Compute a log mel spectrogram from audio samples at 16kHz.
///
/// Returns a flattened [n_mels * n_frames] array in row-major order
/// (mel bin 0 frame 0, mel bin 0 frame 1, ..., mel bin 1 frame 0, ...).
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

        // Apply window and compute power spectrum via DFT
        let mut power_spec = vec![0.0f32; fft_bins];
        for (k, power_spec_k) in power_spec.iter_mut().enumerate() {
            let mut real = 0.0f32;
            let mut imag = 0.0f32;
            let freq = -2.0 * std::f32::consts::PI * k as f32 / MEL_N_FFT as f32;
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
            *power_spec_k = real * real + imag * imag;
        }

        // Apply mel filterbank
        for mel_idx in 0..MEL_N_MELS {
            let mut energy = 0.0f32;
            for k in 0..fft_bins {
                energy += mel_filters[mel_idx * fft_bins + k] * power_spec[k];
            }
            // Log mel: log(max(energy, 1e-10))
            mel_spec[mel_idx * n_frames + frame_idx] = (energy.max(1e-10)).ln();
        }
    }

    mel_spec
}

/// Create a Hann window of the given length.
fn hann_window(length: usize) -> Vec<f32> {
    (0..length)
        .map(|n| 0.5 * (1.0 - (2.0 * std::f32::consts::PI * n as f32 / length as f32).cos()))
        .collect()
}

/// Create a mel filterbank matrix [n_mels x fft_bins].
fn create_mel_filterbank() -> Vec<f32> {
    let fft_bins = MEL_N_FFT / 2 + 1;
    let mut filterbank = vec![0.0f32; MEL_N_MELS * fft_bins];

    let mel_fmin = hz_to_mel(MEL_FMIN);
    let mel_fmax = hz_to_mel(MEL_FMAX);

    // Create n_mels + 2 equally spaced points in mel scale
    let mel_points: Vec<f32> = (0..=MEL_N_MELS + 1)
        .map(|i| mel_fmin + (mel_fmax - mel_fmin) * i as f32 / (MEL_N_MELS + 1) as f32)
        .collect();

    let hz_points: Vec<f32> = mel_points.iter().map(|&m| mel_to_hz(m)).collect();
    let bin_points: Vec<f32> = hz_points
        .iter()
        .map(|&hz| hz * MEL_N_FFT as f32 / MEL_SAMPLE_RATE as f32)
        .collect();

    for m in 0..MEL_N_MELS {
        // Convert to integer bin indices (matching Python's np.floor().astype(int))
        let left = bin_points[m].floor() as usize;
        let mut center = bin_points[m + 1].floor() as usize;
        let mut right = bin_points[m + 2].floor() as usize;

        // Edge case: if the triangle collapses to a single bin, widen it to
        // guarantee a non-zero response (matches Python reference).
        if left == center && center == right {
            center = (center + 1).min(fft_bins - 1);
            right = (right + 2).min(fft_bins - 1);
        } else if left == center {
            center = (center + 1).min(fft_bins - 1);
        }
        if center == right {
            right = (right + 1).min(fft_bins - 1);
        }

        // Rising slope
        for k in left..center {
            if center > left {
                filterbank[m * fft_bins + k] = (k - left) as f32 / (center - left) as f32;
            }
        }

        // Falling slope
        for k in center..right {
            if right > center {
                filterbank[m * fft_bins + k] = (right - k) as f32 / (right - center) as f32;
            }
        }

        // Ensure center bin always has weight >= 1.0
        if center < fft_bins {
            filterbank[m * fft_bins + center] = filterbank[m * fft_bins + center].max(1.0);
        }
    }

    filterbank
}

fn hz_to_mel(hz: f32) -> f32 {
    2595.0 * (1.0 + hz / 700.0).log10()
}

fn mel_to_hz(mel: f32) -> f32 {
    700.0 * (10.0_f32.powf(mel / 2595.0) - 1.0)
}

#[cfg(test)]
mod speaker_encoder_tests {
    use super::*;

    #[test]
    fn test_resample_linear_same_rate() {
        let samples = vec![1.0, 2.0, 3.0, 4.0];
        let result = resample_linear(&samples, 16000, 16000);
        assert_eq!(result, samples);
    }

    #[test]
    fn test_resample_linear_downsample() {
        let samples: Vec<f32> = (0..1000).map(|i| (i as f32).sin()).collect();
        let result = resample_linear(&samples, 48000, 16000);
        // 48kHz -> 16kHz = 1/3 ratio
        assert!((result.len() as f32 - 334.0).abs() < 2.0);
    }

    #[test]
    fn test_resample_linear_empty() {
        let result = resample_linear(&[], 48000, 16000);
        assert!(result.is_empty());
    }

    #[test]
    fn test_hann_window_endpoints() {
        let w = hann_window(512);
        assert_eq!(w.len(), 512);
        assert!(w[0].abs() < 1e-6); // First sample near zero
    }

    #[test]
    fn test_hz_to_mel_roundtrip() {
        let hz = 1000.0;
        let mel = hz_to_mel(hz);
        let hz_back = mel_to_hz(mel);
        assert!((hz - hz_back).abs() < 0.01);
    }

    #[test]
    fn test_mel_filterbank_shape() {
        let fb = create_mel_filterbank();
        let fft_bins = MEL_N_FFT / 2 + 1;
        assert_eq!(fb.len(), MEL_N_MELS * fft_bins);
    }

    #[test]
    fn test_compute_mel_spectrogram_short_audio() {
        // Audio shorter than n_fft should produce empty spectrogram
        let short_audio = vec![0.0f32; 100];
        let mel = compute_mel_spectrogram(&short_audio);
        assert!(mel.is_empty());
    }

    #[test]
    fn test_compute_mel_spectrogram_basic() {
        // Generate 1 second of 16kHz audio (sine wave)
        let n_samples = 16000;
        let audio: Vec<f32> = (0..n_samples)
            .map(|i| (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 16000.0).sin())
            .collect();
        let mel = compute_mel_spectrogram(&audio);
        let n_frames = (n_samples - MEL_N_FFT) / MEL_HOP_LENGTH + 1;
        assert_eq!(mel.len(), MEL_N_MELS * n_frames);
        // All values should be finite
        assert!(mel.iter().all(|v| v.is_finite()));
    }
}
