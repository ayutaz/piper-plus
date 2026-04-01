//! Core [`Phonemizer`] trait, [`PhonemizerRegistry`], and shared types
//! ([`ProsodyInfo`], [`ProsodyFeature`], [`PhonemeIdMap`]).
//!
//! Each language module (e.g. [`crate::english`], [`crate::chinese`])
//! provides a concrete implementation of [`Phonemizer`].

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

/// Maximum input text length (characters).
const MAX_INPUT_LENGTH: usize = 10_000;

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

    /// Validate and sanitize input text.
    ///
    /// Default implementation checks length and strips control characters.
    /// Returns sanitized text or error.
    fn validate_input(&self, text: &str) -> Result<String, G2pError> {
        if text.len() > MAX_INPUT_LENGTH {
            return Err(G2pError::Phonemize(format!(
                "input too long: {} chars (max {})",
                text.chars().count(),
                MAX_INPUT_LENGTH
            )));
        }
        // Strip control characters (keep \n, \t, \r)
        let sanitized: String = text
            .chars()
            .filter(|c| !c.is_control() || *c == '\n' || *c == '\t' || *c == '\r')
            .collect();
        Ok(sanitized)
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
