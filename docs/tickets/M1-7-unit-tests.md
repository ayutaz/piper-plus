# M1-7: C API 単体テスト (モデル不要)

> **Phase:** 1 --- 基本 C API (MVP)
> **見積り:** 中
> **依存:** M1-6 (実装)
> **ブロック:** M1-8
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m1-7-c-api-単体テスト-モデル不要)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

piper-plus C API の Phase 1 関数について、モデルファイルを必要としない単体テストを作成する。テストは既存の Google Test フレームワーク (v1.14.0) を使用し、3 プラットフォーム (Linux, macOS, Windows) で実行可能であること。

**ゴール:**
1. 全 Phase 1 API 関数の基本動作をモデルなしで検証
2. NULL 安全性 (全関数に NULL を渡してもクラッシュしない)
3. エラーメッセージ取得 (`get_last_error()`) の動作確認
4. デフォルト値の正確性確認

---

## 2. 実装する内容の詳細

### 変更対象ファイル

| ファイル | 状態 |
|----------|------|
| `src/cpp/tests/test_c_api.cpp` | 新規作成 |
| `src/cpp/tests/CMakeLists.txt` | テスト追加 |

### 具体的な変更内容

#### 2.1 テストケース (`test_c_api.cpp`)

```cpp
#include <gtest/gtest.h>
#include "piper_plus.h"

// ===== Version tests =====

TEST(CApiVersion, VersionReturnsNonNull) {
    const char* ver = piper_plus_version();
    ASSERT_NE(ver, nullptr);
    EXPECT_GT(strlen(ver), 0u);
}

TEST(CApiVersion, VersionContainsDot) {
    // Version string should be like "1.10.0"
    const char* ver = piper_plus_version();
    EXPECT_NE(strchr(ver, '.'), nullptr);
}

TEST(CApiVersion, ApiVersionMatchesConstant) {
    EXPECT_EQ(piper_plus_api_version(), PIPER_PLUS_API_VERSION);
}

// ===== Default options tests =====

TEST(CApiDefaultOptions, HasExpectedDefaults) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    EXPECT_EQ(opts.speaker_id, 0);
    EXPECT_EQ(opts.language_id, -1);      // Auto-detect
    EXPECT_FLOAT_EQ(opts.noise_scale, 0.667f);
    EXPECT_FLOAT_EQ(opts.length_scale, 1.0f);
    EXPECT_FLOAT_EQ(opts.noise_w, 0.8f);
    EXPECT_FLOAT_EQ(opts.sentence_silence_sec, 0.2f);
}

TEST(CApiDefaultOptions, ReservedFieldsAreZero) {
    PiperPlusSynthOptions opts = piper_plus_default_options();
    for (int i = 0; i < 8; i++) {
        EXPECT_EQ(opts._reserved[i], 0);
    }
}

// ===== NULL safety tests =====

TEST(CApiNullSafety, CreateWithNullConfig) {
    PiperPlusEngine* engine = piper_plus_create(nullptr);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, CreateWithNullModelPath) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = nullptr;

    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

TEST(CApiNullSafety, SynthesizeWithNullEngine) {
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;

    int32_t status = piper_plus_synthesize(
        nullptr, "hello", nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);  // Error code
}

TEST(CApiNullSafety, SynthesizeWithNullText) {
    // Cannot test with valid engine without a model, but ensure it handles NULL text
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;

    int32_t status = piper_plus_synthesize(
        nullptr, nullptr, nullptr, &samples, &num_samples, &sample_rate);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, SynthesizeWithNullOutputParams) {
    int32_t status = piper_plus_synthesize(
        nullptr, "hello", nullptr, nullptr, nullptr, nullptr);
    EXPECT_LT(status, 0);
}

TEST(CApiNullSafety, FreeNullEngine) {
    // Must not crash
    piper_plus_free(nullptr);
}

TEST(CApiNullSafety, FreeAudioNull) {
    // Must not crash
    piper_plus_free_audio(nullptr);
}

// ===== Query functions with NULL engine =====

TEST(CApiQueryNull, SampleRateReturnsZero) {
    EXPECT_EQ(piper_plus_sample_rate(nullptr), 0);
}

TEST(CApiQueryNull, NumSpeakersReturnsZero) {
    EXPECT_EQ(piper_plus_num_speakers(nullptr), 0);
}

TEST(CApiQueryNull, NumLanguagesReturnsZero) {
    EXPECT_EQ(piper_plus_num_languages(nullptr), 0);
}

TEST(CApiQueryNull, LanguageIdReturnsNegative) {
    EXPECT_EQ(piper_plus_language_id(nullptr, "ja"), -1);
}

TEST(CApiQueryNull, LanguageIdNullNameReturnsNegative) {
    EXPECT_EQ(piper_plus_language_id(nullptr, nullptr), -1);
}

// ===== Invalid model path tests =====

TEST(CApiCreateError, InvalidModelPath) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/path/model.onnx";

    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);

    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
    EXPECT_GT(strlen(err), 0u);
}

TEST(CApiCreateError, InvalidModelPathAutoConfig) {
    // config_path = NULL should auto-generate model_path + ".json"
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent/path/model.onnx";
    config.config_path = nullptr;

    PiperPlusEngine* engine = piper_plus_create(&config);
    EXPECT_EQ(engine, nullptr);
}

// ===== Error message tests =====

TEST(CApiErrorMessage, ErrorClearedAfterNoError) {
    // get_last_error() returns NULL when no error has occurred on this thread
    // (or after a successful operation).
    // After a failed create, get_last_error() should return a message.
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));
    config.model_path = "/nonexistent";

    piper_plus_create(&config);  // Will fail

    const char* err = piper_plus_get_last_error();
    EXPECT_NE(err, nullptr);
}

// ===== Status code sanity =====

TEST(CApiStatusCodes, ValuesAreDefined) {
    EXPECT_EQ(PIPER_PLUS_OK, 0);
    EXPECT_GT(PIPER_PLUS_DONE, 0);
    EXPECT_LT(PIPER_PLUS_ERR, 0);
    EXPECT_LT(PIPER_PLUS_ERR_MODEL, 0);
    EXPECT_LT(PIPER_PLUS_ERR_CONFIG, 0);
    EXPECT_LT(PIPER_PLUS_ERR_TEXT, 0);
    EXPECT_LT(PIPER_PLUS_ERR_BUSY, 0);
}

TEST(CApiStatusCodes, ErrorCodesAreDistinct) {
    std::set<int32_t> codes = {
        PIPER_PLUS_OK, PIPER_PLUS_DONE,
        PIPER_PLUS_ERR, PIPER_PLUS_ERR_MODEL,
        PIPER_PLUS_ERR_CONFIG, PIPER_PLUS_ERR_TEXT,
        PIPER_PLUS_ERR_BUSY
    };
    EXPECT_EQ(codes.size(), 7u);
}

// ===== Config struct tests =====

TEST(CApiConfigStruct, MemsetSafe) {
    PiperPlusConfig config;
    memset(&config, 0, sizeof(config));

    EXPECT_EQ(config.model_path, nullptr);
    EXPECT_EQ(config.config_path, nullptr);
    EXPECT_EQ(config.provider, nullptr);
    EXPECT_EQ(config.num_threads, 0);
    EXPECT_EQ(config.gpu_device_id, 0);
    EXPECT_EQ(config.dict_dir, nullptr);
}

TEST(CApiConfigStruct, SynthOptionsMemsetSafe) {
    PiperPlusSynthOptions opts;
    memset(&opts, 0, sizeof(opts));

    EXPECT_EQ(opts.speaker_id, 0);
    EXPECT_EQ(opts.language_id, 0);
    EXPECT_FLOAT_EQ(opts.noise_scale, 0.0f);
    EXPECT_FLOAT_EQ(opts.length_scale, 0.0f);
}
```

