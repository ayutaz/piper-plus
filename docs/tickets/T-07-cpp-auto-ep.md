# T-07: C++ piper.cpp に "auto" EP モード、main.cpp に env var 追加

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01（ort-session-contract.toml EP 仕様追記）
**後続タスク:** T-10（全体回帰テスト）

---

## 1. タスク目的とゴール

### 目的

`src/cpp/piper.cpp` と `src/cpp/main.cpp` に以下の機能を追加し、C++ ランタイムを他の 4 ランタイム（Python / Rust / C# / Go）と同水準の EP 対応に引き上げる。

1. **`provider == "auto"` の auto-detect モード** (`piper.cpp`) — ORT C-API の `GetAvailableProviders` を使って利用可能な EP を列挙し、CUDA → CoreML → DirectML → CPU の順に初期化を試みる
2. **`PIPER_EXECUTION_PROVIDER` 環境変数対応** (`main.cpp`) — CLI フラグ `--use-cuda` / `--provider` より優先して EP を指定できるようにする
3. **help テキストへの環境変数追記** (`main.cpp`) — `printUsage()` に `PIPER_EXECUTION_PROVIDER` の説明を追記する

### Done 基準

- `piper.cpp:loadModel()` で `provider == "auto"` または `provider == ""` が auto-detect として動作する
- CoreML は `#ifdef __APPLE__` でガード、DirectML は `#ifdef PIPER_HAS_DIRECTML`（既存マクロ）でガード
- `main.cpp:parseArgs()` で `PIPER_EXECUTION_PROVIDER` が `PIPER_GPU_DEVICE_ID` の前に読まれ、provider 変数に反映される
- `printUsage()` に `PIPER_EXECUTION_PROVIDER` の説明が追加される
- `cmake -B build/cpp -S src/cpp && cmake --build build/cpp --parallel` がエラーなしで完了する
- smoke test: `--provider auto` で CPU フォールバックが動作する

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

- **主要変更:** `src/cpp/piper.cpp`（`loadModel()` 関数、437行目付近）
- **main.cpp 変更:** `src/cpp/main.cpp`（`parseArgs()` 関数、792行目付近 + `printUsage()` 関数、773行目付近）

### 2.2 現状の piper.cpp の EP 処理構造

現在（452行目付近）の実装：

```cpp
// Execution provider selection
if (provider == "cuda") {
    OrtCUDAProviderOptions cuda_options{};
    cuda_options.device_id = gpuDeviceId;
    cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
    session.options.AppendExecutionProvider_CUDA(cuda_options);
    spdlog::info("Using CUDA execution provider with GPU device ID: {}", gpuDeviceId);
} else if (provider == "coreml") {
#ifdef __APPLE__
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CoreML(session.options, 0));
    spdlog::info("Using CoreML execution provider");
#else
    throw std::runtime_error("CoreML is only available on macOS/iOS");
#endif
} else if (provider == "directml") {
#ifdef PIPER_HAS_DIRECTML
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_DML(session.options, gpuDeviceId));
    spdlog::info("Using DirectML execution provider with device ID: {}", gpuDeviceId);
#elif defined(_WIN32)
    throw std::runtime_error("DirectML support requires the DirectML ONNX Runtime package");
#else
    throw std::runtime_error("DirectML is only available on Windows");
#endif
} else if (!provider.empty() && provider != "cpu") {
    throw std::runtime_error("Unknown provider: " + provider);
}
```

### 2.3 piper.cpp への変更: "auto" モードの追加

既存の `} else if (!provider.empty() && provider != "cpu") {` の**直前**に `provider == "auto"` のブロックを挿入する。

