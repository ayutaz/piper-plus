use serde::Deserialize;
use std::collections::HashMap;
use std::path::Path;

use crate::error::PiperError;

pub type PhonemeIdMap = HashMap<String, Vec<i64>>;

#[derive(Debug, Clone, Deserialize)]
pub struct VoiceConfig {
    #[serde(default)]
    pub audio: AudioConfig,

    #[serde(default = "default_num_speakers")]
    pub num_speakers: usize,

    #[serde(default)]
    pub num_symbols: usize,

    #[serde(default)]
    pub phoneme_type: PhonemeType,

    #[serde(default)]
    pub phoneme_id_map: PhonemeIdMap,

    #[serde(default = "default_num_languages")]
    pub num_languages: usize,

    #[serde(default)]
    pub language_id_map: HashMap<String, i64>,

    #[serde(default)]
    pub speaker_id_map: HashMap<String, i64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AudioConfig {
    #[serde(default = "default_sample_rate")]
    pub sample_rate: u32,

    /// VITS hop length (samples per acoustic frame).
    ///
    /// Required for converting frame-level ``durations`` (model output) into
    /// audio-sample positions during Strategy A post-trim. Defaults to 256
    /// to keep older config.json files (no `audio.hop_size` field) working.
    #[serde(default = "default_hop_size")]
    pub hop_size: u32,
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self {
            sample_rate: 22050,
            hop_size: 256,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Default, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum PhonemeType {
    #[default]
    #[serde(alias = "espeak")]
    Espeak,
    #[serde(alias = "openjtalk")]
    OpenJTalk,
    Bilingual,
    Multilingual,
    Text,
}

fn default_num_speakers() -> usize {
    1
}
fn default_num_languages() -> usize {
    1
}
fn default_sample_rate() -> u32 {
    22050
}
fn default_hop_size() -> u32 {
    256
}

impl VoiceConfig {
    /// config.json を読み込む
    pub fn load(path: &Path) -> Result<Self, PiperError> {
        let content = std::fs::read_to_string(path).map_err(|_| PiperError::ConfigNotFound {
            path: path.display().to_string(),
        })?;
        let config: VoiceConfig = serde_json::from_str(&content)?;
        Ok(config)
    }

    /// モデルがマルチスピーカーか
    pub fn is_multi_speaker(&self) -> bool {
        self.num_speakers > 1
    }

    /// モデルが多言語か
    pub fn is_multilingual(&self) -> bool {
        self.num_languages > 1
    }

    /// sid テンソルが必要か
    pub fn needs_sid(&self) -> bool {
        self.is_multi_speaker() || self.is_multilingual()
    }

    /// lid テンソルが必要か
    pub fn needs_lid(&self) -> bool {
        self.is_multilingual()
    }

    /// prosody_features テンソルが必要か (phoneme_id_map に prosody 関連キーがあるか)
    pub fn needs_prosody(&self) -> bool {
        // prosody_features の有無はONNXモデルの入力ノードで判定するのが正確
        // ここではconfig情報からのヒューリスティック
        self.phoneme_type == PhonemeType::OpenJTalk
            || self.phoneme_type == PhonemeType::Bilingual
            || self.phoneme_type == PhonemeType::Multilingual
    }

    /// config.json のフォールバック検索
    /// 1. --config で明示指定
    /// 2. {model}.onnx.json
    /// 3. {model_dir}/config.json
    pub fn resolve_config_path(
        model_path: &Path,
        explicit_config: Option<&Path>,
    ) -> Result<std::path::PathBuf, PiperError> {
        if let Some(p) = explicit_config {
            if p.exists() {
                return Ok(p.to_path_buf());
            }
            return Err(PiperError::ConfigNotFound {
                path: p.display().to_string(),
            });
        }

        // {model}.onnx.json
        let onnx_json = model_path.with_extension("onnx.json");
        if onnx_json.exists() {
            return Ok(onnx_json);
        }

        // {model_dir}/config.json
        if let Some(dir) = model_path.parent() {
            let dir_config = dir.join("config.json");
            if dir_config.exists() {
                return Ok(dir_config);
            }
        }

        Err(PiperError::ConfigNotFound {
            path: format!("no config found for {}", model_path.display()),
        })
    }

    /// Validate the config for correctness.
    /// Returns Ok(()) if valid, or Err with a description of the first problem found.
    pub fn validate(&self) -> Result<(), String> {
        // 1. phoneme_id_map must not be empty
        if self.phoneme_id_map.is_empty() {
            return Err("phoneme_id_map is empty".to_string());
        }

        // 2-4. Required markers
        if !self.phoneme_id_map.contains_key("^") {
            return Err("phoneme_id_map missing required BOS marker '^'".to_string());
        }
        if !self.phoneme_id_map.contains_key("_") {
            return Err("phoneme_id_map missing required PAD marker '_'".to_string());
        }
        if !self.phoneme_id_map.contains_key("$") {
            return Err("phoneme_id_map missing required EOS marker '$'".to_string());
        }

        // 5. Each ID list must be non-empty
        for (key, ids) in &self.phoneme_id_map {
            if ids.is_empty() {
                return Err(format!("phoneme_id_map[\"{key}\"] has empty ID list"));
            }
        }

        // 6. sample_rate range check
        if self.audio.sample_rate < 8000 || self.audio.sample_rate > 48000 {
            return Err(format!(
                "audio.sample_rate={} out of range [8000, 48000]",
                self.audio.sample_rate
            ));
        }

        // 7-8. Multilingual/Bilingual require non-empty language_id_map
        if matches!(
            self.phoneme_type,
            PhonemeType::Multilingual | PhonemeType::Bilingual
        ) {
            if self.language_id_map.is_empty() {
                return Err("multilingual model requires non-empty language_id_map".to_string());
            }
            if self.num_languages > 1 && self.language_id_map.len() != self.num_languages {
                return Err(format!(
                    "num_languages={} but language_id_map has {} entries",
                    self.num_languages,
                    self.language_id_map.len()
                ));
            }
        }

        // 9. speaker_id_map warning (non-blocking)
        if self.num_speakers > 1 && self.speaker_id_map.is_empty() {
            eprintln!(
                "warning: num_speakers={} but speaker_id_map is empty",
                self.num_speakers
            );
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_minimal_config() {
        let json = r#"{"phoneme_id_map": {"a": [1]}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.audio.sample_rate, 22050);
        // hop_size defaults to 256 when missing — keeps older configs working.
        assert_eq!(config.audio.hop_size, 256);
        assert_eq!(config.num_speakers, 1);
        assert_eq!(config.num_languages, 1);
        assert!(!config.is_multilingual());
        assert!(!config.needs_lid());
    }

    #[test]
    fn test_deserialize_audio_hop_size() {
        // Explicit hop_size is honoured.
        let json =
            r#"{"phoneme_id_map": {"a": [1]}, "audio": {"sample_rate": 22050, "hop_size": 512}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.audio.hop_size, 512);
    }

    #[test]
    fn test_deserialize_audio_default_hop_size_when_audio_missing() {
        // No audio section at all → both defaults apply.
        let json = r#"{"phoneme_id_map": {"a": [1]}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.audio.sample_rate, 22050);
        assert_eq!(config.audio.hop_size, 256);
    }

    #[test]
    fn test_audio_config_default() {
        // Ensure Default impl matches serde defaults.
        let audio = AudioConfig::default();
        assert_eq!(audio.sample_rate, 22050);
        assert_eq!(audio.hop_size, 256);
    }

    #[test]
    fn test_deserialize_multilingual_config() {
        let json = r#"{
            "num_speakers": 571,
            "num_languages": 6,
            "phoneme_type": "multilingual",
            "phoneme_id_map": {"^": [1], "_": [0]},
            "language_id_map": {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5}
        }"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert!(config.is_multilingual());
        assert!(config.needs_sid());
        assert!(config.needs_lid());
        assert_eq!(config.language_id_map.len(), 6);
    }

    #[test]
    fn test_phoneme_type_deserialization() {
        let json = r#"{"phoneme_type": "openjtalk"}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.phoneme_type, PhonemeType::OpenJTalk);
    }

    #[test]
    fn test_validate_minimal_valid() {
        let json = r#"{
            "phoneme_id_map": {"^": [1], "_": [0], "$": [2], "a": [15]},
            "audio": {"sample_rate": 22050}
        }"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_validate_empty_phoneme_id_map() {
        let json = r#"{"phoneme_id_map": {}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("empty"), "Error: {err}");
    }

    #[test]
    fn test_validate_missing_bos() {
        let json = r#"{"phoneme_id_map": {"_": [0], "$": [2]}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("BOS"), "Error: {err}");
    }

    #[test]
    fn test_validate_missing_pad() {
        let json = r#"{"phoneme_id_map": {"^": [1], "$": [2]}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("PAD"), "Error: {err}");
    }

    #[test]
    fn test_validate_missing_eos() {
        let json = r#"{"phoneme_id_map": {"^": [1], "_": [0]}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("EOS"), "Error: {err}");
    }

    #[test]
    fn test_validate_empty_id_list() {
        let json = r#"{"phoneme_id_map": {"^": [1], "_": [0], "$": [2], "a": []}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("empty ID list"), "Error: {err}");
    }

    #[test]
    fn test_validate_sample_rate_zero() {
        let json =
            r#"{"phoneme_id_map": {"^": [1], "_": [0], "$": [2]}, "audio": {"sample_rate": 0}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("out of range"), "Error: {err}");
    }

    #[test]
    fn test_validate_sample_rate_too_high() {
        let json = r#"{"phoneme_id_map": {"^": [1], "_": [0], "$": [2]}, "audio": {"sample_rate": 100000}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("out of range"), "Error: {err}");
    }

    #[test]
    fn test_validate_multilingual_empty_lang_map() {
        let json = r#"{
            "phoneme_id_map": {"^": [1], "_": [0], "$": [2]},
            "audio": {"sample_rate": 22050},
            "phoneme_type": "multilingual",
            "num_languages": 6,
            "language_id_map": {}
        }"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        let err = config.validate().unwrap_err();
        assert!(err.contains("requires non-empty"), "Error: {err}");
    }

    #[test]
    fn test_validate_multilingual_valid() {
        let json = r#"{
            "phoneme_id_map": {"^": [1], "_": [0], "$": [2], "a": [15]},
            "audio": {"sample_rate": 22050},
            "phoneme_type": "multilingual",
            "num_languages": 6,
            "language_id_map": {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5}
        }"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_validate_single_lang_empty_lang_map_ok() {
        let json = r#"{
            "phoneme_id_map": {"^": [1], "_": [0], "$": [2]},
            "audio": {"sample_rate": 22050},
            "num_languages": 1,
            "language_id_map": {}
        }"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert!(config.validate().is_ok());
    }
}
