//! Swedish per-word LID (language identification) tests (Issue #539).
//!
//! Verifies the conservative Swedish per-word post-pass in
//! [`piper_plus_g2p::multilingual::segment_text`]. The char-level detector
//! maps å/ä/ö to `default_latin_language` (shared with other Latin scripts);
//! a conservative word-level post-pass then re-classifies default-Latin
//! segments to "sv" when a STRONG indicator is present:
//!
//!   * the å/Å character, OR
//!   * an exact match in the Swedish function-word set.
//!
//! The weak chars ä/ö ALONE are NOT sufficient (they are shared with
//! German/Finnish/loanwords). This is the central correctness invariant —
//! see the `weak_char_invariant` cases below.
//!
//! These mirror the 7 behavioral cases of the canonical Python tests for
//! `_refine_latin_segments_for_swedish`.

use piper_plus_g2p::multilingual::{UnicodeLanguageDetector, segment_text};

/// Build a detector for the given language codes + default Latin language.
fn make_detector(langs: &[&str], default_latin: &str) -> UnicodeLanguageDetector {
    let lang_strings: Vec<String> = langs.iter().map(|s| s.to_string()).collect();
    UnicodeLanguageDetector::new(&lang_strings, default_latin)
}

/// Assert the whole input collapses to a single segment classified as `lang`.
fn assert_single_lang(langs: &[&str], default_latin: &str, text: &str, lang: &str) {
    let det = make_detector(langs, default_latin);
    let segs = segment_text(text, &det);
    assert_eq!(
        segs.len(),
        1,
        "expected a single segment for {text:?}, got {segs:?}"
    );
    assert_eq!(
        segs[0].0, lang,
        "expected {text:?} -> {lang:?}, got {segs:?}"
    );
}

/// Assert that *some* segment of the input is classified as `lang`.
fn assert_contains_lang(langs: &[&str], default_latin: &str, text: &str, lang: &str) {
    let det = make_detector(langs, default_latin);
    let segs = segment_text(text, &det);
    assert!(
        segs.iter().any(|(l, _)| l == lang),
        "expected some segment of {text:?} to be {lang:?}, got {segs:?}"
    );
}

// ===========================================================================
// Case 1: strong å/Å character → "sv"
// ===========================================================================

#[test]
fn test_strong_a_ring_reclassifies_to_sv() {
    // "så" and "från" both contain å — a STRONG indicator.
    assert_contains_lang(&["en", "sv"], "en", "s\u{00e5}", "sv");
    assert_contains_lang(&["en", "sv"], "en", "fr\u{00e5}n", "sv");
}

// ===========================================================================
// Case 2/3: function words → "sv"
// ===========================================================================

#[test]
fn test_function_words_reclassify_to_sv() {
    // Exact function-word matches (no special chars needed).
    assert_single_lang(&["en", "sv"], "en", "och", "sv");
    assert_single_lang(&["en", "sv"], "en", "jag", "sv");
    assert_single_lang(&["en", "sv"], "en", "inte", "sv");
    // "för", "när", "är" are function words containing ö/ä — they qualify via
    // the function-word list, NOT via the weak char (see invariant below).
    assert_single_lang(&["en", "sv"], "en", "f\u{00f6}r", "sv");
    assert_single_lang(&["en", "sv"], "en", "n\u{00e4}r", "sv");
    assert_single_lang(&["en", "sv"], "en", "\u{00e4}r", "sv");
}

// ===========================================================================
// Case 4/5: weak chars ä/ö ALONE are NOT sufficient (THE key invariant)
// ===========================================================================

#[test]
fn test_weak_chars_alone_not_swedish() {
    // German words with ä/ö that are NOT Swedish function words and contain
    // no å must stay as the default Latin language ("en").
    assert_single_lang(&["en", "sv"], "en", "M\u{00e4}dchen", "en");
    assert_single_lang(&["en", "sv"], "en", "sch\u{00f6}n", "en");
    // Non-words with ä/ö that are not function words: also NOT sv.
    assert_single_lang(&["en", "sv"], "en", "w\u{00f6}rter", "en");
    assert_single_lang(&["en", "sv"], "en", "x\u{00f6}x", "en");
}

// ===========================================================================
// Case 6: no Swedish in the language set → post-pass disabled
// ===========================================================================

#[test]
fn test_no_sv_in_languages_no_reclassification() {
    // languages = [en, es] (no sv): even a word with å stays "en".
    assert_single_lang(&["en", "es"], "en", "fr\u{00e5}n", "en");
}

// ===========================================================================
// Case 7: a sentence with one strong word → whole segment becomes "sv"
// ===========================================================================

#[test]
fn test_sentence_with_function_word_reclassifies_segment() {
    // "jag" is a function word → the whole Latin segment becomes "sv".
    assert_single_lang(&["en", "sv"], "en", "jag heter Anna", "sv");
}
