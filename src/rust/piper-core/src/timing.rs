//! Phoneme timing extraction from ONNX model duration output.
//!
//! VITS models optionally output a `durations` tensor [1, phoneme_length]
//! containing the number of frames (hop_length-sized) each phoneme occupies.
//! This module converts frame counts to millisecond timestamps.

use serde::Serialize;
use std::collections::HashMap;

use crate::error::PiperError;

/// Default hop length for VITS models
pub const DEFAULT_HOP_LENGTH: usize = 256;

/// Timing information for a single phoneme
#[derive(Debug, Clone, Serialize)]
pub struct PhonemeTimingInfo {
    pub phoneme: String,
    pub start_ms: f64,
    pub end_ms: f64,
    pub duration_ms: f64,
}

/// Complete timing result for a synthesized utterance
#[derive(Debug, Clone, Serialize)]
pub struct TimingResult {
    pub phonemes: Vec<PhonemeTimingInfo>,
    pub total_duration_ms: f64,
    pub sample_rate: u32,
}

impl TimingResult {
    /// Serialize to JSON string (pretty-printed)
    pub fn to_json(&self) -> Result<String, PiperError> {
        serde_json::to_string_pretty(self).map_err(PiperError::from)
    }

    /// Serialize to JSON string (compact, one line per phoneme)
    pub fn to_json_compact(&self) -> Result<String, PiperError> {
        serde_json::to_string(self).map_err(PiperError::from)
    }

    /// Serialize to TSV string (tab-separated: start_ms, end_ms, duration_ms, phoneme).
    ///
    /// spec [output_formats.tsv].escape_tab_in_phoneme = "\\t" / escape_newline_in_phoneme = "\\n"
    /// (docs/spec/phoneme-timing-contract.toml). Phoneme tokens that themselves
    /// contain a tab or newline must be escaped to literal "\t" / "\n" (2-char
    /// sequences) so the TSV column count remains 4. Cross-runtime parity with
    /// Python (timing.py:167), C# (TimingWriter.cs EscapeForTsv), Go (timing.go),
    /// and WASM/JS (timing.js).
    pub fn to_tsv(&self) -> String {
        let mut buf = String::from("start_ms\tend_ms\tduration_ms\tphoneme\n");
        for p in &self.phonemes {
            let escaped = p.phoneme.replace('\t', "\\t").replace('\n', "\\n");
            buf.push_str(&format!(
                "{:.3}\t{:.3}\t{:.3}\t{}\n",
                p.start_ms, p.end_ms, p.duration_ms, escaped
            ));
        }
        buf
    }

    /// Serialize to SRT-like subtitle format
    pub fn to_srt(&self) -> String {
        let mut buf = String::new();
        for (i, p) in self.phonemes.iter().enumerate() {
            let idx = i + 1;
            let start = format_srt_timestamp(p.start_ms);
            let end = format_srt_timestamp(p.end_ms);
            buf.push_str(&format!("{idx}\n{start} --> {end}\n{}\n\n", p.phoneme));
        }
        buf
    }
}

/// Format milliseconds as SRT timestamp: HH:MM:SS,mmm
fn format_srt_timestamp(ms: f64) -> String {
    let total_ms = ms.round() as u64;
    let millis = total_ms % 1000;
    let total_secs = total_ms / 1000;
    let secs = total_secs % 60;
    let total_mins = total_secs / 60;
    let mins = total_mins % 60;
    let hours = total_mins / 60;
    format!("{hours:02}:{mins:02}:{secs:02},{millis:03}")
}

/// Convert duration tensor output to timing information.
///
/// # Arguments
/// * `durations` - Duration values from ONNX output tensor [phoneme_length]
/// * `phoneme_tokens` - Corresponding phoneme token strings
/// * `sample_rate` - Audio sample rate (e.g., 22050)
/// * `hop_length` - STFT hop length (typically 256 for VITS)
///
/// # Returns
/// TimingResult with start/end timestamps for each phoneme
/// phoneme ID から表示名への逆引きマップを構築する。
///
/// `docs/spec/phoneme-timing-contract.toml` の `[reverse_map]` 規定に従う:
///
/// - **first-wins**: 複数の phoneme 文字列が同一 ID に割り当たっている場合、
///   最初に見つかったものを保持する
/// - **PUA fallback**: 明示マッピングの無い PUA 文字 (U+E000..U+F8FF) は
///   `U+XXXX` 形式 (大文字 hex, 4 桁ゼロ埋め) で表示する
/// - **explicit mapping**: `pua_to_multi_char` が与えられていればそれを優先する
///
/// canonical 実装は `src/python_run/piper_plus/timing.py`
/// (`build_phoneme_id_reverse_map`) で、JS 版は
/// `src/wasm/openjtalk-web/src/timing.js` (`buildPhonemeIdToTokenMap`)。
///
/// # 反復順について
///
/// Python の dict と JS の object は挿入順を保つため first-wins の「最初」が
/// 一意に定まるが、Rust の `HashMap` の反復順は非決定的である。そのため
/// **キーをソートしてから**反復し、決定的な結果を返す。ID が衝突していない
/// マップでは順序が結果に影響しないため canonical と完全に一致する
/// (出荷されている全モデルがこれに該当: fixture の 173 キーで衝突 0 件)。
/// 衝突のあるマップでは canonical と異なる勝者を選び得る。
pub fn build_phoneme_id_reverse_map(
    phoneme_id_map: &HashMap<String, Vec<i64>>,
    pua_to_multi_char: Option<&HashMap<String, String>>,
) -> HashMap<i64, String> {
    let mut reverse: HashMap<i64, String> = HashMap::new();

    let mut keys: Vec<&String> = phoneme_id_map.keys().collect();
    keys.sort();

    for key in keys {
        let display = if let Some(name) = pua_to_multi_char.and_then(|m| m.get(key)) {
            name.clone()
        } else {
            let mut chars = key.chars();
            match (chars.next(), chars.next()) {
                (Some(c), None) if is_private_use_area(c) => {
                    format!("U+{:04X}", c as u32)
                }
                _ => key.clone(),
            }
        };

        for id in &phoneme_id_map[key] {
            reverse.entry(*id).or_insert_with(|| display.clone());
        }
    }

    reverse
}

