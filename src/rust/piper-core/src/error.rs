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
}
