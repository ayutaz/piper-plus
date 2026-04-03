# M1-5: `piper_plus.h` ヘッダー作成

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 中
> **依存:** なし (M1-4 と並行可能)
> **ブロック:** M1-3, M1-4, M1-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-5-piper_plush-ヘッダー作成)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

piper-plus の公開 C API ヘッダー `piper_plus.h` を作成する。このヘッダーは共有ライブラリの唯一の公開インターフェースであり、Flutter/Dart (`dart:ffi`)、Godot GDExtension、Swift C interop など、C FFI に依存するプラットフォームから利用される。

**ゴール:**
1. C99 (`gcc -std=c99`) と C++17 (`g++ -std=c++17`) の両方でコンパイルエラーなし
2. Dart `ffigen` 互換 (POD struct + opaque pointer のみ)
3. ABI 安定性のための `_reserved` パディングと `PIPER_PLUS_API_VERSION` 定数
4. スレッドセーフティ・排他制約のドキュメントコメント

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 状態 |
|----------|------|
| `src/cpp/piper_plus.h` | 新規作成 |

### 具体的な変更内容

以下のヘッダーを作成する。要求定義書 Section 5 の設計案を基に、技術調査の指摘事項を反映。

```c
/**
 * @file piper_plus.h
 * @brief piper-plus C API for shared library usage.
 *
 * This header provides a stable C ABI for piper-plus text-to-speech engine.
 * All functions use extern "C" linkage and are compatible with C99 and C++17.
 *
 * Thread safety:
 *   - PiperPlusEngine is NOT thread-safe. Each thread must create its own instance.
 *   - piper_plus_get_last_error() returns a thread-local error message.
 *   - Only one synthesis operation (synthesize / synth_start+synth_next) may be
 *     active on a given engine at any time. Concurrent calls return PIPER_PLUS_ERR_BUSY.
 *
 * Memory management:
 *   - One-shot synthesis: caller must free audio via piper_plus_free_audio().
 *   - Iterator pattern (Phase 2): chunk data is valid until next synth_next() call.
 *   - Engine: caller must free via piper_plus_free().
 *
 * String encoding: All strings are UTF-8.
 */

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

/** Return library version string (e.g. "1.10.0"). Never returns NULL. */
PIPER_PLUS_API const char *piper_plus_version(void);

/** Return API version number. Matches PIPER_PLUS_API_VERSION at build time. */
PIPER_PLUS_API int32_t     piper_plus_api_version(void);

/* ===== Status codes ===== */
#define PIPER_PLUS_OK          0
#define PIPER_PLUS_DONE        1   /* Iterator: no more chunks */
#define PIPER_PLUS_ERR        -1   /* Generic error */
#define PIPER_PLUS_ERR_MODEL  -2   /* Model load failure */
#define PIPER_PLUS_ERR_CONFIG -3   /* Config load failure */
#define PIPER_PLUS_ERR_TEXT   -4   /* Invalid text input */
#define PIPER_PLUS_ERR_BUSY   -5   /* Engine is busy (synthesis in progress) */

/**
 * Return the last error message for the calling thread, or NULL if no error.
 * The returned pointer is valid until the next piper_plus_* call on the same thread.
 */
PIPER_PLUS_API const char *piper_plus_get_last_error(void);

/* ===== Opaque types ===== */
typedef struct PiperPlusEngine PiperPlusEngine;

/* ===== Config structs (POD, memset-safe) ===== */

/**
 * Engine creation configuration.
 * Initialize with memset(&config, 0, sizeof(config)) for safe defaults.
 */
typedef struct PiperPlusConfig {
    const char *model_path;       /**< .onnx file path (UTF-8, required) */
    const char *config_path;      /**< .json config path (UTF-8, NULL = model_path + ".json") */
    const char *provider;         /**< "cpu", "cuda", "coreml", "directml" (NULL = "cpu") */
    int32_t     num_threads;      /**< ONNX Runtime intra-op threads (0 = auto) */
    int32_t     gpu_device_id;    /**< GPU device index (ignored when provider = "cpu") */
    const char *dict_dir;         /**< OpenJTalk dictionary dir (UTF-8, NULL = auto-detect).
                                   *   When using piper-plus as a shared library, set this
                                   *   explicitly since auto-detection uses the host executable
                                   *   path which may not contain the dictionary. */
    int32_t     _reserved[7];     /**< Reserved for future use. Must be zero. */
} PiperPlusConfig;

/**
 * Per-synthesis options.
 * Use piper_plus_default_options() to get recommended defaults.
 */
typedef struct PiperPlusSynthOptions {
    int32_t speaker_id;           /**< Speaker ID (default: 0) */
    int32_t language_id;          /**< Language ID (-1 = auto-detect from text) */
    float   noise_scale;          /**< Noise scale (default: 0.667) */
    float   length_scale;         /**< Length scale (default: 1.0) */
    float   noise_w;              /**< Noise W (default: 0.8) */
    float   sentence_silence_sec; /**< Silence between sentences in seconds (default: 0.2) */
    int32_t _reserved[8];         /**< Reserved for future use. Must be zero. */
} PiperPlusSynthOptions;

/* ===== Lifecycle ===== */

/**
 * Create a piper-plus engine from the given configuration.
 * @param config  Engine configuration. model_path is required.
 * @return Opaque engine pointer, or NULL on failure (check piper_plus_get_last_error()).
 */
PIPER_PLUS_API PiperPlusEngine *piper_plus_create(
    const PiperPlusConfig *config);

/**
 * Free an engine. Passing NULL is a no-op.
 */
PIPER_PLUS_API void piper_plus_free(
    PiperPlusEngine *engine);

/* ===== Default options ===== */

/**
 * Return synthesis options with recommended defaults.
 * Caller can modify individual fields before passing to synthesize().
 */
PIPER_PLUS_API PiperPlusSynthOptions piper_plus_default_options(void);

/* ===== Synthesis: one-shot ===== */

/**
 * Synthesize text to audio (blocking, one-shot).
 *
 * @param engine          Engine created by piper_plus_create().
 * @param text            UTF-8 text to synthesize.
 * @param opts            Synthesis options (NULL = defaults).
 * @param out_samples     [out] Pointer to float array (caller must free with piper_plus_free_audio).
 * @param out_num_samples [out] Number of samples in the output array.
 * @param out_sample_rate [out] Sample rate of the output audio (e.g. 22050).
 * @return PIPER_PLUS_OK on success, negative error code on failure.
 */
PIPER_PLUS_API int32_t piper_plus_synthesize(
    PiperPlusEngine              *engine,
    const char                   *text,
    const PiperPlusSynthOptions  *opts,
    float                       **out_samples,
    int32_t                      *out_num_samples,
    int32_t                      *out_sample_rate);

/**
 * Free audio samples returned by piper_plus_synthesize().
 * Passing NULL is a no-op.
 */
PIPER_PLUS_API void piper_plus_free_audio(float *samples);

/* ===== Query ===== */

/** Return sample rate (e.g. 22050), or 0 if engine is NULL. */
PIPER_PLUS_API int32_t piper_plus_sample_rate(const PiperPlusEngine *engine);

/** Return number of speakers, or 0 if engine is NULL. */
PIPER_PLUS_API int32_t piper_plus_num_speakers(const PiperPlusEngine *engine);

/** Return number of languages, or 0 if engine is NULL. */
PIPER_PLUS_API int32_t piper_plus_num_languages(const PiperPlusEngine *engine);

/**
 * Look up language ID by name (e.g. "ja" -> 0, "en" -> 1).
 * @return Language ID (>= 0), or -1 if not found or engine is NULL.
 */
PIPER_PLUS_API int32_t piper_plus_language_id(
    const PiperPlusEngine *engine,
    const char            *language_name);

#ifdef __cplusplus
}
#endif

#endif /* PIPER_PLUS_H_ */
```

