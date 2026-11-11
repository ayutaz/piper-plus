//! Core [`Phonemizer`] trait, [`PhonemizerRegistry`], and shared types
//! ([`ProsodyInfo`], [`ProsodyFeature`], [`PhonemeIdMap`]).
//!
//! Each language module (e.g. [`crate::english`], [`crate::chinese`])
//! provides a concrete implementation of [`Phonemizer`].

use std::borrow::Cow;
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

    /// Like [`Self::phonemize_with_prosody`], for text in `language`.
    ///
    /// Multilingual phonemizers still split the text by script, but assign
    /// Latin-script text to `language`: es / fr / pt / sv cannot be told apart
    /// from English by their letters. The default ignores `language`.
    fn phonemize_with_language(
        &self,
        text: &str,
        _language: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError> {
        self.phonemize_with_prosody(text)
    }

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
    ///
    /// The phonemizers of this crate strip control characters themselves
    /// (see `strip_control_chars`) and set no length limit; this method is
    /// for callers that want the limit too.
    fn validate_input(&self, text: &str) -> Result<String, G2pError> {
        let chars = text.chars().count();
        if chars > MAX_INPUT_LENGTH {
            return Err(G2pError::Phonemize(format!(
                "input too long: {chars} chars (max {MAX_INPUT_LENGTH})"
            )));
        }
        Ok(strip_control_chars(text).into_owned())
    }

    /// Toggle the ZH-EN code-switching dispatch (Issue #384).
    ///
    /// Default is a no-op so single-language phonemizers don't have to know
    /// about it. `MultilingualPhonemizer` overrides this when the `chinese`
    /// feature is enabled, routing English-adjacent-to-Chinese segments
    /// through the loanword path.
    fn set_zh_en_dispatch(&mut self, _enabled: bool) {}

    /// Returns whether the ZH-EN dispatch is currently enabled.
    /// Default is `false` for phonemizers that don't implement the toggle.
    fn is_zh_en_dispatch_enabled(&self) -> bool {
        false
    }
}

/// Strip Unicode control characters (category Cc) except `\n`, `\t` and `\r`.
///
/// Every phonemizer of this crate calls it first
/// (`docs/spec/input-sanitize-contract.toml`). Format characters (U+200D,
/// U+FEFF), separators (U+2028) and NBSP are kept. Returns the input
/// unchanged, without allocating, when there is nothing to strip.
pub(crate) fn strip_control_chars(text: &str) -> Cow<'_, str> {
    let stripped = |c: char| c.is_control() && !matches!(c, '\n' | '\t' | '\r');
    if text.chars().any(stripped) {
        Cow::Owned(text.chars().filter(|&c| !stripped(c)).collect())
    } else {
        Cow::Borrowed(text)
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
