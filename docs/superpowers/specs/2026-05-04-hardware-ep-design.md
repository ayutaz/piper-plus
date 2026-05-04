# Hardware Execution Provider 自動選択 — 設計仕様

**Issue:** #382
**Branch:** `feat/hardware-ep`
**Date:** 2026-05-04
**Author:** yousan

---

## 1. 背景と目的

現在 piper-plus の全ランタイムは ONNX Runtime (ORT) の CPU Execution Provider (EP) を基本とし、学習側（`ort_utils.py`）と Python ランタイム（`voice.py`）に限り CUDA EP の自動検出が実装されている。CoreML (macOS/iOS)・DirectML (Windows)・OpenVINO (Intel CPU) は未対応。

本仕様は **モデル・品質への変更なし** に、利用可能なハードウェアアクセラレーターを起動時に自動検出して最適な EP を選択するロジックを、全 5 ネイティブランタイム（Python / Rust / C# / C++ / Go）に統一実装する。

### 期待効果

| 環境 | EP | 期待ゲイン |
|---|---|---|
| macOS / iOS (Apple Silicon) | CoreML | 3〜10x |
| NVIDIA GPU | CUDA | 5〜20x（既存拡張） |
| Windows | DirectML | 2〜5x |
| Intel CPU | OpenVINO | 1.5〜3x |
| 上記なし | CPU | 変化なし（フォールバック） |

WASM はブラウザのサンドボックス制限により対象外。onnxruntime-web は SIMD 最適化をすでに利用している。

---

## 2. EP 選択ロジック

### 2.1 優先度順

```
PIPER_EXECUTION_PROVIDER 環境変数（明示指定）
  ↓ なければ自動検出
TensorRT  （NVIDIA GPU、TensorRT インストール済み）
CUDA      （NVIDIA GPU）
CoreML    （macOS / iOS）
DirectML  （Windows）
OpenVINO  （Intel CPU + OpenVINO インストール済み）
CPU       （フォールバック、常に利用可能）
```

- 自動検出は ORT の `get_available_providers()` 相当の API を利用
- EP が利用可能でも初期化に失敗した場合は次の EP に降格し警告ログを出す
- 実際に使用した EP を起動時にログ出力する（INFO レベル）

### 2.2 環境変数

`PIPER_EXECUTION_PROVIDER` で明示的に EP を上書きできる。

| 値 | 意味 |
|---|---|
| `cpu` | CPU EP 強制（デフォルト動作相当） |
| `cuda` / `cuda:0` / `cuda:1` | CUDA EP（デバイス番号指定可） |
| `coreml` | CoreML EP |
| `directml` / `directml:0` | DirectML EP（デバイス番号指定可） |
| `openvino` | OpenVINO EP |
| `tensorrt` | TensorRT EP |
| （未設定） | 優先度順に自動選択 |

既存の `PIPER_INTRA_THREADS`, `PIPER_DISABLE_WARMUP`, `PIPER_DISABLE_CACHE` は変更なし。

---

## 3. キャッシュファイル命名規則

現行は `model.cpu.opt.onnx` / `model.cuda0.opt.onnx`。EP ごとに最適化グラフが異なるため、EP ラベルをファイル名に含める。

| EP | device_label | キャッシュ例 |
|---|---|---|
| CPU | `cpu` | `model.cpu.opt.onnx` |
| CUDA (device 0) | `cuda0` | `model.cuda0.opt.onnx` |
| CUDA (device 1) | `cuda1` | `model.cuda1.opt.onnx` |
| CoreML | `coreml` | `model.coreml.opt.onnx` |
| DirectML (device 0) | `directml0` | `model.directml0.opt.onnx` |
| OpenVINO | `openvino` | `model.openvino.opt.onnx` |
| TensorRT | `tensorrt0` | `model.tensorrt0.opt.onnx` |

- センチネルファイルは `.opt.onnx.ok` のまま（拡張子ペアを保持）
- CoreML / OpenVINO は外部コンポーネントにグラフを渡すため ORT 最適化グラフが存在しない場合がある。その場合はキャッシュを生成せず毎回ロードする（`PIPER_DISABLE_CACHE` 相当）

---

## 4. ORT パッケージ要件

### Python