#### 2.2 CMakeLists.txt への追加 (`src/cpp/tests/CMakeLists.txt`)

```cmake
# C API test (model-free)
if(PIPER_PLUS_BUILD_SHARED OR BUILD_TESTS)
    list(APPEND TEST_SOURCES test_c_api.cpp)
endif()
```

テスト `test_c_api` は共有ライブラリにリンクする方式と、ソースを直接コンパイルする方式の 2 通りが考えられる。M1-4 で `piper_common` OBJECT ライブラリが定義されるため、以下のいずれかで構成する:

**方式 A: 共有ライブラリにリンク (推奨)**

```cmake
if(${test_name} STREQUAL "test_c_api")
    target_sources(${test_name} PRIVATE
        ../piper_plus_c_api.cpp
    )
    target_link_libraries(${test_name} piper_common)

    # Include directories
    target_include_directories(${test_name} PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/..
        ${CMAKE_BINARY_DIR}/fi/include
        ${CMAKE_BINARY_DIR}/si/include
        ${ORT_INCLUDE_DIR}
        ${CMAKE_BINARY_DIR}/oj/include
        ${CMAKE_BINARY_DIR}/oj/include/openjtalk
        ${CMAKE_BINARY_DIR}/hts_stub/include
    )

    # Link libraries (same as piper_plus)
    target_link_directories(${test_name} PRIVATE
        ${CMAKE_BINARY_DIR}/fi/lib
        ${CMAKE_BINARY_DIR}/si/lib
        ${ORT_LIB_DIR}
    )
    if(WIN32)
        target_link_libraries(${test_name}
            optimized ${CMAKE_BINARY_DIR}/fi/lib/fmt.lib
            debug ${CMAKE_BINARY_DIR}/fi/lib/fmtd.lib
            optimized ${CMAKE_BINARY_DIR}/si/lib/spdlog.lib
            debug ${CMAKE_BINARY_DIR}/si/lib/spdlogd.lib
            ${ORT_LIB_DIR}/onnxruntime.lib
        )
    else()
        target_link_libraries(${test_name} fmt spdlog onnxruntime)
    endif()

    if(UNIX)
        find_package(Threads REQUIRED)
        target_link_libraries(${test_name} Threads::Threads)
    endif()

    link_openjtalk_to_test(${test_name})

    add_dependencies(${test_name} fmt_external spdlog_external)
endif()
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| テストエージェント | 1 | test_c_api.cpp 作成、CMakeLists.txt 更新 |

合計: 1 名。既存のテストパターン (`test_phoneme_parser.cpp`, `test_gpu_device_id.cpp` 等) に倣って実装する。

---

## 4. 提供範囲とテスト項目

### スコープ

- `test_c_api.cpp` の作成 (Google Test)
- `CMakeLists.txt` への test_c_api 追加
- 以下のテストカテゴリを網羅:
  - バージョン情報
  - デフォルトオプション
  - NULL 安全性 (全 API 関数)
  - 無効なモデルパスでのエラー
  - エラーメッセージ取得
  - ステータスコード定数
  - Config struct の memset 安全性

### スコープ外

- モデルを使用する統合テスト (Phase 2 M2-5)
- ストリーミング API のテスト (Phase 2 M2-4)
- パフォーマンステスト

### テスト一覧

| テスト名 | カテゴリ | 内容 |
|----------|---------|------|
| `CApiVersion/VersionReturnsNonNull` | バージョン | `version()` が非 NULL で空でない |
| `CApiVersion/VersionContainsDot` | バージョン | バージョン文字列にドットを含む |
| `CApiVersion/ApiVersionMatchesConstant` | バージョン | `api_version()` == `PIPER_PLUS_API_VERSION` |
| `CApiDefaultOptions/HasExpectedDefaults` | デフォルト | 全デフォルト値の確認 |
| `CApiDefaultOptions/ReservedFieldsAreZero` | デフォルト | `_reserved` がゼロ |
| `CApiNullSafety/CreateWithNullConfig` | NULL 安全 | `create(NULL)` -> NULL + エラー |
| `CApiNullSafety/CreateWithNullModelPath` | NULL 安全 | model_path=NULL -> NULL + エラー |
| `CApiNullSafety/SynthesizeWithNullEngine` | NULL 安全 | エラーコード返却 |
| `CApiNullSafety/SynthesizeWithNullText` | NULL 安全 | エラーコード返却 |
| `CApiNullSafety/SynthesizeWithNullOutputParams` | NULL 安全 | エラーコード返却 |
| `CApiNullSafety/FreeNullEngine` | NULL 安全 | クラッシュなし |
| `CApiNullSafety/FreeAudioNull` | NULL 安全 | クラッシュなし |
| `CApiQueryNull/SampleRateReturnsZero` | クエリ | `sample_rate(NULL)` -> 0 |
| `CApiQueryNull/NumSpeakersReturnsZero` | クエリ | `num_speakers(NULL)` -> 0 |
| `CApiQueryNull/NumLanguagesReturnsZero` | クエリ | `num_languages(NULL)` -> 0 |
| `CApiQueryNull/LanguageIdReturnsNegative` | クエリ | `language_id(NULL, "ja")` -> -1 |
| `CApiQueryNull/LanguageIdNullNameReturnsNegative` | クエリ | `language_id(NULL, NULL)` -> -1 |
| `CApiCreateError/InvalidModelPath` | エラー | 存在しないパス -> NULL + メッセージ |
| `CApiCreateError/InvalidModelPathAutoConfig` | エラー | config_path=NULL の自動生成でも失敗 |
| `CApiErrorMessage/ErrorClearedAfterNoError` | エラー | 失敗後にエラーメッセージ取得可能 |
| `CApiStatusCodes/ValuesAreDefined` | 定数 | OK=0, DONE>0, ERR系<0 |
| `CApiStatusCodes/ErrorCodesAreDistinct` | 定数 | 全コードが一意 |
| `CApiConfigStruct/MemsetSafe` | struct | memset 後に全フィールド NULL/0 |
| `CApiConfigStruct/SynthOptionsMemsetSafe` | struct | memset 後に全フィールド 0 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| 懸念 | 影響度 | 対策 |
|------|--------|------|
| `create` に無効パスを渡すとモデルロードが走り、テストが遅い | 低 | `/nonexistent` パスの場合、ファイルオープン失敗で即座に例外が投げられるため高速 |
| テストが ONNX Runtime に依存する | 中 | `test_c_api` は `piper_common` OBJECT ライブラリにリンクするため、ONNX Runtime ヘッダーとライブラリが必要。CI ではインストール済み |
| Windows の `set` include パス | 低 | `test_c_api.cpp` で `<set>` を include すること (ErrorCodesAreDistinct テスト) |

### レビュー項目

- [ ] 全テストが `ASSERT_*` / `EXPECT_*` で適切な検証を行っているか
- [ ] NULL ポインタテストが全 API 関数を網羅しているか
- [ ] テストが 3 プラットフォームでコンパイル可能か (MSVC, GCC, Clang)
- [ ] CMakeLists.txt でリンク依存が正しく設定されているか
- [ ] テストにモデルファイル依存がないか

---

## 6. 一から作り直すとしたら

### テストの分離レベル

現在のテストは `piper_common` OBJECT ライブラリ全体にリンクしているが、理想的には C API レイヤーのみの薄いテスト (ヘッダーのコンパイルチェック + モック) と、実際のエンジンを使う統合テストを分離する。

**レイヤー 1: ヘッダーコンパイルテスト (C99)**
```c
// test_c_api_header.c (pure C)
#include "piper_plus.h"

