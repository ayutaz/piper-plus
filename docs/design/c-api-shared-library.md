# C API 共有ライブラリ (Issue #295) — 要求定義書

> **Status:** Implemented (Phase 1〜5 全完了)
> **Issue:** [#295](https://github.com/ayutaz/piper-plus/issues/295)
> **Branch:** `feature/c-api-shared-library`
> **Date:** 2026-04-03 (Phase 5 完了時点に更新)

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

- 全関数は `PiperPlusStatus` (enum) を返す (0 = 成功, 正 = 完了, 負 = エラー)
- ステータスコード (`typedef enum PiperPlusStatus`): `PIPER_PLUS_OK` (0), `PIPER_PLUS_DONE` (1), `PIPER_PLUS_ERR` (-1), `PIPER_PLUS_ERR_MODEL` (-2), `PIPER_PLUS_ERR_CONFIG` (-3), `PIPER_PLUS_ERR_TEXT` (-4), `PIPER_PLUS_ERR_BUSY` (-5), `PIPER_PLUS_ERR_ORT` (-6)
- `piper_plus_get_last_error()` でエラーメッセージ取得 (スレッドローカル)
- C++ 例外は API 境界で全捕捉 (例外がライブラリ外に漏れない)
- **実装済み (M5-13):** `#define` 定数から `typedef enum PiperPlusStatus` に変更し、`ERR_BUSY` / `ERR_ORT` を追加

#### NFR-5: シンボル可視性

- デフォルト: `-fvisibility=hidden` (GCC/Clang), 全シンボル非公開
- 公開 API のみ `PIPER_PLUS_API` マクロでエクスポート
- Windows: `__declspec(dllexport)` / `__declspec(dllimport)` 切替

#### NFR-6: 文字列エンコーディング

- 全文字列パラメータは UTF-8
- ONNX Runtime ガイドライン準拠
- Dart/Go/Rust/Swift すべてと互換

---

## 5. 実装済み API (Phase 5 完了時点)

> **注:** 以下は実装済みの `src/cpp/piper_plus.h` の内容を反映。初期設計案からの主な変更点は 5.1 節で説明。

**全 API 関数一覧:**

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

**ステータスコード (typedef enum PiperPlusStatus):**

| 値 | 名前 | 説明 |
|----|------|------|
| 0 | `PIPER_PLUS_OK` | 成功 |
| 1 | `PIPER_PLUS_DONE` | Iterator: チャンク終了 |
| -1 | `PIPER_PLUS_ERR` | 汎用エラー |
| -2 | `PIPER_PLUS_ERR_MODEL` | モデル読み込み失敗 |
| -3 | `PIPER_PLUS_ERR_CONFIG` | 設定読み込み失敗 |
| -4 | `PIPER_PLUS_ERR_TEXT` | 不正テキスト入力 |
| -5 | `PIPER_PLUS_ERR_BUSY` | 合成中の再入 |
| -6 | `PIPER_PLUS_ERR_ORT` | ONNX Runtime エラー |

**Config struct (POD, memset-safe):**

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

**SynthOptions (zero-init safe):**

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

**Cancellable streaming callback (M5-7):**

```c
typedef int (*PiperPlusAudioCallbackEx)(
    const float *samples, int32_t num_samples, int32_t sample_rate, void *user_data);

PIPER_PLUS_API PiperPlusStatus piper_plus_synthesize_streaming_ex(
    PiperPlusEngine *engine, const char *text,
    const PiperPlusSynthOptions *opts, PiperPlusAudioCallbackEx callback, void *user_data);
```

> 完全なヘッダーは `src/cpp/piper_plus.h` を参照。

### 5.1 初期設計案からの変更点 (Phase 5)

| 変更 | 初期設計案 | 実装 (Phase 5 後) | 理由 / チケット |
|------|-----------|------------------|----------------|
| ステータスコード | `#define` 定数 | `typedef enum PiperPlusStatus` | デバッガでの可読性向上。ABI 互換性は `int32_t` と同等 (M5-13) |
| `piper_plus_create` | `PiperPlusEngine*` 戻り | `PiperPlusStatus` 戻り + `out_engine` | `ERR_MODEL` / `ERR_CONFIG` / `ERR_ORT` の正確な返却 (M5-14) |
| `PiperPlusConfig` | `_reserved[8]` | `dict_dir` フィールド + `_reserved[7]` | 共有ライブラリでの辞書パス指定 (M1-3) |
| `num_threads` | 設計のみ (Phase 1 では無視) | `Ort::SessionOptions::SetIntraOpNumThreads()` に反映 (M5-5) |
| `provider` | `"cpu"` / `"cuda"` のみ | `"coreml"` / `"directml"` も実装済み (M5-6) |
| ゼロ初期化 | 未規定 | `noise_scale` 等が 0.0 ならデフォルト値に自動置換 (M5-9) |
| ストリーミング中断 | 未設計 | `synthesize_streaming_ex` + `PiperPlusAudioCallbackEx` (M5-7) |
| 追加エラーコード | なし | `ERR_BUSY` (-5), `ERR_ORT` (-6) (M5-13) |

### 5.2 API 設計判断の根拠

| 設計判断 | 根拠 |
|----------|------|
| 4つの合成パターン (one-shot / iterator / callback / cancel-callback) | one-shot は Python/C#、iterator は Go/Rust、callback は Flutter/Dart、cancel-callback はリアルタイム中断に最適 |
| `_reserved[7]`/`[8]` | struct サイズ変更なしで将来フィールド追加可能 (ABI 互換) |
| `language_id = -1` で自動検出 | piper-plus の `MultilingualPhonemizer` / `LanguageDetector` を活用 |
| `provider` 文字列 | ONNX Runtime の ExecutionProvider 名をそのまま渡せる |
| `PiperPlusAudioCallback` が `void` 戻り | Dart `NativeCallable.listener` との互換性 (void 戻りのみ対応) |
| `PiperPlusAudioCallbackEx` が `int` 戻り | 非ゼロで中断。ゲームエンジン等のリアルタイム用途向け |
| `piper_plus_free_audio()` 専用関数 | アロケータ不一致 (malloc vs new) を防止 |
| `const char*` UTF-8 統一 | ONNX Runtime ガイドライン準拠、全 FFI 言語と互換 |
| グローバルステートなし | 複数エンジンインスタンスの並行利用を許可 |
| `typedef enum PiperPlusStatus` | デバッガでの可読性。`int32_t` とサイズ互換なので ABI は安全 |
| RAII ガード (ConfigGuard / BusyGuard) | 例外発生時も `synthesisConfig` 復元 + `inProgress` フラグ解除を保証 |

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

## 6. CMake ビルド設計 (実装済み)

### 6.1 CMake モジュール分割 (M5-15)

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

**OBJECT ライブラリ `piper_common`** でコアソースを一元管理し、`piper` (実行ファイル)、`piper_plus` (共有ライブラリ)、`test_piper` (テスト) で共有。

### 6.2 プラットフォーム別設定

| 設定 | Linux | macOS | Windows |
|------|-------|-------|---------|
| 出力名 | `libpiper_plus.so.1` | `libpiper_plus.1.dylib` | `piper_plus.dll` + `piper_plus.lib` |
| RPATH | `$ORIGIN` | `@loader_path` | N/A |
| C++ runtime | `libstdc++` 動的リンク (共有ライブラリ)、`-static-libstdc++` (CLI のみ) | system | MSVC DLL |
| export | `visibility("default")` | `visibility("default")` | `__declspec(dllexport)` |
| -fPIC | ExternalProject に `CMAKE_POSITION_INDEPENDENT_CODE=ON` 適用済み | 常に PIC | 常に PIC |

---

## 7. CI 構成 (実装済み)

### 7.1 Reusable workflow (M5-17)

C++ テスト部分を `_build-test-cpp.yml` reusable workflow に抽出し、`cpp-tests.yml` と `ci.yml` の両方から呼び出す構造に統一。

### 7.2 CI マトリクス

| ワークフロー | プラットフォーム | 内容 |
|-------------|-----------------|------|
| `_build-test-cpp.yml` | Linux, macOS, Windows | 共有ライブラリビルド + C API テスト (単体/統合) |
| `android-build.yml` | Android arm64-v8a/armeabi-v7a/x86_64 | NDK クロスコンパイル + multi-ABI |
| 既存 `cpp-tests.yml` | Linux, macOS, Windows | reusable workflow 経由 |

### 7.3 検証項目 (実装済み)

| テスト | 内容 |
|--------|------|
| ビルド成功 | 3 プラットフォーム + 3 Android ABI で `.so`/`.dylib`/`.dll` 生成 |
| シンボル確認 | `nm -D` / `nm -gU` / `dumpbin /EXPORTS` で公開 API のみエクスポート |
| 単体テスト | モデル不要テスト (NULL safety, バージョン, デフォルトオプション等) |
| 統合テスト | テストモデルによるライフサイクル (create → synthesize → free)、Iterator、ストリーミング |
| 音声回帰テスト | deterministic 合成の SHA-256 ハッシュ比較 (M5-21) |
| テストモデルキャッシュ | CI キャッシュによるモデルダウンロード高速化 |

---

## 8. 実装フェーズ (全完了)

### Phase 1: 基本 C API (MVP) -- Done

**成果物:**
- `libpiper_plus.so` / `.dylib` / `.dll`
- `piper_plus.h` ヘッダー
- ワンショット合成 (`piper_plus_synthesize`)
- speaker_id / language_id / dict_dir 対応
- 3 プラットフォームビルド

### Phase 2: ストリーミング + テスト -- Done

**成果物:**
- Iterator パターン (`synth_start` / `synth_next`)
- コールバック合成 (`synthesize_streaming`)
- 単体テスト + 統合テスト (Google Test)
- CI 統合

### Phase 3: 配布 -- Done

**成果物:**
- リリースワークフロー (`cmake --install` ベース)
- pkg-config / CMake Config パッケージ生成
- 使用例ドキュメント (`examples/c-api/`)

### Phase 4: 拡張 -- Done

**成果物:**
- カスタム辞書 API (`load_custom_dict`, `clear_custom_dict`, `add_dict_word`)
- Phoneme timing 出力 (`get_phoneme_timing`)
- G2P 単独利用 API (`piper_plus_phonemize`, `available_languages`)
- Android NDK ビルド (arm64-v8a)
- float32 直接出力パス
- dladdr 辞書自動検出

### Phase 5: 品質改善 + エコシステム拡大 -- Done

**成果物:**
- RAII ガード (ConfigGuard / BusyGuard) (M5-1)
- num_threads / CoreML / DirectML provider 対応 (M5-5, M5-6)
- ゼロ初期化安全対策 (M5-9)
- PiperPlusStatus enum 化 + ERR_BUSY / ERR_ORT 追加 (M5-13)
- piper_plus_create の status+out_engine パターン (M5-14)
- ストリーミング中断 API: synthesize_streaming_ex (M5-7)
- 多言語文分割改善 (M5-2)
- phonemizeText 副作用除去 (M5-8)
- Iterator crossfade (M5-3)
- CMake 分割 (9ファイル) (M5-15)
- CI reusable workflow (M5-17)
- Android multi-ABI (arm64-v8a / armeabi-v7a / x86_64) (M5-11)
- Dart FFI サンプル (`examples/dart/`) (M5-18)
- Godot GDExtension サンプル (`examples/godot/`) (M5-19)
- Android AAR パッケージング (M5-20)
- 音声回帰テスト (M5-21)

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
