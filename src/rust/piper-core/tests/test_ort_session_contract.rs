//! ORT session contract parity test (Rust runtime).
//!
//! Loads `tests/fixtures/ort_session/contract.json` and verifies that the
//! Rust constants in `piper_core::engine` agree with the canonical contract
//! values for max_intra_threads, warmup parameters, etc.
//!
//! Sister tests in Python/Go/C# load the same fixture and assert their
//! own runtime constants — drift in any of them is caught locally.

use std::path::PathBuf;

use piper_plus::engine::{DEFAULT_WARMUP_RUNS, MAX_INTRA_THREADS, WARMUP_PHONEME_LENGTH};
use serde_json::Value;

fn load_fixture() -> Value {
    let path = repo_root().join("tests/fixtures/ort_session/contract.json");
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("failed to read {}: {}", path.display(), e));
    serde_json::from_str(&text)
        .unwrap_or_else(|e| panic!("failed to parse {}: {}", path.display(), e))
}

fn repo_root() -> PathBuf {
    // CARGO_MANIFEST_DIR points at src/rust/piper-core; ../../.. is repo root.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

#[test]
fn test_fixture_loads_with_expected_schema() {
    let fixture = load_fixture();
    assert_eq!(fixture["schema_version"], 1);
    for section in ["session", "warmup", "cache", "env_vars"] {
        assert!(
            fixture.get(section).is_some(),
            "fixture missing '{section}' section"
        );
    }
}

#[test]
fn test_max_intra_threads_matches_contract() {
    let fixture = load_fixture();
    let expected = fixture["session"]["max_intra_threads"].as_u64().unwrap() as usize;
    assert_eq!(MAX_INTRA_THREADS, expected);
}

#[test]
fn test_warmup_phoneme_length_matches_contract() {
    let fixture = load_fixture();
    let expected = fixture["warmup"]["phoneme_length"].as_u64().unwrap() as usize;
    assert_eq!(WARMUP_PHONEME_LENGTH, expected);
}

#[test]
fn test_default_warmup_runs_matches_contract() {
    let fixture = load_fixture();
    let expected = fixture["warmup"]["default_runs"].as_u64().unwrap() as usize;
    assert_eq!(DEFAULT_WARMUP_RUNS, expected);
}

#[test]
fn test_inter_op_threads_value() {
    let fixture = load_fixture();
    // Rust calls `.with_inter_threads(1)` in engine.rs build_session.
    assert_eq!(fixture["session"]["inter_op_threads"].as_u64().unwrap(), 1);
}

#[test]
fn test_dynamic_block_base_value() {
    let fixture = load_fixture();
    // Rust calls `.with_dynamic_block_base(4)` in engine.rs build_session.
    assert_eq!(
        fixture["session"]["dynamic_block_base"].as_u64().unwrap(),
        4
    );
}

#[test]
fn test_graph_optimization_level_canonical_name() {
    let fixture = load_fixture();
    assert_eq!(
        fixture["session"]["graph_optimization_level"]
            .as_str()
            .unwrap(),
        "ORT_ENABLE_ALL"
    );
}

#[test]
fn test_execution_mode_canonical_name() {
    let fixture = load_fixture();
    assert_eq!(
        fixture["session"]["execution_mode"].as_str().unwrap(),
        "SEQUENTIAL"
    );
}

#[test]
fn test_warmup_token_values() {
    let fixture = load_fixture();
    assert_eq!(fixture["warmup"]["bos_token"].as_u64().unwrap(), 1);
    assert_eq!(fixture["warmup"]["eos_token"].as_u64().unwrap(), 2);
    assert_eq!(fixture["warmup"]["dummy_phoneme"].as_u64().unwrap(), 8);
}

#[test]
fn test_warmup_scale_values() {
    let fixture = load_fixture();
    let noise_scale = fixture["warmup"]["noise_scale"].as_f64().unwrap();
    let length_scale = fixture["warmup"]["length_scale"].as_f64().unwrap();
    let noise_w = fixture["warmup"]["noise_w"].as_f64().unwrap();
    assert!((noise_scale - 0.667).abs() < 1e-9);
    assert!((length_scale - 1.0).abs() < 1e-9);
    assert!((noise_w - 0.8).abs() < 1e-9);
}

#[test]
fn test_cache_extensions_match_contract() {
    let fixture = load_fixture();
    assert_eq!(
        fixture["cache"]["optimized_extension"].as_str().unwrap(),
        "opt.onnx"
    );
    assert_eq!(
        fixture["cache"]["sentinel_extension"].as_str().unwrap(),
        "opt.onnx.ok"
    );
    assert_eq!(
        fixture["cache"]["sentinel_content"].as_str().unwrap(),
        "ok"
    );
}

#[test]
fn test_env_var_names() {
    let fixture = load_fixture();
    assert_eq!(
        fixture["env_vars"]["disable_warmup"].as_str().unwrap(),
        "PIPER_DISABLE_WARMUP"
    );
    assert_eq!(
        fixture["env_vars"]["disable_cache"].as_str().unwrap(),
        "PIPER_DISABLE_CACHE"
    );
    assert_eq!(
        fixture["env_vars"]["intra_threads"].as_str().unwrap(),
        "PIPER_INTRA_THREADS"
    );
}
