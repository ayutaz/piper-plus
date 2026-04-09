//! SSML (Speech Synthesis Markup Language) basic tag parser.
//!
//! Supports a subset of the SSML W3C spec:
//! - `<speak>` root element
//! - `<break time="500ms"/>` or `<break time="1s"/>` for silence
//! - `<break strength="medium"/>` for predefined silence durations
//! - `<prosody rate="slow">text</prosody>` for speech rate control
//!
//! Unknown tags are gracefully degraded by extracting their text content.
//! XML syntax errors cause a fallback to plain-text processing.

use quick_xml::events::Event;
use quick_xml::reader::Reader;
use regex::Regex;
use std::sync::LazyLock;

/// A segment produced by SSML parsing.
#[derive(Debug, Clone, PartialEq)]
pub struct SsmlSegment {
    /// Text to phonemize. Empty string indicates a silence-only segment.
    pub text: String,
    /// Silence duration in milliseconds to insert after this segment.
    pub break_ms: u32,
    /// Speech rate multiplier. Maps to `length_scale` at synthesis time.
    /// Values > 1.0 mean slower speech; values < 1.0 mean faster speech.
    pub rate: f32,
}

impl Default for SsmlSegment {
    fn default() -> Self {
        Self {
            text: String::new(),
            break_ms: 0,
            rate: 1.0,
        }
    }
}

/// Predefined break strength durations in milliseconds, per W3C SSML spec.
fn break_strength_ms(strength: &str) -> u32 {
    match strength.to_ascii_lowercase().as_str() {
        "none" => 0,
        "x-weak" => 100,
        "weak" => 200,
        "medium" => 400,
        "strong" => 700,
        "x-strong" => 1000,
        _ => 400, // default to medium for unknown strengths
    }
}

/// Named rate values. The returned value is the length_scale multiplier:
/// > 1.0 is slower, < 1.0 is faster.
fn rate_by_name(name: &str) -> Option<f32> {
    match name {
        "x-slow" => Some(1.5),
        "slow" => Some(1.25),
        "medium" => Some(1.0),
        "fast" => Some(0.8),
        "x-fast" => Some(0.6),
        _ => None,
    }
}

/// Regex for detecting SSML: starts with optional whitespace then `<speak`.
static RE_SSML: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?s)^\s*<speak[\s>]").expect("valid regex"));

/// Regex for stripping all XML tags (used in fallback).
static RE_STRIP_TAGS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"<[^>]*>").expect("valid regex"));

/// Parser for a basic subset of SSML tags.
///
/// All methods are associated functions (no mutable state).
pub struct SsmlParser;

impl SsmlParser {
    /// Return `true` if `text` looks like an SSML document.
    ///
    /// Detection is based on the presence of a `<speak` opening tag
    /// near the start of the string.
    pub fn is_ssml(text: &str) -> bool {
        RE_SSML.is_match(text)
    }

