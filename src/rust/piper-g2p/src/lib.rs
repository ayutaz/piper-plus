//! piper-g2p: Multilingual G2P (Grapheme-to-Phoneme) for TTS.
//!
//! eSpeak-ng free, MIT licensed. 7 languages supported.
//!
//! # IPA-first design
//!
//! `Phonemizer::phonemize_with_prosody()` returns clean IPA token lists
//! without BOS/EOS markers or PUA encoding. The encoding step
//! (PUA mapping, phoneme_id_map, BOS/EOS/padding insertion) is handled
//! separately by [`encode`].

pub mod error;
pub mod phonemizer;
pub mod token_map;
pub mod custom_dict;
pub mod encode;

#[cfg(feature = "japanese")]
pub mod japanese;
pub mod english;
pub mod chinese;
pub mod korean;
pub mod spanish;
pub mod french;
pub mod portuguese;
pub mod multilingual;

pub use error::G2pError;
pub use phonemizer::{Phonemizer, PhonemizerRegistry, ProsodyInfo, ProsodyFeature, PhonemeIdMap};
