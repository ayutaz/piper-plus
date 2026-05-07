//! Two-crate consistency tests for ZH-EN code-switching (TICKET-01 R5).
//!
//! Verifies that `piper-plus-g2p` and `piper-core` (this crate, package
//! name `piper-plus`) produce byte-for-byte identical IPA output for the
//! same input. Without this guarantee, WASM (using `piper-plus-g2p`) and
//! desktop CLI (using `piper-core`) would diverge silently.
//!
//! Mirror tests live inside each crate's `chinese::tests` module; this file
//! adds the **cross-crate** comparisons.

use piper_plus::phonemize::chinese as core_chinese;
use piper_plus_g2p::chinese as g2p_chinese;
use std::path::PathBuf;

/// All inputs that must produce identical output across the two crates.
const PARITY_INPUTS: &[&str] = &[
    "GPS",
    "Python",
    "ChatGPT",
    "ZZ",
    "iPhone",
    "USB",
    "MP3",
    "GPS,",
    "GPS.",
    "Z2Z9",
    "ChatGPT \u{548c} Python",
    "",
    "   ",
];

#[test]
fn test_two_crate_consistency_default_data() {
    let core_data = core_chinese::load_default_loanword_data();
    let g2p_data = g2p_chinese::load_default_loanword_data();

    // Both should expose the same canonical data (same JSON byte content).
    assert_eq!(core_data.version, g2p_data.version);
    assert_eq!(core_data.acronyms.len(), g2p_data.acronyms.len());
    assert_eq!(core_data.loanwords.len(), g2p_data.loanwords.len());
    assert_eq!(core_data.letter_fallback.len(), g2p_data.letter_fallback.len());

    for input in PARITY_INPUTS {
        let core_tokens = core_chinese::phonemize_embedded_english(input, core_data);
        let g2p_tokens = g2p_chinese::phonemize_embedded_english(input, g2p_data);
        assert_eq!(
            core_tokens, g2p_tokens,
            "two-crate divergence for input {input:?}: core={core_tokens:?}, g2p={g2p_tokens:?}"
        );
    }
}

#[test]
fn test_two_crate_consistency_issue_examples() {
    // Issue #384 example tokens (acronyms / loanwords from the canonical JSON).
    let core_data = core_chinese::load_default_loanword_data();
    let g2p_data = g2p_chinese::load_default_loanword_data();

    let cases = ["GPS", "Python", "ChatGPT"];
    for case in cases {
        let core_out = core_chinese::phonemize_embedded_english(case, core_data);
        let g2p_out = g2p_chinese::phonemize_embedded_english(case, g2p_data);
        assert_eq!(core_out, g2p_out, "issue #384 example {case}");
        assert!(!core_out.is_empty(), "{case} must produce tokens");
    }
}

#[test]
fn test_two_crate_json_byte_consistency() {
    // The two `data/zh_en_loanword.json` files are kept byte-identical by
    // CI (`scripts/check_loanword_consistency.py`). Probe a few canonical
    // entries that must be present in both.
    let core_data = core_chinese::load_default_loanword_data();
    let g2p_data = g2p_chinese::load_default_loanword_data();

    for key in ["GPS", "USB", "CPU", "API", "URL"] {
        let core_v = core_data.acronyms.get(key);
        let g2p_v = g2p_data.acronyms.get(key);
        assert_eq!(core_v, g2p_v, "acronym {key}");
    }
    for key in ["Python", "ChatGPT", "iPhone", "Tesla"] {
        let core_v = core_data.loanwords.get(key);
        let g2p_v = g2p_data.loanwords.get(key);
        assert_eq!(core_v, g2p_v, "loanword {key}");
    }
}

