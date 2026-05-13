#![no_main]
//! Fuzz target for `piper_core::text_splitter::split_sentences` and
//! `split_chunks`.
//!
//! Aims to catch:
//!   - panics on multi-byte UTF-8 boundaries near sentence terminators
//!   - off-by-one indexing in abbreviation detection (`ends_with_abbreviation`)
//!   - quadratic blowup on pathological inputs (caught via libfuzzer timeout)
//!
//! Property invariants verified:
//!   1. `split_sentences` never panics on any UTF-8 input.
//!   2. The concatenation of returned chunks contains every non-whitespace
//!      character from the original input (no character is silently dropped).
//!   3. No returned chunk is empty.

use libfuzzer_sys::fuzz_target;
use piper_core::text_splitter::{split_chunks, split_sentences, SplitConfig};

fuzz_target!(|data: &[u8]| {
    let Ok(text) = std::str::from_utf8(data) else {
        return;
    };
    if text.len() > 100_000 {
        return;
    }

    // Invariant 1: never panics.
    let sentences = split_sentences(text);

    // Invariant 3: no empty chunk.
    for s in &sentences {
        assert!(!s.is_empty(), "empty sentence from input len={}", text.len());
    }

    // Invariant 2: every non-whitespace character is preserved in order.
    let original: String = text.chars().filter(|c| !c.is_whitespace()).collect();
    let joined: String = sentences
        .iter()
        .flat_map(|s| s.chars())
        .filter(|c| !c.is_whitespace())
        .collect();
    assert_eq!(
        original, joined,
        "split_sentences dropped or reordered characters (input len={})",
        text.len()
    );

    // Also exercise `split_chunks` with default config — separate code path.
    // Invariant: every returned chunk carries non-empty text (empty list
    // overall is OK for empty/whitespace-only input). `TextChunk` does not
    // expose `is_empty()` directly, so check the inner `text` field.
    let cfg = SplitConfig::default();
    let chunks = split_chunks(text, &cfg);
    for c in &chunks {
        assert!(!c.text.is_empty(), "split_chunks returned empty chunk text");
    }
});
