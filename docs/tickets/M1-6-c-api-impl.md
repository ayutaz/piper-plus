# M1-6: `piper_plus_c_api.cpp` 実装

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 大
> **依存:** M1-5 (ヘッダー), M1-4 (CMake), M1-3 (dict_dir), M1-2 (-static-libstdc++)
> **ブロック:** M1-7, M1-8
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-6-piper_plus_c_apicpp-実装)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

`piper_plus.h` で宣言された Phase 1 の全 API 関数を実装する。C++ の `piper::` 名前空間の関数を C API でラップし、例外を API 境界で捕捉し、opaque handle パターンでメモリ安全性を確保する。

**ゴール:**
1. `create -> synthesize -> free_audio -> free` のライフサイクルが正常動作
2. 全 API 関数で NULL ポインタを渡してもクラッシュしない
3. `synthesisConfig` が呼び出し後に復元される (`languageId` 未復元バグの回避)
4. 合成中の再入は `PIPER_PLUS_ERR_BUSY` を返す
5. C++ 例外が API 境界の外に漏れない

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 状態 |
|----------|------|
| `src/cpp/piper_plus_c_api.cpp` | 新規作成 |

### 具体的な変更内容

#### 2.1 内部構造体とグローバル状態

```cpp
#include "piper_plus.h"
#include "piper.hpp"

#include <cstdlib>    // malloc, free
#include <cstring>    // memset
#include <string>
#include <atomic>

// Thread-local error message (lifetime: until next API call on the same thread)
static thread_local std::string g_last_error;

// Internal engine structure (hidden behind opaque PiperPlusEngine*)
struct PiperPlusEngine {
    piper::PiperConfig config;   // Empty struct (API compatibility)
    piper::Voice       voice;    // ONNX Session + config + dictionaries. Move-only.
    std::atomic<bool>  inProgress{false};  // Reentrancy guard
};

// Exception capture macros
#define PIPER_PLUS_TRY try {
#define PIPER_PLUS_CATCH(retval) \
    } catch (const std::exception& e) { \
        g_last_error = e.what(); \
        return retval; \
    } catch (...) { \
        g_last_error = "Unknown internal error"; \
        return retval; \
    }
```

#### 2.2 `piper_plus_version()` / `piper_plus_api_version()`

```cpp
const char* piper_plus_version(void) {
    // piper::getVersion() returns a static string from VERSION file
    static std::string version = piper::getVersion();
    return version.c_str();
}

int32_t piper_plus_api_version(void) {
    return PIPER_PLUS_API_VERSION;
}
```

#### 2.3 `piper_plus_get_last_error()`

```cpp
const char* piper_plus_get_last_error(void) {
    return g_last_error.empty() ? nullptr : g_last_error.c_str();
}
```

#### 2.4 `piper_plus_default_options()`

```cpp
PiperPlusSynthOptions piper_plus_default_options(void) {
    PiperPlusSynthOptions opts;
    memset(&opts, 0, sizeof(opts));
    opts.speaker_id = 0;
    opts.language_id = -1;   // Auto-detect
    opts.noise_scale = 0.667f;
    opts.length_scale = 1.0f;
    opts.noise_w = 0.8f;
    opts.sentence_silence_sec = 0.2f;
    return opts;
}
```

#### 2.5 `piper_plus_create()`

