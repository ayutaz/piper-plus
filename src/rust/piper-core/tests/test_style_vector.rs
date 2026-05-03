//! Integration tests for the Phase 2 P2-T04 style_vector changes to
//! `SynthesisRequest`, `SynthesisParams`, and `ModelCapabilities`.
//!
//! These tests do not load a real ONNX model — they verify the
//! wiring and type-level contracts so downstream runtimes know the
//! new field behaves as expected.
//!
//! `SynthesisRequest`, `SynthesisParams`, and `ModelCapabilities` are
//! all re-exported under `feature = "onnx"`, so the whole file is gated
//! the same way (matches test_voice_api.rs / test_batch.rs).

#![cfg(feature = "onnx")]

use piper_plus::{ModelCapabilities, SynthesisParams, SynthesisRequest};

#[test]
fn test_synthesis_request_default_style_vector_is_none() {
    let req = SynthesisRequest::default();
    assert!(req.style_vector.is_none());
}

#[test]
fn test_synthesis_request_with_style_vector_256() {
    let req = SynthesisRequest {
        style_vector: Some(vec![0.0_f32; 256]),
        ..SynthesisRequest::default()
    };
    let sv = req.style_vector.expect("style_vector set above");
    assert_eq!(sv.len(), 256);
}

#[test]
fn test_synthesis_params_default_style_vector_none() {
    let params = SynthesisParams::default();
    assert!(params.style_vector.is_none());
}

#[test]
fn test_synthesis_params_carries_style_vector() {
    let params = SynthesisParams {
        style_vector: Some(vec![1.0_f32; 128]),
        ..SynthesisParams::default()
    };
    assert_eq!(params.style_vector.as_ref().map(|v| v.len()), Some(128));
}

#[test]
fn test_model_capabilities_style_vector_defaults() {
    let caps = ModelCapabilities {
        has_sid: false,
        has_lid: false,
        has_prosody: false,
        has_duration_output: false,
        has_speaker_embedding: false,
        has_style_vector: false,
        style_vector_dim: 0,
    };
    assert!(!caps.has_style_vector);
    assert_eq!(caps.style_vector_dim, 0);
}

#[test]
fn test_model_capabilities_style_vector_enabled() {
    let caps = ModelCapabilities {
        has_sid: false,
        has_lid: false,
        has_prosody: false,
        has_duration_output: false,
        has_speaker_embedding: false,
        has_style_vector: true,
        style_vector_dim: 256,
    };
    assert!(caps.has_style_vector);
    assert_eq!(caps.style_vector_dim, 256);
}
