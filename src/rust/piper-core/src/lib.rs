//! Piper-Plus 推論コアライブラリ
//!
//! VITS ベースのニューラル TTS 推論エンジン。
//! ONNX Runtime を使用し、8 言語 G2P (JA/EN/ZH/KO/ES/FR/PT/SV) に対応 (学習済みモデルは 6 言語: ja/en/zh/es/fr/pt)。
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
pub mod input;
#[cfg(feature = "onnx")]
pub mod speaker_encoder;
#[cfg(feature = "onnx")]
pub mod voice;
#[cfg(feature = "onnx")]
pub mod wasm;

// --- Phase 4 modules (推論非依存) ---
pub mod audio_format;
pub mod model_download;
pub mod short_text;
pub mod ssml;
pub mod streaming;
pub mod text_splitter;
pub mod timing;

pub mod playback;

// Re-exports
pub use config::{PhonemeIdMap, PhonemeType, VoiceConfig};
#[cfg(feature = "onnx")]
pub use engine::{
    DEFAULT_WARMUP_RUNS, MIN_BODY_FOR_STRATEGY_A, MIN_PHONEME_IDS, ModelCapabilities, OnnxEngine,
    SynthesisRequest, SynthesisResult, TRIM_EOS_MAX_FRAMES, pad_short_phonemes,
    trim_padding_by_durations,
};
pub use error::PiperError;
pub use phonemize::{ProsodyFeature, ProsodyInfo};
pub use short_text::wrap_short_text_ssml;
#[cfg(feature = "onnx")]
pub use voice::{PiperVoice, SynthesisParams};
