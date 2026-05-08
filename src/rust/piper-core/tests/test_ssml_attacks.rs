//! Adversarial tests for `piper_plus::ssml` — XXE / billion-laughs / DTD / PI.
//!
//! These tests pin the *current* defensive behaviour of [`SsmlParser`]
//! against well-known XML attack vectors. The cases mirror analogous
//! fixtures in the Python / C# / Go runtimes so cross-runtime drift
//! can be detected.
//!
//! The contract for each case is:
//!
//! 1. The parser MUST NOT crash, panic, segfault, OOM, or hang.
//! 2. The parser MUST NOT expand external entities (`file://`, `http://`, ...).
//! 3. Either the input is rejected by `is_ssml()` (DOCTYPE / xml prolog
//!    precedes `<speak>`) and returned as a single plain-text segment,
//!    OR `quick-xml` parses it tolerantly with no entity expansion. In
//!    both branches no entity reference value leaks into the output.
//!
//! `quick-xml`'s `unescape()` returns an `Err(UnrecognizedEntity)` for
//! any non-predefined entity reference, which the existing parser
//! swallows via `unwrap_or_default()` — yielding an empty text segment.
//! This is safe (no expansion possible) but silent; the tests below
//! pin that observable behaviour.

use piper_plus::ssml::SsmlParser;

/// Concatenate all segment text for substring search.
fn all_text(segments: &[piper_plus::ssml::SsmlSegment]) -> String {
    segments
        .iter()
        .map(|s| s.text.as_str())
        .collect::<Vec<_>>()
        .join(" ")
}

// =====================================================================
// XXE — external entity attack
// =====================================================================

/// Standard XXE payload (DOCTYPE + xml prolog) must not resolve a SYSTEM
/// entity. `is_ssml()` regex requires `<speak` to be the first
/// non-whitespace token, so DOCTYPE-prefixed inputs bypass XML parsing
/// entirely and are returned as a plain-text segment.
#[test]
fn test_xxe_external_entity_blocked() {
    let payload = r#"<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><speak>&xxe;</speak>"#;
    let segments = SsmlParser::parse(payload);
    assert!(!segments.is_empty(), "must produce at least one segment");
    let full = all_text(&segments);
    // No /etc/passwd content should leak.
    assert!(!full.contains("root:"), "unexpected file content leaked");
    assert!(!full.contains("/bin/bash"));
    assert!(!full.contains("/bin/sh"));
}

/// DOCTYPE without an xml prolog is also bypassed by `is_ssml`.
#[test]
fn test_xxe_doctype_only_no_xml_prolog() {
    let payload =
        r#"<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><speak>&xxe;</speak>"#;
    let segments = SsmlParser::parse(payload);
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    assert!(!full.contains("root:"));
}

/// `<speak>` first with an undeclared entity reaches `quick-xml`.
/// `quick-xml`'s `unescape()` returns `Err(UnrecognizedEntity)`, which
/// the implementation swallows via `unwrap_or_default()` -> empty text.
/// Pin this behaviour: the segment is empty (filtered by `merge`) and
/// no expansion takes place.
#[test]
fn test_xxe_speak_first_undeclared_entity() {
    let payload = r#"<speak>&xxe;</speak>"#;
    let segments = SsmlParser::parse(payload);
    // Should not panic / hang. Returns either an empty merged segment
    // or a single fallback segment — both are sane responses.
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    assert!(!full.contains("root:"));
    assert!(!full.contains("/etc/passwd"));
    assert!(!full.contains("/bin/"));
}

// =====================================================================
// Billion laughs — exponential entity expansion DoS
// =====================================================================

