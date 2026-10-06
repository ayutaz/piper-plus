//! Execute ONNX inference with legacy/current speaker dimensions and cache storage failures.
#![cfg(feature = "onnx")]

use std::path::PathBuf;

use piper_plus::PiperError;
use piper_plus::config::{PhonemeType, VoiceConfig};
use piper_plus::engine::{OnnxEngine, SynthesisRequest};

fn engine(dimension: usize, masked: bool) -> OnnxEngine {
    let model = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/ort_session")
        .join(format!(
            "embedding_{dimension}_{}.onnx",
            if masked { "masked" } else { "legacy" }
        ));
    assert!(
        model.is_file(),
        "Build mandatory ONNX fixtures with tests/fixtures/ort_session/build_embedding_fixture.py"
    );
    let config = fixture_config();
    let engine = OnnxEngine::load(&model, &config, "cpu").expect("load dimension fixture");
    assert_eq!(engine.capabilities().speaker_embedding_dim, dimension);
    engine
}

fn fixture_config() -> VoiceConfig {
    VoiceConfig {
        audio: Default::default(),
        num_speakers: 1,
        num_symbols: 50,
        phoneme_type: PhonemeType::Text,
        phoneme_id_map: Default::default(),
        num_languages: 1,
        language_id_map: Default::default(),
        speaker_id_map: Default::default(),
    }
}

fn copy_fixture(directory: &std::path::Path) -> PathBuf {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/ort_session/embedding_192_legacy.onnx");
    let model = directory.join("model.onnx");
    std::fs::copy(fixture, &model).expect("mandatory real ONNX fixture");
    model
}

#[test]
fn writable_model_directory_creates_cache_and_reloads() {
    let directory = tempfile::tempdir().expect("isolated model directory");
    let model = copy_fixture(directory.path());
    let cache = directory.path().join("model.cpu.opt.onnx");
    let sentinel = directory.path().join("model.cpu.opt.onnx.ok");
    assert!(!cache.exists());

    for _ in 0..2 {
        let mut engine = OnnxEngine::load(&model, &fixture_config(), "cpu")
            .expect("load original or cached model");
        let result = engine
            .synthesize(&SynthesisRequest {
                phoneme_ids: vec![1; 20],
                ..Default::default()
            })
            .expect("inference from original or cached model");
        assert!(result.audio.iter().any(|&sample| sample != 0));
        assert!(std::fs::metadata(&cache).unwrap().len() > 0);
        assert!(sentinel.is_file());
    }
    assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 3);
}

#[test]
fn invalid_model_still_fails() {
    let directory = tempfile::tempdir().expect("isolated model directory");
    let model = directory.path().join("model.onnx");
    std::fs::write(&model, b"not an ONNX model").unwrap();
    assert!(matches!(
        OnnxEngine::load(&model, &fixture_config(), "cpu"),
        Err(PiperError::ModelLoad(_))
    ));
    assert!(!directory.path().join("model.cpu.opt.onnx.ok").exists());
}

#[cfg(unix)]
#[test]
fn read_only_model_directory_still_synthesizes() {
    use std::os::unix::fs::PermissionsExt;

    let directory = tempfile::tempdir().expect("isolated model directory");
    let model = copy_fixture(directory.path());
    let original_permissions = std::fs::metadata(directory.path()).unwrap().permissions();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
    let write_blocked = std::fs::File::create(directory.path().join("probe")).is_err();
    let loaded = OnnxEngine::load(&model, &fixture_config(), "cpu");
    std::fs::set_permissions(directory.path(), original_permissions).unwrap();

    assert!(
        write_blocked,
        "run Unix permission regressions as an unprivileged user"
    );
    let mut engine = loaded.expect("cache storage failure must not prevent model loading");
    let result = engine
        .synthesize(&SynthesisRequest {
            phoneme_ids: vec![1; 20],
            ..Default::default()
        })
        .expect("real inference from read-only model location");
    assert!(result.audio.iter().any(|&sample| sample != 0));
    assert!(!directory.path().join("model.cpu.opt.onnx").exists());
    assert!(!directory.path().join("model.cpu.opt.onnx.ok").exists());
}

#[test]
fn zero_embedding_uses_declared_dimension() {
    for dimension in [192, 256] {
        for masked in [false, true] {
            let mut engine = engine(dimension, masked);
            let result = engine
                .synthesize(&SynthesisRequest {
                    phoneme_ids: vec![1; 20],
                    ..Default::default()
                })
                .unwrap_or_else(|error| panic!("dimension={dimension}, masked={masked}: {error}"));
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
            let result = engine
                .synthesize(&SynthesisRequest {
                    phoneme_ids: vec![1; 20],
                    speaker_embedding: Some(vec![0.1; dimension]),
                    ..Default::default()
                })
                .unwrap_or_else(|error| panic!("dimension={dimension}, masked={masked}: {error}"));
            assert!(result.audio.iter().any(|&sample| sample != 0));
        }
    }
}

#[test]
fn mismatched_embedding_is_rejected_without_truncation() {
    let mut engine = engine(192, true);
    let error = engine
        .synthesize(&SynthesisRequest {
            phoneme_ids: vec![1; 20],
            speaker_embedding: Some(vec![0.1; 256]),
            ..Default::default()
        })
        .expect_err(
            "a 256-value embedding must not be silently truncated for a 192-dimensional model",
        );
    assert!(error.to_string().contains("speaker_embedding"));
}
