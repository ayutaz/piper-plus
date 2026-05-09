# Hardware Execution Provider 自動選択 — 設計仕様

**Issue:** #382
**Branch:** `feat/hardware-ep`
**Date:** 2026-05-04 (rev.2 — レビュー反映)
**Author:** yousan

---

## 1. 背景と目的

現在 piper-plus の全ランタイムは ONNX Runtime (ORT) の CPU Execution Provider (EP) を基本とし、学習側（`ort_utils.py`）と Python ランタイム（`voice.py`）に限り CUDA EP の自動検出が実装されている。Rust (`gpu.rs`) と Go (`device.go`) にも CUDA/CoreML/DirectML の部分実装が存在するが、コントラクト未定義でランタイム間の動作が統一されていない。CoreML / DirectML / OpenVINO は Python/C#/C++ では未対応。

本仕様は **モデル・品質への変更なし** に、利用可能なハードウェアアクセラレーターを起動時に自動検出して最適な EP を選択するロジックを、全 5 ネイティブランタイム（Python / Rust / C# / C++ / Go）で統一する。

### 期待効果

| 環境 | EP | 期待ゲイン |
|---|---|---|
| macOS / iOS (Apple Silicon) | CoreML | 3〜10x |
| NVIDIA GPU | CUDA | 5〜20x（既存拡張） |
| Windows | DirectML | 2〜5x |
| Intel CPU | OpenVINO | 1.5〜3x（Python のみ、後述） |
| 上記なし | CPU | 変化なし（フォールバック） |

WASM はブラウザのサンドボックス制限により対象外。onnxruntime-web は SIMD 最適化をすでに利用している。

### 各ランタイムの現状

| ランタイム | 実装状況 | 差分作業 |
|---|---|---|
| Python (`ort_utils.py`, `voice.py`) | CUDA のみ部分実装 | CoreML/DirectML/OpenVINO 追加、API 統一 |
| Rust (`gpu.rs`) | CUDA/CoreML/DirectML 実装済み（auto_detect_device あり） | `PIPER_EXECUTION_PROVIDER` env var 対応、コントラクト準拠確認 |
| C# (`SessionFactory.cs`) | CUDA/DirectML 実装済み | CoreML 追加、auto-detect ロジック追加 |
| Go (`device.go`) | CUDA/CoreML/DirectML/TensorRT 実装済み（autoSelectEP あり） | `PIPER_EXECUTION_PROVIDER` env var 対応 |
| C++ (`piper.cpp`) | CUDA のみ実装、明示指定のみ | auto-detect プローブ追加（後述） |

---

## 2. EP 選択ロジック

### 2.1 自動検出の優先度

TensorRT は初回実行時のカーネルコンパイルが 5〜30 分に及び、エンジンキャッシュの無効化条件も複雑であるため、**自動検出の対象外**とする。既存の Rust `auto_detect_device()` も同様に TensorRT を除外しており、本仕様はこれに倣う。

```
PIPER_EXECUTION_PROVIDER 環境変数（明示指定）
  ↓ なければ自動検出
CUDA      （NVIDIA GPU）
CoreML    （macOS / iOS）
DirectML  （Windows）
OpenVINO  （Intel CPU + OpenVINO インストール済み / Python のみ）
CPU       （フォールバック、常に利用可能）
```

- 自動検出は ORT の `get_available_providers()` 相当の API を利用
- EP が利用可能でも初期化に失敗した場合は次の EP に降格し警告ログを出す
- 実際に使用した EP を起動時にログ出力する（INFO レベル）
- OpenVINO は Python 以外ではスコープ外（後述）

### 2.2 環境変数

`PIPER_EXECUTION_PROVIDER` で明示的に EP を上書きできる。TensorRT は自動検出対象外だが、明示指定は可能。