```cpp
} else if (provider == "auto" || provider.empty()) {
    // Auto-detect: CUDA → CoreML → DirectML → CPU
    // ORT 1.17 C-API: GetAvailableProviders
    const OrtApi* ort_api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    char** available_eps = nullptr;
    int num_eps = 0;
    OrtStatus* status = ort_api->GetAvailableProviders(&available_eps, &num_eps);
    if (status == nullptr && available_eps != nullptr) {
        auto has_ep = [&](const std::string& name) -> bool {
            for (int i = 0; i < num_eps; ++i) {
                if (std::string(available_eps[i]) == name) return true;
            }
            return false;
        };
        bool configured = false;

        // 1. CUDA
        if (!configured && has_ep("CUDAExecutionProvider")) {
            try {
                OrtCUDAProviderOptions cuda_opts{};
                cuda_opts.device_id = gpuDeviceId;
                cuda_opts.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
                session.options.AppendExecutionProvider_CUDA(cuda_opts);
                spdlog::info("Auto-detected: using CUDA execution provider (device={})",
                             gpuDeviceId);
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("CUDA EP initialization failed: {}, trying next EP", e.what());
            }
        }

        // 2. CoreML (macOS/iOS のみ)
#ifdef __APPLE__
        if (!configured && has_ep("CoreMLExecutionProvider")) {
            try {
                Ort::ThrowOnError(
                    OrtSessionOptionsAppendExecutionProvider_CoreML(session.options, 0));
                spdlog::info("Auto-detected: using CoreML execution provider");
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("CoreML EP initialization failed: {}, trying next EP", e.what());
            }
        }
#endif

        // 3. DirectML (Windows のみ)
#ifdef PIPER_HAS_DIRECTML
        if (!configured && has_ep("DmlExecutionProvider")) {
            try {
                Ort::ThrowOnError(
                    OrtSessionOptionsAppendExecutionProvider_DML(session.options, gpuDeviceId));
                spdlog::info("Auto-detected: using DirectML execution provider (device={})",
                             gpuDeviceId);
                configured = true;
            } catch (const std::exception& e) {
                spdlog::warn("DirectML EP initialization failed: {}, trying next EP", e.what());
            }
        }
#endif

        ort_api->ReleaseAvailableProviders(available_eps, num_eps);

        if (!configured) {
            spdlog::info("Auto-detect: no hardware EP available, using CPU execution provider");
        }
    } else {
        // GetAvailableProviders 自体が失敗した場合は CPU フォールバック
        spdlog::warn("GetAvailableProviders failed, using CPU execution provider");
        if (status != nullptr) {
            ort_api->ReleaseStatus(status);
        }
    }
```

**変更後の完全な EP 選択ブロック構造:**

```
if (provider == "cuda") {
    ...
} else if (provider == "coreml") {
    ...
} else if (provider == "directml") {
    ...
} else if (provider == "auto" || provider.empty()) {   // ← 新規追加
    ...
} else if (!provider.empty() && provider != "cpu") {  // ← 既存: "unknown" エラー
    throw std::runtime_error("Unknown provider: " + provider);
}
// それ以外 (provider == "cpu") は何もしない → CPU フォールバック
```

### 2.4 main.cpp への変更: PIPER_EXECUTION_PROVIDER 環境変数

`parseArgs()` の `PIPER_GPU_DEVICE_ID` 読み取りブロック（792行目）の**前**に追加する。

```cpp
// PIPER_EXECUTION_PROVIDER は --provider / --use-cuda CLI フラグより優先
const char* epEnv = std::getenv("PIPER_EXECUTION_PROVIDER");
if (epEnv != nullptr && strlen(epEnv) > 0) {
    runConfig.provider = std::string(epEnv);
    spdlog::info("Execution provider set from PIPER_EXECUTION_PROVIDER: {}",
                 runConfig.provider);
}
```

**注意:** `runConfig.provider` フィールドが存在しない場合（現在は `useCuda: bool` と `gpuDeviceId: int` のみ）、`RunConfig` 構造体に `std::string provider = "auto";` を追加する必要がある。既存の `--use-cuda` フラグは後方互換のため残し、`provider = "cuda"` に変換する：

```cpp
} else if (arg == "--use_cuda" || arg == "--use-cuda") {
    runConfig.provider = "cuda";  // 既存: runConfig.useCuda = true; と同等
```

または `useCuda` フラグを残したまま `loadModel()` 呼び出し前に変換する：

```cpp
// loadModel() 呼び出し前
if (runConfig.useCuda && runConfig.provider == "auto") {
    runConfig.provider = "cuda";
}
```

### 2.5 main.cpp への変更: help テキスト追記

