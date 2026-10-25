//! Integration tests for the Chinese (Mandarin) phonemizer.
//!
//! The pinyin dictionaries are read from the repo
//! (`src/rust/piper-plus-g2p/data/`). These tests used to look for them in
//! the working directory or `PIPER_PLUS_DICT_DIR`, neither of which CI
//! provides, and returned early without checking anything: every test in
//! this file passed without running.

use piper_plus::phonemize::Phonemizer;
use piper_plus::phonemize::chinese::ChinesePhonemizer;

fn create() -> ChinesePhonemizer {
    let data = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../piper-plus-g2p/data");
    ChinesePhonemizer::new(
        &data.join("pinyin_single.json"),
        &data.join("pinyin_phrases.json"),
    )
    .expect("ChinesePhonemizer::new with the repo's pinyin dictionaries")
}

macro_rules! require_phonemizer {
    () => {
        create()
    };
}

// =========================================================================
// Basic trait API
// =========================================================================

#[test]
fn test_language_code() {
    let p = require_phonemizer!();
    assert_eq!(p.language_code(), "zh");
}

#[test]
fn test_get_phoneme_id_map_returns_none() {
    let p = require_phonemizer!();
    // Chinese phonemizer relies on config.json phoneme_id_map, not an embedded one
    assert!(p.get_phoneme_id_map().is_none());
}

// =========================================================================
// Phonemization output structure
// =========================================================================

#[test]
fn test_basic_phonemize() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("你好").unwrap();
    assert!(!tokens.is_empty(), "tokens should not be empty for '你好'");
    assert_eq!(
        tokens.len(),
        prosody.len(),
        "tokens and prosody must have the same length"
    );
}

#[test]
fn test_single_character() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("你").unwrap();
    assert!(!tokens.is_empty(), "tokens should not be empty for '你'");
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_longer_sentence() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("今天天气很好").unwrap();
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
    // 6 characters should produce more tokens than a single character
    let (single_tokens, _) = p.phonemize_with_prosody("你").unwrap();
    assert!(
        tokens.len() > single_tokens.len(),
        "6 characters should produce more tokens than 1 character"
    );
}

// =========================================================================
// Tone markers (PUA U+E046..U+E04A)
// =========================================================================

#[test]
fn test_tone_markers_present() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("你好").unwrap();
    // Chinese phonemes must contain tone markers (tone1..tone5 mapped to PUA)
    let has_tone = tokens.iter().any(|t| {
        t.chars().next().is_some_and(|c| {
            let code = c as u32;
            (0xE046..=0xE04A).contains(&code)
        })
    });
    assert!(has_tone, "Expected tone markers in: {:?}", tokens);
}

#[test]
fn test_each_syllable_has_tone() {
    let p = require_phonemizer!();
    // "你好" has 2 syllables, so there should be at least 2 tone markers
    let (tokens, _) = p.phonemize_with_prosody("你好").unwrap();
    let tone_count = tokens
        .iter()
        .filter(|t| {
            t.chars().next().is_some_and(|c| {
                let code = c as u32;
                (0xE046..=0xE04A).contains(&code)
            })
        })
        .count();
    assert!(
        tone_count >= 2,
        "Expected at least 2 tone markers for '你好', got {}: {:?}",
        tone_count,
        tokens
    );
}

// =========================================================================
// Prosody values
// =========================================================================

#[test]
fn test_prosody_has_tone() {
    let p = require_phonemizer!();
    let (_, prosody) = p.phonemize_with_prosody("你").unwrap();
    // a1 should be tone (1-5) for phoneme tokens
    let has_tone_prosody = prosody.iter().flatten().any(|pi| pi.a1 >= 1 && pi.a1 <= 5);
    assert!(
        has_tone_prosody,
        "Expected tone in prosody a1 field: {:?}",
        prosody
    );
}

#[test]
fn test_prosody_word_position() {
    let p = require_phonemizer!();
    // "你好" is a 2-character word; a2 (syllable position) and a3 (word length)
    // should reflect this
    let (_, prosody) = p.phonemize_with_prosody("你好").unwrap();
    let has_position = prosody.iter().flatten().any(|pi| pi.a2 >= 1);
    assert!(
        has_position,
        "Expected syllable position (a2 >= 1) in prosody: {:?}",
        prosody
    );
    let has_word_len = prosody.iter().flatten().any(|pi| pi.a3 >= 1);
    assert!(
        has_word_len,
        "Expected word length (a3 >= 1) in prosody: {:?}",
        prosody
    );
}

// =========================================================================
// Punctuation handling
// =========================================================================

#[test]
fn test_chinese_punctuation_converted() {
    let p = require_phonemizer!();
    // Chinese period 。 should be converted to "."
    let (tokens, _) = p.phonemize_with_prosody("你好。").unwrap();
    let has_period = tokens.iter().any(|t| t == ".");
    assert!(
        has_period,
        "Expected '.' from Chinese period '。' in: {:?}",
        tokens
    );
}

#[test]
fn test_chinese_comma_converted() {
    let p = require_phonemizer!();
    // Chinese comma ， should be converted to ","
    let (tokens, _) = p.phonemize_with_prosody("你好，世界").unwrap();
    let has_comma = tokens.iter().any(|t| t == ",");
    assert!(
        has_comma,
        "Expected ',' from Chinese comma '，' in: {:?}",
        tokens
    );
}

