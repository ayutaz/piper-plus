//! PiperVoice — テキストから音声への高レベル API
//!
//! テキスト入力 → 音素化 → ID 変換 → ONNX 推論 → WAV 出力

use std::path::Path;

use crate::config::VoiceConfig;
use crate::engine::{OnnxEngine, SynthesisRequest, SynthesisResult};
use crate::error::PiperError;
use crate::phonemize::Phonemizer;
use crate::phonemize::adapter::G2pAdapter;

/// テキストレベルの合成パラメータ。
///
/// `PiperVoice::synthesize_with_params()` で使用する高レベル構造体。
/// `..Default::default()` パターンで、変更したいフィールドだけ指定できる。
///
/// # Examples
///
/// ```ignore
/// let result = voice.synthesize_with_params("こんにちは", &SynthesisParams {
///     speaker_id: Some(0),
///     language_override: Some("ja".into()),
///     ..Default::default()
/// })?;
/// ```
///
/// > **Note:** 低レベルの音素ID入力には既存の [`SynthesisRequest`] を使用してください。
#[derive(Debug, Clone)]
pub struct SynthesisParams {
    /// 話者 ID (マルチスピーカーモデル用)
    pub speaker_id: Option<i64>,
    /// 言語オーバーライド (マルチリンガルモデル用、phonemizer の自動検出を上書き)
    pub language_override: Option<String>,
    /// ノイズスケール (音声の変動量、0.0-1.0)
    pub noise_scale: f32,
    /// 長さスケール (話速、1.0 = 標準)
    pub length_scale: f32,
    /// ノイズスケール W (持続時間の変動量)
    pub noise_w: f32,
    /// Speaker embedding vector for voice cloning (overrides speaker_id).
    pub speaker_embedding: Option<Vec<f32>>,
}

