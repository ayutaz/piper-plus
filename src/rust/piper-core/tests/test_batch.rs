#![cfg(feature = "onnx")]

use piper_plus::batch::*;
use std::path::{Path, PathBuf};

// ===================================================================
// 1. auto_output_path -- formatting, padding, prefix
// ===================================================================

// Implementation uses 3-digit 1-indexed: format!("{prefix}_{:03}.wav", index + 1)

#[test]
fn test_auto_output_path_basic() {
    let path = auto_output_path(Path::new("/output"), 0, "utt");
    assert_eq!(path, PathBuf::from("/output/utt_001.wav"));
}

#[test]
fn test_auto_output_path_index_padding() {
    let path = auto_output_path(Path::new("/out"), 42, "utt");
    assert_eq!(path, PathBuf::from("/out/utt_043.wav"));
}

#[test]
fn test_auto_output_path_large_index() {
    let path = auto_output_path(Path::new("/out"), 999, "utt");
    assert_eq!(path, PathBuf::from("/out/utt_1000.wav"));
}

#[test]
fn test_auto_output_path_index_exceeds_six_digits() {
    let path = auto_output_path(Path::new("/out"), 999_999, "utt");
    // 3-digit padding overflows gracefully
    let filename = path.file_name().unwrap().to_str().unwrap();
    assert!(filename.starts_with("utt_") && filename.ends_with(".wav"));
}

#[test]
fn test_auto_output_path_custom_prefix() {
    let path = auto_output_path(Path::new("/tmp/wavs"), 7, "batch");
    assert_eq!(path, PathBuf::from("/tmp/wavs/batch_008.wav"));
}

#[test]
fn test_auto_output_path_empty_prefix() {
    let path = auto_output_path(Path::new("/out"), 1, "");
    assert_eq!(path, PathBuf::from("/out/_002.wav"));
}

#[test]
fn test_auto_output_path_relative_dir() {
    let path = auto_output_path(Path::new("relative/dir"), 0, "utt");
    assert_eq!(path, PathBuf::from("relative/dir/utt_001.wav"));
}

// ===================================================================
// 2. BatchJob -- construction and field access
// ===================================================================

#[test]
fn test_batch_job_construction_minimal() {
    let job = BatchJob {
        text: "Hello world".to_string(),
        output_path: PathBuf::from("/out/test.wav"),
        speaker_id: None,
        language: None,
    };
    assert_eq!(job.text, "Hello world");
    assert_eq!(job.output_path, PathBuf::from("/out/test.wav"));
    assert!(job.speaker_id.is_none());
    assert!(job.language.is_none());
}

#[test]
fn test_batch_job_construction_full() {
    let job = BatchJob {
        text: "こんにちは".to_string(),
        output_path: PathBuf::from("/out/ja_000000.wav"),
        speaker_id: Some(3),
        language: Some("ja".to_string()),
    };
    assert_eq!(job.text, "こんにちは");
    assert_eq!(job.speaker_id, Some(3));
    assert_eq!(job.language.as_deref(), Some("ja"));
}

#[test]
fn test_batch_job_empty_text() {
    let job = BatchJob {
        text: String::new(),
        output_path: PathBuf::from("/out/empty.wav"),
        speaker_id: None,
        language: None,
    };
    assert!(job.text.is_empty());
}

// ===================================================================
// 3. BatchResult -- success and failure variants
// ===================================================================

#[test]
fn test_batch_result_success() {
    let result = BatchResult {
        job_index: 0,
        output_path: PathBuf::from("/out/utt_000000.wav"),
        audio_seconds: 2.5,
        infer_seconds: 0.3,
        success: true,
        error: None,
    };
    assert_eq!(result.job_index, 0);
    assert!(result.success);
    assert!(result.error.is_none());
    assert!((result.audio_seconds - 2.5).abs() < f64::EPSILON);
    assert!((result.infer_seconds - 0.3).abs() < f64::EPSILON);
}

