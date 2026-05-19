//! CLI smoke tests for piper-plus-cli.
//!
//! These tests pin the public CLI surface (flag presence, defaults, exclusivity
//! constraints) so refactors in main.rs don't silently break the contract that
//! Python / Go / C# CLIs are aligned with.

use assert_cmd::Command;
use predicates::prelude::*;
use std::path::PathBuf;

fn cli() -> Command {
    Command::cargo_bin("piper-plus-cli").expect("piper-plus-cli binary should be built")
}

/// 6 runtime parity gate と同じ canonical fixture を inline で持つ。
/// `tests/fixtures/audio-corpus/parity/phoneme_ids.jsonl` と byte-for-byte
/// 一致させ、 fixture が更新されたら本テストも更新するよう pin する。
const CANONICAL_JSONL: &str =
    r#"{"phoneme_ids": [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2], "language_id": 0}"#;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
}

fn test_model_path() -> PathBuf {
    repo_root()
        .join("test")
        .join("models")
        .join("multilingual-test-medium.onnx")
}

fn test_config_path() -> PathBuf {
    repo_root()
        .join("test")
        .join("models")
        .join("multilingual-test-medium.onnx.json")
}

#[test]
fn shows_help() {
    cli()
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("Usage"))
        .stdout(predicate::str::contains("Piper-Plus TTS inference"));
}

#[test]
fn shows_version() {
    cli().arg("--version").assert().success();
}

#[test]
fn rejects_invalid_flag() {
    cli().arg("--definitely-not-a-real-flag").assert().failure();
}

#[test]
fn help_advertises_model_flag() {
    cli()
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("--model"));
}

#[test]
fn help_advertises_text_flag() {
    cli()
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("--text"));
}

#[test]
fn help_advertises_language_flag() {
    cli()
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("--language"));
}

#[test]
fn help_advertises_voice_cloning_flags() {
    let out = cli().arg("--help").assert().success();
    out.stdout(
        predicate::str::contains("--reference-audio")
            .and(predicate::str::contains("--speaker-embedding"))
            .and(predicate::str::contains("--speaker-encoder-model")),
    );
}

#[test]
fn help_advertises_streaming_and_timing_flags() {
    let out = cli().arg("--help").assert().success();
    out.stdout(predicate::str::contains("--stream").and(predicate::str::contains("--timing")));
}

#[test]
fn help_advertises_list_devices_and_list_models() {
    let out = cli().arg("--help").assert().success();
    out.stdout(
        predicate::str::contains("--list-devices").and(predicate::str::contains("--list-models")),
    );
}

#[test]
fn help_advertises_default_noise_scale() {
    cli()
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("0.667"));
}

#[test]
fn help_advertises_length_and_noise_w_flags() {
    let out = cli().arg("--help").assert().success();
    out.stdout(
        predicate::str::contains("--length-scale").and(predicate::str::contains("--noise-w")),
    );
}

#[test]
fn list_devices_runs_without_model() {
    cli().arg("--list-devices").assert().success();
}

#[test]
fn invalid_phoneme_silence_format_fails() {
    cli()
        .args([
            "--phoneme-silence",
            "missing-seconds",
            "--text",
            "test",
            "--model",
            "/nonexistent/model.onnx",
        ])
        .assert()
        .failure();
}

// ---------------------------------------------------------------------------
// JSONL phoneme_ids 入力経路の contract test (PR #511 Phase 2 で 6 runtime
// parity gate に Rust を組み込んだ際、 Rust 単独の E2E test が欠落していた
// ことが cross-runtime 監査で判明したため追加)。
//
// 軽量な構造 contract は `cargo test` 既定で実行 (ORT 不要)。
// 重い E2E は `#[ignore]` で gate し、 `cargo test -- --ignored` 又は
// runtime-parity-deep workflow の dump-rust step で実行する。
// ---------------------------------------------------------------------------

