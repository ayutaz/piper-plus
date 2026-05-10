//! Layer-2 E2E cosine gate for the speaker encoder.
//!
//! Mirrors `test/test_speaker_encoder_e2e.py`. See
//! `docs/spec/speaker-encoder-contract.md` for the contract.
//!
//! This test is **opt-in** and skips by default — it activates only when:
//! 1. The fixture `test/fixtures/speaker_encoder_golden.json` contains an
//!    `e2e_cosine_gate` block, AND
//! 2. `PIPER_SPEAKER_ENCODER_ONNX_PATH` env var points at a local encoder
//!    ONNX (we do **not** auto-download from HF in Rust tests — opt-in only).
//!
//! Run: `PIPER_SPEAKER_ENCODER_ONNX_PATH=/path/to/encoder.onnx \
//!       cargo test --features onnx --test test_speaker_encoder_e2e`
//!
//! The test body is gated behind the `onnx` feature because `SpeakerEncoder`
//! itself is. With `--no-default-features` or without `onnx`, the test
//! becomes a no-op (still compiles, still passes — just skipped).

#![cfg(feature = "onnx")]

use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;
use sha2::{Digest, Sha256};

use piper_plus::speaker_encoder::SpeakerEncoder;

#[derive(Deserialize)]
struct Fixture {
    e2e_cosine_gate: Option<E2EBlock>,
}

#[derive(Deserialize)]
struct E2EBlock {
    encoder_onnx: EncoderRef,
    reference_wav: ReferenceWav,
    expected_embedding: ExpectedEmbedding,
    cosine_threshold: f32,
}

#[derive(Deserialize)]
struct EncoderRef {
    sha256: Option<String>,
    #[allow(dead_code)]
    hf_repo: String,
    #[allow(dead_code)]
    hf_revision: String,
    #[allow(dead_code)]
    hf_filename: String,
}

#[derive(Deserialize)]
struct ReferenceWav {
    path: String,
    #[allow(dead_code)]
    sha256: Option<String>,
}

#[derive(Deserialize)]
struct ExpectedEmbedding {
    #[allow(dead_code)]
    dim: usize,
    values: Vec<f32>,
    #[allow(dead_code)]
    checksum: Option<String>,
}

fn fixture_path() -> PathBuf {
    let crate_root = env!("CARGO_MANIFEST_DIR");
    PathBuf::from(crate_root)
        .join("..")
        .join("..")
        .join("..")
        .join("test")
        .join("fixtures")
        .join("speaker_encoder_golden.json")
}

fn repo_root() -> PathBuf {
    let crate_root = env!("CARGO_MANIFEST_DIR");
    PathBuf::from(crate_root).join("..").join("..").join("..")
}

fn sha256_file(path: &Path) -> std::io::Result<String> {
    let bytes = fs::read(path)?;
    let mut h = Sha256::new();
    h.update(&bytes);
    Ok(format!("{:x}", h.finalize()))
}

fn cosine(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if na == 0.0 || nb == 0.0 {
        0.0
    } else {
        dot / (na * nb)
    }
}

#[test]
fn e2e_cosine_gate_against_pinned_embedding() {
    let raw = match fs::read_to_string(fixture_path()) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("[skip] cannot read fixture: {e}");
            return;
        }
    };
    let fixture: Fixture = match serde_json::from_str(&raw) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("[skip] cannot parse fixture: {e}");
            return;
        }
    };
    let gate = match fixture.e2e_cosine_gate {
        Some(g) => g,
        None => {
            eprintln!(
                "[skip] fixture has no e2e_cosine_gate block — generator was \
                 run without --encoder-onnx; layer-1 mel parity tests still apply"
            );
            return;
        }
    };

    let encoder_path = match std::env::var("PIPER_SPEAKER_ENCODER_ONNX_PATH") {
        Ok(p) => PathBuf::from(p),
        Err(_) => {
            eprintln!(
                "[skip] PIPER_SPEAKER_ENCODER_ONNX_PATH not set — opt-in test, \
                 skipping by default"
            );
            return;
        }
    };
    if !encoder_path.exists() {
        panic!(
            "PIPER_SPEAKER_ENCODER_ONNX_PATH={} does not exist",
            encoder_path.display()
        );
    }

    if let Some(expected_sha) = gate.encoder_onnx.sha256.as_deref()
        && !expected_sha.is_empty()
    {
        let actual_sha = sha256_file(&encoder_path).expect("sha256");
        assert_eq!(
            actual_sha, expected_sha,
            "encoder ONNX sha256 mismatch (silent upstream replacement?)"
        );
    }

    let wav_path = {
        let p = PathBuf::from(&gate.reference_wav.path);
        if p.is_absolute() {
            p
        } else {
            repo_root().join(p)
        }
    };
    if !wav_path.exists() {
        eprintln!("[skip] reference WAV not found at {}", wav_path.display());
        return;
    }

    let mut encoder = SpeakerEncoder::new(&encoder_path).expect("load encoder");
    let actual = encoder.encode_file(&wav_path).expect("encode");

    assert_eq!(
        actual.len(),
        gate.expected_embedding.values.len(),
        "embedding dim drift"
    );

    let cos = cosine(&actual, &gate.expected_embedding.values);
    assert!(
        cos >= gate.cosine_threshold,
        "cosine gate failed: cos={cos:.6} < threshold={:.6} \
         (encoder={}, wav={})",
        gate.cosine_threshold,
        encoder_path.display(),
        wav_path.display(),
    );
}
