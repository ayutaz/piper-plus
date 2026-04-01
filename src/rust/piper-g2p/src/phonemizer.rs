//! Phonemizer trait and common types.

use std::collections::HashMap;

use crate::error::G2pError;

/// Phoneme ID map: maps (PUA-encoded) symbol strings to integer ID lists.
pub type PhonemeIdMap = HashMap<String, Vec<i64>>;

/// Prosody information shared across all languages.
#[derive(Debug, Clone, Copy)]
pub struct ProsodyInfo {
    pub a1: i32,
    pub a2: i32,
    pub a3: i32,
}

/// Prosody feature array for ONNX input.
pub type ProsodyFeature = [i32; 3];

/// G2P abstract trait — IPA-first design.
///
/// `phonemize_with_prosody()` returns clean IPA token lists.
/// BOS/EOS/padding/PUA encoding is NOT included — that is
/// the responsibility of [`crate::encode::PiperEncoder`].
///
/// Compared to `piper_core::phonemize::Phonemizer`:
/// - No `get_phoneme_id_map()` (encode responsibility)
/// - No `post_process_ids()` (encode responsibility)
pub trait Phonemizer: Send + Sync {
    /// Convert text to IPA token list + prosody information.
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError>;

    /// Language code (e.g. "ja", "en", "zh").
    fn language_code(&self) -> &str;

    /// Detect the primary language of the given text.
    ///
    /// Multilingual phonemizers may inspect the text to determine
    /// the dominant language. The default returns `language_code()`.
    fn detect_primary_language(&self, _text: &str) -> &str {
        self.language_code()
    }
}

/// Language phonemizer registry.
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
