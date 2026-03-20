#![cfg(feature = "japanese")]

use piper_plus::phonemize::Phonemizer;
use piper_plus::phonemize::japanese::JapanesePhonemizer;

/// Try to create a JapanesePhonemizer.
/// With naist-jdic feature: uses bundled dictionary.
/// Without: searches for dictionary file, returns None if not found.
fn try_create_phonemizer() -> Option<JapanesePhonemizer> {
    #[cfg(feature = "naist-jdic")]
    {
        Some(JapanesePhonemizer::new_bundled().expect("Failed to create with bundled dict"))
    }
    #[cfg(not(feature = "naist-jdic"))]
    {
        JapanesePhonemizer::new().ok()
    }
}

/// Macro to get a phonemizer or skip the test if dictionary is unavailable.
macro_rules! require_phonemizer {
    () => {
        match try_create_phonemizer() {
            Some(p) => p,
            None => {
                eprintln!("SKIP: NAIST-JDIC dictionary not found. Run with --features naist-jdic.");
                return;
            }
        }
    };
}

#[test]
fn test_phonemize_basic_text() {
    let phonemizer = require_phonemizer!();
    let (tokens, prosody) = phonemizer.phonemize_with_prosody("こんにちは").unwrap();

    // Should start with ^ and end with $
    assert_eq!(tokens.first().map(|s| s.as_str()), Some("^"));
    assert_eq!(tokens.last().map(|s| s.as_str()), Some("$"));

    // Should have prosody info
    assert_eq!(tokens.len(), prosody.len());

    // BOS and EOS should have None prosody
    assert!(prosody.first().unwrap().is_none());
    assert!(prosody.last().unwrap().is_none());
}

#[test]
fn test_phonemize_question() {
    let phonemizer = require_phonemizer!();
    let (tokens, _) = phonemizer.phonemize_with_prosody("本当？").unwrap();
    assert_eq!(tokens.last().map(|s| s.as_str()), Some("?"));
}

#[test]
fn test_phonemize_emphatic_question() {
    let phonemizer = require_phonemizer!();
    // ?! should produce the PUA character for "?!"
    let (tokens, _) = phonemizer.phonemize_with_prosody("本当？！").unwrap();
    // The last token should be the PUA-mapped "?!" character
    let last = tokens.last().unwrap();
    // "?!" maps to U+E016
    assert!(last == "\u{E016}" || last == "?!");
}

#[test]
fn test_phonemize_with_pause() {
    let phonemizer = require_phonemizer!();
    let (tokens, _) = phonemizer
        .phonemize_with_prosody("こんにちは、元気ですか。")
        .unwrap();

    // Should contain a pause marker "_" somewhere
    assert!(tokens.iter().any(|t| t == "_"));
}

#[test]
fn test_phonemize_contains_prosody_marks() {
    let phonemizer = require_phonemizer!();
    let (tokens, _) = phonemizer
        .phonemize_with_prosody("今日は良い天気ですね。")
        .unwrap();

    // Should contain some prosody marks like [, ], #
    let prosody_marks: Vec<&str> = tokens
        .iter()
        .map(|t| t.as_str())
        .filter(|t| matches!(*t, "[" | "]" | "#"))
        .collect();
    assert!(!prosody_marks.is_empty(), "Should contain prosody marks");
}

#[test]
fn test_phonemize_prosody_values() {
    let phonemizer = require_phonemizer!();
    let (tokens, prosody) = phonemizer.phonemize_with_prosody("こんにちは").unwrap();

    // Phoneme tokens should have Some prosody, special tokens should have None
    for (token, p) in tokens.iter().zip(prosody.iter()) {
        if matches!(token.as_str(), "^" | "$" | "_" | "#" | "[" | "]") {
            assert!(
                p.is_none(),
                "Special token {} should have None prosody",
                token
            );
        }
        // Actual phoneme tokens should have Some prosody (usually)
    }
}

#[test]
fn test_post_process_ids_is_noop() {
    let phonemizer = require_phonemizer!();
    let ids = vec![1i64, 2, 3];
    let prosody = vec![Some([0i32, 1, 2]), None, Some([1, 2, 3])];
    let map = std::collections::HashMap::new();

    let (result_ids, result_prosody) =
        phonemizer.post_process_ids(ids.clone(), prosody.clone(), &map);
    assert_eq!(result_ids, ids);
    assert_eq!(result_prosody.len(), prosody.len());
}

#[test]
fn test_language_code() {
    let phonemizer = require_phonemizer!();
    assert_eq!(phonemizer.language_code(), "ja");
}

#[test]
fn test_get_phoneme_id_map_returns_none() {
    let phonemizer = require_phonemizer!();
    assert!(phonemizer.get_phoneme_id_map().is_none());
}

#[test]
fn test_phonemize_n_variant_bilabial() {
    let phonemizer = require_phonemizer!();
    let (tokens, _) = phonemizer.phonemize_with_prosody("さんぽ").unwrap();

    // Should contain N_m (PUA U+E019) before 'p'
    let has_n_m = tokens.iter().any(|t| t == "\u{E019}" || t == "N_m");
    assert!(
        has_n_m,
        "さんぽ should have N_m before p, got: {:?}",
        tokens
    );
}

#[test]
fn test_phonemize_n_variant_velar() {
    let phonemizer = require_phonemizer!();
    let (tokens, _) = phonemizer.phonemize_with_prosody("ぎんこう").unwrap();

    // Should contain N_ng (PUA U+E01B) before 'k'
    let has_n_ng = tokens.iter().any(|t| t == "\u{E01B}" || t == "N_ng");
    assert!(
        has_n_ng,
        "ぎんこう should have N_ng before k, got: {:?}",
        tokens
    );
}

// ---------------------------------------------------------------------------
// detect_primary_language
// ---------------------------------------------------------------------------

#[test]
fn test_detect_primary_language_returns_ja() {
    let phonemizer = require_phonemizer!();
    assert_eq!(
        phonemizer.detect_primary_language("こんにちは"),
        "ja",
        "detect_primary_language should return 'ja' for Japanese phonemizer"
    );
}

#[test]
fn test_detect_primary_language_empty_string() {
    let phonemizer = require_phonemizer!();
    assert_eq!(
        phonemizer.detect_primary_language(""),
        "ja",
        "detect_primary_language should return 'ja' even for empty input"
    );
}