| 値 | 意味 |
|---|---|
| `cpu` | CPU EP 強制 |
| `cuda` / `cuda:0` / `cuda:1` | CUDA EP（デバイス番号指定可） |
| `coreml` | CoreML EP |
| `directml` / `directml:0` | DirectML EP（デバイス番号指定可） |
| `openvino` | OpenVINO EP（Python のみ） |
| `tensorrt` / `tensorrt:0` | TensorRT EP（明示指定のみ） |
| （未設定） | 優先度順に自動選択 |

### 2.3 `PIPER_GPU_DEVICE_ID` との関係

C# (`SessionFactory.cs`) と C++ (`main.cpp`) では既存の `PIPER_GPU_DEVICE_ID` 環境変数で CUDA デバイスを指定していた。`PIPER_EXECUTION_PROVIDER` が設定されている場合はそちらを優先する。両方設定された場合: `PIPER_EXECUTION_PROVIDER=cuda` かつ `PIPER_GPU_DEVICE_ID=1` → device 1 の CUDA EP を使用（互換性維持）。`PIPER_EXECUTION_PROVIDER=cuda:1` と `PIPER_GPU_DEVICE_ID` が競合する場合は `PIPER_EXECUTION_PROVIDER` を優先する。

既存の `PIPER_INTRA_THREADS`, `PIPER_DISABLE_WARMUP`, `PIPER_DISABLE_CACHE` は変更なし。

---

## 3. キャッシュファイル命名規則

現行の既存 flat キーを拡張する（`[cache.device_labels]` サブテーブルは使用しない）。

| EP | device_label | キャッシュ例 |
|---|---|---|
| CPU | `cpu` | `model.cpu.opt.onnx` |
| CUDA (device 0) | `cuda0` | `model.cuda0.opt.onnx` |
| CUDA (device 1) | `cuda1` | `model.cuda1.opt.onnx` |
| CoreML | `coreml` | `model.coreml.opt.onnx` |
| DirectML (device 0) | `directml0` | `model.directml0.opt.onnx` |
| OpenVINO | `openvino` | `model.openvino.opt.onnx` |
| TensorRT (device 0) | `tensorrt0` | `model.tensorrt0.opt.onnx` |

- センチネルファイルは `.opt.onnx.ok` のまま（既存の拡張子ペアを保持）
- CoreML EP: ORT グラフ最適化キャッシュ（`.opt.onnx`）は通常通り生成する。CoreML の ANE コンパイルは ORT セッション初期化時に内部で行われ、キャッシュファイルには含まれない。そのため CoreML 利用時は初回セッション初期化が数秒かかる場合がある。実測後にキャッシュ戦略を調整する。
- TensorRT EP: ORT とは別にエンジンキャッシュを生成する。本 Issue ではキャッシュパスの設定は行わず、TensorRT のデフォルト動作に従う。

---

## 4. ORT パッケージ要件とランタイムスコープ

### Python

| EP | 必要パッケージ |
|---|---|
| CPU / CoreML | `onnxruntime`（macOS では CoreML が自動有効） |
| CUDA / TensorRT | `onnxruntime-gpu` |
| DirectML | `onnxruntime-directml`（Windows のみ） |
| OpenVINO | `onnxruntime-openvino` |

インストール方法はユーザー側の選択とし、piper-plus はインストール済みの EP を自動検出するのみ。`src/python_run/pyproject.toml` の optional dependencies として以下のグループを追加：

```toml
[project.optional-dependencies]
gpu = ["onnxruntime-gpu"]
directml = ["onnxruntime-directml"]
openvino = ["onnxruntime-openvino"]
# CoreML は onnxruntime に含まれるため追加不要
```

### Rust (`ort` crate)

バージョンは `ort-versions.md` 記載の `2.0.0-rc.12` に固定：

```toml
[dependencies]
ort = { version = "=2.0.0-rc.12", features = ["cuda", "coreml", "directml"] }
```