### 設計判断の根拠

| 設計判断 | 根拠 |
|----------|------|
| `#define` 定数 (enum 不使用) | C enum の underlying type は ABI 非安定。Fuchsia / ONNX Runtime ガイドライン準拠 |
| `_reserved[N]` パディング | struct サイズ変更なしで将来フィールド追加可能 |
| `language_id = -1` で自動検出 | piper.cpp 内の `detectDominantLanguage()` を活用 |
| `const char*` UTF-8 統一 | ONNX Runtime / Dart / Go / Rust / Swift 全てと互換 |
| `PIPER_PLUS_ERR_BUSY` コード追加 | 技術調査 5.1 で特定された再入問題への対策 |
| Phase 1 では Iterator / callback を含めない | ヘッダーの Phase 2 拡張時に追加。既存 struct への影響なし |
| `piper_plus_language_id()` クエリ関数 | 技術調査 5.2 で「言語名 -> ID 変換 API の欠如」が指摘されている |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| API 設計エージェント | 1 | ヘッダー作成、ドキュメントコメント記述 |
| レビューエージェント | 1 | C99 / C++17 コンパイル検証、Dart ffigen 互換性確認 |

合計: 2 名。API ヘッダーはプロジェクトの公開インターフェースであるため、設計レビューが重要。

---

## 4. 提供範囲とテスト項目

### スコープ

- `src/cpp/piper_plus.h` の作成
- Phase 1 の API 宣言 (create, free, synthesize, free_audio, default_options, version, api_version, get_last_error, sample_rate, num_speakers, num_languages, language_id)
- エクスポートマクロ、ステータスコード定数、POD struct 定義
- ドキュメントコメント (スレッドセーフティ、メモリ管理、ABI 規約)

### スコープ外

- Phase 2 の API (synth_start, synth_next, synthesize_streaming, PiperPlusAudioChunk, PiperPlusAudioCallback)
- 実装 (M1-6)

