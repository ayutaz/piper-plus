# T-05: Go device.go に PIPER_EXECUTION_PROVIDER env var 対応追加

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01（ort-session-contract.toml への EP 仕様追記）
**後続タスク:** T-08（Python パッケージ extras_require 追加）、T-09（ドキュメント更新）、T-10（全体回帰テスト）

---

## 1. タスク目的とゴール

### 目的

`src/go/piperplus/device.go` に `selectDeviceWithEnv()` 関数を追加し、`configureSessionOptions()` の先頭でこれを呼び出すことで `PIPER_EXECUTION_PROVIDER` 環境変数による EP 上書きを実現する。Go ランタイムを設計仕様 `docs/superpowers/specs/2026-05-04-hardware-ep-design.md` の §5.5 に準拠させる。

### なぜ必要か

現状、`configureSessionOptions()` は引数 `device string` をそのまま `ParseDevice()` に渡す。環境変数を参照しないため、`PIPER_EXECUTION_PROVIDER=coreml` を設定しても Go ランタイムでは無視される。Python・Rust・C#・C++ との動作統一に欠け、コントラクト (`ort-session-contract.toml`) が規定する「`PIPER_EXECUTION_PROVIDER` env var は device パラメータより優先される」という契約を満たせない。

Go の `autoSelectEP()` はすでに CUDA→CoreML→DirectML→CPU の優先度順で自動検出を実装しており、本タスクの差分は env var の読み取りを先頭に追加するのみである。

### 完了の定義（Done 基準）

- `device.go` に `func selectDeviceWithEnv(device string) string` が追加されている
- `configureSessionOptions()` の先頭で `device = selectDeviceWithEnv(device)` が呼び出されている
- `device_test.go` に追加したテスト群がすべて `go test ./piperplus/` で PASS する
- `PIPER_EXECUTION_PROVIDER` が未設定または空文字列の場合は従来動作と完全に一致する
- `PIPER_EXECUTION_PROVIDER=cpu` を設定した状態で `configureSessionOptions("auto", ...)` を呼ぶと CPU が選択される

---

## 2. 実装する内容の詳細

### 2.1 変更ファイル

| ファイル | 変更種別 | 概要 |
|---|---|---|
| `src/go/piperplus/device.go` | 関数追加 + 1行変更 | `selectDeviceWithEnv()` 追加、`configureSessionOptions()` 先頭に挿入 |
| `src/go/piperplus/device_test.go` | テスト追加 | `TestSelectDeviceWithEnv`、`TestConfigureSessionOptionsEnvVar` 追加 |

### 2.2 device.go への追加コード

`ParseDevice()` 関数の直前に以下を挿入する：

```go
// selectDeviceWithEnv returns the effective device string after applying the
// PIPER_EXECUTION_PROVIDER environment variable override.
//
// Priority: PIPER_EXECUTION_PROVIDER env var > device parameter.
// If the env var is set but empty, it is ignored and device is used as-is.
// This function does NOT validate the returned string; ParseDevice handles that.
func selectDeviceWithEnv(device string) string {
    if ep := os.Getenv("PIPER_EXECUTION_PROVIDER"); ep != "" {
        return strings.ToLower(strings.TrimSpace(ep))
    }
    return device
}
```

`configureSessionOptions()` の本体先頭（`logger == nil` チェックの前）に 1 行追加する：

```go
func configureSessionOptions(device string, logger *slog.Logger) (*ort.SessionOptions, error) {
    device = selectDeviceWithEnv(device)  // ← この1行を追加
    if logger == nil {
        logger = slog.Default()
    }
    // ... 残りは既存のまま
```

`import` ブロックへ `"os"` が含まれていなければ追加する（現在の import は `"fmt"`, `"log/slog"`, `"strconv"`, `"strings"`, `ort "github.com/yalue/onnxruntime_go"` であり、`"os"` が不足している）：

```go
import (
    "fmt"
    "log/slog"
    "os"          // ← 追加
    "strconv"
    "strings"

    ort "github.com/yalue/onnxruntime_go"
)
```

### 2.3 device_test.go への追加テスト

`device_test.go` の末尾（`TestDeviceType_String` の後）に以下を追加する：