TensorRT feature は明示指定時のみ有効にする（auto-detect 対象外のため、デフォルト features には含めない）。`gpu.rs` の `auto_detect_device()` は既存実装を流用し、`PIPER_EXECUTION_PROVIDER` env var 対応を追加する。

### C#

| EP | NuGet パッケージ | スコープ |
|---|---|---|
| CPU | `Microsoft.ML.OnnxRuntime` | 対象 |
| CUDA / TensorRT | `Microsoft.ML.OnnxRuntime.Gpu` | 対象 |
| DirectML | `Microsoft.ML.OnnxRuntime.DirectML` | 対象 |
| CoreML | `Microsoft.ML.OnnxRuntime`（macOS ビルド） | 対象 |
| OpenVINO | — NuGet パッケージなし | **スコープ外** |

OpenVINO は `Microsoft.ML.OnnxRuntime` NuGet に含まれないため C# では対象外。

### Go

`onnxruntime_go` はすでに CUDA/CoreML/DirectML をサポートする共有ライブラリを使用。`device.go` の `autoSelectEP` 実装を流用し、`PIPER_EXECUTION_PROVIDER` env var 対応を追加する。OpenVINO は共有ライブラリの差し替えが必要なため、本 Issue ではスコープ外。

### C++

既存の `provider` 文字列パラメータ（`"cuda"`, `"coreml"`, `"directml"`, `"cpu"`）に加え、auto-detect を追加する。

ORT 1.17.0 C-API には `OrtApiBase::GetApi` 経由で `GetAvailableProviders` が存在する。C++ の auto-detect はこれを使用する：

```cpp
// ORT 1.17 C-API による利用可能 EP 列挙
const OrtApi* api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
char** providers;
int num_providers;
api->GetAvailableProviders(&providers, &num_providers);
// → 列挙して優先度順に試みる
api->ReleaseAvailableProviders(providers, num_providers);
```

利用可能 EP への `AppendExecutionProvider_*` が失敗した場合は `try-catch(Ort::Exception)` で捕捉して CPU にフォールバック。OpenVINO はスコープ外（コンパイル時フラグ `PIPER_USE_OPENVINO` を追加するが、デフォルト OFF で本 Issue では検証しない）。

---

## 5. 実装詳細

### 5.1 Python (`ort_utils.py` + `voice.py`)

**`ort_utils.py`**: 現行の `get_providers(device: str)` を拡張する。

```python
# TensorRT は auto-detect 対象外（明示指定時のみ）
EP_AUTO_PRIORITY = [
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
    "OpenVINOExecutionProvider",
    "CPUExecutionProvider",
]

def get_providers(device: str = "auto") -> list[str | tuple[str, dict]]:
    """
    device: "auto" | "cpu" | "cuda" | "cuda:N" | "coreml" |
            "directml" | "directml:N" | "openvino" | "tensorrt" | "tensorrt:N"
    """
    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower()
    target = env or device

    if target == "cpu":
        return ["CPUExecutionProvider"]

    available = onnxruntime.get_available_providers()

    if target == "auto":
        for ep in EP_AUTO_PRIORITY:
            if ep in available:
                logger.info("Using execution provider: %s", ep)
                return [ep, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    # 明示指定: "cuda:1" → ("CUDAExecutionProvider", {"device_id": 1})
    ep_name, ep_opts = _parse_ep_target(target)
    if ep_name in available:
        return [(ep_name, ep_opts), "CPUExecutionProvider"]
    logger.warning("Requested EP %s not available, falling back to CPU", ep_name)
    return ["CPUExecutionProvider"]
```

EP 初期化失敗時は `onnxruntime.OrtException` をキャッチして CPU にフォールバック（`load_onnx_model` 内で try-except を追加）。

**`voice.py` API 変更**: 既存の `use_cuda: bool` パラメータを非推奨にし、`device: str = "auto"` を追加する。