### テスト項目

| テスト | 方法 | 期待結果 |
|--------|------|----------|
| C99 コンパイル | `gcc -std=c99 -fsyntax-only -Wall -Wextra piper_plus.h` | エラーなし |
| C++17 コンパイル | `g++ -std=c++17 -fsyntax-only -Wall -Wextra piper_plus.h` | エラーなし |
| MSVC コンパイル | CI (Windows) でビルド | エラーなし |
| `sizeof(PiperPlusConfig)` 安定性 | テストコードで sizeof を検証 | 64-bit: 特定の固定値 |
| `memset` 安全性 | `memset(&config, 0, sizeof(config))` 後に全フィールドがゼロ/NULL | 全てデフォルト値として安全 |
| include guard | 2 回 `#include` してもエラーなし | エラーなし |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `_reserved` のサイズ計算 | 低 | `PiperPlusConfig`: ポインタ 3 つ (24 bytes on 64-bit) + int32_t 2 つ (8 bytes) + ポインタ 1 つ (8 bytes) + `_reserved[7]` (28 bytes) = 68 bytes。アラインメントで 72 bytes になる可能性。`static_assert` でサイズを固定するのは ABI 安定性に逆効果のため行わない |
| Phase 2 で追加するストリーミング API との互換性 | 低 | Phase 2 の API は新しい関数宣言と struct 追加のみ。既存の struct / 関数は変更しない |
| `piper_plus_language_id()` が要求定義書の Section 5 に含まれていない | 低 | 技術調査 5.2 の指摘事項「言語名->ID 変換 API の欠如」への対応として追加。Phase 1 のスコープ内で実装可能 |

### レビュー項目

- [ ] `extern "C"` で全 API が囲まれているか
- [ ] `PIPER_PLUS_API` マクロが Windows (`__declspec`) / Unix (`visibility`) に対応しているか
- [ ] 全ての関数が `PIPER_PLUS_API` でマークされているか
- [ ] `PiperPlusConfig` / `PiperPlusSynthOptions` が POD (Plain Old Data) であるか (仮想関数テーブルなし)
- [ ] `#include` が `<stdint.h>` と `<stddef.h>` のみか (C++ ヘッダーを include していないか)
- [ ] 全ポインタパラメータに NULL 許容の有無がドキュメントされているか
- [ ] `_reserved` フィールドに「Must be zero」が記載されているか
- [ ] スレッドセーフティの制約がヘッダーコメントに記載されているか

---

## 6. 一から作り直すとしたら

API ヘッダーの設計では、以下の追加検討を最初から行う:

1. **バージョンネゴシエーション**: `piper_plus_create()` に `api_version` パラメータを追加し、ライブラリとクライアントの API バージョン不一致を検出する。sherpa-onnx はこれを Config struct のフィールドとして実装している。

2. **エラーコードの拡張性**: `#define` 定数ではなく、`piper_plus_error_name(code)` のような関数でエラーコードを文字列に変換する API を追加する。

3. **Config struct のバージョニング**: `sizeof(PiperPlusConfig)` をパラメータとして渡す方式 (Windows COM の `cbSize` パターン) を採用すれば、`_reserved` フィールドが不要になる:

```c
PiperPlusConfig config;
config.cb_size = sizeof(PiperPlusConfig);  // バージョン識別
```

4. **nullability アノテーション**: Clang の `_Nullable` / `_Nonnull` アノテーションを追加して、静的解析ツールとの統合を強化する。

---

## 実装推奨

> **M1-6 と同一 PR で対応すること。** M1-5 (ヘッダー) は M1-6 (C API 実装) と密結合しており、ヘッダーと実装を分割して PR にする意味が薄い。振り返りで「M1-3 + M1-5 + M1-6 は統合可能だった」と指摘されている (c-api-milestones.md Phase 1 振り返り参照)。

---

## 7. 後続タスクへの連絡事項

- **M1-3 (dict_dir):** `PiperPlusConfig` に `dict_dir` フィールドが含まれている。`_reserved` は 7 要素。
- **M1-4 (CMake):** ヘッダーは `src/cpp/piper_plus.h` に配置。CMake の `PUBLIC_HEADER` プロパティで install 対象にすること。
- **M1-6 (実装):** 全関数の実装が必要。特に以下に注意:
  - `piper_plus_synthesize()` で `synthesisConfig` の save/restore (技術調査 5.1)
  - `piper_plus_language_id()` で `voice.modelConfig.languageIdMap` を検索
  - `piper_plus_get_last_error()` は `thread_local std::string` を使用
- **Phase 2:** 以下の API をヘッダーに追加する:
  - `PiperPlusAudioChunk` struct
  - `PiperPlusAudioCallback` typedef
  - `piper_plus_synth_start()`, `piper_plus_synth_next()`
  - `piper_plus_synthesize_streaming()`
