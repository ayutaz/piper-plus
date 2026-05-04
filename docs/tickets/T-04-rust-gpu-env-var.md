# T-04: Rust gpu.rs に resolve_device_string() 追加（env var 対応）

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01（ort-session-contract.toml への EP 仕様追記）
**後続タスク:** T-08（Python パッケージ extras_require 追加）、T-09（ドキュメント更新）、T-10（全体回帰テスト）

---

## 1. タスク目的とゴール

### 目的

`src/rust/piper-core/src/gpu.rs` に `resolve_device_string()` 関数を追加し、`PIPER_EXECUTION_PROVIDER` 環境変数を読み取って EP 選択を上書きできるようにする。Rust ランタイムを設計仕様 `docs/superpowers/specs/2026-05-04-hardware-ep-design.md` の §5.2 に準拠させる。

### なぜ必要か

現状、`engine.rs` の `OnnxEngine::load()` は `parse_device_string(device)` を呼び出す。この関数は引数の文字列のみを参照し、環境変数を読まない。そのため `PIPER_EXECUTION_PROVIDER=coreml` を設定しても Rust ランタイムでは無視される。Python・C#・Go・C++ との動作統一に欠け、コントラクト (`ort-session-contract.toml`) が規定する「env var は device パラメータより優先される」という契約を満たせない。

### 完了の定義（Done 基準）

- `gpu.rs` に `pub fn resolve_device_string(device: &str) -> Result<DeviceType, PiperError>` が追加されている
- `engine.rs` の `parse_device_string` 呼び出しが `resolve_device_string` に切り替えられている
- 追加した 6 件のユニットテストがすべて `cargo test -p piper-core -- --test-threads=1` で PASS する（env var の並列汚染を防ぐため `--test-threads=1` 必須）
- `PIPER_EXECUTION_PROVIDER` が未設定または空文字列の場合は従来動作と完全に一致する
- `PIPER_EXECUTION_PROVIDER=cpu` を設定した状態で `parse_device_string("cuda")` 相当の呼び出しが `DeviceType::Cpu` を返す

---

## 2. 実装する内容の詳細

### 2.1 変更ファイル

| ファイル | 変更種別 | 概要 |
|---|---|---|
| `src/rust/piper-core/src/gpu.rs` | 関数追加 + テスト追加 | `resolve_device_string()` を `parse_device_string()` 直後に追加 |
| `src/rust/piper-core/src/engine.rs` | 1 行変更 | `parse_device_string` → `resolve_device_string` |

### 2.2 gpu.rs への追加コード

`parse_device_string()` 関数の直後（`AUTO_DEVICE_CACHE` 静的変数の前）に以下を挿入する：

```rust
/// Resolve a device string, applying `PIPER_EXECUTION_PROVIDER` env var override.
///
/// Priority: `PIPER_EXECUTION_PROVIDER` env var > `device` argument > auto-detect.
///
/// The env var takes precedence over the `device` parameter at all times.
/// If the env var is set but empty, it is ignored and `device` is used instead.
/// If `device` (or env var) is "auto" or empty, `auto_detect_device()` is called.
///
/// Use this instead of `parse_device_string` in inference engines.
pub fn resolve_device_string(device: &str) -> Result<DeviceType, PiperError> {
    let env_ep = std::env::var("PIPER_EXECUTION_PROVIDER")
        .ok()
        .filter(|s| !s.is_empty());

    let effective = env_ep.as_deref().unwrap_or(device);

    if effective.eq_ignore_ascii_case("auto") || effective.is_empty() {
        return Ok(auto_detect_device());
    }

    parse_device_string(effective)
}
```

### 2.3 engine.rs の変更

`src/rust/piper-core/src/engine.rs` の 402 行目付近：

```rust
// 変更前
let device_type = crate::gpu::parse_device_string(device)
    .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;

// 変更後
let device_type = crate::gpu::resolve_device_string(device)
    .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;
```

### 2.4 テストコード（gpu.rs の `#[cfg(test)]` ブロック末尾に追加）

