use piper_plus::phonemize::Phonemizer;
use piper_plus::phonemize::english::EnglishPhonemizer;

fn try_create_phonemizer() -> Option<EnglishPhonemizer> {
    EnglishPhonemizer::new().ok()
}

macro_rules! require_phonemizer {
    () => {
        match try_create_phonemizer() {
            Some(p) => p,
            None => {
                eprintln!("SKIP: CMU dictionary not found");
                return;
            }
        }
    };
}

// ---------------------------------------------------------------------------
// Basic trait methods
// ---------------------------------------------------------------------------

#[test]
fn test_language_code() {
    let p = require_phonemizer!();
    assert_eq!(p.language_code(), "en");
}

#[test]
fn test_get_phoneme_id_map_returns_none() {
    let p = require_phonemizer!();
    assert!(p.get_phoneme_id_map().is_none());
}

// ---------------------------------------------------------------------------
// Phonemization — basic output checks
// ---------------------------------------------------------------------------

#[test]
fn test_basic_phonemize() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("hello").unwrap();
    assert!(
        !tokens.is_empty(),
        "phonemize('hello') should produce tokens"
    );
    assert_eq!(
        tokens.len(),
        prosody.len(),
        "tokens and prosody must have equal length"
    );
}

#[test]
fn test_phonemize_multi_word() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("hello world").unwrap();
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
}

// ---------------------------------------------------------------------------
// Stress markers
// ---------------------------------------------------------------------------

#[test]
fn test_stress_markers() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello").unwrap();
    // "hello" has primary stress on the second syllable (OW1),
    // so the output should contain the primary stress marker.
    let has_stress = tokens.iter().any(|t| t == "\u{02C8}" || t == "\u{02CC}");
    assert!(
        has_stress,
        "phonemize('hello') should contain stress marker, got: {:?}",
        tokens
    );
}

#[test]
fn test_primary_stress_marker_present() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello").unwrap();
    // "hello" should have primary stress marker (U+02C8)
    assert!(
        tokens.iter().any(|t| t == "\u{02C8}"),
        "expected primary stress marker in 'hello', got: {:?}",
        tokens
    );
}

#[test]
fn test_secondary_stress_marker() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("information").unwrap();
    // "information" has secondary stress (IH2) on the first syllable
    let has_secondary = tokens.iter().any(|t| t == "\u{02CC}");
    assert!(
        has_secondary,
        "phonemize('information') should contain secondary stress marker, got: {:?}",
        tokens
    );
}

// ---------------------------------------------------------------------------
// Function word stress removal
// ---------------------------------------------------------------------------

#[test]
fn test_function_word_no_stress() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("the").unwrap();
    // "the" is a function word — stress markers should be removed
    assert!(
        !tokens.iter().any(|t| t == "\u{02C8}"),
        "'the' is a function word and should not have primary stress, got: {:?}",
        tokens
    );
}

#[test]
fn test_function_word_are_no_stress() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("are").unwrap();
    assert!(
        !tokens.iter().any(|t| t == "\u{02C8}"),
        "'are' is a function word and should not have primary stress, got: {:?}",
        tokens
    );
}

#[test]
fn test_function_word_you_no_stress() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("you").unwrap();
    assert!(
        !tokens.iter().any(|t| t == "\u{02C8}"),
        "'you' is a function word and should not have primary stress, got: {:?}",
        tokens
    );
}

// ---------------------------------------------------------------------------
// Word boundary spaces
// ---------------------------------------------------------------------------

#[test]
fn test_word_boundary_space() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello world").unwrap();
    assert!(
        tokens.contains(&" ".to_string()),
        "multi-word input should contain word boundary space, got: {:?}",
        tokens
    );
}

#[test]
fn test_no_leading_space() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello").unwrap();
    assert_ne!(
        tokens.first().map(|s| s.as_str()),
        Some(" "),
        "single word should not start with space"
    );
}

// ---------------------------------------------------------------------------
// Punctuation handling
// ---------------------------------------------------------------------------

