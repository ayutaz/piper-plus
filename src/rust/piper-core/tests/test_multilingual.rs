//! Integration tests for multilingual phonemizer and Unicode language detection.
//!
//! Validates `UnicodeLanguageDetector`, `segment_text`, and
//! `default_post_process_ids` from `piper_plus::phonemize::multilingual`.

use std::collections::HashMap;

use piper_plus::phonemize::multilingual::{
    UnicodeLanguageDetector, default_post_process_ids, segment_text,
};

// ===========================================================================
// Helpers
// ===========================================================================

fn make_detector(langs: &[&str], default_latin: &str) -> UnicodeLanguageDetector {
    let lang_strings: Vec<String> = langs.iter().map(|s| s.to_string()).collect();
    UnicodeLanguageDetector::new(&lang_strings, default_latin)
}

// ===========================================================================
// Language Detection — Kana
// ===========================================================================

#[test]
fn test_detect_hiragana_as_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{3042}', false), Some("ja")); // あ
    assert_eq!(detector.detect_char('\u{3093}', false), Some("ja")); // ん
}

#[test]
fn test_detect_katakana_as_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{30A2}', false), Some("ja")); // ア
    assert_eq!(detector.detect_char('\u{30F3}', false), Some("ja")); // ン
}

#[test]
fn test_detect_katakana_phonetic_extension() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{31F0}', false), Some("ja")); // ㇰ
}

#[test]
fn test_kana_not_detected_when_ja_absent() {
    let detector = make_detector(&["en", "zh"], "en");
    assert_eq!(detector.detect_char('\u{3042}', false), None); // あ — no JA
}

// ===========================================================================
// Language Detection — Hangul
// ===========================================================================

#[test]
fn test_detect_hangul_syllable_as_korean() {
    let detector = make_detector(&["ja", "ko", "en"], "en");
    assert_eq!(detector.detect_char('\u{D55C}', false), Some("ko")); // 한
}

#[test]
fn test_detect_hangul_range_boundaries() {
    let detector = make_detector(&["ko", "en"], "en");
    assert_eq!(detector.detect_char('\u{AC00}', false), Some("ko")); // 가 (first syllable)
    assert_eq!(detector.detect_char('\u{D7AF}', false), Some("ko")); // last in range
}

#[test]
fn test_detect_hangul_jamo() {
    let detector = make_detector(&["ko", "en"], "en");
    assert_eq!(detector.detect_char('\u{1100}', false), Some("ko")); // ᄀ (Jamo)
    assert_eq!(detector.detect_char('\u{3131}', false), Some("ko")); // ㄱ (Compat Jamo)
}

#[test]
fn test_hangul_not_detected_when_ko_absent() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{D55C}', false), None);
}

// ===========================================================================
// Language Detection — CJK disambiguation
// ===========================================================================

#[test]
fn test_detect_cjk_with_kana_context_is_japanese() {
    let detector = make_detector(&["ja", "zh"], "en");
    // CJK ideograph with kana context -> Japanese
    assert_eq!(detector.detect_char('\u{6F22}', true), Some("ja")); // 漢
}

#[test]
fn test_detect_cjk_without_kana_context_is_chinese() {
    let detector = make_detector(&["ja", "zh"], "en");
    // CJK ideograph without kana context -> Chinese
    assert_eq!(detector.detect_char('\u{6F22}', false), Some("zh")); // 漢
}

#[test]
fn test_detect_cjk_ja_only_always_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    // Only JA supported, no ZH -> always Japanese regardless of context
    assert_eq!(detector.detect_char('\u{4E16}', false), Some("ja")); // 世
    assert_eq!(detector.detect_char('\u{4E16}', true), Some("ja"));
}

#[test]
fn test_detect_cjk_zh_only_always_chinese() {
    let detector = make_detector(&["zh", "en"], "en");
    // Only ZH supported -> always Chinese
    assert_eq!(detector.detect_char('\u{4E16}', false), Some("zh"));
    assert_eq!(detector.detect_char('\u{4E16}', true), Some("zh"));
}

#[test]
fn test_detect_cjk_no_ja_no_zh_returns_none() {
    let detector = make_detector(&["en", "ko"], "en");
    assert_eq!(detector.detect_char('\u{4E16}', false), None);
}

#[test]
fn test_detect_cjk_extension_a() {
    let detector = make_detector(&["zh", "en"], "en");
    assert_eq!(detector.detect_char('\u{3400}', false), Some("zh")); // CJK Extension A start
}

#[test]
fn test_detect_cjk_compatibility() {
    let detector = make_detector(&["zh", "en"], "en");
    assert_eq!(detector.detect_char('\u{F900}', false), Some("zh")); // CJK Compatibility start
}