    /// Parse an SSML string into a list of [`SsmlSegment`].
    ///
    /// If `ssml_text` is not valid XML the entire string is returned as
    /// a single plain-text segment (graceful fallback).
    pub fn parse(ssml_text: &str) -> Vec<SsmlSegment> {
        if !Self::is_ssml(ssml_text) {
            return vec![SsmlSegment {
                text: ssml_text.to_string(),
                ..Default::default()
            }];
        }

        match Self::parse_xml(ssml_text) {
            Ok(segments) => {
                let merged = Self::merge(segments);
                if merged.is_empty() {
                    vec![SsmlSegment {
                        text: String::new(),
                        ..Default::default()
                    }]
                } else {
                    merged
                }
            }
            Err(_) => {
                // XML parse error -- strip tags and return as plain text
                tracing::warn!(
                    "SSML parse error; falling back to plain text: {}",
                    &ssml_text[..ssml_text.len().min(120)]
                );
                let stripped = RE_STRIP_TAGS.replace_all(ssml_text, "").trim().to_string();
                vec![SsmlSegment {
                    text: if stripped.is_empty() {
                        ssml_text.to_string()
                    } else {
                        stripped
                    },
                    ..Default::default()
                }]
            }
        }
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    /// Parse the XML and walk the tree structure using a stack-based approach.
    ///
    /// This replicates the Python `_walk()` recursive traversal using
    /// `quick-xml`'s streaming reader with a rate-scope stack.
    fn parse_xml(ssml_text: &str) -> Result<Vec<SsmlSegment>, quick_xml::Error> {
        let mut reader = Reader::from_str(ssml_text);
        reader.config_mut().trim_text_start = false;
        reader.config_mut().trim_text_end = false;

        let mut segments: Vec<SsmlSegment> = Vec::new();
        // Stack tracks (tag_name, rate) for each open element.
        let mut rate_stack: Vec<(String, f32)> = Vec::new();

        fn current_rate(stack: &[(String, f32)]) -> f32 {
            stack.last().map(|(_, r)| *r).unwrap_or(1.0)
        }

        loop {
            match reader.read_event() {
                Ok(Event::Start(ref e)) => {
                    let tag = local_tag(e.name().as_ref());
                    let parent_rate = current_rate(&rate_stack);

                    if tag == "prosody" {
                        let rate_attr = Self::get_attr(e, "rate");
                        let new_rate = rate_attr
                            .as_deref()
                            .map(Self::parse_rate)
                            .unwrap_or(parent_rate);
                        rate_stack.push((tag, new_rate));
                    } else {
                        rate_stack.push((tag, parent_rate));
                    }
                }
                Ok(Event::End(_)) => {
                    rate_stack.pop();
                }
                Ok(Event::Empty(ref e)) => {
                    let tag = local_tag(e.name().as_ref());
                    if tag == "break" {
                        let break_ms = Self::resolve_break_from_event(e);
                        segments.push(SsmlSegment {
                            text: String::new(),
                            break_ms,
                            rate: current_rate(&rate_stack),
                        });
                    }
                    // Other self-closing tags are ignored (no text content).
                }
                Ok(Event::Text(ref e)) => {
                    let text = e.unescape().unwrap_or_default().trim().to_string();
                    if !text.is_empty() {
                        segments.push(SsmlSegment {
                            text,
                            break_ms: 0,
                            rate: current_rate(&rate_stack),
                        });
                    }
                }
                Ok(Event::Eof) => break,
                Ok(_) => {} // CData, Comment, PI, Decl -- skip
                Err(e) => return Err(e),
            }
        }
        Ok(segments)
    }

    /// Extract an attribute value from a quick-xml event.
    fn get_attr(event: &quick_xml::events::BytesStart<'_>, name: &str) -> Option<String> {
        for attr in event.attributes().flatten() {
            if attr.key.as_ref() == name.as_bytes() {
                return String::from_utf8(attr.value.to_vec()).ok();
            }
        }
        None
    }

    /// Resolve break duration from a `<break>` element's attributes.
    fn resolve_break_from_event(event: &quick_xml::events::BytesStart<'_>) -> u32 {
        if let Some(time_val) = Self::get_attr(event, "time") {
            return Self::parse_break_time(&time_val);
        }
        if let Some(strength_val) = Self::get_attr(event, "strength") {
            return break_strength_ms(&strength_val);
        }
        // Default break with no attributes -> medium
        break_strength_ms("medium")
    }

    /// Convert `"500ms"` or `"1s"` to milliseconds. Returns 0 for unparseable values.
    fn parse_break_time(time_str: &str) -> u32 {
        let s = time_str.trim().to_ascii_lowercase();
        if let Some(ms_part) = s.strip_suffix("ms") {
            return ms_part
                .parse::<f64>()
                .map(|v| v as u32)
                .unwrap_or_else(|_| {
                    tracing::warn!("Invalid break time: {}", time_str);
                    0
                });
        }
        if let Some(s_part) = s.strip_suffix('s') {
            return s_part
                .parse::<f64>()
                .map(|v| (v * 1000.0) as u32)
                .unwrap_or_else(|_| {
                    tracing::warn!("Invalid break time: {}", time_str);
                    0
                });
        }
        // Bare number -- assume milliseconds
        s.parse::<f64>().map(|v| v as u32).unwrap_or_else(|_| {
            tracing::warn!("Invalid break time: {}", time_str);
            0
        })
    }

    /// Parse a rate specification into a float multiplier.
    ///
    /// Accepted formats:
    /// - Named: `"slow"`, `"fast"`, etc.
    /// - Percentage: `"120%"` (120% speaking rate -> length_scale = 100/120 = 0.833)
    /// - Bare float: treated as direct length_scale multiplier.
    fn parse_rate(rate_str: &str) -> f32 {
        let s = rate_str.trim().to_ascii_lowercase();

        // Named rate
        if let Some(rate) = rate_by_name(&s) {
            return rate;
        }

        // Percentage
        if let Some(pct_part) = s.strip_suffix('%') {
            if let Ok(pct) = pct_part.parse::<f64>() {
                if pct <= 0.0 {
                    tracing::warn!("Invalid rate percentage: {}", rate_str);
                    return 1.0;
                }
                return (100.0 / pct) as f32;
            }
            tracing::warn!("Invalid rate percentage: {}", rate_str);
            return 1.0;
        }

        // Bare float
        if let Ok(val) = s.parse::<f64>() {
            if val <= 0.0 {
                tracing::warn!("Invalid rate value: {}", rate_str);
                return 1.0;
            }
            return val as f32;
        }

        tracing::warn!("Unrecognized rate: {}", rate_str);
        1.0
    }

    /// Remove empty-text segments with zero break (no-ops).
    fn merge(segments: Vec<SsmlSegment>) -> Vec<SsmlSegment> {
        segments
            .into_iter()
            .filter(|s| !s.text.trim().is_empty() || s.break_ms > 0)
            .collect()
    }
}

/// Strip XML namespace prefix if present.
/// e.g., `{http://www.w3.org/2001/10/synthesis}speak` -> `speak`
fn local_tag(raw: &[u8]) -> String {
    let s = String::from_utf8_lossy(raw);
    if let Some(pos) = s.find('}') {
        s[pos + 1..].to_string()
    } else {
        s.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- is_ssml detection ----

    #[test]
    fn test_is_ssml_with_speak_tag() {
        assert!(SsmlParser::is_ssml("<speak>Hello</speak>"));
    }

    #[test]
    fn test_is_ssml_with_leading_whitespace() {
        assert!(SsmlParser::is_ssml("  \n <speak>Hello</speak>"));
    }

    #[test]
    fn test_is_ssml_with_attributes() {
        assert!(SsmlParser::is_ssml(
            r#"<speak version="1.0" xml:lang="ja-JP">Hello</speak>"#
        ));
    }

    #[test]
    fn test_is_ssml_plain_text() {
        assert!(!SsmlParser::is_ssml("Hello, world!"));
    }

    #[test]
    fn test_is_ssml_xml_but_not_speak() {
        assert!(!SsmlParser::is_ssml("<root>Hello</root>"));
    }

    #[test]
    fn test_is_ssml_empty() {
        assert!(!SsmlParser::is_ssml(""));
    }

    // ---- Plain text fallback ----

    #[test]
    fn test_parse_plain_text() {
        let segments = SsmlParser::parse("Hello, world!");
        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].text, "Hello, world!");
        assert_eq!(segments[0].break_ms, 0);
        assert!((segments[0].rate - 1.0).abs() < f32::EPSILON);
    }

