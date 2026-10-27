//! Speaker Encoder for Voice Cloning
//!
//! Loads a speaker encoder ONNX model and extracts speaker embeddings from
//! audio samples. The embedding can then be passed to
//! `SynthesisRequest::speaker_embedding` for voice cloning synthesis.
//!
//! Two feature front ends are available ([`SpeakerFrontEnd`]):
//!
//! - [`SpeakerFrontEnd::KaldiFbank`]: the recipe the public zs-v1 base's
//!   CAM++ encoder (192-dim) was verified with: kaiser_best resample to
//!   16 kHz, Kaldi fbank, mean subtraction, L2-normalized output. See
//!   [`crate::kaldi_fbank`].
//! - [`SpeakerFrontEnd::Mel`]: the legacy ECAPA-TDNN (256-dim) contract
//!   below.
//!
//! [`SpeakerEncoder::new`] picks the front end from the model's output
//! dimension; [`SpeakerEncoder::with_front_end`] sets it explicitly.
//!
//! # Legacy mel spectrogram parameters (unified across all runtimes):
//! - sample_rate: 16000
//! - n_fft: 400  (Kaldi frame_length=25ms at 16kHz = 400 samples)
//! - hop_length: 160
//! - n_mels: 80
//! - fmin: 20
//! - fmax: 7600

use std::borrow::Cow;
use std::path::Path;

use ort::session::Session;
use ort::session::builder::GraphOptimizationLevel;
use ort::value::Tensor;

use crate::error::PiperError;
use crate::kaldi_fbank;

/// Mel spectrogram parameters — must match across all runtimes.
const MEL_SAMPLE_RATE: u32 = 16000;
const MEL_N_FFT: usize = 400; // Kaldi frame_length=25ms at 16kHz = 400 samples
const MEL_HOP_LENGTH: usize = 160;
const MEL_N_MELS: usize = 80;
const MEL_FMIN: f32 = 20.0;
const MEL_FMAX: f32 = 7600.0;

/// Embedding dimension of the CAM++ encoder bundled with the public zs-v1
/// base (`campplus.onnx`).
pub const CAMPPLUS_EMBEDDING_DIM: usize = 192;

/// Feature front end that turns audio into the encoder's input.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpeakerFrontEnd {
    /// Legacy ECAPA-TDNN mel spectrogram (linear resample, Hann window,
    /// 400-point DFT, 20-7600 Hz). The output is returned as the model
    /// produced it.
    Mel,
    /// zs-v1 CAM++ recipe: kaiser_best resample, Kaldi fbank, mean
    /// subtraction. The output is L2-normalized.
    KaldiFbank,
}

impl SpeakerFrontEnd {
    /// Front end for an encoder whose embedding has `dim` values:
    /// [`SpeakerFrontEnd::KaldiFbank`] for CAM++ (192), otherwise
    /// [`SpeakerFrontEnd::Mel`].
    pub fn for_embedding_dim(dim: Option<usize>) -> Self {
        if dim == Some(CAMPPLUS_EMBEDDING_DIM) {
            Self::KaldiFbank
        } else {
            Self::Mel
        }
    }
}

/// Speaker encoder wrapping a speaker encoder ONNX model.
pub struct SpeakerEncoder {
    session: Session,
    front_end: SpeakerFrontEnd,
}

impl SpeakerEncoder {
    /// Load a speaker encoder model from the given ONNX file path.
    ///
    /// The front end follows the model's output dimension (see
    /// [`SpeakerFrontEnd::for_embedding_dim`]): the zs-v1 CAM++ encoder gets
    /// [`SpeakerFrontEnd::KaldiFbank`], anything else
    /// [`SpeakerFrontEnd::Mel`].
    pub fn new(model_path: &Path) -> Result<Self, PiperError> {
        // Load for the CAM++ front end first; the output dimension decides
        // whether the legacy optimization level is needed instead.
        let session = Self::load_session(model_path, SpeakerFrontEnd::KaldiFbank)?;
        let front_end = SpeakerFrontEnd::for_embedding_dim(output_dim(&session));
        tracing::info!("Speaker encoder front end: {front_end:?}");
        if front_end == SpeakerFrontEnd::KaldiFbank {
            return Ok(Self { session, front_end });
        }
        drop(session);
        Self::with_front_end(model_path, front_end)
    }

