#![cfg(feature = "japanese")]

use piper_core::phonemize::japanese::JapanesePhonemizer;
use piper_core::phonemize::Phonemizer;

/// Helper to create a phonemizer for tests (using bundled NAIST-JDIC dictionary).
#[cfg(feature = "naist-jdic")]
fn create_phonemizer() -> JapanesePhonemizer {
    JapanesePhonemizer::new_bundled().expect("Failed to create JapanesePhonemizer with bundled dict")
}

/// Fallback: search for dictionary file when naist-jdic feature is not enabled.
#[cfg(not(feature = "naist-jdic"))]
fn create_phonemizer() -> JapanesePhonemizer {
    JapanesePhonemizer::new().expect("Failed to create JapanesePhonemizer. Set JPREPROCESS_DICT env var.")
}

#[test]
fn test_phonemize_basic_text() {
    let phonemizer = create_phonemizer();
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
    let phonemizer = create_phonemizer();
    let (tokens, _) = phonemizer.phonemize_with_prosody("本当？").unwrap();
    assert_eq!(tokens.last().map(|s| s.as_str()), Some("?"));
}

#[test]
fn test_phonemize_emphatic_question() {
    let phonemizer = create_phonemizer();
    // ?! should produce the PUA character for "?!"
    let (tokens, _) = phonemizer.phonemize_with_prosody("本当？！").unwrap();
    // The last token should be the PUA-mapped "?!" character
    let last = tokens.last().unwrap();
    // "?!" maps to U+E016
    assert!(last == "\u{E016}" || last == "?!");
}

#[test]
fn test_phonemize_with_pause() {
    let phonemizer = create_phonemizer();
    let (tokens, _) = phonemizer.phonemize_with_prosody("こんにちは、元気ですか。").unwrap();

    // Should contain a pause marker "_" somewhere
    assert!(tokens.iter().any(|t| t == "_"));
}

#[test]
fn test_phonemize_contains_prosody_marks() {
    let phonemizer = create_phonemizer();
    let (tokens, _) = phonemizer.phonemize_with_prosody("今日は良い天気ですね。").unwrap();

    // Should contain some prosody marks like [, ], #
    let prosody_marks: Vec<&str> = tokens.iter()
        .map(|t| t.as_str())
        .filter(|t| matches!(*t, "[" | "]" | "#"))
        .collect();
    assert!(!prosody_marks.is_empty(), "Should contain prosody marks");
}

#[test]
fn test_phonemize_prosody_values() {
    let phonemizer = create_phonemizer();
    let (tokens, prosody) = phonemizer.phonemize_with_prosody("こんにちは").unwrap();

    // Phoneme tokens should have Some prosody, special tokens should have None
    for (token, p) in tokens.iter().zip(prosody.iter()) {
        if matches!(token.as_str(), "^" | "$" | "_" | "#" | "[" | "]") {
            assert!(p.is_none(), "Special token {} should have None prosody", token);
        }
        // Actual phoneme tokens should have Some prosody (usually)
    }
}

#[test]
fn test_post_process_ids_is_noop() {
    let phonemizer = create_phonemizer();
    let ids = vec![1i64, 2, 3];
    let prosody = vec![Some([0i32, 1, 2]), None, Some([1, 2, 3])];
    let map = std::collections::HashMap::new();

    let (result_ids, result_prosody) = phonemizer.post_process_ids(ids.clone(), prosody.clone(), &map);
    assert_eq!(result_ids, ids);
    assert_eq!(result_prosody.len(), prosody.len());
}

#[test]
fn test_language_code() {
    let phonemizer = create_phonemizer();
    assert_eq!(phonemizer.language_code(), "ja");
}

#[test]
fn test_get_phoneme_id_map_returns_none() {
    let phonemizer = create_phonemizer();
    assert!(phonemizer.get_phoneme_id_map().is_none());
}

#[test]
fn test_phonemize_n_variant_bilabial() {
    let phonemizer = create_phonemizer();
    let (tokens, _) = phonemizer.phonemize_with_prosody("さんぽ").unwrap();

    // Should contain N_m (PUA U+E019) before 'p'
    let has_n_m = tokens.iter().any(|t| t == "\u{E019}" || t == "N_m");
    assert!(has_n_m, "さんぽ should have N_m before p, got: {:?}", tokens);
}

#[test]
fn test_phonemize_n_variant_velar() {
    let phonemizer = create_phonemizer();
    let (tokens, _) = phonemizer.phonemize_with_prosody("ぎんこう").unwrap();

    // Should contain N_ng (PUA U+E01B) before 'k'
    let has_n_ng = tokens.iter().any(|t| t == "\u{E01B}" || t == "N_ng");
    assert!(has_n_ng, "ぎんこう should have N_ng before k, got: {:?}", tokens);
}
