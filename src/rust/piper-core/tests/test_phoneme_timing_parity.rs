//! Cross-runtime parity test for phoneme timing extraction.
//!
//! Loads `tests/fixtures/phoneme_timing/golden_matrix.json` (canonical
//! Python output produced by `src/python_run/piper/timing.py:durations_to_timing`)
//! and asserts that the Rust implementation in
//! `piper_core::timing::durations_to_timing` produces byte-equivalent
//! timing values.
//!
//! Spec: `docs/spec/phoneme-timing-contract.toml` v1.0
//! Fixture generator: `scripts/regenerate_timing_fixture.py`

use std::fs;
use std::path::PathBuf;

use piper_plus::timing::durations_to_timing;
use serde::Deserialize;

const FIXTURE_PATH: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../../tests/fixtures/phoneme_timing/golden_matrix.json"
);

/// Tolerance for inter-runtime float comparison (milliseconds).
/// 1e-3 ms = 1 microsecond, well below the contract's display precision (3 decimals).
const TOLERANCE_MS: f64 = 1e-3;

#[derive(Debug, Deserialize)]
struct Fixture {
    schema_version: u32,
    cases: Vec<Case>,
}

#[derive(Debug, Deserialize)]
struct Case {
    name: String,
    inputs: Inputs,
    expected: Expected,
}

#[derive(Debug, Deserialize)]
struct Inputs {
    durations: Vec<f64>,
    phoneme_tokens: Vec<String>,
    sample_rate: u32,
    hop_length: usize,
}

#[derive(Debug, Deserialize)]
struct Expected {
    phonemes: Vec<ExpectedPhoneme>,
    total_duration_ms: f64,
    sample_rate: u32,
}

#[derive(Debug, Deserialize)]
struct ExpectedPhoneme {
    phoneme: String,
    start_ms: f64,
    end_ms: f64,
    duration_ms: f64,
}

fn load_fixture() -> Fixture {
    let path = PathBuf::from(FIXTURE_PATH);
    let bytes = fs::read(&path).unwrap_or_else(|e| {
        panic!(
            "Failed to read golden fixture at {}: {}\n\
             Run `python scripts/regenerate_timing_fixture.py` to (re)generate.",
            path.display(),
            e
        )
    });
    serde_json::from_slice(&bytes).expect("golden fixture JSON is malformed")
}

#[test]
fn fixture_schema_version_is_supported() {
    let fixture = load_fixture();
    assert_eq!(
        fixture.schema_version, 1,
        "Unknown fixture schema_version. Adapt this test or regenerate the fixture."
    );
    assert!(!fixture.cases.is_empty(), "fixture must contain at least one case");
}

#[test]
fn matches_python_canonical_output() {
    let fixture = load_fixture();

    for case in &fixture.cases {
        let durations_f32: Vec<f32> = case.inputs.durations.iter().map(|&d| d as f32).collect();

        let result = durations_to_timing(
            &durations_f32,
            &case.inputs.phoneme_tokens,
            case.inputs.sample_rate,
            case.inputs.hop_length,
        )
        .unwrap_or_else(|e| panic!("case '{}': durations_to_timing failed: {}", case.name, e));

        // sample_rate parity
        assert_eq!(
            result.sample_rate, case.expected.sample_rate,
            "case '{}': sample_rate mismatch",
            case.name
        );

        // total_duration_ms parity
        assert!(
            (result.total_duration_ms - case.expected.total_duration_ms).abs() < TOLERANCE_MS,
            "case '{}': total_duration_ms mismatch — Rust={}, expected={}",
            case.name,
            result.total_duration_ms,
            case.expected.total_duration_ms
        );

        // phoneme array length parity
        assert_eq!(
            result.phonemes.len(),
            case.expected.phonemes.len(),
            "case '{}': phoneme count mismatch — Rust={}, expected={}",
            case.name,
            result.phonemes.len(),
            case.expected.phonemes.len()
        );

        // per-phoneme parity (token, start_ms, end_ms, duration_ms)
        for (i, (got, want)) in result
            .phonemes
            .iter()
            .zip(case.expected.phonemes.iter())
            .enumerate()
        {
            assert_eq!(
                got.phoneme, want.phoneme,
                "case '{}' phoneme[{}]: token mismatch",
                case.name, i
            );
            assert!(
                (got.start_ms - want.start_ms).abs() < TOLERANCE_MS,
                "case '{}' phoneme[{}] '{}': start_ms — Rust={}, expected={}",
                case.name,
                i,
                got.phoneme,
                got.start_ms,
                want.start_ms
            );
            assert!(
                (got.end_ms - want.end_ms).abs() < TOLERANCE_MS,
                "case '{}' phoneme[{}] '{}': end_ms — Rust={}, expected={}",
                case.name,
                i,
                got.phoneme,
                got.end_ms,
                want.end_ms
            );
            assert!(
                (got.duration_ms - want.duration_ms).abs() < TOLERANCE_MS,
                "case '{}' phoneme[{}] '{}': duration_ms — Rust={}, expected={}",
                case.name,
                i,
                got.phoneme,
                got.duration_ms,
                want.duration_ms
            );
        }
    }
}

#[test]
fn continuous_boundaries_are_preserved() {
    // Spec: each phoneme's end_ms must equal the next phoneme's start_ms.
    // This invariant should hold across all canonical cases.
    let fixture = load_fixture();

    for case in &fixture.cases {
        let durations_f32: Vec<f32> = case.inputs.durations.iter().map(|&d| d as f32).collect();
        let result = durations_to_timing(
            &durations_f32,
            &case.inputs.phoneme_tokens,
            case.inputs.sample_rate,
            case.inputs.hop_length,
        )
        .unwrap();

        for w in result.phonemes.windows(2) {
            let prev_end = w[0].end_ms;
            let next_start = w[1].start_ms;
            assert!(
                (prev_end - next_start).abs() < TOLERANCE_MS,
                "case '{}': discontinuous boundary between '{}' and '{}' (end={}, next_start={})",
                case.name,
                w[0].phoneme,
                w[1].phoneme,
                prev_end,
                next_start
            );
        }
    }
}