    /// Load a speaker encoder model with an explicit front end.
    pub fn with_front_end(
        model_path: &Path,
        front_end: SpeakerFrontEnd,
    ) -> Result<Self, PiperError> {
        let session = Self::load_session(model_path, front_end)?;
        Ok(Self { session, front_end })
    }

    /// The feature front end this encoder uses.
    pub fn front_end(&self) -> SpeakerFrontEnd {
        self.front_end
    }

    fn load_session(model_path: &Path, front_end: SpeakerFrontEnd) -> Result<Session, PiperError> {
        // ONNX Runtime 1.24-1.28 graph optimizations (even the basic level)
        // change CAM++ output (cosine 0.998 against the unoptimized and 1.29+
        // result). The bundled 1.31 is not affected, but the CAM++ session
        // runs unoptimized in every runtime so the embedding does not depend
        // on the ONNX Runtime version; it runs once per reference.
        let level = match front_end {
            SpeakerFrontEnd::KaldiFbank => GraphOptimizationLevel::Disable,
            SpeakerFrontEnd::Mel => GraphOptimizationLevel::Level3,
        };
        let session = crate::ort_env::session_builder()?
            .with_optimization_level(level)
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
        Ok(session)
    }

    /// Encode audio samples into a speaker embedding vector.
    ///
    /// `audio_samples` should be mono float32 PCM. If `sample_rate` is not
    /// 16000, the audio is resampled first (kaiser_best sinc for
    /// [`SpeakerFrontEnd::KaldiFbank`], linear interpolation for
    /// [`SpeakerFrontEnd::Mel`]).
    ///
    /// Returns the speaker embedding (192-d and L2-normalized for the zs-v1
    /// CAM++ encoder, 256-d for the legacy ECAPA-TDNN encoder).
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

        if sample_rate == 0 {
            return Err(PiperError::Inference(
                "speaker encoder: sample rate must be positive".to_string(),
            ));
        }
        let kaldi = self.front_end == SpeakerFrontEnd::KaldiFbank;

        // Resample to 16kHz if needed
        let resampled = if sample_rate == MEL_SAMPLE_RATE {
            audio_samples.to_vec()
        } else if kaldi {
            kaldi_fbank::resample_kaiser_best(audio_samples, sample_rate, MEL_SAMPLE_RATE)
        } else {
            resample_linear(audio_samples, sample_rate, MEL_SAMPLE_RATE)
        };

        // Compute features (frame-major [n_frames * n_mels])
        let mel = if kaldi {
            let mut feats = kaldi_fbank::kaldi_fbank(&resampled);
            kaldi_fbank::subtract_band_means(&mut feats);
            feats
        } else {
            compute_mel_spectrogram(&resampled)
        };
        let n_frames = mel.len() / MEL_N_MELS;

        if n_frames == 0 {
            return Err(PiperError::Inference(
                "speaker encoder: audio too short for mel spectrogram".to_string(),
            ));
        }

        // Create input tensor: [1, n_frames, n_mels] (frame-major, as expected by CAM++)
        let mel_tensor =
            Tensor::from_array(([1_usize, n_frames, MEL_N_MELS], mel.into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("speaker encoder mel tensor: {e}")))?;

        // Dynamically read input/output names before run() to avoid borrow conflicts
        let input_name = self
            .session
            .inputs()
            .iter()
            .next()
            .map(|i| i.name().to_string())
            .unwrap_or_else(|| "feats".to_string());
        let output_name = self
            .session
            .outputs()
            .iter()
            .next()
            .map(|o| o.name().to_string())
            .unwrap_or_else(|| "output".to_string());

