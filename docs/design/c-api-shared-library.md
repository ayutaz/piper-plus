# C API 共有ライブラリ (Issue #295) — 要求定義書

> **Status:** Draft
> **Issue:** [#295](https://github.com/ayutaz/piper-plus/issues/295)
> **Branch:** `feature/c-api-shared-library`
> **Date:** 2026-04-02

---

## 1. 目的

piper-plus の C++ 実装を共有ライブラリ (`.dll` / `.so` / `.dylib`) + `extern "C"` ヘッダーとして公開し、他言語から FFI で利用可能にする。

### 1.1 解決する課題

piper-plus は既に Rust / Python / Go / C# / JS(WASM) でネイティブライブラリを提供しているが、C API (`.so`/`.dylib`/`.dll` + `extern "C"`) が存在しないため、**C FFI に依存するプラットフォーム**からの利用がブロックされている:

| ユースケース | 必要なバインディング | 現状 |
|---|---|---|
| Flutter/Dart アプリ | `dart:ffi` (C のみ) | **不可** |
| Godot GDExtension | C バインディング | piper-plus C++ ソースを丸ごとコピーして直接ビルド ([godot-piper-plus](https://github.com/ayutaz/godot-piper-plus)) — 保守コスト大 |
| Swift / iOS アプリ | C interop | **不可** |

#### 1.1.1 Godot GDExtension の現状と課題

[godot-piper-plus](https://github.com/ayutaz/godot-piper-plus) は C API がないため、piper-plus の C++ ソース 25+ ファイルを `src/piper_core/` にコピー (vendor) して GDExtension に直接コンパイルしている。

**現在の技術的課題:**

| 課題 | 詳細 |
|------|------|
| ソース同期の保守コスト | piper-plus 更新のたびに 25+ ファイルの手動コピー + 改変が必要 |
| 日本語のみ対応 | 8言語 G2P 中、OpenJTalk (日本語) のみ統合。英語 G2P は未実装 (TODO) |
| 複雑なビルドシステム | 227行 CMakeLists.txt + ExternalProject で OpenJTalk/HTSEngine をソースからクロスコンパイル |
| 手動改変が必要 | spdlog → no-op シム差替え、eSpeak 除去、PhonemeType 再番号付け等 |
| ABI 不安定 | C++ 名前空間を直接呼び出すため、コンパイラ・標準ライブラリの一致が必要 |

**C API 共有ライブラリがあれば:**

| 項目 | 現状 (ソースコピー) | C API 方式 |
|------|-------------------|-----------|
| GDExtension 側ソースファイル | 25+ | **4** (register_types + TTS ノード) |
| ビルドスクリプト | 227行 CMake + ExternalProject | **~30行** |
| 多言語 G2P | 日本語のみ | **8言語が即時利用可能** |
| piper-plus 更新の追従 | ファイルコピー + 手動改変 | **ヘッダー + バイナリ差し替えのみ** |
| OpenJTalk/HTSEngine ビルド | GDExtension 側でクロスコンパイル | **不要 (C API に内包)** |

> **参考:** [godot-kokoro](https://github.com/PhilNikitin/godot-kokoro) が sherpa-onnx の C API 共有ライブラリを GDExtension から利用する方式で同パターンを実証済み (SConstruct 43行、ソースファイル 4つのみ)。

> **Note:** 以下の言語は既にネイティブライブラリが提供済みのため、C API は不要。
>
> | 言語 | パッケージ | 提供形態 |
> |------|-----------|---------|
> | Rust | `piper-plus` クレート (`src/rust/piper-core/`) | `PiperVoice::synthesize_text()` 等の完全な TTS API |
> | Python | `piper-plus` PyO3 バインディング (`src/rust/piper-python/`) | `PiperVoice.synthesize()` + numpy 統合 |
> | Go | `github.com/ayutaz/piper-plus/src/go` (`src/go/piperplus/`) | `Voice.Synthesize()` + HTTP API サーバー |
> | C# | `PiperPlus.Core` (`src/csharp/PiperPlus.Core/`) | `PiperSession` + NuGet 配布準備済み |
> | JS/WASM | `piper-plus` npm (`src/wasm/openjtalk-web/`) | `PiperPlus.synthesize()` + ストリーミング |

---

## 2. 先行事例の調査結果

### 2.1 endo5501 の実装 (`feat/support_cpp_library`)

[@endo5501](https://github.com/endo5501) が Flutter FFI 用の C API ラッパーを実装済み。

**変更ファイル (3件):**
- `src/cpp/piper_tts_c_api.h` (48行)
- `src/cpp/piper_tts_c_api.cpp` (135行)
- `CMakeLists.txt` (+122行)

**提供 API:**

```c
// Lifecycle
piper_tts_ctx* piper_tts_init(const char* model_path, const char* dic_dir);
int             piper_tts_is_loaded(const piper_tts_ctx* ctx);
void            piper_tts_free(piper_tts_ctx* ctx);

// Synthesis
int             piper_tts_synthesize(piper_tts_ctx* ctx, const char* text);

// Parameters
int             piper_tts_set_length_scale(piper_tts_ctx* ctx, float value);
int             piper_tts_set_noise_scale(piper_tts_ctx* ctx, float value);
int             piper_tts_set_noise_w(piper_tts_ctx* ctx, float value);

// Result access
const float*    piper_tts_get_audio(const piper_tts_ctx* ctx);
int             piper_tts_get_audio_length(const piper_tts_ctx* ctx);
int             piper_tts_get_sample_rate(const piper_tts_ctx* ctx);
const char*     piper_tts_get_error(const piper_tts_ctx* ctx);
```

**評価:**

| 項目 | 評価 |
|------|------|
| opaque handle パターン | 良い — FFI 安全 |
| エラーハンドリング | 良い — int 戻り値 + `get_error()` |
| float32 変換 | 良い — Flutter audio plugin 互換 |
| クロスプラットフォーム export | 良い — Windows/Unix 両対応 |
| visibility hidden デフォルト | 良い — シンボル隠蔽 |

**不足点 (issue #295 の Proposed API との差分):**

| 不足項目 | 詳細 | 重要度 |
|----------|------|--------|
| speaker_id 未対応 | マルチスピーカーモデルで話者切替不可 | **必須** |
| language 未対応 | 多言語モデルで言語指定不可 | **必須** |
| config_path が暗黙的 | `model_path + ".json"` にハードコード | **必須** |
| 辞書パスが `setenv` 依存 | プロセスグローバルな副作用 | 高 |
| CUDA/GPU 未対応 | `useCuda=false` ハードコード | 中 |
| ストリーミング未対応 | 同期合成のみ | 中 |
| バージョン API なし | ライブラリバージョン確認不可 | 低 |
| スレッドセーフティ未文書化 | 並行利用の安全性不明 | 低 |

### 2.2 類似 TTS エンジンの C API

#### sherpa-onnx (最も参考になる設計)

piper-plus と同じ VITS + ONNX Runtime 構成。Flutter 向け `sherpa_onnx` pub パッケージを公式提供。

```c
// Config は POD struct
typedef struct SherpaOnnxOfflineTtsConfig { ... } SherpaOnnxOfflineTtsConfig;

// エンジンは opaque pointer
typedef struct SherpaOnnxOfflineTts SherpaOnnxOfflineTts;

// 音声出力は callee-owned struct
typedef struct SherpaOnnxGeneratedAudio {
    float *samples;
    int32_t n;
    int32_t sample_rate;
} SherpaOnnxGeneratedAudio;

// ライフサイクル
SherpaOnnxOfflineTts* SherpaOnnxCreateOfflineTts(config);
void SherpaOnnxDestroyOfflineTts(tts);

// 合成 (同期 / コールバック付きストリーミング)
SherpaOnnxGeneratedAudio* SherpaOnnxOfflineTtsGenerate(tts, text, sid, speed);
SherpaOnnxGeneratedAudio* SherpaOnnxOfflineTtsGenerateWithCallback(..., callback, user_data);
void SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
```

**設計ポイント:**
- Config は `memset` + フィールド設定パターンで初期化
- すべてのオブジェクトに対応する `Destroy` 関数
- コールバックに `void* user_data` を渡す C 標準パターン
- `num_threads` を Config で管理

#### OHF-Voice/piper1-gpl の libpiper

piper フォークによる C API 実装。Iterator パターンが特徴。

```c
// Iterator パターン
piper_synthesizer* piper_create(model_path, config_path, espeak_data);
int piper_synthesize_start(synthesizer, text, options);
int piper_synthesize_next(synthesizer, &chunk);  // PIPER_OK or PIPER_DONE
void piper_free(piper_synthesizer*);
```

**設計ポイント:**
- Iterator (start/next/done) — コールバック不要でシンプル
- `piper_audio_chunk` に phoneme timing/alignment を含む
- sentence 単位の chunk 分割

#### espeak-ng

```c
int espeak_Initialize(output, buflength, path, options);
espeak_ERROR espeak_Synth(text, size, ...);
espeak_ERROR espeak_Terminate(void);
```

**注意:** グローバルステートパターン — 非推奨。piper-plus では避けるべき。

### 2.3 参考リンク

| リソース | URL |
|----------|-----|
| sherpa-onnx C API | `github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/c-api/c-api.h` |
| OHF-Voice/piper1-gpl libpiper | `github.com/OHF-Voice/piper1-gpl/tree/main/libpiper` |
| ONNX Runtime C API Guidelines | `github.com/microsoft/onnxruntime/blob/main/docs/C_API_Guidelines.md` |
| Dart FFI guide | `dart.dev/interop/c-interop` |
| piper Issue #232 "Piper as Library?" | `github.com/rhasspy/piper/issues/232` |

---

## 3. 現行アーキテクチャ分析

### 3.1 C++ ソースコード構成

**ファイル数:** 58ファイル / 36,980行

| カテゴリ | ファイル数 | 主要ファイル |
|----------|-----------|-------------|
| コア合成エンジン | 2 | `piper.cpp` (2,030行), `piper.hpp` |
| CLI / モデル管理 | 2 | `main.cpp` (1,037行), `model_manager.cpp` |
| 言語別 G2P | 8 | `{english,chinese,japanese,...}_phonemize.cpp` |
| OpenJTalk C API | 8 | `openjtalk_*.c/h` |
| ユーティリティ | 8+ | `json.hpp`, `utf8.h`, `wavfile.hpp` 等 |

### 3.2 公開 API 境界 (`piper.hpp`)

```cpp
namespace piper {
    // ライフサイクル
    void initialize(PiperConfig &config);
    void terminate(PiperConfig &config);
    void loadVoice(PiperConfig&, string modelPath, string configPath,
                   Voice&, optional<SpeakerId>&, bool useCuda, int gpuDeviceId = 0);

    // 合成 (同期)
    void textToAudio(PiperConfig&, Voice&, string text,
                     vector<int16_t>& audioBuffer, SynthesisResult&,
                     const function<void()>& audioCallback, ...);

    // 合成 (ストリーミング)
    void textToAudioStreaming(PiperConfig&, Voice&, string text,
                              vector<int16_t>& audioBuffer, SynthesisResult&,
                              const function<void(const vector<int16_t>&)>& chunkCallback,
                              size_t chunkSize = 4096);

    // 音素→音声
    void phonemesToAudio(PiperConfig&, Voice&, const vector<Phoneme>&, ...);
    void phonemesToAudioStreaming(PiperConfig&, Voice&, const vector<Phoneme>&, ...);

    // ユーティリティ
    string getVersion();
}
```

### 3.3 共有ライブラリ化の分離ポイント

```
piper_shared (共有ライブラリに含める)
├── piper.cpp              — コア合成エンジン
├── phoneme_parser.cpp     — [[ ]] 記法パーサー
├── custom_dictionary.cpp  — カスタム辞書
├── language_detector.cpp  — 多言語判定
├── *_phonemize.cpp        — 8言語 G2P
├── openjtalk_*.c          — OpenJTalk C API
└── audio_neon.cpp         — ARM64 最適化 (条件付き)

除外 (CLIのみ)
├── main.cpp               — CLI エントリポイント
└── model_manager.cpp      — モデル DL/管理 (CLI部分)
```

### 3.4 依存ライブラリ

| ライブラリ | バージョン | リンク形態 | 備考 |
|-----------|-----------|-----------|------|
| ONNX Runtime | 1.14.1 | 動的リンク | 自動ダウンロード |
| OpenJTalk (pyopenjtalk-plus) | 0.4.1.post7 | 静的リンク | 日本語 G2P |
| HTS Engine | 1.10 | スタブ (静的) | デフォルト |
| spdlog | 1.12.0 | 静的リンク | ロギング |
| fmt | 10.0.0 | ヘッダーオンリー | フォーマッティング |
| nlohmann/json | — | ヘッダーオンリー | JSON 処理 |

### 3.5 CI/CD 現状

- **30個の GitHub Actions ワークフロー** が運用中
- **リリースビルド:** 6プラットフォーム (Linux x64/ARM64/ARMv7, macOS ARM64, Windows x64)
- **テスト:** Google Test v1.14.0、20+ テストファイル
- **キャッシュ:** ccache + 依存ライブラリキャッシュ完備
- **配布:** GitHub Releases + PyPI + NuGet + crates.io

---

## 4. 要求仕様

### 4.1 機能要件

#### FR-1: C API ヘッダー (`piper_plus.h`)

`extern "C"` ヘッダーで以下の API を提供する。

**ライフサイクル:**

| 関数 | 説明 | 優先度 |
|------|------|--------|
| `piper_plus_create(config)` | エンジン作成 | 必須 |
| `piper_plus_free(engine)` | エンジン破棄 | 必須 |
| `piper_plus_version()` | ライブラリバージョン取得 | 必須 |
| `piper_plus_api_version()` | API バージョン取得 | 必須 |

**合成 (3パターン):**

| 関数 | 説明 | 用途 | 優先度 |
|------|------|------|--------|
| `piper_plus_synthesize(...)` | ワンショット同期合成 | Python/C#/シンプル用途 | 必須 |
| `piper_plus_synth_start/next(...)` | Iterator パターン | Go/Rust/低メモリ環境 | 必須 |
| `piper_plus_synthesize_streaming(...)` | コールバック付き | Flutter/Dart | 必須 |

**パラメータ制御:**

| 関数 | 説明 | 優先度 |
|------|------|--------|
| `piper_plus_default_options()` | デフォルトオプション取得 | 必須 |
| `PiperPlusSynthOptions.speaker_id` | 話者 ID | 必須 |
| `PiperPlusSynthOptions.language_id` | 言語 ID (-1 = 自動検出) | 必須 |
| `PiperPlusSynthOptions.noise_scale` | ノイズスケール | 必須 |
| `PiperPlusSynthOptions.length_scale` | 長さスケール | 必須 |
| `PiperPlusSynthOptions.noise_w` | ノイズ W | 必須 |
| `PiperPlusSynthOptions.sentence_silence_sec` | 文間無音 | 必須 |

**クエリ:**

| 関数 | 説明 | 優先度 |
|------|------|--------|
| `piper_plus_sample_rate(engine)` | サンプルレート | 必須 |
| `piper_plus_num_speakers(engine)` | 話者数 | 必須 |
| `piper_plus_num_languages(engine)` | 言語数 | 必須 |

**エラーハンドリング:**

| 関数 | 説明 | 優先度 |
|------|------|--------|
| `piper_plus_get_last_error()` | 直前のエラーメッセージ取得 | 必須 |

**メモリ管理:**

| 関数 | 説明 | 優先度 |
|------|------|--------|
| `piper_plus_free_audio(samples)` | ワンショット合成の音声バッファ解放 | 必須 |

#### FR-2: 共有ライブラリ

- CMake オプション `PIPER_PLUS_BUILD_SHARED` (デフォルト OFF) で共有ライブラリをビルド
- 出力: `libpiper_plus.so` (Linux), `libpiper_plus.dylib` (macOS), `piper_plus.dll` (Windows)

#### FR-3: クロスプラットフォーム

以下のプラットフォームでビルド・動作すること:

| プラットフォーム | アーキテクチャ | 備考 |
|-----------------|---------------|------|
| Linux | x86_64, aarch64 | glibc 2.31+ |
| macOS | arm64 | macOS 12+ |
| Windows | x64 | MSVC 2022 |

#### FR-4: CI ビルド検証

- 既存の CI マトリクス (Linux/macOS/Windows) で共有ライブラリのビルドを検証

### 4.2 非機能要件

#### NFR-1: ABI 安定性

- opaque pointer パターンで内部構造を隠蔽
- Config struct に `_reserved[8]` フィールドで将来拡張に備える
- `PIPER_PLUS_API_VERSION` 定数でバージョン管理
- 既存関数のシグネチャ変更禁止 (追加のみ)

#### NFR-2: メモリ安全性

- 音声バッファはライブラリが所有 (callee-owned)
- ワンショット合成の音声バッファは `piper_plus_free_audio()` で明示解放
- Iterator パターンのチャンクデータは次の `synth_next()` まで有効
- NULL ポインタチェックを全 API 関数に実装

#### NFR-3: スレッドセーフティ

- `PiperPlusEngine` インスタンスはスレッド間で共有不可
- 複数スレッドは各自別インスタンスを生成
- ヘッダーに "This object is NOT thread-safe" を明記

#### NFR-4: エラーハンドリング

- 全関数は `int32_t` を返す (0 = 成功, 負 = エラー)
- エラーコード定数: `PIPER_PLUS_OK`, `PIPER_PLUS_ERR`, `PIPER_PLUS_ERR_MODEL`, `PIPER_PLUS_ERR_CONFIG`, `PIPER_PLUS_ERR_TEXT`, `PIPER_PLUS_DONE`
- `piper_plus_get_last_error()` でエラーメッセージ取得
- C++ 例外は API 境界で全捕捉 (例外がライブラリ外に漏れない)

#### NFR-5: シンボル可視性

- デフォルト: `-fvisibility=hidden` (GCC/Clang), 全シンボル非公開
- 公開 API のみ `PIPER_PLUS_API` マクロでエクスポート
- Windows: `__declspec(dllexport)` / `__declspec(dllimport)` 切替

#### NFR-6: 文字列エンコーディング

- 全文字列パラメータは UTF-8
- ONNX Runtime ガイドライン準拠
- Dart/Go/Rust/Swift すべてと互換

---

## 5. 推奨 API 設計

以下は sherpa-onnx / libpiper / endo5501 実装のベストプラクティスを統合した設計案。

```c
#ifndef PIPER_PLUS_H_
#define PIPER_PLUS_H_

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ===== Export macro ===== */
#if defined(_WIN32) || defined(_WIN64)
  #ifdef PIPER_PLUS_BUILDING_DLL
    #define PIPER_PLUS_API __declspec(dllexport)
  #else
    #define PIPER_PLUS_API __declspec(dllimport)
  #endif
#elif defined(__GNUC__) && __GNUC__ >= 4
  #define PIPER_PLUS_API __attribute__((visibility("default")))
#else
  #define PIPER_PLUS_API
#endif

/* ===== Version ===== */
#define PIPER_PLUS_API_VERSION 1

PIPER_PLUS_API const char *piper_plus_version(void);
PIPER_PLUS_API int32_t     piper_plus_api_version(void);

/* ===== Status codes ===== */
#define PIPER_PLUS_OK          0
#define PIPER_PLUS_DONE        1   /* Iterator: no more chunks */
#define PIPER_PLUS_ERR        -1   /* Generic error */
#define PIPER_PLUS_ERR_MODEL  -2   /* Model load failure */
#define PIPER_PLUS_ERR_CONFIG -3   /* Config load failure */
#define PIPER_PLUS_ERR_TEXT   -4   /* Invalid text input */

PIPER_PLUS_API const char *piper_plus_get_last_error(void);

/* ===== Opaque types ===== */
typedef struct PiperPlusEngine PiperPlusEngine;

/* ===== Config structs (POD) ===== */
typedef struct PiperPlusConfig {
    const char *model_path;       /* .onnx file path (UTF-8) */
    const char *config_path;      /* .json config path (UTF-8, NULL = model_path + ".json") */
    const char *provider;         /* "cpu", "cuda", "coreml", "directml" (NULL = "cpu") */
    int32_t     num_threads;      /* ONNX Runtime intra-op threads (0 = auto) */
    int32_t     gpu_device_id;    /* GPU device index (provider != "cpu" の場合) */
    int32_t     _reserved[8];     /* ABI padding */
} PiperPlusConfig;

typedef struct PiperPlusSynthOptions {
    int32_t speaker_id;           /* 話者 ID (default: 0) */
    int32_t language_id;          /* 言語 ID (-1 = auto-detect) */
    float   noise_scale;          /* default: 0.667 */
    float   length_scale;         /* default: 1.0 */
    float   noise_w;              /* default: 0.8 */
    float   sentence_silence_sec; /* default: 0.2 */
    int32_t _reserved[8];         /* ABI padding */
} PiperPlusSynthOptions;

/* ===== Audio output ===== */
typedef struct PiperPlusAudioChunk {
    const float *samples;         /* PCM float32 [-1.0, 1.0] */
    int32_t      num_samples;
    int32_t      sample_rate;
    int32_t      is_last;         /* 1 if final chunk */
} PiperPlusAudioChunk;

/* ===== Streaming callback ===== */
typedef void (*PiperPlusAudioCallback)(
    const float *samples,
    int32_t      num_samples,
    int32_t      sample_rate,
    void        *user_data
);

/* ===== Lifecycle ===== */
PIPER_PLUS_API PiperPlusEngine *piper_plus_create(
    const PiperPlusConfig *config);

PIPER_PLUS_API void piper_plus_free(
    PiperPlusEngine *engine);

/* ===== Default options ===== */
PIPER_PLUS_API PiperPlusSynthOptions piper_plus_default_options(void);

/* ===== Synthesis: one-shot ===== */
PIPER_PLUS_API int32_t piper_plus_synthesize(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,         /* NULL = defaults */
    float                       **out_samples,
    int32_t                      *out_num_samples,
    int32_t                      *out_sample_rate);

PIPER_PLUS_API void piper_plus_free_audio(float *samples);

/* ===== Synthesis: iterator pattern ===== */
PIPER_PLUS_API int32_t piper_plus_synth_start(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts);        /* NULL = defaults */

PIPER_PLUS_API int32_t piper_plus_synth_next(
    PiperPlusEngine      *engine,
    PiperPlusAudioChunk  *out_chunk);           /* caller provides, callee fills */

/* ===== Synthesis: streaming with callback ===== */
PIPER_PLUS_API int32_t piper_plus_synthesize_streaming(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,         /* NULL = defaults */
    PiperPlusAudioCallback        callback,
    void                         *user_data);

/* ===== Query ===== */
PIPER_PLUS_API int32_t piper_plus_sample_rate(const PiperPlusEngine *engine);
PIPER_PLUS_API int32_t piper_plus_num_speakers(const PiperPlusEngine *engine);
PIPER_PLUS_API int32_t piper_plus_num_languages(const PiperPlusEngine *engine);

#ifdef __cplusplus
}
#endif

#endif /* PIPER_PLUS_H_ */
```

### 5.1 API 設計判断の根拠

| 設計判断 | 根拠 |
|----------|------|
| 3つの合成パターン (one-shot / iterator / callback) | one-shot は Python/C#、iterator は Go/Rust、callback は Flutter/Dart に最適 |
| `_reserved[8]` | struct サイズ変更なしで将来フィールド追加可能 (ABI 互換) |
| `language_id = -1` で自動検出 | piper-plus の `MultilingualPhonemizer` / `LanguageDetector` を活用 |
| `provider` 文字列 | ONNX Runtime の ExecutionProvider 名をそのまま渡せる |
| `PiperPlusAudioCallback` が `void` 戻り | Dart `NativeCallable.listener` との互換性 (void 戻りのみ対応) |
| `piper_plus_free_audio()` 専用関数 | アロケータ不一致 (malloc vs new) を防止 |
| `const char*` UTF-8 統一 | ONNX Runtime ガイドライン準拠、全 FFI 言語と互換 |
| グローバルステートなし | 複数エンジンインスタンスの並行利用を許可 |
| `#define` 定数 (enum 不使用) | C enum は ABI 脆弱。Fuchsia ガイドライン準拠 |

### 5.2 endo5501 実装との差分

| 項目 | endo5501 | 本設計 | 理由 |
|------|----------|--------|------|
| 第2引数 | `dic_dir` | `config_path` (Config struct) | config パス明示指定が必要 |
| speaker_id | なし | `SynthOptions.speaker_id` | マルチスピーカー対応 |
| language | なし | `SynthOptions.language_id` | 多言語対応 |
| GPU | `useCuda=false` 固定 | `Config.provider` | GPU 推論対応 |
| ストリーミング | なし | iterator + callback | 低レイテンシ合成 |
| バージョン | なし | `piper_plus_version()` | ABI 管理 |
| エラー | `get_error()` per-ctx | `get_last_error()` global | スレッドローカル、ctx なし時も使用可 |

---

## 6. CMake ビルド設計

### 6.1 概要

```cmake
option(PIPER_PLUS_BUILD_SHARED "Build piper-plus shared library" OFF)

if(PIPER_PLUS_BUILD_SHARED)
    add_library(piper_plus SHARED
        src/cpp/piper_plus_c_api.cpp    # C API ラッパー (新規)
        src/cpp/piper.cpp
        src/cpp/phoneme_parser.cpp
        src/cpp/custom_dictionary.cpp
        src/cpp/language_detector.cpp
        src/cpp/english_phonemize.cpp
        src/cpp/chinese_phonemize.cpp
        src/cpp/korean_phonemize.cpp
        src/cpp/spanish_phonemize.cpp
        src/cpp/french_phonemize.cpp
        src/cpp/portuguese_phonemize.cpp
        src/cpp/swedish_phonemize.cpp
        src/cpp/openjtalk_phonemize.cpp
        src/cpp/openjtalk_phonemize_utils.cpp
        src/cpp/openjtalk_wrapper.c
        src/cpp/openjtalk_dictionary_manager.c
        src/cpp/openjtalk_error.c
        src/cpp/openjtalk_security.c
        src/cpp/openjtalk_optimized.c
        src/cpp/openjtalk_api.c
        # ARM64 条件付き
        # $<$<STREQUAL:${CMAKE_SYSTEM_PROCESSOR},aarch64>:src/cpp/audio_neon.cpp>
    )

    target_compile_definitions(piper_plus PRIVATE PIPER_PLUS_BUILDING_DLL)
    set_target_properties(piper_plus PROPERTIES
        C_VISIBILITY_PRESET hidden
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON
        VERSION ${PIPER_VERSION}
        SOVERSION 1
    )

    # 依存ライブラリのリンク (既存と同等)
    target_link_libraries(piper_plus PRIVATE
        onnxruntime fmt spdlog openjtalk hts_engine Threads::Threads)

    install(TARGETS piper_plus DESTINATION lib)
    install(FILES src/cpp/piper_plus.h DESTINATION include)
endif()
```

### 6.2 プラットフォーム別設定

| 設定 | Linux | macOS | Windows |
|------|-------|-------|---------|
| 出力名 | `libpiper_plus.so.1` | `libpiper_plus.1.dylib` | `piper_plus.dll` + `piper_plus.lib` |
| RPATH | `$ORIGIN` | `@rpath` | N/A |
| C++ runtime | `-static-libstdc++` | system | MSVC DLL |
| export | `visibility("default")` | `visibility("default")` | `__declspec(dllexport)` |

---

## 7. CI 拡張計画

### 7.1 既存 CI の活用

既存の CI マトリクスにビルドオプションを追加:

```yaml
# cpp-tests.yml への追加
strategy:
  matrix:
    os: [ubuntu-22.04, macos-latest, windows-latest]
    build_type: [Release]
    include:
      - os: ubuntu-22.04
        shared_lib: ON
      - os: macos-latest
        shared_lib: ON
      - os: windows-latest
        shared_lib: ON
```

### 7.2 検証項目

| テスト | 内容 |
|--------|------|
| ビルド成功 | 3 プラットフォームで `.so`/`.dylib`/`.dll` 生成 |
| シンボル確認 | `nm -D` / `otool -t` で公開 API のみエクスポートされていること |
| リンクテスト | C プログラムから `piper_plus_create()` を呼び出し |
| ライフサイクル | create → synthesize → free が正常動作 |

---

## 8. 実装フェーズ

### Phase 1: 基本 C API (MVP)

**スコープ:**
- `piper_plus.h` ヘッダー
- `piper_plus_c_api.cpp` 実装
- CMake `PIPER_PLUS_BUILD_SHARED` オプション
- ワンショット合成 (`piper_plus_synthesize`)
- speaker_id / language_id 対応
- 3 プラットフォームビルド

**成果物:**
- `libpiper_plus.so` / `.dylib` / `.dll`
- `piper_plus.h` ヘッダー

### Phase 2: ストリーミング + テスト

**スコープ:**
- Iterator パターン (`synth_start` / `synth_next`)
- コールバック合成 (`synthesize_streaming`)
- Google Test でユニットテスト
- CI 統合

### Phase 3: 配布

**スコープ:**
- リリースワークフローでバイナリ配布
- pkg-config / CMake Config 生成
- 使用例ドキュメント (C / Dart / Go)

### Phase 4: 拡張 (将来)

**候補:**
- カスタム辞書 API
- Phoneme timing 出力
- G2P 単独利用 API (`piper_plus_phonemize`)
- Android NDK ビルド

---

## 9. Flutter/Dart FFI 設計ガイドライン

本 C API は Flutter/Dart からの利用を主要ユースケースとして設計。以下は Dart FFI 側の制約と対応:

| Dart FFI の制約 | C API 側の対応 |
|----------------|---------------|
| `extern "C"` 必須 | 全 API が `extern "C"` |
| `NativeCallable.listener` は void 戻りのみ | `PiperPlusAudioCallback` は void 戻り |
| `Pointer<Float>.asTypedList()` でゼロコピー | 音声データは `float*` + `int32_t count` |
| `toNativeUtf8()` で文字列変換 | 全文字列が UTF-8 |
| macOS コード署名必須 | `MACOSX_RPATH` 設定済み |
| ffigen で自動バインディング生成可 | ヘッダーが ffigen 互換 (POD struct + opaque pointer) |

---

## 10. Appendix: endo5501 実装 (参考)

### A.1 ヘッダー全文 (`piper_tts_c_api.h`)

```c
#ifndef PIPER_TTS_C_API_H
#define PIPER_TTS_C_API_H

#ifdef __cplusplus
extern "C" {
#endif

#ifdef _WIN32
#  ifdef PIPER_TTS_SHARED
#    define PIPER_TTS_API __declspec(dllexport)
#  else
#    define PIPER_TTS_API __declspec(dllimport)
#  endif
#else
#  define PIPER_TTS_API __attribute__((visibility("default")))
#endif

typedef struct piper_tts_ctx piper_tts_ctx;

PIPER_TTS_API piper_tts_ctx* piper_tts_init(const char* model_path,
                                              const char* dic_dir);
PIPER_TTS_API int             piper_tts_is_loaded(const piper_tts_ctx* ctx);
PIPER_TTS_API void            piper_tts_free(piper_tts_ctx* ctx);
PIPER_TTS_API int             piper_tts_synthesize(piper_tts_ctx* ctx,
                                                    const char* text);
PIPER_TTS_API int             piper_tts_set_length_scale(piper_tts_ctx* ctx,
                                                          float value);
PIPER_TTS_API int             piper_tts_set_noise_scale(piper_tts_ctx* ctx,
                                                         float value);
PIPER_TTS_API int             piper_tts_set_noise_w(piper_tts_ctx* ctx,
                                                     float value);
PIPER_TTS_API const float*    piper_tts_get_audio(const piper_tts_ctx* ctx);
PIPER_TTS_API int             piper_tts_get_audio_length(const piper_tts_ctx* ctx);
PIPER_TTS_API int             piper_tts_get_sample_rate(const piper_tts_ctx* ctx);
PIPER_TTS_API const char*     piper_tts_get_error(const piper_tts_ctx* ctx);

#ifdef __cplusplus
}
#endif

#endif // PIPER_TTS_C_API_H
```

### A.2 実装全文 (`piper_tts_c_api.cpp`)

```cpp
#include "piper_tts_c_api.h"
#include "piper.hpp"

#include <cstdlib>
#include <new>
#include <string>
#include <vector>

struct piper_tts_ctx {
    piper::PiperConfig config;
    piper::Voice voice;
    std::vector<float> last_audio;
    std::string last_error;
    bool loaded = false;
};

extern "C" {

PIPER_TTS_API piper_tts_ctx* piper_tts_init(const char* model_path,
                                              const char* dic_dir) {
    auto* ctx = new (std::nothrow) piper_tts_ctx();
    if (!ctx) return nullptr;

    try {
        if (dic_dir && dic_dir[0] != '\0') {
#ifdef _WIN32
            _putenv_s("OPENJTALK_DICTIONARY_PATH", dic_dir);
#else
            setenv("OPENJTALK_DICTIONARY_PATH", dic_dir, 1);
#endif
        }
        piper::initialize(ctx->config);
        std::string mp(model_path);
        std::string cp = mp + ".json";
        std::optional<piper::SpeakerId> sid;
        piper::loadVoice(ctx->config, mp, cp, ctx->voice, sid, false);
        ctx->loaded = true;
    } catch (const std::exception& e) {
        ctx->last_error = e.what();
        ctx->loaded = false;
    }
    return ctx;
}

PIPER_TTS_API int piper_tts_is_loaded(const piper_tts_ctx* ctx) {
    if (!ctx) return 0;
    return ctx->loaded ? 1 : 0;
}

PIPER_TTS_API void piper_tts_free(piper_tts_ctx* ctx) {
    if (ctx) {
        if (ctx->loaded) piper::terminate(ctx->config);
        delete ctx;
    }
}

PIPER_TTS_API int piper_tts_synthesize(piper_tts_ctx* ctx, const char* text) {
    if (!ctx || !ctx->loaded) {
        if (ctx) ctx->last_error = "Model not loaded";
        return -1;
    }
    if (!text || text[0] == '\0') {
        ctx->last_error = "Empty text";
        return -1;
    }
    try {
        std::vector<int16_t> pcm;
        piper::SynthesisResult result;
        piper::textToAudio(ctx->config, ctx->voice,
                           std::string(text), pcm, result, nullptr);
        ctx->last_audio.resize(pcm.size());
        constexpr float scale = 1.0f / 32768.0f;
        for (size_t i = 0; i < pcm.size(); i++) {
            ctx->last_audio[i] = static_cast<float>(pcm[i]) * scale;
        }
        return 0;
    } catch (const std::exception& e) {
        ctx->last_error = e.what();
        return -1;
    }
}

PIPER_TTS_API int piper_tts_set_length_scale(piper_tts_ctx* ctx, float value) {
    if (!ctx || !ctx->loaded) return -1;
    ctx->voice.synthesisConfig.lengthScale = value;
    return 0;
}

PIPER_TTS_API int piper_tts_set_noise_scale(piper_tts_ctx* ctx, float value) {
    if (!ctx || !ctx->loaded) return -1;
    ctx->voice.synthesisConfig.noiseScale = value;
    return 0;
}

PIPER_TTS_API int piper_tts_set_noise_w(piper_tts_ctx* ctx, float value) {
    if (!ctx || !ctx->loaded) return -1;
    ctx->voice.synthesisConfig.noiseW = value;
    return 0;
}

PIPER_TTS_API const float* piper_tts_get_audio(const piper_tts_ctx* ctx) {
    if (!ctx || ctx->last_audio.empty()) return nullptr;
    return ctx->last_audio.data();
}

PIPER_TTS_API int piper_tts_get_audio_length(const piper_tts_ctx* ctx) {
    if (!ctx) return 0;
    return static_cast<int>(ctx->last_audio.size());
}

PIPER_TTS_API int piper_tts_get_sample_rate(const piper_tts_ctx* ctx) {
    if (!ctx || !ctx->loaded) return 0;
    return ctx->voice.synthesisConfig.sampleRate;
}

PIPER_TTS_API const char* piper_tts_get_error(const piper_tts_ctx* ctx) {
    if (!ctx) return "null context";
    return ctx->last_error.c_str();
}

} // extern "C"
```
