//! Integration tests for the phoneme timing module.
//!
//! Verifies duration-to-timestamp conversion, serialization formats
//! (JSON / TSV / SRT), edge cases, and timing invariants.

use piper_plus::timing::{DEFAULT_HOP_LENGTH, durations_to_timing};

// =========================================================================
// Helper
// =========================================================================

/// Expected milliseconds for a single frame at the given sample rate / hop.
fn frame_ms(sample_rate: u32, hop_length: usize) -> f64 {
    (hop_length as f64 / sample_rate as f64) * 1000.0
}

// =========================================================================
// 1. Basic conversion
// =========================================================================

#[test]
fn test_three_phonemes_known_timestamps() {
    let durations = [10.0_f32, 20.0, 15.0];
    let tokens: Vec<String> = vec!["a", "b", "c"].into_iter().map(String::from).collect();
    let sr = 22050;
    let hop = 256;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    let ms_per_frame = frame_ms(sr, hop);

    // Phoneme "a": frames 0..10 -> 0 .. 10*ms_per_frame
    assert!((result.phonemes[0].start_ms - 0.0).abs() < 1e-6);
    assert!((result.phonemes[0].duration_ms - 10.0 * ms_per_frame).abs() < 1e-6);
    assert!((result.phonemes[0].end_ms - 10.0 * ms_per_frame).abs() < 1e-6);

    // Phoneme "b": frames 10..30 -> 10*ms .. 30*ms
    assert!((result.phonemes[1].start_ms - 10.0 * ms_per_frame).abs() < 1e-6);
    assert!((result.phonemes[1].duration_ms - 20.0 * ms_per_frame).abs() < 1e-6);
    assert!((result.phonemes[1].end_ms - 30.0 * ms_per_frame).abs() < 1e-6);

    // Phoneme "c": frames 30..45 -> 30*ms .. 45*ms
    assert!((result.phonemes[2].start_ms - 30.0 * ms_per_frame).abs() < 1e-6);
    assert!((result.phonemes[2].duration_ms - 15.0 * ms_per_frame).abs() < 1e-6);
    assert!((result.phonemes[2].end_ms - 45.0 * ms_per_frame).abs() < 1e-6);

    // Total duration
    assert!((result.total_duration_ms - 45.0 * ms_per_frame).abs() < 1e-6);
    assert_eq!(result.sample_rate, sr);
}

#[test]
fn test_single_phoneme() {
    let durations = [7.0_f32];
    let tokens: Vec<String> = vec!["x".to_string()];
    let sr = 16000;
    let hop = 256;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    assert_eq!(result.phonemes.len(), 1);
    assert!((result.phonemes[0].start_ms - 0.0).abs() < 1e-6);
    let expected = 7.0 * frame_ms(sr, hop);
    assert!((result.phonemes[0].duration_ms - expected).abs() < 1e-6);
    assert!((result.phonemes[0].end_ms - expected).abs() < 1e-6);
    assert!((result.total_duration_ms - expected).abs() < 1e-6);
    assert_eq!(result.phonemes[0].phoneme, "x");
}

#[test]
fn test_equal_durations() {
    let n = 5;
    let dur_val = 12.0_f32;
    let durations = vec![dur_val; n];
    let tokens: Vec<String> = (0..n).map(|i| format!("p{}", i)).collect();
    let sr = 22050;
    let hop = DEFAULT_HOP_LENGTH;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    assert_eq!(result.phonemes.len(), n);
    let ms = frame_ms(sr, hop);
    for (i, ph) in result.phonemes.iter().enumerate() {
        let expected_start = i as f64 * dur_val as f64 * ms;
        assert!(
            (ph.start_ms - expected_start).abs() < 1e-6,
            "phoneme {} start mismatch",
            i
        );
        assert!(
            (ph.duration_ms - dur_val as f64 * ms).abs() < 1e-6,
            "phoneme {} duration mismatch",
            i
        );
    }
    assert!((result.total_duration_ms - n as f64 * dur_val as f64 * ms).abs() < 1e-6);
}

// =========================================================================
// 2. Edge cases
// =========================================================================

