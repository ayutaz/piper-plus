#![cfg(feature = "onnx")]
//! Tests for the default output.wav behavior.
//!
//! The CLI writes to "output.wav" in the current directory when
//! neither `--output-file` nor `--output-dir` is specified.
//! These tests verify the underlying `audio::write_wav` function
//! that the CLI delegates to for that default path.

use piper_plus::audio;
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// write_wav creates a valid WAV file at the specified path
// ---------------------------------------------------------------------------

#[test]
fn test_write_wav_creates_file_at_path() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("output.wav");

    let samples: Vec<i16> = vec![0, 1000, -1000, 16384, -16384];
    audio::write_wav(&path, 22050, &samples).unwrap();

    assert!(path.exists(), "write_wav should create the file");
    let metadata = std::fs::metadata(&path).unwrap();
    assert!(
        metadata.len() > 44,
        "WAV file should be larger than the 44-byte header, got {} bytes",
        metadata.len()
    );
}

#[test]
fn test_write_wav_default_output_name() {
    // Simulates the CLI default: writing to "output.wav" in a temp directory.
    // The CLI uses `PathBuf::from("output.wav")` when no output option is given.
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("output.wav");

    let samples: Vec<i16> = vec![100; 22050]; // 1 second of audio at 22050 Hz
    audio::write_wav(&path, 22050, &samples).unwrap();

    assert!(path.exists());
    // 44-byte header + 22050 samples * 2 bytes = 44 + 44100 = 44144 bytes
    let expected_size: u64 = 44 + (22050 * 2);
    let actual_size = std::fs::metadata(&path).unwrap().len();
    assert_eq!(
        actual_size,
        expected_size,
        "WAV file size should be header (44) + data ({} samples * 2 bytes)",
        samples.len()
    );
}

#[test]
fn test_write_wav_empty_audio() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("output.wav");

    audio::write_wav(&path, 22050, &[]).unwrap();

    assert!(path.exists());
    // Empty audio: just the WAV header (44 bytes)
    let size = std::fs::metadata(&path).unwrap().len();
    assert_eq!(
        size, 44,
        "empty audio WAV should be exactly 44 bytes (header only)"
    );
}

#[test]
fn test_write_wav_overwrites_existing_file() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("output.wav");

    // Write first file
    let samples_a: Vec<i16> = vec![100; 100];
    audio::write_wav(&path, 22050, &samples_a).unwrap();
    let size_a = std::fs::metadata(&path).unwrap().len();

    // Overwrite with different-length audio
    let samples_b: Vec<i16> = vec![200; 500];
    audio::write_wav(&path, 22050, &samples_b).unwrap();
    let size_b = std::fs::metadata(&path).unwrap().len();

    assert_ne!(
        size_a, size_b,
        "overwritten file should have different size"
    );
    assert_eq!(
        size_b,
        44 + 500 * 2,
        "overwritten file should match new audio length"
    );
}

#[test]
fn test_write_wav_nonexistent_directory_fails() {
    let path = PathBuf::from("/nonexistent/directory/output.wav");
    let result = audio::write_wav(&path, 22050, &[100, 200]);
    assert!(
        result.is_err(),
        "writing to a nonexistent directory should fail"
    );
}

// ---------------------------------------------------------------------------
// Default path resolution logic (mirrors CLI behavior)
// ---------------------------------------------------------------------------

#[test]
fn test_default_output_path_is_output_wav() {
    // The CLI uses `PathBuf::from("output.wav")` when no output option is given.
    // Verify this produces the expected relative path.
    let default_path = PathBuf::from("output.wav");
    assert_eq!(
        default_path.file_name().and_then(|s| s.to_str()),
        Some("output.wav")
    );
    assert_eq!(
        default_path.extension().and_then(|s| s.to_str()),
        Some("wav")
    );
}

#[test]
fn test_output_dir_join_produces_output_wav() {
    // When --output-dir is given, the CLI uses `dir.join("output.wav")`.
    let dir = PathBuf::from("/some/output/dir");
    let path = dir.join("output.wav");
    assert!(
        path.ends_with("output.wav"),
        "joined path should end with output.wav, got: {:?}",
        path
    );
    assert!(
        path.starts_with("/some/output/dir"),
        "joined path should start with the output dir"
    );
}
