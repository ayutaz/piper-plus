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
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self { sample_rate: 22050 }
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
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deserialize_minimal_config() {
        let json = r#"{"phoneme_id_map": {"a": [1]}, "audio": {"sample_rate": 22050}}"#;
        let config: VoiceConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.audio.sample_rate, 22050);
        assert_eq!(config.num_speakers, 1);
        assert_eq!(config.num_languages, 1);
        assert!(!config.is_multilingual());
        assert!(!config.needs_lid());
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
}
