//! Model-specific tokenization of already-transcribed IPA.
use crate::token_map::pua_to_token;
use crate::{G2pError, PhonemeIdMap};
use std::collections::HashSet;

/// Splits IPA using only the target model's supported token spellings.
/// This is a literal, greedy tokenizer, not a universal IPA parser. It uses
/// longest-match segmentation over nonempty model keys and the canonical
/// spellings of PUA keys present in that model. It does not normalize Unicode,
/// infer pronunciation, or approximate unsupported sounds. For ambiguous
/// sequences, supply explicit tokens to [`crate::PiperEncoder::encode`].
pub struct IpaTokenizer {
    vocabulary: Vec<String>,
}

impl IpaTokenizer {
    /// Build a tokenizer from a model's phoneme ID map.
    pub fn new(id_map: &PhonemeIdMap) -> Self {
        let mut vocabulary = HashSet::new();
        for (key, ids) in id_map {
            // BOS/EOS/PAD are inserted by the encoder. An underscore within
            // an ordinary internal spelling (e.g. y_vowel) is not padding.
            if key.is_empty() || ids.is_empty() || key == "_" || key.contains(['^', '$']) {
                continue;
            }
            vocabulary.insert(key.clone());
            let mut chars = key.chars();
            if let (Some(ch), None) = (chars.next(), chars.next())
                && let Some(token) = pua_to_token(ch)
            {
                vocabulary.insert(token.to_owned());
            }
        }
        let mut vocabulary: Vec<_> = vocabulary.into_iter().collect();
        // Prefix matches must come after their longer alternatives. The
        // lexical tie-break makes results independent of HashMap iteration.
        vocabulary.sort_by(|a, b| b.len().cmp(&a.len()).then_with(|| a.cmp(b)));
        Self { vocabulary }
    }

    /// Tokenize a nonempty IPA string without running a language G2P backend.
    /// Spaces are word-boundary tokens only when the model supports them;
    /// they are not token separators. Do not include `/.../` or `[...]` wrappers.
    /// Unsupported characters report their UTF-8 byte offset and always fail.
    pub fn tokenize(&self, ipa: &str) -> Result<Vec<String>, G2pError> {
        if ipa.is_empty() {
            return Err(G2pError::Phonemize("IPA input must not be empty".into()));
        }
        let mut tokens = Vec::new();
        let mut offset = 0;
        while offset < ipa.len() {
            let remaining = &ipa[offset..];
            let token = self
                .vocabulary
                .iter()
                .find(|token| remaining.starts_with(token.as_str()))
                .ok_or_else(|| {
                    let symbol = remaining.chars().next().expect("nonempty remainder");
                    G2pError::Phonemize(format!(
                        "unsupported IPA symbol {symbol:?} at byte {offset}"
                    ))
                })?;
            offset += token.len();
            tokens.push(token.clone());
        }
        Ok(tokens)
    }
}
