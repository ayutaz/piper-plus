//! zs-v1 CAM++ embedding parity with the Python recipe, using the real model.
//!
//! `test_kaldi_fbank_golden.rs` checks the features; this checks what the
//! runtime feeds the base model: `SpeakerEncoder` on the pinned
//! `campplus.onnx`, against embeddings that
//! `test/generate_zs_campplus_golden.py` computed with torchaudio +
//! onnxruntime (the recipe in `huggingface-space/zero_shot.py`). The browser
//! runs the same fixture in `test-zs-campplus-parity.js`.
//!
//! Needs the pinned model; set `PIPER_PLUS_CAMPPLUS_ONNX` to its path (CI
//! does). Without it the tests return early.
//!
//! Run: PIPER_PLUS_CAMPPLUS_ONNX=/path/to/campplus.onnx \
//!      cargo test -p piper-plus --features onnx --test test_campplus_parity

#![cfg(feature = "onnx")]

use std::path::PathBuf;

use piper_plus::speaker_encoder::{SpeakerEncoder, SpeakerFrontEnd};
use serde::Deserialize;

const CAMPPLUS_SHA256: &str = "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73";

// Same thresholds as the browser test: measured cosine >= 0.9999999 on these
// signals. Changing one detail lands below: preemphasis 0.97 -> 0.96 gives
// 0.99969, resampler rolloff 0.99 gives 0.981, a plain Hann window 0.987.
const MIN_COSINE: f64 = 0.9999;
const MAX_ABS: f32 = 5e-4;

#[derive(Deserialize)]
struct Fixture {
    campplus_sha256: String,
    syllable_hz: f64,
    amplitude: f64,
    max_harmonics: u32,
    noise_partials: Vec<[f64; 2]>,
    noise_floor: f64,
    noise_seed: u32,
    distinct_pair: [String; 2],
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    name: String,
    sample_rate: u32,
    seconds: f64,
    f0: f64,
    vibrato_hz: f64,
    vibrato_depth_hz: f64,
    embedding: Vec<f32>,
}

fn fixture() -> Fixture {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../test/fixtures/zs_campplus_golden.json");
    let text =
        std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {}: {e}", path.display()));
    serde_json::from_str(&text).expect("parse zs_campplus_golden.json")
}

/// Path to the pinned model, or `None` (test skipped) when the variable is
/// unset. A set but missing path fails, so CI cannot skip by accident.
fn model_path() -> Option<PathBuf> {
    let path = PathBuf::from(std::env::var_os("PIPER_PLUS_CAMPPLUS_ONNX")?);
    assert!(
        path.is_file(),
        "PIPER_PLUS_CAMPPLUS_ONNX={} is missing",
        path.display()
    );
    Some(path)
}

fn sha256_hex(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    Sha256::digest(bytes)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// xorshift32 in [-0.5, 0.5), bit-identical to `white_noise()` in the
/// generator.
fn white_noise(n: usize, seed: u32) -> Vec<f64> {
    let mut x = seed;
    (0..n)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            f64::from(x) / 4294967296.0 - 0.5
        })
        .collect()
}

/// Mirrors `voiced_signal()` in the generator: a harmonic tone with vibrato
/// and a syllable-rate envelope, high partials in the gaps (they exercise
/// the resampler cutoff) and a weak white floor, computed in f64 and stored
/// as f32.
fn voiced_signal(fx: &Fixture, c: &Case) -> Vec<f32> {
    use std::f64::consts::PI;
    let rate = f64::from(c.sample_rate);
    let n = (rate * c.seconds).round() as usize;
    let floor = white_noise(n, fx.noise_seed);
    (0..n)
        .map(|i| {
            let t = i as f64 / rate;
            let phase = 2.0 * PI * c.f0 * t
                - (c.vibrato_depth_hz / c.vibrato_hz) * (2.0 * PI * c.vibrato_hz * t).cos();
            let envelope = 0.5 * (1.0 - (2.0 * PI * fx.syllable_hz * t).cos());
            let mut x = 0.0;
            let mut k = 1u32;
            while f64::from(k) * (c.f0 + c.vibrato_depth_hz) < rate / 2.0 && k <= fx.max_harmonics {
                x += (fx.amplitude / f64::from(k)) * (f64::from(k) * phase).sin();
                k += 1;
            }
            let mut noise = 0.0;
            for &[amplitude, freq] in &fx.noise_partials {
                if freq < rate / 2.0 {
                    noise += amplitude * (2.0 * PI * freq * t).sin();
                }
            }
            (envelope * x + (1.0 - envelope) * noise + fx.noise_floor * floor[i]) as f32
        })
        .collect()
}

fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let (mut dot, mut na, mut nb) = (0.0f64, 0.0f64, 0.0f64);
    for (&x, &y) in a.iter().zip(b) {
        dot += f64::from(x) * f64::from(y);
        na += f64::from(x) * f64::from(x);
        nb += f64::from(y) * f64::from(y);
    }
    dot / (na * nb).sqrt()
}

#[test]
fn campplus_embeddings_match_python_recipe() {
    let Some(path) = model_path() else {
        eprintln!("skipped: PIPER_PLUS_CAMPPLUS_ONNX is not set");
        return;
    };
    let fx = fixture();
    let bytes = std::fs::read(&path).expect("read campplus.onnx");
    assert_eq!(sha256_hex(&bytes), CAMPPLUS_SHA256, "campplus.onnx hash");
    assert_eq!(
        fx.campplus_sha256, CAMPPLUS_SHA256,
        "fixture was generated with another model"
    );

    // The default constructor must pick the zs-v1 front end for CAM++.
    let mut encoder = SpeakerEncoder::new(&path).expect("load campplus.onnx");
    assert_eq!(encoder.front_end(), SpeakerFrontEnd::KaldiFbank);

    let mut embeddings = std::collections::HashMap::new();
    for c in &fx.cases {
        let embedding = encoder
            .encode(&voiced_signal(&fx, c), c.sample_rate)
            .unwrap_or_else(|e| panic!("{}: {e}", c.name));
        assert_eq!(embedding.len(), c.embedding.len(), "{}", c.name);
        let max_abs = embedding
            .iter()
            .zip(&c.embedding)
            .map(|(a, b)| (a - b).abs())
            .fold(0.0f32, f32::max);
        let cos = cosine(&embedding, &c.embedding);
        eprintln!("{}: cosine {cos:.7}, max abs {max_abs:.2e}", c.name);
        assert!(cos >= MIN_COSINE, "{}: cosine {cos} < {MIN_COSINE}", c.name);
        assert!(
            max_abs <= MAX_ABS,
            "{}: max abs {max_abs} > {MAX_ABS}",
            c.name
        );
        embeddings.insert(c.name.clone(), embedding);
    }

    // Guards against a degenerate encoder that returns the same vector for
    // every voice.
    let [low, high] = &fx.distinct_pair;
    let cos = cosine(&embeddings[low], &embeddings[high]);
    assert!(cos < 0.95, "cosine {cos} between distinct voices");
}

#[test]
fn mel_front_end_does_not_match_python_recipe() {
    // The legacy front end on the same model drifts well away from the
    // Python embedding; this is what #915 fixed for CAM++.
    let Some(path) = model_path() else {
        eprintln!("skipped: PIPER_PLUS_CAMPPLUS_ONNX is not set");
        return;
    };
    let fx = fixture();
    let c = fx
        .cases
        .iter()
        .find(|c| c.sample_rate != 16000)
        .expect("a resampled case");
    let mut encoder =
        SpeakerEncoder::with_front_end(&path, SpeakerFrontEnd::Mel).expect("load campplus.onnx");
    let embedding = encoder
        .encode(&voiced_signal(&fx, c), c.sample_rate)
        .unwrap();
    let cos = cosine(&embedding, &c.embedding);
    eprintln!("{} with the legacy front end: cosine {cos:.4}", c.name);
    assert!(
        cos < MIN_COSINE,
        "legacy front end unexpectedly matched: cosine {cos}"
    );
}