impl Default for SynthesisParams {
    fn default() -> Self {
        Self {
            speaker_id: None,
            language_override: None,
            noise_scale: 0.667,
            length_scale: 1.0,
            noise_w: 0.8,
            speaker_embedding: None,
        }
    }
}

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
    /// - Bilingual/Multilingual → MultilingualPhonemizer (Unicode言語検出)
    pub fn load(
        model_path: &Path,
        config_path: Option<&Path>,
        device: &str,
    ) -> Result<Self, PiperError> {
        let resolved_config = VoiceConfig::resolve_config_path(model_path, config_path)?;
        let config = VoiceConfig::load(&resolved_config)?;
        let model_dir = model_path.parent().map(|p| p.to_path_buf());

        // COLD-M3: phonemizer と engine の初期化を並列化。
        // 両者は独立しているため、max(phonemizer_time, engine_time) に短縮できる。

        // Native: std::thread::spawn で並列化
        #[cfg(not(target_arch = "wasm32"))]
        let (phonemizer, engine) = {
            let config_clone = config.clone();
            let model_dir_clone = model_dir.clone();
            let phonemizer_handle = std::thread::spawn(move || {
                Self::create_phonemizer(&config_clone, model_dir_clone.as_deref())
            });

            let engine = OnnxEngine::load(model_path, &config, device)?;

            let phonemizer = phonemizer_handle.join().map_err(|e| {
                let msg = e
                    .downcast_ref::<&str>()
                    .map(|s| s.to_string())
                    .or_else(|| e.downcast_ref::<String>().cloned())
                    .unwrap_or_else(|| "unknown panic".to_string());
                PiperError::ModelLoad(format!("phonemizer init panicked: {}", msg))
            })??;

            (phonemizer, engine)
        };

        // WASM: 逐次実行 (std::thread::spawn は wasm32 で不可)
        #[cfg(target_arch = "wasm32")]
        let (phonemizer, engine) = {
            let phonemizer = Self::create_phonemizer(&config, model_dir.as_deref())?;
            let engine = OnnxEngine::load(model_path, &config, device)?;
            (phonemizer, engine)
        };

        Ok(Self {
            config,
            engine,
            phonemizer,
        })
    }

    /// phoneme_type に基づいて Phonemizer を生成する。
    ///
    /// `model_dir` はモデルファイルの親ディレクトリ。辞書ファイルの検索に使用。
    /// テスト容易性のため独立関数として切り出し。
    /// `--test-mode` (CLI) で ONNX エンジンなしに phonemizer のみ使用する場合にも利用。
    pub fn create_phonemizer(
        config: &VoiceConfig,
        model_dir: Option<&Path>,
    ) -> Result<Box<dyn Phonemizer>, PiperError> {
        match config.phoneme_type {
            #[cfg(feature = "japanese")]
            crate::config::PhonemeType::OpenJTalk => Ok(Box::new(G2pAdapter::new(Box::new(
                Self::create_japanese_phonemizer()?,
            )))),
            crate::config::PhonemeType::Bilingual | crate::config::PhonemeType::Multilingual => {
                let mut languages: Vec<String> = config.language_id_map.keys().cloned().collect();
                languages.sort();
                if languages.is_empty() {
                    return Err(PiperError::InvalidConfig {
                        reason: "multilingual model requires language_id_map".to_string(),
                    });
                }
                let default_latin = if languages.contains(&"en".to_string()) {
                    "en".to_string()
                } else {
                    languages
                        .iter()
                        .find(|l| matches!(l.as_str(), "es" | "fr" | "pt" | "sv"))
                        .cloned()
                        .unwrap_or_else(|| languages[0].clone())
                };
                let mut g2p_phonemizers: std::collections::HashMap<
                    String,
                    Box<dyn piper_plus_g2p::Phonemizer>,
                > = std::collections::HashMap::new();
                for lang in &languages {
                    let p = Self::create_language_g2p_phonemizer(lang, model_dir)?;
                    g2p_phonemizers.insert(lang.clone(), p);
                }
                Ok(Box::new(G2pAdapter::new(Box::new(
                    piper_plus_g2p::multilingual::MultilingualPhonemizer::new(
                        languages,
                        default_latin,
                        g2p_phonemizers,
                    ),
                ))))
            }
            _ => Err(PiperError::UnsupportedLanguage {
                code: format!("{:?}", config.phoneme_type),
            }),
        }
    }

    /// 言語コードに基づいて適切な piper_plus_g2p::Phonemizer を生成する。
    ///
    /// 辞書が必要な言語 (ja, en, zh) は `model_dir` 配下またはデフォルトパスから
    /// 辞書を検索する。JA は dictionary_manager による自動ダウンロードも対応。
    /// 辞書が見つからない場合は PassthroughPhonemizer にフォールバックする。
    fn create_language_g2p_phonemizer(
        lang: &str,
        model_dir: Option<&Path>,
    ) -> Result<Box<dyn piper_plus_g2p::Phonemizer>, PiperError> {
        match lang {
            #[cfg(feature = "japanese")]
            "ja" => match Self::create_japanese_phonemizer() {
                Ok(p) => Ok(Box::new(p)),
                Err(e) => {
                    tracing::warn!("Japanese phonemizer unavailable ({}), using passthrough", e);
                    Ok(Box::new(
                        piper_plus_g2p::multilingual::PassthroughPhonemizer::new(lang),
                    ))
                }
            },
            "en" => match Self::create_english_phonemizer(model_dir) {
                Ok(p) => Ok(Box::new(p)),
                Err(e) => {
                    tracing::warn!("English phonemizer unavailable ({}), using passthrough", e);
                    Ok(Box::new(
                        piper_plus_g2p::multilingual::PassthroughPhonemizer::new(lang),
                    ))
                }
            },
            "zh" => match Self::create_chinese_phonemizer(model_dir) {
                Ok(p) => Ok(Box::new(p)),
                Err(e) => {
                    tracing::warn!("Chinese phonemizer unavailable ({}), using passthrough", e);
                    Ok(Box::new(
                        piper_plus_g2p::multilingual::PassthroughPhonemizer::new(lang),
                    ))
                }
            },
            "es" => Ok(Box::new(piper_plus_g2p::spanish::SpanishPhonemizer::new())),
            "fr" => Ok(Box::new(piper_plus_g2p::french::FrenchPhonemizer::new())),
            "pt" => Ok(Box::new(
                piper_plus_g2p::portuguese::PortuguesePhonemizer::new(),
            )),
            "ko" => Ok(Box::new(piper_plus_g2p::korean::KoreanPhonemizer::new())),
            "sv" => Ok(Box::new(piper_plus_g2p::swedish::SwedishPhonemizer::new())),
            _ => Ok(Box::new(
                piper_plus_g2p::multilingual::PassthroughPhonemizer::new(lang),
            )),
        }
    }

    /// EnglishPhonemizer を生成する (piper-g2p)。
    ///
    /// CMU辞書を以下の順で検索:
    /// 1. `CMUDICT_PATH` 環境変数
    /// 2. `{model_dir}/cmudict_data.json`
    /// 3. `./cmudict_data.json`
    /// 4. `/usr/share/piper/cmudict_data.json`
    fn create_english_phonemizer(
        model_dir: Option<&Path>,
    ) -> Result<piper_plus_g2p::english::EnglishPhonemizer, PiperError> {
        // Try model_dir first if available
        if let Some(dir) = model_dir {
            let model_dict = dir.join("cmudict_data.json");
            if model_dict.exists() {
                return piper_plus_g2p::english::EnglishPhonemizer::new_with_dict(&model_dict)
                    .map_err(PiperError::from);
            }
        }
        // Fall back to default search (env var, local, system)
        piper_plus_g2p::english::EnglishPhonemizer::new().map_err(PiperError::from)
    }

    /// ChinesePhonemizer を生成する (piper-g2p)。
    ///
    /// Pinyin辞書を以下の順で検索:
    /// 1. `PINYIN_SINGLE_PATH` / `PINYIN_PHRASES_PATH` 環境変数
    /// 2. `{model_dir}/pinyin_single.json` + `{model_dir}/pinyin_phrases.json`
    /// 3. `./pinyin_single.json` + `./pinyin_phrases.json`
    fn create_chinese_phonemizer(
        model_dir: Option<&Path>,
    ) -> Result<piper_plus_g2p::chinese::ChinesePhonemizer, PiperError> {
        // 1. Environment variable override
        if let (Ok(single), Ok(phrases)) = (
            std::env::var("PINYIN_SINGLE_PATH"),
            std::env::var("PINYIN_PHRASES_PATH"),
        ) {
            let sp = std::path::PathBuf::from(&single);
            let pp = std::path::PathBuf::from(&phrases);
            if sp.exists() && pp.exists() {
                return piper_plus_g2p::chinese::ChinesePhonemizer::new(&sp, &pp)
                    .map_err(PiperError::from);
            }
        }

        // 2. model_dir
        if let Some(dir) = model_dir {
            let single = dir.join("pinyin_single.json");
            let phrases = dir.join("pinyin_phrases.json");
            if single.exists() && phrases.exists() {
                return piper_plus_g2p::chinese::ChinesePhonemizer::new(&single, &phrases)
                    .map_err(PiperError::from);
            }
        }

        // 3. Local development path
        let single = std::path::PathBuf::from("pinyin_single.json");
        let phrases = std::path::PathBuf::from("pinyin_phrases.json");
        if single.exists() && phrases.exists() {
            return piper_plus_g2p::chinese::ChinesePhonemizer::new(&single, &phrases)
                .map_err(PiperError::from);
        }

        Err(PiperError::DictionaryLoad {
            path: "pinyin_single.json / pinyin_phrases.json not found. \
                   Place dictionaries next to the model or set PINYIN_SINGLE_PATH / PINYIN_PHRASES_PATH env vars"
                .to_string(),
        })
    }

    /// テキストを音声に変換 (`SynthesisParams` 版)
    ///
    /// `SynthesisParams` で合成パラメータをまとめて指定する新 API。
    /// `..Default::default()` パターンで、変更したいフィールドだけ指定できる。
    ///
    /// 短いテキスト (空白除く10文字以下) には自動的に Strategy C
    /// (SSML `<break>` ラップ) を適用する。
    ///
    /// # Examples
    ///
    /// ```ignore
    /// let result = voice.synthesize_with_params("こんにちは", &SynthesisParams {
    ///     speaker_id: Some(0),
    ///     language_override: Some("ja".into()),
    ///     ..Default::default()
    /// })?;
    /// ```
    pub fn synthesize_with_params(
        &mut self,
        text: &str,
        params: &SynthesisParams,
    ) -> Result<SynthesisResult, PiperError> {
        // Strategy C: 短テキストを SSML <break> でラップ
        let effective_text = crate::short_text::wrap_short_text_ssml(text);
        let text_ref = effective_text.as_str();

        // 1. Phonemize: テキストをトークン列 + プロソディ情報に変換
        let (tokens, prosody) = self.phonemizer.phonemize_with_prosody(text_ref)?;

        // 2. Convert tokens to IDs using phoneme_id_map
        let phoneme_id_map = self
            .phonemizer
            .get_phoneme_id_map()
            .unwrap_or(&self.config.phoneme_id_map);

        let ids = piper_plus_g2p::encode::tokens_to_ids(&tokens, phoneme_id_map)
            .map_err(PiperError::from)?;
        let prosody_feats = prosody_to_optional_features(&prosody);

        // 3. Post-process IDs (BOS/EOS/padding insertion, language-specific)
        let (ids, prosody_feats) =
            self.phonemizer
                .post_process_ids(ids, prosody_feats, phoneme_id_map);

        // 4. Build prosody tensor directly from post-processed features
        //    (single pass: Option<ProsodyFeature>[] → Option<Vec<ProsodyFeature>>)
        let prosody_tensor = build_prosody_tensor(&prosody_feats);

        // 5. Determine language_id from config
        //    language_override が指定されていればそちらを優先。
        //    多言語モデルの場合、テキストの最初の言語セグメントを自動検出して language_id を決定。
        //    単言語モデルの場合は phonemizer の言語コードを使用。
        let language_id = if self.config.needs_lid() {
            let lang_code = if let Some(ref ovr) = params.language_override {
                ovr.as_str()
            } else {
                self.detect_language(text)
            };
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

        // 6. Build request and run inference
        let request = SynthesisRequest {
            phoneme_ids: ids,
            prosody_features: prosody_tensor,
            speaker_id: params.speaker_id,
            language_id,
            noise_scale: params.noise_scale,
            length_scale: params.length_scale,
            noise_w: params.noise_w,
            speaker_embedding: params.speaker_embedding.clone(),
        };

        self.engine.synthesize(&request)
    }

    /// テキストを音声に変換 (旧 API)
    ///
    /// `language_override` を指定すると、phonemizer の自動検出を上書きして
    /// 指定言語の language_id を使用する。多言語モデルで特定言語を強制する場合に使用。
    #[deprecated(
        since = "1.14.0",
        note = "Use `synthesize_with_params()` with `SynthesisParams` instead"
    )]
    pub fn synthesize_text(
        &mut self,
        text: &str,
        speaker_id: Option<i64>,
        language_override: Option<&str>,
        noise_scale: f32,
        length_scale: f32,
        noise_w: f32,
    ) -> Result<SynthesisResult, PiperError> {
        self.synthesize_with_params(
            text,
            &SynthesisParams {
                speaker_id,
                language_override: language_override.map(String::from),
                noise_scale,
                length_scale,
                noise_w,
                ..Default::default()
            },
        )
    }

    /// テキストを音素化して phoneme IDs を返す (ONNX 推論なし)
    ///
    /// `--test-mode` (CI用) で phonemization パイプラインのみ検証する場合に使用。
    pub fn phonemize_to_ids(&self, text: &str) -> Result<Vec<i64>, PiperError> {
        let (tokens, prosody) = self.phonemizer.phonemize_with_prosody(text)?;

        let phoneme_id_map = self
            .phonemizer
            .get_phoneme_id_map()
            .unwrap_or(&self.config.phoneme_id_map);

        let ids = piper_plus_g2p::encode::tokens_to_ids(&tokens, phoneme_id_map)
            .map_err(PiperError::from)?;
        let prosody_feats = prosody_to_optional_features(&prosody);

        let (ids, _prosody_feats) =
            self.phonemizer
                .post_process_ids(ids, prosody_feats, phoneme_id_map);

        Ok(ids)
    }

    /// テキストを WAV ファイルに出力 (デフォルトパラメータ使用)
    pub fn text_to_wav_file(
        &mut self,
        text: &str,
        output: &Path,
        speaker_id: Option<i64>,
    ) -> Result<SynthesisResult, PiperError> {
        let result = self.synthesize_with_params(
            text,
            &SynthesisParams {
                speaker_id,
                ..Default::default()
            },
        )?;
        crate::audio::write_wav(output, result.sample_rate, &result.audio)?;
        Ok(result)
    }

    /// テキストの主要言語を検出する。
    ///
    /// 多言語/バイリンガルモデルの場合、`MultilingualPhonemizer` の
    /// `detect_primary_language` を使用して最初の言語セグメントを検出。
    /// 単言語モデルの場合は phonemizer の `language_code()` にフォールバック。
    fn detect_language(&self, text: &str) -> &str {
        self.phonemizer.detect_primary_language(text)
    }

    /// JapanesePhonemizer を生成する (piper-g2p)。
    ///
    /// `naist-jdic` feature が有効なら bundled 辞書を使用し、
    /// 無効なら `dictionary_manager::ensure_dictionary()` で外部辞書を
    /// 自動検索・ダウンロードする。
    #[cfg(feature = "japanese")]
    fn create_japanese_phonemizer()
    -> Result<piper_plus_g2p::japanese::JapanesePhonemizer, PiperError> {
        #[cfg(feature = "naist-jdic")]
        {
            piper_plus_g2p::japanese::JapanesePhonemizer::new_bundled().map_err(PiperError::from)
        }
        #[cfg(not(feature = "naist-jdic"))]
        {
            // Try dictionary_manager first (searches standard paths + auto-download)
            match crate::dictionary_manager::ensure_dictionary() {
                Ok(dict_path) => {
                    tracing::info!("Using OpenJTalk dictionary from {}", dict_path.display());
                    piper_plus_g2p::japanese::JapanesePhonemizer::new_with_dict(&dict_path)
                        .map_err(PiperError::from)
                }
                Err(e) => {
                    tracing::warn!(
                        "dictionary_manager failed ({}), falling back to JapanesePhonemizer::new()",
                        e
                    );
                    // Fall back to jpreprocess's own dictionary search
                    piper_plus_g2p::japanese::JapanesePhonemizer::new().map_err(PiperError::from)
                }
            }
        }
    }

    /// ORT warmup をこの Voice インスタンスで実行する。
    pub fn warmup(&mut self, runs: usize) -> Result<(), PiperError> {
        self.engine.warmup(runs)
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
        Some(features.iter().map(|p| p.unwrap_or([0, 0, 0])).collect())
    } else {
        None
    }
}

