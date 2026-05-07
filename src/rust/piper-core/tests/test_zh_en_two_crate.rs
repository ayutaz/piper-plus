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
