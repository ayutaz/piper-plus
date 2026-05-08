//! Cross-runtime parity test for short-text contract constants.
//!
//! Loads `tests/fixtures/short_text/contract.json` (canonical values
//! exported from `docs/spec/short-text-contract.toml`) and asserts the
//! Rust runtime constants in `src/rust/piper-core/src/{engine,short_text}.rs`
//! agree with the contract.
//!
//! Public constants are checked directly. Private ones (`TRIM_THRESHOLD_RMS`,
//! `TRIM_MIN_SAMPLES`, `TRIM_WINDOW_SIZE`, `PAUSE_TOKEN_ID`, `SILENCE_PAD_MS`)
//! are extracted from the source file via a regex-style line scan, mirroring
//! the Python check in `scripts/check_short_text_contract.py`.
//!
//! `MIN_PHONEME_IDS` / `MIN_BODY_FOR_STRATEGY_A` live in `engine.rs`, which
//! is gated behind the `onnx` feature. The whole test file is therefore
//! gated to that feature; without it `cargo test` simply skips it.
//!
//! Spec: `docs/spec/short-text-contract.toml`
//! Fixture generator: `scripts/regenerate_short_text_fixture.py`

#![cfg(feature = "onnx")]

use std::fs;

use piper_plus::engine::{MIN_BODY_FOR_STRATEGY_A, MIN_PHONEME_IDS};
use piper_plus::short_text::SHORT_TEXT_CHARS;
use serde::Deserialize;

const FIXTURE_PATH: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../../tests/fixtures/short_text/contract.json"
);

const ENGINE_RS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/src/engine.rs");
const SHORT_TEXT_RS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/src/short_text.rs");

#[derive(Debug, Deserialize)]
struct Fixture {
    schema_version: u32,
    padding: PaddingSection,
    trim: TrimSection,
    scales: ScalesSection,
    ssml_injection: SsmlSection,
}

#[derive(Debug, Deserialize)]
struct PaddingSection {
    min_phoneme_ids: usize,
    min_body_for_strategy_a: usize,
    pause_token_id: i64,
    split: String,
    prosody_fill: i32,
}

#[derive(Debug, Deserialize)]
struct TrimSection {
    threshold_rms: f64,
    min_samples: usize,
    window_size: usize,
    sample_rate: u32,
}

#[derive(Debug, Deserialize)]
struct ScalesSection {
    noise_scale_min_ratio: f64,
    noise_w_min_ratio: f64,
}

#[derive(Debug, Deserialize)]
struct SsmlSection {
    short_text_chars: usize,
    silence_pad_ms: u32,
    skip_if_ssml: bool,
}

fn load_fixture() -> Fixture {
    let bytes = fs::read(FIXTURE_PATH).unwrap_or_else(|e| {
        panic!(
            "Failed to read short-text contract fixture at {}: {}\n\
             Run `python scripts/regenerate_short_text_fixture.py` to (re)generate.",
            FIXTURE_PATH,
            e
        )
    });
    serde_json::from_slice(&bytes).expect("contract fixture JSON is malformed")
}

fn read_source(path: &str) -> String {
    fs::read_to_string(path).unwrap_or_else(|e| panic!("failed to read {}: {}", path, e))
}

/// Extract the right-hand side literal of a top-level Rust const declaration.
/// Returns `None` if the constant is not found.
///
/// Recognised forms:
///   `pub const NAME: TYPE = VALUE;`
///   `const NAME: TYPE = VALUE;`
fn extract_const_literal(source: &str, name: &str) -> Option<String> {
    for line in source.lines() {
        let trimmed = line.trim_start();
        let needle = format!("const {name}");
        let after_pub = format!("pub const {name}");
        let head = if trimmed.starts_with(&after_pub) {
            &trimmed[after_pub.len()..]
        } else if trimmed.starts_with(&needle) {
            &trimmed[needle.len()..]
        } else {
            continue;
        };
        // The next char after NAME must be ':' (type annotation) or whitespace.
        let head = head.trim_start();
        if !head.starts_with(':') {
            continue;
        }
        // Find '=' after the type, then read until ';'.
        let eq = line.find('=')?;
        let semi = line[eq + 1..].find(';')?;
        let value = line[eq + 1..eq + 1 + semi].trim();
        return Some(value.to_string());
    }
    None
}

#[test]
fn fixture_schema_version_is_supported() {
    let fixture = load_fixture();
    assert_eq!(
        fixture.schema_version, 1,
        "Unknown short-text contract fixture schema_version. Adapt this test or regenerate."
    );
}

