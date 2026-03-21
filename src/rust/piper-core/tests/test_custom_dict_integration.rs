//! Integration tests for the custom dictionary feature.
//!
//! These tests verify that `CustomDictionary` works correctly in the context
//! of the phonemizer pipeline, including file loading, multi-file merging,
//! priority resolution, case sensitivity, and word boundary behaviour.

use piper_plus::phonemize::custom_dict::CustomDictionary;
use std::io::Write;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

/// Helper to create a temporary JSON file with a unique name.
fn write_temp_json(content: &str) -> std::path::PathBuf {
    let id = COUNTER.fetch_add(1, Ordering::SeqCst);
    let path = std::env::temp_dir().join(format!(
        "piper_integ_dict2_{}_{}.json",
        std::process::id(),
        id
    ));
    let mut f = std::fs::File::create(&path).unwrap();
    f.write_all(content.as_bytes()).unwrap();
    f.flush().unwrap();
    path
}

// -----------------------------------------------------------------------
// 1. Custom dict applied before phonemization (Japanese)
// -----------------------------------------------------------------------

#[cfg(feature = "japanese")]
#[test]
fn test_custom_dict_applied_before_phonemization_ja() {
    use piper_plus::phonemize::Phonemizer;
    use piper_plus::phonemize::japanese::JapanesePhonemizer;

    let json = r#"{"version":"1.0","entries":{"テスト":"テ ス ト"}}"#;
    let path = write_temp_json(json);

    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path).unwrap();

    // Verify the dictionary applies the replacement
    let replaced = dict.apply_to_text("テストです");
    assert_eq!(replaced, "テ ス トです");

    // Now verify that phonemization succeeds with the replaced text.
    // new_bundled() requires the naist-jdic feature (part of default).
    #[cfg(feature = "naist-jdic")]
    {
        let mut phonemizer =
            JapanesePhonemizer::new_bundled().expect("Failed to create JapanesePhonemizer");
        phonemizer.set_dictionary(dict);

        let (tokens, prosody) = phonemizer
            .phonemize_with_prosody("テストです")
            .expect("phonemization should succeed");

        // Should produce valid tokens: begins with ^, ends with $ or ?
        assert_eq!(tokens.first().map(|s| s.as_str()), Some("^"));
        assert!(
            tokens.last().map(|s| s.as_str()) == Some("$")
                || tokens.last().map(|s| s.as_str()) == Some("?"),
            "expected sentence-end marker, got {:?}",
            tokens.last()
        );
        assert_eq!(tokens.len(), prosody.len());
    }
}

// -----------------------------------------------------------------------
// 2. Custom dict applied before phonemization (English)
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_applied_before_phonemization_en() {
    let json = r#"{"version":"1.0","entries":{"hello":"world"}}"#;
    let path = write_temp_json(json);

    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path).unwrap();

    let result = dict.apply_to_text("hello there");
    assert_eq!(result, "world there");
}

// -----------------------------------------------------------------------
// 3. Multiple dictionary files merged
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_multiple_files() {
    let json1 = r#"{"version":"1.0","entries":{"API":"エーピーアイ"}}"#;
    let json2 = r#"{"version":"1.0","entries":{"GPU":"ジーピーユー"}}"#;
    let path1 = write_temp_json(json1);
    let path2 = write_temp_json(json2);

    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path1).unwrap();
    dict.load_dictionary(&path2).unwrap();

    // Entries from both files should be available
    assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
    assert_eq!(dict.get_pronunciation("gpu"), Some("ジーピーユー"));

    // apply_to_text replaces both
    let result = dict.apply_to_text("API and GPU");
    assert_eq!(result, "エーピーアイ and ジーピーユー");
}

// -----------------------------------------------------------------------
// 4. Priority override across files
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_priority_override() {
    // File 1: lower priority
    let json_low =
        r#"{"version":"2.0","entries":{"API":{"pronunciation":"エーピーアイ低","priority":3}}}"#;
    // File 2: higher priority
    let json_high =
        r#"{"version":"2.0","entries":{"API":{"pronunciation":"エーピーアイ高","priority":8}}}"#;
    let path_low = write_temp_json(json_low);
    let path_high = write_temp_json(json_high);

    // Load low-priority first, then high-priority -> high wins
    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path_low).unwrap();
    dict.load_dictionary(&path_high).unwrap();
    assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ高"));

    // Load high-priority first, then low-priority -> high still wins
    let mut dict2 = CustomDictionary::new();
    dict2.load_dictionary(&path_high).unwrap();
    dict2.load_dictionary(&path_low).unwrap();
    assert_eq!(dict2.get_pronunciation("api"), Some("エーピーアイ高"));
}