// ===========================================================================
// Language Detection — Latin characters
// ===========================================================================

#[test]
fn test_detect_latin_as_default_language() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('a', false), Some("en"));
    assert_eq!(detector.detect_char('Z', false), Some("en"));
}

#[test]
fn test_detect_accented_latin() {
    let detector = make_detector(&["ja", "fr"], "fr");
    assert_eq!(detector.detect_char('\u{00E9}', false), Some("fr")); // e-acute
    assert_eq!(detector.detect_char('\u{00C0}', false), Some("fr")); // A-grave
}

#[test]
fn test_detect_latin_with_spanish_default() {
    let detector = make_detector(&["ja", "es"], "es");
    assert_eq!(detector.detect_char('H', false), Some("es"));
    assert_eq!(detector.detect_char('\u{00F1}', false), Some("es")); // n-tilde
}

#[test]
fn test_detect_fullwidth_latin_as_default() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{FF21}', false), Some("en")); // fullwidth A
    assert_eq!(detector.detect_char('\u{FF5A}', false), Some("en")); // fullwidth z
}

#[test]
fn test_latin_none_when_default_absent() {
    let detector = make_detector(&["ja", "zh"], "en");
    // "en" is not in languages set -> None for Latin
    assert_eq!(detector.detect_char('a', false), None);
}

// ===========================================================================
// Language Detection — Japanese punctuation
// ===========================================================================

#[test]
fn test_detect_cjk_punctuation_as_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{3001}', false), Some("ja")); // ideographic comma
    assert_eq!(detector.detect_char('\u{3002}', false), Some("ja")); // ideographic period
    assert_eq!(detector.detect_char('\u{300C}', false), Some("ja")); // left corner bracket
}

#[test]
fn test_fullwidth_symbol_as_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{FF01}', false), Some("ja")); // fullwidth exclamation
}

// ===========================================================================
// Language Detection — Neutral characters
// ===========================================================================

#[test]
fn test_detect_space_is_neutral() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char(' ', false), None);
}

#[test]
fn test_detect_digit_is_neutral() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('0', false), None);
    assert_eq!(detector.detect_char('9', false), None);
}

#[test]
fn test_detect_ascii_punctuation_is_neutral() {
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char(',', false), None);
    assert_eq!(detector.detect_char('.', false), None);
    assert_eq!(detector.detect_char('!', false), None);
    assert_eq!(detector.detect_char('?', false), None);
}

#[test]
fn test_detect_multiplication_sign_is_neutral() {
    // U+00D7 is inside the accented Latin range but excluded
    let detector = make_detector(&["ja", "en"], "en");
    assert_eq!(detector.detect_char('\u{00D7}', false), None);
}

// ===========================================================================
// has_kana
// ===========================================================================

#[test]
fn test_has_kana_with_kana() {
    let detector = make_detector(&["ja", "en"], "en");
    assert!(detector.has_kana("こんにちは world"));
    assert!(detector.has_kana("テスト"));
}

#[test]
fn test_has_kana_without_kana() {
    let detector = make_detector(&["ja", "en"], "en");
    assert!(!detector.has_kana("Hello world"));
    assert!(!detector.has_kana("你好世界"));
    assert!(!detector.has_kana("12345"));
}

// ===========================================================================
// Segmentation — Pure language text
// ===========================================================================

#[test]
fn test_segment_pure_japanese() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("こんにちは", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "ja");
    assert_eq!(segments[0].1, "こんにちは");
}

#[test]
fn test_segment_pure_english() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("hello world", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "en");
    assert_eq!(segments[0].1, "hello world");
}

#[test]
fn test_segment_pure_chinese() {
    let detector = make_detector(&["zh", "en"], "en");
    let segments = segment_text("你好世界", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "zh");
}

// ===========================================================================
// Segmentation — Mixed language text
// ===========================================================================

#[test]
fn test_segment_mixed_ja_en() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("今日はgoodですね", &detector);
    // Expect at least JA and EN segments
    assert!(
        segments.len() >= 2,
        "expected >= 2 segments, got {}",
        segments.len()
    );
    // First segment should be Japanese
    assert_eq!(segments[0].0, "ja");
    // There should be an English segment somewhere
    assert!(
        segments.iter().any(|(lang, _)| lang == "en"),
        "expected an English segment"
    );
}

#[test]
fn test_segment_mixed_ja_en_three_segments() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("今日はgood morningですね", &detector);
    assert_eq!(segments.len(), 3);
    assert_eq!(segments[0].0, "ja");
    assert_eq!(segments[0].1, "今日は");
    assert_eq!(segments[1].0, "en");
    assert_eq!(segments[1].1, "good morning");
    assert_eq!(segments[2].0, "ja");
    assert_eq!(segments[2].1, "ですね");
}