| EP | 必要パッケージ |
|---|---|
| CPU / CoreML | `onnxruntime`（macOS では CoreML が自動有効） |
| CUDA / TensorRT | `onnxruntime-gpu` |
| DirectML | `onnxruntime-directml`（Windows のみ） |
| OpenVINO | `onnxruntime-openvino` または ORT with OpenVINO EP ビルド |

インストール方法はユーザー側の選択とし、piper-plus はインストール済みの EP を自動検出するのみ。`pyproject.toml` の optional dependencies として `gpu` / `coreml` グループを定義する。

### Rust (`ort` crate)

Cargo features で EP を有効化：

```toml
[dependencies]
ort = { version = "2", features = ["cuda", "tensorrt", "coreml", "directml", "openvino"] }
```

EP が使用できなくてもコンパイルは通る（featureの有無は利用可否フラグ）。デフォルトの `Cargo.toml` は `["cuda", "coreml"]` を有効にし、CI マトリクスで全 EP をテストする。

### C#

| EP | NuGet パッケージ |
|---|---|
| CPU | `Microsoft.ML.OnnxRuntime` |
| CUDA / TensorRT | `Microsoft.ML.OnnxRuntime.Gpu` |
| DirectML | `Microsoft.ML.OnnxRuntime.DirectML` |

プロジェクトファイルで条件付き参照（`$(UseGpu)` / `$(UseDirectML)` MSBuild プロパティ）を追加。

### Go

`onnxruntime_go` ライブラリは事前ビルド済み共有ライブラリを使用。EP 対応の共有ライブラリを差し替えることで各 EP を有効化できる。環境変数 `ORT_DYLIB_PATH` で切り替える。

### C++

CMakeLists でコンパイルオプション追加：

```cmake
option(PIPER_USE_CUDA    "Enable CUDA EP"    OFF)
option(PIPER_USE_COREML  "Enable CoreML EP"  OFF)
option(PIPER_USE_DIRECTML "Enable DirectML EP" OFF)
option(PIPER_USE_OPENVINO "Enable OpenVINO EP" OFF)
```

---

## 5. 実装詳細

### 5.1 Python (`ort_utils.py`)

現行の `get_providers(device: str)` を拡張する。

```python
EP_PRIORITY = [
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider",
    "CoreMLExecutionProvider",
    "DmlExecutionProvider",
    "OpenVINOExecutionProvider",
    "CPUExecutionProvider",
]

def get_providers(device: str = "auto") -> list[str | tuple[str, dict]]:
    """
    device: "auto" | "cpu" | "cuda" | "cuda:N" | "coreml" |
            "directml" | "directml:N" | "openvino" | "tensorrt"
    """
    env = os.environ.get("PIPER_EXECUTION_PROVIDER", "").lower()
    target = env or device

    if target == "cpu":
        return ["CPUExecutionProvider"]

    available = onnxruntime.get_available_providers()

    if target == "auto":
        for ep in EP_PRIORITY:
            if ep in available:
                return [ep, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    # 明示指定: "cuda:1" → ("CUDAExecutionProvider", {"device_id": 1})
    ep_name, ep_opts = _parse_ep_target(target)
    if ep_name in available:
        return [(ep_name, ep_opts), "CPUExecutionProvider"]
    logger.warning("Requested EP %s not available, falling back to CPU", ep_name)
    return ["CPUExecutionProvider"]
```

- EP 初期化失敗時は `except OrtException` をキャッチして次の EP に降格
- `voice.py` でも同じ `get_providers()` を呼び出す（重複実装を統一）

### 5.2 Rust (`engine.rs`)

```rust
fn select_execution_providers(config: &EngineConfig) -> Vec<ExecutionProviderDispatch> {
    // 1. PIPER_EXECUTION_PROVIDER env var
    // 2. auto-detect: TensorRT → CUDA → CoreML → DirectML → OpenVINO → CPU
    // 3. 初期化失敗時は warn!() して次へ降格
}
```

`ort` crate の `Session::builder().with_execution_providers(...)` に渡す。

### 5.3 C# (`SessionFactory.cs`)

```csharp
private static SessionOptions CreateSessionOptions(ExecutionProvider ep)
{
    return ep switch
    {
        ExecutionProvider.Cuda => SessionOptions.MakeSessionOptionWithCudaProvider(...),
        ExecutionProvider.DirectML => SessionOptions.MakeSessionOptionWithDirectMLProvider(...),
        ExecutionProvider.CoreML => opts with CoreML appended,
        ExecutionProvider.Cpu => new SessionOptions(),
        _ => new SessionOptions(),
    };
}
```

