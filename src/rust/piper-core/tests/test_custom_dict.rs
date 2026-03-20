use piper_plus::phonemize::custom_dict::CustomDictionary;
use std::io::Write;
use std::sync::atomic::{AtomicU32, Ordering};

static COUNTER: AtomicU32 = AtomicU32::new(0);

/// Helper to create a temporary JSON file for dictionary loading tests.
fn write_temp_json(content: &str) -> std::path::PathBuf {
    let id = COUNTER.fetch_add(1, Ordering::SeqCst);
    let path = std::env::temp_dir().join(format!(
        "piper_integ_dict_{}_{}.json",
        std::process::id(),
        id
    ));
    let mut f = std::fs::File::create(&path).unwrap();
    f.write_all(content.as_bytes()).unwrap();
    f.flush().unwrap();
    path
}

#[test]
fn test_new_empty_dictionary() {
    let dict = CustomDictionary::new();
    assert!(dict.get_pronunciation("test").is_none());
}

#[test]
fn test_add_word() {
    let mut dict = CustomDictionary::new();
    // "API" is all-uppercase -> stored in case-insensitive map (lowercase normalized)
    dict.add_word("API", "エーピーアイ", 5);
    assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
    assert_eq!(dict.get_pronunciation("API"), Some("エーピーアイ"));
}

#[test]
fn test_case_sensitive_word() {
    let mut dict = CustomDictionary::new();
    // "GitHub" is mixed-case -> stored in case-sensitive map
    dict.add_word("GitHub", "ギットハブ", 5);
    assert_eq!(dict.get_pronunciation("GitHub"), Some("ギットハブ"));
    // Lowercase lookup does NOT match the case-sensitive map
    assert_eq!(dict.get_pronunciation("github"), None);
}

#[test]
fn test_apply_to_text_japanese() {
    let mut dict = CustomDictionary::new();
    dict.add_word("人工知能", "ジンコウチノウ", 5);
    let result = dict.apply_to_text("人工知能は便利です");
    assert_eq!(result, "ジンコウチノウは便利です");
}

#[test]
fn test_apply_to_text_english_boundaries() {
    let mut dict = CustomDictionary::new();
    dict.add_word("api", "エーピーアイ", 5);
    // "API" matches as a whole word via \b boundaries (case-insensitive)
    let result = dict.apply_to_text("The API is ready");
    assert_eq!(result, "The エーピーアイ is ready");
    // "api" inside "rapid" does NOT match because \b requires a word boundary
    let result2 = dict.apply_to_text("rapid development");
    assert_eq!(result2, "rapid development");
}

#[test]
fn test_priority_ordering() {
    let mut dict = CustomDictionary::new();
    dict.add_word("test", "テスト", 3);
    dict.add_word("test", "試験", 5); // higher priority -> overrides
    assert_eq!(dict.get_pronunciation("test"), Some("試験"));
}

#[test]
fn test_priority_lower_does_not_override() {
    let mut dict = CustomDictionary::new();
    dict.add_word("test", "テスト", 5);
    dict.add_word("test", "試験", 3); // lower priority -> does NOT override
    assert_eq!(dict.get_pronunciation("test"), Some("テスト"));
}

#[test]
fn test_load_v1_dictionary() {
    let json = r#"{"version": "1.0", "entries": {"hello": "ハロー", "world": "ワールド"}}"#;
    let path = write_temp_json(json);

    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path).unwrap();
    assert_eq!(dict.get_pronunciation("hello"), Some("ハロー"));
    assert_eq!(dict.get_pronunciation("world"), Some("ワールド"));
}

#[test]
fn test_load_v2_dictionary() {
    let json =
        r#"{"version": "2.0", "entries": {"hello": {"pronunciation": "ハロー", "priority": 5}}}"#;
    let path = write_temp_json(json);

    let mut dict = CustomDictionary::new();
    dict.load_dictionary(&path).unwrap();
    assert_eq!(dict.get_pronunciation("hello"), Some("ハロー"));
}

#[test]
fn test_longest_match_first() {
    let mut dict = CustomDictionary::new();
    dict.add_word("東京", "トウキョウ", 5);
    dict.add_word("東京都", "トウキョウト", 5);
    let result = dict.apply_to_text("東京都に住む");
    // "東京都" (longer) should match first
    assert_eq!(result, "トウキョウトに住む");
}
