//! Batch synthesis for processing multiple texts.
//!
//! Process a list of texts sequentially, producing one WAV per text.
//! Useful for batch processing scripts, audiobook generation, etc.

use std::fs;
use std::io::BufRead;
use std::path::{Path, PathBuf};

use crate::error::PiperError;

/// A single synthesis job in a batch
#[derive(Debug, Clone)]
pub struct BatchJob {
    pub text: String,
    pub output_path: PathBuf,
    pub speaker_id: Option<i64>,
    pub language: Option<String>,
}

/// Batch synthesis result for a single job
#[derive(Debug, Clone)]
pub struct BatchResult {
    pub job_index: usize,
    pub output_path: PathBuf,
    pub audio_seconds: f64,
    pub infer_seconds: f64,
    pub success: bool,
    pub error: Option<String>,
}

/// Summary of a batch synthesis run
#[derive(Debug, Clone)]
pub struct BatchSummary {
    pub total_jobs: usize,
    pub successful: usize,
    pub failed: usize,
    pub total_audio_seconds: f64,
    pub total_infer_seconds: f64,
    pub results: Vec<BatchResult>,
}

impl BatchSummary {
    /// Compute summary from a list of results.
    pub fn from_results(results: Vec<BatchResult>) -> Self {
        let total_jobs = results.len();
        let successful = results.iter().filter(|r| r.success).count();
        let failed = total_jobs - successful;
        let total_audio_seconds: f64 = results.iter().map(|r| r.audio_seconds).sum();
        let total_infer_seconds: f64 = results.iter().map(|r| r.infer_seconds).sum();

        Self {
            total_jobs,
            successful,
            failed,
            total_audio_seconds,
            total_infer_seconds,
            results,
        }
    }

    /// Overall real-time factor (infer_seconds / audio_seconds).
    /// Returns 0.0 if no audio was produced.
    pub fn real_time_factor(&self) -> f64 {
        if self.total_audio_seconds > 0.0 {
            self.total_infer_seconds / self.total_audio_seconds
        } else {
            0.0
        }
    }

    /// Format as human-readable summary string.
    pub fn to_summary_string(&self) -> String {
        format!(
            "Batch complete: {}/{} succeeded, {} failed | audio {:.2}s, infer {:.2}s, RTF {:.3}",
            self.successful,
            self.total_jobs,
            self.failed,
            self.total_audio_seconds,
            self.total_infer_seconds,
            self.real_time_factor(),
        )
    }
}

/// Progress callback for batch processing.
///
/// Called after each job completes with (job_index, total_jobs, result).
pub type BatchProgressCallback = Box<dyn Fn(usize, usize, &BatchResult) + Send>;

/// Auto-generate output filename from job index.
///
/// Produces paths like `output_dir/prefix_001.wav` with zero-padded 3-digit index.
pub fn auto_output_path(output_dir: &Path, index: usize, prefix: &str) -> PathBuf {
    output_dir.join(format!("{prefix}_{:03}.wav", index + 1))
}

/// Build batch jobs from a text file (one line = one utterance).
///
/// Each non-empty line becomes a job. Output paths are auto-generated as
/// `output_dir/utt_001.wav`, `utt_002.wav`, etc. Empty lines are skipped.
pub fn jobs_from_text_file(
    text_file: &Path,
    output_dir: &Path,
    speaker_id: Option<i64>,
    language: Option<&str>,
) -> Result<Vec<BatchJob>, PiperError> {
    let content = fs::read_to_string(text_file)?;
    let mut jobs = Vec::new();
    let mut index = 0usize;

    for line in content.lines() {
        let text = line.trim().to_string();
        if text.is_empty() {
            continue;
        }
        jobs.push(BatchJob {
            text,
            output_path: auto_output_path(output_dir, index, "utt"),
            speaker_id,
            language: language.map(|s| s.to_string()),
        });
        index += 1;
    }

    Ok(jobs)
}

/// JSONL line schema for batch jobs.
///
/// Each line must have a "text" field. Optional fields: "speaker_id",
/// "language", "output_file".
#[derive(serde::Deserialize)]
struct BatchJsonlLine {
    text: String,
    #[serde(default)]
    speaker_id: Option<i64>,
    #[serde(default)]
    language: Option<String>,
    #[serde(default)]
    output_file: Option<String>,
}