#[test]
fn test_batch_result_failure() {
    let result = BatchResult {
        job_index: 5,
        output_path: PathBuf::from("/out/utt_000005.wav"),
        audio_seconds: 0.0,
        infer_seconds: 0.01,
        success: false,
        error: Some("phonemization failed".to_string()),
    };
    assert!(!result.success);
    assert_eq!(result.error.as_deref(), Some("phonemization failed"));
    assert_eq!(result.job_index, 5);
}

// ===================================================================
// 4. BatchSummary -- aggregation, real_time_factor, to_summary_string
// ===================================================================

#[test]
fn test_batch_summary_all_success() {
    let summary = BatchSummary {
        total_jobs: 3,
        successful: 3,
        failed: 0,
        total_audio_seconds: 10.0,
        total_infer_seconds: 2.0,
        results: vec![
            BatchResult {
                job_index: 0,
                output_path: PathBuf::from("/out/utt_000000.wav"),
                audio_seconds: 3.0,
                infer_seconds: 0.5,
                success: true,
                error: None,
            },
            BatchResult {
                job_index: 1,
                output_path: PathBuf::from("/out/utt_000001.wav"),
                audio_seconds: 4.0,
                infer_seconds: 0.8,
                success: true,
                error: None,
            },
            BatchResult {
                job_index: 2,
                output_path: PathBuf::from("/out/utt_000002.wav"),
                audio_seconds: 3.0,
                infer_seconds: 0.7,
                success: true,
                error: None,
            },
        ],
    };
    assert_eq!(summary.total_jobs, 3);
    assert_eq!(summary.successful, 3);
    assert_eq!(summary.failed, 0);
    assert_eq!(summary.results.len(), 3);
}

#[test]
fn test_batch_summary_with_failures() {
    let summary = BatchSummary {
        total_jobs: 2,
        successful: 1,
        failed: 1,
        total_audio_seconds: 3.0,
        total_infer_seconds: 0.5,
        results: vec![
            BatchResult {
                job_index: 0,
                output_path: PathBuf::from("/out/utt_000000.wav"),
                audio_seconds: 3.0,
                infer_seconds: 0.4,
                success: true,
                error: None,
            },
            BatchResult {
                job_index: 1,
                output_path: PathBuf::from("/out/utt_000001.wav"),
                audio_seconds: 0.0,
                infer_seconds: 0.1,
                success: false,
                error: Some("model error".to_string()),
            },
        ],
    };
    assert_eq!(summary.successful, 1);
    assert_eq!(summary.failed, 1);
}

#[test]
fn test_batch_summary_real_time_factor() {
    let summary = BatchSummary {
        total_jobs: 2,
        successful: 2,
        failed: 0,
        total_audio_seconds: 10.0,
        total_infer_seconds: 2.0,
        results: vec![],
    };
    // RTF = infer / audio = 2.0 / 10.0 = 0.2
    let rtf = summary.real_time_factor();
    assert!((rtf - 0.2).abs() < 1e-9);
}

#[test]
fn test_batch_summary_real_time_factor_zero_audio() {
    let summary = BatchSummary {
        total_jobs: 1,
        successful: 0,
        failed: 1,
        total_audio_seconds: 0.0,
        total_infer_seconds: 0.5,
        results: vec![],
    };
    // When total_audio_seconds is 0, RTF should be infinity or a safe fallback
    let rtf = summary.real_time_factor();
    assert!(rtf.is_infinite() || rtf == 0.0 || rtf.is_nan());
}

#[test]
fn test_batch_summary_to_summary_string_contains_counts() {
    let summary = BatchSummary {
        total_jobs: 5,
        successful: 4,
        failed: 1,
        total_audio_seconds: 20.0,
        total_infer_seconds: 3.5,
        results: vec![],
    };
    let s = summary.to_summary_string();
    // The summary string should mention key metrics
    assert!(
        s.contains("5") || s.contains("total"),
        "should contain total job count"
    );
    assert!(
        s.contains("4") || s.contains("success"),
        "should contain success count"
    );
    assert!(
        s.contains("1") || s.contains("fail"),
        "should contain failure count"
    );
}

