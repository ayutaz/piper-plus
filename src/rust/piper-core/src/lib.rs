//! Piper-Plus 推論コアライブラリ
//!
//! VITS ベースのニューラル TTS 推論エンジン。
//! ONNX Runtime を使用し、7 言語 (JA/EN/ZH/KO/ES/FR/PT) に対応。

pub mod audio;
pub mod config;
pub mod engine;
pub mod error;
pub mod input;
pub mod phonemize;
pub mod voice;

// Re-exports
pub use config::{PhonemeIdMap, PhonemeType, VoiceConfig};
pub use engine::{ModelCapabilities, OnnxEngine, SynthesisRequest, SynthesisResult};
pub use error::PiperError;
pub use phonemize::{ProsodyFeature, ProsodyInfo};
pub use voice::PiperVoice;
