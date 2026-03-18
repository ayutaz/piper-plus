//! PiperVoice — テキストから音声への高レベル API
//!
//! テキスト入力 → 音素化 → ID 変換 → ONNX 推論 → WAV 出力

use std::path::Path;

use crate::config::VoiceConfig;
use crate::engine::{OnnxEngine, SynthesisRequest, SynthesisResult};
use crate::error::PiperError;
use crate::phonemize::phoneme_converter;
use crate::phonemize::Phonemizer;

/// テキストから音声を合成する高レベル API
pub struct PiperVoice {
    config: VoiceConfig,
    engine: OnnxEngine,
    phonemizer: Box<dyn Phonemizer>,
}

impl PiperVoice {
    /// モデルとconfigを読み込んで初期化
    ///
    /// phoneme_type に基づいて適切な Phonemizer を自動選択:
    /// - OpenJTalk → JapanesePhonemizer (feature = "japanese")
    /// - Bilingual/Multilingual → 将来の Phase 3 で対応
    pub fn load(
        model_path: &Path,
        config_path: Option<&Path>,
        device: &str,
    ) -> Result<Self, PiperError> {
        let resolved_config = VoiceConfig::resolve_config_path(model_path, config_path)?;
        let config = VoiceConfig::load(&resolved_config)?;
        let phonemizer = Self::create_phonemizer(&config)?;
        let engine = OnnxEngine::load(model_path, &config, device)?;

        Ok(Self {
            config,
            engine,
            phonemizer,
        })
    }

    /// phoneme_type に基づいて Phonemizer を生成する。
    ///
    /// テスト容易性のため独立関数として切り出し。
    fn create_phonemizer(config: &VoiceConfig) -> Result<Box<dyn Phonemizer>, PiperError> {
        #[cfg(feature = "japanese")]
        if config.phoneme_type == crate::config::PhonemeType::OpenJTalk {
            return Ok(
                Box::new(crate::phonemize::japanese::JapanesePhonemizer::new()?)
            );
        }

        Err(PiperError::UnsupportedLanguage {
            code: format!("{:?}", config.phoneme_type),
        })
    }

    /// テキストを音声に変換
    pub fn synthesize_text(
        &mut self,
        text: &str,
        speaker_id: Option<i64>,
        noise_scale: f32,
        length_scale: f32,
        noise_w: f32,
    ) -> Result<SynthesisResult, PiperError> {
        // 1. Phonemize: テキストをトークン列 + プロソディ情報に変換
        let (tokens, prosody) = self.phonemizer.phonemize_with_prosody(text)?;

        // 2. Convert tokens to IDs using phoneme_id_map
        let phoneme_id_map = self
            .phonemizer
            .get_phoneme_id_map()
            .unwrap_or(&self.config.phoneme_id_map);

        let ids = phoneme_converter::tokens_to_ids(&tokens, phoneme_id_map)?;
        let prosody_feats = prosody_to_optional_features(&prosody);

        // 3. Post-process IDs (BOS/EOS/padding insertion, language-specific)
        let (ids, prosody_feats) =
            self.phonemizer
                .post_process_ids(ids, prosody_feats, phoneme_id_map);

        // 4. Determine language_id from config
        let language_id = if self.config.needs_lid() {
            let lang_code = self.phonemizer.language_code();
            Some(
                self.config
                    .language_id_map
                    .get(lang_code)
                    .copied()
                    .unwrap_or(0),
            )
        } else {
            None
        };

        // 5. Build request and run inference
        let request = SynthesisRequest {
            phoneme_ids: ids,
            prosody_features: build_prosody_tensor(&prosody_feats),
            speaker_id,
            language_id,
            noise_scale,
            length_scale,
            noise_w,
        };

        self.engine.synthesize(&request)
    }

    /// テキストを WAV ファイルに出力 (デフォルトパラメータ使用)
    pub fn text_to_wav_file(
        &mut self,
        text: &str,
        output: &Path,
        speaker_id: Option<i64>,
    ) -> Result<SynthesisResult, PiperError> {
        let result = self.synthesize_text(text, speaker_id, 0.667, 1.0, 0.8)?;
        crate::audio::write_wav(output, result.sample_rate, &result.audio)?;
        Ok(result)
    }