    // ---- Break with time attribute ----

    #[test]
    fn test_break_time_ms() {
        let ssml = r#"<speak>Hello<break time="500ms"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 3);
        assert_eq!(segments[0].text, "Hello");
        assert_eq!(segments[1].text, "");
        assert_eq!(segments[1].break_ms, 500);
        assert_eq!(segments[2].text, "world");
    }

    #[test]
    fn test_break_time_seconds() {
        let ssml = r#"<speak>Hello<break time="1.5s"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let brk = segments.iter().find(|s| s.break_ms > 0).unwrap();
        assert_eq!(brk.break_ms, 1500);
    }

    #[test]
    fn test_break_time_bare_number() {
        let ssml = r#"<speak>Hello<break time="750"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let brk = segments.iter().find(|s| s.break_ms > 0).unwrap();
        assert_eq!(brk.break_ms, 750);
    }

    #[test]
    fn test_break_time_invalid() {
        let ssml = r#"<speak>Hello<break time="abc"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        // Invalid time parses to 0ms, which is filtered out by merge.
        // Only text segments remain.
        assert_eq!(segments.len(), 2);
        assert_eq!(segments[0].text, "Hello");
        assert_eq!(segments[1].text, "world");
    }

    // ---- Break with strength attribute ----

    #[test]
    fn test_break_strength_none() {
        let ssml = r#"<speak>Hello<break strength="none"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        // "none" = 0ms, so the break segment is filtered out by merge
        assert_eq!(segments.len(), 2);
        assert_eq!(segments[0].text, "Hello");
        assert_eq!(segments[1].text, "world");
    }

    #[test]
    fn test_break_strength_medium() {
        let ssml = r#"<speak>Hello<break strength="medium"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let brk = segments.iter().find(|s| s.break_ms > 0).unwrap();
        assert_eq!(brk.break_ms, 400);
    }

    #[test]
    fn test_break_strength_x_strong() {
        let ssml = r#"<speak>Hello<break strength="x-strong"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let brk = segments.iter().find(|s| s.break_ms > 0).unwrap();
        assert_eq!(brk.break_ms, 1000);
    }