`printUsage()` の環境変数セクション（776行目付近）に追記する。

```cpp
cerr << "environment variables:" << endl;
cerr << "   PIPER_DEFAULT_MODEL           default model path (if --model not specified)" << endl;
cerr << "   PIPER_DEFAULT_CONFIG          default config file path" << endl;
cerr << "   PIPER_MODEL_DIR               default model directory (if --model-dir not specified)" << endl;
cerr << "   PIPER_GPU_DEVICE_ID           GPU device ID for CUDA" << endl;
// ↓ 追加
cerr << "   PIPER_EXECUTION_PROVIDER      Execution provider: auto|cpu|cuda[:<id>]|coreml|directml[:<id>]|tensorrt[:<id>]" << endl;
cerr << endl;
```

### 2.6 既存コードへの影響確認

`loadModel()` は `piper.cpp:437行目` で定義される。呼び出し元を確認してシグネチャ変更の影響がないことを確認する。`provider` が文字列として渡される既存呼び出しパターン：

- デフォルト引数がある場合: `loadModel(modelPath, session, "")` → `provider.empty()` として auto-detect に入る
- `"cpu"` が渡される場合: 既存の `provider != "cpu"` 条件が `provider.empty() || provider == "cpu"` の後に評価されるため動作は変わらない

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | piper.cpp の auto-detect ブロック追加（コンパイルガード含む）、main.cpp の env var 読み取りと printUsage() 更新 |
| Build/Test Agent | 1 | cmake ビルド実行、smoke test 実行、警告ゼロを確認 |
| Review Agent | 1 | コンパイルガードの正確性（`#ifdef __APPLE__` / `#ifdef PIPER_HAS_DIRECTML`）、GetAvailableProviders の RAII 処理（ReleaseAvailableProviders）、例外ハンドリング、既存 `--use-cuda` との後方互換 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/cpp/piper.hpp` | `RunConfig` 構造体に `std::string provider = "auto";` フィールド追加 |
| `src/cpp/piper.cpp` | `loadModel()` に `provider == "auto"` / `provider.empty()` の auto-detect ブロック追加 |
| `src/cpp/main.cpp` | `parseArgs()` に `PIPER_EXECUTION_PROVIDER` env var 読み取り追加。`printUsage()` に env var 説明追記 |

**スコープ外:**
- OpenVINO EP（コンパイル時フラグ `PIPER_USE_OPENVINO` を予約するが、本 Issue では実装しない）
- TensorRT EP（auto-detect 対象外。明示指定のサポートは将来 Issue）
- C++ ユニットテストの新規追加（既存の smoke test で代替）

### Unit テスト

C++ はビルド検証と smoke test で代替する。厳密なユニットテストは将来 Issue で対応予定。

| 検証内容 | 方法 |
|---|---|
| `provider == "auto"` で CPU フォールバックが動作する | smoke test: `--provider auto` |
| `PIPER_EXECUTION_PROVIDER=cpu` が provider を上書きする | env var 設定後に smoke test 実行 |
| `--use-cuda` が引き続き動作する | 既存回帰テスト |
| `GetAvailableProviders` が返す EP 名の確認 | デバッグログ（`--debug` オプション） |

### E2E テスト

```bash
# CPU フォールバック確認
build/cpp/piper --model test/models/multilingual-test-medium.onnx \
  --provider auto --output-raw - <<< "test" > /dev/null && echo "PASS"

# PIPER_EXECUTION_PROVIDER 環境変数確認
PIPER_EXECUTION_PROVIDER=cpu \
build/cpp/piper --model test/models/multilingual-test-medium.onnx \
  --output-raw - <<< "test" > /dev/null && echo "PASS"

# 既存の --use-cuda 後方互換確認（CUDA なし環境では CPU にフォールバック）
build/cpp/piper --model test/models/multilingual-test-medium.onnx \
  --use-cuda --output-raw - <<< "test" > /dev/null && echo "PASS (with fallback)"