#[test]
fn test_segment_mixed_zh_en() {
    let detector = make_detector(&["zh", "en"], "en");
    let segments = segment_text("Hello你好", &detector);
    assert_eq!(segments.len(), 2);
    assert_eq!(segments[0].0, "en");
    assert_eq!(segments[0].1, "Hello");
    assert_eq!(segments[1].0, "zh");
    assert_eq!(segments[1].1, "你好");
}

// ===========================================================================
// Segmentation — Neutral character absorption
// ===========================================================================

#[test]
fn test_segment_neutral_absorbed_into_preceding() {
    let detector = make_detector(&["ja", "en"], "en");
    // Comma and space after "Hello" are neutral -> absorbed into English segment
    let segments = segment_text("Hello, こんにちは", &detector);
    assert_eq!(segments.len(), 2);
    assert_eq!(segments[0].0, "en");
    assert_eq!(segments[0].1, "Hello, ");
    assert_eq!(segments[1].0, "ja");
    assert_eq!(segments[1].1, "こんにちは");
}

#[test]
fn test_segment_leading_neutral_absorbed_into_first_language() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("123 Hello", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "en");
    assert_eq!(segments[0].1, "123 Hello");
}

// ===========================================================================
// Segmentation — Edge cases
// ===========================================================================

#[test]
fn test_segment_empty_text() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("", &detector);
    assert!(segments.is_empty());
}

#[test]
fn test_segment_whitespace_only() {
    let detector = make_detector(&["ja", "en"], "en");
    let segments = segment_text("   ", &detector);
    assert!(segments.is_empty());
}

#[test]
fn test_segment_digits_only_fallback() {
    let detector = make_detector(&["ja", "en"], "en");
    // No language-specific characters -> falls back to default_latin_language
    let segments = segment_text("12345", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "en");
    assert_eq!(segments[0].1, "12345");
}

// ===========================================================================
// Segmentation — CJK disambiguation in context
// ===========================================================================

#[test]
fn test_segment_cjk_with_kana_context_becomes_japanese() {
    let detector = make_detector(&["ja", "en", "zh"], "en");
    // Text has kana -> CJK ideographs classified as Japanese
    let segments = segment_text("漢字とかな", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "ja");
}

#[test]
fn test_segment_cjk_without_kana_becomes_chinese() {
    let detector = make_detector(&["ja", "en", "zh"], "en");
    // Pure CJK ideographs without kana -> Chinese
    let segments = segment_text("你好世界", &detector);
    assert_eq!(segments.len(), 1);
    assert_eq!(segments[0].0, "zh");
}

// ===========================================================================
// Post-process IDs — BOS/EOS/padding
// ===========================================================================

fn make_id_map() -> HashMap<String, Vec<i64>> {
    let mut map = HashMap::new();
    map.insert("_".to_string(), vec![0]);
    map.insert("^".to_string(), vec![1]);
    map.insert("$".to_string(), vec![2]);
    map.insert("?".to_string(), vec![3]);
    map
}

