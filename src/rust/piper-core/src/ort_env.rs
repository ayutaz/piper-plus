//! ONNX Runtime の Environment をプロセスで 1 つだけ持つ。
//!
//! ort 2.0.0-rc.14 以降、セッションは `Session::builder(&env)` で作る。
//! Environment は 1 プロセスに 1 回しか作れず、2 回目の
//! `ort::init().build()` は 1 回目を捨てたあとでも失敗する。そのため、
//! piper-plus のセッション (音声モデル・speaker encoder・WASM API) は、
//! すべてここで作った 1 つの Environment を使い回す。
//!
//! アプリが自分で Environment を作る場合 (ログやスレッドプールを設定したい、
//! 別の ONNX モデルも動かしている、など) は、最初のモデルを読み込む前に
//! [`set_environment`] で渡す。渡さずにアプリ側で先に作ると、piper-plus は
//! Environment を作れずにモデルの読み込みが失敗する。
//!
//! セッションは [`session_builder`] から作る。ort の `SessionBuilder` は
//! 既定で EP を自動選択し (`AutoDevicePolicy::MaxEfficiency`)、macOS では
//! CPU EP を明示しても CoreML EP を登録する。CoreML がノードをコンパイルすると
//! 最適化済みモデルを保存できず、キャッシュ付きの読み込みが失敗する
//! ("Unable to serialize model as it contains compiled nodes")。piper-plus は
//! 使う EP を `--device` で明示的に選ぶので、自動選択は止めておく。

use std::sync::{Mutex, PoisonError};

use ort::environment::Environment;
use ort::session::Session;
use ort::session::builder::{AutoDevicePolicy, SessionBuilder};

use crate::error::PiperError;

static ENVIRONMENT: Mutex<Option<Environment>> = Mutex::new(None);

/// 共有の Environment から、EP の自動選択を止めた `SessionBuilder` を作る。
pub fn session_builder() -> Result<SessionBuilder, PiperError> {
    let env = environment()?;
    Session::builder(&env)
        .map_err(|e| PiperError::ModelLoad(format!("session builder: {e}")))?
        .with_auto_device(AutoDevicePolicy::PreferCPU)
        .map_err(|e| PiperError::ModelLoad(format!("auto device policy: {e}")))
}

/// piper-plus が使う Environment を返す。まだなければ既定の設定で作る。
pub fn environment() -> Result<Environment, PiperError> {
    let mut slot = ENVIRONMENT.lock().unwrap_or_else(PoisonError::into_inner);
    if let Some(env) = slot.as_ref() {
        return Ok(env.clone());
    }
    let env = ort::init().build().map_err(|e| {
        PiperError::ModelLoad(format!(
            "ONNX Runtime environment: {e} (if the application creates its own \
             environment, pass it with piper_plus::ort_env::set_environment before \
             loading a model)"
        ))
    })?;
    *slot = Some(env.clone());
    Ok(env)
}

/// アプリが作った Environment を piper-plus に使わせる。
///
/// 最初のモデルを読み込む前に呼ぶ。piper-plus がすでに Environment を
/// 持っている場合はエラーを返し、持っている Environment は変えない。
pub fn set_environment(env: Environment) -> Result<(), PiperError> {
    let mut slot = ENVIRONMENT.lock().unwrap_or_else(PoisonError::into_inner);
    if slot.is_some() {
        return Err(PiperError::InvalidArgument {
            reason: "the ONNX Runtime environment is already set; call set_environment \
                     before loading any model"
                .to_string(),
        });
    }
    *slot = Some(env);
    Ok(())
}
