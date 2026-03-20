//! Piper-Plus 推論コアライブラリ
//!
//! VITS ベースのニューラル TTS 推論エンジン。
//! ONNX Runtime を使用し、7 言語 (JA/EN/ZH/KO/ES/FR/PT) に対応。
//!
//! Phase 4 追加機能:
//! - ストリーミング合成 (`streaming`)
//! - リアルタイム再生 (`playback`, feature-gated)
//! - 音素タイミング (`timing`)
//! - GPU 推論 (`gpu`)
//! - WASM 互換 API (`wasm`)
//! - モデルダウンロード (`model_download`)
//! - 音声フォーマット変換 (`audio_format`)
//! - テキスト分割 (`text_splitter`)
//! - バッチ合成 (`batch`)
//! - デバイス列挙 (`device`)

// --- Core modules ---
pub mod audio;
pub mod config;
pub mod dictionary_manager;
pub mod engine;
pub mod error;
pub mod input;
pub mod phonemize;
pub mod voice;

// --- Phase 4 modules ---
pub mod audio_format;
pub mod batch;
pub mod device;
pub mod gpu;
pub mod model_download;
pub mod streaming;
pub mod text_splitter;
pub mod timing;
pub mod wasm;

pub mod playback;

// Re-exports
pub use config::{PhonemeIdMap, PhonemeType, VoiceConfig};
pub use engine::{ModelCapabilities, OnnxEngine, SynthesisRequest, SynthesisResult};
pub use error::PiperError;
pub use phonemize::{ProsodyFeature, ProsodyInfo};
pub use voice::PiperVoice;