```go
func TestSelectDeviceWithEnv(t *testing.T) {
    tests := []struct {
        envVal string
        device string
        want   string
    }{
        {envVal: "cpu", device: "auto", want: "cpu"},
        {envVal: "cuda", device: "auto", want: "cuda"},
        {envVal: "coreml", device: "cpu", want: "coreml"},
        {envVal: "", device: "cpu", want: "cpu"},
        {envVal: "", device: "cuda", want: "cuda"},
        {envVal: "", device: "auto", want: "auto"},
    }
    for _, tt := range tests {
        t.Run(tt.envVal+"_"+tt.device, func(t *testing.T) {
            if tt.envVal != "" {
                t.Setenv("PIPER_EXECUTION_PROVIDER", tt.envVal)
            } else {
                t.Setenv("PIPER_EXECUTION_PROVIDER", "")
            }
            got := selectDeviceWithEnv(tt.device)
            if got != tt.want {
                t.Errorf("selectDeviceWithEnv(%q) with env=%q = %q, want %q",
                    tt.device, tt.envVal, got, tt.want)
            }
        })
    }
}

func TestConfigureSessionOptionsEnvVar(t *testing.T) {
    // PIPER_EXECUTION_PROVIDER=cpu の場合は CPU が選択されること
    // configureSessionOptions は実際の ORT セッションを作るため、
    // selectDeviceWithEnv のユニットテストで env var 制御を検証する。
    t.Setenv("PIPER_EXECUTION_PROVIDER", "cpu")
    result := selectDeviceWithEnv("auto")
    if result != "cpu" {
        t.Errorf("selectDeviceWithEnv(auto) with PIPER_EXECUTION_PROVIDER=cpu = %q, want %q",
            result, "cpu")
    }
}
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | `device.go` への `selectDeviceWithEnv()` 実装、`configureSessionOptions()` への1行追加、`"os"` import 追加 |
| Review Agent | 1 | Go の `t.Setenv` による env var 分離の確認、既存テストへの回帰影響確認、コントラクト準拠確認 |
| QA Agent | 1 | `go test ./piperplus/ -v` 全件 PASS 確認、env var をセット/アンセットした状態での go vet・staticcheck 実施 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/go/piperplus/device.go` | `selectDeviceWithEnv()` 追加（約10行）、`configureSessionOptions()` 先頭に1行追加、`"os"` import 追加 |
| `src/go/piperplus/device_test.go` | `TestSelectDeviceWithEnv`（約30行）、`TestConfigureSessionOptionsEnvVar`（約10行） |

スコープ外: `ParseDevice()`、`configureEP()`、`autoSelectEP()`、`appendCUDA()`、`appendTensorRT()` は変更しない。`go.mod`・`go.sum` も変更しない。

### Unit テスト

`selectDeviceWithEnv()` のユニットテスト（`TestSelectDeviceWithEnv`）の検証マトリクス：

| envVal | device | 期待返値 | 理由 |
|---|---|---|---|
| `"cpu"` | `"auto"` | `"cpu"` | env var が device を上書きする |
| `"cuda"` | `"auto"` | `"cuda"` | env var で明示指定 |
| `"coreml"` | `"cpu"` | `"coreml"` | env var で別 EP を強制 |
| `""` | `"cpu"` | `"cpu"` | env var 空 → device をそのまま返す |
| `""` | `"cuda"` | `"cuda"` | env var 空 → device をそのまま返す |
| `""` | `"auto"` | `"auto"` | env var 空 → "auto" のまま渡す（`autoSelectEP` に委譲） |

Go の `t.Setenv` は `testing.T` がスコープを管理し、サブテスト終了後に自動で元の値に復元するため、テスト間の env var 汚染が発生しない。

### E2E テスト

```bash
# env var なし: 従来動作（CPU 推論）
cd /Users/inamotoyuuta/Desktop/piper-plus/src/go
go run ./cmd/piper-plus/ \
  --model ../../test/models/multilingual-test-medium.onnx \
  --device cpu \
  --text "テスト" \
  --output /tmp/out.wav

# PIPER_EXECUTION_PROVIDER=cpu: 明示 CPU 強制
PIPER_EXECUTION_PROVIDER=cpu go run ./cmd/piper-plus/ \
  --model ../../test/models/multilingual-test-medium.onnx \
  --device auto \
  --text "テスト" \
  --output /tmp/out.wav

# macOS のみ: PIPER_EXECUTION_PROVIDER=coreml
PIPER_EXECUTION_PROVIDER=coreml go run ./cmd/piper-plus/ \
  --model ../../test/models/multilingual-test-medium.onnx \
  --text "テスト" \
  --output /tmp/out.wav
```

すべてのケースで出力 WAV ファイルが生成されること、RMS > 0 であること（音声ゼロ出力でないこと）を確認する。

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

#### 1. `selectDeviceWithEnv` が返す文字列が `ParseDevice` で検証される設計