#[test]
fn test_empty_input() {
    let durations: Vec<f32> = vec![];
    let tokens: Vec<String> = vec![];

    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    assert!(result.phonemes.is_empty());
    assert!((result.total_duration_ms - 0.0).abs() < 1e-6);
}

#[test]
fn test_zero_duration_phonemes() {
    let durations = [0.0_f32, 5.0, 0.0];
    let tokens: Vec<String> = vec!["a", "b", "c"].into_iter().map(String::from).collect();
    let sr = 22050;
    let hop = DEFAULT_HOP_LENGTH;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    assert_eq!(result.phonemes.len(), 3);
    // First phoneme: 0 duration
    assert!((result.phonemes[0].start_ms - 0.0).abs() < 1e-6);
    assert!((result.phonemes[0].end_ms - 0.0).abs() < 1e-6);
    assert!((result.phonemes[0].duration_ms - 0.0).abs() < 1e-6);
    // Second phoneme starts at 0
    assert!((result.phonemes[1].start_ms - 0.0).abs() < 1e-6);
    // Third phoneme: zero duration, starts where b ends
    let b_end = 5.0 * frame_ms(sr, hop);
    assert!((result.phonemes[2].start_ms - b_end).abs() < 1e-6);
    assert!((result.phonemes[2].duration_ms - 0.0).abs() < 1e-6);
}

#[test]
fn test_mismatched_lengths_returns_error() {
    let durations = [1.0_f32, 2.0, 3.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();

    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH);
    assert!(result.is_err(), "mismatched lengths should return an error");
}

#[test]
fn test_mismatched_lengths_more_tokens_than_durations() {
    let durations = [1.0_f32];
    let tokens: Vec<String> = vec!["a", "b", "c"].into_iter().map(String::from).collect();

    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH);
    assert!(result.is_err());
}

#[test]
fn test_very_large_duration_values() {
    let durations = [1_000_000.0_f32];
    let tokens: Vec<String> = vec!["long".to_string()];
    let sr = 22050;
    let hop = DEFAULT_HOP_LENGTH;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    let expected_ms = 1_000_000.0 * frame_ms(sr, hop);
    assert!((result.phonemes[0].duration_ms - expected_ms).abs() < 1.0);
    assert!((result.total_duration_ms - expected_ms).abs() < 1.0);
}

#[test]
fn test_very_small_sample_rate() {
    let durations = [1.0_f32];
    let tokens: Vec<String> = vec!["p".to_string()];
    let sr = 100; // very small
    let hop = 10;

    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    // 1 frame * (10 / 100) * 1000 = 100 ms
    assert!((result.phonemes[0].duration_ms - 100.0).abs() < 1e-6);
}

#[test]
fn test_default_hop_length_value() {
    assert_eq!(DEFAULT_HOP_LENGTH, 256);
}

// =========================================================================
// 3. JSON output
// =========================================================================

