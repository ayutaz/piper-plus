# M5-6: CoreML / DirectML provider 対応

> **Phase:** 5 -- 品質改善
> **利用者視点の優先度:** 中 -- macOS / Windows で GPU 推論を利用したいユーザー
> **見積り:** 小
> **依存:** Phase 1 完了 (M1-6)
> **ブロック:** なし
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`PiperPlusConfig.provider` は `"cpu"` / `"cuda"` のみ対応している。`"coreml"` (macOS/iOS) と `"directml"` (Windows) を追加し、ORT の Execution Provider として反映する。

**現状:** `piper_plus_create()` は `provider == "cuda"` のみ分岐し、`useCuda` フラグを `loadVoice()` に渡している。`loadVoice()` / `loadModel()` は CUDA EP のみ実装済み。

**ゴール:** `provider` 文字列 `"coreml"`, `"directml"` を `OrtSessionOptionsAppendExecutionProvider_*` に反映する。不明な provider はエラーを返す。

---

## 2. 実装する内容の詳細

### 2.1 piper.cpp (`loadModel`) の変更

CUDA 分岐に加えて CoreML / DirectML を追加:

```cpp
if (provider == "cuda") {
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CUDA(options, gpuDeviceId));
} else if (provider == "coreml") {
#ifdef __APPLE__
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_CoreML(options, 0));
#else
    throw std::runtime_error("CoreML is only available on macOS/iOS");
#endif
} else if (provider == "directml") {
#ifdef _WIN32
    Ort::ThrowOnError(OrtSessionOptionsAppendExecutionProvider_DML(options, gpuDeviceId));
#else
    throw std::runtime_error("DirectML is only available on Windows");
#endif
}
```

### 2.2 piper.hpp / piper.cpp の変更

`loadVoice` / `loadModel` の `useCuda` パラメータを `provider` 文字列に変更:

```cpp
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice,
               std::optional<SpeakerId> &speakerId,
               const std::string &provider = "cpu",
               int gpuDeviceId = 0, int numThreads = 0);
```

### 2.3 piper_plus_c_api.cpp の変更

`piper_plus_create()` で `config->provider` を直接 `loadVoice()` に渡す:

```cpp
std::string provider = (config->provider && config->provider[0] != '\0')
                       ? config->provider : "cpu";
piper::loadVoice(engine->config, modelPath, configPath,
                 engine->voice, speakerId, provider, gpuDeviceId, numThreads);
```

### 2.4 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper.hpp` | `loadVoice` の `useCuda` を `provider` 文字列に変更 |
| `src/cpp/piper.cpp` | `loadModel` / `loadVoice` で CoreML / DirectML EP 追加 |
| `src/cpp/piper_plus_c_api.cpp` | `provider` 文字列を `loadVoice` に渡す |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | Provider 分岐実装 + テスト |

合計 1 名。

---

## 4. 提供範囲とテスト項目

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestProviderNull` | `provider=NULL` でエンジン作成 | CPU フォールバック |
| `TestProviderCpu` | `provider="cpu"` | 正常作成 |
| `TestProviderUnknown` | `provider="tpu"` | `PIPER_PLUS_ERR` + エラーメッセージ |

### プラットフォーム依存テスト

| テスト | プラットフォーム | 期待結果 |
|--------|------------------|----------|
| `TestProviderCoreml` | macOS (CI) | EP 登録成功 (推論は ORT ビルド依存) |
| `TestProviderDirectml` | Windows (CI) | EP 登録成功 (推論は ORT ビルド依存) |

---

## 5. 懸念事項とレビュー項目

| リスク | 影響度 | 対策 |
|--------|--------|------|
| ORT ビルドに CoreML/DirectML EP が含まれていない場合 | 中 | `#ifdef` ガードで未対応プラットフォームはコンパイルエラーを回避、ランタイムエラーを返す |
| `useCuda` -> `provider` の変更が CLI に影響 | 低 | CLI 側の `--cuda` オプションを `provider="cuda"` に変換する互換コード追加 |
| CoreML は FP16 モデルのみ対応の可能性 | 低 | ドキュメントに注記 |

### レビュー時の確認項目

1. `useCuda` を使用していた全呼び出し元が `provider` 文字列に移行していること
2. 不明な provider 文字列がエラーを返すこと (黙って CPU にフォールバックしない)
3. CoreML / DirectML の `#ifdef` ガードが正しいこと

---

## 6. 一から作り直すとしたら

Provider 文字列ではなく enum を使う設計の方が型安全。ただし C API では文字列の方が拡張性が高く (新 EP 追加時にヘッダー変更不要)、Dart/Swift の FFI でも扱いやすい。現設計を維持する。

---

## 7. 後続タスクへの連絡事項

- **M5-5 (num_threads):** `loadVoice` のシグネチャ変更が重複する。同時実装が効率的。
- **M5-11 (Android):** Android NDK ビルドでは NNAPI EP (`onnxruntime_providers_nnapi`) も候補。M5-11 で `"nnapi"` provider を追加検討。