#[test]
fn test_punctuation_attached_to_word() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello, world").unwrap();
    // Comma should appear in the token list
    assert!(
        tokens.contains(&",".to_string()),
        "comma should appear in token list, got: {:?}",
        tokens
    );
    // Find the comma position — it should NOT be preceded by a space
    if let Some(comma_pos) = tokens.iter().position(|t| t == ",")
        && comma_pos > 0
    {
        assert_ne!(
            tokens[comma_pos - 1],
            " ",
            "comma should not be preceded by a space (attached to previous word)"
        );
    }
}

// ---------------------------------------------------------------------------
// Context-dependent IPA conversions
// ---------------------------------------------------------------------------

#[test]
fn test_aa_r_merge() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("car").unwrap();
    // "car" = K AA1 R -> should produce merged ɑːɹ
    let ipa_string: String = tokens.join("");
    assert!(
        ipa_string.contains("\u{0251}\u{02D0}\u{0279}"), // ɑːɹ
        "phonemize('car') should contain merged AA+R -> ɑːɹ, got tokens: {:?}",
        tokens
    );
}

#[test]
fn test_stressed_er() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("bird").unwrap();
    // "bird" = B ER1 D -> ER1 should become ɜː
    let ipa_string: String = tokens.join("");
    assert!(
        ipa_string.contains("\u{025C}\u{02D0}"), // ɜː
        "phonemize('bird') should contain stressed ER -> ɜː, got tokens: {:?}",
        tokens
    );
}

#[test]
fn test_unstressed_ah_to_schwa() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("hello").unwrap();
    // "hello" = HH AH0 L OW1 -> AH0 should become ə (schwa)
    assert!(
        tokens.contains(&"\u{0259}".to_string()), // ə
        "phonemize('hello') should contain schwa for unstressed AH, got: {:?}",
        tokens
    );
}

// ---------------------------------------------------------------------------
// Prosody feature values
// ---------------------------------------------------------------------------

#[test]
fn test_prosody_a1_always_zero() {
    let p = require_phonemizer!();
    let (_, prosody) = p.phonemize_with_prosody("hello world").unwrap();
    for p_info in prosody.iter().flatten() {
        assert_eq!(p_info.a1, 0, "English prosody a1 should always be 0");
    }
}

#[test]
fn test_prosody_a2_stress_level() {
    let p = require_phonemizer!();
    let (_, prosody) = p.phonemize_with_prosody("hello").unwrap();
    // "hello" should have at least one phoneme with a2=2 (primary stress)
    let has_primary = prosody.iter().flatten().any(|p| p.a2 == 2);
    assert!(
        has_primary,
        "phonemize('hello') should have at least one phoneme with a2=2 (primary stress)"
    );
}

#[test]
fn test_prosody_a3_word_phoneme_count() {
    let p = require_phonemizer!();
    let (_, prosody) = p.phonemize_with_prosody("cat").unwrap();
    // "cat" = K AE1 T -> 3 IPA characters -> a3 should be 3
    let a3_values: Vec<i32> = prosody.iter().flatten().map(|p| p.a3).collect();
    assert!(
        a3_values.iter().any(|&v| v > 0),
        "phonemize('cat') should have positive a3 values"
    );
}

// ---------------------------------------------------------------------------
// Post-process IDs: BOS/EOS/padding insertion
// ---------------------------------------------------------------------------

#[test]
fn test_post_process_ids_adds_bos_eos() {
    let p = require_phonemizer!();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("_".to_string(), vec![0i64]);
    id_map.insert("^".to_string(), vec![1]);
    id_map.insert("$".to_string(), vec![2]);
    id_map.insert("a".to_string(), vec![10]);

    let ids = vec![10i64];
    let prosody = vec![None];
    let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);

    // Should have: [1, 0, 10, 0, 2] = BOS, pad, a, pad, EOS
    assert_eq!(
        result_ids[0], 1,
        "first ID should be BOS (^=1), got: {:?}",
        result_ids
    );
    assert_eq!(
        *result_ids.last().unwrap(),
        2,
        "last ID should be EOS ($=2), got: {:?}",
        result_ids
    );
    assert_eq!(result_ids, vec![1, 0, 10, 0, 2]);
    assert_eq!(
        result_ids.len(),
        result_prosody.len(),
        "IDs and prosody must have equal length"
    );
}