### 5.4 C++ (`piper.cpp`)

`Ort::SessionOptions` に `AppendExecutionProvider_*` を条件付きで呼び出す。コンパイル時フラグで EP の有無を制御。

### 5.5 Go (`session.go` 相当)

`onnxruntime_go` の `NewSessionOptions()` に EP を設定。共有ライブラリの差し替えで対応。

---

## 6. `ort-session-contract.toml` への追記

```toml
[execution_provider]
# EP 選択の優先度順（全実装共通）
priority = [
    "TensorRT",
    "CUDA",
    "CoreML",
    "DirectML",
    "OpenVINO",
    "CPU",
]

[execution_provider.env]
override_var = "PIPER_EXECUTION_PROVIDER"
# 値: "cpu" | "cuda" | "cuda:N" | "coreml" | "directml" | "directml:N" | "openvino" | "tensorrt"

[cache.device_labels]
cpu        = "cpu"
cuda       = "cuda{device_id}"    # e.g., "cuda0"
coreml     = "coreml"
directml   = "directml{device_id}"
openvino   = "openvino"
tensorrt   = "tensorrt{device_id}"

# 注: CoreML / OpenVINO EP も ORT グラフ最適化キャッシュ（.opt.onnx）は通常通り生成する。
# ただし EP 側が内部で別形式にコンパイルする場合（CoreML mlpackage 等）は起動時間が増加する
# ことがあるため、実測後にキャッシュ戦略を調整する。
```

---

## 7. CI / ビルドマトリクス追加

| Runner | EP | テスト内容 |
|---|---|---|
| `ubuntu-24.04` + NVIDIA (self-hosted) | CUDA | 推論完了・音声品質 smoke test |
| `macos-14` (Apple Silicon) | CoreML | 推論完了・音声品質 smoke test |
| `windows-2025` | DirectML | 推論完了・音声品質 smoke test |
| `ubuntu-24.04` Intel (self-hosted) | OpenVINO | 推論完了・音声品質 smoke test |

GPU / OpenVINO ランナーは self-hosted のため PR CI ではオプション、release CI で実行。

---

## 8. テスト戦略

### ユニットテスト（全 EP 共通）

- `get_providers("auto")` が利用可能な EP を返すこと
- `get_providers("cpu")` が常に `["CPUExecutionProvider"]` を返すこと
- 存在しない EP 指定時に警告を出して CPU にフォールバックすること
- EP ラベルからキャッシュファイル名が正しく生成されること

### 統合テスト

- 各 EP で `test/models/multilingual-test-medium.onnx` の合成が完了し、音声の RMS > 0 であること
- CPU EP 出力と他 EP 出力の音声が `max(abs(diff)) < 1e-2`（float32）以内に一致すること（数値誤差許容）

### 回帰テスト

- CPU EP での既存テストが全て通ること（新規 EP 追加で既存動作を壊さない）

---

## 9. 実装スコープと除外

### スコープ内

- Python / Rust / C# / C++ / Go の 5 ランタイムへの EP 自動選択実装
- `ort-session-contract.toml` の更新
- `docs/spec/ort-versions.md` への EP 対応状況追記
- CI マトリクスの追加（smoke test レベル）

### スコープ外（将来 Issue）

- WASM: onnxruntime-web の WebGPU EP 対応（ブラウザ API の成熟を待つ）
- TensorRT: 詳細な精度検証（本 Issue では基本動作のみ）
- モデル変換（CoreML mlpackage 形式への変換）: ORT の CoreML EP はモデル変換不要のため対象外

---

## 10. 実装順序

1. `ort-session-contract.toml` に EP 仕様を追記（全ランタイムの実装基準）
2. Python ランタイム（`ort_utils.py` + `voice.py`）— 最も素早く検証可能
3. Rust ランタイム（`engine.rs`）— クロスプラットフォームのメイン
4. C# ランタイム（`SessionFactory.cs`）
5. C++ ランタイム（`piper.cpp`）
6. Go ランタイム（`session.go` 相当）
7. CI マトリクス追加
8. ドキュメント更新（`ort-versions.md`, README）
