//! Cross-runtime parity test: Rust split_sentences against contract.json.
//!
//! Loads `tests/fixtures/text_splitter/contract.json` and asserts that the
//! Rust streaming module's behaviour matches the `runtimes.rust.*` projection
//! of the toml-generated fixture:
//!
//! 1. Each closing-punctuation codepoint listed in `runtimes.rust.closing_punctuation`
//!    is greedily consumed after a sentence terminator (post-consume strategy).
//! 2. Each sentence-terminator codepoint listed in `runtimes.rust.sentence_terminators`
//!    triggers a chunk split.
//! 3. The known terminator omitted from rust (U+FF0E fullwidth full stop) is
//!    NOT recognised as a terminator (current divergence).
//!
//! The drift gate (`text-splitter-parity.yml`) ensures the fixture stays in
//! sync with `docs/spec/text-splitter-contract.toml`.

use std::fs;
use std::path::PathBuf;

use piper_plus::streaming::split_sentences;
use serde_json::Value;

fn fixture_path() -> PathBuf {
    // tests live at src/rust/piper-core/tests/, repo root is 4 parents up.
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join("tests/fixtures/text_splitter/contract.json")
}

fn load_fixture() -> Value {
    let path = fixture_path();
    let text = fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("failed to read fixture {}: {}", path.display(), e));
    serde_json::from_str(&text).expect("fixture is valid JSON")
}

fn cp_to_char(cp: u64) -> char {
    char::from_u32(cp as u32).unwrap_or_else(|| panic!("invalid codepoint {cp}"))
}

#[test]
fn fixture_loads_with_rust_runtime_section() {
    let fixture = load_fixture();
    assert_eq!(fixture["schema_version"], 1);
    assert!(fixture["runtimes"]["rust"].is_object());
    assert_eq!(fixture["runtimes"]["rust"]["strategy"], "post-consume");
}

#[test]
fn rust_consumes_each_listed_closing_punctuation() {
    let fixture = load_fixture();
    let codepoints: Vec<u64> = fixture["runtimes"]["rust"]["closing_punctuation"]
        .as_array()
        .expect("closing_punctuation array")
        .iter()
        .map(|v| v.as_u64().expect("u64 codepoint"))
        .collect();

    for cp in codepoints {
        let close = cp_to_char(cp);
        // Build "Hi.<close> Next." — after period, the closing char must be
        // greedily consumed into the first chunk; no leak into the second.
        let input = format!("Hi.{close} Next.");
        let chunks = split_sentences(&input);
        assert_eq!(
            chunks.len(),
            2,
            "codepoint U+{cp:04X} ({close:?}): expected 2 chunks, got {chunks:?} for input {input:?}"
        );
        assert!(
            chunks[0].ends_with(close),
            "codepoint U+{cp:04X} ({close:?}): expected first chunk to end with the closing punct, got {:?}",
            chunks[0]
        );
        assert!(
            !chunks[1].starts_with(close),
            "codepoint U+{cp:04X} ({close:?}): closing punct leaked into second chunk: {:?}",
            chunks[1]
        );
    }
}

#[test]
fn rust_splits_on_each_listed_sentence_terminator() {
    let fixture = load_fixture();
    let codepoints: Vec<u64> = fixture["runtimes"]["rust"]["sentence_terminators"]
        .as_array()
        .expect("sentence_terminators array")
        .iter()
        .map(|v| v.as_u64().expect("u64 codepoint"))
        .collect();

    for cp in codepoints {
        let term = cp_to_char(cp);
        // Western-style terminators (.!?) require trailing whitespace per the
        // streaming.rs algorithm to recognise the boundary cleanly. CJK ones
        // (。！？) split immediately, so use a space after either case.
        let input = format!("a{term} b{term}");
        let chunks = split_sentences(&input);
        assert_eq!(
            chunks.len(),
            2,
            "codepoint U+{cp:04X} ({term:?}): expected 2 chunks, got {chunks:?} for input {input:?}"
        );
    }
}

#[test]
fn rust_does_not_recognise_omitted_terminator() {
    // U+FF0E ．(fullwidth full stop) is canonical but currently NOT in rust's
    // is_sentence_terminator(). Confirm the divergence is preserved (a future
    // realignment PR should update both this test and the OMITS table).
    let input = "a\u{FF0E} b\u{FF0E}";
    let chunks = split_sentences(input);
    // No split: rust treats U+FF0E as a regular char.
    assert_eq!(chunks.len(), 1, "U+FF0E should NOT split in rust today; got {chunks:?}");
}
