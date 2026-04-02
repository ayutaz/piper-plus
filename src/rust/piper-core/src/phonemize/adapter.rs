//! Adapter from `piper_plus_g2p::Phonemizer` to `piper_core::phonemize::Phonemizer`.
//!
//! `piper-g2p`'s `Phonemizer` trait is IPA-first: it returns clean token lists
//! without BOS/EOS/padding or `phoneme_id_map` knowledge.  The adapter fills
//! in `get_phoneme_id_map()` (always `None` -- use config.json) and
//! `post_process_ids()` (delegates to `default_post_process_ids` for non-JA
//! languages; no-op for JA which handles markers inline).

use piper_plus_g2p::Phonemizer as G2pPhonemizer;

use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;
use piper_plus_g2p::multilingual::default_post_process_ids;

/// Wraps a `piper_plus_g2p::Phonemizer` so it satisfies
/// `piper_core::phonemize::Phonemizer`.
pub struct G2pAdapter {
    inner: Box<dyn G2pPhonemizer>,
    /// Japanese handles BOS/EOS/padding inline during phonemization,
    /// so `post_process_ids` is a no-op.
    is_japanese: bool,
}

impl G2pAdapter {
    pub fn new(inner: Box<dyn G2pPhonemizer>) -> Self {
        let is_japanese = inner.language_code() == "ja";
        Self { inner, is_japanese }
    }
}

impl Phonemizer for G2pAdapter {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        let (tokens, prosody) = self.inner.phonemize_with_prosody(text)?;

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
        None // All languages use config.json's map
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        if self.is_japanese {
            // No-op: Japanese handles BOS/EOS/padding inline during phonemization.
            (ids, prosody)
        } else {
            default_post_process_ids(ids, prosody, id_map, "$")
        }
    }

    fn language_code(&self) -> &str {
        self.inner.language_code()
    }

    fn detect_primary_language(&self, text: &str) -> &str {
        self.inner.detect_primary_language(text)
    }
}