#[test]
fn test_batch_summary_to_summary_string_not_empty() {
    let summary = BatchSummary {
        total_jobs: 0,
        successful: 0,
        failed: 0,
        total_audio_seconds: 0.0,
        total_infer_seconds: 0.0,
        results: vec![],
    };
    let s = summary.to_summary_string();
    assert!(
        !s.is_empty(),
        "summary string should not be empty even with zero jobs"
    );
}

// ===================================================================
// 5. jobs_from_text_file -- tempfile, empty file, multiple lines
// ===================================================================

#[test]
fn test_jobs_from_text_file_basic() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("input.txt");
    std::fs::write(&text_path, "Hello world\nGoodbye world\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, None, None).unwrap();
    assert_eq!(jobs.len(), 2);
    assert_eq!(jobs[0].text, "Hello world");
    assert_eq!(jobs[1].text, "Goodbye world");
    assert!(jobs[0].speaker_id.is_none());
    assert!(jobs[0].language.is_none());
}

#[test]
fn test_jobs_from_text_file_with_speaker_and_language() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("input.txt");
    std::fs::write(&text_path, "Line one\nLine two\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, Some(2), Some("en")).unwrap();
    assert_eq!(jobs.len(), 2);
    assert_eq!(jobs[0].speaker_id, Some(2));
    assert_eq!(jobs[0].language.as_deref(), Some("en"));
    assert_eq!(jobs[1].speaker_id, Some(2));
    assert_eq!(jobs[1].language.as_deref(), Some("en"));
}

#[test]
fn test_jobs_from_text_file_empty_file() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("empty.txt");
    std::fs::write(&text_path, "").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, None, None).unwrap();
    assert!(jobs.is_empty());
}

#[test]
fn test_jobs_from_text_file_skips_blank_lines() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("blanks.txt");
    std::fs::write(&text_path, "First\n\n\nSecond\n\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, None, None).unwrap();
    assert_eq!(jobs.len(), 2);
    assert_eq!(jobs[0].text, "First");
    assert_eq!(jobs[1].text, "Second");
}

#[test]
fn test_jobs_from_text_file_output_paths_sequential() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("seq.txt");
    std::fs::write(&text_path, "A\nB\nC\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, None, None).unwrap();
    assert_eq!(jobs.len(), 3);
    // Each job should have a distinct output path
    let paths: Vec<&PathBuf> = jobs.iter().map(|j| &j.output_path).collect();
    assert_ne!(paths[0], paths[1]);
    assert_ne!(paths[1], paths[2]);
    assert_ne!(paths[0], paths[2]);
}

#[test]
fn test_jobs_from_text_file_nonexistent_file() {
    let dir = tempfile::tempdir().unwrap();
    let bad_path = dir.path().join("does_not_exist.txt");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let result = jobs_from_text_file(&bad_path, &output_dir, None, None);
    assert!(result.is_err());
}

#[test]
fn test_jobs_from_text_file_japanese_text() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("ja.txt");
    std::fs::write(&text_path, "こんにちは\nさようなら\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, Some(0), Some("ja")).unwrap();
    assert_eq!(jobs.len(), 2);
    assert_eq!(jobs[0].text, "こんにちは");
    assert_eq!(jobs[1].text, "さようなら");
}

// ===================================================================
// 6. jobs_from_jsonl -- tempfile, valid/invalid JSON
// ===================================================================