        // Run inference
        let inputs: Vec<(Cow<str>, ort::session::SessionInputValue<'_>)> =
            vec![(input_name.into(), (&mel_tensor).into())];
        let outputs = self
            .session
            .run(inputs)
            .map_err(|e| PiperError::Inference(format!("speaker encoder inference: {e}")))?;

        // Extract embedding from output
        let (_shape, emb_data) = outputs[&output_name as &str]
            .try_extract_tensor::<f32>()
            .map_err(|e| PiperError::Inference(format!("speaker encoder output: {e}")))?;

        let embedding = if kaldi {
            l2_normalize(emb_data)?
        } else {
            emb_data.to_vec()
        };
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

/// The last dimension of the model's first output, when it is static.
fn output_dim(session: &Session) -> Option<usize> {
    let output = session.outputs().iter().next()?;
    match output.dtype() {
        ort::value::ValueType::Tensor { shape, .. } => match shape.last() {
            Some(&d) if d > 0 => Some(d as usize),
            _ => None,
        },
        _ => None,
    }
}

/// Scale an embedding to unit L2 norm.
fn l2_normalize(embedding: &[f32]) -> Result<Vec<f32>, PiperError> {
    let norm = embedding
        .iter()
        .map(|&v| f64::from(v) * f64::from(v))
        .sum::<f64>()
        .sqrt();
    if !norm.is_finite() || norm == 0.0 {
        return Err(PiperError::Inference(
            "speaker encoder returned a zero or non-finite embedding".to_string(),
        ));
    }
    Ok(embedding
        .iter()
        .map(|&v| (f64::from(v) / norm) as f32)
        .collect())
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
/// Returns a flattened [n_frames * n_mels] array in frame-major order
/// (frame 0 mel 0, frame 0 mel 1, ..., frame 1 mel 0, ...).
/// This matches the CAM++ expected input layout [batch, T, 80].
/// Per-band mean subtraction (CMVN) is applied after computing the log mel.
fn compute_mel_spectrogram(samples: &[f32]) -> Vec<f32> {
    let mel_filters = create_mel_filterbank();
    let window = hann_window(MEL_N_FFT);

    let n_frames = if samples.len() >= MEL_N_FFT {
        (samples.len() - MEL_N_FFT) / MEL_HOP_LENGTH + 1
    } else {
        0
    };

    let fft_bins = MEL_N_FFT / 2 + 1;
    // Frame-major layout: [n_frames * n_mels], index = frame_idx * MEL_N_MELS + mel_idx
    let mut mel_spec = vec![0.0f32; n_frames * MEL_N_MELS];

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

        // Apply mel filterbank and store in frame-major order
        for mel_idx in 0..MEL_N_MELS {
            let mut energy = 0.0f32;
            for k in 0..fft_bins {
                energy += mel_filters[mel_idx * fft_bins + k] * power_spec[k];
            }
            // Log mel: log(max(energy, 1e-10))
            mel_spec[frame_idx * MEL_N_MELS + mel_idx] = (energy.max(1e-10)).ln();
        }
    }

    // CMVN: subtract per-band mean from each mel band
    if n_frames > 0 {
        for mel_idx in 0..MEL_N_MELS {
            let mean: f32 = (0..n_frames)
                .map(|f| mel_spec[f * MEL_N_MELS + mel_idx])
                .sum::<f32>()
                / n_frames as f32;
            for frame_idx in 0..n_frames {
                mel_spec[frame_idx * MEL_N_MELS + mel_idx] -= mean;
            }
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
    fn test_front_end_follows_embedding_dim() {
        assert_eq!(
            SpeakerFrontEnd::for_embedding_dim(Some(192)),
            SpeakerFrontEnd::KaldiFbank
        );
        assert_eq!(
            SpeakerFrontEnd::for_embedding_dim(Some(256)),
            SpeakerFrontEnd::Mel
        );
        assert_eq!(
            SpeakerFrontEnd::for_embedding_dim(None),
            SpeakerFrontEnd::Mel
        );
    }

    #[test]
    fn test_l2_normalize() {
        let out = l2_normalize(&[3.0, 4.0]).unwrap();
        assert!((out[0] - 0.6).abs() < 1e-7 && (out[1] - 0.8).abs() < 1e-7);
        assert!(l2_normalize(&[0.0, 0.0]).is_err());
        assert!(l2_normalize(&[f32::NAN, 1.0]).is_err());
    }

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
