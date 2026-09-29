//! Cross-runtime parity test for phoneme timing extraction.
//!
//! Loads `tests/fixtures/phoneme_timing/golden_matrix.json` (canonical
//! Python output produced by `src/python_run/piper_plus/timing.py:durations_to_timing`)
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
    reverse_map_cases: Vec<ReverseMapCase>,
}

/// Reverse-map cases (issue #698). `cases` above start from resolved token
/// strings, so nothing in them says how `phoneme_id_map` is turned back into
/// names. The contract said first-wins without defining "first", and the
/// runtimes split three/three -- python / js / csharp iterated in insertion
/// order, cpp / rust / go sorted. Every shipped model is collision-free, so
/// all six agreed byte-for-byte and no test could see it.
#[derive(Debug, Deserialize)]
struct ReverseMapCase {
    name: String,
    inputs: ReverseMapInputs,
    /// JSON object keys are strings; parsed back to i64 below.
    expected: std::collections::BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct ReverseMapInputs {
    phoneme_id_map: std::collections::HashMap<String, Vec<i64>>,
    pua_names: Option<std::collections::HashMap<String, String>>,
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
    tsv: String,
    srt: String,
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
    assert!(
        !fixture.cases.is_empty(),
        "fixture must contain at least one case"
    );
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

        // Formatted-output parity, byte for byte.
        //
        // The fixture held only float milliseconds until spec_version 1.2, so
        // the FORMATTING layer went unchecked in every runtime. Three defects
        // were found there one at a time by reading code rather than by a
        // failing test: rounding at .5 (#681), CRLF on Windows (#683), a
        // thousands separator in the cue index (#684).
        assert_eq!(
            result.to_tsv(),
            case.expected.tsv,
            "case '{}': TSV bytes differ from the fixture",
            case.name
        );
        assert_eq!(
            result.to_srt(),
            case.expected.srt,
            "case '{}': SRT bytes differ from the fixture",
            case.name
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

#[test]
fn reverse_map_cases_match_the_fixture() {
    let fixture = load_fixture();

    for case in &fixture.reverse_map_cases {
        let got = piper_plus::timing::build_phoneme_id_reverse_map(
            &case.inputs.phoneme_id_map,
            case.inputs.pua_names.as_ref(),
        );
        let expected: std::collections::HashMap<i64, String> = case
            .expected
            .iter()
            .map(|(k, v)| (k.parse::<i64>().expect("id is an integer"), v.clone()))
            .collect();

        assert_eq!(got, expected, "case {}", case.name);
    }
}

/// Anti-vacuity: without a MIRRORED colliding case, key order is
/// unobservable. A collision-free map resolves identically under any
/// iteration order, and a single colliding map can be satisfied by a runtime
/// that happens to receive its keys already sorted.
#[test]
fn reverse_map_cases_include_a_mirrored_collision() {
    let fixture = load_fixture();
    let mut orders_by_keyset: std::collections::HashMap<
        std::collections::BTreeSet<String>,
        std::collections::BTreeSet<Vec<String>>,
    > = std::collections::HashMap::new();

    for case in &fixture.reverse_map_cases {
        let mut seen = std::collections::BTreeSet::new();
        let mut collides = false;
        for ids in case.inputs.phoneme_id_map.values() {
            for id in ids {
                if !seen.insert(*id) {
                    collides = true;
                }
            }
        }
        if !collides {
            continue;
        }
        // serde_json into a HashMap loses the JSON's key order, so the
        // mirrored pair is identified by the winner disagreeing with
        // insertion order rather than by the order itself. Both members share
        // the same key SET, and there are two of them.
        let keyset: std::collections::BTreeSet<String> =
            case.inputs.phoneme_id_map.keys().cloned().collect();
        orders_by_keyset
            .entry(keyset)
            .or_default()
            .insert(vec![case.name.clone()]);
    }

    assert!(
        orders_by_keyset.values().any(|names| names.len() >= 2),
        "no colliding key set appears twice in the fixture, so these cases \
         cannot detect a runtime that iterates phoneme_id_map in insertion \
         order"
    );
}
