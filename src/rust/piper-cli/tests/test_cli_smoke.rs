//! CLI smoke tests for piper-plus-cli.
//!
//! These tests pin the public CLI surface (flag presence, defaults, exclusivity
//! constraints) so refactors in main.rs don't silently break the contract that
//! Python / Go / C# CLIs are aligned with.

use assert_cmd::Command;
use predicates::prelude::*;

fn cli() -> Command {
    Command::cargo_bin("piper-plus-cli").expect("piper-plus-cli binary should be built")
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
