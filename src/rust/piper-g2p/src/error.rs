//! G2P-specific error types.

use thiserror::Error;

/// G2P error type, independent of piper-core's `PiperError`.
#[derive(Error, Debug)]
pub enum G2pError {
    #[error("unsupported language: {code}")]
    UnsupportedLanguage { code: String },

    #[error("unknown phoneme: {phoneme}")]
    UnknownPhoneme { phoneme: String },

    #[error("phonemization error: {0}")]
    Phonemize(String),

    #[error("dictionary load error: {path}")]
    DictionaryLoad { path: String },

    #[error("phoneme ID not found: {phoneme}")]
    PhonemeIdNotFound { phoneme: String },

    #[error("label parse error: {0}")]
    LabelParse(String),

    #[error("jpreprocess initialization error: {0}")]
    JPreprocessInit(String),
}