    /// config への参照を返す
    pub fn config(&self) -> &VoiceConfig {
        &self.config
    }

    /// engine への参照を返す
    pub fn engine(&self) -> &OnnxEngine {
        &self.engine
    }
}

// ---------------------------------------------------------------------------
// ヘルパー関数
// ---------------------------------------------------------------------------

/// ProsodyInfo 列を Option<ProsodyFeature> 列に変換する。
///
/// `synthesize_text` で phonemizer の `post_process_ids` に渡すための中間形式。
fn prosody_to_optional_features(
    prosody: &[Option<crate::phonemize::ProsodyInfo>],
) -> Vec<Option<crate::phonemize::ProsodyFeature>> {
    prosody
        .iter()
        .map(|p| p.map(|info| [info.a1, info.a2, info.a3]))
        .collect()
}

/// Optional prosody features を ONNX 入力用の Vec<[i32; 3]> に変換する。
///
/// いずれかの要素が Some なら全体を Some(Vec) として返す。
/// 全要素が None なら None を返す (prosody テンソル不要)。
fn build_prosody_tensor(
    features: &[Option<crate::phonemize::ProsodyFeature>],
) -> Option<Vec<crate::phonemize::ProsodyFeature>> {
    if features.iter().any(|p| p.is_some()) {
        Some(
            features
                .iter()
                .map(|p| p.unwrap_or([0, 0, 0]))
                .collect(),
        )
    } else {
        None
    }
}

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::PhonemeType;
    use crate::engine::SynthesisRequest;
    use crate::phonemize::ProsodyInfo;
    use std::collections::HashMap;

    /// Helper: extract PiperError from a Result, panicking if Ok.
    fn expect_err<T>(result: Result<T, PiperError>) -> PiperError {
        match result {
            Err(e) => e,
            Ok(_) => panic!("expected Err, got Ok"),
        }
    }

    // -----------------------------------------------------------------------
    // 1. PiperVoice::load fails gracefully with missing model file
    // -----------------------------------------------------------------------
    #[test]
    fn test_load_fails_with_missing_model() {
        let result = PiperVoice::load(
            Path::new("/nonexistent/model.onnx"),
            None,
            "cpu",
        );
        let err = expect_err(result);
        // config が見つからないためエラーになる
        let msg = format!("{err}");
        assert!(
            msg.contains("config") || msg.contains("not found") || msg.contains("Config"),
            "unexpected error message: {msg}"
        );
    }

    // -----------------------------------------------------------------------
    // 2. phoneme_type matching logic — all unsupported types return error
    // -----------------------------------------------------------------------
    #[test]
    fn test_create_phonemizer_unsupported_espeak() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 1,
            num_symbols: 0,
            phoneme_type: PhonemeType::Espeak,
            phoneme_id_map: HashMap::new(),
            num_languages: 1,
            language_id_map: HashMap::new(),
            speaker_id_map: HashMap::new(),
        };
        match expect_err(PiperVoice::create_phonemizer(&config)) {
            PiperError::UnsupportedLanguage { code } => {
                assert!(
                    code.contains("Espeak"),
                    "expected 'Espeak' in code, got: {code}"
                );
            }
            other => panic!("expected UnsupportedLanguage, got: {other:?}"),
        }
    }

    #[test]
    fn test_create_phonemizer_unsupported_bilingual() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 1,
            num_symbols: 0,
            phoneme_type: PhonemeType::Bilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: HashMap::new(),
            speaker_id_map: HashMap::new(),
        };
        match expect_err(PiperVoice::create_phonemizer(&config)) {
            PiperError::UnsupportedLanguage { code } => {
                assert!(
                    code.contains("Bilingual"),
                    "expected 'Bilingual' in code, got: {code}"
                );
            }
            other => panic!("expected UnsupportedLanguage, got: {other:?}"),
        }
    }

    #[test]
    fn test_create_phonemizer_unsupported_multilingual() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 571,
            num_symbols: 173,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 6,
            language_id_map: [
                ("ja".into(), 0),
                ("en".into(), 1),
                ("zh".into(), 2),
            ]
            .into_iter()
            .collect(),
            speaker_id_map: HashMap::new(),
        };
        match expect_err(PiperVoice::create_phonemizer(&config)) {
            PiperError::UnsupportedLanguage { code } => {
                assert!(
                    code.contains("Multilingual"),
                    "expected 'Multilingual' in code, got: {code}"
                );
            }
            other => panic!("expected UnsupportedLanguage, got: {other:?}"),
        }
    }

    #[test]
    fn test_create_phonemizer_unsupported_text() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 1,
            num_symbols: 0,
            phoneme_type: PhonemeType::Text,
            phoneme_id_map: HashMap::new(),
            num_languages: 1,
            language_id_map: HashMap::new(),
            speaker_id_map: HashMap::new(),
        };
        match expect_err(PiperVoice::create_phonemizer(&config)) {
            PiperError::UnsupportedLanguage { code } => {
                assert!(
                    code.contains("Text"),
                    "expected 'Text' in code, got: {code}"
                );
            }
            other => panic!("expected UnsupportedLanguage, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // 3. language_id determination
    // -----------------------------------------------------------------------
    #[test]
    fn test_language_id_single_language_no_lid() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 1,
            num_symbols: 0,
            phoneme_type: PhonemeType::OpenJTalk,
            phoneme_id_map: HashMap::new(),
            num_languages: 1,
            language_id_map: HashMap::new(),
            speaker_id_map: HashMap::new(),
        };
        // Single language: needs_lid() should return false
        assert!(!config.needs_lid());
        assert!(!config.is_multilingual());
    }

    #[test]
    fn test_language_id_multilingual_needs_lid() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 571,
            num_symbols: 173,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 6,
            language_id_map: [
                ("ja".into(), 0i64),
                ("en".into(), 1),
                ("zh".into(), 2),
                ("es".into(), 3),
                ("fr".into(), 4),
                ("pt".into(), 5),
            ]
            .into_iter()
            .collect(),
            speaker_id_map: HashMap::new(),
        };
        assert!(config.needs_lid());
        assert_eq!(config.language_id_map.get("ja"), Some(&0));
        assert_eq!(config.language_id_map.get("en"), Some(&1));
        assert_eq!(config.language_id_map.get("zh"), Some(&2));
        // Unknown language falls back to 0
        assert_eq!(
            config.language_id_map.get("ko").copied().unwrap_or(0),
            0
        );
    }

    #[test]
    fn test_language_id_bilingual_needs_lid() {
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 330,
            num_symbols: 97,
            phoneme_type: PhonemeType::Bilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("ja".into(), 0i64), ("en".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        assert!(config.needs_lid());
        assert_eq!(config.language_id_map.get("ja"), Some(&0));
        assert_eq!(config.language_id_map.get("en"), Some(&1));
    }

    // -----------------------------------------------------------------------
    // 4. SynthesisRequest construction
    // -----------------------------------------------------------------------
    #[test]
    fn test_synthesis_request_construction_basic() {
        let ids = vec![1i64, 8, 5, 39, 42, 10, 2];
        let request = SynthesisRequest {
            phoneme_ids: ids.clone(),
            prosody_features: None,
            speaker_id: Some(0),
            language_id: None,
            noise_scale: 0.667,
            length_scale: 1.0,
            noise_w: 0.8,
        };
        assert_eq!(request.phoneme_ids, ids);
        assert!(request.prosody_features.is_none());
        assert_eq!(request.speaker_id, Some(0));
        assert!(request.language_id.is_none());
    }

    #[test]
    fn test_synthesis_request_construction_with_prosody() {
        let prosody_feats = vec![[-2, 1, 5], [0, 2, 5], [1, 3, 5]];
        let request = SynthesisRequest {
            phoneme_ids: vec![1, 2, 3],
            prosody_features: Some(prosody_feats.clone()),
            speaker_id: Some(3),
            language_id: Some(0),
            noise_scale: 0.5,
            length_scale: 1.2,
            noise_w: 0.6,
        };
        assert_eq!(request.prosody_features.as_ref().unwrap().len(), 3);
        assert_eq!(request.prosody_features.as_ref().unwrap()[0], [-2, 1, 5]);
        assert_eq!(request.speaker_id, Some(3));
        assert_eq!(request.language_id, Some(0));
    }

    #[test]
    fn test_synthesis_request_construction_multilingual() {
        let request = SynthesisRequest {
            phoneme_ids: vec![1, 5, 10, 20],
            prosody_features: None,
            speaker_id: Some(100),
            language_id: Some(2), // zh
            noise_scale: 0.667,
            length_scale: 1.0,
            noise_w: 0.8,
        };
        assert_eq!(request.language_id, Some(2));
        assert_eq!(request.speaker_id, Some(100));
    }

    // -----------------------------------------------------------------------
    // 5. Prosody feature conversion
    // -----------------------------------------------------------------------
    #[test]
    fn test_prosody_to_optional_features_with_values() {
        let prosody = vec![
            Some(ProsodyInfo { a1: -2, a2: 1, a3: 5 }),
            None,
            Some(ProsodyInfo { a1: 0, a2: 3, a3: 5 }),
        ];
        let result = prosody_to_optional_features(&prosody);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], Some([-2, 1, 5]));
        assert_eq!(result[1], None);
        assert_eq!(result[2], Some([0, 3, 5]));
    }

    #[test]
    fn test_prosody_to_optional_features_all_none() {
        let prosody: Vec<Option<ProsodyInfo>> = vec![None, None, None];
        let result = prosody_to_optional_features(&prosody);
        assert!(result.iter().all(|p| p.is_none()));
    }

    #[test]
    fn test_prosody_to_optional_features_empty() {
        let prosody: Vec<Option<ProsodyInfo>> = vec![];
        let result = prosody_to_optional_features(&prosody);
        assert!(result.is_empty());
    }

    #[test]
    fn test_build_prosody_tensor_with_some() {
        let features = vec![
            Some([-2, 1, 5]),
            None,
            Some([0, 3, 5]),
        ];
        let tensor = build_prosody_tensor(&features);
        assert!(tensor.is_some());
        let t = tensor.unwrap();
        assert_eq!(t.len(), 3);
        assert_eq!(t[0], [-2, 1, 5]);
        assert_eq!(t[1], [0, 0, 0]); // None -> zero-filled
        assert_eq!(t[2], [0, 3, 5]);
    }

    #[test]
    fn test_build_prosody_tensor_all_none() {
        let features: Vec<Option<[i32; 3]>> = vec![None, None];
        let tensor = build_prosody_tensor(&features);
        assert!(tensor.is_none());
    }

    #[test]
    fn test_build_prosody_tensor_empty() {
        let features: Vec<Option<[i32; 3]>> = vec![];
        let tensor = build_prosody_tensor(&features);
        assert!(tensor.is_none());
    }

    // -----------------------------------------------------------------------
    // phoneme_converter integration (tokens_to_ids)
    // -----------------------------------------------------------------------
    #[test]
    fn test_tokens_to_ids_via_converter() {
        let mut id_map: HashMap<String, Vec<i64>> = HashMap::new();
        id_map.insert("a".into(), vec![5]);
        id_map.insert("k".into(), vec![10]);
        id_map.insert("o".into(), vec![15]);

        let tokens: Vec<String> = vec!["a".into(), "k".into(), "o".into()];
        let ids = phoneme_converter::tokens_to_ids(&tokens, &id_map).unwrap();
        assert_eq!(ids, vec![5, 10, 15]);
    }

    #[test]
    fn test_tokens_to_ids_unknown_phoneme() {
        let id_map: HashMap<String, Vec<i64>> = HashMap::new();
        let tokens: Vec<String> = vec!["xyz".into()];
        let result = phoneme_converter::tokens_to_ids(&tokens, &id_map);
        assert!(result.is_err());
        match result.unwrap_err() {
            PiperError::PhonemeIdNotFound { phoneme } => {
                assert_eq!(phoneme, "xyz");
            }
            other => panic!("expected PhonemeIdNotFound, got: {other:?}"),
        }
    }
}