/// Unicode Private Use Area (U+E000..U+F8FF) の判定。
fn is_private_use_area(c: char) -> bool {
    matches!(c as u32, 0xE000..=0xF8FF)
}

/// phoneme ID 列を表示名列に変換する。逆引きマップに無い ID は
/// `U+XXXX` でも表現できないため `<id>` 形式のまま残す
/// (プレースホルダ `ph_0` と違い、どの ID が未知なのかが分かる)。
pub fn phoneme_ids_to_tokens(
    phoneme_ids: &[i64],
    reverse_map: &HashMap<i64, String>,
) -> Vec<String> {
    phoneme_ids
        .iter()
        .map(|id| {
            reverse_map
                .get(id)
                .cloned()
                .unwrap_or_else(|| format!("<{}>", id))
        })
        .collect()
}

/// timing 出力に使う表示名列を決める。
///
/// `phoneme_ids` が `duration_count` と一致していれば逆引きした実音素名を
/// 返し、一致しなければ位置プレースホルダ (`ph_0`, `ph_1`, ...) を返す。
/// フォールバックは意図的なもので、自信をもって間違えた音素名を出すほうが
/// 明らかに無意味なプレースホルダより有害 (出力だけを見て区別できない)。
/// 戻り値の `bool` はどちらの経路を通ったかを示し、呼び出し側が warn を
/// 出せるようにしている。
///
/// CLI から切り出してテスト可能にしたもの: alignment 条件とフォールバックは
/// piper-cli の中にインラインで書かれていて、どのテストも CI step も
/// どちらの分岐も実行していなかった (issue #656)。
pub fn resolve_timing_tokens(
    phoneme_ids: Option<&[i64]>,
    duration_count: usize,
    phoneme_id_map: &HashMap<String, Vec<i64>>,
    pua_to_multi_char: Option<&HashMap<String, String>>,
) -> (Vec<String>, bool) {
    match phoneme_ids {
        Some(ids) if ids.len() == duration_count && duration_count > 0 => {
            let reverse_map = build_phoneme_id_reverse_map(phoneme_id_map, pua_to_multi_char);
            (phoneme_ids_to_tokens(ids, &reverse_map), true)
        }
        _ => (
            (0..duration_count).map(|i| format!("ph_{}", i)).collect(),
            false,
        ),
    }
}

