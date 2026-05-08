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
        // "hej" is 3 graphemes; the rule-based G2P must produce *some* tokens
        // (≥1) and the wrapper must keep tokens / prosody aligned. We avoid
        // pinning a specific phoneme string here because that belongs to the
        // detailed parity tests in `tests/test_swedish_integration.rs`, but we
        // do pin (a) ≥ 1 token, (b) all-non-empty token strings, and (c) a
        // matching prosody slot per token.
        assert!(
            !tokens.is_empty(),
            "should produce phonemes for 'hej', got {:?}",
            tokens
        );
        assert_eq!(
            tokens.len(),
            prosody.len(),
            "tokens and prosody must have same length"
        );
        for (i, t) in tokens.iter().enumerate() {
            assert!(!t.is_empty(), "token[{i}] must not be the empty string");
        }
    }

    #[test]
    fn test_phonemize_sentence() {
        let p = SwedishPhonemizer::new();
        let (tokens, prosody) = p
            .phonemize_with_prosody("God morgon, hur m\u{00e5}r du?")
            .unwrap();
        // A 4-word sentence must produce more tokens than a single word, and
        // at least one whitespace token must survive (word boundary). This is
        // a stronger contract than the previous `!is_empty()` check while
        // still being implementation-neutral.
        let (single, _) = p.phonemize_with_prosody("hej").unwrap();
        assert!(
            tokens.len() > single.len(),
            "4-word sentence ({} tokens) must produce more tokens than 1-word ({} tokens), got tokens={:?}",
            tokens.len(),
            single.len(),
            tokens
        );
        assert!(
            tokens.iter().any(|t| t == " "),
            "multi-word input must yield at least one space token, got {:?}",
            tokens
        );
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
        let (out_ids, out_prosody) = p.post_process_ids(ids, prosody, &id_map);

        // Pin the exact intersperse pattern the trait emits today so any
        // accidental reordering (e.g. dropping BOS, swapping pad/phoneme) is
        // caught by CI rather than only at runtime.
        // Expected layout for 3 phoneme IDs:
        //   ^ _ 10 _ 20 _ 30 _ $
        assert_eq!(
            out_ids,
            vec![1, 0, 10, 0, 20, 0, 30, 0, 2],
            "BOS + pad-interspersed phonemes + EOS sequence drifted"
        );
        assert_eq!(
            out_prosody.len(),
            out_ids.len(),
            "prosody must stay aligned with ids after post_process_ids"
        );
        // BOS / EOS / pad slots all have `None` prosody — verify the
        // out_prosody vec is fully None to lock down current behavior.
        assert!(
            out_prosody.iter().all(|p| p.is_none()),
            "all prosody slots must be None after intersperse; got {:?}",
            out_prosody
        );
    }
}