```rust
    #[test]
    fn test_resolve_device_string_env_var_cpu() {
        // SAFETY: テスト内で環境変数を設定/解除する。並列実行に注意。
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "cpu");
        let result = resolve_device_string("auto").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_env_var_cuda() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "cuda");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cuda { device_id: 0 });
    }

    #[test]
    fn test_resolve_device_string_env_var_coreml() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "coreml");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::CoreML);
    }

    #[test]
    fn test_resolve_device_string_no_env_var_uses_param() {
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        let result = resolve_device_string("cpu").unwrap();
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_empty_env_var_uses_param() {
        std::env::set_var("PIPER_EXECUTION_PROVIDER", "");
        let result = resolve_device_string("cpu").unwrap();
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        assert_eq!(result, DeviceType::Cpu);
    }

    #[test]
    fn test_resolve_device_string_auto_without_env() {
        std::env::remove_var("PIPER_EXECUTION_PROVIDER");
        // auto → always returns a valid DeviceType (at minimum CPU)
        let result = resolve_device_string("auto").unwrap();
        match result {
            DeviceType::Cpu
            | DeviceType::Cuda { .. }
            | DeviceType::CoreML
            | DeviceType::DirectML { .. }
            | DeviceType::TensorRT { .. } => {}
        }
    }
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | `gpu.rs` への `resolve_device_string()` 実装、テスト追加、`engine.rs` の1行変更 |
| Review Agent | 1 | OnceLock キャッシュと env var の競合検証、スレッド安全性レビュー、コントラクト準拠確認 |
| QA Agent | 1 | `cargo test -p piper-core` 全件 PASS 確認、env var をセット/アンセットした状態での smoke test 実施 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/rust/piper-core/src/gpu.rs` | `pub fn resolve_device_string()` 追加（約20行）、テスト6件追加（約60行） |
| `src/rust/piper-core/src/engine.rs` | `parse_device_string` → `resolve_device_string` への1行変更 |

スコープ外: `gpu.rs` の既存関数（`parse_device_string`, `auto_detect_device`, `configure_session_builder`, `list_devices`）は変更しない。`Cargo.toml` の features も変更しない。

### Unit テスト

`resolve_device_string()` の単体テスト 6 件を `gpu.rs` の `#[cfg(test)]` ブロックに追加する：

| テスト名 | 検証内容 |
|---|---|
| `test_resolve_device_string_env_var_cpu` | `PIPER_EXECUTION_PROVIDER=cpu` + `device="auto"` → `DeviceType::Cpu` |
| `test_resolve_device_string_env_var_cuda` | `PIPER_EXECUTION_PROVIDER=cuda` + `device="cpu"` → `DeviceType::Cuda{0}` |
| `test_resolve_device_string_env_var_coreml` | `PIPER_EXECUTION_PROVIDER=coreml` + `device="cpu"` → `DeviceType::CoreML` |
| `test_resolve_device_string_no_env_var_uses_param` | env var 未設定 + `device="cpu"` → `DeviceType::Cpu` |
| `test_resolve_device_string_empty_env_var_uses_param` | `PIPER_EXECUTION_PROVIDER=""` + `device="cpu"` → `DeviceType::Cpu` |
| `test_resolve_device_string_auto_without_env` | env var 未設定 + `device="auto"` → 有効な `DeviceType` の任意のバリアント |

既存の `parse_device_string` テスト群（34 件）は変更しない。回帰として全件 PASS を確認する。

### E2E テスト

```bash
# env var なし: 従来動作（CPU 推論）
CUDA_VISIBLE_DEVICES="" cargo run -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx --device cpu \
  --text "テスト" --output /tmp/out.wav

# PIPER_EXECUTION_PROVIDER=cpu: 明示 CPU 強制
PIPER_EXECUTION_PROVIDER=cpu cargo run -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx --device auto \
  --text "テスト" --output /tmp/out.wav

# macOS のみ: PIPER_EXECUTION_PROVIDER=coreml
PIPER_EXECUTION_PROVIDER=coreml cargo run -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト" --output /tmp/out.wav
```

すべてのケースで出力 WAV ファイルが生成されること、RMS > 0 であること（音声ゼロ出力でないこと）を確認する。

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

#### 1. OnceLock キャッシュと env var の競合

最大の懸念点。既存の `auto_detect_device()` は `AUTO_DEVICE_CACHE: OnceLock<DeviceType>` でプロセス生存期間中の結果をキャッシュする。このキャッシュは「最初の `auto_detect_device()` 呼び出し時の環境変数値」で永続化される。