```

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **`OrtGetApiBase()->GetApi(ORT_API_VERSION)->GetAvailableProviders` の可用性:** ORT 1.17.0 以降に存在する API。`ort-versions.md` 記載のバージョンであることを確認すること。古い ORT ライブラリとリンクされている場合はリンクエラーになる。
2. **`ReleaseAvailableProviders` の呼び出し忘れ:** `GetAvailableProviders` が成功した場合は必ず `ReleaseAvailableProviders` を呼ぶ必要がある。例外が途中で発生しても解放されるよう、RAII ラッパーか `unique_ptr` + カスタムデリータを検討する。
3. **`provider.empty()` の挙動変更:** 現在 `provider.empty()` は「何もしない（CPU）」として扱われているが、変更後は auto-detect に入る。既存の呼び出しで `provider = ""` を意図的に渡している箇所がないか確認すること。
4. **`runConfig.provider` フィールドの追加:** 既存コードが `runConfig.useCuda` を直接参照している箇所がある場合、`provider` への移行が必要。`loadModel()` への引数渡しを確認すること。
5. **Windows ビルドでの `PIPER_HAS_DIRECTML` の状態:** DirectML ヘッダーが存在しない Windows ビルドでは `PIPER_HAS_DIRECTML` が未定義になるため、auto-detect ブロックから DirectML 部分が除外される。この動作が意図的であることをコメントに明記すること。
6. **`OrtStatus*` の解放:** `GetAvailableProviders` が失敗して `status != nullptr` になった場合、`ReleaseStatus` を呼ぶ必要がある。実装例のコードに含まれているが、レビュー時に確認すること。

### レビューチェックリスト

- [ ] `#ifdef __APPLE__` が CoreML のみを囲んでいること（CUDA/DirectML には不要）
- [ ] `#ifdef PIPER_HAS_DIRECTML` が DirectML ブロックを囲んでいること（既存パターンと一致）
- [ ] `ReleaseAvailableProviders` が必ず呼ばれていること（正常系・例外系の両方）
- [ ] `ReleaseStatus` が失敗時に呼ばれていること
- [ ] `provider == "auto"` ブロックが `provider != "cpu"` の `throw` より**前**に配置されていること
- [ ] `PIPER_EXECUTION_PROVIDER` が `PIPER_GPU_DEVICE_ID` の読み取り**前**に処理されていること
- [ ] `--use-cuda` フラグが後方互換で動作すること（`provider = "cuda"` への変換）
- [ ] spdlog の INFO/WARN ログレベルが設計仕様に従っていること（auto-detect 結果は INFO、失敗は WARN）
- [ ] `printUsage()` の環境変数リストに `PIPER_EXECUTION_PROVIDER` が追加されていること
- [ ] cmake ビルドが `-Wall` / `-Wextra` 相当の警告設定で警告ゼロであること

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

C++ の強みであるゼロコストアブストラクション（テンプレート・コンパイル時条件分岐）を活かし、EP の登録・検出・適用を型安全かつ拡張可能な仕組みにする。実行時の文字列比較を排除し、コンパイル時に利用可能な EP が確定する設計にする。

### アーキテクチャ

```cpp
// 理想形: EP アダプターの静的登録
// try_append は非キャプチャラムダを生関数ポインタとして保持（std::function は不要かつ constexpr 非対応）
struct EpDescriptor {
    const char* ort_name;     // "CUDAExecutionProvider"
    const char* piper_name;   // "cuda"
    int priority;             // auto-detect 優先度
    bool(*try_append)(Ort::SessionOptions&, int);  // 生関数ポインタ（非キャプチャラムダから暗黙変換可）
};

// EP レジストリ: inline static const（std::vector は constexpr 非対応のため constexpr 不採用）
// コンパイル時フラグで有効エントリが決まり、起動時に一度だけ初期化される
inline static const std::vector<EpDescriptor> EP_REGISTRY = {
    {
        "CUDAExecutionProvider", "cuda", 10,
        [](Ort::SessionOptions& opts, int dev) -> bool {
            OrtCUDAProviderOptions o{}; o.device_id = dev;
            o.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchHeuristic;
            opts.AppendExecutionProvider_CUDA(o);
            return true;
        }
    },
#ifdef __APPLE__
    {
        "CoreMLExecutionProvider", "coreml", 20,
        [](Ort::SessionOptions& opts, int) -> bool {
            Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CoreML(opts, 0));
            return true;
        }
    },
#endif
#ifdef PIPER_HAS_DIRECTML
    {
        "DmlExecutionProvider", "directml", 30,
        [](Ort::SessionOptions& opts, int dev) -> bool {
            Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_DML(opts, dev));
            return true;
        }
    },
#endif
};

// auto-detect: EP_REGISTRY を priority 順にソートして try_append
std::string auto_detect_ep(Ort::SessionOptions& opts, int device_id);
```