fn build_billion_laughs(depth: usize, fanout: usize) -> String {
    let mut decls = String::from(r#"<!ENTITY lol "lol">"#);
    let mut prev = String::from("lol");
    for d in 2..=depth {
        let kids: String = (0..fanout).map(|_| format!("&{};", prev)).collect();
        let name = format!("lol{}", d);
        decls.push_str(&format!(r#"<!ENTITY {} "{}">"#, name, kids));
        prev = name;
    }
    format!("<!DOCTYPE lolz [{}]><speak>&{};</speak>", decls, prev)
}

/// 9-deep, fan-out-10 billion laughs. Even the unbounded textual
/// expansion would yield 10^9 = 1 billion characters, but the
/// `is_ssml` regex check rejects DOCTYPE-prefixed input entirely.
/// The whole payload is returned as a single plain-text segment.
#[test]
fn test_billion_laughs_bounded() {
    let payload = build_billion_laughs(9, 10);
    // Time / memory bounded: must complete promptly.
    let start = std::time::Instant::now();
    let segments = SsmlParser::parse(&payload);
    let elapsed = start.elapsed();
    assert!(
        elapsed.as_secs() < 5,
        "billion laughs took too long: {:?}",
        elapsed
    );
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    // No expansion can have occurred — output must be at most ~2x
    // input length (allowing for the trim path differences).
    assert!(
        full.len() <= payload.len() * 2,
        "output ballooned: input={}, output={}",
        payload.len(),
        full.len()
    );
}

/// `<speak>`-first variant: undefined entity refs reach `quick-xml`,
/// which returns `Err(UnrecognizedEntity)` per character — no
/// expansion possible. Mirrors the Python
/// ``test_billion_laughs_speak_first_falls_back_safely`` parity case
/// to lock down behaviour when the DOCTYPE shield does not fire.
#[test]
fn test_billion_laughs_speak_first_falls_back_safely() {
    // Internal entity ref without DOCTYPE — undefined entity.
    let payload = r#"<speak><prosody rate="slow">&lol;&lol;&lol;</prosody></speak>"#;
    let segments = SsmlParser::parse(payload);
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    // Should not have ballooned. Small bound regardless of fallback path.
    assert!(
        full.len() < 1000,
        "speak-first billion-laughs ballooned: {}",
        full.len()
    );
}

// =====================================================================
// DTD — external SYSTEM declaration
// =====================================================================

/// External SYSTEM DTD must not be fetched. `quick-xml` emits a
/// `DocType` event which the parser ignores. `is_ssml` regex rejects
/// DOCTYPE-prefixed payloads, which is the actual code path for this
/// case.
#[test]
fn test_dtd_inline_safely_handled() {
    let payload =
        r#"<!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd"><speak>Hello</speak>"#;
    let start = std::time::Instant::now();
    let segments = SsmlParser::parse(payload);
    let elapsed = start.elapsed();
    // No network fetch — must complete near-instantaneously.
    assert!(elapsed.as_millis() < 500);
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    // The "Hello" content (or the literal payload) should be present.
    assert!(full.contains("Hello") || full.contains("speak"));
}

/// External SYSTEM DTD preceded by an XML prolog. Mirrors the Python
/// ``test_dtd_external_with_xml_prolog`` parity case so that all four
/// runtimes share both DTD shapes (with and without prolog).
#[test]
fn test_dtd_external_with_xml_prolog() {
    let payload = concat!(
        r#"<?xml version="1.0"?>"#,
        r#"<!DOCTYPE speak SYSTEM "http://example.invalid/external.dtd">"#,
        r#"<speak>Hello</speak>"#
    );
    let start = std::time::Instant::now();
    let segments = SsmlParser::parse(payload);
    let elapsed = start.elapsed();
    // Still no network fetch — must be fast.
    assert!(
        elapsed.as_millis() < 500,
        "external DTD parse took too long: {:?}",
        elapsed
    );
    assert!(!segments.is_empty());
}

/// Bare XML prolog with no DOCTYPE in front of `<speak>`. The
/// `is_ssml` regex still rejects this (since `<?` precedes `<speak>`)
/// so the entire payload is returned as plain text. Mirrors Python
/// ``test_xml_prolog_only`` for parity.
#[test]
fn test_xml_prolog_only() {
    let payload = r#"<?xml version="1.0" encoding="UTF-8"?><speak>Hi</speak>"#;
    let segments = SsmlParser::parse(payload);
    assert!(!segments.is_empty());
}

// =====================================================================
// Processing instruction
// =====================================================================

/// Stylesheet PI must not trigger any XSL fetching.
/// `is_ssml` regex rejects `<?xml-stylesheet ...?>` prefixed input
/// because `<?` is not `<speak`.
#[test]
fn test_xml_processing_instruction_ignored() {
    let payload = r#"<?xml-stylesheet type="text/xsl" href="evil.xsl"?><speak>Hello</speak>"#;
    let start = std::time::Instant::now();
    let segments = SsmlParser::parse(payload);
    let elapsed = start.elapsed();
    assert!(elapsed.as_millis() < 500);
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    // "Hello" should be reachable somehow.
    assert!(full.contains("Hello"));
}

// =====================================================================
// Attribute with entity reference
// =====================================================================

/// Predefined entity `&amp;` in an attribute is valid; an undeclared
/// entity in an attribute (`&xxe;`) hits the `unescape` error branch
/// inside `quick-xml`, which the implementation handles silently.
#[test]
fn test_attribute_with_entity_reference() {
    // Predefined entity — should parse without error.
    let payload_amp = r#"<speak><break time="&amp;500ms"/></speak>"#;
    let segments = SsmlParser::parse(payload_amp);
    assert!(!segments.is_empty(), "amp entity must not crash");

    // Undefined entity — must not crash, must not leak.
    let payload_xxe = r#"<speak><break time="&xxe;"/></speak>"#;
    let segments = SsmlParser::parse(payload_xxe);
    // No panic.
    let full = all_text(&segments);
    assert!(!full.contains("root:"));
    assert!(!full.contains("/etc/passwd"));
}

/// DOCTYPE-prefixed XXE inside a `<break>` attribute. The `is_ssml`
/// regex rejects the DOCTYPE prefix, so the payload is returned as
/// plain text — but the `&xxe;` token must NEVER expand to file
/// content. Mirrors Python ``test_attribute_with_xxe_entity_falls_back``
/// and C# ``AttributeWithXxeEntity_DoctypePrefix_FallsBackSafely``.
#[test]
fn test_attribute_with_xxe_entity_doctype_prefix() {
    let payload = concat!(
        r#"<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>"#,
        r#"<speak><break time="&xxe;"/></speak>"#
    );
    let segments = SsmlParser::parse(payload);
    assert!(!segments.is_empty());
    let full = all_text(&segments);
    assert!(!full.contains("root:"));
    assert!(!full.contains("/bin/"));
}

// =====================================================================
// Cross-runtime drift sentinel
// =====================================================================

/// `is_ssml` regex must be identical across runtimes.
///
/// Pinned: `^\s*<speak[\s>]` is the regex used in Python / Rust / Go /
/// C#. All four runtimes treat DOCTYPE / xml prolog / processing
/// instruction prefixes as plain text. If this assertion changes,
/// review the analogous tests in the other three runtimes for drift.
#[test]
fn test_doctype_prefix_treated_as_plain_text() {
    let cases: &[&str] = &[
        "<!DOCTYPE speak><speak>Hi</speak>",
        "<!DOCTYPE foo [<!ENTITY x 'y'>]><speak>Hi</speak>",
        r#"<?xml version='1.0'?><speak>Hi</speak>"#,
        r#"<?xml-stylesheet href='x.xsl'?><speak>Hi</speak>"#,
    ];
    for payload in cases {
        assert!(
            !SsmlParser::is_ssml(payload),
            "unexpected is_ssml=true for {:?}",
            payload
        );
        let segments = SsmlParser::parse(payload);
        assert_eq!(segments.len(), 1, "{:?}", payload);
        assert_eq!(segments[0].text, *payload, "{:?}", payload);
    }
}