```python
# 変更前
@classmethod
def load(cls, model_path, config_path, use_cuda: bool = False, ...) -> "PiperVoice":

# 変更後
@classmethod
def load(cls, model_path, config_path,
         use_cuda: bool = False,   # deprecated, 後方互換のため残す
         device: str = "auto",     # 新規: "auto"|"cpu"|"cuda"|"coreml"|...
         ...) -> "PiperVoice":
    # use_cuda=True かつ device="auto" の場合は device="cuda" として扱う（移行期の互換）
    if use_cuda and device == "auto":
        device = "cuda"
```

### 5.2 Rust (`gpu.rs`)

既存の `auto_detect_device()` / `configure_session_builder()` を流用。差分作業は `PIPER_EXECUTION_PROVIDER` env var の読み取りを `auto_detect_device()` の先頭に追加するのみ：

```rust
pub fn auto_detect_device() -> DeviceType {
    // 1. PIPER_EXECUTION_PROVIDER env var を確認
    if let Ok(ep) = std::env::var("PIPER_EXECUTION_PROVIDER") {
        return parse_device_string(&ep).unwrap_or(DeviceType::Cpu);
    }
    // 2. 既存の自動検出ロジック（TensorRT は対象外、既存実装と一致）
    // ...
}
```

`configure_session_builder(builder, &device_type)` は変更なし。

### 5.3 C# (`SessionFactory.cs`)

```csharp
// 疑似コード — TryAppendCoreMLProvider 等の実際の ORT C# API を参照
private static SessionOptions CreateSessionOptions(ExecutionProvider ep, int deviceId = 0)
{
    return ep switch
    {
        ExecutionProvider.Cuda =>
            SessionOptions.MakeSessionOptionWithCudaProvider(deviceId),
        ExecutionProvider.DirectML =>
            SessionOptions.MakeSessionOptionWithDirectMLProvider(deviceId),
        ExecutionProvider.CoreML =>
            CreateWithCoreML(),   // OrtApis.AppendExecutionProvider_CoreML
        ExecutionProvider.Cpu => new SessionOptions(),
        _ => new SessionOptions(),
    };
}
```

auto-detect は `OrtEnv.Instance.GetAvailableProviders()` を使用して EP_AUTO_PRIORITY 順に試みる。OpenVINO は C# スコープ外のため `switch` に含めない。

### 5.4 C++ (`piper.cpp`)

`provider == "auto"` の場合に `OrtGetApiBase()->GetApi(ORT_API_VERSION)->GetAvailableProviders` で列挙し、優先度順（CUDA → CoreML → DirectML → CPU）に `AppendExecutionProvider_*` を試みる。失敗時は `Ort::Exception` で捕捉して次の EP に降格。

```cpp
// 疑似コード
if (provider == "auto") {
    char** eps; int n;
    ort_api->GetAvailableProviders(&eps, &n);
    for (auto pref : {"CUDA", "CoreML", "DML"}) {
        if (is_available(eps, n, pref)) {
            try { append_ep(session_options, pref, gpu_device_id); break; }
            catch (const Ort::Exception&) { /* 次へ */ }
        }
    }
    ort_api->ReleaseAvailableProviders(eps, n);
}
```

### 5.5 Go (`device.go`)

`autoSelectEP()` は実装済み。差分は `PIPER_EXECUTION_PROVIDER` env var の読み取りを先頭に追加するのみ：

```go
func selectDevice(requested string) DeviceType {
    if ep := os.Getenv("PIPER_EXECUTION_PROVIDER"); ep != "" {
        requested = ep
    }
    if requested == "auto" || requested == "" {
        return autoSelectEP()  // 既存実装
    }
    return parseDeviceString(requested)
}
```

---

## 6. `ort-session-contract.toml` への追記

既存の flat キー構造を拡張する（サブテーブルは使用しない）。