#[test]
fn test_punctuation_has_none_prosody() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("你好。").unwrap();
    // Find the "." token and verify its prosody is None
    for (token, pi) in tokens.iter().zip(prosody.iter()) {
        if token == "." {
            assert!(
                pi.is_none(),
                "Punctuation '.' should have None prosody, got: {:?}",
                pi
            );
        }
    }
}

// =========================================================================
// Tone sandhi
// =========================================================================

#[test]
fn test_third_tone_sandhi() {
    let p = require_phonemizer!();
    // "你好" (nǐ hǎo): both are tone 3, so first should become tone 2
    // After sandhi: ní hǎo → tone2 + tone3
    let (tokens, prosody) = p.phonemize_with_prosody("你好").unwrap();

    // Collect tones from prosody (a1 field of the first phoneme in each syllable)
    let tones: Vec<i32> = prosody
        .iter()
        .flatten()
        .filter(|pi| pi.a1 >= 1 && pi.a1 <= 5)
        .map(|pi| pi.a1)
        .collect();

    // We should see tone 2 somewhere (from sandhi on 你)
    assert!(
        tones.contains(&2),
        "Expected tone 2 from third-tone sandhi in '你好', tones={:?}, tokens={:?}",
        tones,
        tokens
    );
}

// =========================================================================
// Post-processing (BOS/EOS)
// =========================================================================

#[test]
fn test_post_process_ids_matches_default() {
    // Same BOS / padding / EOS as the production path (G2pAdapter ->
    // default_post_process_ids): ^ _ a _ b _ c _ $
    let p = require_phonemizer!();
    let mut map = std::collections::HashMap::new();
    map.insert("_".to_string(), vec![0i64]);
    map.insert("^".to_string(), vec![1]);
    map.insert("$".to_string(), vec![2]);
    let ids = vec![10i64, 11, 12];
    let prosody = vec![Some([0i32, 1, 2]), None, Some([1, 2, 3])];

    let (result_ids, result_prosody) = p.post_process_ids(ids.clone(), prosody.clone(), &map);
    assert_eq!(result_ids, vec![1, 0, 10, 0, 11, 0, 12, 0, 2]);
    assert_eq!(
        (result_ids, result_prosody),
        piper_plus_g2p::multilingual::default_post_process_ids(ids, prosody, &map, "$")
    );
}

// =========================================================================
// Edge cases
// =========================================================================

#[test]
fn test_empty_text() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("").unwrap();
    assert!(tokens.is_empty(), "Empty text should produce no tokens");
    assert!(prosody.is_empty(), "Empty text should produce no prosody");
}

#[test]
fn test_whitespace_only() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody(" ").unwrap();
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_mixed_chinese_and_ascii() {
    let p = require_phonemizer!();
    // Text mixing Chinese characters with ASCII letters
    let (tokens, prosody) = p.phonemize_with_prosody("Hello你好").unwrap();
    assert!(!tokens.is_empty());
    assert_eq!(tokens.len(), prosody.len());
}

#[test]
fn test_digits_pass_through() {
    let p = require_phonemizer!();
    let (tokens, prosody) = p.phonemize_with_prosody("123").unwrap();
    assert_eq!(tokens.len(), prosody.len());
    // Digits should appear as-is in the token list
    let has_digit = tokens.iter().any(|t| t.chars().all(|c| c.is_ascii_digit()));
    assert!(
        has_digit,
        "Digits should pass through as tokens: {:?}",
        tokens
    );
}

// =========================================================================
// IPA token content verification
// =========================================================================

#[test]
fn test_contains_ipa_vowels_or_consonants() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("你好").unwrap();
    // Should contain actual IPA phoneme tokens (not just tone markers)
    // Filter out PUA tone markers and check remaining tokens exist
    let non_tone_tokens: Vec<&String> = tokens
        .iter()
        .filter(|t| {
            !t.chars().next().is_some_and(|c| {
                let code = c as u32;
                (0xE046..=0xE04A).contains(&code)
            })
        })
        .collect();
    assert!(
        !non_tone_tokens.is_empty(),
        "Expected IPA phoneme tokens besides tone markers in: {:?}",
        tokens
    );
}

#[test]
fn test_no_raw_pinyin_in_output() {
    let p = require_phonemizer!();
    let (tokens, _) = p.phonemize_with_prosody("你好世界").unwrap();
    // Output should be IPA tokens (possibly PUA-mapped), not raw pinyin strings
    // like "ni3", "hao3", etc.
    for token in &tokens {
        assert!(
            !token.chars().last().is_some_and(|c| c.is_ascii_digit()),
            "Token {:?} looks like raw pinyin with tone number; expected IPA",
            token
        );
    }
}

// =========================================================================
// detect_primary_language
// =========================================================================

#[test]
fn test_detect_primary_language_returns_zh() {
    let p = require_phonemizer!();
    assert_eq!(
        p.detect_primary_language("你好世界"),
        "zh",
        "detect_primary_language should return 'zh' for Chinese phonemizer"
    );
}

#[test]
fn test_detect_primary_language_empty_string() {
    let p = require_phonemizer!();
    assert_eq!(
        p.detect_primary_language(""),
        "zh",
        "detect_primary_language should return 'zh' even for empty input"
    );
}