```cpp
PiperPlusEngine* piper_plus_create(const PiperPlusConfig* config) {
    PIPER_PLUS_TRY

    if (!config || !config->model_path) {
        g_last_error = "config and config->model_path must not be NULL";
        return nullptr;
    }

    // Set dictionary directory before loadVoice() triggers OpenJTalk init (M1-3)
    if (config->dict_dir && config->dict_dir[0] != '\0') {
#ifdef _WIN32
        _putenv_s("OPENJTALK_DICTIONARY_PATH", config->dict_dir);
#else
        setenv("OPENJTALK_DICTIONARY_PATH", config->dict_dir, 1);
#endif
    }

    // Auto-generate config_path if not specified
    std::string modelPath = config->model_path;
    std::string configPath;
    if (config->config_path && config->config_path[0] != '\0') {
        configPath = config->config_path;
    } else {
        configPath = modelPath + ".json";
    }

    // Determine CUDA usage
    bool useCuda = false;
    int gpuDeviceId = config->gpu_device_id;
    if (config->provider) {
        std::string provider(config->provider);
        if (provider == "cuda") {
            useCuda = true;
        }
        // CoreML / DirectML: future support (log warning and fallback to CPU)
    }

    auto engine = new PiperPlusEngine();

    piper::initialize(engine->config);

    std::optional<piper::SpeakerId> speakerId;
    piper::loadVoice(engine->config, modelPath, configPath,
                     engine->voice, speakerId, useCuda, gpuDeviceId);

    g_last_error.clear();
    return engine;

    PIPER_PLUS_CATCH(nullptr)
}
```

#### 2.6 `piper_plus_free()`

```cpp
void piper_plus_free(PiperPlusEngine* engine) {
    if (engine) {
        piper::terminate(engine->config);
        delete engine;
    }
}
```

#### 2.7 `piper_plus_synthesize()`

**重要:** `voice.synthesisConfig` を save/restore して `languageId` 未復元バグ (技術調査 5.1) を回避する。

```cpp
int32_t piper_plus_synthesize(
    PiperPlusEngine* engine,
    const char* text,
    const PiperPlusSynthOptions* opts,
    float** out_samples,
    int32_t* out_num_samples,
    int32_t* out_sample_rate)
{
    PIPER_PLUS_TRY

    // NULL checks
    if (!engine) {
        g_last_error = "engine must not be NULL";
        return PIPER_PLUS_ERR;
    }
    if (!text || text[0] == '\0') {
        g_last_error = "text must not be NULL or empty";
        return PIPER_PLUS_ERR_TEXT;
    }
    if (!out_samples || !out_num_samples || !out_sample_rate) {
        g_last_error = "output parameters must not be NULL";
        return PIPER_PLUS_ERR;
    }

    // Reentrancy guard
    bool expected = false;
    if (!engine->inProgress.compare_exchange_strong(expected, true)) {
        g_last_error = "Engine is busy (synthesis already in progress)";
        return PIPER_PLUS_ERR_BUSY;
    }

    // Save original synthesisConfig
    auto savedConfig = engine->voice.synthesisConfig;

    // Apply options
    PiperPlusSynthOptions options = opts ? *opts : piper_plus_default_options();

    engine->voice.synthesisConfig.noiseScale = options.noise_scale;
    engine->voice.synthesisConfig.lengthScale = options.length_scale;
    engine->voice.synthesisConfig.noiseW = options.noise_w;
    engine->voice.synthesisConfig.sentenceSilenceSeconds = options.sentence_silence_sec;

    if (options.speaker_id >= 0) {
        engine->voice.synthesisConfig.speakerId = options.speaker_id;
    }

    if (options.language_id >= 0) {
        engine->voice.synthesisConfig.languageId = options.language_id;
    } else {
        // language_id = -1: auto-detect (use default from model config)
        // Reset to default so textToAudio's auto-detection logic works correctly.
        if (engine->voice.modelConfig.numLanguages > 1) {
            engine->voice.synthesisConfig.languageId = 0;
        }
    }

    // Synthesize
    std::vector<int16_t> audioBuffer;
    piper::SynthesisResult result;
    piper::textToAudio(engine->config, engine->voice, std::string(text),
                       audioBuffer, result, nullptr);

    // Restore original synthesisConfig (critical: fixes languageId mutation bug)
    engine->voice.synthesisConfig = savedConfig;

    // Convert int16 -> float32
    int32_t numSamples = static_cast<int32_t>(audioBuffer.size());
    float* samples = static_cast<float*>(malloc(numSamples * sizeof(float)));
    if (!samples) {
        engine->inProgress.store(false);
        g_last_error = "Failed to allocate audio buffer";
        return PIPER_PLUS_ERR;
    }

    for (int32_t i = 0; i < numSamples; i++) {
        samples[i] = static_cast<float>(audioBuffer[i]) / 32768.0f;
    }

    *out_samples = samples;
    *out_num_samples = numSamples;
    *out_sample_rate = engine->voice.synthesisConfig.sampleRate;

    engine->inProgress.store(false);
    g_last_error.clear();
    return PIPER_PLUS_OK;

    PIPER_PLUS_CATCH((engine ? (engine->inProgress.store(false), PIPER_PLUS_ERR) : PIPER_PLUS_ERR))
}
```

