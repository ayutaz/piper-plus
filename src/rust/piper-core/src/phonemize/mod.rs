//! Phonemizer trait and language registry.
//!
//! Phase 1 (MVP) ではテキスト音素化は未実装。
//! JSONL 入力で phoneme_ids を直接受け取る。

use std::collections::HashMap;

use crate::config::PhonemeIdMap;
use crate::error::PiperError;

pub mod token_map;

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