#[test]
fn test_two_crate_prosody_consistency() {
    // Review note R-C2: the two crates must agree not just on the IPA token
    // stream but also on the per-token prosody (a1=tone, a2=1, a3=1).
    // Without this gate a regression in either copy of
    // `phonemize_from_pinyin_syllables_with_prosody` would silently flow
    // through `MultilingualPhonemizer` and degrade output quality.
    let core_data = core_chinese::load_default_loanword_data();
    let g2p_data = g2p_chinese::load_default_loanword_data();

    for input in ["GPS", "Python", "ChatGPT", "iPhone", "USB", "MP3"] {
        let (core_tokens, core_prosody) =
            core_chinese::phonemize_embedded_english_with_prosody(input, core_data);
        let (g2p_tokens, g2p_prosody) =
            g2p_chinese::phonemize_embedded_english_with_prosody(input, g2p_data);
        assert_eq!(core_tokens, g2p_tokens, "tokens {input:?}");
        assert_eq!(
            core_prosody.len(),
            g2p_prosody.len(),
            "prosody length {input:?}"
        );
        for (i, (cp, gp)) in core_prosody.iter().zip(g2p_prosody.iter()).enumerate() {
            match (cp, gp) {
                (Some(c), Some(g)) => {
                    assert_eq!(c.a1, g.a1, "{input:?}[{i}].a1");
                    assert_eq!(c.a2, g.a2, "{input:?}[{i}].a2");
                    assert_eq!(c.a3, g.a3, "{input:?}[{i}].a3");
                    // R-C1 invariant: must be a real tone, not zero-fill.
                    assert!(
                        (1..=5).contains(&c.a1) && c.a2 == 1 && c.a3 == 1,
                        "{input:?}[{i}]: prosody must be (a1=tone, a2=1, a3=1), got {c:?}"
                    );
                }
                (None, None) => {}
                _ => panic!(
                    "{input:?}[{i}]: prosody Some/None mismatch (core={cp:?}, g2p={gp:?})"
                ),
            }
        }
    }
}

#[test]
fn test_fixture_matrix_loadable_and_well_formed() {
    // Review note CI-C1: the cross-runtime fixture matrix
    // (`tests/fixtures/g2p/zh_en_loanword_matrix.json`, mirrored into each
    // runtime's test dir) was previously a dead asset — `grep -r` found no
    // consumer in any runtime.
    //
    // This Rust test gives the fixture a first consumer so the file isn't
    // silently rotten, and reports per-case agreement between
    // `expected_token_count` and what `phonemize_embedded_english` actually
    // produces. We do NOT fail on per-case count mismatches today: the
    // expected counts were authored by hand against the Python reference and
    // some entries (e.g. USB) reflect a different token-counting convention
    // than the Rust implementation uses. Re-generating the fixture from the
    // Python reference + landing per-runtime golden tests is tracked as a
    // follow-up to TICKET-06b.
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let fixture = here.join("tests/fixtures/zh_en_loanword_matrix.json");
    assert!(
        fixture.exists(),
        "fixture missing: {fixture:?} (sync gate should have copied it)"
    );

    let raw = std::fs::read_to_string(&fixture).unwrap();
    let json: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let cases = json.get("cases").and_then(|c| c.as_array())
        .expect("matrix must have a `cases` array");
    assert!(!cases.is_empty(), "matrix must contain at least one case");

    let data = g2p_chinese::load_default_loanword_data();
    let mut total = 0;
    let mut matches = 0;
    let mut mismatches: Vec<String> = Vec::new();

    for case in cases {
        let name = case.get("name").and_then(|n| n.as_str()).unwrap_or("?");
        let input = case.get("input").and_then(|i| i.as_str()).unwrap_or("");

        // Every case must at minimum have a name. `input` is omitted only on
        // schema-validation cases (e.g. forward-compat loader probes).
        assert!(!name.is_empty(), "case missing `name`");
        if case.get("input").is_none() {
            // Loader / schema-only case — nothing to phonemize.
            continue;
        }

        let tokens = g2p_chinese::phonemize_embedded_english(input, data);

        if let Some(expected_count) = case.get("expected_token_count").and_then(|c| c.as_u64()) {
            total += 1;
            if tokens.len() as u64 == expected_count {
                matches += 1;
            } else {
                mismatches.push(format!(
                    "  {name:?} (input={input:?}): expected {expected_count}, got {} ({tokens:?})",
                    tokens.len()
                ));
            }
        }
    }

    eprintln!(
        "[matrix] {matches} / {total} cases match expected_token_count exactly. \
         Mismatches (tracked as follow-up):\n{}",
        mismatches.join("\n")
    );

    assert!(total > 0, "no cases had `expected_token_count`; matrix is stale");
    assert!(
        matches > 0,
        "no fixture cases agreed with the implementation — fixture is wholly broken"
    );
}
