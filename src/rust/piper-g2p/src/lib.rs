//! # piper-g2p
//!
//! Multilingual G2P (Grapheme-to-Phoneme) for TTS — eSpeak-ng free, MIT licensed.
//!
//! ## IPA-first design
//!
//! [`Phonemizer::phonemize_with_prosody()`] returns clean IPA token lists
//! without BOS/EOS markers or PUA encoding. The encoding step
//! (PUA mapping, phoneme_id_map, BOS/EOS/padding insertion) is handled
//! separately by [`encode`].
//!
//! ## Supported languages
//!
//! | Language   | Code | Feature flag |
//! |------------|------|--------------|
//! | Japanese   | ja   | `japanese`   |
//! | English    | en   | (default)    |
//! | Chinese    | zh   | (default)    |
//! | Korean     | ko   | (default)    |
//! | Spanish    | es   | (default)    |
//! | French     | fr   | (default)    |
//! | Portuguese | pt   | (default)    |
//!
//! ## Quick start
//!
//! ```rust,no_run
//! use piper_g2p::{Phonemizer, PhonemizerRegistry};
//! use piper_g2p::english::EnglishPhonemizer;
//!
//! // Create a registry and register language phonemizers
//! let mut registry = PhonemizerRegistry::new();
//! let en = EnglishPhonemizer::new().unwrap();
//! registry.register("en", Box::new(en));
//!
//! // Look up a phonemizer by language code
//! let phonemizer = registry.get("en").unwrap();
//!
//! // Phonemize text to IPA tokens with prosody info
//! let (tokens, prosody) = phonemizer
//!     .phonemize_with_prosody("Hello, world!")
//!     .unwrap();
//!
//! // Encode tokens to phoneme IDs using a model's phoneme_id_map
//! // let ids = piper_g2p::encode::tokens_to_ids(&tokens, &phoneme_id_map)?;
//! ```

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