`selectDeviceWithEnv` は env var の値をそのまま（lowercase + TrimSpace のみ）返す。`configureSessionOptions` はその後 `ParseDevice(device)` を呼び出すため、不正な env var 値（例: `PIPER_EXECUTION_PROVIDER=vulkan`）は `ParseDevice` のエラーになる。このエラーは `configureSessionOptions` の呼び出し元に `error` として伝播するため、ユーザーには「piperplus: unknown device provider "vulkan"」というエラーメッセージが届く。

この設計は意図的なものであり、env var バリデーションを `ParseDevice` に一元化している。ただし、エラーメッセージに `PIPER_EXECUTION_PROVIDER` 環境変数が原因であることを明示するために、`configureSessionOptions` 内で env var 由来の場合に追加のコンテキストをエラーに付加することを検討すべきである。

#### 2. `selectDeviceWithEnv` が返した文字列に対して `configureSessionOptions` が `device = selectDeviceWithEnv(device)` で上書きした後も `ParseDevice` がログに使うデバイス文字列が env var 由来であることを示さない

現状のログ出力（`logger.Info("ONNX Runtime execution provider configured", "device", selected.String())`）は選択された結果のみを示す。「なぜその EP が選ばれたか」（env var か引数か自動検出か）がログに残らない。運用上の問題になりうるため、`configureSessionOptions` 内で env var が使われた場合に `logger.Info("PIPER_EXECUTION_PROVIDER overrides device", "env", ep_value, "device_param", original_device)` を出力することを検討すべきである。

#### 3. `"os"` パッケージの import 追加

`device.go` の現行 import に `"os"` が含まれていない。`os.Getenv` を使うために追加が必要。Go の import 整理は `goimports` または `go fmt` で自動化できるが、CI が厳格な場合は `go vet` を通してから commit すること。

#### 4. `t.Setenv` の Go バージョン要件

`testing.T.Setenv` は Go 1.17 以降で利用可能。現在のプロジェクトの Go バージョンが 1.17 以上であることを `go.mod` で確認すること。

#### 5. `autoSelectEP` との連携

`selectDeviceWithEnv("auto")` が `"auto"` を返した場合、`ParseDevice("auto")` は `DeviceType{Provider: "auto", DeviceID: 0}` を返す。その後 `configureEP` が `case "auto": return autoSelectEP(sessOpts, logger)` に入る。これは意図した設計だが、env var に `"auto"` を設定した場合も同様に autoSelectEP に委譲されることを明示的にテストすることが望ましい。

### レビューチェックリスト

- [ ] `selectDeviceWithEnv` が `strings.ToLower(strings.TrimSpace(ep))` を適用しているか（大文字混じりの env var `"CUDA"` も正しく `"cuda"` に変換されるか）
- [ ] `configureSessionOptions` の `device = selectDeviceWithEnv(device)` が他の変数を変更しないか（ローカル変数への再代入のみ）
- [ ] 既存の `TestParseDevice`（14件）と `TestDeviceType_String`（5件）が変更の影響を受けないか（`go test ./piperplus/` で全件 PASS 確認）
- [ ] `"os"` の import 追加で `go vet ./piperplus/` が通過するか
- [ ] env var が `"tensorrt"` の場合（`PIPER_EXECUTION_PROVIDER=tensorrt`）に `selectDeviceWithEnv` が `"tensorrt"` を返し、`ParseDevice` → `configureEP` → `appendTensorRT` の経路に入るか
- [ ] `PIPER_EXECUTION_PROVIDER=COREML`（大文字）の場合に `strings.ToLower` で `"coreml"` に変換され `ParseDevice` が正常処理するか

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

Go の設計哲学「明示的であること」「シンプルであること」に従い、EP 選択ロジックは副作用（env var 読み取り、ORT へのプローブ）を外部から注入可能な形にすべきである。また、Go のインターフェースを活用して EP プローブをモック可能にし、実際の ORT ライブラリなしにテストできる設計が理想的である。

### アーキテクチャ