void test_compile(void) {
    PiperPlusConfig config = {0};
    PiperPlusSynthOptions opts = piper_plus_default_options();
    (void)config;
    (void)opts;
}
```

**レイヤー 2: API 動作テスト (C++, Google Test)**
```cpp
// test_c_api.cpp (現在のテスト)
// NULL safety, error handling, default values
```

**レイヤー 3: 統合テスト (C++, モデル必要)**
```cpp
// test_c_api_integration.cpp (Phase 2 M2-5)
// create -> synthesize -> verify audio -> free
```

この 3 レイヤー構成を最初から採用すれば、テストの依存関係が明確になる。

---

## 7. 後続タスクへの連絡事項

- **M1-8 (CI):** `test_c_api` を CI のテスト実行リストに追加すること。`ctest -R "^test_c_api$"` で単独実行可能。
- **Phase 2 M2-4 (ストリーミングテスト):** `test_c_api.cpp` にストリーミング API のテストケースを追加する。同一ファイルに追加するか、`test_c_api_streaming.cpp` として分離するか検討。
- **Phase 2 M2-5 (統合テスト):** モデルを使用するテストは `test_c_api_integration.cpp` として分離。テストモデル (`test/models/multilingual-test-medium.onnx`) が存在しない場合は SKIP (`return 77`) にする。
- **C99 ヘッダーコンパイルテスト:** 可能であれば `test_c_api_header.c` (pure C ファイル) を追加して、ヘッダーが C99 でコンパイル可能なことを自動検証する。