/// JSONL stdin pipeline は `--text` 不在 + stdin pipe で自動検出される
/// (main.rs:714 の else 分岐)。 CLI argv parser が `--text` を必須化して
/// いると Phase 2 で追加した phoneme_ids 経路が silently 死ぬため、
/// argv level で reject されないことを ORT を起動せずに pin する。
/// 失敗位置はモデルロード時点 (Failed to load ONNX model) であるべき。
#[test]
fn jsonl_stdin_without_text_flag_passes_argv_validation() {
    cli()
        .args([
            "--model",
            "/nonexistent/model.onnx",
            "--config",
            "/nonexistent/config.json",
            "--output-file",
            "/tmp/should-never-be-written.wav",
            "--no-warmup",
        ])
        .write_stdin(CANONICAL_JSONL.to_string() + "\n")
        .assert()
        .failure()
        .stderr(predicate::str::contains("Failed to load ONNX model").or(
            // 環境によって anyhow context が異なる文言で先頭に来ることがあるため、
            // model path 自体が error chain に含まれることを weaker invariant として
            // 受け入れる。 重要なのは argv parse error ではないこと。
            predicate::str::contains("/nonexistent/model.onnx"),
        ));
}

/// JSONL phoneme_ids → WAV ファイル出力 E2E (model 必要、 ORT 起動)。
/// canonical fixture を stdin に流し、 `--output-file` で指定した path
/// に RIFF/WAVE header を持つ非空 WAV が書かれることを assert。
#[test]
#[ignore = "requires test model + ORT runtime; runs via `cargo test -- --ignored` or runtime-parity-deep workflow"]
fn jsonl_phoneme_ids_writes_valid_wav_file() {
    let model = test_model_path();
    if !model.exists() {
        eprintln!("SKIP: test model not found at {:?}", model);
        return;
    }
    let tmp = tempfile::tempdir().expect("tempdir");
    let out = tmp.path().join("out.wav");
    cli()
        .args([
            "--model",
            model.to_str().unwrap(),
            "--config",
            test_config_path().to_str().unwrap(),
            "--output-file",
            out.to_str().unwrap(),
            "--no-warmup",
        ])
        .write_stdin(CANONICAL_JSONL.to_string() + "\n")
        .assert()
        .success();
    let bytes = std::fs::read(&out).expect("output wav should exist");
    assert!(bytes.len() > 44, "WAV must have payload beyond header");
    assert_eq!(&bytes[0..4], b"RIFF", "first 4 bytes must be RIFF magic");
    assert_eq!(&bytes[8..12], b"WAVE", "bytes 8..12 must be WAVE");
}

/// JSONL entry の `output_file` field は CLI `--output-file` flag より
/// 優先する (main.rs:768-774 の precedence)。 これは Python/Go/C#/C++ の
/// per-line override contract と対称。
#[test]
#[ignore = "requires test model + ORT runtime; runs via `cargo test -- --ignored` or runtime-parity-deep workflow"]
fn jsonl_per_line_output_file_overrides_cli_flag() {
    let model = test_model_path();
    if !model.exists() {
        eprintln!("SKIP: test model not found at {:?}", model);
        return;
    }
    let tmp = tempfile::tempdir().expect("tempdir");
    let cli_out = tmp.path().join("cli-default.wav");
    let line_out = tmp.path().join("per-line.wav");
    // Rust CLI の per-line override は `--output-dir` mode で動くため、
    // dir + utterance.output_file の combination で test する。
    let jsonl = format!(
        r#"{{"phoneme_ids": [1, 10, 0, 11, 0, 12, 0, 13, 0, 14, 0, 2], "language_id": 0, "output_file": "{}"}}"#,
        line_out.file_name().unwrap().to_str().unwrap()
    );
    cli()
        .args([
            "--model",
            model.to_str().unwrap(),
            "--config",
            test_config_path().to_str().unwrap(),
            "--output-dir",
            tmp.path().to_str().unwrap(),
            "--output-file",
            cli_out.to_str().unwrap(),
            "--no-warmup",
        ])
        .write_stdin(jsonl + "\n")
        .assert()
        .success();
    assert!(line_out.exists(), "per-line output_file must be honoured");
}

/// `--speaker-id` と `--speaker-embedding` は voice conditioning の
/// 排他的な指定方法であるため、両方与えられた場合は推論を始める前に
/// reject されること (engine 側 `SynthesisRequest::validate()` と仕様一致)。
#[test]
fn rejects_speaker_id_with_speaker_embedding() {
    cli()
        .args([
            "--speaker",
            "0",
            "--speaker-embedding",
            "/nonexistent/embedding.bin",
            "--text",
            "test",
            "--model",
            "/nonexistent/model.onnx",
        ])
        .assert()
        .failure()
        .stderr(
            predicate::str::contains("--speaker-id")
                .and(predicate::str::contains("--speaker-embedding"))
                .and(predicate::str::contains("mutually exclusive")),
        );
}
