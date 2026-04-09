//! WASM-compatible synthesis API
//!
//! Provides an API that works without filesystem access, suitable for
//! WebAssembly (wasm32) targets. Model and config data are passed as byte slices
//! instead of file paths.
//!
//! This module is available on all platforms but is designed primarily for WASM.
//! On native platforms, prefer `PiperVoice::load()` for convenience.

use std::borrow::Cow;
use std::time::Instant;

use ort::session::Session;
use ort::value::Tensor;

use crate::audio::audio_float_to_int16;
use crate::config::VoiceConfig;
use crate::error::PiperError;

/// WASM-friendly synthesis result (no file I/O)
#[derive(Debug, Clone)]
pub struct WasmSynthesisResult {
    /// Raw PCM audio samples (16-bit signed, mono)
    pub audio_samples: Vec<i16>,
    /// Audio sample rate (e.g., 22050)
    pub sample_rate: u32,
    /// Inference time in seconds
    pub infer_seconds: f64,
    /// Audio duration in seconds
    pub audio_seconds: f64,
}

impl WasmSynthesisResult {
    /// Real-time factor (infer_seconds / audio_seconds).
    /// Below 1.0 means faster than real-time.
    pub fn real_time_factor(&self) -> f64 {
        if self.audio_seconds > 0.0 {
            self.infer_seconds / self.audio_seconds
        } else {
            0.0
        }
    }
}

/// Model capabilities detected from ONNX input/output node names.
#[derive(Debug, Clone)]
pub struct WasmModelCapabilities {
    pub has_sid: bool,
    pub has_lid: bool,
    pub has_prosody: bool,
    pub has_duration_output: bool,
}

/// WASM-compatible voice synthesizer.
/// Loads model from bytes rather than file paths.
#[derive(Debug)]
pub struct WasmVoice {
    config: VoiceConfig,
    session: Session,
    capabilities: WasmModelCapabilities,
}

impl WasmVoice {
    /// Load from in-memory model and config data.
    ///
    /// # Arguments
    /// * `model_bytes` - ONNX model file contents
    /// * `config_json` - config.json file contents as string
    pub fn load_from_bytes(model_bytes: &[u8], config_json: &str) -> Result<Self, PiperError> {
        let config: VoiceConfig = parse_config(config_json)?;

        let session = Session::builder()
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
            .commit_from_memory(model_bytes)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

        // Detect capabilities from ONNX input/output node names
        let input_names: Vec<String> = session
            .inputs()
            .iter()
            .map(|i| i.name().to_string())
            .collect();
        let output_names: Vec<String> = session
            .outputs()
            .iter()
            .map(|o| o.name().to_string())
            .collect();

        let has_input = |name: &str| input_names.iter().any(|n| n == name);
        let has_output = |name: &str| output_names.iter().any(|n| n == name);

        let capabilities = WasmModelCapabilities {
            has_sid: has_input("sid"),
            has_lid: has_input("lid"),
            has_prosody: has_input("prosody_features"),
            has_duration_output: has_output("durations"),
        };

        tracing::info!(
            "WasmVoice loaded: inputs={:?}, outputs={:?}",
            input_names,
            output_names,
        );
        tracing::info!(
            "Capabilities: sid={}, lid={}, prosody={}, durations={}",
            capabilities.has_sid,
            capabilities.has_lid,
            capabilities.has_prosody,
            capabilities.has_duration_output,
        );

        Ok(Self {
            config,
            session,
            capabilities,
        })
    }

