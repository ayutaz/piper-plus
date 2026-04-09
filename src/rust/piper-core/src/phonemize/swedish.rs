//! Swedish phonemizer for piper-core.
//!
//! Thin wrapper around [`piper_plus_g2p::swedish`] that implements the
//! [`piper_core::phonemize::Phonemizer`](super::Phonemizer) trait
//! (with `PiperError`, `get_phoneme_id_map`, `post_process_ids`).
//!
//! The actual G2P logic lives in the `piper-plus-g2p` crate.

use super::multilingual::default_post_process_ids;
use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// ---------------------------------------------------------------------------
// SwedishPhonemizer
// ---------------------------------------------------------------------------

/// Swedish phonemizer using rule-based G2P.
///
/// Delegates to [`piper_plus_g2p::swedish::phonemize_swedish_with_prosody`]
/// for the actual grapheme-to-phoneme conversion.
pub struct SwedishPhonemizer;

impl SwedishPhonemizer {
    pub fn new() -> Self {
        Self
    }
}

impl Default for SwedishPhonemizer {
    fn default() -> Self {
        Self::new()
    }
}

impl Phonemizer for SwedishPhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        let (tokens, prosody) = piper_plus_g2p::swedish::phonemize_swedish_with_prosody(text);

        // Convert piper_plus_g2p::ProsodyInfo -> piper_core::phonemize::ProsodyInfo
        let prosody = prosody
            .into_iter()
            .map(|opt| {
                opt.map(|p| ProsodyInfo {
                    a1: p.a1,
                    a2: p.a2,
                    a3: p.a3,
                })
            })
            .collect();

        Ok((tokens, prosody))
    }

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> {
        // Swedish uses the phoneme_id_map from config.json
        None
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        // Reuse shared BOS + intersperse padding + EOS logic
        default_post_process_ids(ids, prosody, id_map, "$")
    }

    fn language_code(&self) -> &str {
        "sv"
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_language_code() {
        assert_eq!(SwedishPhonemizer::new().language_code(), "sv");
    }

    #[test]
    fn test_phonemize_basic() {
        let p = SwedishPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("hej").unwrap();
        assert!(!tokens.is_empty(), "should produce phonemes for 'hej'");
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );
    }

    #[test]
    fn test_phonemize_sentence() {
        let p = SwedishPhonemizer::new();
        let (tokens, prosody) = p
            .phonemize_with_prosody("God morgon, hur m\u{00e5}r du?")
            .unwrap();
        assert!(!tokens.is_empty(), "should produce phonemes for a sentence");
        assert_eq!(tokens.len(), prosody.len());
    }

    #[test]
    fn test_phonemize_empty() {
        let p = SwedishPhonemizer::new();
        let (tokens, prosody) = p.phonemize_with_prosody("").unwrap();
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }

    #[test]
    fn test_default_impl() {
        let p = SwedishPhonemizer;
        assert_eq!(p.language_code(), "sv");
    }

    #[test]
    fn test_post_process_ids_bos_eos() {
        use std::collections::HashMap;

        let p = SwedishPhonemizer::new();
        let mut id_map: PhonemeIdMap = HashMap::new();
        id_map.insert("_".to_string(), vec![0]);
        id_map.insert("^".to_string(), vec![1]);
        id_map.insert("$".to_string(), vec![2]);

        let ids = vec![10, 20, 30];
        let prosody = vec![None, None, None];
        let (out_ids, _out_prosody) = p.post_process_ids(ids, prosody, &id_map);

        // Should start with BOS (1) and end with EOS (2)
        assert_eq!(*out_ids.first().unwrap(), 1, "should start with BOS");
        assert_eq!(*out_ids.last().unwrap(), 2, "should end with EOS");
        // Should have padding between phonemes
        assert!(out_ids.len() > 5, "should have BOS + padded phonemes + EOS");
    }
}
