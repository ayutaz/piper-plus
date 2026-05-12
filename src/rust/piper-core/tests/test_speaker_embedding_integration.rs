//! Issue #426 integration test — speaker_embedding fallback on a real ort::Session.
//!
//! Unit tests in `engine.rs::tests` only assert the validate() layer.
//! This test loads the in-tree fixture
//! `tests/fixtures/mb_istft_speaker_embedding/model.onnx` (built by
//! `build_fixture.py`) and confirms that synthesize() succeeds when
//! `SynthesisRequest::speaker_embedding` is `None` — i.e. the engine
//! injects a zero embedding + mask=0 internally and the ORT session
//! does NOT raise "Required inputs missing".
//!
//! The fixture is built on first use via the Python builder so local
//! `cargo test` works without a separate setup step.

#![cfg(feature = "onnx")]

use std::path::{Path, PathBuf};
use std::process::Command;

use piper_plus::config::{PhonemeIdMap, PhonemeType, VoiceConfig};
use piper_plus::engine::{OnnxEngine, SynthesisRequest};

fn repo_root() -> PathBuf {
    // src/rust/piper-core/tests -> repo root is 4 levels up.
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repo root")
        .to_path_buf()
}

fn fixture_model_path() -> Option<PathBuf> {
    let root = repo_root();
    let path = root.join("tests/fixtures/mb_istft_speaker_embedding/model.onnx");
    if path.exists() {
        return Some(path);
    }
    // Build on first use.
    let builder = root.join("tests/fixtures/mb_istft_speaker_embedding/build_fixture.py");
    if !builder.exists() {
        return None;
    }
    // Prefer uv if available (matches the project's standard Python invocation),
    // fall back to python3.
    let interpreters: &[&[&str]] = &[&["uv", "run", "python"], &["python3"], &["python"]];
    for cmd_args in interpreters {
        let (cmd, args) = cmd_args.split_first().unwrap();
        let status = Command::new(cmd)
            .args(args.iter().copied())
            .arg(&builder)
            .current_dir(&root)
            .status();
        if let Ok(s) = status
            && s.success()
            && path.exists()
        {
            return Some(path);
        }
    }
    None
}

fn dummy_config() -> VoiceConfig {
    // Minimal VoiceConfig that matches the fixture (n_speakers=2, n_vocab=50).
    let mut phoneme_id_map: PhonemeIdMap = PhonemeIdMap::new();
    for i in 0_i64..50 {
        phoneme_id_map.insert(i.to_string(), vec![i]);
    }
    VoiceConfig {
        audio: Default::default(),
        num_speakers: 2,
        num_symbols: 50,
        phoneme_type: PhonemeType::Text,
        phoneme_id_map,
        num_languages: 1,
        language_id_map: Default::default(),
        speaker_id_map: Default::default(),
    }
}

#[test]
fn synthesize_without_embedding_uses_zero_fallback() {
    // Skip cleanly when the fixture cannot be produced (e.g. CI without Python).
    let Some(model_path) = fixture_model_path() else {
        eprintln!(
            "skipping: tests/fixtures/mb_istft_speaker_embedding/model.onnx missing \
             and could not be built (no Python interpreter in PATH?)"
        );
        return;
    };

    let config = dummy_config();
    let mut engine = OnnxEngine::load(&model_path, &config, "cpu").expect("load fixture model");

    // The fixture declares speaker_embedding/mask — confirm detection.
    let caps = engine.capabilities();
    assert!(
        caps.has_speaker_embedding,
        "fixture must declare speaker_embedding (Issue #426 regression)"
    );

    // Issue #426 reproducer: synthesize WITHOUT supplying speaker_embedding.
    // engine.rs:758-787 must inject zero+mask=0 internally; otherwise ORT
    // raises "Required inputs missing".
    let req = SynthesisRequest {
        phoneme_ids: vec![1, 10, 20, 30, 40, 2],
        speaker_id: Some(0),
        speaker_embedding: None,
        ..SynthesisRequest::default()
    };

    let result = engine
        .synthesize(&req)
        .expect("synthesize must succeed with zero-embedding fallback");

    assert!(
        !result.audio.is_empty(),
        "audio output must be non-empty (Issue #426 fallback regression?)"
    );
    assert!(
        result.audio.iter().any(|&s| s != 0),
        "audio must not be all-zero (model degenerated?)"
    );
}