pub fn durations_to_timing(
    durations: &[f32],
    phoneme_tokens: &[String],
    sample_rate: u32,
    hop_length: usize,
) -> Result<TimingResult, PiperError> {
    if durations.len() != phoneme_tokens.len() {
        return Err(PiperError::Inference(format!(
            "durations length ({}) != phoneme_tokens length ({})",
            durations.len(),
            phoneme_tokens.len()
        )));
    }

    if sample_rate == 0 {
        return Err(PiperError::Inference("sample_rate must be > 0".to_string()));
    }

    if hop_length == 0 {
        return Err(PiperError::Inference("hop_length must be > 0".to_string()));
    }

    // Time in seconds for one frame
    let frame_time_s = hop_length as f64 / sample_rate as f64;
    let frame_time_ms = frame_time_s * 1000.0;

    let mut phonemes = Vec::with_capacity(durations.len());
    let mut cursor_ms: f64 = 0.0;

    for (dur, token) in durations.iter().zip(phoneme_tokens.iter()) {
        let dur_frames = (*dur).max(0.0) as f64;
        let duration_ms = dur_frames * frame_time_ms;
        let start_ms = cursor_ms;
        let end_ms = cursor_ms + duration_ms;

        phonemes.push(PhonemeTimingInfo {
            phoneme: token.clone(),
            start_ms,
            end_ms,
            duration_ms,
        });

        cursor_ms = end_ms;
    }

    Ok(TimingResult {
        total_duration_ms: cursor_ms,
        phonemes,
        sample_rate,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---------------------------------------------------------------
    // Helper
    // ---------------------------------------------------------------

    fn tokens(names: &[&str]) -> Vec<String> {
        names.iter().map(|s| s.to_string()).collect()
    }

    // ---------------------------------------------------------------
    // 1. Basic duration conversion (known values)
    // ---------------------------------------------------------------

    #[test]
    fn test_basic_conversion_22050() {
        // sample_rate=22050, hop=256 => frame_time = 256/22050 s ~ 11.6099 ms
        let durations = vec![10.0, 20.0, 5.0];
        let toks = tokens(&["a", "b", "c"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let frame_ms = 256.0 / 22050.0 * 1000.0;

        assert_eq!(result.phonemes.len(), 3);
        assert_eq!(result.sample_rate, 22050);

        // phoneme "a": start=0, dur=10*frame_ms
        assert!((result.phonemes[0].start_ms - 0.0).abs() < 1e-6);
        assert!((result.phonemes[0].duration_ms - 10.0 * frame_ms).abs() < 1e-6);
        assert!((result.phonemes[0].end_ms - 10.0 * frame_ms).abs() < 1e-6);

        // phoneme "b": start=10*frame_ms, dur=20*frame_ms
        assert!((result.phonemes[1].start_ms - 10.0 * frame_ms).abs() < 1e-6);
        assert!((result.phonemes[1].duration_ms - 20.0 * frame_ms).abs() < 1e-6);

        // phoneme "c": start=30*frame_ms, dur=5*frame_ms
        assert!((result.phonemes[2].start_ms - 30.0 * frame_ms).abs() < 1e-6);

        // total = 35 * frame_ms
        assert!((result.total_duration_ms - 35.0 * frame_ms).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 2. Empty durations
    // ---------------------------------------------------------------

    #[test]
    fn test_empty_durations() {
        let result = durations_to_timing(&[], &[], 22050, 256).unwrap();
        assert!(result.phonemes.is_empty());
        assert!((result.total_duration_ms - 0.0).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 3. Single phoneme
    // ---------------------------------------------------------------

    #[test]
    fn test_single_phoneme() {
        let durations = vec![8.0];
        let toks = tokens(&["k"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        assert_eq!(result.phonemes.len(), 1);
        assert!((result.phonemes[0].start_ms - 0.0).abs() < 1e-6);

        let frame_ms = 256.0 / 22050.0 * 1000.0;
        assert!((result.phonemes[0].duration_ms - 8.0 * frame_ms).abs() < 1e-6);
        assert!((result.total_duration_ms - 8.0 * frame_ms).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 4. Zero durations
    // ---------------------------------------------------------------

    #[test]
    fn test_zero_durations() {
        let durations = vec![0.0, 10.0, 0.0];
        let toks = tokens(&["^", "a", "_"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        assert_eq!(result.phonemes.len(), 3);

        // First phoneme has zero duration
        assert!((result.phonemes[0].duration_ms - 0.0).abs() < 1e-6);
        assert!((result.phonemes[0].start_ms - result.phonemes[0].end_ms).abs() < 1e-6);

        // Second phoneme starts at 0 too
        assert!((result.phonemes[1].start_ms - 0.0).abs() < 1e-6);

        // Third phoneme starts at 10*frame_ms, zero duration
        let frame_ms = 256.0 / 22050.0 * 1000.0;
        assert!((result.phonemes[2].start_ms - 10.0 * frame_ms).abs() < 1e-6);
        assert!((result.phonemes[2].duration_ms - 0.0).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 5. Mismatched lengths error
    // ---------------------------------------------------------------

    #[test]
    fn test_mismatched_lengths() {
        let durations = vec![1.0, 2.0, 3.0];
        let toks = tokens(&["a", "b"]);
        let err = durations_to_timing(&durations, &toks, 22050, 256).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("3"));
        assert!(msg.contains("2"));
    }

    // ---------------------------------------------------------------
    // 6. JSON pretty-print serialization roundtrip
    // ---------------------------------------------------------------

    #[test]
    fn test_json_roundtrip() {
        let durations = vec![5.0, 15.0];
        let toks = tokens(&["h", "i"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let json = result.to_json().unwrap();

        // Deserialize back to verify structure
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert!(parsed.is_object());
        assert!(parsed["phonemes"].is_array());
        assert_eq!(parsed["phonemes"].as_array().unwrap().len(), 2);
        assert_eq!(parsed["sample_rate"].as_u64().unwrap(), 22050);

        let first = &parsed["phonemes"][0];
        assert_eq!(first["phoneme"].as_str().unwrap(), "h");
        assert!((first["start_ms"].as_f64().unwrap() - 0.0).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 7. JSON compact serialization
    // ---------------------------------------------------------------

    #[test]
    fn test_json_compact() {
        let durations = vec![3.0];
        let toks = tokens(&["x"]);
        let result = durations_to_timing(&durations, &toks, 16000, 256).unwrap();

        let json_compact = result.to_json_compact().unwrap();
        // Compact should not contain newlines (single-line JSON)
        assert!(!json_compact.contains('\n'));
        assert!(json_compact.contains("\"phoneme\":\"x\""));
    }

    // ---------------------------------------------------------------
    // 8. TSV format correctness
    // ---------------------------------------------------------------

    #[test]
    fn test_tsv_format() {
        let durations = vec![10.0, 20.0];
        let toks = tokens(&["p", "q"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let tsv = result.to_tsv();
        let lines: Vec<&str> = tsv.lines().collect();

        // Header line
        assert_eq!(lines[0], "start_ms\tend_ms\tduration_ms\tphoneme");

        // Data rows
        assert_eq!(lines.len(), 3); // header + 2 phonemes

        // First row should start at 0.000
        assert!(lines[1].starts_with("0.000\t"));
        assert!(lines[1].ends_with("\tp"));

        // Second row phoneme should be "q"
        assert!(lines[2].ends_with("\tq"));
    }

    // ---------------------------------------------------------------
    // 9. TSV empty input
    // ---------------------------------------------------------------

    #[test]
    fn test_tsv_empty() {
        let result = durations_to_timing(&[], &[], 22050, 256).unwrap();
        let tsv = result.to_tsv();
        let lines: Vec<&str> = tsv.lines().collect();
        assert_eq!(lines.len(), 1); // header only
    }

    // ---------------------------------------------------------------
    // 10. SRT format correctness
    // ---------------------------------------------------------------

    #[test]
    fn test_srt_format() {
        // Use easy numbers: sample_rate=1000, hop_length=1 => 1 frame = 1 ms
        let durations = vec![500.0, 1500.0, 3000.0];
        let toks = tokens(&["a", "bb", "c"]);
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let srt = result.to_srt();
        let blocks: Vec<&str> = srt.split("\n\n").filter(|b| !b.is_empty()).collect();
        assert_eq!(blocks.len(), 3);

        // First block: index 1, 00:00:00,000 --> 00:00:00,500, phoneme "a"
        let lines0: Vec<&str> = blocks[0].lines().collect();
        assert_eq!(lines0[0], "1");
        assert_eq!(lines0[1], "00:00:00,000 --> 00:00:00,500");
        assert_eq!(lines0[2], "a");

        // Second block: index 2, 00:00:00,500 --> 00:00:02,000, phoneme "bb"
        let lines1: Vec<&str> = blocks[1].lines().collect();
        assert_eq!(lines1[0], "2");
        assert_eq!(lines1[1], "00:00:00,500 --> 00:00:02,000");
        assert_eq!(lines1[2], "bb");

        // Third block: 00:00:02,000 --> 00:00:05,000
        let lines2: Vec<&str> = blocks[2].lines().collect();
        assert_eq!(lines2[0], "3");
        assert_eq!(lines2[1], "00:00:02,000 --> 00:00:05,000");
        assert_eq!(lines2[2], "c");
    }

    // ---------------------------------------------------------------
    // 11. SRT timestamp with hours/minutes
    // ---------------------------------------------------------------

    #[test]
    fn test_srt_large_timestamps() {
        // 90 minutes + 5 seconds + 123 ms = 5,405,123 ms
        // Use sample_rate=1000, hop=1 so frames = ms directly
        let dur_ms = 5_405_123.0_f32;
        let durations = vec![dur_ms];
        let toks = tokens(&["long"]);
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let srt = result.to_srt();
        assert!(srt.contains("00:00:00,000 --> 01:30:05,123"));
    }

    // ---------------------------------------------------------------
    // 12. Sample rate 16000
    // ---------------------------------------------------------------

    #[test]
    fn test_sample_rate_16000() {
        let durations = vec![16.0];
        let toks = tokens(&["z"]);
        let result = durations_to_timing(&durations, &toks, 16000, 256).unwrap();

        // frame_ms = 256/16000*1000 = 16.0 ms
        // duration_ms = 16 frames * 16.0 ms = 256.0 ms
        let expected_ms = 16.0 * (256.0 / 16000.0 * 1000.0);
        assert!((result.phonemes[0].duration_ms - expected_ms).abs() < 1e-6);
        assert!((result.total_duration_ms - expected_ms).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 13. Sample rate 44100
    // ---------------------------------------------------------------

    #[test]
    fn test_sample_rate_44100() {
        let durations = vec![100.0];
        let toks = tokens(&["w"]);
        let result = durations_to_timing(&durations, &toks, 44100, 256).unwrap();

        let frame_ms = 256.0 / 44100.0 * 1000.0;
        let expected_ms = 100.0 * frame_ms;
        assert!((result.phonemes[0].duration_ms - expected_ms).abs() < 1e-6);
        assert_eq!(result.sample_rate, 44100);
    }

    // ---------------------------------------------------------------
    // 14. Large duration values
    // ---------------------------------------------------------------

    #[test]
    fn test_large_duration_values() {
        let durations = vec![100_000.0, 200_000.0];
        let toks = tokens(&["aa", "bb"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let frame_ms = 256.0 / 22050.0 * 1000.0;
        let expected_total = 300_000.0 * frame_ms;
        assert!((result.total_duration_ms - expected_total).abs() < 1e-3);

        // Second phoneme starts after the first
        assert!((result.phonemes[1].start_ms - 100_000.0 * frame_ms).abs() < 1e-3);
    }

    // ---------------------------------------------------------------
    // 15. Floating point precision -- cumulative sum stays accurate
    // ---------------------------------------------------------------

    #[test]
    fn test_floating_point_precision() {
        // Many small durations to test accumulation
        let n = 1000;
        let durations: Vec<f32> = vec![1.0; n];
        let toks: Vec<String> = (0..n).map(|i| format!("p{i}")).collect();
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let frame_ms = 256.0 / 22050.0 * 1000.0;
        let expected_total = n as f64 * frame_ms;

        // Total should be very close despite 1000 additions
        assert!(
            (result.total_duration_ms - expected_total).abs() < 0.01,
            "total={} expected={}",
            result.total_duration_ms,
            expected_total
        );

        // Last phoneme end should equal total
        let last = result.phonemes.last().unwrap();
        assert!((last.end_ms - result.total_duration_ms).abs() < 1e-9);
    }

    // ---------------------------------------------------------------
    // 16. Negative duration values are clamped to zero
    // ---------------------------------------------------------------

    #[test]
    fn test_negative_durations_clamped() {
        let durations = vec![-5.0, 10.0, -1.0];
        let toks = tokens(&["a", "b", "c"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        // Negative durations should be treated as 0
        assert!((result.phonemes[0].duration_ms - 0.0).abs() < 1e-6);
        assert!((result.phonemes[2].duration_ms - 0.0).abs() < 1e-6);

        // Only phoneme "b" contributes to total
        let frame_ms = 256.0 / 22050.0 * 1000.0;
        assert!((result.total_duration_ms - 10.0 * frame_ms).abs() < 1e-6);
    }

    // ---------------------------------------------------------------
    // 17. Zero sample_rate error
    // ---------------------------------------------------------------

    #[test]
    fn test_zero_sample_rate_error() {
        let durations = vec![1.0];
        let toks = tokens(&["a"]);
        let err = durations_to_timing(&durations, &toks, 0, 256).unwrap_err();
        assert!(err.to_string().contains("sample_rate"));
    }

    // ---------------------------------------------------------------
    // 18. Zero hop_length error
    // ---------------------------------------------------------------

    #[test]
    fn test_zero_hop_length_error() {
        let durations = vec![1.0];
        let toks = tokens(&["a"]);
        let err = durations_to_timing(&durations, &toks, 22050, 0).unwrap_err();
        assert!(err.to_string().contains("hop_length"));
    }

    // ---------------------------------------------------------------
    // 19. DEFAULT_HOP_LENGTH constant value
    // ---------------------------------------------------------------

    #[test]
    fn test_default_hop_length() {
        assert_eq!(DEFAULT_HOP_LENGTH, 256);
    }

    // ---------------------------------------------------------------
    // 20. Phoneme ordering preserved
    // ---------------------------------------------------------------

    #[test]
    fn test_phoneme_ordering_preserved() {
        let durations = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let toks = tokens(&["^", "k", "o", "N", "_"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let names: Vec<&str> = result.phonemes.iter().map(|p| p.phoneme.as_str()).collect();
        assert_eq!(names, vec!["^", "k", "o", "N", "_"]);

        // Each start equals previous end
        for i in 1..result.phonemes.len() {
            assert!(
                (result.phonemes[i].start_ms - result.phonemes[i - 1].end_ms).abs() < 1e-9,
                "gap between phoneme {} and {}",
                i - 1,
                i
            );
        }
    }

    // ---------------------------------------------------------------
    // 21. TSV field values match JSON values
    // ---------------------------------------------------------------

    #[test]
    fn test_tsv_and_json_consistency() {
        let durations = vec![7.0, 13.0];
        let toks = tokens(&["s", "t"]);
        let result = durations_to_timing(&durations, &toks, 22050, 256).unwrap();

        let json_str = result.to_json().unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();

        let tsv = result.to_tsv();
        let data_lines: Vec<&str> = tsv.lines().skip(1).collect();

        for (i, line) in data_lines.iter().enumerate() {
            let fields: Vec<&str> = line.split('\t').collect();
            assert_eq!(fields.len(), 4);

            let tsv_start: f64 = fields[0].parse().unwrap();
            let tsv_end: f64 = fields[1].parse().unwrap();
            let tsv_dur: f64 = fields[2].parse().unwrap();
            let tsv_phoneme = fields[3];

            let json_ph = &parsed["phonemes"][i];
            let json_start = json_ph["start_ms"].as_f64().unwrap();
            let json_end = json_ph["end_ms"].as_f64().unwrap();
            let json_phoneme = json_ph["phoneme"].as_str().unwrap();

            assert!((tsv_start - json_start).abs() < 0.01);
            assert!((tsv_end - json_end).abs() < 0.01);
            assert!(tsv_dur > 0.0 || (tsv_dur - 0.0).abs() < 1e-6);
            assert_eq!(tsv_phoneme, json_phoneme);
        }
    }

    // ---------------------------------------------------------------
    // 22. Phoneme name containing tab in TSV output
    // ---------------------------------------------------------------

    #[test]
    fn test_tsv_phoneme_with_tab() {
        // spec [output_formats.tsv].escape_tab_in_phoneme = "\\t":
        // a phoneme token containing a literal tab character must be
        // escaped to the 2-char sequence `\t` so the TSV column count
        // remains 4 (cross-runtime parity with Python/C#/Go/WASM).
        let durations = vec![5.0];
        let toks = vec!["a\tb".to_string()];
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let tsv = result.to_tsv();
        let data_line = tsv.lines().nth(1).expect("expected a data line");
        let fields: Vec<&str> = data_line.split('\t').collect();

        // Spec-conforming behavior: 4 fields, phoneme column contains
        // the escaped 4-char sequence `a\tb` (a, backslash, t, b).
        assert_eq!(
            fields.len(),
            4,
            "tab inside phoneme name must be escaped (spec compliance)"
        );
        assert_eq!(fields[3], "a\\tb");
    }

    // ---------------------------------------------------------------
    // 22b. Phoneme name containing newline in TSV output
    // ---------------------------------------------------------------

    #[test]
    fn test_tsv_phoneme_with_newline() {
        // spec [output_formats.tsv].escape_newline_in_phoneme = "\\n":
        // a phoneme token containing an embedded newline must be
        // escaped so the TSV row count is preserved.
        let durations = vec![5.0];
        let toks = vec!["x\ny".to_string()];
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let tsv = result.to_tsv();
        // Header + 1 data row + trailing newline (no third row).
        let lines: Vec<&str> = tsv.lines().collect();
        assert_eq!(lines.len(), 2, "newline in phoneme must not split the row");

        let fields: Vec<&str> = lines[1].split('\t').collect();
        assert_eq!(fields.len(), 4);
        assert_eq!(fields[3], "x\\ny");
    }

    #[test]
    fn test_tsv_phoneme_with_tab_and_newline_mixed() {
        // Both escapes applied in a single token.
        let durations = vec![5.0];
        let toks = vec!["a\tb\nc".to_string()];
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let tsv = result.to_tsv();
        let data_line = tsv.lines().nth(1).unwrap();
        let fields: Vec<&str> = data_line.split('\t').collect();
        assert_eq!(fields.len(), 4);
        assert_eq!(fields[3], "a\\tb\\nc");
    }

    // ---------------------------------------------------------------
    // 23. Phoneme name containing newline in SRT output
    // ---------------------------------------------------------------

    #[test]
    fn test_srt_phoneme_with_newline() {
        // A phoneme token with an embedded newline will split the
        // subtitle text across two visual lines inside the SRT entry.
        // The entry count should still be 1 since entries are delimited
        // by blank lines ("\n\n").
        let durations = vec![10.0];
        let toks = vec!["line1\nline2".to_string()];
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        let srt = result.to_srt();

        // The block delimiter is "\n\n".  Because the phoneme itself
        // contains "\n", we verify that the index "1" and the arrow
        // marker are still present and structurally correct.
        assert!(srt.contains("1\n"));
        assert!(srt.contains(" --> "));
        assert!(srt.contains("line1\nline2"));
    }

    // ---------------------------------------------------------------
    // 24. Duration with NaN — clamped to 0 by f32::max(0.0)
    // ---------------------------------------------------------------

    #[test]
    fn test_nan_duration() {
        let durations = vec![f32::NAN, 10.0];
        let toks = tokens(&["nan_ph", "ok"]);
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        // Rust's f32::max returns the non-NaN argument when one operand
        // is NaN, so NAN.max(0.0) == 0.0. The NaN is effectively clamped.
        assert!(
            (result.phonemes[0].duration_ms - 0.0).abs() < 1e-9,
            "NaN duration is clamped to 0 by f32::max"
        );
        assert!(
            (result.phonemes[0].start_ms - result.phonemes[0].end_ms).abs() < 1e-9,
            "start == end for zero-duration phoneme"
        );

        // The second phoneme should still have a valid duration.
        assert!(
            (result.phonemes[1].duration_ms - 10.0).abs() < 1e-6,
            "non-NaN phoneme keeps its value"
        );

        // Total should only reflect the valid phoneme
        assert!(
            (result.total_duration_ms - 10.0).abs() < 1e-6,
            "total reflects only the non-NaN phoneme"
        );
    }

    // ---------------------------------------------------------------
    // 25. Duration with Infinity — propagates as infinite ms
    // ---------------------------------------------------------------

    #[test]
    fn test_infinity_duration() {
        let durations = vec![f32::INFINITY];
        let toks = tokens(&["inf_ph"]);
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        assert!(
            result.phonemes[0].duration_ms.is_infinite(),
            "Infinity duration propagates"
        );
        assert!(
            result.total_duration_ms.is_infinite(),
            "total also becomes infinite"
        );
    }

    // ---------------------------------------------------------------
    // 26. Unicode / IPA phoneme names in all formats
    // ---------------------------------------------------------------

    #[test]
    fn test_unicode_phoneme_names() {
        let ipa_tokens = vec![
            "\u{0251}\u{02D0}".to_string(), // ɑː
            "\u{0283}".to_string(),         // ʃ
            "\u{014B}".to_string(),         // ŋ
        ];
        let durations = vec![5.0, 3.0, 7.0];
        let result = durations_to_timing(&durations, &ipa_tokens, 1000, 1).unwrap();

        // Verify phoneme names are preserved
        assert_eq!(result.phonemes[0].phoneme, "\u{0251}\u{02D0}");
        assert_eq!(result.phonemes[1].phoneme, "\u{0283}");
        assert_eq!(result.phonemes[2].phoneme, "\u{014B}");

        // JSON roundtrip preserves Unicode
        let json = result.to_json().unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(
            parsed["phonemes"][0]["phoneme"].as_str().unwrap(),
            "\u{0251}\u{02D0}"
        );

        // TSV contains the Unicode characters
        let tsv = result.to_tsv();
        assert!(tsv.contains("\u{0251}\u{02D0}"));
        assert!(tsv.contains("\u{0283}"));
        assert!(tsv.contains("\u{014B}"));

        // SRT contains the Unicode characters
        let srt = result.to_srt();
        assert!(srt.contains("\u{0251}\u{02D0}"));
        assert!(srt.contains("\u{0283}"));
        assert!(srt.contains("\u{014B}"));
    }

    // ---------------------------------------------------------------
    // 27. Very small durations preserve precision
    // ---------------------------------------------------------------

    #[test]
    fn test_very_small_durations_precision() {
        // 0.001 frames at sample_rate=1000, hop=1 => 0.001 ms per frame
        let durations = vec![0.001_f32];
        let toks = tokens(&["tiny"]);
        let result = durations_to_timing(&durations, &toks, 1000, 1).unwrap();

        // frame_time_ms = 1.0 ms; duration = 0.001 * 1.0 = 0.001 ms
        let expected = 0.001_f64;
        assert!(
            (result.phonemes[0].duration_ms - expected).abs() < 1e-9,
            "very small duration: got {} expected {}",
            result.phonemes[0].duration_ms,
            expected
        );

        // TSV should render with sub-millisecond precision via {:.3}
        let tsv = result.to_tsv();
        let data_line = tsv.lines().nth(1).unwrap();
        // The duration field (3rd column) should be "0.001"
        let fields: Vec<&str> = data_line.split('\t').collect();
        assert_eq!(fields[2], "0.001");
    }

    // ---------------------------------------------------------------
    // 28. TimingResult direct construction and field access
    // ---------------------------------------------------------------

    #[test]
    fn test_timing_result_direct_construction() {
        let timing = TimingResult {
            phonemes: vec![
                PhonemeTimingInfo {
                    phoneme: "hello".to_string(),
                    start_ms: 0.0,
                    end_ms: 100.5,
                    duration_ms: 100.5,
                },
                PhonemeTimingInfo {
                    phoneme: "world".to_string(),
                    start_ms: 100.5,
                    end_ms: 250.0,
                    duration_ms: 149.5,
                },
            ],
            total_duration_ms: 250.0,
            sample_rate: 48000,
        };

        // Field access
        assert_eq!(timing.phonemes.len(), 2);
        assert_eq!(timing.phonemes[0].phoneme, "hello");
        assert_eq!(timing.phonemes[1].phoneme, "world");
        assert!((timing.phonemes[0].start_ms - 0.0).abs() < 1e-9);
        assert!((timing.phonemes[0].end_ms - 100.5).abs() < 1e-9);
        assert!((timing.phonemes[0].duration_ms - 100.5).abs() < 1e-9);
        assert!((timing.phonemes[1].start_ms - 100.5).abs() < 1e-9);
        assert!((timing.phonemes[1].end_ms - 250.0).abs() < 1e-9);
        assert!((timing.phonemes[1].duration_ms - 149.5).abs() < 1e-9);
        assert!((timing.total_duration_ms - 250.0).abs() < 1e-9);
        assert_eq!(timing.sample_rate, 48000);

        // Clone trait works
        let cloned = timing.clone();
        assert_eq!(cloned.phonemes.len(), timing.phonemes.len());
        assert_eq!(cloned.sample_rate, timing.sample_rate);

        // Serialization works on directly constructed structs
        let json = timing.to_json().unwrap();
        assert!(json.contains("\"hello\""));
        assert!(json.contains("\"world\""));
        assert!(json.contains("48000"));
    }

    // ---------------------------------------------------------------
    // 29. JSON serializes non-finite f64 as null (serde_json >=1.0.128)
    // ---------------------------------------------------------------

    #[test]
    fn test_json_nonfinite_serialized_as_null() {
        // serde_json >= 1.0.128 serializes NaN / Infinity as JSON null
        // rather than returning an error.  Verify this behaviour so that
        // callers know what to expect when a TimingResult contains
        // non-finite values (e.g. from an Infinity input duration).
        let timing = TimingResult {
            phonemes: vec![PhonemeTimingInfo {
                phoneme: "inf".to_string(),
                start_ms: 0.0,
                end_ms: f64::INFINITY,
                duration_ms: f64::INFINITY,
            }],
            total_duration_ms: f64::INFINITY,
            sample_rate: 22050,
        };

        // to_json should succeed (not error)
        let json = timing.to_json().expect("to_json should succeed");
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();

        // Non-finite values become null in JSON
        assert!(
            parsed["total_duration_ms"].is_null(),
            "Infinity total_duration_ms serialized as null"
        );
        assert!(
            parsed["phonemes"][0]["end_ms"].is_null(),
            "Infinity end_ms serialized as null"
        );
        assert!(
            parsed["phonemes"][0]["duration_ms"].is_null(),
            "Infinity duration_ms serialized as null"
        );

        // Finite values remain as numbers
        assert!(
            parsed["phonemes"][0]["start_ms"].is_number(),
            "finite start_ms remains a number"
        );

        // Compact format also succeeds
        let compact = timing.to_json_compact().expect("compact should succeed");
        assert!(
            compact.contains("null"),
            "compact JSON contains null for Infinity"
        );

        // PiperError::from(serde_json::Error) conversion is exercised
        // by to_json / to_json_compact internally via map_err.
        // Verify the error path is reachable with truly invalid JSON input.
        let bad_json = "{ not valid json }";
        let serde_err: Result<serde_json::Value, _> = serde_json::from_str(bad_json);
        let piper_err: PiperError = serde_err.unwrap_err().into();
        let msg = piper_err.to_string();
        assert!(
            msg.contains("JSON"),
            "PiperError from serde_json mentions JSON: {}",
            msg
        );
    }

    /// SRT millisecond rounding is half-away-from-zero per
    /// docs/spec/phoneme-timing-contract.toml [output_formats.srt].rounding. Every
    /// case has an EVEN integer part, which is exactly where half-to-even and
    /// half-away-from-zero disagree; a case such as 1.5 rounds to 2 under both and
    /// proves nothing. Python and C# used their language default (ToEven) and were
    /// 1 ms early on every such boundary (issue #681) -- this runtime is the
    /// reference the others cite, so these cases lock it in place.
    #[test]
    fn format_srt_timestamp_rounds_half_away_from_zero() {
        let cases: [(f64, &str); 6] = [
            (0.5_f64, "00:00:00,001"),
            (1234.5_f64, "00:00:01,235"),
            (2500.5_f64, "00:00:02,501"),
            (0.0_f64, "00:00:00,000"),
            // Largest double below 0.5: `ms + 0.5` is exactly 1.0 in binary64,
            // so the floor(ms + 0.5) idiom yields 1 here while a true round()
            // yields 0. This case is what keeps Python and C++ off that idiom.
            (0.49999999999999994_f64, "00:00:00,000"),
            (3661500.0_f64, "01:01:01,500"),
        ];
        for (ms, want) in cases {
            assert_eq!(
                format_srt_timestamp(ms),
                want,
                "format_srt_timestamp({ms}) must round half away from zero"
            );
        }
    }

    // ---- reverse map (issue #656) ----
    //
    // spec `[reverse_map]` の 3 規定 (first-wins / PUA fallback /
    // explicit mapping) と、canonical (Python) / JS との一致を pin する。
    // 修正前の Rust CLI は `ph_0`, `ph_1`, ... という連番プレースホルダを
    // 出力しており、timing から音素を識別できなかった。

    fn sample_id_map() -> HashMap<String, Vec<i64>> {
        let mut m = HashMap::new();
        m.insert("a".to_string(), vec![5]);
        m.insert("b".to_string(), vec![6, 7]);
        m.insert("\u{e019}".to_string(), vec![42]);
        m.insert("ch".to_string(), vec![50]);
        m
    }

    #[test]
    fn reverse_map_maps_every_id_of_a_key() {
        let reverse = build_phoneme_id_reverse_map(&sample_id_map(), None);
        assert_eq!(reverse.get(&5), Some(&"a".to_string()));
        // Both ids of "b" must resolve; the canonical doctest pins {6: 'b', 7: 'b'}.
        assert_eq!(reverse.get(&6), Some(&"b".to_string()));
        assert_eq!(reverse.get(&7), Some(&"b".to_string()));
    }

    #[test]
    fn reverse_map_renders_unmapped_pua_as_codepoint() {
        let reverse = build_phoneme_id_reverse_map(&sample_id_map(), None);
        // U+E019 has no explicit name, so the contract's
        // [reverse_map.pua_handling] fallback applies: uppercase, 4 hex digits.
        assert_eq!(reverse.get(&42), Some(&"U+E019".to_string()));
    }

    #[test]
    fn reverse_map_prefers_explicit_pua_name() {
        let mut pua = HashMap::new();
        pua.insert("\u{e019}".to_string(), "N_m".to_string());
        let reverse = build_phoneme_id_reverse_map(&sample_id_map(), Some(&pua));
        assert_eq!(reverse.get(&42), Some(&"N_m".to_string()));
    }

    #[test]
    fn reverse_map_passes_multi_char_keys_through() {
        let reverse = build_phoneme_id_reverse_map(&sample_id_map(), None);
        // "ch" is two chars, so the PUA branch must not fire even though its
        // first char would not be PUA either.
        assert_eq!(reverse.get(&50), Some(&"ch".to_string()));
    }

    #[test]
    fn resolve_timing_tokens_uses_real_phonemes_when_aligned() {
        let ids = vec![5, 6, 50];
        let (tokens, resolved) =
            resolve_timing_tokens(Some(&ids), ids.len(), &sample_id_map(), None);
        assert!(resolved, "aligned ids must take the reverse-map branch");
        assert_eq!(tokens, vec!["a", "b", "ch"]);
    }

    #[test]
    fn resolve_timing_tokens_applies_pua_names_when_aligned() {
        let mut pua = HashMap::new();
        pua.insert("\u{e019}".to_string(), "N_m".to_string());
        let ids = vec![42, 5];
        let (tokens, resolved) =
            resolve_timing_tokens(Some(&ids), ids.len(), &sample_id_map(), Some(&pua));
        assert!(resolved);
        assert_eq!(tokens, vec!["N_m", "a"]);
    }

    #[test]
    fn resolve_timing_tokens_falls_back_when_counts_differ() {
        // The pre-#656 bug shape: the caller passed text-derived ids (5) while
        // the decoder produced 15 durations (Strategy A padding / Strategy C
        // SSML wrap). Emitting the 5 names against 15 slots would silently
        // mislabel every entry, so placeholders are required here.
        let ids = vec![5, 6, 7, 50, 42];
        let (tokens, resolved) = resolve_timing_tokens(Some(&ids), 15, &sample_id_map(), None);
        assert!(!resolved, "mismatched counts must NOT claim resolution");
        assert_eq!(tokens.len(), 15);
        assert_eq!(tokens[0], "ph_0");
        assert_eq!(tokens[14], "ph_14");
        // No real phoneme name may leak into the fallback labels.
        assert!(
            tokens.iter().all(|t| t.starts_with("ph_")),
            "fallback leaked a reverse-mapped name: {:?}",
            tokens
        );
    }

    #[test]
    fn resolve_timing_tokens_falls_back_when_ids_absent() {
        let (tokens, resolved) = resolve_timing_tokens(None, 3, &sample_id_map(), None);
        assert!(!resolved);
        assert_eq!(tokens, vec!["ph_0", "ph_1", "ph_2"]);
    }

    #[test]
    fn resolve_timing_tokens_treats_zero_durations_as_unresolved() {
        // Zero durations means there is nothing to label; claiming `resolved`
        // would make the caller skip the warning for an empty-and-broken
        // result. Empty ids also trivially "match" length 0, so the guard has
        // to be explicit.
        let ids: Vec<i64> = Vec::new();
        let (tokens, resolved) = resolve_timing_tokens(Some(&ids), 0, &sample_id_map(), None);
        assert!(!resolved);
        assert!(tokens.is_empty());
    }

    #[test]
    fn resolve_timing_tokens_keeps_padded_alignment() {
        // Strategy A pads the id list; engine.rs now returns the PADDED ids so
        // they line up with the padded durations. This pins that contract: a
        // 15-long id list against 15 durations resolves, and the pad ids
        // themselves get real names rather than placeholders.
        let ids: Vec<i64> = (0..15).map(|i| if i % 2 == 0 { 5 } else { 6 }).collect();
        let (tokens, resolved) =
            resolve_timing_tokens(Some(&ids), ids.len(), &sample_id_map(), None);
        assert!(resolved);
        assert_eq!(tokens.len(), 15);
        assert_eq!(tokens[0], "a");
        assert_eq!(tokens[1], "b");
    }

    #[test]
    fn resolve_timing_tokens_marks_unknown_ids_distinctly() {
        // An id outside the map is a different failure from a count mismatch:
        // alignment holds, so only that one slot is unknown. It must be
        // `<id>`, never `ph_N` (which would imply the whole run is unaligned).
        let ids = vec![5, 9999];
        let (tokens, resolved) =
            resolve_timing_tokens(Some(&ids), ids.len(), &sample_id_map(), None);
        assert!(resolved);
        assert_eq!(tokens, vec!["a", "<9999>"]);
    }

    #[test]
    fn reverse_map_is_first_wins_and_deterministic() {
        // Two keys claim id 9. HashMap iteration order is not stable, so the
        // implementation sorts keys: "aa" wins over "zz" on every run.
        let mut m = HashMap::new();
        m.insert("zz".to_string(), vec![9]);
        m.insert("aa".to_string(), vec![9]);

        for _ in 0..16 {
            let reverse = build_phoneme_id_reverse_map(&m, None);
            assert_eq!(
                reverse.get(&9),
                Some(&"aa".to_string()),
                "collision winner must not vary between runs"
            );
        }
    }

    #[test]
    fn reverse_map_pua_boundaries() {
        let mut m = HashMap::new();
        // U+DFFF is a surrogate and cannot be a Rust char literal, so the
        // "just below" probe uses the nearest valid scalar instead.
        m.insert("\u{d7ff}".to_string(), vec![1]); // just below the surrogate block
        m.insert("\u{e000}".to_string(), vec![2]); // first PUA
        m.insert("\u{f8ff}".to_string(), vec![3]); // last PUA
        m.insert("\u{f900}".to_string(), vec![4]); // just above
        let reverse = build_phoneme_id_reverse_map(&m, None);

        assert_eq!(reverse.get(&2), Some(&"U+E000".to_string()));
        assert_eq!(reverse.get(&3), Some(&"U+F8FF".to_string()));
        // Outside the range the character passes through unchanged.
        assert_ne!(reverse.get(&4), Some(&"U+F900".to_string()));
        assert_ne!(reverse.get(&1), Some(&"U+D7FF".to_string()));
    }

    #[test]
    fn tokens_mark_unknown_ids_distinguishably() {
        let reverse = build_phoneme_id_reverse_map(&sample_id_map(), None);
        let tokens = phoneme_ids_to_tokens(&[5, 999, 42], &reverse);
        // A missing id must be identifiable, unlike the old `ph_N` placeholder
        // which said nothing about which id it was.
        assert_eq!(tokens, vec!["a", "<999>", "U+E019"]);
    }
}