```toml
# --- 新規追加セクション ---

[execution_provider]
# 自動検出の優先度順（TensorRT は auto-detect 対象外 — 明示指定のみ）
auto_priority = ["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]
# OpenVINO は Python のみ対応。C#/C++/Go/Rust ではスコープ外。

[execution_provider.env]
override_var = "PIPER_EXECUTION_PROVIDER"
# 値: "cpu" | "cuda" | "cuda:N" | "coreml" | "directml" | "directml:N"
#     | "openvino" | "tensorrt" | "tensorrt:N"
# TensorRT は auto-detect 対象外だが明示指定は可能

# --- 既存 [cache] セクションへの flat key 追記 ---
# 既存: device_label_cpu / device_label_cuda_format に追加

[cache]
# ... 既存キーはそのまま ...
device_label_coreml          = "coreml"
device_label_directml_format = "directml{device_id}"   # e.g., "directml0"
device_label_openvino        = "openvino"
device_label_tensorrt_format = "tensorrt{device_id}"   # e.g., "tensorrt0"

# --- 既存 [env_vars.implementation_status] への追記 ---
#                        Rust    C#     C++    Python   Go
# ep auto-detect         ✓       ✓      ✓      ✓        ✓
# ep env var             ✓       ✓      ✓      ✓        ✓
# openvino ep            -       -      -      ✓        -
```

---

## 7. CI / ビルドマトリクス追加

| Runner | EP | テスト内容 |
|---|---|---|
| `ubuntu-24.04` + NVIDIA (self-hosted) | CUDA | 推論完了・smoke test |
| `macos-14` (Apple Silicon) | CoreML | 推論完了・smoke test |
| `windows-2022` | DirectML | 推論完了・smoke test |
| `ubuntu-24.04` Intel (self-hosted) | OpenVINO (Python のみ) | 推論完了・smoke test |

GPU / OpenVINO ランナーは self-hosted のため PR CI ではオプション、release CI で実行。

---

## 8. テスト戦略

### ユニットテスト（全 EP 共通）

- `get_providers("auto")` が利用可能な EP を返すこと
- `get_providers("cpu")` が常に `["CPUExecutionProvider"]` を返すこと
- 存在しない EP 指定時に警告を出して CPU にフォールバックすること
- EP ラベルからキャッシュファイル名が正しく生成されること
- TensorRT が自動検出に含まれないこと

### 統合テスト（smoke test）

- 各 EP で `test/models/multilingual-test-medium.onnx` の合成が完了すること
- 出力音声に NaN が含まれないこと、RMS > 0 であること（品質の最低保証）
- CPU EP との数値比較は行わない（EP 間で FP 演算順序が異なるため差分が大きくなり得る）

### 回帰テスト

- CPU EP での既存テストが全て通ること

---

## 9. 実装スコープと除外

### スコープ内

- Python / Rust / C# / C++ / Go の 5 ランタイムへの EP 自動選択統一
- `ort-session-contract.toml` の更新
- `docs/spec/ort-versions.md` への EP 対応状況追記
- CI マトリクスの追加（smoke test レベル）

### スコープ外（将来 Issue）

- WASM: onnxruntime-web の WebGPU EP 対応
- TensorRT: 詳細な精度検証・エンジンキャッシュ管理
- OpenVINO: Python 以外のランタイム対応
- `PIPER_GPU_DEVICE_ID` の正式 deprecation（本 Issue では後方互換を維持するのみ）

---

## 10. 実装順序

1. `ort-session-contract.toml` に EP 仕様を追記（全ランタイムの実装基準）
2. Python ランタイム（`ort_utils.py` + `voice.py`）— 最も素早く検証可能
3. Rust ランタイム（`gpu.rs` env var 対応）— 差分が最小
4. Go ランタイム（`device.go` env var 対応）— 差分が最小
5. C# ランタイム（`SessionFactory.cs` auto-detect + CoreML 追加）
6. C++ ランタイム（`piper.cpp` auto-detect プローブ追加）
7. CI マトリクス追加
8. ドキュメント更新（`ort-versions.md`, README）
