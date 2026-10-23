//! English text normalization parity with Python's g2p_en.
//!
//! Reads `tests/fixtures/g2p/english_normalize_cases.json`, which
//! `scripts/build_english_normalize_fixture.py` generates from the vendored
//! Python code:
//!
//!   - `numbers`: g2p_en's `normalize_numbers(input)` (inflect spelling);
//!   - `tokens`: the lowercased words after number expansion, accent
//!     stripping, the character filter, the i.e./e.g. replacement and nltk's
//!     `TweetTokenizer`.
//!
//! Every case must match. All mismatches are reported at once, and a fixture
//! with no case fails rather than passing vacuously.

#![cfg(feature = "english")]

use std::path::Path;

use piper_plus_g2p::english::{normalize_and_tokenize, normalize_numbers};
use serde_json::Value;

fn load_fixture() -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repository root")
        .join("tests/fixtures/g2p/english_normalize_cases.json");
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", path.display()));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("cannot parse {}: {e}", path.display()))
}

#[test]
fn normalize_numbers_matches_python() {
    let fixture = load_fixture();
    let mut compared = 0;
    let mut failures = Vec::new();
    for case in fixture["numbers"].as_array().expect("numbers") {
        let input = case["input"].as_str().unwrap();
        let expected = case["output"].as_str().unwrap();
        let actual = normalize_numbers(input);
        compared += 1;
        if actual != expected {
            failures.push(format!(
                "{input:?}\n  expected: {expected:?}\n  actual:   {actual:?}"
            ));
        }
    }

    assert!(compared > 0, "no 'numbers' case compared");
    assert!(
        failures.is_empty(),
        "{} of {compared} 'numbers' case(s) differ:\n{}",
        failures.len(),
        failures.join("\n")
    );
}

#[test]
fn tokens_match_python() {
    let fixture = load_fixture();
    let mut compared = 0;
    let mut failures = Vec::new();
    for case in fixture["tokens"].as_array().expect("tokens") {
        let input = case["input"].as_str().unwrap();
        let expected: Vec<String> = case["tokens"]
            .as_array()
            .unwrap()
            .iter()
            .map(|t| t.as_str().unwrap().to_string())
            .collect();
        let actual: Vec<String> = normalize_and_tokenize(input)
            .iter()
            .map(|t| t.to_lowercase())
            .collect();
        compared += 1;
        if actual != expected {
            failures.push(format!(
                "{input:?}\n  expected: {expected:?}\n  actual:   {actual:?}"
            ));
        }
    }

    assert!(compared > 0, "no 'tokens' case compared");
    assert!(
        failures.is_empty(),
        "{} of {compared} 'tokens' case(s) differ:\n{}",
        failures.len(),
        failures.join("\n")
    );
}
