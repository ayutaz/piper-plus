# C API 共有ライブラリ (Issue #295)

> **Status:** Implemented (Phase 1〜5 全完了)
> **Issue:** [#295](https://github.com/ayutaz/piper-plus/issues/295)
> **Branch:** `feature/c-api-shared-library`

---

## 目次

1. [概要・背景](#1-概要背景)
2. [要求定義 (NFR含む)](#2-要求定義)
3. [API 設計・仕様](#3-api-設計仕様)
4. [技術調査結果](#4-技術調査結果)
5. [マイルストーン (Phase 1〜5)](#5-マイルストーン)
6. [完了チケット一覧 (47件)](#6-完了チケット一覧-47件)
7. [ビルド・配布](#7-ビルド配布)
8. [CI/CD](#8-cicd)

---

## 1. 概要・背景

piper-plus の C++ 実装を共有ライブラリ (`.dll` / `.so` / `.dylib`) + `extern "C"` ヘッダーとして公開し、他言語から FFI で利用可能にする。

### 1.1 解決する課題

piper-plus は既に Rust / Python / Go / C# / JS(WASM) でネイティブライブラリを提供しているが、C API (`.so`/`.dylib`/`.dll` + `extern "C"`) が存在しないため、**C FFI に依存するプラットフォーム**からの利用がブロックされている:

| ユースケース | 必要なバインディング | 現状 |
|---|---|---|
| Flutter/Dart アプリ | `dart:ffi` (C のみ) | **不可** |
| Godot GDExtension | C バインディング | piper-plus C++ ソースを丸ごとコピーして直接ビルド ([godot-piper-plus](https://github.com/ayutaz/godot-piper-plus)) -- 保守コスト大 |
| Swift / iOS アプリ | C interop | **不可** |

#### Godot GDExtension の現状と課題

[godot-piper-plus](https://github.com/ayutaz/godot-piper-plus) は C API がないため、piper-plus の C++ ソース 25+ ファイルを `src/piper_core/` にコピー (vendor) して GDExtension に直接コンパイルしている。

| 課題 | 詳細 |
|------|------|
| ソース同期の保守コスト | piper-plus 更新のたびに 25+ ファイルの手動コピー + 改変が必要 |
| 日本語のみ対応 | 8言語 G2P 中、OpenJTalk (日本語) のみ統合。英語 G2P は未実装 (TODO) |
| 複雑なビルドシステム | 227行 CMakeLists.txt + ExternalProject で OpenJTalk/HTSEngine をソースからクロスコンパイル |
| 手動改変が必要 | spdlog -> no-op シム差替え、eSpeak 除去、PhonemeType 再番号付け等 |
| ABI 不安定 | C++ 名前空間を直接呼び出すため、コンパイラ・標準ライブラリの一致が必要 |

**C API 共有ライブラリによる改善:**

| 項目 | 現状 (ソースコピー) | C API 方式 |
|------|-------------------|-----------|
| GDExtension 側ソースファイル | 25+ | **4** (register_types + TTS ノード) |
| ビルドスクリプト | 227行 CMake + ExternalProject | **~30行** |
| 多言語 G2P | 日本語のみ | **8言語が即時利用可能** |
| piper-plus 更新の追従 | ファイルコピー + 手動改変 | **ヘッダー + バイナリ差し替えのみ** |
| OpenJTalk/HTSEngine ビルド | GDExtension 側でクロスコンパイル | **不要 (C API に内包)** |

> **参考:** [godot-kokoro](https://github.com/PhilNikitin/godot-kokoro) が sherpa-onnx の C API 共有ライブラリを GDExtension から利用する方式で同パターンを実証済み (SConstruct 43行、ソースファイル 4つのみ)。

### 1.2 先行事例

#### endo5501 の実装 (`feat/support_cpp_library`)

[@endo5501](https://github.com/endo5501) が Flutter FFI 用の C API ラッパーを実装済み。

**提供 API:**

```c
piper_tts_ctx* piper_tts_init(const char* model_path, const char* dic_dir);
int             piper_tts_is_loaded(const piper_tts_ctx* ctx);
void            piper_tts_free(piper_tts_ctx* ctx);
int             piper_tts_synthesize(piper_tts_ctx* ctx, const char* text);
int             piper_tts_set_length_scale(piper_tts_ctx* ctx, float value);
int             piper_tts_set_noise_scale(piper_tts_ctx* ctx, float value);
int             piper_tts_set_noise_w(piper_tts_ctx* ctx, float value);
const float*    piper_tts_get_audio(const piper_tts_ctx* ctx);
int             piper_tts_get_audio_length(const piper_tts_ctx* ctx);
int             piper_tts_get_sample_rate(const piper_tts_ctx* ctx);
const char*     piper_tts_get_error(const piper_tts_ctx* ctx);
```

**評価:** opaque handle パターン、int 戻り値 + `get_error()`、float32 変換、クロスプラットフォーム export、visibility hidden デフォルト -- いずれも良い設計。

**不足点:**

| 不足項目 | 重要度 |
|----------|--------|
| speaker_id / language 未対応 | **必須** |
| config_path が `model_path + ".json"` にハードコード | **必須** |
| 辞書パスが `setenv` 依存 (プロセスグローバル副作用) | 高 |
| CUDA/GPU 未対応 | 中 |
| ストリーミング未対応 | 中 |
| バージョン API なし | 低 |

#### 類似 TTS エンジンの C API

**sherpa-onnx** (最も参考になる設計): Config は POD struct + `memset` 初期化、opaque pointer、callee-owned 音声出力、コールバック + `user_data`、`num_threads` 管理。

**OHF-Voice/piper1-gpl libpiper**: Iterator パターン (start/next/done)、phoneme timing/alignment 付き chunk。

**espeak-ng**: グローバルステートパターン -- 非推奨。piper-plus では避けるべき。

### 1.3 C++ ソースコード構成

**ファイル数:** 58ファイル / 36,980行

| カテゴリ | ファイル数 | 主要ファイル |
|----------|-----------|-------------|
| コア合成エンジン | 2 | `piper.cpp` (2,030行), `piper.hpp` |
| CLI / モデル管理 | 2 | `main.cpp` (1,037行), `model_manager.cpp` |
| 言語別 G2P | 8 | `{english,chinese,japanese,...}_phonemize.cpp` |
| OpenJTalk C API | 8 | `openjtalk_*.c/h` |
| ユーティリティ | 8+ | `json.hpp`, `utf8.h`, `wavfile.hpp` 等 |

**共有ライブラリ化の分離ポイント:**

```
piper_shared (共有ライブラリに含める)
├── piper.cpp              -- コア合成エンジン
├── phoneme_parser.cpp     -- [[ ]] 記法パーサー
├── custom_dictionary.cpp  -- カスタム辞書
├── language_detector.cpp  -- 多言語判定
├── *_phonemize.cpp        -- 8言語 G2P
├── openjtalk_*.c          -- OpenJTalk C API
└── audio_neon.cpp         -- ARM64 最適化 (条件付き)

除外 (CLIのみ)
├── main.cpp               -- CLI エントリポイント
└── model_manager.cpp      -- モデル DL/管理 (CLI部分)
```

---

## 2. 要求定義

### 2.1 機能要件

#### FR-1: C API ヘッダー (`piper_plus.h`)

`extern "C"` ヘッダーで以下の API を提供する。

**ライフサイクル:** `piper_plus_create`, `piper_plus_free`, `piper_plus_version`, `piper_plus_api_version`

**合成 (4パターン):**

| 関数 | 説明 | 用途 |
|------|------|------|
| `piper_plus_synthesize(...)` | ワンショット同期合成 | Python/C#/シンプル用途 |
| `piper_plus_synth_start/next(...)` | Iterator パターン | Go/Rust/低メモリ環境 |
| `piper_plus_synthesize_streaming(...)` | コールバック付き | Flutter/Dart |
| `piper_plus_synthesize_streaming_ex(...)` | キャンセル可能コールバック | ゲームエンジン等リアルタイム用途 |

**パラメータ制御:** `piper_plus_default_options()`, `PiperPlusSynthOptions` (speaker_id, language_id, noise_scale, length_scale, noise_w, sentence_silence_sec)

**クエリ:** `piper_plus_sample_rate`, `piper_plus_num_speakers`, `piper_plus_num_languages`, `piper_plus_language_id`

**エラーハンドリング:** `piper_plus_get_last_error()` (スレッドローカル)

**メモリ管理:** `piper_plus_free_audio()` (ワンショット合成の音声バッファ解放)

**カスタム辞書:** `piper_plus_load_custom_dict`, `piper_plus_clear_custom_dict`, `piper_plus_add_dict_word`, `piper_plus_dict_entry_count`

**G2P:** `piper_plus_phonemize`, `piper_plus_available_languages`

**タイミング:** `piper_plus_get_phoneme_timing`

#### FR-2: 共有ライブラリ

CMake オプション `PIPER_PLUS_BUILD_SHARED` (デフォルト OFF) で共有ライブラリをビルド。出力: `libpiper_plus.so` (Linux), `libpiper_plus.dylib` (macOS), `piper_plus.dll` (Windows)。

#### FR-3: クロスプラットフォーム

| プラットフォーム | アーキテクチャ | 備考 |
|-----------------|---------------|------|
| Linux | x86_64, aarch64 | glibc 2.31+ |
| macOS | arm64 | macOS 12+ |
| Windows | x64 | MSVC 2022 |
| Android | arm64-v8a, armeabi-v7a, x86_64 | NDK |

### 2.2 非機能要件

#### NFR-1: ABI 安定性

- opaque pointer パターンで内部構造を隠蔽
- Config struct に `_reserved` フィールドで将来拡張に備える
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

- 全関数は `PiperPlusStatus` (enum) を返す (0 = 成功, 正 = 完了, 負 = エラー)
- `typedef enum PiperPlusStatus`: `OK` (0), `DONE` (1), `ERR` (-1), `ERR_MODEL` (-2), `ERR_CONFIG` (-3), `ERR_TEXT` (-4), `ERR_BUSY` (-5), `ERR_ORT` (-6)
- `piper_plus_get_last_error()` でエラーメッセージ取得 (スレッドローカル)
- C++ 例外は API 境界で全捕捉 (例外がライブラリ外に漏れない)

#### NFR-5: シンボル可視性

- デフォルト: `-fvisibility=hidden` (GCC/Clang)
- 公開 API のみ `PIPER_PLUS_API` マクロでエクスポート
- Windows: `__declspec(dllexport)` / `__declspec(dllimport)` 切替

#### NFR-6: 文字列エンコーディング

全文字列パラメータは UTF-8。ONNX Runtime ガイドライン準拠。Dart/Go/Rust/Swift すべてと互換。

---

## 3. API 設計・仕様

### 3.1 全 API 関数一覧

| カテゴリ | 関数 | Phase |
|---------|------|-------|
| Version | `piper_plus_version()`, `piper_plus_api_version()` | 1 |
| Error | `piper_plus_get_last_error()` | 1 |
| Lifecycle | `piper_plus_create(config, &out_engine)`, `piper_plus_free(engine)` | 1 (M5-14 で status+out パターンに変更) |
| Options | `piper_plus_default_options()` | 1 |
| One-shot | `piper_plus_synthesize(...)`, `piper_plus_free_audio(samples)` | 1 |
| Iterator | `piper_plus_synth_start(...)`, `piper_plus_synth_next(...)` | 2 |
| Streaming | `piper_plus_synthesize_streaming(...)` | 2 |
| Streaming (cancel) | `piper_plus_synthesize_streaming_ex(...)` | 5 (M5-7) |
| Query | `piper_plus_sample_rate()`, `piper_plus_num_speakers()`, `piper_plus_num_languages()`, `piper_plus_language_id()` | 1 |
| Custom dict | `piper_plus_load_custom_dict()`, `piper_plus_clear_custom_dict()`, `piper_plus_add_dict_word()`, `piper_plus_dict_entry_count()` | 4 (M4-1) |
| Timing | `piper_plus_get_phoneme_timing()` | 4 (M4-2) |
| G2P | `piper_plus_phonemize()`, `piper_plus_available_languages()` | 4 (M4-3) |

### 3.2 ステータスコード

```c
typedef enum PiperPlusStatus {
    PIPER_PLUS_OK         =  0,  // 成功
    PIPER_PLUS_DONE       =  1,  // Iterator: チャンク終了
    PIPER_PLUS_ERR        = -1,  // 汎用エラー
    PIPER_PLUS_ERR_MODEL  = -2,  // モデル読み込み失敗
    PIPER_PLUS_ERR_CONFIG = -3,  // 設定読み込み失敗
    PIPER_PLUS_ERR_TEXT   = -4,  // 不正テキスト入力
    PIPER_PLUS_ERR_BUSY   = -5,  // 合成中の再入
    PIPER_PLUS_ERR_ORT    = -6,  // ONNX Runtime エラー
} PiperPlusStatus;
```

### 3.3 Config struct (POD, memset-safe)

```c
typedef struct PiperPlusConfig {
    const char *model_path;       /* Required: .onnx file path (UTF-8) */
    const char *config_path;      /* Optional: .json config path (NULL = model_path + ".json") */
    const char *provider;         /* Optional: "cpu","cuda","coreml","directml" (NULL = "cpu") */
    int32_t     num_threads;      /* ONNX intra-op threads (0 = auto) */
    int32_t     gpu_device_id;    /* GPU device index (ignored for cpu) */
    const char *dict_dir;         /* Optional: OpenJTalk dict dir (NULL = auto-detect) */
    int32_t     _reserved[7];     /* Must be zero */
} PiperPlusConfig;
```

### 3.4 SynthOptions (zero-init safe)

```c
typedef struct PiperPlusSynthOptions {
    int32_t speaker_id;           /* Speaker index (default: 0) */
    int32_t language_id;          /* Language index (-1 = auto-detect, default: -1) */
    float   noise_scale;          /* VITS noise_scale (0.0 = default 0.667) */
    float   length_scale;         /* VITS length_scale (0.0 = default 1.0) */
    float   noise_w;              /* VITS noise_w (0.0 = default 0.8) */
    float   sentence_silence_sec; /* Silence between sentences (default: 0.2) */
    int32_t _reserved[8];         /* Must be zero */
} PiperPlusSynthOptions;
```

### 3.5 キャンセル可能ストリーミングコールバック (M5-7)

```c
typedef int (*PiperPlusAudioCallbackEx)(
    const float *samples, int32_t num_samples, int32_t sample_rate, void *user_data);

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming_ex(
    PiperPlusEngine *engine, const char *text,
    const PiperPlusSynthOptions *opts, PiperPlusAudioCallbackEx callback, void *user_data);
```

> 完全なヘッダーは `src/cpp/piper_plus.h` を参照。

### 3.6 初期設計案からの変更点

| 変更 | 初期設計案 | 実装 (Phase 5 後) | 理由 / チケット |
|------|-----------|------------------|----------------|
| ステータスコード | `#define` 定数 | `typedef enum PiperPlusStatus` | デバッガでの可読性向上 (M5-13) |
| `piper_plus_create` | `PiperPlusEngine*` 戻り | `PiperPlusStatus` 戻り + `out_engine` | エラー種別の正確な返却 (M5-14) |
| `PiperPlusConfig` | `_reserved[8]` | `dict_dir` + `_reserved[7]` | 辞書パス指定 (M1-3) |
| `num_threads` | 設計のみ | `Ort::SessionOptions::SetIntraOpNumThreads()` に反映 | M5-5 |
| `provider` | `"cpu"` / `"cuda"` のみ | `"coreml"` / `"directml"` 追加 | M5-6 |
| ゼロ初期化 | 未規定 | `noise_scale` 等 0.0 でデフォルト値に自動置換 | M5-9 |
| ストリーミング中断 | 未設計 | `synthesize_streaming_ex` + `PiperPlusAudioCallbackEx` | M5-7 |

### 3.7 API 設計判断の根拠

| 設計判断 | 根拠 |
|----------|------|
| 4つの合成パターン | one-shot=Python/C#、iterator=Go/Rust、callback=Flutter/Dart、cancel-callback=リアルタイム中断 |
| `_reserved` フィールド | struct サイズ変更なしで将来フィールド追加可能 (ABI 互換) |
| `language_id = -1` で自動検出 | piper-plus の `MultilingualPhonemizer` / `LanguageDetector` を活用 |
| `PiperPlusAudioCallback` が `void` 戻り | Dart `NativeCallable.listener` との互換性 |
| `PiperPlusAudioCallbackEx` が `int` 戻り | 非ゼロで中断。ゲームエンジン等のリアルタイム用途向け |
| `piper_plus_free_audio()` 専用関数 | アロケータ不一致 (malloc vs new) を防止 |
| `const char*` UTF-8 統一 | ONNX Runtime ガイドライン準拠、全 FFI 言語と互換 |
| グローバルステートなし | 複数エンジンインスタンスの並行利用を許可 |
| RAII ガード (ConfigGuard / BusyGuard) | 例外発生時も `synthesisConfig` 復元 + `inProgress` フラグ解除を保証 |

### 3.8 endo5501 実装との差分

| 項目 | endo5501 | 本設計 | 理由 |
|------|----------|--------|------|
| 第2引数 | `dic_dir` | `config_path` (Config struct) | config パス明示指定が必要 |
| speaker_id | なし | `SynthOptions.speaker_id` | マルチスピーカー対応 |
| language | なし | `SynthOptions.language_id` | 多言語対応 |
| GPU | `useCuda=false` 固定 | `Config.provider` | GPU 推論対応 |
| ストリーミング | なし | iterator + callback | 低レイテンシ合成 |
| バージョン | なし | `piper_plus_version()` | ABI 管理 |
| エラー | `get_error()` per-ctx | `get_last_error()` global | スレッドローカル、ctx なし時も使用可 |

### 3.9 Flutter/Dart FFI 設計ガイドライン

| Dart FFI の制約 | C API 側の対応 |
|----------------|---------------|
| `extern "C"` 必須 | 全 API が `extern "C"` |
| `NativeCallable.listener` は void 戻りのみ | `PiperPlusAudioCallback` は void 戻り |
| `Pointer<Float>.asTypedList()` でゼロコピー | 音声データは `float*` + `int32_t count` |
| `toNativeUtf8()` で文字列変換 | 全文字列が UTF-8 |
| macOS コード署名必須 | `MACOSX_RPATH` 設定済み |
| ffigen で自動バインディング生成可 | ヘッダーが ffigen 互換 (POD struct + opaque pointer) |

---

## 4. 技術調査結果

### 4.1 C API -> C++ API マッピング

#### piper_plus_create() の実装方針

**重要な発見:** `piper::initialize()` は現状 **no-op** (spdlog::info のみ)。`PiperConfig` も空 struct。実質的な初期化は全て `loadVoice()` が行う。

**引数マッピング:**

| C API (PiperPlusConfig) | C++ API (loadVoice) | 備考 |
|---|---|---|
| `model_path` | `modelPath` | そのまま |
| `config_path` | `modelConfigPath` | NULL なら `model_path + ".json"` |
| `provider` | `useCuda` (bool) + ORT Session options | `"cuda"` -> useCuda=true、`"coreml"` / `"directml"` も実装済み (M5-6) |
| `gpu_device_id` | `gpuDeviceId` | そのまま |
| `num_threads` | `Ort::SessionOptions::SetIntraOpNumThreads()` | 実装済み (M5-5): 0 = ORT デフォルト |

**PiperPlusEngine 内部構造体:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;   // 空 struct (API 互換のため保持)
    piper::Voice       voice;    // ONNX Session + config + 辞書。move-only
    bool               inProgress; // 合成中フラグ (BusyGuard で自動管理)
    IteratorState       iterState; // 文分割結果キュー + currentChunkSamples
};
```

#### piper_plus_synthesize() の実装方針

**speaker_id / language_id の設定:** `voice.synthesisConfig` フィールドを直接変更 -> 合成 -> 復元するパターン (main.cpp の processLine と同一)。`ConfigGuard` RAII で例外安全性を保証。

**音声データの変換:** `textToAudioFloat()` / `synthesizeFloat()` で float32 直接出力パスを実装済み (M4-5)。int16 変換ステップを排除し精度向上 + CPU コスト削減。

**メモリ管理:** `malloc()` で確保 -> `piper_plus_free_audio()` で `free()`。DLL 境界越えで安全。

#### language_id = -1 (自動検出) の実装

`textToAudio()` 内部に `detectDominantLanguage()` が既に実装済み。`synthesisConfig.languageId` が入口時点の `originalLanguageId` と一致していれば自動検出が発動する。

#### ストリーミング (callback) の実装

`textToAudioStreaming()` を Iterator 駆動に移行済み (M5-16)。`MultilingualPhonemes` デッドコード問題を根本解決。

#### Iterator パターン (synth_start/synth_next)

文分割 -> 逐次合成の設計。コールバック -> キュー変換ではなく、`synth_start()` でテキストを文単位に分割してキューに保持、`synth_next()` で 1 文ずつ `textToAudio()` で合成して返す。libpiper (OHF-Voice) と同一パターン。

**ポインタ寿命:** `out_chunk->samples` は `IteratorState.currentChunkSamples` の内部バッファ。次の `synth_next()` まで有効。

### 4.2 スレッドローカルエラーと内部状態

#### thread_local の互換性

| コンパイラ | 対応状況 | DLL 制約 |
|-----------|---------|---------|
| MSVC 2022 | 完全対応 | .cpp 内部使用なら問題なし |
| GCC 4.8+ | 完全対応 | -fPIC 共有ライブラリで正常動作 |
| Clang 3.3+ | 完全対応 | GCC と同等 |

**piper-plus に前例あり:** `openjtalk_wrapper.c` で `__declspec(thread)` / `__thread` を既に使用。

```cpp
static thread_local std::string g_last_error;  // .cpp 内部に閉じる

const char* piper_plus_get_last_error(void) {
    return g_last_error.empty() ? nullptr : g_last_error.c_str();
}
```

ライフタイム: 次の API 呼び出しまで有効 (SQLite `sqlite3_errmsg()` と同じ規約)。

#### 例外捕捉パターン

```cpp
#define PIPER_PLUS_TRY try {
#define PIPER_PLUS_CATCH(retval) \
    } catch (const std::exception& e) { \
        g_last_error = e.what(); return retval; \
    } catch (...) { \
        g_last_error = "Unknown error"; return retval; \
    }
```

#### 複数エンジン並行利用

- `PiperConfig` は空 struct -- グローバルステートなし
- `initialize()` / `terminate()` は no-op
- 各 `Voice` が独立した `Ort::Session` + `Ort::Env` を保持
- **ほぼ安全** -- 唯一の懸念は `openjtalk_dictionary_manager.c` の初回書き込み時の理論的レース。ヘッダーに排他制約を明記済み

### 4.3 発見された技術的リスクと解決状況

#### 高リスク (全て解決済み)

| リスク | 対策 | 解決 |
|--------|------|------|
| `textToAudio` が `languageId` を変更して復元しない | `ConfigGuard` RAII で自動 save/restore + `phonemizeText` 自体の副作用も除去 | M1-6, M5-1, M5-8 |
| 辞書パス自動検出が共有ライブラリで機能しない | `dict_dir` フィールド追加 + `dladdr()` / `GetModuleHandleEx` による自動検出 | M1-3, M4-6 |
| Iterator / one-shot 合成の再入問題 | `BusyGuard` RAII で自動管理。`PIPER_PLUS_ERR_BUSY` (-5) | M1-6, M5-1, M5-13 |
| OpenJTalk/spdlog の -fPIC 不足 | ExternalProject に `CMAKE_POSITION_INDEPENDENT_CODE=ON` 追加 | M1-1 |

#### 中リスク (全て解決済み)

| リスク | 対策 | 解決 |
|--------|------|------|
| 言語名->ID 変換 API の欠如 | `piper_plus_language_id()` + `piper_plus_available_languages()` | M1-6, M4-3 |
| `-static-libstdc++` の共有ライブラリ競合 | `piper` (CLI) のみに適用。共有ライブラリは動的リンク | M1-2 |
| macOS RPATH が `@executable_path` | `@loader_path` に設定。ORT install_name も修正 | M1-4, M3-4 |
| Iterator の文分割が想定より複雑 | `phonemizeText()` / `splitTextToSentences()` を抽出。多言語文分割も改善 | M2-1, M5-2 |
| `OPENJTALK_DIC_PATH` が OBJECT ライブラリと非互換 | 消費側 target で個別設定 | M1-4 |
| textToAudioStreaming のマルチリンガル未対応 | Iterator ベースで実装。後に内部を Iterator 駆動に置換し根本解決 | M5-16 |

#### 低リスク (全て解決済み)

| リスク | 対策 | 解決 |
|--------|------|------|
| int16->float32 2重変換 | `textToAudioFloat()` / `synthesizeFloat()` で float32 直接出力 | M4-5 |
| 辞書パス初期化のレース条件 | ヘッダーに排他制約を明記 | 対策済み |
| num_threads の未対応 | `Ort::SessionOptions::SetIntraOpNumThreads()` に反映 | M5-5 |

### 4.4 正誤表

| セクション | 元の記述 | 正しい内容 |
|-----------|---------|-----------|
| 言語自動検出 | 「languageId をデフォルト値 (0) のまま渡すだけで自動検出が有効」 | 正確には「`synthesisConfig.languageId` が入口時点の `originalLanguageId` と一致していれば自動検出が発動」 |
| ストリーミングのマルチリンガル | 「piper.cpp L1756-1761 で TODO」 | `usesOpenJTalk()` が `MultilingualPhonemes` でも true を返すためデッドコード。M5-16 で根本解決 |
| グローバルステート | `dict_path` と `g_openjtalk_bin_path` のみ | 追加: `data_dir`, `exe_dict_path`, `warnedNoCmuDict` (static bool) |

---

## 5. マイルストーン

### 概要

| Phase | 内容 | チケット数 | Status |
|-------|------|-----------|--------|
| Phase 1 | 基本 C API (MVP) -- ワンショット合成 + 3 プラットフォームビルド | 8 | **Done** |
| Phase 2 | ストリーミング + テスト | 6 | **Done** |
| Phase 3 | 配布 | 6 | **Done** |
| Phase 4 | 拡張 | 6 | **Done** |
| Phase 5 | 品質改善 + エコシステム拡大 | 21 (M5-1〜M5-21) | **Done** |
| **合計** | | **47** | |

### Phase 1: 基本 C API (MVP)

**依存関係グラフ:**

```
M1-1 (-fPIC)  ──────────────────────────────┐
                                             v
M1-5 (piper_plus.h) ──┬──> M1-4 (CMake + OBJECT lib) ──┐
                       │                                 │
M1-2 (-static-libstdc++)                                 v
                                                  M1-6 (C API 実装)
M1-3 (dict_dir) ─────────────────────────────────┘      │
                                                         v
                                                  M1-7 (テスト)
                                                         │
                                                         v
                                                  M1-8 (CI)
```

**成果物:** `libpiper_plus.so` / `.dylib` / `.dll`, `piper_plus.h` ヘッダー, ワンショット合成, speaker_id / language_id / dict_dir 対応, 3 プラットフォームビルド

### Phase 2: ストリーミング + テスト

**依存関係グラフ:**

```
M1-8 (Phase 1 完了)
    │
    v
M2-1 (音素化ループ抽出) ──> M2-2 (Iterator) ──┬──> M2-4 (ストリーミングテスト)
                                                │         │
                                          M2-3 (Callback) │
                                                          v
                                                   M2-5 (統合テスト)
                                                          │
                                                          v
                                                   M2-6 (CI 更新)
```

**成果物:** Iterator パターン, コールバック合成, 単体テスト + 統合テスト, CI 統合

### Phase 3: 配布

**依存関係グラフ:**

```
Phase 2 完了
    │
    v
M3-1 (install manifest) ──┬──> M3-2 (pkg-config) ──────┬──> M3-6 (examples)
                           │                             │
                           ├──> M3-3 (CMake Config) ─────┤
                           │                             │
                           └──> M3-4 (RPATH fix) ────────┘
                                    │
                                    v
                              M3-5 (release workflow) ──> M3-6 (examples)
```

**成果物:** リリースワークフロー, pkg-config / CMake Config パッケージ, 使用例 (`examples/c-api/`)

### Phase 4: 拡張

全チケット独立実装。

**成果物:** カスタム辞書 API, Phoneme timing 出力, G2P 単独利用 API, Android NDK ビルド, float32 直接出力パス, dladdr 辞書自動検出

### Phase 5: 品質改善 + エコシステム拡大

**依存関係グラフ:**

```
Batch 1 (API 基盤改善)
M5-1 (RAII ガード) ──┐
M5-5 (num_threads)   ├──> Batch 2 (ストリーミング改善)
M5-6 (providers)     │    M5-2 (多言語文分割) ──┐
M5-9 (ゼロ初期化)    │    M5-7 (中断 API)       ├──> Batch 3 (内部改善)
M5-12 (reserved)     │    M5-8 (phonemize純粋)  │    M5-3 (crossfade) ──┐
M5-13 (enum化) ──────┘                          │    M5-4 (多言語例)    │
                                                 │    M5-10 (getExeDir)  │
                                                 │                       │
Batch 4a (API + CI)                              │    Batch 4b (ビルド)  │
M5-14 (create パターン) ─┐                       │    M5-15 (CMake分割)  │
M5-17 (reusable WF)     │                       │    M5-21 (音声回帰)   │
                         v                       v                       v
Batch 5 (エコシステム)
M5-11 (Android multi-ABI) ──┐
M5-16 (Streaming移行)       ├──> M5-20 (Android AAR)
M5-18 (Dart FFI サンプル)    │
M5-19 (Godot GDExtension)  ─┘
```

**成果物:**
- API 基盤: RAII ガード, num_threads / CoreML / DirectML, ゼロ初期化安全策, enum 化, create の status+out パターン
- ストリーミング: 多言語文分割改善, crossfade, 中断 API, phonemizeText 副作用除去, Iterator 駆動移行
- ビルド: CMake 9ファイル分割, CI reusable workflow, Android multi-ABI
- エコシステム: Dart FFI サンプル, Godot GDExtension サンプル, Android AAR, 音声回帰テスト

### Phase 別サマリ

| Phase | チケット | 見積り (小/中/大) | Status |
|-------|---------|-----------------|--------|
| Phase 1 | M1-1〜M1-8 | 小x2 + 中x4 + 大x2 | **Done** |
| Phase 2 | M2-1〜M2-6 | 小x1 + 中x4 + 大x1 | **Done** |
| Phase 3 | M3-1〜M3-6 | 小x2 + 中x3 + 大x1 | **Done** |
| Phase 4 | M4-1〜M4-6 | 中x5 + 大x1 | **Done** |
| Phase 5 | M5-1〜M5-21 | 小x2 + 中x13 + 大x6 | **Done** |

### 全体スケジュール

```
Phase 1 (MVP)         Phase 2 (ストリーミング)   Phase 3 (配布)          Phase 4 (拡張)      Phase 5 (品質+エコシステム)
M1-1 → M1-4 ──────→ M2-1 → M2-2 ──────────→ M3-1 ──────────────→ M4-1〜M4-6 ────→ M5-1〜M5-21
M1-5 ↗   ↘ M1-6     M2-3 ↗  ↘ M2-4          M3-2, M3-3, M3-4      (独立)             (5 Batch)
M1-2 ↗     ↘ M1-7        M2-5 → M2-6       M3-5 → M3-6
M1-3 ↗       ↘ M1-8
[Done]                [Done]                  [Done]                [Done]             [Done]
```

### 振り返り (設計判断の再検討)

**Phase 1:**
- M1-1 (fPIC) / M1-2 (static-libstdc++) は M1-4 (CMake) にまとめても良かった
- RPATH / install を Phase 1 に含めるべきだった -> 対応済み: M1-4 に RPATH/GNUInstallDirs/EXPORT を統合

**Phase 2:**
- Iterator を `textToAudio` ベースにした判断は正しい (`textToAudioStreaming` のデッドコード回避)
- Iterator の crossfade 非対応 -> M5-3 で解決

**Phase 3:**
- pkg-config + CMake Config 両方の提供は低コストで両立可能

**Phase 4:**
- G2P 単独 API と Rust piper-g2p FFI は設計哲学が異なる (C++ 版はエンジン依存)。長期的には Rust FFI 呼び出し移行を検討

---

## 6. 完了チケット一覧 (47件)

### Phase 1: 基本 C API (M1-1〜M1-8)

| ID | タイトル | 見積り |
|----|---------|--------|
| M1-1 | ExternalProject に `-fPIC` を追加 | 小 |
| M1-2 | `-static-libstdc++` を共有ライブラリに適用しない | 小 |
| M1-3 | PiperPlusConfig に `dict_dir` フィールド追加 | 中 |
| M1-4 | CMake `PIPER_PLUS_BUILD_SHARED` + OBJECT ライブラリ | 大 |
| M1-5 | `piper_plus.h` ヘッダー作成 | 中 |
| M1-6 | `piper_plus_c_api.cpp` 実装 | 大 |
| M1-7 | C API 単体テスト (モデル不要) 24件 | 中 |
| M1-8 | CI 統合 (3 プラットフォームビルド検証) | 中 |

<details><summary>M1 チケット詳細</summary>

**M1-1:** Linux x86_64 で共有ライブラリビルド時のリンクエラー回避。OpenJTalk/spdlog/hts_engine に `-DCMAKE_POSITION_INDEPENDENT_CODE=ON` および `CFLAGS=-fPIC` を追加。

**M1-2:** `-static-libgcc -static-libstdc++` を `piper` 実行ファイルのみに限定。`-Wl,-rpath,'$ORIGIN'` をグローバルから `piper` ターゲット固有に移動。

**M1-3:** 共有ライブラリ利用者が OpenJTalk 辞書ディレクトリを明示指定可能にする `dict_dir` フィールドを追加。`setenv("OPENJTALK_DICTIONARY_PATH", ...)` 方式で統合。

**M1-4:** `piper_common` OBJECT ライブラリでソース二重列挙を解消。GNUInstallDirs、EXPORT PiperPlusTargets、RPATH 設定 (`$ORIGIN` / `@loader_path`) を含む。

**M1-5:** C99/C++17 両対応の公開 C API ヘッダー。POD struct、opaque handle、`PIPER_PLUS_API` エクスポートマクロ、`_reserved` ABI パディング、スレッドセーフティドキュメント。Dart `ffigen` 互換。

**M1-6:** Phase 1 全 API 関数の実装。`synthesisConfig` save/restore、`atomic<bool> inProgress` による再入防止、`thread_local` エラーメッセージ、int16->float32 変換。

**M1-7:** Google Test ベースの 24 テストケース。バージョン情報、デフォルトオプション、NULL 安全性、無効モデルパス、エラーメッセージ取得、ステータスコード定数、struct memset 安全性。

**M1-8:** `cpp-tests.yml` に共有ライブラリビルド + テストを統合。Windows マトリクス追加、シンボル可視性検証、Linux `libstdc++` 動的リンク確認。

</details>

### Phase 2: ストリーミング + テスト (M2-1〜M2-6)

| ID | タイトル | 見積り |
|----|---------|--------|
| M2-1 | textToAudio の音素化ループを再利用可能関数に抽出 | 中 |
| M2-2 | Iterator パターン (synth_start / synth_next) | 大 |
| M2-3 | コールバック合成 (synthesize_streaming) | 小 |
| M2-4 | ストリーミング単体テスト (モデル不要) 13件 | 中 |
| M2-5 | 統合テスト (モデル必要) 13件 | 中 |
| M2-6 | CI 統合更新 | 中 |

<details><summary>M2 チケット詳細</summary>

**M2-1:** `textToAudio()` から `phonemizeText()` と `splitTextToSentences()` を抽出する純粋なリファクタリング。Iterator パターン (M2-2) の前提条件。

**M2-2:** 文単位の逐次合成 API。`synth_start()` でテキストを文分割してキューに保持し、`synth_next()` で 1 文ずつ合成。`textToAudio()` ベースでマルチリンガルを完全サポート。

**M2-3:** M2-2 の Iterator を内部駆動する薄いラッパー。`PiperPlusAudioCallback` でチャンクごとにコールバック呼び出し。Dart `NativeCallable.listener` 互換 (void 戻り)。

**M2-4:** 13 テストケース。Iterator/コールバックの NULL safety、`PiperPlusAudioChunk` struct レイアウト検証、ステータスコード定数、排他制御 precedence。

**M2-5:** テストモデル (`multilingual-test-medium.onnx`) を使用した 13 テストケース。ワンショット/Iterator/コールバックの全合成パス検証、クエリ API、排他制御、speaker_id 変更、Iterator 再利用。

**M2-6:** テストモデル + 辞書のキャッシュ機構追加。統合テストとシンボル可視性検証を 3 プラットフォーム CI に組み込み。

</details>

### Phase 3: 配布 (M3-1〜M3-6)

| ID | タイトル | 見積り |
|----|---------|--------|
| M3-1 | 配布ファイルマニフェスト + install ターゲット整備 | 中 |
| M3-2 | pkg-config ファイル生成 | 小 |
| M3-3 | CMake Config パッケージ生成 | 中 |
| M3-4 | macOS RPATH 修正 + プラットフォーム別リンク設定 | 小 |
| M3-5 | リリースワークフロー拡張 (4 プラットフォーム) | 大 |
| M3-6 | 使用例ドキュメント (`examples/c-api/`) | 中 |

<details><summary>M3 チケット詳細</summary>

**M3-1:** ONNX Runtime 同梱 install、OpenJTalk 辞書/G2P 辞書 install、`verify_install_layout.cmake` 検証スクリプト。

**M3-2:** `cmake/piper_plus.pc.in` テンプレートから `piper_plus.pc` を生成。`dictdir`/`g2p_dictdir` カスタム変数、`Libs.private` に ORT。

**M3-3:** `find_package(PiperPlus)` + `target_link_libraries(app PiperPlus::piper_plus)` を実現。`PiperPlusConfig.cmake.in`、`write_basic_package_version_file`。

**M3-4:** ONNX Runtime dylib の `install_name` を `@rpath/...` に修正する `install_name_tool` カスタムコマンド。install 後の RPATH 検証テスト。

**M3-5:** 4 プラットフォーム (Linux x64/arm64, macOS arm64, Windows x64) の共有ライブラリ配布。install layout/RPATH/シンボル可視性/pkg-config 検証、リリースアセット自動アップロード。

**M3-6:** `examples/c-api/` に 3 つの C サンプル (basic/streaming/multi_language)。Makefile (pkg-config) + CMakeLists.txt (find_package) の両方でビルド可能。

</details>

### Phase 4: 拡張 (M4-1〜M4-6)

| ID | タイトル | 見積り |
|----|---------|--------|
| M4-1 | カスタム辞書 API | 中 |
| M4-2 | Phoneme timing 出力 | 中 |
| M4-3 | G2P 単独利用 API | 中 |
| M4-4 | Android NDK ビルド | 大 |
| M4-5 | int16/float32 二重変換の解消 | 中 |
| M4-6 | dladdr による辞書自動検出改善 | 中 |

<details><summary>M4 チケット詳細</summary>

**M4-1:** 既存の `CustomDictionary` C++ クラスを C API でラップ。`piper_plus_load_custom_dict()`, `piper_plus_clear_custom_dict()`, `piper_plus_add_dict_word()`, `piper_plus_dict_entry_count()` の 4 関数。JSON v1.0/v2.0 対応。

**M4-2:** 合成後の音素タイミング情報 (開始/終了時刻、フレームインデックス) を C 構造体で取得。`PiperPlusPhonemeInfo`/`PiperPlusTimingResult` + `piper_plus_get_phoneme_timing()`。リップシンク (Godot/Unity) 向け。

**M4-3:** ONNX 推論なしでテキストから IPA 音素列に変換。`piper_plus_phonemize()` + `piper_plus_available_languages()`。カスタム辞書 (M4-1) との統合済み。

**M4-4:** Android NDK ツールチェインで `libpiper_plus.so` (arm64-v8a) をクロスコンパイル。ONNX Runtime Android AAR 統合、全 ExternalProject のツールチェイン引き渡し、ARM64 NEON 有効化。

**M4-5:** `float32 -> int16 -> float32` の二重変換を解消。`synthesize()` に float32 出力バリアント追加。C API は ONNX 出力を直接 float32 のまま返却。既存 int16 パス (CLI/WAV) は維持。

**M4-6:** `dladdr()` / `GetModuleHandleEx()` でライブラリ自身のパスを取得し、`../share/open_jtalk/dic/` を自動検出。`library_path.h/c` に統一ヘルパー。3 箇所のフォールバック付き統合。

</details>

### Phase 5: 品質改善 (M5-1〜M5-21)

| ID | タイトル | 見積り |
|----|---------|--------|
| M5-1 | RAII ガード導入 (ConfigGuard / BusyGuard) | 小 |
| M5-2 | 多言語文分割の改善 | 中 |
| M5-3 | Iterator crossfade 対応 | 中 |
| M5-4 | multi_language.c サンプル追加 | 小 |
| M5-5 | num_threads ORT SessionOptions 接続 | 小 |
| M5-6 | CoreML / DirectML provider 対応 | 小 |
| M5-7 | ストリーミング中断 API (synthesize_streaming_ex) | 小 |
| M5-8 | phonemizeText 副作用除去 | 中 |
| M5-9 | SynthOptions ゼロ初期化対策 | 小 |
| M5-10 | getExeDir() 統一 (Closed: M4-6 で解決済み) | 小 |
| M5-11 | Android armeabi-v7a / x86_64 対応 | 中 |
| M5-12 | PiperPlusPhonemeResult._reserved 追加 | 小 |
| M5-13 | ステータスコード enum 化 | 小 |
| M5-14 | piper_plus_create を status + out_engine パターンに変更 | 中 |
| M5-15 | CMakeLists.txt ファイル分割 (9ファイル) | 中 |
| M5-16 | textToAudioStreaming Iterator 駆動移行 | 大 |
| M5-17 | cpp-tests.yml / ci.yml 重複解消 | 小 |
| M5-18 | Dart FFI サンプル | 中 |
| M5-19 | Godot GDExtension サンプル | 中 |
| M5-20 | Android AAR パッケージング | 大 |
| M5-21 | 音声回帰テスト | 中 |

<details><summary>M5 チケット詳細</summary>

**M5-1:** `piper_plus_c_api.cpp` の手動 SynthesisConfig save/restore (14箇所) と `inProgress.store(false)` (17箇所) を RAII クラスで自動化。

**M5-2:** `splitTextToSentences()` が JA 正規表現のみだった問題を修正。CJK + Latin 句読点の両方に対応した多言語統合正規表現パターン。

**M5-3:** Iterator パターンの文境界でのクリック音を crossfade 処理で解消。`IteratorState` に `prevTail` バッファ追加、10ms (220サンプル @ 22050Hz) の線形 crossfade。

**M5-4:** `examples/c-api/multi_language.c` に 6 言語テキストの順次合成と `language_id` 自動検出のデモ。

**M5-5:** `PiperPlusConfig.num_threads` を `Ort::SessionOptions::SetIntraOpNumThreads()` に接続。`num_threads=0` は ORT デフォルト維持。

**M5-6:** `PiperPlusConfig.provider` に `"coreml"` (macOS/iOS) と `"directml"` (Windows) を追加。`useCuda` フラグを `provider` 文字列に置換。

**M5-7:** コールバック戻り値 (`int`: 0=continue, 非0=abort) で合成を途中中断できる `piper_plus_synthesize_streaming_ex()` を追加。

**M5-8:** `phonemizeText()` が `voice.synthesisConfig.languageId` を副作用として変更していた問題を修正。検出結果を `PhonemizeResult.detectedLanguageId` で返す純粋関数に変更。

**M5-9:** FFI 利用者が `memset` / `calloc` でゼロ初期化した `PiperPlusSynthOptions` でも安全動作。`noise_scale=0.0` 等をデフォルト値に自動置換。

**M5-10:** M4-6 (dladdr) の `library_path.h/c` で解決済みのためクローズ。

**M5-11:** `android-build.yml` を 3 ABI マトリクス (`arm64-v8a`, `armeabi-v7a`, `x86_64`) に拡張。

**M5-12:** `PiperPlusPhonemeResult` に `_reserved[4]` フィールドを追加し ABI 拡張性を確保。

**M5-13:** `#define` マクロから `typedef enum PiperPlusStatus` に変更。`ERR_BUSY` (-5) / `ERR_ORT` (-6) 追加。`static_assert` で `int32_t` とのサイズ一致を保証。

**M5-14:** `piper_plus_create()` の戻り値を `PiperPlusEngine*` から `PiperPlusStatus` に変更。`ERR_MODEL` / `ERR_CONFIG` / `ERR_ORT` の正確な返却が可能に。

**M5-15:** 1,080行超のルート `CMakeLists.txt` を 9 つの `cmake/*.cmake` モジュールに分割。ルートを ~50行の `include()` に縮小。

**M5-16:** `piper.cpp` の `textToAudioStreaming()` 内部を Iterator 駆動に書き換え。`MultilingualPhonemes` デッドコード問題を根本解決。

**M5-17:** C++ テスト部分を `_build-test-cpp.yml` reusable workflow に抽出。テスト定義の重複解消。

**M5-18:** `examples/dart/` に Flutter での C API 利用リファレンス。`NativeCallable.listener` でストリーミングを `Stream<Uint8List>` に変換。

**M5-19:** `examples/godot/` に C API 経由の GDExtension ラッパー。PiperTTS ノード + SConstruct ~30行。

**M5-20:** JNI ラッパー + Kotlin API (`PiperPlus.kt`) による AAR パッケージ。Gradle ベースの配布準備。

**M5-21:** deterministic 合成の SHA-256 ハッシュ比較による音声回帰テスト。`UPDATE_BASELINE=1` による更新メカニズム。

</details>

---

## 7. ビルド・配布

### 7.1 CMake モジュール分割 (M5-15)

ルート `CMakeLists.txt` を 9 つの `cmake/*.cmake` モジュールに分割済み:

| モジュール | 役割 |
|-----------|------|
| `cmake/CompilerSettings.cmake` | コンパイラフラグ、C/C++ 標準設定 |
| `cmake/ExternalDeps.cmake` | OpenJTalk, spdlog, fmt 等の ExternalProject (-fPIC 設定含む) |
| `cmake/OnnxRuntime.cmake` | ONNX Runtime 検出/自動ダウンロード |
| `cmake/PiperCommon.cmake` | OBJECT ライブラリ `piper_common` (ソース一元管理) |
| `cmake/PiperPlusShared.cmake` | 共有ライブラリ `piper_plus` (`PIPER_PLUS_BUILD_SHARED=ON` 時) |
| `cmake/PiperExecutable.cmake` | CLI 実行ファイル `piper` |
| `cmake/PiperLink.cmake` | リンク設定共通化 |
| `cmake/Testing.cmake` | テストターゲット (Google Test) |
| `cmake/Install.cmake` | install ルール (GNUInstallDirs, EXPORT) |

### 7.2 OBJECT ライブラリによるソース共有

```cmake
# cmake/PiperCommon.cmake
add_library(piper_common OBJECT ${PIPER_CORE_SOURCES})
set_target_properties(piper_common PROPERTIES POSITION_INDEPENDENT_CODE ON)

# cmake/PiperExecutable.cmake
add_executable(piper src/cpp/main.cpp src/cpp/model_manager.cpp)
target_link_libraries(piper PRIVATE piper_common ...)

# cmake/PiperPlusShared.cmake
add_library(piper_plus SHARED src/cpp/piper_plus_c_api.cpp)
target_link_libraries(piper_plus PRIVATE piper_common ...)
```

### 7.3 -fPIC 対応 (M1-1)

OpenJTalk / spdlog / hts_engine_stub が `-fPIC` なしで静的ビルドされていた問題を解決:

```cmake
# 全 ExternalProject に追加
-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=ON
```

macOS/Windows は影響なし (常に PIC)。パフォーマンスオーバーヘッドは 1% 未満。

### 7.4 プラットフォーム別設定

| 設定 | Linux | macOS | Windows |
|------|-------|-------|---------|
| 出力名 | `libpiper_plus.so.1` | `libpiper_plus.1.dylib` | `piper_plus.dll` + `piper_plus.lib` |
| RPATH | `$ORIGIN` | `@loader_path` | N/A |
| C++ runtime | `libstdc++` 動的リンク (共有ライブラリ)、`-static-libstdc++` (CLI のみ) | system | MSVC DLL |
| export | `visibility("default")` | `visibility("default")` | `__declspec(dllexport)` |

### 7.5 install ターゲット

```
lib/libpiper_plus.so(.1)(.1.10.0) | .dylib | .dll + .lib
lib/libonnxruntime.so | .dylib | .dll
include/piper_plus.h
share/open_jtalk/dic/
share/piper/dicts/ (CMU, pinyin)
lib/pkgconfig/piper_plus.pc
lib/cmake/PiperPlus/
```

### 7.6 依存ライブラリ

| ライブラリ | バージョン | リンク形態 | 備考 |
|-----------|-----------|-----------|------|
| ONNX Runtime | 1.14.1 | 動的リンク | 自動ダウンロード |
| OpenJTalk (pyopenjtalk-plus) | 0.4.1.post7 | 静的リンク | 日本語 G2P |
| HTS Engine | 1.10 | スタブ (静的) | デフォルト |
| spdlog | 1.12.0 | 静的リンク | ロギング |
| fmt | 10.0.0 | ヘッダーオンリー | フォーマッティング |
| nlohmann/json | -- | ヘッダーオンリー | JSON 処理 |

---

## 8. CI/CD

### 8.1 Reusable workflow (M5-17)

C++ テスト部分を `_build-test-cpp.yml` reusable workflow に抽出し、`cpp-tests.yml` と `ci.yml` の両方から呼び出す構造に統一。

### 8.2 CI マトリクス

| ワークフロー | プラットフォーム | 内容 |
|-------------|-----------------|------|
| `_build-test-cpp.yml` | Linux, macOS, Windows | 共有ライブラリビルド + C API テスト (単体/統合) |
| `android-build.yml` | Android arm64-v8a/armeabi-v7a/x86_64 | NDK クロスコンパイル + multi-ABI |
| 既存 `cpp-tests.yml` | Linux, macOS, Windows | reusable workflow 経由 |

### 8.3 検証項目

| テスト | 内容 |
|--------|------|
| ビルド成功 | 3 プラットフォーム + 3 Android ABI で `.so`/`.dylib`/`.dll` 生成 |
| シンボル確認 | `nm -D` / `nm -gU` / `dumpbin /EXPORTS` で公開 API のみエクスポート |
| 単体テスト | モデル不要テスト (NULL safety, バージョン, デフォルトオプション等) |
| 統合テスト | テストモデルによるライフサイクル (create -> synthesize -> free)、Iterator、ストリーミング |
| 音声回帰テスト | deterministic 合成の SHA-256 ハッシュ比較 (M5-21) |
| テストモデルキャッシュ | CI キャッシュによるモデルダウンロード高速化 |

### 8.4 リリース配布プラットフォーム

Linux x86_64, Linux aarch64, macOS arm64, Windows x64 の 4 プラットフォームで共有ライブラリを配布。`build-piper.yml` に `build-shared` input 追加、install layout/RPATH/シンボル可視性/pkg-config 検証、リリースアセット自動アップロード。

---

## Appendix: endo5501 実装 (参考)

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
