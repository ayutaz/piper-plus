//! Model-specific tokenization of already-transcribed IPA.
use crate::{G2pError, PhonemeIdMap};

/// Splits IPA using only the target model's supported token spellings.
pub struct IpaTokenizer;

impl IpaTokenizer {
    /// Build a tokenizer from a model's phoneme ID map.
    pub fn new(_id_map: &PhonemeIdMap) -> Self {
        Self
    }

    /// Tokenize a nonempty IPA string without running a language G2P backend.
    pub fn tokenize(&self, _ipa: &str) -> Result<Vec<String>, G2pError> {
        Err(G2pError::Phonemize("IPA input is not implemented".into()))
    }
}