    #[test]
    fn test_break_no_attributes_defaults_to_medium() {
        let ssml = r#"<speak>Hello<break/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let brk = segments.iter().find(|s| s.break_ms > 0).unwrap();
        assert_eq!(brk.break_ms, 400);
    }

    // ---- Prosody rate (named) ----

    #[test]
    fn test_prosody_rate_slow() {
        let ssml = r#"<speak><prosody rate="slow">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert!((segments[0].rate - 1.25).abs() < 0.01);
    }

    #[test]
    fn test_prosody_rate_fast() {
        let ssml = r#"<speak><prosody rate="fast">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert!((segments[0].rate - 0.8).abs() < 0.01);
    }

    #[test]
    fn test_prosody_rate_x_slow() {
        let ssml = r#"<speak><prosody rate="x-slow">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert!((segments[0].rate - 1.5).abs() < 0.01);
    }

    #[test]
    fn test_prosody_rate_x_fast() {
        let ssml = r#"<speak><prosody rate="x-fast">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert!((segments[0].rate - 0.6).abs() < 0.01);
    }

    // ---- Prosody rate (percentage) ----

    #[test]
    fn test_prosody_rate_percentage_120() {
        let ssml = r#"<speak><prosody rate="120%">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        // 100/120 = 0.8333...
        assert!((segments[0].rate - (100.0_f32 / 120.0)).abs() < 0.01);
    }

    #[test]
    fn test_prosody_rate_percentage_50() {
        let ssml = r#"<speak><prosody rate="50%">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        // 100/50 = 2.0
        assert!((segments[0].rate - 2.0).abs() < 0.01);
    }

    #[test]
    fn test_prosody_rate_percentage_zero_fallback() {
        let ssml = r#"<speak><prosody rate="0%">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert!((segments[0].rate - 1.0).abs() < f32::EPSILON);
    }

    // ---- Prosody rate (bare float) ----

    #[test]
    fn test_prosody_rate_bare_float() {
        let ssml = r#"<speak><prosody rate="1.3">Hello</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert!((segments[0].rate - 1.3).abs() < 0.01);
    }

    // ---- Nested elements ----

    #[test]
    fn test_nested_prosody_and_break() {
        let ssml =
            r#"<speak><prosody rate="slow">Hello<break time="300ms"/>world</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 3);
        assert_eq!(segments[0].text, "Hello");
        assert!((segments[0].rate - 1.25).abs() < 0.01);
        assert_eq!(segments[1].break_ms, 300);
        assert_eq!(segments[2].text, "world");
        assert!((segments[2].rate - 1.25).abs() < 0.01);
    }

    #[test]
    fn test_multiple_segments_mixed() {
        let ssml = r#"<speak>Start<break time="200ms"/><prosody rate="fast">fast text</prosody> end</speak>"#;
        let segments = SsmlParser::parse(ssml);
        // "Start", break(200), "fast text" (rate=0.8), "end"
        assert!(segments.len() >= 3);
        let start = &segments[0];
        assert_eq!(start.text, "Start");
        assert!((start.rate - 1.0).abs() < f32::EPSILON);

        let brk = segments.iter().find(|s| s.break_ms == 200).unwrap();
        assert_eq!(brk.break_ms, 200);

        let fast = segments.iter().find(|s| s.text == "fast text").unwrap();
        assert!((fast.rate - 0.8).abs() < 0.01);
    }

    // ---- Unknown tags ----

    #[test]
    fn test_unknown_tag_extracts_text() {
        let ssml = r#"<speak><emphasis>important</emphasis></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].text, "important");
    }

    // ---- XML error fallback ----

    #[test]
    fn test_xml_error_fallback_mismatched_tags() {
        // Mismatched closing tag triggers a parse error
        let bad_ssml = r#"<speak>Hello</wrong>"#;
        let segments = SsmlParser::parse(bad_ssml);
        // Should fallback to stripped plain text
        assert_eq!(segments.len(), 1);
        assert!(!segments[0].text.is_empty());
        // Tags should be stripped
        assert!(!segments[0].text.contains('<'));
    }

    #[test]
    fn test_xml_error_fallback_unclosed() {
        // Unclosed <break> (not self-closing) may still parse in quick-xml,
        // so test with something that produces a plain-text fallback.
        let bad_ssml = r#"<speak>Hello <break time="500ms"> world"#;
        let segments = SsmlParser::parse(bad_ssml);
        // Either parsed leniently or fell back -- text should be present
        assert!(!segments.is_empty());
        let has_text = segments
            .iter()
            .any(|s| s.text.contains("Hello") || s.text.contains("world"));
        assert!(has_text);
    }