#[test]
fn test_post_process_adds_bos_eos_padding() {
    let id_map = make_id_map();
    let ids = vec![10i64, 11];
    let prosody = vec![None, None];
    let (result_ids, result_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");

    // Expected: BOS(1) + pad(0) + 10 + pad(0) + 11 + pad(0) + EOS(2)
    assert_eq!(result_ids, vec![1, 0, 10, 0, 11, 0, 2]);
    assert_eq!(result_ids[0], 1); // BOS
    assert_eq!(result_ids[1], 0); // pad after BOS
    assert_eq!(*result_ids.last().unwrap(), 2); // EOS
    assert_eq!(result_ids.len(), result_prosody.len());
}

#[test]
fn test_post_process_three_phonemes() {
    let id_map = make_id_map();
    let ids = vec![10i64, 11, 12];
    let prosody = vec![None, None, None];
    let (result_ids, result_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");

    // Expected: ^(1) + pad(0) + 10 + pad(0) + 11 + pad(0) + 12 + pad(0) + $(2)
    assert_eq!(result_ids, vec![1, 0, 10, 0, 11, 0, 12, 0, 2]);
    assert_eq!(result_prosody.len(), result_ids.len());
}

#[test]
fn test_post_process_skip_pad_after_pad_token() {
    let id_map = make_id_map();
    // ID 0 is a pad token -- should NOT get another pad after it
    let ids = vec![10i64, 0, 12];
    let prosody = vec![None, None, None];
    let (result_ids, _) = default_post_process_ids(ids, prosody, &id_map, "$");

    // Expected: ^(1) + pad(0) + 10 + pad(0) + 0(no extra pad) + 12 + pad(0) + $(2)
    assert_eq!(result_ids, vec![1, 0, 10, 0, 0, 12, 0, 2]);
}

#[test]
fn test_post_process_question_eos() {
    let id_map = make_id_map();
    let ids = vec![10i64];
    let prosody = vec![None];
    let (result_ids, _) = default_post_process_ids(ids, prosody, &id_map, "?");

    // Expected: ^(1) + pad(0) + 10 + pad(0) + ?(3)
    assert_eq!(result_ids, vec![1, 0, 10, 0, 3]);
}

#[test]
fn test_post_process_eos_fallback_to_dollar() {
    let id_map = make_id_map();
    let ids = vec![10i64];
    let prosody = vec![None];
    // Request nonexistent EOS token -> falls back to "$"
    let (result_ids, _) = default_post_process_ids(ids, prosody, &id_map, "nonexistent");

    // Expected: ^(1) + pad(0) + 10 + pad(0) + $(2)
    assert_eq!(result_ids, vec![1, 0, 10, 0, 2]);
}

#[test]
fn test_post_process_empty_input() {
    let id_map = make_id_map();
    let ids: Vec<i64> = vec![];
    let prosody = vec![];
    let (result_ids, result_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");

    // Expected: ^(1) + pad(0) + $(2)
    assert_eq!(result_ids, vec![1, 0, 2]);
    assert_eq!(result_prosody.len(), result_ids.len());
}

#[test]
fn test_post_process_prosody_propagated() {
    let id_map = make_id_map();
    let ids = vec![10i64, 11];
    let prosody = vec![Some([1, 2, 3]), None];
    let (result_ids, result_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");

    // ^=None, pad=None, 10=Some([1,2,3]), pad=None, 11=None, pad=None, $=None
    assert_eq!(result_ids, vec![1, 0, 10, 0, 11, 0, 2]);
    assert!(result_prosody[0].is_none()); // ^
    assert!(result_prosody[1].is_none()); // pad
    assert_eq!(result_prosody[2], Some([1, 2, 3])); // phoneme 10
    assert!(result_prosody[3].is_none()); // pad
    assert!(result_prosody[4].is_none()); // phoneme 11
    assert!(result_prosody[5].is_none()); // pad
    assert!(result_prosody[6].is_none()); // $
}

#[test]
fn test_post_process_ids_and_prosody_lengths_always_match() {
    let id_map = make_id_map();
    let ids = vec![5i64, 6, 7, 8, 9];
    let prosody = vec![Some([1, 0, 3]), None, Some([0, 2, 4]), None, None];
    let (out_ids, out_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");
    assert_eq!(
        out_ids.len(),
        out_prosody.len(),
        "IDs ({}) and prosody ({}) length mismatch",
        out_ids.len(),
        out_prosody.len()
    );
}

#[test]
fn test_post_process_no_bos_eos_in_map() {
    // If the id_map has no "^" or "$", post-processing still works
    // (just no BOS/EOS wrapping)
    let mut id_map: HashMap<String, Vec<i64>> = HashMap::new();
    id_map.insert("_".to_string(), vec![0]);

    let ids = vec![10i64, 11];
    let prosody = vec![None, None];
    let (result_ids, result_prosody) = default_post_process_ids(ids, prosody, &id_map, "$");

    // No BOS/EOS, just intersperse padding: 10 + pad(0) + 11 + pad(0)
    assert_eq!(result_ids, vec![10, 0, 11, 0]);
    assert_eq!(result_prosody.len(), result_ids.len());
}

// ===========================================================================
// Segmentation — Six-language scenario
// ===========================================================================

#[test]
fn test_segment_six_language_detector() {
    // Verify the detector works with all 6 project languages
    let detector = make_detector(&["ja", "en", "zh", "es", "fr", "pt"], "en");

    // Japanese kana
    assert_eq!(detector.detect_char('\u{3042}', false), Some("ja"));
    // Chinese ideograph (no kana context)
    assert_eq!(detector.detect_char('\u{4F60}', false), Some("zh")); // 你
    // Latin -> default (en)
    assert_eq!(detector.detect_char('A', false), Some("en"));
    // Neutral
    assert_eq!(detector.detect_char('5', false), None);
}

#[test]
fn test_segment_six_language_mixed_text() {
    let detector = make_detector(&["ja", "en", "zh", "ko", "es", "fr"], "en");
    // Text mixing Japanese and English
    let segments = segment_text("テストtest", &detector);
    assert_eq!(segments.len(), 2);
    assert_eq!(segments[0].0, "ja");
    assert_eq!(segments[1].0, "en");
}