問題シナリオ:
1. プロセス起動時点で `PIPER_EXECUTION_PROVIDER` が未設定 → `auto_detect_device()` が CPU を検出してキャッシュ
2. その後 `os::set_var("PIPER_EXECUTION_PROVIDER", "cuda")` で変更
3. `resolve_device_string("auto")` を呼び出すと env var 値 `"cuda"` を読んで `parse_device_string("cuda")` を呼び出す（`auto_detect_device()` は経由しない）

上記シナリオでは問題は発生しない。しかし逆の場合:
1. `PIPER_EXECUTION_PROVIDER=auto` をセット（これは spec 未定義だが考慮が必要）
2. `resolve_device_string("cpu")` → env var `"auto"` を読んで `auto_detect_device()` を呼び出す → OnceLock キャッシュが返る
3. その後 `os::remove_var()` しても OnceLock キャッシュは変わらない

テスト上の注意: 並列テスト実行時（`cargo test` はデフォルト並列）に `set_var`/`remove_var` が競合する。テスト環境では `RUST_TEST_THREADS=1` を使うか、テスト内で `std::env::remove_var` 後にアサートする。テストは `unsafe` ブロックを使わず `std::env::set_var` を呼ぶが、Rust 1.81 以降では `set_var` が unsafe になるため、将来的なコンパイラバージョンアップ時に対処が必要。

実際の問題度: エンジン起動時に env var を読み込む設計であり、ランタイム中の env var 変更はサポート外。したがってプロダクションコードでの競合リスクは低い。テストコードでは直列化が必要。

#### 2. `resolve_device_string` が `auto_detect_device` の OnceLock をバイパスする設計

設計では `PIPER_EXECUTION_PROVIDER` が設定されている場合、`resolve_device_string` は `auto_detect_device()` を呼ばずに `parse_device_string(effective)` を直接呼び出す。これは意図した設計であり、env var が明示指定である以上キャッシュに依存する必要はない。ただし `effective == "auto"` の場合は `auto_detect_device()` を呼び出すため OnceLock を経由する。

#### 3. `gpu.rs` のモジュール公開 (`pub`) 範囲

`parse_device_string` は既に `pub` で公開されている。`resolve_device_string` も `pub` にする。`auto_detect_device` は `pub(crate)` 程度で十分だが、現状 `fn`（非 pub）のまま維持する（既存テストが `super::auto_detect_device()` を直接呼び出しているため）。

### レビューチェックリスト

- [ ] `resolve_device_string` が `parse_device_string` を完全に置き換える API として機能しているか（既存の直接呼び出し箇所が engine.rs のみであることを `grep` で確認）
- [ ] env var が空文字列のケース（`PIPER_EXECUTION_PROVIDER=""`）で `filter(|s| !s.is_empty())` が正しく機能しているか
- [ ] `engine.rs` 以外に `parse_device_string` を直接呼び出している箇所がないか（将来の追加ファイルを含め `grep -r parse_device_string src/rust/` で確認）
- [ ] テストが並列実行時に env var 競合を引き起こさないか（`RUST_TEST_THREADS=1` が必要な場合は CI に明記）
- [ ] `PIPER_EXECUTION_PROVIDER=tensorrt` の場合に `parse_device_string("tensorrt")` が呼ばれ `DeviceType::TensorRT{0}` が返ること（TensorRT は auto-detect 対象外だが明示指定は可能）
- [ ] `DeviceType::Display` の `:` 除去ロジック（`"cuda:0".replace(':', "")` → `"cuda0"`）が `resolve_device_string` を通過した後も正しく機能するか（engine.rs のキャッシュパス計算への影響確認）

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

Rust の強みは型安全性とゼロコスト抽象化にある。EP 選択は「ランタイム設定（env var）」と「呼び出し元指定（引数）」と「自動検出（ハードウェアプローブ）」という 3 層のフォールバックチェーンであり、これを Rust の型システムで明示的に表現すべきである。

具体的には `DeviceRequest` という型を定義し、`Auto`, `Explicit(DeviceType)`, `FromEnv` というバリアントで意図を表現する。環境変数読み取りは副作用であり、型境界で明確に分離すべきだ。

### アーキテクチャ

