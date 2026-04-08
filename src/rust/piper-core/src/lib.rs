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

// --- Core modules (常に有効) ---
pub mod audio;
pub mod config;
pub mod dictionary_manager;
pub mod error;
pub mod phonemize;

// --- Inference-dependent modules ---
#[cfg(feature = "onnx")]
pub mod batch;
#[cfg(feature = "onnx")]
pub mod device;
#[cfg(feature = "onnx")]
pub mod engine;
#[cfg(feature = "onnx")]
pub mod gpu;
#[cfg(feature = "onnx")]
pub mod speaker_encoder;
#[cfg(feature = "onnx")]
pub mod input;
#[cfg(feature = "onnx")]
pub mod voice;
#[cfg(feature = "onnx")]
pub mod wasm;

// --- Phase 4 modules (推論非依存) ---
pub mod audio_format;
pub mod model_download;
pub mod streaming;
pub mod text_splitter;
pub mod timing;

pub mod playback;

// Re-exports
pub use config::{PhonemeIdMap, PhonemeType, VoiceConfig};
#[cfg(feature = "onnx")]
pub use engine::{
    DEFAULT_WARMUP_RUNS, ModelCapabilities, OnnxEngine, SynthesisRequest, SynthesisResult,
};
pub use error::PiperError;
pub use phonemize::{ProsodyFeature, ProsodyInfo};
#[cfg(feature = "onnx")]
pub use voice::{PiperVoice, SynthesisParams};
