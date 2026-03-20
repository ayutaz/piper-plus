//! Integration tests for Japanese question marker detection (Issue #204).
//!
//! Tests `piper_plus::phonemize::japanese::get_question_type` which determines
//! the appropriate end-of-sentence marker based on trailing punctuation.
//!
//! Marker reference:
//! - "?!" : Emphatic question (強調疑問)
//! - "?." : Neutral/rhetorical question (平叙疑問)
//! - "?~" : Tag/confirmation question (確認疑問)
//! - "?"  : Generic question
//! - "$"  : Declarative (non-question)

#[cfg(feature = "japanese")]
use piper_plus::phonemize::japanese::get_question_type;

// ---------------------------------------------------------------------------
// Standard question mark
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_question_standard_fullwidth() {
    // Full-width ？ (U+FF1F) → generic question
    assert_eq!(get_question_type("こんにちは？"), "?");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_standard_ascii() {
    // ASCII ? → generic question
    assert_eq!(get_question_type("こんにちは?"), "?");
}

// ---------------------------------------------------------------------------
// Emphatic question (?!)
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_question_emphatic_fullwidth() {
    // ？！ (U+FF1F U+FF01) → emphatic
    assert_eq!(get_question_type("本当？！"), "?!");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_emphatic_reversed() {
    // ！？ (U+FF01 U+FF1F) → emphatic (order-insensitive)
    assert_eq!(get_question_type("本当！？"), "?!");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_emphatic_ascii() {
    // ASCII ?! → emphatic
    assert_eq!(get_question_type("本当?!"), "?!");
}

// ---------------------------------------------------------------------------
// Neutral / rhetorical question (?.)
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_question_neutral_fullwidth() {
    // ？。 (U+FF1F U+3002) → neutral
    assert_eq!(get_question_type("そうなの？。"), "?.");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_neutral_reversed() {
    // 。？ (U+3002 U+FF1F) → neutral (order-insensitive)
    assert_eq!(get_question_type("そうなの。？"), "?.");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_neutral_ascii() {
    // ASCII ?. → neutral
    assert_eq!(get_question_type("そうなの?."), "?.");
}

// ---------------------------------------------------------------------------
// Tag / confirmation question (?~)
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_question_tag_fullwidth() {
    // ？～ (U+FF1F U+FF5E) → tag
    assert_eq!(get_question_type("行くよね？～"), "?~");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_tag_reversed() {
    // ～？ (U+FF5E U+FF1F) → tag (order-insensitive)
    assert_eq!(get_question_type("行くよね～？"), "?~");
}

#[test]
#[cfg(feature = "japanese")]
fn test_question_tag_ascii() {
    // ASCII ?~ → tag
    assert_eq!(get_question_type("行くよね?~"), "?~");
}

// ---------------------------------------------------------------------------
// Non-question (declarative → "$")
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_nonquestion_period() {
    // Sentence ending with 。 → declarative
    assert_eq!(get_question_type("こんにちは。"), "$");
}

#[test]
#[cfg(feature = "japanese")]
fn test_nonquestion_plain() {
    // Plain text without any punctuation → declarative
    assert_eq!(get_question_type("こんにちは"), "$");
}

// ---------------------------------------------------------------------------
// Whitespace handling
// ---------------------------------------------------------------------------

#[test]
#[cfg(feature = "japanese")]
fn test_question_trailing_whitespace() {
    // Trailing whitespace should be trimmed before detection
    assert_eq!(get_question_type("こんにちは？  "), "?");
}