```rust
/// EP 選択の意図を表す型
pub enum DeviceRequest {
    /// 自動検出（ハードウェアプローブ）
    Auto,
    /// 明示指定（呼び出し元からの入力）
    Explicit(DeviceType),
}

/// 解決済みの EP（プロセス起動時に1回決定）
pub struct ResolvedDevice {
    device: DeviceType,
    source: DeviceSource,
}

pub enum DeviceSource {
    EnvVar,
    Argument,
    AutoDetected,
}

/// EP 選択の単一エントリポイント
pub fn resolve_device(request: DeviceRequest) -> ResolvedDevice {
    // 1. env var を最優先
    if let Some(ep_str) = std::env::var("PIPER_EXECUTION_PROVIDER").ok().filter(|s| !s.is_empty()) {
        let device = parse_device_string(&ep_str).unwrap_or(DeviceType::Cpu);
        return ResolvedDevice { device, source: DeviceSource::EnvVar };
    }
    // 2. 明示指定
    match request {
        DeviceRequest::Auto => {
            let device = auto_detect_device();
            ResolvedDevice { device, source: DeviceSource::AutoDetected }
        }
        DeviceRequest::Explicit(d) => ResolvedDevice { device: d, source: DeviceSource::Argument },
    }
}
```

`OnceLock` によるキャッシュは `auto_detect_device` のみに限定し、env var の読み取りはキャッシュしない（プロセス内で env var が変わる可能性は低いが、キャッシュすると理由が不明になる）。

### 実装アプローチ

`resolve_device` の返値を `engine.rs` が受け取り、`actual_device` のトレースログに `source` フィールドを含める。これにより「なぜその EP が選ばれたか」をログで追跡できる。

キャッシュ戦略として、auto-detect 結果（ハードウェアプローブ）は `OnceLock` でキャッシュするが、env var の読み取りはキャッシュしない（実装が単純になる）。

### 現行実装との主な差異

| 項目 | 現行 | Green Field |
|---|---|---|
| API | `parse_device_string(&str)` → `resolve_device_string(&str)` (2段階) | `resolve_device(DeviceRequest)` → `ResolvedDevice` (1段階) |
| 型安全性 | 文字列引数で意図が不明 | バリアント型で明示 |
| ログ | 選択された EP のみ | EP の選択理由（env var / 引数 / 自動検出）も出力 |
| テスト | env var 競合リスクあり | `DeviceResolver` トレイトで DI して env var を注入、テストが容易 |
| OnceLock | auto-detect 結果をキャッシュ | 同様（ただしキャッシュ範囲を明確に文書化） |

現行実装は差分最小の方針（既存 `parse_device_string` を残しつつ薄いラッパーを追加）であり、互換性維持の観点では合理的。Green Field 設計は次世代 API 設計の参考として活用できる。

---

## 7. 後続タスクへの引き継ぎ事項

### T-01（コントラクト更新）完了を前提として

T-04 は T-01（`ort-session-contract.toml` への EP 仕様追記）完了後に着手する。コントラクトの `override_var = "PIPER_EXECUTION_PROVIDER"` が確定している前提で `resolve_device_string` を実装するため、T-01 が未完了の場合は T-01 の実装内容を先に確認すること。

### 変更した内容の要約（T-08/T-09/T-10 担当者へ）

1. `gpu.rs` に `pub fn resolve_device_string()` が追加された。既存の `parse_device_string()` は変更なし（後方互換を維持）。
2. `engine.rs` の `OnnxEngine::load()` が内部で `resolve_device_string` を使う。`engine.rs` の外部 API は変更なし。
3. テスト環境では `RUST_TEST_THREADS=1` が必要な場合がある（env var 競合）。CI の `.cargo/config.toml` に設定を追加するか、テストレベルで対処すること。
4. `PIPER_EXECUTION_PROVIDER` が設定されていない既存のユーザー環境では動作変化なし（完全後方互換）。

### T-05（Go）担当者との並行作業の注意点

T-04 と T-05 は並行実施可能。共有ファイルはなし。ただし両タスクのコミット後に T-10（全体回帰テスト）で `cargo test --workspace` と `go test ./...` を同時実行するため、どちらかのテストが env var 汚染を引き起こさないよう注意すること。