#### 2.8 `piper_plus_free_audio()`

```cpp
void piper_plus_free_audio(float* samples) {
    free(samples);  // matches malloc() in synthesize()
}
```

#### 2.9 クエリ関数

```cpp
int32_t piper_plus_sample_rate(const PiperPlusEngine* engine) {
    if (!engine) return 0;
    return engine->voice.synthesisConfig.sampleRate;
}

int32_t piper_plus_num_speakers(const PiperPlusEngine* engine) {
    if (!engine) return 0;
    return engine->voice.modelConfig.numSpeakers;
}

int32_t piper_plus_num_languages(const PiperPlusEngine* engine) {
    if (!engine) return 0;
    return engine->voice.modelConfig.numLanguages;
}

int32_t piper_plus_language_id(const PiperPlusEngine* engine, const char* language_name) {
    if (!engine || !language_name) return -1;
    const auto& langMap = engine->voice.modelConfig.languageIdMap;
    if (!langMap) return -1;
    auto it = langMap->find(std::string(language_name));
    if (it == langMap->end()) return -1;
    return static_cast<int32_t>(it->second);
}
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | piper_plus_c_api.cpp の全関数実装 |
| レビューエージェント | 1 | 例外安全性、メモリ管理、synthesisConfig save/restore の正確性 |

合計: 2 名。C API ラッパーは piper-plus の公開インターフェースであり、メモリ安全性と例外安全性が特に重要。

---

## 4. 提供範囲とテスト項目

### スコープ

- `PiperPlusEngine` 内部構造体
- `thread_local std::string g_last_error`
- `PIPER_PLUS_TRY` / `PIPER_PLUS_CATCH` マクロ
- 全 Phase 1 API 関数の実装

### スコープ外

- Phase 2 の API (synth_start, synth_next, synthesize_streaming)
- テストコード (M1-7)
- `num_threads` の ORT SessionOptions 反映 (将来)

### テスト項目 (M1-7 で実装)

| テスト | 期待結果 |
|--------|----------|
| `version()` が非 NULL | `"1.10.0"` 等の文字列 |
| `api_version()` が `PIPER_PLUS_API_VERSION` と一致 | `1` |
| `default_options()` の各フィールド | デフォルト値に一致 |
| `create(NULL)` | NULL 返却 + `get_last_error()` 非 NULL |
| `create({model_path: "/nonexistent"})` | NULL 返却 + エラーメッセージ |
| `synthesize(NULL, ...)` | `PIPER_PLUS_ERR` |
| `free(NULL)` | クラッシュなし |
| `free_audio(NULL)` | クラッシュなし |
| `sample_rate(NULL)` | 0 |
| `num_speakers(NULL)` | 0 |
| `num_languages(NULL)` | 0 |
| `language_id(NULL, "ja")` | -1 |
| `synthesize` 中の再入 | `PIPER_PLUS_ERR_BUSY` (モデル必要テスト) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `synthesisConfig` の save/restore が不完全 | **高** | `auto savedConfig = engine->voice.synthesisConfig;` で全フィールドをコピー。`SynthesisConfig` は POD 的構造 (std::optional を含む) だが、コピー可能。例外時も catch ブロックで `inProgress` をリセット |
| `PIPER_PLUS_CATCH` 内の `inProgress` リセット | **高** | catch ブロック内で `engine->inProgress.store(false)` を呼ぶが、`engine` が NULL の場合がある。三項演算子で NULL チェック |
| `malloc` / `free` の DLL 境界越え | 中 | C ランタイムの `malloc` / `free` を使用。`piper_plus_free_audio()` が同一 DLL 内で `free` を呼ぶため安全。ユーザーが `delete[]` で解放するバグを防ぐため、専用関数を提供 |
| `textToAudio` が内部で `languageId` を変更する | **高** | L1279 で `voice.synthesisConfig.languageId` が auto-detect 値に上書きされる。save/restore で対処。技術調査 5.1 参照 |
| int16 -> float32 変換のオーバーヘッド | 低 | 将来 M4-5 で float 出力バリアントを追加して解消。Phase 1 では許容 |

### レビュー項目

- [ ] `g_last_error` が `thread_local` であるか
- [ ] 全 API 関数で NULL チェックが行われているか
- [ ] `piper_plus_synthesize()` で `synthesisConfig` が save/restore されているか
- [ ] `inProgress` フラグが例外発生時にもリセットされるか
- [ ] `piper_plus_free_audio()` が `free()` を使用しているか (`delete` ではない)
- [ ] `piper_plus_create()` で `setenv` が `loadVoice()` より前に呼ばれているか
- [ ] `config_path` が NULL の場合に `model_path + ".json"` が生成されるか
- [ ] C++ 例外が `extern "C"` 関数の外に漏れないか

---

## 6. 一から作り直すとしたら

### synthesisConfig の immutability

`textToAudio()` が `synthesisConfig` を内部変更する設計が根本的な問題。理想的には `textToAudio()` が `const SynthesisConfig&` を受け取り、内部で可変コピーを作成する設計にする。ただし、既存の C++ API を変更するのは Phase 1 のスコープ外。

### RAII によるリソース管理

`inProgress` フラグのリセットを try-catch ではなく RAII ガードで管理する:

```cpp
struct SynthGuard {
    PiperPlusEngine& engine;
    piper::SynthesisConfig savedConfig;

