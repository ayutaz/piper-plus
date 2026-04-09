//! 短テキスト緩和策 Strategy C: SSML `<break>` 自動挿入
//!
//! テキストが短い場合 (空白除く文字数 <= SHORT_TEXT_CHARS) に、
//! `<speak><break time="300ms"/>{text}<break time="300ms"/></speak>` で
//! ラップして SSML として処理させることで、モデルに十分なコンテキストを与える。
//!
//! テキストが既に `<speak>` で始まっている場合は何もしない。

/// 短テキストの閾値 (空白除く文字数)。
/// これ以下の場合に `<break>` を自動挿入する。
pub const SHORT_TEXT_CHARS: usize = 10;

/// 自動挿入する `<break>` の時間 (ミリ秒)。
const SILENCE_PAD_MS: u32 = 300;

/// 短テキストを SSML `<break>` でラップする。
///
/// 条件:
/// 1. テキストが `<speak>` で始まっていない (既に SSML ではない)
/// 2. 空白を除いた文字数が `SHORT_TEXT_CHARS` 以下
///
/// 両方を満たす場合、テキストを
/// `<speak><break time="{SILENCE_PAD_MS}ms"/>{text}<break time="{SILENCE_PAD_MS}ms"/></speak>`
/// に変換して返す。
///
/// そうでなければ元のテキストをそのまま返す。
pub fn wrap_short_text_ssml(text: &str) -> String {
    let trimmed = text.trim();

    // 既に SSML の場合はそのまま返す
    if trimmed.starts_with("<speak>") || trimmed.starts_with("<speak ") {
        return text.to_string();
    }

    // 空白を除いた文字数をカウント
    let char_count = trimmed.chars().filter(|c| !c.is_whitespace()).count();

    if char_count <= SHORT_TEXT_CHARS {
        let escaped = trimmed
            .replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;");
        format!(
            "<speak><break time=\"{}ms\"/>{}<break time=\"{}ms\"/></speak>",
            SILENCE_PAD_MS, escaped, SILENCE_PAD_MS
        )
    } else {
        text.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_short_text_gets_wrapped() {
        let result = wrap_short_text_ssml("hello");
        assert!(result.starts_with("<speak>"));
        assert!(result.ends_with("</speak>"));
        assert!(result.contains("<break time=\"300ms\"/>"));
        assert!(result.contains("hello"));
    }

    #[test]
    fn test_exact_threshold_gets_wrapped() {
        // Exactly SHORT_TEXT_CHARS non-whitespace characters
        let text = "1234567890"; // 10 chars
        let result = wrap_short_text_ssml(text);
        assert!(result.starts_with("<speak>"));
        assert!(result.contains(text));
    }

    #[test]
    fn test_above_threshold_not_wrapped() {
        let text = "12345678901"; // 11 chars
        let result = wrap_short_text_ssml(text);
        assert_eq!(result, text);
    }

    #[test]
    fn test_whitespace_not_counted() {
        // "h e l l o" has 5 non-whitespace chars, <= 10
        let text = "h e l l o";
        let result = wrap_short_text_ssml(text);
        assert!(result.starts_with("<speak>"));
    }

    #[test]
    fn test_existing_ssml_not_wrapped() {
        let text = "<speak>hello</speak>";
        let result = wrap_short_text_ssml(text);
        assert_eq!(result, text);
    }

    #[test]
    fn test_existing_ssml_with_attrs_not_wrapped() {
        let text = "<speak xml:lang=\"ja\">hello</speak>";
        let result = wrap_short_text_ssml(text);
        assert_eq!(result, text);
    }

    #[test]
    fn test_empty_text_gets_wrapped() {
        let result = wrap_short_text_ssml("");
        assert!(result.starts_with("<speak>"));
    }

    #[test]
    fn test_long_text_not_wrapped() {
        let text = "This is a much longer sentence that exceeds the threshold.";
        let result = wrap_short_text_ssml(text);
        assert_eq!(result, text);
    }

    #[test]
    fn test_japanese_short_text() {
        let text = "こんにちは"; // 5 chars
        let result = wrap_short_text_ssml(text);
        assert!(result.starts_with("<speak>"));
        assert!(result.contains("こんにちは"));
    }

    #[test]
    fn test_japanese_long_text() {
        let text = "こんにちは、今日は良い天気ですね。"; // 15 chars > 10
        let result = wrap_short_text_ssml(text);
        assert_eq!(result, text);
    }

    #[test]
    fn test_whitespace_only_gets_wrapped() {
        let text = "   ";
        let result = wrap_short_text_ssml(text);
        assert!(result.starts_with("<speak>"));
    }

    #[test]
    fn test_wrap_preserves_trimmed_content() {
        let text = "  hi  ";
        let result = wrap_short_text_ssml(text);
        assert!(result.contains("hi"));
        // The wrapped version uses trimmed text
        assert!(result.contains("<break time=\"300ms\"/>hi<break time=\"300ms\"/>"));
    }

    #[test]
    fn test_silence_pad_ms_value() {
        assert_eq!(SILENCE_PAD_MS, 300);
    }

    #[test]
    fn test_short_text_chars_value() {
        assert_eq!(SHORT_TEXT_CHARS, 10);
    }

    #[test]
    fn test_xml_special_chars_escaped() {
        let result = wrap_short_text_ssml("A & B");
        assert!(result.contains("A &amp; B"));
        assert!(!result.contains("A & B"));
    }

    #[test]
    fn test_angle_bracket_escaped() {
        let result = wrap_short_text_ssml("1<2");
        assert!(result.contains("1&lt;2"));
    }

    #[test]
    fn test_gt_escaped() {
        let result = wrap_short_text_ssml("2>1");
        assert!(result.contains("2&gt;1"));
    }
}