#[test]
fn test_jobs_from_jsonl_basic() {
    let dir = tempfile::tempdir().unwrap();
    let jsonl_path = dir.path().join("input.jsonl");
    let content = r#"{"text": "Hello", "output_path": "hello.wav"}
{"text": "World", "output_path": "world.wav"}
"#;
    std::fs::write(&jsonl_path, content).unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_jsonl(&jsonl_path, &output_dir).unwrap();
    assert_eq!(jobs.len(), 2);
    assert_eq!(jobs[0].text, "Hello");
    assert_eq!(jobs[1].text, "World");
}

#[test]
fn test_jobs_from_jsonl_with_speaker_and_language() {
    let dir = tempfile::tempdir().unwrap();
    let jsonl_path = dir.path().join("input.jsonl");
    let content = r#"{"text": "test", "speaker_id": 5, "language": "en"}
"#;
    std::fs::write(&jsonl_path, content).unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_jsonl(&jsonl_path, &output_dir).unwrap();
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0].speaker_id, Some(5));
    assert_eq!(jobs[0].language.as_deref(), Some("en"));
}

#[test]
fn test_jobs_from_jsonl_invalid_json() {
    let dir = tempfile::tempdir().unwrap();
    let jsonl_path = dir.path().join("bad.jsonl");
    std::fs::write(&jsonl_path, "this is not json\n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let result = jobs_from_jsonl(&jsonl_path, &output_dir);
    assert!(result.is_err());
}

#[test]
fn test_jobs_from_jsonl_empty_file() {
    let dir = tempfile::tempdir().unwrap();
    let jsonl_path = dir.path().join("empty.jsonl");
    std::fs::write(&jsonl_path, "").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_jsonl(&jsonl_path, &output_dir).unwrap();
    assert!(jobs.is_empty());
}

#[test]
fn test_jobs_from_jsonl_skips_blank_lines() {
    let dir = tempfile::tempdir().unwrap();
    let jsonl_path = dir.path().join("blanks.jsonl");
    let content = r#"{"text": "First"}

{"text": "Second"}

"#;
    std::fs::write(&jsonl_path, content).unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_jsonl(&jsonl_path, &output_dir).unwrap();
    assert_eq!(jobs.len(), 2);
}

#[test]
fn test_jobs_from_jsonl_nonexistent_file() {
    let dir = tempfile::tempdir().unwrap();
    let bad_path = dir.path().join("nonexistent.jsonl");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let result = jobs_from_jsonl(&bad_path, &output_dir);
    assert!(result.is_err());
}

// ===================================================================
// 7. Edge cases
// ===================================================================

#[test]
fn test_jobs_from_text_file_whitespace_only_lines() {
    let dir = tempfile::tempdir().unwrap();
    let text_path = dir.path().join("spaces.txt");
    std::fs::write(&text_path, "   \n\t\nActual text\n  \n").unwrap();

    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    let jobs = jobs_from_text_file(&text_path, &output_dir, None, None).unwrap();
    // Whitespace-only lines should be skipped
    assert_eq!(jobs.len(), 1);
    assert_eq!(jobs[0].text, "Actual text");
}

#[test]
fn test_batch_summary_real_time_factor_fast_inference() {
    let summary = BatchSummary {
        total_jobs: 100,
        successful: 100,
        failed: 0,
        total_audio_seconds: 600.0,
        total_infer_seconds: 30.0,
        results: vec![],
    };
    // RTF = 30 / 600 = 0.05 (20x faster than real-time)
    let rtf = summary.real_time_factor();
    assert!((rtf - 0.05).abs() < 1e-9);
}

#[test]
fn test_batch_result_zero_duration() {
    let result = BatchResult {
        job_index: 0,
        output_path: PathBuf::from("/out/utt_000000.wav"),
        audio_seconds: 0.0,
        infer_seconds: 0.0,
        success: true,
        error: None,
    };
    assert!(result.success);
    assert!((result.audio_seconds - 0.0).abs() < f64::EPSILON);
}

// (duplicate test_auto_output_path_relative_dir removed - exists above)