    SynthGuard(PiperPlusEngine& e) : engine(e), savedConfig(e.voice.synthesisConfig) {
        engine.inProgress.store(true);
    }
    ~SynthGuard() {
        engine.voice.synthesisConfig = savedConfig;
        engine.inProgress.store(false);
    }
};
```

この方式なら例外発生時も確実にリセットされ、`PIPER_PLUS_CATCH` マクロ内の複雑な条件分岐が不要になる。

### float 出力ネイティブ対応

C++ 側の `synthesize()` に float 出力パスを追加すれば、int16 -> float32 変換のステップが不要になる。ONNX Runtime の出力は元々 float なので、int16 経由は本来不要なオーバーヘッド。

---

## 7. 後続タスクへの連絡事項

- **M1-7 (テスト):** このチケットで実装した全関数について、モデル不要のテストケースを作成すること。特に NULL 安全性と `get_last_error()` の動作確認。
- **M1-8 (CI):** `piper_plus_c_api.cpp` が CMake のソースリストに含まれており、`-DPIPER_PLUS_BUILD_SHARED=ON` でビルドされることを確認すること。
- **Phase 2 (M2-1, M2-2):** `PiperPlusEngine` struct に `IteratorState` (文分割キュー、currentChunkSamples) を追加する際、`inProgress` フラグとの統合に注意。Iterator 中の `synthesize` 呼び出しも `PIPER_PLUS_ERR_BUSY` を返すこと。
- **`piper_plus_synthesize()` の synthesisConfig restore について:** save/restore は例外安全でなければならない。上記の RAII ガード方式を Phase 2 で導入することを推奨。