#[test]
fn test_to_json_produces_valid_json() {
    let durations = [5.0_f32, 10.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let json_str = result.to_json().unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
    assert!(parsed.is_object(), "JSON root should be an object");
}

#[test]
fn test_to_json_contains_all_fields() {
    let durations = [5.0_f32, 10.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let json_str = result.to_json().unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();

    // Top-level fields
    assert!(parsed.get("total_duration_ms").is_some());
    assert!(parsed.get("sample_rate").is_some());
    assert!(parsed.get("phonemes").is_some());

    // Phoneme fields
    let phonemes = parsed["phonemes"].as_array().unwrap();
    assert_eq!(phonemes.len(), 2);
    for ph in phonemes {
        assert!(ph.get("phoneme").is_some());
        assert!(ph.get("start_ms").is_some());
        assert!(ph.get("end_ms").is_some());
        assert!(ph.get("duration_ms").is_some());
    }
}

#[test]
fn test_to_json_phoneme_values_match() {
    let durations = [10.0_f32];
    let tokens: Vec<String> = vec!["k".to_string()];
    let sr = 22050;
    let hop = DEFAULT_HOP_LENGTH;
    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    let json_str = result.to_json().unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();

    let ph = &parsed["phonemes"][0];
    assert_eq!(ph["phoneme"].as_str().unwrap(), "k");
    assert!((ph["start_ms"].as_f64().unwrap() - 0.0).abs() < 1e-6);

    let expected_dur = 10.0 * frame_ms(sr, hop);
    assert!((ph["duration_ms"].as_f64().unwrap() - expected_dur).abs() < 1e-3);
    assert!((ph["end_ms"].as_f64().unwrap() - expected_dur).abs() < 1e-3);
}

#[test]
fn test_to_json_compact_produces_valid_json() {
    let durations = [3.0_f32, 7.0, 2.0];
    let tokens: Vec<String> = vec!["x", "y", "z"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let compact = result.to_json_compact().unwrap();
    // Should be valid JSON
    let parsed: serde_json::Value = serde_json::from_str(&compact).unwrap();
    assert!(parsed.is_object());
}

#[test]
fn test_to_json_compact_no_indentation() {
    let durations = [5.0_f32];
    let tokens: Vec<String> = vec!["p".to_string()];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let compact = result.to_json_compact().unwrap();
    // Compact JSON should not contain newlines followed by spaces (indentation)
    assert!(
        !compact.contains("\n  "),
        "compact JSON should not have indented newlines"
    );
}

#[test]
fn test_json_roundtrip_field_preservation() {
    let durations = [4.0_f32, 8.0, 6.0];
    let tokens: Vec<String> = vec!["s", "t", "u"].into_iter().map(String::from).collect();
    let sr = 22050;
    let hop = DEFAULT_HOP_LENGTH;
    let result = durations_to_timing(&durations, &tokens, sr, hop).unwrap();

    let json_str = result.to_json().unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();

    // Verify sample_rate
    assert_eq!(parsed["sample_rate"].as_u64().unwrap(), sr as u64);

    // Verify total_duration_ms matches sum
    let total = parsed["total_duration_ms"].as_f64().unwrap();
    let phonemes = parsed["phonemes"].as_array().unwrap();
    let sum: f64 = phonemes
        .iter()
        .map(|p| p["duration_ms"].as_f64().unwrap())
        .sum();
    assert!((total - sum).abs() < 1e-3);

    // Verify phoneme names preserved in order
    let names: Vec<&str> = phonemes
        .iter()
        .map(|p| p["phoneme"].as_str().unwrap())
        .collect();
    assert_eq!(names, vec!["s", "t", "u"]);
}

// =========================================================================
// 4. TSV output
// =========================================================================

#[test]
fn test_tsv_header_row() {
    let durations = [5.0_f32];
    let tokens: Vec<String> = vec!["a".to_string()];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let tsv = result.to_tsv();
    let first_line = tsv.lines().next().unwrap();
    assert_eq!(first_line, "start_ms\tend_ms\tduration_ms\tphoneme");
}

#[test]
fn test_tsv_correct_number_of_data_rows() {
    let n = 4;
    let durations = vec![5.0_f32; n];
    let tokens: Vec<String> = (0..n).map(|i| format!("p{}", i)).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let tsv = result.to_tsv();
    let lines: Vec<&str> = tsv.lines().collect();
    // 1 header + n data rows
    assert_eq!(lines.len(), n + 1);
}

#[test]
fn test_tsv_tab_separated() {
    let durations = [10.0_f32, 20.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let tsv = result.to_tsv();
    for line in tsv.lines() {
        let cols: Vec<&str> = line.split('\t').collect();
        assert_eq!(cols.len(), 4, "each TSV row should have exactly 4 columns");
    }
}

#[test]
fn test_tsv_numeric_values_parseable() {
    let durations = [10.0_f32, 20.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let tsv = result.to_tsv();
    // Skip header, parse numeric columns
    for line in tsv.lines().skip(1) {
        let cols: Vec<&str> = line.split('\t').collect();
        let _start: f64 = cols[0].parse().expect("start_ms should be numeric");
        let _end: f64 = cols[1].parse().expect("end_ms should be numeric");
        let _dur: f64 = cols[2].parse().expect("duration_ms should be numeric");
        // cols[3] is the phoneme string, no parse needed
    }
}

// =========================================================================
// 5. SRT output
// =========================================================================

#[test]
fn test_srt_sequential_numbering() {
    let durations = [5.0_f32, 10.0, 15.0];
    let tokens: Vec<String> = vec!["a", "b", "c"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let srt = result.to_srt();
    let lines: Vec<&str> = srt.lines().collect();

    // SRT format: index, timestamp, text, blank line
    // First entry index
    assert_eq!(lines[0].trim(), "1");
    // Find second entry
    let second_idx = lines
        .iter()
        .position(|l| l.trim() == "2")
        .expect("should have entry 2");
    assert!(second_idx > 0);
    // Find third entry
    let third_idx = lines
        .iter()
        .position(|l| l.trim() == "3")
        .expect("should have entry 3");
    assert!(third_idx > second_idx);
}

#[test]
fn test_srt_timestamp_format() {
    let durations = [10.0_f32];
    let tokens: Vec<String> = vec!["a".to_string()];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let srt = result.to_srt();
    let lines: Vec<&str> = srt.lines().collect();

    // Second line should be the timestamp line: "HH:MM:SS,mmm --> HH:MM:SS,mmm"
    let timestamp_line = lines[1];
    assert!(
        timestamp_line.contains("-->"),
        "timestamp line should contain '-->'"
    );

    let parts: Vec<&str> = timestamp_line.split(" --> ").collect();
    assert_eq!(parts.len(), 2, "should have start and end timestamps");

    // Verify HH:MM:SS,mmm format
    for part in &parts {
        let trimmed = part.trim();
        // Pattern: DD:DD:DD,DDD
        let segments: Vec<&str> = trimmed.split(',').collect();
        assert_eq!(segments.len(), 2, "timestamp should have comma separator");
        let hms: Vec<&str> = segments[0].split(':').collect();
        assert_eq!(hms.len(), 3, "should have HH:MM:SS");
        // Milliseconds part
        assert_eq!(segments[1].len(), 3, "milliseconds should be 3 digits");
    }
}

#[test]
fn test_srt_blank_lines_between_entries() {
    let durations = [5.0_f32, 10.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let srt = result.to_srt();

    // SRT entries should be separated by blank lines.
    // After the first entry (index, timestamp, text), there should be a blank line.
    let lines: Vec<&str> = srt.lines().collect();

    // Find the blank line(s) between entries
    let blank_positions: Vec<usize> = lines
        .iter()
        .enumerate()
        .filter(|(_, l)| l.trim().is_empty())
        .map(|(i, _)| i)
        .collect();

    assert!(
        !blank_positions.is_empty(),
        "SRT should have blank lines between entries"
    );
}

// =========================================================================
// 6. Timing accuracy / invariants
// =========================================================================

#[test]
fn test_total_duration_equals_sum_of_individual() {
    let durations = [3.0_f32, 7.0, 11.0, 2.0, 5.0];
    let tokens: Vec<String> = (0..5).map(|i| format!("p{}", i)).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let sum: f64 = result.phonemes.iter().map(|p| p.duration_ms).sum();
    assert!(
        (result.total_duration_ms - sum).abs() < 1e-6,
        "total ({}) != sum of durations ({})",
        result.total_duration_ms,
        sum
    );
}

#[test]
fn test_end_of_phoneme_i_equals_start_of_phoneme_i_plus_1() {
    let durations = [4.0_f32, 9.0, 6.0, 3.0];
    let tokens: Vec<String> = vec!["a", "b", "c", "d"]
        .into_iter()
        .map(String::from)
        .collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    for i in 0..result.phonemes.len() - 1 {
        assert!(
            (result.phonemes[i].end_ms - result.phonemes[i + 1].start_ms).abs() < 1e-6,
            "end of phoneme {} ({}) != start of phoneme {} ({})",
            i,
            result.phonemes[i].end_ms,
            i + 1,
            result.phonemes[i + 1].start_ms
        );
    }
}

#[test]
fn test_first_phoneme_starts_at_zero() {
    let durations = [8.0_f32, 12.0];
    let tokens: Vec<String> = vec!["a", "b"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    assert!(
        (result.phonemes[0].start_ms - 0.0).abs() < 1e-6,
        "first phoneme should start at 0.0, got {}",
        result.phonemes[0].start_ms
    );
}

#[test]
fn test_last_phoneme_end_equals_total_duration() {
    let durations = [6.0_f32, 14.0, 3.0];
    let tokens: Vec<String> = vec!["a", "b", "c"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let last = result.phonemes.last().unwrap();
    assert!(
        (last.end_ms - result.total_duration_ms).abs() < 1e-6,
        "last phoneme end ({}) != total_duration_ms ({})",
        last.end_ms,
        result.total_duration_ms
    );
}

#[test]
fn test_all_durations_non_negative() {
    let durations = [0.0_f32, 5.0, 0.0, 10.0, 0.0];
    let tokens: Vec<String> = (0..5).map(|i| format!("p{}", i)).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    for (i, ph) in result.phonemes.iter().enumerate() {
        assert!(
            ph.duration_ms >= 0.0,
            "phoneme {} has negative duration: {}",
            i,
            ph.duration_ms
        );
        assert!(
            ph.start_ms >= 0.0,
            "phoneme {} has negative start: {}",
            i,
            ph.start_ms
        );
        assert!(
            ph.end_ms >= 0.0,
            "phoneme {} has negative end: {}",
            i,
            ph.end_ms
        );
    }
}

#[test]
fn test_monotonically_increasing_timestamps() {
    let durations = [3.0_f32, 7.0, 1.0, 12.0, 5.0, 2.0];
    let tokens: Vec<String> = (0..6).map(|i| format!("p{}", i)).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    for i in 1..result.phonemes.len() {
        assert!(
            result.phonemes[i].start_ms >= result.phonemes[i - 1].start_ms,
            "start times should be monotonically increasing: phoneme {} start ({}) < phoneme {} start ({})",
            i,
            result.phonemes[i].start_ms,
            i - 1,
            result.phonemes[i - 1].start_ms
        );
    }
}

#[test]
fn test_different_sample_rates_produce_different_timings() {
    let durations = [10.0_f32];
    let tokens: Vec<String> = vec!["a".to_string()];
    let hop = DEFAULT_HOP_LENGTH;

    let r1 = durations_to_timing(&durations, &tokens, 16000, hop).unwrap();
    let r2 = durations_to_timing(&durations, &tokens, 22050, hop).unwrap();

    // Higher sample rate -> shorter duration for the same number of frames
    assert!(
        r1.phonemes[0].duration_ms > r2.phonemes[0].duration_ms,
        "16kHz ({} ms) should produce longer duration than 22050Hz ({} ms)",
        r1.phonemes[0].duration_ms,
        r2.phonemes[0].duration_ms
    );
}

#[test]
fn test_phoneme_names_preserved() {
    let durations = [1.0_f32, 1.0, 1.0];
    let tokens: Vec<String> = vec!["^", "a", "$"].into_iter().map(String::from).collect();
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    assert_eq!(result.phonemes[0].phoneme, "^");
    assert_eq!(result.phonemes[1].phoneme, "a");
    assert_eq!(result.phonemes[2].phoneme, "$");
}

#[test]
fn test_empty_json_output() {
    let durations: Vec<f32> = vec![];
    let tokens: Vec<String> = vec![];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let json_str = result.to_json().unwrap();
    let parsed: serde_json::Value = serde_json::from_str(&json_str).unwrap();
    let phonemes = parsed["phonemes"].as_array().unwrap();
    assert!(phonemes.is_empty());
    assert!((parsed["total_duration_ms"].as_f64().unwrap() - 0.0).abs() < 1e-6);
}

#[test]
fn test_empty_tsv_output() {
    let durations: Vec<f32> = vec![];
    let tokens: Vec<String> = vec![];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let tsv = result.to_tsv();
    let lines: Vec<&str> = tsv.lines().collect();
    // Should have header only
    assert_eq!(lines.len(), 1);
    assert_eq!(lines[0], "start_ms\tend_ms\tduration_ms\tphoneme");
}

#[test]
fn test_empty_srt_output() {
    let durations: Vec<f32> = vec![];
    let tokens: Vec<String> = vec![];
    let result = durations_to_timing(&durations, &tokens, 22050, DEFAULT_HOP_LENGTH).unwrap();

    let srt = result.to_srt();
    assert!(
        srt.trim().is_empty(),
        "empty input should produce empty SRT"
    );
}
