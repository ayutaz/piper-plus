//! End-to-end zero-shot TTS inference tests.
//!
//! These tests load the real ONNX model from `test/models/zero-shot-test.onnx`
//! and exercise `OnnxEngine::synthesize()` with a `speaker_embedding` input,
//! verifying that the engine:
//!
//! - produces non-empty, finite audio samples
//! - produces different audio for different speaker embeddings
//! - does not panic on an all-zeros embedding
//!
//! The tests are gated on the `onnx` feature and gracefully skip when the
//! model files are absent (via `assets_available()`).  Run with:
//!
//! ```sh
//! cargo test --test test_zero_shot_e2e --features onnx
//! ```

#![cfg(feature = "onnx")]

use std::path::PathBuf;

use piper_plus::config::VoiceConfig;
use piper_plus::{OnnxEngine, SynthesisRequest};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Resolve a path relative to the repository root.
///
/// `CARGO_MANIFEST_DIR` for `piper-core` is `src/rust/piper-core`.
/// Three `.parent()` calls reach the repo root.
fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap() // piper-core -> src/rust
        .parent()
        .unwrap() // src/rust -> src
        .parent()
        .unwrap() // src -> repo root
        .to_path_buf()
}

fn model_path() -> PathBuf {
    repo_root()
        .join("test")
        .join("models")
        .join("zero-shot-test.onnx")
}

fn config_path() -> PathBuf {
    repo_root()
        .join("test")
        .join("models")
        .join("zero-shot-test.onnx.json")
}

fn npy_path() -> PathBuf {
    repo_root()
        .join("test")
        .join("models")
        .join("test_speaker.npy")
}

/// Return `true` only when all three test asset files exist.
fn assets_available() -> bool {
    model_path().exists() && config_path().exists() && npy_path().exists()
}

/// Load an `OnnxEngine` from the test model.
fn load_engine() -> OnnxEngine {
    let config =
        VoiceConfig::load(&config_path()).expect("Failed to load VoiceConfig from test config");
    OnnxEngine::load(&model_path(), &config, "cpu")
        .expect("Failed to load OnnxEngine from test model")
}

/// Parse a NumPy v1.0 `.npy` file containing a 1-D float32 array.
///
/// Layout: `\x93NUMPY` (6 B) + major (1 B) + minor (1 B) +
///         header_len (2 B LE) + header (header_len B) + data
///
/// Returns the raw `f32` values.
fn load_npy_f32(path: &std::path::Path) -> Vec<f32> {
    let bytes =
        std::fs::read(path).unwrap_or_else(|e| panic!("Failed to read {}: {}", path.display(), e));

    // Verify the NumPy magic bytes.
    assert!(
        bytes.starts_with(b"\x93NUMPY"),
        "File does not start with NumPy magic"
    );

    // Bytes 8-9 (LE u16) encode the length of the ASCII header dict.
    let header_len = u16::from_le_bytes([bytes[8], bytes[9]]) as usize;
    let data_offset = 10 + header_len;

    let data_bytes = &bytes[data_offset..];
    assert_eq!(
        data_bytes.len() % 4,
        0,
        "Data section length is not a multiple of 4"
    );

    data_bytes
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect()
}

/// Build a minimal `SynthesisRequest` long enough to avoid the short-text
/// padding path (MIN_PHONEME_IDS = 40).
///
/// We use IDs [1, 8, 8, …, 8, 2] where 1 = BOS, 2 = EOS, 8 = mid phoneme.
fn make_request(embedding: Option<Vec<f32>>) -> SynthesisRequest {
    const N: usize = 50;
    let mut ids = vec![8i64; N];
    ids[0] = 1; // BOS
    ids[N - 1] = 2; // EOS

    SynthesisRequest {
        phoneme_ids: ids,
        speaker_embedding: embedding,
        noise_scale: 0.4,
        noise_w: 0.5,
        length_scale: 1.0,
        ..SynthesisRequest::default()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

/// Load the zero-shot model and synthesize audio with a real speaker embedding
/// loaded from `test_speaker.npy`.
///
/// Verifies:
/// - Output audio is non-empty.
/// - Every sample is finite (no NaN / ±Inf).
#[test]
fn test_zero_shot_inference_produces_audio() {
    if !assets_available() {
        eprintln!("SKIP: test model assets not found");
        return;
    }

    let embedding = load_npy_f32(&npy_path());
    assert_eq!(embedding.len(), 192, "Expected 192-dimensional embedding");

    let mut engine = load_engine();
    let request = make_request(Some(embedding));
    let result = engine
        .synthesize(&request)
        .expect("synthesize() should not fail");

    assert!(!result.audio.is_empty(), "Audio output must be non-empty");
    assert!(
        result.audio.iter().all(|&s| (s as f32).is_finite()),
        "All audio samples must be finite"
    );
    assert!(result.sample_rate > 0, "sample_rate must be positive");
    assert!(
        result.audio_seconds > 0.0,
        "audio_seconds must be positive, got {}",
        result.audio_seconds
    );
}

/// Verify that two different speaker embeddings produce different audio output.
///
/// A zero-shot model must condition its output on the speaker embedding;
/// if both outputs were identical the speaker encoder would be non-functional.
#[test]
fn test_zero_shot_different_embeddings_produce_different_audio() {
    if !assets_available() {
        eprintln!("SKIP: test model assets not found");
        return;
    }

    let emb1 = load_npy_f32(&npy_path());
    assert_eq!(emb1.len(), 192);

    // Create a clearly different embedding by negating all values.
    let emb2: Vec<f32> = emb1.iter().map(|v| -v).collect();

    let mut engine = load_engine();

    let result1 = engine
        .synthesize(&make_request(Some(emb1)))
        .expect("synthesize() with emb1 should not fail");

    let result2 = engine
        .synthesize(&make_request(Some(emb2)))
        .expect("synthesize() with emb2 should not fail");

    // The outputs must differ in at least one sample.  We compare a prefix
    // whose length is the minimum of both outputs to handle variable-length audio.
    let min_len = result1.audio.len().min(result2.audio.len());
    assert!(min_len > 0, "Both outputs must be non-empty");

    let differ = result1.audio[..min_len]
        .iter()
        .zip(result2.audio[..min_len].iter())
        .any(|(a, b)| a != b);

    assert!(
        differ,
        "Audio from different speaker embeddings must differ"
    );
}

/// Verify that synthesizing with an all-zeros speaker embedding does not panic.
///
/// The model logs a warning about the missing embedding and falls back to zeros
/// internally, so passing zeros explicitly is a valid (if degenerate) use-case.
#[test]
fn test_zero_shot_zero_embedding_does_not_crash() {
    if !assets_available() {
        eprintln!("SKIP: test model assets not found");
        return;
    }

    let zero_emb = vec![0.0f32; 192];

    let mut engine = load_engine();
    let result = engine.synthesize(&make_request(Some(zero_emb)));

    // The call must not panic.  A successful result is ideal; an `Err` is
    // also acceptable (some models reject degenerate inputs), but a panic
    // (including an unwrap inside OnnxEngine) is a failure.
    match result {
        Ok(r) => {
            // If synthesis succeeded, basic sanity checks apply.
            assert!(
                r.audio.is_empty() || r.audio.iter().all(|&s| (s as f32).is_finite()),
                "Audio samples must be finite when zero-embedding synthesis succeeds"
            );
        }
        Err(e) => {
            // A model-level error is acceptable; we only forbid panics.
            eprintln!("zero-embedding synthesis returned Err (acceptable): {e}");
        }
    }
}