    // ---- Japanese text ----

    #[test]
    fn test_japanese_text() {
        let ssml = r#"<speak>こんにちは<break time="500ms"/>世界</speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 3);
        assert_eq!(segments[0].text, "こんにちは");
        assert_eq!(segments[1].break_ms, 500);
        assert_eq!(segments[2].text, "世界");
    }

    #[test]
    fn test_japanese_with_prosody() {
        let ssml = r#"<speak><prosody rate="slow">ゆっくり話します</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert_eq!(segments[0].text, "ゆっくり話します");
        assert!((segments[0].rate - 1.25).abs() < 0.01);
    }

    // ---- Edge cases ----

    #[test]
    fn test_empty_speak() {
        let ssml = "<speak></speak>";
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert!(segments[0].text.is_empty());
    }

    #[test]
    fn test_speak_only_whitespace() {
        let ssml = "<speak>   \n  </speak>";
        let segments = SsmlParser::parse(ssml);
        // Whitespace-only text is trimmed, producing empty segment
        assert_eq!(segments.len(), 1);
        assert!(segments[0].text.is_empty());
    }

    #[test]
    fn test_all_break_strengths() {
        let strengths = [
            ("none", 0),
            ("x-weak", 100),
            ("weak", 200),
            ("medium", 400),
            ("strong", 700),
            ("x-strong", 1000),
        ];
        for (name, expected_ms) in &strengths {
            let ssml = format!(r#"<speak>a<break strength="{}"/>b</speak>"#, name);
            let segments = SsmlParser::parse(&ssml);
            if *expected_ms == 0 {
                // "none" break is filtered out by merge
                assert_eq!(segments.len(), 2, "strength={}", name);
            } else {
                let brk = segments
                    .iter()
                    .find(|s| s.break_ms > 0)
                    .unwrap_or_else(|| panic!("no break for strength={}", name));
                assert_eq!(brk.break_ms, *expected_ms, "strength={}", name);
            }
        }
    }

    #[test]
    fn test_all_named_rates() {
        let rates = [
            ("x-slow", 1.5_f32),
            ("slow", 1.25),
            ("medium", 1.0),
            ("fast", 0.8),
            ("x-fast", 0.6),
        ];
        for (name, expected) in &rates {
            let ssml = format!(r#"<speak><prosody rate="{}">text</prosody></speak>"#, name);
            let segments = SsmlParser::parse(&ssml);
            assert!(
                (segments[0].rate - expected).abs() < 0.01,
                "rate={}: expected={}, got={}",
                name,
                expected,
                segments[0].rate,
            );
        }
    }

    #[test]
    fn test_multiple_breaks_in_sequence() {
        let ssml = r#"<speak>Hello<break time="200ms"/><break time="300ms"/>world</speak>"#;
        let segments = SsmlParser::parse(ssml);
        let breaks: Vec<_> = segments.iter().filter(|s| s.break_ms > 0).collect();
        assert_eq!(breaks.len(), 2);
        assert_eq!(breaks[0].break_ms, 200);
        assert_eq!(breaks[1].break_ms, 300);
    }

    #[test]
    fn test_prosody_rate_unrecognized_name() {
        let ssml = r#"<speak><prosody rate="unknown_name">text</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        // unrecognized name is not a float nor percentage -> falls back to 1.0
        assert!((segments[0].rate - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_prosody_without_rate_attribute() {
        let ssml = r#"<speak><prosody volume="loud">text</prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        assert!((segments[0].rate - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_nested_prosody_rate_override() {
        let ssml =
            r#"<speak><prosody rate="slow"><prosody rate="fast">inner</prosody></prosody></speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert_eq!(segments.len(), 1);
        // Inner prosody overrides outer
        assert!((segments[0].rate - 0.8).abs() < 0.01);
    }

    #[test]
    fn test_text_outside_and_inside_prosody() {
        let ssml = r#"<speak>before <prosody rate="fast">inside</prosody> after</speak>"#;
        let segments = SsmlParser::parse(ssml);
        assert!(segments.len() >= 3);
        let before = segments.iter().find(|s| s.text == "before").unwrap();
        assert!((before.rate - 1.0).abs() < f32::EPSILON);
        let inside = segments.iter().find(|s| s.text == "inside").unwrap();
        assert!((inside.rate - 0.8).abs() < 0.01);
        let after = segments.iter().find(|s| s.text == "after").unwrap();
        assert!((after.rate - 1.0).abs() < f32::EPSILON);
    }
}