    /// Synthesize from pre-computed phoneme IDs (no G2P needed).
    /// This is the primary API for WASM since G2P may not be available.
    pub fn synthesize_ids(
        &mut self,
        phoneme_ids: &[i64],
        speaker_id: Option<i64>,
        language_id: Option<i64>,
        noise_scale: f32,
        length_scale: f32,
        noise_w: f32,
    ) -> Result<WasmSynthesisResult, PiperError> {
        let phoneme_len = phoneme_ids.len();
        if phoneme_len == 0 {
            return Err(PiperError::Inference("empty phoneme_ids".to_string()));
        }

        // --- Build input tensors ---

        // 1. input: int64 [1, phoneme_len]
        let input_tensor = Tensor::from_array((
            [1_usize, phoneme_len],
            phoneme_ids.to_vec().into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("input tensor: {e}")))?;

        // 2. input_lengths: int64 [1]
        let lengths_tensor =
            Tensor::from_array(([1_usize], vec![phoneme_len as i64].into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("input_lengths tensor: {e}")))?;

        // 3. scales: float32 [3]
        let scales_tensor = Tensor::from_array((
            [3_usize],
            vec![noise_scale, length_scale, noise_w].into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("scales tensor: {e}")))?;

        // 4. sid: int64 [1] (conditional)
        let sid_val = speaker_id.unwrap_or(0);
        let sid_tensor = if self.capabilities.has_sid {
            Some(
                Tensor::from_array(([1_usize], vec![sid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("sid tensor: {e}")))?,
            )
        } else {
            None
        };

        // 5. lid: int64 [1] (conditional)
        let lid_val = language_id.unwrap_or(0);
        let lid_tensor = if self.capabilities.has_lid {
            Some(
                Tensor::from_array(([1_usize], vec![lid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("lid tensor: {e}")))?,
            )
        } else {
            None
        };

        // 6. prosody_features: int64 [1, phoneme_len, 3] (conditional, zero-filled)
        let prosody_tensor = if self.capabilities.has_prosody {
            let flat = vec![0i64; phoneme_len * 3];
            Some(
                Tensor::from_array(([1_usize, phoneme_len, 3], flat.into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("prosody tensor: {e}")))?,
            )
        } else {
            None
        };

        // Build input map
        let mut inputs: Vec<(Cow<str>, ort::session::SessionInputValue<'_>)> =
            Vec::with_capacity(6);

        inputs.push(("input".into(), (&input_tensor).into()));
        inputs.push(("input_lengths".into(), (&lengths_tensor).into()));
        inputs.push(("scales".into(), (&scales_tensor).into()));

        if let Some(ref t) = sid_tensor {
            inputs.push(("sid".into(), t.into()));
        }
        if let Some(ref t) = lid_tensor {
            inputs.push(("lid".into(), t.into()));
        }
        if let Some(ref t) = prosody_tensor {
            inputs.push(("prosody_features".into(), t.into()));
        }

        // --- Run inference ---
        let start = Instant::now();

        let outputs = self
            .session
            .run(inputs)
            .map_err(|e| PiperError::Inference(e.to_string()))?;

        let infer_seconds = start.elapsed().as_secs_f64();

        // --- Extract output ---
        // output: float32 [1, 1, audio_samples]
        let (_shape, audio_slice) = outputs["output"]
            .try_extract_tensor::<f32>()
            .map_err(|e| PiperError::Inference(format!("extract output: {e}")))?;

        let audio_f32: Vec<f32> = audio_slice.to_vec();

        // float32 -> int16 peak normalization
        let audio_i16 = audio_float_to_int16(&audio_f32);
        let sample_rate = self.config.audio.sample_rate;
        let audio_seconds = audio_i16.len() as f64 / sample_rate as f64;

        Ok(WasmSynthesisResult {
            audio_samples: audio_i16,
            sample_rate,
            infer_seconds,
            audio_seconds,
        })
    }

    /// Get the loaded config
    pub fn config(&self) -> &VoiceConfig {
        &self.config
    }

    /// Whether the model accepts a speaker ID input
    pub fn has_speaker_id(&self) -> bool {
        self.capabilities.has_sid
    }

    /// Whether the model accepts a language ID input
    pub fn has_language_id(&self) -> bool {
        self.capabilities.has_lid
    }

    /// Whether the model accepts prosody features input
    pub fn has_prosody(&self) -> bool {
        self.capabilities.has_prosody
    }

    /// Get model capabilities
    pub fn capabilities(&self) -> &WasmModelCapabilities {
        &self.capabilities
    }
}

/// Convert i16 PCM samples to f32 normalized audio (-1.0 to 1.0)
pub fn samples_i16_to_f32(samples: &[i16]) -> Vec<f32> {
    samples.iter().map(|&s| s as f32 / 32768.0).collect()
}

/// Convert f32 audio to WAV bytes (in-memory, no filesystem)
///
/// Writes a complete WAV file (RIFF header + fmt chunk + data chunk) into a `Vec<u8>`.
/// The format is 16-bit signed PCM, mono, at the given sample rate.
/// Useful for creating a downloadable Blob in WASM environments.
pub fn samples_to_wav_bytes(samples: &[i16], sample_rate: u32) -> Vec<u8> {
    let data_size = (samples.len() * 2) as u32;
    let file_size = data_size + 36;

    // Total WAV size: 44-byte header + data
    let total_size = 44 + samples.len() * 2;
    let mut buf = Vec::with_capacity(total_size);

    // RIFF header (12 bytes)
    buf.extend_from_slice(b"RIFF");
    buf.extend_from_slice(&file_size.to_le_bytes());
    buf.extend_from_slice(b"WAVE");

    // fmt chunk (24 bytes)
    buf.extend_from_slice(b"fmt ");
    buf.extend_from_slice(&16u32.to_le_bytes()); // chunk size
    buf.extend_from_slice(&1u16.to_le_bytes()); // PCM format
    buf.extend_from_slice(&1u16.to_le_bytes()); // mono
    buf.extend_from_slice(&sample_rate.to_le_bytes()); // sample rate
    buf.extend_from_slice(&(sample_rate * 2).to_le_bytes()); // byte rate (sample_rate * channels * bytes_per_sample)
    buf.extend_from_slice(&2u16.to_le_bytes()); // block align (channels * bytes_per_sample)
    buf.extend_from_slice(&16u16.to_le_bytes()); // bits per sample

    // data chunk (8 bytes header + sample data)
    buf.extend_from_slice(b"data");
    buf.extend_from_slice(&data_size.to_le_bytes());
    buf.extend_from_slice(
        &samples
            .iter()
            .flat_map(|s| s.to_le_bytes())
            .collect::<Vec<u8>>(),
    );

    buf
}

/// Parse config JSON string into VoiceConfig
pub fn parse_config(config_json: &str) -> Result<VoiceConfig, PiperError> {
    let config: VoiceConfig = serde_json::from_str(config_json)?;
    Ok(config)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // 1. parse_config: valid JSON
    // -----------------------------------------------------------------------
    #[test]
    fn test_parse_config_valid_minimal() {
        let json = r#"{"phoneme_id_map": {"a": [1]}, "audio": {"sample_rate": 22050}}"#;
        let config = parse_config(json).unwrap();
        assert_eq!(config.audio.sample_rate, 22050);
        assert_eq!(config.num_speakers, 1);
        assert_eq!(config.num_languages, 1);
        assert!(!config.is_multilingual());
    }

    #[test]
    fn test_parse_config_valid_multilingual() {
        let json = r#"{
            "num_speakers": 571,
            "num_languages": 6,
            "phoneme_type": "multilingual",
            "phoneme_id_map": {"^": [1], "_": [0]},
            "language_id_map": {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5},
            "audio": {"sample_rate": 22050}
        }"#;
        let config = parse_config(json).unwrap();
        assert_eq!(config.num_speakers, 571);
        assert_eq!(config.num_languages, 6);
        assert!(config.is_multilingual());
        assert!(config.needs_lid());
        assert_eq!(config.language_id_map.len(), 6);
        assert_eq!(config.language_id_map.get("ja"), Some(&0));
        assert_eq!(config.language_id_map.get("pt"), Some(&5));
    }

    #[test]
    fn test_parse_config_valid_defaults() {
        // Empty JSON object should use all defaults
        let json = r#"{}"#;
        let config = parse_config(json).unwrap();
        assert_eq!(config.audio.sample_rate, 22050);
        assert_eq!(config.num_speakers, 1);
        assert_eq!(config.num_languages, 1);
        assert!(config.phoneme_id_map.is_empty());
    }

    // -----------------------------------------------------------------------
    // 2. parse_config: invalid JSON
    // -----------------------------------------------------------------------
    #[test]
    fn test_parse_config_invalid_json() {
        let json = r#"{ not valid json }"#;
        let result = parse_config(json);
        assert!(result.is_err());
        match result.unwrap_err() {
            PiperError::JsonParse(_) => {} // expected
            other => panic!("expected JsonParse, got: {other:?}"),
        }
    }

    #[test]
    fn test_parse_config_empty_string() {
        let result = parse_config("");
        assert!(result.is_err());
        match result.unwrap_err() {
            PiperError::JsonParse(_) => {} // expected
            other => panic!("expected JsonParse, got: {other:?}"),
        }
    }

    #[test]
    fn test_parse_config_wrong_type() {
        // num_speakers as string instead of number
        let json = r#"{"num_speakers": "not_a_number"}"#;
        let result = parse_config(json);
        assert!(result.is_err());
        match result.unwrap_err() {
            PiperError::JsonParse(_) => {} // expected
            other => panic!("expected JsonParse, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // 3. samples_i16_to_f32: conversion accuracy
    // -----------------------------------------------------------------------
    #[test]
    fn test_samples_i16_to_f32_basic() {
        let samples: Vec<i16> = vec![0, 32767, -32768, 16384, -16384];
        let result = samples_i16_to_f32(&samples);
        assert_eq!(result.len(), 5);
        // 0 -> 0.0
        assert!((result[0] - 0.0).abs() < 1e-6);
        // 32767 -> 32767/32768 ~ 0.999969
        assert!((result[1] - 32767.0 / 32768.0).abs() < 1e-4);
        // -32768 -> -32768/32768 = -1.0
        assert!((result[2] - (-1.0)).abs() < 1e-6);
        // 16384 -> 0.5
        assert!((result[3] - 0.5).abs() < 1e-4);
        // -16384 -> -0.5
        assert!((result[4] - (-0.5)).abs() < 1e-4);
    }

    #[test]
    fn test_samples_i16_to_f32_empty() {
        let result = samples_i16_to_f32(&[]);
        assert!(result.is_empty());
    }

    #[test]
    fn test_samples_i16_to_f32_silence() {
        let samples = vec![0i16; 100];
        let result = samples_i16_to_f32(&samples);
        assert_eq!(result.len(), 100);
        assert!(result.iter().all(|&x| x == 0.0));
    }

    // -----------------------------------------------------------------------
    // 4. samples_to_wav_bytes: format validation
    // -----------------------------------------------------------------------
    #[test]
    fn test_wav_bytes_riff_header() {
        let samples = vec![0i16; 10];
        let wav = samples_to_wav_bytes(&samples, 22050);

        // Check RIFF magic
        assert_eq!(&wav[0..4], b"RIFF");

        // Check file size field (total - 8)
        let file_size = u32::from_le_bytes([wav[4], wav[5], wav[6], wav[7]]);
        assert_eq!(file_size, (wav.len() - 8) as u32);

        // Check WAVE magic
        assert_eq!(&wav[8..12], b"WAVE");
    }

    #[test]
    fn test_wav_bytes_fmt_chunk() {
        let samples = vec![100i16, -100, 200, -200];
        let wav = samples_to_wav_bytes(&samples, 44100);

        // fmt chunk starts at offset 12
        assert_eq!(&wav[12..16], b"fmt ");

        // fmt chunk size = 16
        let fmt_size = u32::from_le_bytes([wav[16], wav[17], wav[18], wav[19]]);
        assert_eq!(fmt_size, 16);

        // Audio format: PCM = 1
        let audio_format = u16::from_le_bytes([wav[20], wav[21]]);
        assert_eq!(audio_format, 1);

        // Channels: mono = 1
        let channels = u16::from_le_bytes([wav[22], wav[23]]);
        assert_eq!(channels, 1);

        // Sample rate
        let sample_rate = u32::from_le_bytes([wav[24], wav[25], wav[26], wav[27]]);
        assert_eq!(sample_rate, 44100);

        // Byte rate = sample_rate * channels * bytes_per_sample
        let byte_rate = u32::from_le_bytes([wav[28], wav[29], wav[30], wav[31]]);
        assert_eq!(byte_rate, 44100 * 2);

        // Block align = channels * bytes_per_sample
        let block_align = u16::from_le_bytes([wav[32], wav[33]]);
        assert_eq!(block_align, 2);

        // Bits per sample
        let bits_per_sample = u16::from_le_bytes([wav[34], wav[35]]);
        assert_eq!(bits_per_sample, 16);
    }

    #[test]
    fn test_wav_bytes_data_chunk() {
        let samples: Vec<i16> = vec![1000, -2000, 3000];
        let wav = samples_to_wav_bytes(&samples, 22050);

        // data chunk starts at offset 36
        assert_eq!(&wav[36..40], b"data");

        // data size = samples.len() * 2
        let data_size = u32::from_le_bytes([wav[40], wav[41], wav[42], wav[43]]);
        assert_eq!(data_size, 6); // 3 samples * 2 bytes each

        // Verify sample data (little-endian i16)
        let s0 = i16::from_le_bytes([wav[44], wav[45]]);
        let s1 = i16::from_le_bytes([wav[46], wav[47]]);
        let s2 = i16::from_le_bytes([wav[48], wav[49]]);
        assert_eq!(s0, 1000);
        assert_eq!(s1, -2000);
        assert_eq!(s2, 3000);
    }

    #[test]
    fn test_wav_bytes_total_length() {
        let samples = vec![0i16; 100];
        let wav = samples_to_wav_bytes(&samples, 22050);
        // Total = 44 header bytes + 100 samples * 2 bytes = 244
        assert_eq!(wav.len(), 244);
    }

    #[test]
    fn test_wav_bytes_empty_samples() {
        let wav = samples_to_wav_bytes(&[], 22050);
        // Total = 44 header bytes + 0 data bytes
        assert_eq!(wav.len(), 44);

        // RIFF header still valid
        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(&wav[8..12], b"WAVE");

        // data size should be 0
        let data_size = u32::from_le_bytes([wav[40], wav[41], wav[42], wav[43]]);
        assert_eq!(data_size, 0);
    }

    // -----------------------------------------------------------------------
    // 5. WasmSynthesisResult construction and methods
    // -----------------------------------------------------------------------
    #[test]
    fn test_wasm_synthesis_result_construction() {
        let result = WasmSynthesisResult {
            audio_samples: vec![100i16, -200, 300],
            sample_rate: 22050,
            infer_seconds: 0.05,
            audio_seconds: 0.5,
        };
        assert_eq!(result.audio_samples.len(), 3);
        assert_eq!(result.sample_rate, 22050);
        assert!((result.infer_seconds - 0.05).abs() < 1e-9);
        assert!((result.audio_seconds - 0.5).abs() < 1e-9);
    }

    #[test]
    fn test_wasm_synthesis_result_rtf() {
        let result = WasmSynthesisResult {
            audio_samples: vec![0i16; 22050],
            sample_rate: 22050,
            infer_seconds: 0.5,
            audio_seconds: 1.0,
        };
        assert!((result.real_time_factor() - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_wasm_synthesis_result_rtf_zero_audio() {
        let result = WasmSynthesisResult {
            audio_samples: Vec::new(),
            sample_rate: 22050,
            infer_seconds: 0.1,
            audio_seconds: 0.0,
        };
        assert!((result.real_time_factor()).abs() < 1e-6);
    }

    #[test]
    fn test_wasm_synthesis_result_clone() {
        let result = WasmSynthesisResult {
            audio_samples: vec![1, 2, 3],
            sample_rate: 44100,
            infer_seconds: 0.01,
            audio_seconds: 0.1,
        };
        let cloned = result.clone();
        assert_eq!(cloned.audio_samples, result.audio_samples);
        assert_eq!(cloned.sample_rate, result.sample_rate);
    }

    // -----------------------------------------------------------------------
    // 6. WasmModelCapabilities
    // -----------------------------------------------------------------------
    #[test]
    fn test_wasm_model_capabilities() {
        let caps = WasmModelCapabilities {
            has_sid: true,
            has_lid: true,
            has_prosody: false,
            has_duration_output: false,
        };
        assert!(caps.has_sid);
        assert!(caps.has_lid);
        assert!(!caps.has_prosody);
        assert!(!caps.has_duration_output);

        // Clone works
        let cloned = caps.clone();
        assert_eq!(cloned.has_sid, caps.has_sid);
        assert_eq!(cloned.has_lid, caps.has_lid);
    }

    // -----------------------------------------------------------------------
    // 7. WAV roundtrip: i16 -> wav bytes -> verify sample data
    // -----------------------------------------------------------------------
    #[test]
    fn test_wav_roundtrip_samples() {
        let original: Vec<i16> = vec![i16::MIN, -1000, 0, 1000, i16::MAX];
        let wav = samples_to_wav_bytes(&original, 16000);

        // Extract samples back from WAV bytes (data starts at offset 44)
        let mut recovered = Vec::new();
        for i in 0..original.len() {
            let offset = 44 + i * 2;
            let sample = i16::from_le_bytes([wav[offset], wav[offset + 1]]);
            recovered.push(sample);
        }
        assert_eq!(recovered, original);
    }

    // -----------------------------------------------------------------------
    // 8. samples_i16_to_f32 range boundaries
    // -----------------------------------------------------------------------
    #[test]
    fn test_samples_i16_to_f32_range() {
        let samples = vec![i16::MAX, i16::MIN, 0];
        let result = samples_i16_to_f32(&samples);

        // i16::MAX (32767) / 32768.0 should be just under 1.0
        assert!(result[0] > 0.999 && result[0] < 1.0);
        // i16::MIN (-32768) / 32768.0 should be exactly -1.0
        assert!((result[1] - (-1.0)).abs() < 1e-6);
        // 0 / 32768.0 should be exactly 0.0
        assert!((result[2] - 0.0).abs() < 1e-6);
    }

    // -----------------------------------------------------------------------
    // 9. WAV bytes with different sample rates
    // -----------------------------------------------------------------------
    #[test]
    fn test_wav_bytes_various_sample_rates() {
        for &rate in &[8000u32, 16000, 22050, 44100, 48000] {
            let wav = samples_to_wav_bytes(&[0i16; 10], rate);
            let sr = u32::from_le_bytes([wav[24], wav[25], wav[26], wav[27]]);
            assert_eq!(sr, rate, "sample rate mismatch for {rate}");
            let br = u32::from_le_bytes([wav[28], wav[29], wav[30], wav[31]]);
            assert_eq!(br, rate * 2, "byte rate mismatch for {rate}");
        }
    }

    // -----------------------------------------------------------------------
    // 10. WasmVoice::load_from_bytes with invalid model bytes
    // -----------------------------------------------------------------------
    #[test]
    fn test_load_from_bytes_invalid_model() {
        let config = r#"{
            "audio": {"sample_rate": 22050},
            "num_speakers": 1,
            "num_symbols": 10,
            "phoneme_type": "openjtalk",
            "phoneme_id_map": {},
            "num_languages": 1,
            "language_id_map": {},
            "speaker_id_map": {}
        }"#;
        let result = WasmVoice::load_from_bytes(b"not a model", config);
        assert!(result.is_err());
        match result.err().unwrap() {
            PiperError::ModelLoad(msg) => {
                assert!(!msg.is_empty(), "error message should be non-empty");
            }
            other => panic!("expected ModelLoad, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // 11. WasmVoice::load_from_bytes with invalid config JSON
    // -----------------------------------------------------------------------
    #[test]
    fn test_load_from_bytes_invalid_config() {
        let result = WasmVoice::load_from_bytes(b"fake", "not json");
        assert!(result.is_err());
        match result.err().unwrap() {
            PiperError::JsonParse(_) => {} // config parse fails before model load
            other => panic!("expected JsonParse, got: {other:?}"),
        }
    }

    #[test]
    fn test_load_from_bytes_empty_config() {
        // Empty string is not valid JSON
        let result = WasmVoice::load_from_bytes(b"fake model data", "");
        assert!(result.is_err());
        match result.err().unwrap() {
            PiperError::JsonParse(_) => {}
            other => panic!("expected JsonParse, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // 12. WasmSynthesisResult edge cases
    // -----------------------------------------------------------------------
    #[test]
    fn test_wasm_synthesis_result_large_audio() {
        // Simulate a large audio output (~60 seconds at 22050 Hz)
        let num_samples = 22050 * 60;
        let result = WasmSynthesisResult {
            audio_samples: vec![0i16; num_samples],
            sample_rate: 22050,
            infer_seconds: 2.5,
            audio_seconds: num_samples as f64 / 22050.0,
        };
        assert_eq!(result.audio_samples.len(), num_samples);
        assert!((result.audio_seconds - 60.0).abs() < 1e-6);
        // RTF < 1 means faster than real-time
        assert!(result.real_time_factor() < 1.0);
    }

    #[test]
    fn test_wasm_synthesis_result_negative_infer_seconds() {
        // Negative infer_seconds is unusual but should not panic
        let result = WasmSynthesisResult {
            audio_samples: vec![1, 2, 3],
            sample_rate: 22050,
            infer_seconds: -0.5,
            audio_seconds: 1.0,
        };
        // RTF will be negative, which is meaningless but should not crash
        let rtf = result.real_time_factor();
        assert!(rtf < 0.0);
    }

    // -----------------------------------------------------------------------
    // 13. samples_i16_to_f32 boundary values
    // -----------------------------------------------------------------------
    #[test]
    fn test_samples_i16_to_f32_boundaries() {
        let samples = vec![i16::MIN, i16::MAX, 0];
        let f32s = samples_i16_to_f32(&samples);
        // i16::MIN (-32768) / 32768.0 = exactly -1.0
        assert!(f32s[0] <= -1.0 + 0.001);
        // i16::MAX (32767) / 32768.0 ~ 0.99997
        assert!(f32s[1] >= 1.0 - 0.001);
        // 0 / 32768.0 = 0.0
        assert!((f32s[2]).abs() < 0.001);
    }

    #[test]
    fn test_samples_i16_to_f32_all_within_range() {
        // Every possible i16 value should produce f32 in [-1.0, 1.0)
        let samples: Vec<i16> = vec![i16::MIN, i16::MIN + 1, -1, 0, 1, i16::MAX - 1, i16::MAX];
        let f32s = samples_i16_to_f32(&samples);
        for &v in &f32s {
            assert!(v >= -1.0, "value {v} below -1.0");
            assert!(v < 1.0, "value {v} >= 1.0 (i16::MAX / 32768 should be < 1)");
        }
    }

    // -----------------------------------------------------------------------
    // 14. samples_to_wav_bytes with large data (no overflow)
    // -----------------------------------------------------------------------
    #[test]
    fn test_wav_bytes_large_sample_count() {
        // 10 seconds of audio at 22050 Hz = 220,500 samples
        let num_samples = 220_500;
        let samples = vec![0i16; num_samples];
        let wav = samples_to_wav_bytes(&samples, 22050);

        // Total should be 44 header + num_samples * 2 bytes
        let expected_len = 44 + num_samples * 2;
        assert_eq!(wav.len(), expected_len);

        // RIFF file size = total - 8
        let file_size = u32::from_le_bytes([wav[4], wav[5], wav[6], wav[7]]);
        assert_eq!(file_size, (expected_len - 8) as u32);

        // data chunk size = num_samples * 2
        let data_size = u32::from_le_bytes([wav[40], wav[41], wav[42], wav[43]]);
        assert_eq!(data_size, (num_samples * 2) as u32);
    }

    // -----------------------------------------------------------------------
    // 15. parse_config with extra/unknown fields (should be ignored)
    // -----------------------------------------------------------------------
    #[test]
    fn test_parse_config_extra_fields_ignored() {
        let json = r#"{
            "audio": {"sample_rate": 44100},
            "num_speakers": 5,
            "some_unknown_field": "should be ignored",
            "another_unknown": 42,
            "nested_unknown": {"a": 1, "b": [2, 3]}
        }"#;
        let config = parse_config(json).unwrap();
        assert_eq!(config.audio.sample_rate, 44100);
        assert_eq!(config.num_speakers, 5);
        // The parse succeeded despite unknown fields
    }

    // -----------------------------------------------------------------------
    // 16. parse_config with speaker_id_map
    // -----------------------------------------------------------------------
    #[test]
    fn test_parse_config_speaker_id_map() {
        let json = r#"{
            "num_speakers": 3,
            "speaker_id_map": {"alice": 0, "bob": 1, "charlie": 2},
            "phoneme_id_map": {"a": [1], "b": [2]}
        }"#;
        let config = parse_config(json).unwrap();
        assert_eq!(config.num_speakers, 3);
        assert_eq!(config.speaker_id_map.len(), 3);
        assert_eq!(config.speaker_id_map.get("alice"), Some(&0));
        assert_eq!(config.speaker_id_map.get("charlie"), Some(&2));
    }

    // -----------------------------------------------------------------------
    // 17. WasmVoice::load_from_bytes with empty model bytes
    // -----------------------------------------------------------------------
    #[test]
    fn test_load_from_bytes_empty_model() {
        let config = r#"{"audio": {"sample_rate": 22050}}"#;
        let result = WasmVoice::load_from_bytes(b"", config);
        assert!(result.is_err());
        match result.err().unwrap() {
            PiperError::ModelLoad(_) => {} // ONNX runtime cannot load empty bytes
            other => panic!("expected ModelLoad, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // 18. samples_to_wav_bytes roundtrip with extreme values
    // -----------------------------------------------------------------------
    #[test]
    fn test_wav_bytes_extreme_sample_values() {
        let samples: Vec<i16> = vec![i16::MIN, i16::MAX, i16::MIN, i16::MAX];
        let wav = samples_to_wav_bytes(&samples, 22050);

        // Verify each extreme value survives the WAV encoding
        for (i, &expected) in samples.iter().enumerate() {
            let offset = 44 + i * 2;
            let recovered = i16::from_le_bytes([wav[offset], wav[offset + 1]]);
            assert_eq!(
                recovered, expected,
                "sample {i}: expected {expected}, got {recovered}",
            );
        }
    }

    // -----------------------------------------------------------------------
    // 19. WasmSynthesisResult real_time_factor edge: both zero
    // -----------------------------------------------------------------------
    #[test]
    fn test_wasm_synthesis_result_rtf_both_zero() {
        let result = WasmSynthesisResult {
            audio_samples: Vec::new(),
            sample_rate: 22050,
            infer_seconds: 0.0,
            audio_seconds: 0.0,
        };
        // audio_seconds == 0 -> returns 0.0 (guarded division)
        assert!((result.real_time_factor()).abs() < 1e-6);
    }
}