```go
// EPSelector は EP 選択の戦略を表すインターフェース
type EPSelector interface {
    // Select は利用可能な EP を返す。失敗時はエラーを返す。
    Select(sessOpts *ort.SessionOptions, logger *slog.Logger) (DeviceType, error)
}

// EnvVarSelector は PIPER_EXECUTION_PROVIDER を読み取る
type EnvVarSelector struct {
    Fallback EPSelector
}

func (e *EnvVarSelector) Select(sessOpts *ort.SessionOptions, logger *slog.Logger) (DeviceType, error) {
    ep := os.Getenv("PIPER_EXECUTION_PROVIDER")
    if ep == "" {
        return e.Fallback.Select(sessOpts, logger)
    }
    dev, err := ParseDevice(strings.ToLower(strings.TrimSpace(ep)))
    if err != nil {
        logger.Warn("PIPER_EXECUTION_PROVIDER invalid, falling back", "value", ep, "error", err)
        return e.Fallback.Select(sessOpts, logger)
    }
    logger.Info("EP selected from PIPER_EXECUTION_PROVIDER", "device", dev.String())
    return dev, nil
}

// AutoDetectSelector は自動検出（OnceLock 相当の sync.Once でキャッシュ）
type AutoDetectSelector struct {
    once   sync.Once
    result DeviceType
}

// ExplicitSelector は明示指定
type ExplicitSelector struct {
    Device DeviceType
}
```

`configureSessionOptions` のシグネチャを `func configureSessionOptions(selector EPSelector, logger *slog.Logger) (*ort.SessionOptions, error)` に変更し、EP 選択の依存を外部から注入する。

### 実装アプローチ

プロダクションコードでは `EnvVarSelector{Fallback: &AutoDetectSelector{}}` を使い、テストコードでは `ExplicitSelector{Device: DeviceType{"cpu", 0}}` をモックとして注入する。これにより:
- ORT ライブラリなしに EP 選択ロジックをテストできる
- `t.Setenv` による env var 操作が不要になり、テストが完全に決定的になる
- EP 選択の「理由」（env var / 明示 / 自動検出）が型として明示される

### 現行実装との主な差異

| 項目 | 現行 | Green Field |
|---|---|---|
| EP 選択の責務 | `configureSessionOptions` 内で直接処理 | `EPSelector` インターフェースに委譲 |
| env var の読み取り | `selectDeviceWithEnv` 関数（文字列変換のみ） | `EnvVarSelector` 型（バリデーション・フォールバック込み） |
| テスト方法 | `t.Setenv` で env var を操作 | モック `EPSelector` を注入（env var 操作不要） |
| ORT への依存 | テスト時も ORT が必要 | `EPSelector` 差し替えで ORT 不要 |
| キャッシュ | `autoSelectEP` を毎回呼ぶ（OnceLock は内部実装） | `AutoDetectSelector` の `sync.Once` で明示キャッシュ |
| ログの粒度 | 選択された EP のみ | 選択理由（型・ソース）も含む |

現行実装は差分最小の方針（既存の `configureEP`/`autoSelectEP` を維持しつつ薄いラッパーを追加）であり、リスクが低く学習コストも小さい。Green Field 設計は将来の大規模リファクタリング時の参考として活用できる。

Go の「シンプルさ」の哲学からすると、現行の薄いラッパー追加でも十分であり、インターフェース導入は過剰設計になる可能性もある。プロジェクト規模・チームの判断次第である。

---

## 7. 後続タスクへの引き継ぎ事項

### T-01（コントラクト更新）完了を前提として

T-05 は T-01（`ort-session-contract.toml` への EP 仕様追記）完了後に着手する。コントラクトの `override_var = "PIPER_EXECUTION_PROVIDER"` が確定している前提で `selectDeviceWithEnv` を実装するため、T-01 が未完了の場合は T-01 の実装内容を先に確認すること。

### 変更した内容の要約（T-08/T-09/T-10 担当者へ）

1. `device.go` に `func selectDeviceWithEnv(device string) string` が追加された。既存の `ParseDevice`, `configureEP`, `autoSelectEP` は変更なし（後方互換を維持）。
2. `configureSessionOptions()` が env var を認識するようになった。外部 API（関数シグネチャ）は変更なし。
3. `device.go` の import に `"os"` が追加された。
4. `PIPER_EXECUTION_PROVIDER` が設定されていない既存のユーザー環境では動作変化なし（完全後方互換）。
5. テストは `t.Setenv` を使用しているため env var の競合はない。`go test ./piperplus/ -count=1` で安全に実行可能。

### T-04（Rust）担当者との並行作業の注意点

T-04 と T-05 は並行実施可能。共有ファイルはなし。T-10（全体回帰テスト）では `cargo test --workspace` と `go test ./...` を順次実行するため、どちらかの変更が他言語のテストに影響しないことを事前に確認すること。

Go の `t.Setenv` は Rust の `std::env::set_var/remove_var` より安全（サブテスト終了時に自動復元）なため、Go 側のテスト実装は比較的シンプルである。Rust 側のテストでは `RUST_TEST_THREADS=1` が必要な場合があることに留意する（これは T-04 の引き継ぎ事項として記載済み）。
