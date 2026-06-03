//! Cross-runtime Swedish per-word LID parity fixture matrix — piper-core side
//! (Issue #539).
//!
//! piper-core re-exports the LID via `piper_plus::phonemize::multilingual`
//! (which forwards to `piper_plus_g2p`). This consumer loads the shared fixture
//! (`tests/fixtures/swedish_lid_matrix.json`, mirrored byte-for-byte from the
//! canonical `tests/fixtures/g2p/swedish_lid_matrix.json` by
//! `scripts/check_swedish_lid_consistency.py`) and verifies that
//! `segment_text` agrees with each case's `expect_contains_sv` flag — so the
//! desktop CLI crate stays byte-for-byte in parity with the WASM/g2p crate.
//!
//! Sister of `piper-plus-g2p`'s `test_swedish_lid_matrix` (same fixture).

use std::path::PathBuf;

use piper_plus::phonemize::multilingual::{UnicodeLanguageDetector, segment_text};

fn fixture_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/swedish_lid_matrix.json")
}

/// Does any segment of `text` get classified as Swedish?
fn contains_sv(langs: &[String], default_latin: &str, text: &str) -> bool {
    let lang_strings: Vec<String> = langs.iter().map(|s| s.to_string()).collect();
    let det = UnicodeLanguageDetector::new(&lang_strings, default_latin);
    segment_text(text, &det).iter().any(|(l, _)| l == "sv")
}

#[test]
fn test_swedish_lid_matrix() {
    let path = fixture_path();
    assert!(
        path.exists(),
        "fixture missing: {path:?} (sync gate should have copied it)"
    );

    let raw = std::fs::read_to_string(&path).unwrap();
    let json: serde_json::Value = serde_json::from_str(&raw).unwrap();

    assert_eq!(
        json.get("schema_version").and_then(|v| v.as_u64()),
        Some(1),
        "unexpected schema_version"
    );

    let langs: Vec<String> = json
        .get("languages")
        .and_then(|v| v.as_array())
        .expect("`languages` array")
        .iter()
        .map(|v| v.as_str().unwrap().to_string())
        .collect();
    let default_latin = json
        .get("default_latin")
        .and_then(|v| v.as_str())
        .expect("`default_latin` string");

    let cases = json
        .get("cases")
        .and_then(|c| c.as_array())
        .expect("matrix must have a `cases` array");
    assert!(!cases.is_empty(), "matrix must contain at least one case");

    let mut checked = 0;
    for case in cases {
        let text = case
            .get("text")
            .and_then(|t| t.as_str())
            .expect("case missing `text`");
        let expect_sv = case
            .get("expect_contains_sv")
            .and_then(|e| e.as_bool())
            .expect("case missing `expect_contains_sv`");

        let got = contains_sv(&langs, default_latin, text);
        assert_eq!(
            got, expect_sv,
            "[sv-lid] {text:?}: expected contains_sv={expect_sv}, got {got}.\n  \
             → if intentional, update tests/fixtures/g2p/swedish_lid_matrix.json \
             and re-sync via `python scripts/check_swedish_lid_consistency.py --fix`"
        );
        checked += 1;
    }
    assert!(
        checked >= 10,
        "expected >=10 matrix cases, checked {checked}"
    );
}
