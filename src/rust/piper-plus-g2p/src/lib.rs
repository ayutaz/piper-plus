//! # piper-plus-g2p
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
//! | Language   | Code | Feature flag   |
//! |------------|------|----------------|
//! | Japanese   | ja   | `japanese`     |
//! | English    | en   | `english` (default) |
//! | Chinese    | zh   | `chinese` (default) |
//! | Korean     | ko   | `korean` (default)  |
//! | Spanish    | es   | `spanish` (default) |
//! | French     | fr   | `french` (default)  |
//! | Portuguese | pt   | `portuguese` (default) |
//! | Swedish    | sv   | `swedish`              |
//!
//! ## Quick start
//!
//! ```rust,ignore
//! use piper_plus_g2p::{Phonemizer, PhonemizerRegistry, PiperEncoder, UnknownTokenMode};
//! use piper_plus_g2p::english::EnglishPhonemizer;
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
//! // let encoder = PiperEncoder::new(phoneme_id_map, UnknownTokenMode::Strict)?;
//! // let ids = encoder.encode(&tokens)?;
//! ```
//!
//! ## Already have IPA? Skip G2P
//!
//! [`PiperEncoder::encode_ipa()`] accepts an IPA string without registering a
//! language. [`IpaTokenizer`] segments it using the target model's vocabulary;
//! unsupported symbols are errors. IDs are model-specific, not universal IPA
//! numbers. PUA mappings and special tokens remain compatible with that model.
//!
//! ```rust
//! use piper_plus_g2p::{PhonemeIdMap, PiperEncoder, UnknownTokenMode};
//!
//! // Illustrative IDs only. In production, deserialize config.json's
//! // phoneme_id_map from the SAME model used for synthesis.
//! let map: PhonemeIdMap = serde_json::from_str(
//!     r#"{"^": [1], "_": [0], "$": [2], "k": [3], "a": [4]}"#,
//! )?;
//! let encoder = PiperEncoder::new(map, UnknownTokenMode::Strict)?;
//! assert_eq!(encoder.encode_ipa("ka")?, vec![1, 0, 3, 0, 4, 0, 2]);
//! # Ok::<(), Box<dyn std::error::Error>>(())
//! ```
//!
//! Longest-match segmentation can be ambiguous (e.g. `an` versus `a`, `n`).
//! Use [`PiperEncoder::encode()`] with explicit tokens to specify boundaries
//! under the existing G2P/PUA encoding convention. Neither API teaches the model
//! new sounds or infers stress/prosody from an IPA transcription.

pub mod custom_dict;
pub mod encode;
pub mod error;
pub mod ipa;
pub mod phonemizer;
pub mod ssml;
pub mod token_map;

#[cfg(feature = "chinese")]
pub mod chinese;
#[cfg(feature = "english")]
pub mod english;
#[cfg(feature = "french")]
pub mod french;
#[cfg(feature = "japanese")]
pub mod japanese;
#[cfg(feature = "korean")]
pub mod korean;
pub mod multilingual;
#[cfg(feature = "portuguese")]
pub mod portuguese;
#[cfg(feature = "spanish")]
pub mod spanish;
#[cfg(feature = "swedish")]
pub mod swedish;

#[cfg(feature = "ffi")]
pub mod ffi;

pub use encode::{PiperEncoder, UnknownTokenMode};
pub use error::G2pError;
pub use ipa::IpaTokenizer;
pub use phonemizer::{PhonemeIdMap, Phonemizer, PhonemizerRegistry, ProsodyFeature, ProsodyInfo};