#[test]
fn public_constants_match_contract() {
    let fixture = load_fixture();

    assert_eq!(
        MIN_PHONEME_IDS, fixture.padding.min_phoneme_ids,
        "engine::MIN_PHONEME_IDS drifted from short-text contract"
    );
    assert_eq!(
        MIN_BODY_FOR_STRATEGY_A, fixture.padding.min_body_for_strategy_a,
        "engine::MIN_BODY_FOR_STRATEGY_A drifted from short-text contract"
    );
    assert_eq!(
        SHORT_TEXT_CHARS, fixture.ssml_injection.short_text_chars,
        "short_text::SHORT_TEXT_CHARS drifted from short-text contract"
    );
}

#[test]
fn private_engine_constants_match_contract() {
    let fixture = load_fixture();
    let src = read_source(ENGINE_RS);

    let pause_lit =
        extract_const_literal(&src, "PAUSE_TOKEN_ID").expect("PAUSE_TOKEN_ID not found in engine.rs");
    assert_eq!(
        pause_lit.parse::<i64>().unwrap(),
        fixture.padding.pause_token_id,
        "PAUSE_TOKEN_ID drifted: source={pause_lit}, contract={}",
        fixture.padding.pause_token_id
    );

    let threshold_lit = extract_const_literal(&src, "TRIM_THRESHOLD_RMS")
        .expect("TRIM_THRESHOLD_RMS not found in engine.rs");
    let threshold = threshold_lit.parse::<f64>().unwrap();
    assert!(
        (threshold - fixture.trim.threshold_rms).abs() < 1e-9,
        "TRIM_THRESHOLD_RMS drifted: source={threshold}, contract={}",
        fixture.trim.threshold_rms
    );

    let min_samples_lit = extract_const_literal(&src, "TRIM_MIN_SAMPLES")
        .expect("TRIM_MIN_SAMPLES not found in engine.rs");
    assert_eq!(
        min_samples_lit.parse::<usize>().unwrap(),
        fixture.trim.min_samples,
        "TRIM_MIN_SAMPLES drifted"
    );

    let window_size_lit = extract_const_literal(&src, "TRIM_WINDOW_SIZE")
        .expect("TRIM_WINDOW_SIZE not found in engine.rs");
    assert_eq!(
        window_size_lit.parse::<usize>().unwrap(),
        fixture.trim.window_size,
        "TRIM_WINDOW_SIZE drifted"
    );
}

#[test]
fn short_text_silence_pad_constant_matches_contract() {
    let fixture = load_fixture();
    let src = read_source(SHORT_TEXT_RS);
    let value = extract_const_literal(&src, "SILENCE_PAD_MS")
        .expect("SILENCE_PAD_MS not found in short_text.rs");
    assert_eq!(
        value.parse::<u32>().unwrap(),
        fixture.ssml_injection.silence_pad_ms,
        "SILENCE_PAD_MS drifted"
    );
}

#[test]
fn scales_floors_match_contract_in_engine_rs() {
    // The 0.5 / 0.4 floors are inline literals in
    // engine::adjust_scales_for_short_text. They are not named constants but
    // must agree with `scales.noise_scale_min_ratio` / `noise_w_min_ratio`
    // in the contract. We verify the literal pattern is present in engine.rs.
    let fixture = load_fixture();
    let src = read_source(ENGINE_RS);

    let ns_floor = format!("ratio.max({:.1})", fixture.scales.noise_scale_min_ratio);
    let nw_floor = format!("ratio.max({:.1})", fixture.scales.noise_w_min_ratio);

    assert!(
        src.contains(&ns_floor),
        "engine.rs must clamp noise_scale ratio to {}; pattern '{ns_floor}' not found",
        fixture.scales.noise_scale_min_ratio
    );
    assert!(
        src.contains(&nw_floor),
        "engine.rs must clamp noise_w ratio to {}; pattern '{nw_floor}' not found",
        fixture.scales.noise_w_min_ratio
    );
}

#[test]
fn structural_invariants_are_pinned() {
    // padding.split = "front_back_even" — not directly checkable as a
    // string in engine.rs, but if the spec flips this we want a test
    // failure to remind maintainers to revisit `pad_phoneme_ids` ordering.
    let fixture = load_fixture();
    assert_eq!(fixture.padding.split, "front_back_even");
    assert_eq!(fixture.padding.prosody_fill, 0);
    assert!(fixture.ssml_injection.skip_if_ssml);
    // 22050 Hz × 0.1 s = 2205 samples (the reference baseline for trim.min_samples).
    assert_eq!(fixture.trim.sample_rate, 22050);
}
