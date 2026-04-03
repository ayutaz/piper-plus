use piper_plus_g2p::G2pError;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum PiperError {
    #[error("config file not found: {path}")]
    ConfigNotFound { path: String },

    #[error("invalid config: {reason}")]
    InvalidConfig { reason: String },

    #[error("model load failed: {0}")]
    ModelLoad(String),

    #[error("unsupported language: {code}")]
    UnsupportedLanguage { code: String },

    #[error("unknown phoneme: {phoneme}")]
    UnknownPhoneme { phoneme: String },

    #[error("inference failed: {0}")]
    Inference(String),

    #[error("audio output error: {0}")]
    AudioOutput(#[from] std::io::Error),

    #[error("JSON parse error: {0}")]
    JsonParse(#[from] serde_json::Error),

    #[error("WAV write error: {0}")]
    WavWrite(String),

    #[error("phonemization error: {0}")]
    Phonemize(String),

    #[error("dictionary load error: {path}")]
    DictionaryLoad { path: String },

    #[error("jpreprocess initialization error: {0}")]
    JPreprocessInit(String),

    #[error("label parse error: {0}")]
    LabelParse(String),

    #[error("phoneme ID not found: {phoneme}")]
    PhonemeIdNotFound { phoneme: String },

    // --- Phase 4 error variants ---
    #[error("streaming error: {0}")]
    Streaming(String),

    #[error("playback error: {0}")]
    Playback(String),

    #[error("timing error: {0}")]
    Timing(String),

    #[error("download error: {0}")]
    Download(String),

    #[error("resampling error: {0}")]
    Resample(String),

    #[error("device error: {0}")]
    Device(String),

    #[error("batch processing error: {0}")]
    Batch(String),

    #[error("WASM error: {0}")]
    Wasm(String),
}

impl From<G2pError> for PiperError {
    fn from(e: G2pError) -> Self {
        match e {
            G2pError::UnsupportedLanguage { code } => PiperError::UnsupportedLanguage { code },
            G2pError::UnknownPhoneme { phoneme } => PiperError::UnknownPhoneme { phoneme },
            G2pError::Phonemize(msg) => PiperError::Phonemize(msg),
            G2pError::DictionaryLoad { path } => PiperError::DictionaryLoad { path },
            G2pError::PhonemeIdNotFound { phoneme } => PiperError::PhonemeIdNotFound { phoneme },
            G2pError::LabelParse(msg) => PiperError::LabelParse(msg),
            G2pError::JPreprocessInit(msg) => PiperError::JPreprocessInit(msg),
        }
    }
}