/// Build batch jobs from a JSONL file.
///
/// Each line is a JSON object with a required "text" field and optional
/// "speaker_id", "language", and "output_file" fields. When "output_file"
/// is absent, output paths are auto-generated as `output_dir/utt_001.wav`.
pub fn jobs_from_jsonl(jsonl_path: &Path, output_dir: &Path) -> Result<Vec<BatchJob>, PiperError> {
    let file = fs::File::open(jsonl_path)?;
    let reader = std::io::BufReader::new(file);
    let mut jobs = Vec::new();
    let mut auto_index = 0usize;

    for (line_no, line_result) in reader.lines().enumerate() {
        let line = line_result?;
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        let parsed: BatchJsonlLine =
            serde_json::from_str(trimmed).map_err(|e| PiperError::InvalidConfig {
                reason: format!("JSONL line {}: {}", line_no + 1, e),
            })?;

        let output_path = if let Some(ref filename) = parsed.output_file {
            output_dir.join(filename)
        } else {
            auto_output_path(output_dir, auto_index, "utt")
        };

        jobs.push(BatchJob {
            text: parsed.text,
            output_path,
            speaker_id: parsed.speaker_id,
            language: parsed.language,
        });
        auto_index += 1;
    }

    Ok(jobs)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    // -----------------------------------------------------------------------
    // 1. auto_output_path formatting
    // -----------------------------------------------------------------------
    #[test]
    fn test_auto_output_path_basic() {
        let p = auto_output_path(Path::new("/tmp/out"), 0, "utt");
        assert_eq!(p, PathBuf::from("/tmp/out/utt_001.wav"));
    }

    #[test]
    fn test_auto_output_path_double_digit() {
        let p = auto_output_path(Path::new("/tmp/out"), 9, "utt");
        assert_eq!(p, PathBuf::from("/tmp/out/utt_010.wav"));
    }

    #[test]
    fn test_auto_output_path_triple_digit() {
        let p = auto_output_path(Path::new("/tmp/out"), 99, "utt");
        assert_eq!(p, PathBuf::from("/tmp/out/utt_100.wav"));
    }

    #[test]
    fn test_auto_output_path_large_index() {
        // Index beyond 999 should still work (4+ digits)
        let p = auto_output_path(Path::new("/out"), 999, "batch");
        assert_eq!(p, PathBuf::from("/out/batch_1000.wav"));
    }

    #[test]
    fn test_auto_output_path_custom_prefix() {
        let p = auto_output_path(Path::new("/data"), 4, "chapter");
        assert_eq!(p, PathBuf::from("/data/chapter_005.wav"));
    }

    // -----------------------------------------------------------------------
    // 2. BatchJob construction
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_job_construction() {
        let job = BatchJob {
            text: "Hello world".to_string(),
            output_path: PathBuf::from("/tmp/out.wav"),
            speaker_id: Some(3),
            language: Some("en".to_string()),
        };
        assert_eq!(job.text, "Hello world");
        assert_eq!(job.output_path, PathBuf::from("/tmp/out.wav"));
        assert_eq!(job.speaker_id, Some(3));
        assert_eq!(job.language.as_deref(), Some("en"));
    }

    #[test]
    fn test_batch_job_no_optional_fields() {
        let job = BatchJob {
            text: "Test".to_string(),
            output_path: PathBuf::from("/tmp/test.wav"),
            speaker_id: None,
            language: None,
        };
        assert!(job.speaker_id.is_none());
        assert!(job.language.is_none());
    }

    #[test]
    fn test_batch_job_clone() {
        let job = BatchJob {
            text: "Clone me".to_string(),
            output_path: PathBuf::from("/tmp/clone.wav"),
            speaker_id: Some(1),
            language: Some("ja".to_string()),
        };
        let cloned = job.clone();
        assert_eq!(cloned.text, job.text);
        assert_eq!(cloned.output_path, job.output_path);
        assert_eq!(cloned.speaker_id, job.speaker_id);
        assert_eq!(cloned.language, job.language);
    }

    // -----------------------------------------------------------------------
    // 3. BatchResult success/failure
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_result_success() {
        let result = BatchResult {
            job_index: 0,
            output_path: PathBuf::from("/tmp/utt_001.wav"),
            audio_seconds: 2.5,
            infer_seconds: 0.3,
            success: true,
            error: None,
        };
        assert!(result.success);
        assert!(result.error.is_none());
        assert!((result.audio_seconds - 2.5).abs() < 1e-6);
    }

    #[test]
    fn test_batch_result_failure() {
        let result = BatchResult {
            job_index: 5,
            output_path: PathBuf::from("/tmp/utt_006.wav"),
            audio_seconds: 0.0,
            infer_seconds: 0.0,
            success: false,
            error: Some("phonemization failed".to_string()),
        };
        assert!(!result.success);
        assert_eq!(result.error.as_deref(), Some("phonemization failed"));
        assert_eq!(result.job_index, 5);
    }

    // -----------------------------------------------------------------------
    // 4. BatchSummary aggregation
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_summary_from_results() {
        let results = vec![
            BatchResult {
                job_index: 0,
                output_path: PathBuf::from("/tmp/utt_001.wav"),
                audio_seconds: 2.0,
                infer_seconds: 0.4,
                success: true,
                error: None,
            },
            BatchResult {
                job_index: 1,
                output_path: PathBuf::from("/tmp/utt_002.wav"),
                audio_seconds: 0.0,
                infer_seconds: 0.0,
                success: false,
                error: Some("error".to_string()),
            },
            BatchResult {
                job_index: 2,
                output_path: PathBuf::from("/tmp/utt_003.wav"),
                audio_seconds: 3.0,
                infer_seconds: 0.6,
                success: true,
                error: None,
            },
        ];

        let summary = BatchSummary::from_results(results);
        assert_eq!(summary.total_jobs, 3);
        assert_eq!(summary.successful, 2);
        assert_eq!(summary.failed, 1);
        assert!((summary.total_audio_seconds - 5.0).abs() < 1e-6);
        assert!((summary.total_infer_seconds - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_batch_summary_real_time_factor() {
        let summary = BatchSummary {
            total_jobs: 2,
            successful: 2,
            failed: 0,
            total_audio_seconds: 10.0,
            total_infer_seconds: 2.0,
            results: Vec::new(),
        };
        assert!((summary.real_time_factor() - 0.2).abs() < 1e-6);
    }

    #[test]
    fn test_batch_summary_real_time_factor_zero_audio() {
        let summary = BatchSummary {
            total_jobs: 1,
            successful: 0,
            failed: 1,
            total_audio_seconds: 0.0,
            total_infer_seconds: 0.1,
            results: Vec::new(),
        };
        assert!((summary.real_time_factor()).abs() < 1e-6);
    }

    #[test]
    fn test_batch_summary_to_summary_string() {
        let summary = BatchSummary {
            total_jobs: 10,
            successful: 8,
            failed: 2,
            total_audio_seconds: 25.0,
            total_infer_seconds: 5.0,
            results: Vec::new(),
        };
        let s = summary.to_summary_string();
        assert!(s.contains("8/10 succeeded"), "got: {s}");
        assert!(s.contains("2 failed"), "got: {s}");
        assert!(s.contains("audio 25.00s"), "got: {s}");
        assert!(s.contains("infer 5.00s"), "got: {s}");
        assert!(s.contains("RTF 0.200"), "got: {s}");
    }

    #[test]
    fn test_batch_summary_empty() {
        let summary = BatchSummary::from_results(Vec::new());
        assert_eq!(summary.total_jobs, 0);
        assert_eq!(summary.successful, 0);
        assert_eq!(summary.failed, 0);
        assert!((summary.total_audio_seconds).abs() < 1e-6);
        let s = summary.to_summary_string();
        assert!(s.contains("0/0 succeeded"), "got: {s}");
    }

    // -----------------------------------------------------------------------
    // 5. jobs_from_text_file with tempfile
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_text_file_basic() {
        let dir = tempfile::tempdir().unwrap();
        let text_path = dir.path().join("input.txt");
        fs::write(&text_path, "Hello world\nGoodbye world\n").unwrap();

        let jobs = jobs_from_text_file(&text_path, dir.path(), Some(0), Some("en")).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].text, "Hello world");
        assert_eq!(jobs[0].output_path, dir.path().join("utt_001.wav"));
        assert_eq!(jobs[0].speaker_id, Some(0));
        assert_eq!(jobs[0].language.as_deref(), Some("en"));
        assert_eq!(jobs[1].text, "Goodbye world");
        assert_eq!(jobs[1].output_path, dir.path().join("utt_002.wav"));
    }

    #[test]
    fn test_jobs_from_text_file_skips_empty_lines() {
        let dir = tempfile::tempdir().unwrap();
        let text_path = dir.path().join("input.txt");
        fs::write(&text_path, "Line one\n\n\nLine two\n\n").unwrap();

        let jobs = jobs_from_text_file(&text_path, dir.path(), None, None).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].text, "Line one");
        assert_eq!(jobs[1].text, "Line two");
        // Indices are sequential, skipping empty lines
        assert_eq!(jobs[0].output_path, dir.path().join("utt_001.wav"));
        assert_eq!(jobs[1].output_path, dir.path().join("utt_002.wav"));
    }

    #[test]
    fn test_jobs_from_text_file_no_optional_fields() {
        let dir = tempfile::tempdir().unwrap();
        let text_path = dir.path().join("input.txt");
        fs::write(&text_path, "Single line\n").unwrap();

        let jobs = jobs_from_text_file(&text_path, dir.path(), None, None).unwrap();
        assert_eq!(jobs.len(), 1);
        assert!(jobs[0].speaker_id.is_none());
        assert!(jobs[0].language.is_none());
    }

    #[test]
    fn test_jobs_from_text_file_nonexistent() {
        let result = jobs_from_text_file(
            Path::new("/nonexistent/file.txt"),
            Path::new("/tmp"),
            None,
            None,
        );
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // 6. jobs_from_jsonl with tempfile
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_jsonl_basic() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("batch.jsonl");
        let content = r#"{"text": "Hello"}
{"text": "World", "speaker_id": 5}
"#;
        fs::write(&jsonl_path, content).unwrap();

        let jobs = jobs_from_jsonl(&jsonl_path, dir.path()).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].text, "Hello");
        assert!(jobs[0].speaker_id.is_none());
        assert_eq!(jobs[0].output_path, dir.path().join("utt_001.wav"));
        assert_eq!(jobs[1].text, "World");
        assert_eq!(jobs[1].speaker_id, Some(5));
    }

    #[test]
    fn test_jobs_from_jsonl_with_output_file() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("batch.jsonl");
        let content = r#"{"text": "Custom", "output_file": "custom_output.wav"}"#;
        fs::write(&jsonl_path, content).unwrap();

        let jobs = jobs_from_jsonl(&jsonl_path, dir.path()).unwrap();
        assert_eq!(jobs.len(), 1);
        assert_eq!(jobs[0].output_path, dir.path().join("custom_output.wav"));
    }

    #[test]
    fn test_jobs_from_jsonl_with_language() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("batch.jsonl");
        let content = r#"{"text": "Bonjour", "language": "fr", "speaker_id": 2}"#;
        fs::write(&jsonl_path, content).unwrap();

        let jobs = jobs_from_jsonl(&jsonl_path, dir.path()).unwrap();
        assert_eq!(jobs.len(), 1);
        assert_eq!(jobs[0].language.as_deref(), Some("fr"));
        assert_eq!(jobs[0].speaker_id, Some(2));
    }

    #[test]
    fn test_jobs_from_jsonl_skips_empty_lines() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("batch.jsonl");
        let content = "{\"text\": \"A\"}\n\n{\"text\": \"B\"}\n";
        fs::write(&jsonl_path, content).unwrap();

        let jobs = jobs_from_jsonl(&jsonl_path, dir.path()).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].text, "A");
        assert_eq!(jobs[1].text, "B");
    }

    #[test]
    fn test_jobs_from_jsonl_invalid_json() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("bad.jsonl");
        fs::write(&jsonl_path, "not valid json\n").unwrap();

        let result = jobs_from_jsonl(&jsonl_path, dir.path());
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // 7. Empty text handling
    // -----------------------------------------------------------------------
    #[test]
    fn test_empty_text_job_fields() {
        // Empty text jobs can be constructed; the caller decides how to handle them
        let job = BatchJob {
            text: String::new(),
            output_path: PathBuf::from("/tmp/empty.wav"),
            speaker_id: None,
            language: None,
        };
        assert!(job.text.is_empty());

        // A result for an empty-text job should have 0 duration and success=true
        let result = BatchResult {
            job_index: 0,
            output_path: job.output_path.clone(),
            audio_seconds: 0.0,
            infer_seconds: 0.0,
            success: true,
            error: None,
        };
        assert!(result.success);
        assert!((result.audio_seconds).abs() < 1e-6);
    }

    #[test]
    fn test_text_file_all_empty_lines() {
        let dir = tempfile::tempdir().unwrap();
        let text_path = dir.path().join("empty.txt");
        fs::write(&text_path, "\n\n\n").unwrap();

        let jobs = jobs_from_text_file(&text_path, dir.path(), None, None).unwrap();
        assert!(jobs.is_empty());
    }

    // -----------------------------------------------------------------------
    // 8. Large batch index formatting
    // -----------------------------------------------------------------------
    #[test]
    fn test_auto_output_path_four_digits() {
        let p = auto_output_path(Path::new("/out"), 1234, "utt");
        assert_eq!(p, PathBuf::from("/out/utt_1235.wav"));
    }

    // -----------------------------------------------------------------------
    // 9. BatchSummary all-success and all-failure
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_summary_all_success() {
        let results = vec![
            BatchResult {
                job_index: 0,
                output_path: PathBuf::from("a.wav"),
                audio_seconds: 1.0,
                infer_seconds: 0.1,
                success: true,
                error: None,
            },
            BatchResult {
                job_index: 1,
                output_path: PathBuf::from("b.wav"),
                audio_seconds: 2.0,
                infer_seconds: 0.2,
                success: true,
                error: None,
            },
        ];
        let summary = BatchSummary::from_results(results);
        assert_eq!(summary.successful, 2);
        assert_eq!(summary.failed, 0);
        assert!((summary.total_audio_seconds - 3.0).abs() < 1e-6);
        assert!((summary.total_infer_seconds - 0.3).abs() < 1e-6);
    }

    #[test]
    fn test_batch_summary_all_failure() {
        let results = vec![
            BatchResult {
                job_index: 0,
                output_path: PathBuf::from("a.wav"),
                audio_seconds: 0.0,
                infer_seconds: 0.0,
                success: false,
                error: Some("err1".into()),
            },
            BatchResult {
                job_index: 1,
                output_path: PathBuf::from("b.wav"),
                audio_seconds: 0.0,
                infer_seconds: 0.0,
                success: false,
                error: Some("err2".into()),
            },
        ];
        let summary = BatchSummary::from_results(results);
        assert_eq!(summary.successful, 0);
        assert_eq!(summary.failed, 2);
        assert!((summary.real_time_factor()).abs() < 1e-6);
    }

    // -----------------------------------------------------------------------
    // 10. BatchResult clone
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_result_clone() {
        let result = BatchResult {
            job_index: 7,
            output_path: PathBuf::from("/tmp/utt_008.wav"),
            audio_seconds: 1.5,
            infer_seconds: 0.2,
            success: true,
            error: None,
        };
        let cloned = result.clone();
        assert_eq!(cloned.job_index, result.job_index);
        assert_eq!(cloned.output_path, result.output_path);
        assert!((cloned.audio_seconds - result.audio_seconds).abs() < 1e-6);
    }

    // -----------------------------------------------------------------------
    // 11. jobs_from_text_file trims whitespace
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_text_file_trims_whitespace() {
        let dir = tempfile::tempdir().unwrap();
        let text_path = dir.path().join("spaces.txt");
        fs::write(&text_path, "  hello  \n  world  \n").unwrap();

        let jobs = jobs_from_text_file(&text_path, dir.path(), None, None).unwrap();
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].text, "hello");
        assert_eq!(jobs[1].text, "world");
    }

    // -----------------------------------------------------------------------
    // 12. jobs_from_jsonl mixed auto and custom output
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_jsonl_mixed_output_paths() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("mixed.jsonl");
        let mut f = fs::File::create(&jsonl_path).unwrap();
        writeln!(f, r#"{{"text": "auto"}}"#).unwrap();
        writeln!(f, r#"{{"text": "custom", "output_file": "my.wav"}}"#).unwrap();
        writeln!(f, r#"{{"text": "auto2"}}"#).unwrap();
        drop(f);

        let jobs = jobs_from_jsonl(&jsonl_path, dir.path()).unwrap();
        assert_eq!(jobs.len(), 3);
        assert_eq!(jobs[0].output_path, dir.path().join("utt_001.wav"));
        assert_eq!(jobs[1].output_path, dir.path().join("my.wav"));
        assert_eq!(jobs[2].output_path, dir.path().join("utt_003.wav"));
    }

    // -----------------------------------------------------------------------
    // 13. JSONL malformed input: missing "text" field
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_jsonl_missing_text_field() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("no_text.jsonl");
        // "text" key is absent — serde should fail because it is required
        fs::write(&jsonl_path, r#"{"speaker_id": 1, "language": "en"}"#).unwrap();

        let result = jobs_from_jsonl(&jsonl_path, dir.path());
        assert!(
            result.is_err(),
            "missing 'text' field should cause an error"
        );
        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("text") || err_msg.contains("missing field"),
            "error should mention the missing field, got: {err_msg}"
        );
    }

    // -----------------------------------------------------------------------
    // 14. JSONL malformed input: speaker_id as string should error
    // -----------------------------------------------------------------------
    #[test]
    fn test_jobs_from_jsonl_invalid_speaker_id_type() {
        let dir = tempfile::tempdir().unwrap();
        let jsonl_path = dir.path().join("bad_sid.jsonl");
        // speaker_id should be an integer, not a string
        fs::write(
            &jsonl_path,
            r#"{"text": "hello", "speaker_id": "not_a_number"}"#,
        )
        .unwrap();

        let result = jobs_from_jsonl(&jsonl_path, dir.path());
        assert!(
            result.is_err(),
            "speaker_id as string should cause a deserialization error"
        );
    }

    // -----------------------------------------------------------------------
    // 15. BatchSummary from empty results produces zeros
    // -----------------------------------------------------------------------
    #[test]
    fn test_batch_summary_from_empty_results() {
        let summary = BatchSummary::from_results(Vec::new());
        assert_eq!(summary.total_jobs, 0);
        assert_eq!(summary.successful, 0);
        assert_eq!(summary.failed, 0);
        assert!((summary.total_audio_seconds - 0.0).abs() < 1e-9);
        assert!((summary.total_infer_seconds - 0.0).abs() < 1e-9);
        assert!((summary.real_time_factor() - 0.0).abs() < 1e-9);
        assert!(summary.results.is_empty());
    }

    // -----------------------------------------------------------------------
    // 16. real_time_factor returns exactly 0.0 when audio_seconds is zero
    // -----------------------------------------------------------------------
    #[test]
    fn test_real_time_factor_zero_audio_returns_zero() {
        // Even with nonzero infer_seconds, RTF must be 0.0 when audio is 0
        let summary = BatchSummary {
            total_jobs: 5,
            successful: 0,
            failed: 5,
            total_audio_seconds: 0.0,
            total_infer_seconds: 42.0,
            results: Vec::new(),
        };
        assert_eq!(summary.real_time_factor(), 0.0);
    }

    // -----------------------------------------------------------------------
    // 17. auto_output_path with Unicode prefix
    // -----------------------------------------------------------------------
    #[test]
    fn test_auto_output_path_unicode_prefix() {
        let p = auto_output_path(Path::new("/tmp/out"), 0, "発話");
        assert_eq!(p, PathBuf::from("/tmp/out/発話_001.wav"));

        let p2 = auto_output_path(Path::new("/tmp/out"), 9, "テスト");
        assert_eq!(p2, PathBuf::from("/tmp/out/テスト_010.wav"));

        // Emoji prefix
        let p3 = auto_output_path(Path::new("/data"), 2, "🔊audio");
        assert_eq!(p3, PathBuf::from("/data/🔊audio_003.wav"));
    }
}