// -----------------------------------------------------------------------
// 5. Case sensitivity
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_case_sensitivity() {
    let mut dict = CustomDictionary::new();

    // Mixed-case word -> case-sensitive storage
    dict.add_word("PyTorch", "パイトーチ", 5);

    // Exact case matches
    assert_eq!(dict.get_pronunciation("PyTorch"), Some("パイトーチ"));
    // Different case does NOT match the case-sensitive entry
    assert_eq!(dict.get_pronunciation("pytorch"), None);
    assert_eq!(dict.get_pronunciation("PYTORCH"), None);

    // All-lowercase word -> case-insensitive storage
    dict.add_word("tensorflow", "テンソルフロー", 5);

    // Any case matches a case-insensitive entry
    assert_eq!(dict.get_pronunciation("tensorflow"), Some("テンソルフロー"));
    assert_eq!(dict.get_pronunciation("TensorFlow"), Some("テンソルフロー"));
    assert_eq!(dict.get_pronunciation("TENSORFLOW"), Some("テンソルフロー"));

    // All-uppercase word -> also case-insensitive storage (lowercase normalised)
    dict.add_word("CUDA", "クーダ", 5);
    assert_eq!(dict.get_pronunciation("cuda"), Some("クーダ"));
    assert_eq!(dict.get_pronunciation("CUDA"), Some("クーダ"));
    assert_eq!(dict.get_pronunciation("Cuda"), Some("クーダ"));

    // Verify apply_to_text respects case sensitivity
    let result = dict.apply_to_text("PyTorch and pytorch");
    // "PyTorch" (exact case) is replaced; "pytorch" is not (case-sensitive entry)
    assert_eq!(result, "パイトーチ and pytorch");
}

// -----------------------------------------------------------------------
// 6. Empty / invalid file handled gracefully
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_empty_file_graceful() {
    // Completely empty file -> JSON parse error
    let path_empty = write_temp_json("");
    let mut dict = CustomDictionary::new();
    let result = dict.load_dictionary(&path_empty);
    assert!(
        result.is_err(),
        "loading an empty file should return an error"
    );

    // Invalid JSON
    let path_bad = write_temp_json("this is not json");
    let result2 = dict.load_dictionary(&path_bad);
    assert!(
        result2.is_err(),
        "loading invalid JSON should return an error"
    );

    // Nonexistent file
    let result3 = dict.load_dictionary(std::path::Path::new("/no/such/file/dict.json"));
    assert!(
        result3.is_err(),
        "loading a nonexistent file should return an error"
    );

    // Verify the dictionary still works after failed loads (no panic, no corruption)
    dict.add_word("test", "テスト", 5);
    assert_eq!(dict.get_pronunciation("test"), Some("テスト"));
}

// -----------------------------------------------------------------------
// 7. Japanese word boundary — no false negatives
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_japanese_word_boundary() {
    let mut dict = CustomDictionary::new();
    // "AI" is ASCII -> uses \b word-boundary matching
    dict.add_word("AI", "エーアイ", 5);

    // "AI技術" — "AI" is followed by a non-ASCII char; \b should match at
    // the boundary between "I" and "技".
    let result = dict.apply_to_text("AI技術");
    assert_eq!(result, "エーアイ技術");

    // Japanese word replacement: simple substring match
    dict.add_word("人工知能", "ジンコウチノウ", 5);
    let result2 = dict.apply_to_text("人工知能とAI技術");
    assert_eq!(result2, "ジンコウチノウとエーアイ技術");
}

// -----------------------------------------------------------------------
// 8. No partial match for English words
// -----------------------------------------------------------------------

#[test]
fn test_custom_dict_no_partial_match_english() {
    let mut dict = CustomDictionary::new();
    dict.add_word("API", "エーピーアイ", 5);

    // "API" as a standalone word is replaced
    let result = dict.apply_to_text("rapid API call");
    assert_eq!(result, "rapid エーピーアイ call");

    // "API" inside "rapid" is NOT replaced — \b prevents partial match
    let result2 = dict.apply_to_text("rapid development");
    assert_eq!(result2, "rapid development");

    // Also verify that "API" embedded in a longer alphanumeric string is not replaced
    let result3 = dict.apply_to_text("myAPIkey");
    assert_eq!(result3, "myAPIkey");

    // But "API" surrounded by punctuation IS replaced (word boundary at punctuation)
    let result4 = dict.apply_to_text("Use (API) here");
    assert_eq!(result4, "Use (エーピーアイ) here");
}
