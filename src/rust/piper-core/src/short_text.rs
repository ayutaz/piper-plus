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
///
/// これは **SSML パーサを持つパイプライン向け**である。合成経路は
/// [`pad_silence_for_short_text`] を使うこと — この文字列をそのまま
/// phonemizer に渡すとマークアップが読み上げられる (issue #694)。
/// に変換して返す。
///
/// そうでなければ元のテキストをそのまま返す。
/// 短テキストかどうか (Strategy C の発動条件)
///
/// 空白を除いた文字数が [`SHORT_TEXT_CHARS`] 以下で、かつ呼び出し側が自前の
/// SSML を渡していない場合に true。
pub fn is_short_text(text: &str) -> bool {
    let trimmed = text.trim();
    if trimmed.starts_with("<speak>") || trimmed.starts_with("<speak ") {
        return false;
    }
    trimmed.chars().filter(|c| !c.is_whitespace()).count() <= SHORT_TEXT_CHARS
}

/// 合成済み音声の前後に [`SILENCE_PAD_MS`] の無音を挿入する (Strategy C)
///
/// `docs/spec/short-text-contract.toml` `[ssml_injection]` は
/// `silence_pad_ms` を「短テキスト**音声**の前後に付与する無音」と規定して
/// いる。[`wrap_short_text_ssml`] はその同じ意図を SSML テキストとして
/// 表現したもので、**SSML パーサを持つパイプライン向け**である。
///
/// 合成経路がこちらではなくテキスト版を使い、その文字列を SSML として
/// パースせずに phonemizer へ渡していたため、`<speak>` `<break` `time=`
/// が英語として読み上げられていた (issue #694)。`--timing json` の音素列に
/// `s p ˈ i ː k` (= speak) `b ɹ ˈ e ɪ k` (= break) `t ˈ a ɪ m` (= time) が
/// 現れることで発覚した。
pub fn pad_silence_for_short_text(audio: &[i16], sample_rate: u32) -> Vec<i16> {
    if audio.is_empty() {
        return audio.to_vec();
    }
    let silence_samples = ((u64::from(sample_rate) * u64::from(SILENCE_PAD_MS)) / 1000) as usize;
    let mut padded = Vec::with_capacity(silence_samples * 2 + audio.len());
    padded.resize(silence_samples, 0);
    padded.extend_from_slice(audio);
    padded.resize(padded.len() + silence_samples, 0);
    padded
}

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

    #[test]
    fn pads_short_text_audio_with_silence_on_both_sides() {
        let audio = vec![100i16, 200, 300];
        let padded = pad_silence_for_short_text(&audio, 22050);

        // 300 ms at 22050 Hz = 6615 samples on each side.
        let pad = 6615usize;
        assert_eq!(padded.len(), pad * 2 + audio.len());
        assert!(padded[..pad].iter().all(|&s| s == 0));
        assert_eq!(&padded[pad..pad + audio.len()], audio.as_slice());
        assert!(padded[pad + audio.len()..].iter().all(|&s| s == 0));
    }

    #[test]
    fn padding_leaves_empty_audio_alone() {
        assert!(pad_silence_for_short_text(&[], 22050).is_empty());
    }

    #[test]
    fn short_text_detection_matches_the_wrapper_condition() {
        // The two must agree, otherwise the audio gets padded for inputs the
        // contract does not consider short (or vice versa).
        for text in ["Sol", "Hola", "a b c", "  hi  "] {
            assert!(is_short_text(text), "{text:?} should be short");
            assert!(wrap_short_text_ssml(text).starts_with("<speak>"));
        }
        for text in [
            "Hola, esta es una prueba.",
            "<speak>already ssml</speak>",
            "<speak version=\"1.0\">x</speak>",
        ] {
            assert!(!is_short_text(text), "{text:?} should not be short");
        }
    }
}
