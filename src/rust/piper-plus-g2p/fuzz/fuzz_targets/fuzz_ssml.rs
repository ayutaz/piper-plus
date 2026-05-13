#![no_main]
//! Fuzz target for `SsmlParser::parse` and `is_ssml`.
//!
//! Aims to catch:
//!   - panics on malformed XML
//!   - unicode boundary panics in regex fallback (`RE_STRIP_TAGS`)
//!   - integer overflow on `<break time="...ms"/>` values
//!   - stack overflow on deeply nested tags
//!
//! Property invariants verified on every input:
//!   1. `parse` never panics.
//!   2. `is_ssml(text)` is deterministic — calling it twice returns the same
//!      result (regex state should not leak across calls).
//!   3. Every returned segment has `rate > 0.0` (a non-positive rate would
//!      crash downstream synthesis).

use libfuzzer_sys::fuzz_target;
use piper_plus_g2p::ssml::SsmlParser;

fuzz_target!(|data: &[u8]| {
    // libFuzzer feeds arbitrary bytes; we only care about valid UTF-8 input
    // because the public API takes `&str`. Reject non-UTF-8 so we focus
    // fuzzing budget on realistic SSML / plain-text cases.
    let Ok(text) = std::str::from_utf8(data) else {
        return;
    };

    // Bound input size to avoid OOM on pathological cases. The Python
    // implementation enforces 100KB; mirror that here.
    if text.len() > 100_000 {
        return;
    }

    // Invariant 2: `is_ssml` is deterministic.
    let a = SsmlParser::is_ssml(text);
    let b = SsmlParser::is_ssml(text);
    assert_eq!(a, b, "is_ssml not deterministic for input len={}", text.len());

    // Invariant 1: parse never panics.
    let segments = SsmlParser::parse(text);

    // Invariant 3: rates are positive and finite.
    for seg in &segments {
        assert!(
            seg.rate.is_finite() && seg.rate > 0.0,
            "non-positive rate {} from input len={}",
            seg.rate,
            text.len()
        );
    }
});
