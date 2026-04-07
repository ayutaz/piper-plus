//! Phonemizer trait, language registry, and language-specific implementations.
//!
//! 8 languages (ja, en, zh, ko, es, fr, pt, sv) + multilingual support.
//! JSONL 入力 (Phase 1) に加え、テキスト直接入力をサポート。

use std::collections::HashMap;

use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// Re-export from piper-g2p for backward compatibility
pub use piper_plus_g2p::G2pError;
pub use piper_plus_g2p::PhonemeIdMap as G2pPhonemeIdMap;

pub mod adapter;
pub mod chinese;
pub use piper_plus_g2p::custom_dict;
pub mod english;
pub mod french;
#[cfg(feature = "japanese")]
pub mod japanese;
pub mod korean;
pub use piper_plus_g2p::multilingual;
pub mod portuguese;
pub mod spanish;
pub mod swedish;
pub use piper_plus_g2p::token_map;

/// プロソディ情報 (言語間で共有)
#[derive(Debug, Clone, Copy)]
pub struct ProsodyInfo {
    pub a1: i32,
    pub a2: i32,
    pub a3: i32,
}

/// プロソディ特徴量 (ONNX 入力用)
pub type ProsodyFeature = [i32; 3];

/// 言語固有の音素化トレイト
pub trait Phonemizer: Send + Sync {
    /// テキストを音素トークン列 + プロソディ情報に変換
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError>;

    /// 言語固有の phoneme_id_map を返す (None なら config.json のものを使用)
    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap>;

    /// BOS/EOS/パディング挿入
    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);

    /// 言語コード ("ja", "en", "zh" 等)
    fn language_code(&self) -> &str;

    /// テキストの主要言語を検出する。
    ///
    /// 多言語対応の phonemizer は最初の言語セグメントの言語コードを返す。
    /// デフォルト実装は `language_code()` を返す (単言語 phonemizer 用)。
    fn detect_primary_language(&self, _text: &str) -> &str {
        self.language_code()
    }
}

/// 言語レジストリ
pub struct PhonemizerRegistry {
    registry: HashMap<String, Box<dyn Phonemizer>>,
}

impl PhonemizerRegistry {
    pub fn new() -> Self {
        Self {
            registry: HashMap::new(),
        }
    }

    pub fn register(&mut self, lang_code: &str, phonemizer: Box<dyn Phonemizer>) {
        self.registry.insert(lang_code.to_string(), phonemizer);
    }

    pub fn get(&self, lang_code: &str) -> Option<&dyn Phonemizer> {
        self.registry.get(lang_code).map(|p| p.as_ref())
    }

    pub fn available_languages(&self) -> Vec<&str> {
        self.registry.keys().map(|s| s.as_str()).collect()
    }
}

impl Default for PhonemizerRegistry {
    fn default() -> Self {
        Self::new()
    }
}
