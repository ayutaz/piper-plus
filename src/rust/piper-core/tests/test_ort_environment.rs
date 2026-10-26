//! ONNX Runtime の Environment をプロセスで 1 つだけ作り、使い回すことの検査。
//!
//! ort 2.0.0-rc.14 以降、セッションは `Session::builder(&env)` で作り、
//! Environment は 1 プロセスに 1 回しか作れない (2 回目の `build()` は、
//! 1 回目を捨てたあとでも "only one environment is allowed per process" で
//! 失敗する)。読み込みのたびに Environment を作ると、2 つ目のモデルの読み込みで
//! 失敗するので、同じプロセスで複数のモデルを読めることをここで固定する。
//!
//! 各テストは同じプロセス内で Environment を共有するため、テストの実行順に
//! 依存しない形 (どのテストも先に `environment()` を呼ぶ) にしている。

#![cfg(feature = "onnx")]

use std::path::PathBuf;

use piper_plus::config::VoiceConfig;
use piper_plus::speaker_encoder::SpeakerEncoder;
use piper_plus::wasm::WasmVoice;
use piper_plus::{OnnxEngine, ort_env};

fn models_dir() -> PathBuf {
    // src/rust/piper-core -> repo root is 3 levels up.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repo root")
        .join("test")
        .join("models")
}

fn load_engine(name: &str) -> OnnxEngine {
    let model = models_dir().join(format!("{name}.onnx"));
    let config = VoiceConfig::load(&models_dir().join(format!("{name}.onnx.json")))
        .expect("load test model config");
    OnnxEngine::load(&model, &config, "cpu").expect("load test model")
}

#[test]
fn environment_is_shared_across_calls() {
    let first = ort_env::environment().expect("first environment");
    let second = ort_env::environment().expect("second environment");
    ort::session::Session::builder(&first).expect("builder from first");
    ort::session::Session::builder(&second).expect("builder from second");
}

#[test]
fn two_models_load_in_one_process() {
    let _a = load_engine("multilingual-test-medium");
    let _b = load_engine("zero-shot-test");
    // 同じモデルをもう一度読み込んでも失敗しない。
    let _c = load_engine("multilingual-test-medium");
}

#[test]
fn wasm_voice_loads_after_engine() {
    let _engine = load_engine("multilingual-test-medium");
    let model =
        std::fs::read(models_dir().join("multilingual-test-medium.onnx")).expect("read test model");
    let config = std::fs::read_to_string(models_dir().join("multilingual-test-medium.onnx.json"))
        .expect("read test config");
    WasmVoice::load_from_bytes(&model, &config).expect("load WasmVoice after OnnxEngine");
}

#[test]
fn speaker_encoder_reaches_session_creation_after_engine() {
    // speaker encoder の実モデルは repo にないので、壊れたモデルを渡して、
    // Environment の取得を通り越してモデルの解析で失敗することを確かめる。
    let _engine = load_engine("multilingual-test-medium");
    let dir = tempfile::tempdir().expect("tempdir");
    let bogus = dir.path().join("encoder.onnx");
    std::fs::write(&bogus, b"not an onnx model").expect("write bogus model");
    let err = match SpeakerEncoder::new(&bogus) {
        Ok(_) => panic!("bogus model must not load"),
        Err(e) => e.to_string(),
    };
    assert!(
        !err.contains("only one environment"),
        "speaker encoder tried to create a second environment: {err}"
    );
    assert!(
        err.contains("speaker encoder load"),
        "expected a model parse error, got: {err}"
    );
}

#[test]
fn set_environment_after_initialization_is_rejected() {
    let env = ort_env::environment().expect("environment");
    let err = ort_env::set_environment(env).expect_err("second set must fail");
    assert!(
        err.to_string().contains("already"),
        "error should say the environment is already set: {err}"
    );
}