#[test]
fn test_post_process_ids_bos_eos_prosody_is_none() {
    let p = require_phonemizer!();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("_".to_string(), vec![0i64]);
    id_map.insert("^".to_string(), vec![1]);
    id_map.insert("$".to_string(), vec![2]);

    let ids = vec![10i64];
    let prosody = vec![Some([1i32, 2, 3])];
    let (_result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);

    // BOS prosody should be None
    assert!(result_prosody[0].is_none(), "BOS prosody should be None");
    // EOS prosody should be None
    assert!(
        result_prosody.last().unwrap().is_none(),
        "EOS prosody should be None"
    );
}

#[test]
fn test_post_process_ids_padding_between_phonemes() {
    let p = require_phonemizer!();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("_".to_string(), vec![0i64]);
    id_map.insert("^".to_string(), vec![1]);
    id_map.insert("$".to_string(), vec![2]);

    let ids = vec![10i64, 20];
    let prosody = vec![None, None];
    let (result_ids, _) = p.post_process_ids(ids, prosody, &id_map);

    // Expected: [1, 0, 10, 0, 20, 0, 2]
    assert_eq!(result_ids, vec![1, 0, 10, 0, 20, 0, 2]);
}

#[test]
fn test_post_process_ids_no_padding_after_pad_token() {
    let p = require_phonemizer!();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("_".to_string(), vec![0i64]);
    id_map.insert("^".to_string(), vec![1]);
    id_map.insert("$".to_string(), vec![2]);

    // ID 0 is a pad token — should NOT get another pad after it
    let ids = vec![10i64, 0, 20];
    let prosody = vec![None, None, None];
    let (result_ids, _) = p.post_process_ids(ids, prosody, &id_map);

    // Expected: [1, 0, 10, 0, 0, 20, 0, 2]
    assert_eq!(result_ids, vec![1, 0, 10, 0, 0, 20, 0, 2]);
}

#[test]
fn test_post_process_ids_empty_input() {
    let p = require_phonemizer!();
    let mut id_map = std::collections::HashMap::new();
    id_map.insert("_".to_string(), vec![0i64]);
    id_map.insert("^".to_string(), vec![1]);
    id_map.insert("$".to_string(), vec![2]);

    let ids: Vec<i64> = vec![];
    let prosody: Vec<Option<[i32; 3]>> = vec![];
    let (result_ids, result_prosody) = p.post_process_ids(ids, prosody, &id_map);

    // Should have: [1, 0, 2] = BOS, pad, EOS
    assert_eq!(result_ids, vec![1, 0, 2]);
    assert_eq!(result_ids.len(), result_prosody.len());
}

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

#[test]
fn test_empty_input() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("").unwrap();
    assert!(tokens.is_empty());
    assert!(prosody.is_empty());
}

#[test]
fn test_whitespace_only_input() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("   ").unwrap();
    assert!(tokens.is_empty());
    assert!(prosody.is_empty());
}

#[test]
fn test_unknown_word_does_not_error() {
    let p = require_phonemizer!();
    // "xyzzyplugh" is not in any dictionary — should not panic or error
    let result = p.phonemize_with_prosody("xyzzyplugh");
    assert!(result.is_ok());
}

#[test]
fn test_mixed_known_unknown_words() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("hello xyzzy world").unwrap();
    // Should still produce tokens for the known words at minimum
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
}

// ---------------------------------------------------------------------------
// detect_primary_language
// ---------------------------------------------------------------------------

#[test]
fn test_detect_primary_language_returns_en() {
    let p = require_phonemizer!();
    assert_eq!(
        p.detect_primary_language("hello world"),
        "en",
        "detect_primary_language should return 'en' for English phonemizer"
    );
}

#[test]
fn test_detect_primary_language_empty_string() {
    let p = require_phonemizer!();
    assert_eq!(
        p.detect_primary_language(""),
        "en",
        "detect_primary_language should return 'en' even for empty input"
    );
}