/// ProsodyInfo 列から ONNX 入力用の Option<Vec<[i32; 3]>> に直接変換する。
///
/// `prosody_to_optional_features` + `build_prosody_tensor` を 1 パスに統合。
/// 中間の `Vec<Option<[i32; 3]>>` を生成せず、いずれかが Some なら
/// Some(Vec<[i32; 3]>) を返す。全て None なら None を返す。
#[cfg(test)]
fn build_prosody_direct(
    prosody: &[Option<crate::phonemize::ProsodyInfo>],
) -> Option<Vec<crate::phonemize::ProsodyFeature>> {
    if prosody.iter().any(|p| p.is_some()) {
        Some(
            prosody
                .iter()
                .map(|p| match p {
                    Some(info) => [info.a1, info.a2, info.a3],
                    None => [0, 0, 0],
                })
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
        let result = PiperVoice::load(Path::new("/nonexistent/model.onnx"), None, "cpu");
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
        match expect_err(PiperVoice::create_phonemizer(&config, None)) {
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
    fn test_create_phonemizer_bilingual_empty_language_id_map() {
        // Bilingual with empty language_id_map should return InvalidConfig
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
        match expect_err(PiperVoice::create_phonemizer(&config, None)) {
            PiperError::InvalidConfig { reason } => {
                assert!(
                    reason.contains("language_id_map"),
                    "expected 'language_id_map' in reason, got: {reason}"
                );
            }
            other => panic!("expected InvalidConfig, got: {other:?}"),
        }
    }

    #[test]
    fn test_create_phonemizer_bilingual_success() {
        // Bilingual with populated language_id_map should succeed
        // Uses en+es (no "ja") to avoid NAIST-JDIC dependency in tests
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 330,
            num_symbols: 97,
            phoneme_type: PhonemeType::Bilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("en".into(), 0i64), ("es".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());
        let phonemizer = result.unwrap();
        // MultilingualPhonemizer returns default_latin_language as language_code
        assert_eq!(phonemizer.language_code(), "en");
    }

    #[test]
    fn test_create_phonemizer_multilingual_success() {
        // Multilingual with populated language_id_map should succeed
        // Uses en+zh+es+fr+pt (no "ja") to avoid NAIST-JDIC dependency in tests
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 571,
            num_symbols: 173,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 5,
            language_id_map: [
                ("en".into(), 0i64),
                ("zh".into(), 1),
                ("es".into(), 2),
                ("fr".into(), 3),
                ("pt".into(), 4),
            ]
            .into_iter()
            .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());
        let phonemizer = result.unwrap();
        assert_eq!(phonemizer.language_code(), "en");
    }

    #[test]
    fn test_create_phonemizer_multilingual_empty_language_id_map() {
        // Multilingual with empty language_id_map should return InvalidConfig
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 571,
            num_symbols: 173,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 6,
            language_id_map: HashMap::new(),
            speaker_id_map: HashMap::new(),
        };
        match expect_err(PiperVoice::create_phonemizer(&config, None)) {
            PiperError::InvalidConfig { reason } => {
                assert!(
                    reason.contains("language_id_map"),
                    "expected 'language_id_map' in reason, got: {reason}"
                );
            }
            other => panic!("expected InvalidConfig, got: {other:?}"),
        }
    }

    #[test]
    fn test_create_phonemizer_multilingual_default_latin_fallback() {
        // When 'en' is not in language_id_map, should fall back to es/fr/pt
        // Uses zh+es (no "ja" or "en") to test fallback
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 100,
            num_symbols: 100,
            phoneme_type: PhonemeType::Multilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("zh".into(), 0i64), ("es".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let result = PiperVoice::create_phonemizer(&config, None);
        assert!(result.is_ok(), "expected Ok, got: {:?}", result.err());
        let phonemizer = result.unwrap();
        // Should fall back to "es" as the default Latin language
        assert_eq!(phonemizer.language_code(), "es");
    }

    #[test]
    fn test_create_phonemizer_multilingual_detect_language() {
        // Test that detect_primary_language works through the trait
        // Uses en+zh (no "ja") to avoid NAIST-JDIC dependency
        let config = VoiceConfig {
            audio: Default::default(),
            num_speakers: 330,
            num_symbols: 97,
            phoneme_type: PhonemeType::Bilingual,
            phoneme_id_map: HashMap::new(),
            num_languages: 2,
            language_id_map: [("en".into(), 0i64), ("zh".into(), 1)]
                .into_iter()
                .collect(),
            speaker_id_map: HashMap::new(),
        };
        let phonemizer = PiperVoice::create_phonemizer(&config, None).unwrap();
        // English text should be detected as "en"
        assert_eq!(phonemizer.detect_primary_language("Hello world"), "en");
        // Chinese text should be detected as "zh"
        assert_eq!(phonemizer.detect_primary_language("你好世界"), "zh");
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
        match expect_err(PiperVoice::create_phonemizer(&config, None)) {
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
        assert_eq!(config.language_id_map.get("ko").copied().unwrap_or(0), 0);
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
            speaker_embedding: None,
        };
        assert_eq!(request.phoneme_ids, ids);
        assert!(request.prosody_features.is_none());
        assert_eq!(request.speaker_id, Some(0));
        assert!(request.language_id.is_none());
        assert!(request.speaker_embedding.is_none());
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
            speaker_embedding: None,
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
            speaker_embedding: None,
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
            Some(ProsodyInfo {
                a1: -2,
                a2: 1,
                a3: 5,
            }),
            None,
            Some(ProsodyInfo {
                a1: 0,
                a2: 3,
                a3: 5,
            }),
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
        let features = vec![Some([-2, 1, 5]), None, Some([0, 3, 5])];
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
    // 6. build_prosody_direct (consolidated single-pass conversion)
    // -----------------------------------------------------------------------
    #[test]
    fn test_build_prosody_direct_with_some() {
        let prosody = vec![
            Some(ProsodyInfo {
                a1: -2,
                a2: 1,
                a3: 5,
            }),
            None,
            Some(ProsodyInfo {
                a1: 0,
                a2: 3,
                a3: 5,
            }),
        ];
        let tensor = build_prosody_direct(&prosody);
        assert!(tensor.is_some());
        let t = tensor.unwrap();
        assert_eq!(t.len(), 3);
        assert_eq!(t[0], [-2, 1, 5]);
        assert_eq!(t[1], [0, 0, 0]); // None -> zero-filled
        assert_eq!(t[2], [0, 3, 5]);
    }

    #[test]
    fn test_build_prosody_direct_all_none() {
        let prosody: Vec<Option<ProsodyInfo>> = vec![None, None];
        let tensor = build_prosody_direct(&prosody);
        assert!(tensor.is_none());
    }

    #[test]
    fn test_build_prosody_direct_empty() {
        let prosody: Vec<Option<ProsodyInfo>> = vec![];
        let tensor = build_prosody_direct(&prosody);
        assert!(tensor.is_none());
    }

    #[test]
    fn test_build_prosody_direct_matches_two_step() {
        // Verify build_prosody_direct produces the same result as
        // prosody_to_optional_features + build_prosody_tensor
        let prosody = vec![
            Some(ProsodyInfo {
                a1: 1,
                a2: 2,
                a3: 3,
            }),
            None,
            Some(ProsodyInfo {
                a1: -1,
                a2: 0,
                a3: 7,
            }),
            None,
        ];
        let two_step = build_prosody_tensor(&prosody_to_optional_features(&prosody));
        let direct = build_prosody_direct(&prosody);
        assert_eq!(two_step, direct);
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
        let ids = piper_plus_g2p::encode::tokens_to_ids(&tokens, &id_map)
            .map_err(PiperError::from)
            .unwrap();
        assert_eq!(ids, vec![5, 10, 15]);
    }

    #[test]
    fn test_tokens_to_ids_unknown_phoneme() {
        let id_map: HashMap<String, Vec<i64>> = HashMap::new();
        let tokens: Vec<String> = vec!["xyz".into()];
        let result =
            piper_plus_g2p::encode::tokens_to_ids(&tokens, &id_map).map_err(PiperError::from);
        assert!(result.is_err());
        match result.unwrap_err() {
            PiperError::PhonemeIdNotFound { phoneme } => {
                assert_eq!(phoneme, "xyz");
            }
            other => panic!("expected PhonemeIdNotFound, got: {other:?}"),
        }
    }

    // -----------------------------------------------------------------------
    // phonemize_to_ids — cannot be unit-tested without an ONNX model
    // -----------------------------------------------------------------------
    // `PiperVoice::phonemize_to_ids` requires a fully initialized `PiperVoice`
    // (ONNX engine + config), so it cannot be unit-tested without a real model
    // file. Its internals are covered by the component tests above:
    //   - phonemize_with_prosody: tested via language-specific phonemizer tests
    //   - tokens_to_ids: tested in phoneme_converter::tests and above
    //   - post_process_ids: tested in phonemizer trait tests
    // End-to-end testing of phonemize_to_ids is done via integration tests
    // (test_custom_dict_integration.rs) and CLI --test-mode.

    // -----------------------------------------------------------------------
    // 7. SynthesisParams default values and construction
    // -----------------------------------------------------------------------
    #[test]
    fn test_synthesis_params_default() {
        let params = SynthesisParams::default();
        assert!(params.speaker_id.is_none());
        assert!(params.language_override.is_none());
        assert!((params.noise_scale - 0.667).abs() < 1e-6);
        assert!((params.length_scale - 1.0).abs() < 1e-6);
        assert!((params.noise_w - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_params_partial_override() {
        let params = SynthesisParams {
            speaker_id: Some(42),
            language_override: Some("ja".into()),
            ..Default::default()
        };
        assert_eq!(params.speaker_id, Some(42));
        assert_eq!(params.language_override.as_deref(), Some("ja"));
        // Other fields should be default
        assert!((params.noise_scale - 0.667).abs() < 1e-6);
        assert!((params.length_scale - 1.0).abs() < 1e-6);
        assert!((params.noise_w - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_params_full_override() {
        let params = SynthesisParams {
            speaker_id: Some(5),
            language_override: Some("en".into()),
            noise_scale: 0.333,
            length_scale: 1.5,
            noise_w: 0.5,
            speaker_embedding: None,
        };
        assert_eq!(params.speaker_id, Some(5));
        assert_eq!(params.language_override.as_deref(), Some("en"));
        assert!((params.noise_scale - 0.333).abs() < 1e-6);
        assert!((params.length_scale - 1.5).abs() < 1e-6);
        assert!((params.noise_w - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_params_clone() {
        let params = SynthesisParams {
            speaker_id: Some(1),
            language_override: Some("zh".into()),
            ..Default::default()
        };
        let cloned = params.clone();
        assert_eq!(cloned.speaker_id, params.speaker_id);
        assert_eq!(cloned.language_override, params.language_override);
        assert!((cloned.noise_scale - params.noise_scale).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_params_debug() {
        let params = SynthesisParams::default();
        let debug = format!("{:?}", params);
        assert!(debug.contains("SynthesisParams"));
        assert!(debug.contains("noise_scale"));
    }
}
