//! Execute ONNX inference with both legacy and current speaker dimensions.
#![cfg(feature = "onnx")]

use std::path::PathBuf;

use piper_plus::config::{PhonemeType, VoiceConfig};
use piper_plus::engine::{OnnxEngine, SynthesisRequest};

fn engine(dimension: usize, masked: bool) -> OnnxEngine {
    let model = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/ort_session")
        .join(format!("embedding_{dimension}_{}.onnx", if masked { "masked" } else { "legacy" }));
    assert!(model.is_file(), "Build mandatory ONNX fixtures with tests/fixtures/ort_session/build_embedding_fixture.py");
    let config = VoiceConfig {
        audio: Default::default(),
        num_speakers: 1,
        num_symbols: 50,
        phoneme_type: PhonemeType::Text,
        phoneme_id_map: Default::default(),
        num_languages: 1,
        language_id_map: Default::default(),
        speaker_id_map: Default::default(),
    };
    let engine = OnnxEngine::load(&model, &config, "cpu").expect("load dimension fixture");
    assert_eq!(engine.capabilities().speaker_embedding_dim, dimension);
    engine
}

#[test]
fn zero_embedding_uses_declared_dimension() {
    for dimension in [192, 256] {
        for masked in [false, true] {
            let mut engine = engine(dimension, masked);
            let result = engine.synthesize(&SynthesisRequest {
                phoneme_ids: vec![1; 20],
                ..Default::default()
            }).unwrap_or_else(|error| panic!("dimension={dimension}, masked={masked}: {error}"));
            assert!(!result.audio.is_empty());
            assert!(result.audio.iter().any(|&sample| sample != 0));
        }
    }
}

#[test]
fn supplied_embedding_preserves_declared_dimension() {
    for dimension in [192, 256] {
        for masked in [false, true] {
            let mut engine = engine(dimension, masked);
            let result = engine.synthesize(&SynthesisRequest {
                phoneme_ids: vec![1; 20],
                speaker_embedding: Some(vec![0.1; dimension]),
                ..Default::default()
            }).unwrap_or_else(|error| panic!("dimension={dimension}, masked={masked}: {error}"));
            assert!(result.audio.iter().any(|&sample| sample != 0));
        }
    }
}

#[test]
fn mismatched_embedding_is_rejected_without_truncation() {
    let mut engine = engine(192, true);
    let error = engine.synthesize(&SynthesisRequest {
        phoneme_ids: vec![1; 20],
        speaker_embedding: Some(vec![0.1; 256]),
        ..Default::default()
    }).expect_err("a 256-value embedding must not be silently truncated for a 192-dimensional model");
    assert!(error.to_string().contains("speaker_embedding"));
}