### 実装アプローチ

- `EpDescriptor` の `try_append` に `Ort::Exception` キャッチを内包させることで、`loadModel()` 本体から例外処理を分離
- `EP_REGISTRY` は `inline static const` にし起動時に一度だけ初期化する（`std::vector` は `constexpr` 非対応のため `constexpr` は不採用。`std::function` も `constexpr` 非対応かつオーバーヘッドがあるため生関数ポインタを使用）
- 環境変数の読み取りは `main.cpp` の `parseArgs()` に完全に分離し、`piper.cpp` は `provider` 文字列のみを受け取る（関心の分離）
- `RAII` ラッパー: `GetAvailableProviders` の結果を `std::unique_ptr` + カスタムデリータで包み、解放漏れを防ぐ

```cpp
// RAII ラッパー案
struct AvailableProviders {
    char** list = nullptr;
    int count = 0;
    const OrtApi* api;
    ~AvailableProviders() {
        if (list) api->ReleaseAvailableProviders(list, count);
    }
    bool has(const std::string& name) const { ... }
};
```

### 現行実装との主な差異

| 観点 | 現行実装 | 理想形 |
|---|---|---|
| EP 登録 | if-else if の手動連鎖 | `EP_REGISTRY` への宣言的登録 |
| 拡張性 | 新 EP 追加時に if ブロックを手動挿入 | `EP_REGISTRY` に `EpDescriptor` を追加するだけ |
| 解放安全性 | `ReleaseAvailableProviders` を手動呼び出し | RAII ラッパーで自動解放 |
| テスタビリティ | `loadModel()` が ORT に直接依存 | `try_append` を差し替え可能な関数ポインタとして DI |
| 環境変数 | `parseArgs()` と `loadModel()` の両方に分散 | `parseArgs()` のみで処理、`loadModel()` は純粋に EP 設定のみ |
| コンパイルガード | ブロック中間に `#ifdef` が混在 | `EP_REGISTRY` の初期化リストで `#ifdef` が集中 |

---

## 7. 後続タスクへの引き継ぎ事項

後続タスク（T-10: 全体回帰テスト）の担当者へ：

1. **`provider` フィールドの追加:** `RunConfig` 構造体に `std::string provider = "auto";` が追加される（または `useCuda` から変換される）。C++ ランタイムの他のコードが `runConfig.useCuda` を直接参照している場合は `runConfig.provider == "cuda"` への移行が必要。
2. **`provider.empty()` の挙動変更:** 変更前は「何もしない（CPU）」、変更後は auto-detect に入る。既存のテストで `provider = ""` を渡しているものがあれば動作が変わる可能性があるため確認すること。
3. **OpenVINO の予約:** 設計仕様では `PIPER_USE_OPENVINO` というコンパイル時フラグを将来用に予約する。本 Issue では実装しないが、`else if (!provider.empty() && provider != "cpu")` の `throw` 前に `"openvino"` が渡された場合の挙動を考慮しておくこと（現状は "Unknown provider" エラーになる）。
4. **ビルドの前提条件:** `coreml_provider_factory.h` は macOS の ORT ライブラリに含まれる（既存コードで `#include <coreml_provider_factory.h>` が `#ifdef __APPLE__` でガード済み、1行目付近）。`dml_provider_factory.h` は Windows の DirectML パッケージに含まれる（`#define PIPER_HAS_DIRECTML 1` が既存コードで設定済み）。
5. **smoke test の前提:** テストモデル `test/models/multilingual-test-medium.onnx` が存在することを前提とする。存在しない場合はモデルダウンロードが必要。
