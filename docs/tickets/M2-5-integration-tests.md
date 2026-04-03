# M2-5: 統合テスト (モデル必要)

> **Phase:** 2 --- ストリーミング + テスト
> **見積り:** 中
> **依存:** M2-4 (ストリーミング単体テスト)
> **ブロック:** M2-6
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m2-5-統合テスト-モデル必要)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Done

---

## 1. タスク目的とゴール

テストモデル (`test/models/multilingual-test-medium.onnx`) を使用して、C API の全合成パスが実際にオーディオを生成できることを検証する。M1-7 / M2-4 ではモデルなしのエラーパスのみテストしたが、本チケットでは create -> synthesize -> free のフルライフサイクルを通して音声品質のスモークテストまで行う。

**ゴール:**
- ワンショット合成: 音声サンプル数 > 0、サンプルレート確認
- Iterator: 全チャンクのサンプル数合計がワンショットと概ね一致 (10% 以内)
- コールバック: コールバック呼び出し回数 >= 1、user_data 転送確認
- クエリ API: sample_rate, num_speakers, num_languages, language_id
- 排他制御: Iterator 中の synthesize -> ERR_BUSY
- シンボル可視性: 内部シンボルの非公開確認

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/cpp/tests/test_c_api_integration.cpp` | 新規作成 |
| `src/cpp/tests/CMakeLists.txt` | テストターゲット追加 |

### 2.2 テストインフラ

#### モデルパス解決とスキップ制御

```cpp
#include <gtest/gtest.h>
#include <filesystem>
#include "piper_plus.h"

namespace fs = std::filesystem;

// Test model path - relative to project root
static const char* MODEL_PATH = nullptr;
static const char* CONFIG_PATH = nullptr;

class CApiIntegrationTest : public ::testing::Test {
protected:
    static void SetUpTestSuite() {
        // Search for test model in standard locations
        std::vector<std::string> searchPaths = {
            "test/models/multilingual-test-medium.onnx",
            "../test/models/multilingual-test-medium.onnx",
            "../../test/models/multilingual-test-medium.onnx",
        };

        for (const auto& path : searchPaths) {
            if (fs::exists(path)) {
                static std::string modelPath = path;
                static std::string configPath = path + ".json";
                MODEL_PATH = modelPath.c_str();
                CONFIG_PATH = configPath.c_str();
                break;
            }
        }
    }

    void SetUp() override {
        if (!MODEL_PATH) {
            GTEST_SKIP() << "Test model not found; skipping integration test";
        }
    }

    PiperPlusEngine* createEngine() {
        PiperPlusConfig config = {};
        config.model_path = MODEL_PATH;
        config.config_path = CONFIG_PATH;
        config.provider = "cpu";
        config.num_threads = 1;
        config.gpu_device_id = 0;
        return piper_plus_create(&config);
    }
};
```

### 2.3 テストケース一覧

#### グループ 1: ワンショット合成

```cpp
TEST_F(CApiIntegrationTest, OneShotSynthesisProducesAudio) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr) << piper_plus_get_last_error();

    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;

    PiperPlusSynthOptions opts = piper_plus_default_options();

    int32_t rc = piper_plus_synthesize(
        engine, "Hello world.", &opts,
        &samples, &num_samples, &sample_rate);

    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_NE(samples, nullptr);
    EXPECT_GT(num_samples, 0);
    EXPECT_GT(sample_rate, 0);

    // Samples should be in [-1.0, 1.0] range
    bool allInRange = true;
    for (int32_t i = 0; i < num_samples && i < 1000; i++) {
        if (samples[i] < -1.0f || samples[i] > 1.0f) {
            allInRange = false;
            break;
        }
    }
    EXPECT_TRUE(allInRange) << "Audio samples out of [-1.0, 1.0] range";

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, OneShotJapaneseText) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;

    PiperPlusSynthOptions opts = piper_plus_default_options();

    int32_t rc = piper_plus_synthesize(
        engine, u8"こんにちは、今日は良い天気ですね。", &opts,
        &samples, &num_samples, &sample_rate);

    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(num_samples, 0);

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}
```

#### グループ 2: Iterator パターン

```cpp
TEST_F(CApiIntegrationTest, IteratorProducesChunks) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusSynthOptions opts = piper_plus_default_options();

    // Multi-sentence text to ensure multiple chunks
    const char* text = "First sentence. Second sentence. Third sentence.";

    int32_t rc = piper_plus_synth_start(engine, text, &opts);
    EXPECT_EQ(rc, PIPER_PLUS_OK);

    int chunkCount = 0;
    int32_t totalSamples = 0;
    int32_t lastSampleRate = 0;

    while (true) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);

        if (rc == PIPER_PLUS_ERR) {
            FAIL() << "synth_next returned error: " << piper_plus_get_last_error();
        }

        if (chunk.num_samples > 0) {
            chunkCount++;
            totalSamples += chunk.num_samples;
            lastSampleRate = chunk.sample_rate;
        }

        if (rc == PIPER_PLUS_DONE) {
            EXPECT_EQ(chunk.is_last, 1);
            break;
        }
    }

    EXPECT_GE(chunkCount, 1) << "Expected at least 1 audio chunk";
    EXPECT_GT(totalSamples, 0) << "Expected audio output";
    EXPECT_GT(lastSampleRate, 0);

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorTotalSamplesMatchOneShot) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    const char* text = "Hello world.";
    PiperPlusSynthOptions opts = piper_plus_default_options();

    // One-shot synthesis
    float* oneShotSamples = nullptr;
    int32_t oneShotCount = 0;
    int32_t oneShotRate = 0;

    int32_t rc = piper_plus_synthesize(
        engine, text, &opts,
        &oneShotSamples, &oneShotCount, &oneShotRate);
    ASSERT_EQ(rc, PIPER_PLUS_OK);
    ASSERT_GT(oneShotCount, 0);

    piper_plus_free_audio(oneShotSamples);

    // Iterator synthesis of same text
    rc = piper_plus_synth_start(engine, text, &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK);

    int32_t iteratorTotal = 0;
    while (true) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        iteratorTotal += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Iterator and one-shot should produce roughly the same amount of audio.
    // Allow 10% difference due to sentence splitting granularity.
    double ratio = static_cast<double>(iteratorTotal) / oneShotCount;
    EXPECT_GT(ratio, 0.9) << "Iterator produced significantly fewer samples";
    EXPECT_LT(ratio, 1.1) << "Iterator produced significantly more samples";

    piper_plus_free(engine);
}
```

#### グループ 3: コールバック合成

```cpp
struct CallbackData {
    int callCount = 0;
    int32_t totalSamples = 0;
    int32_t sampleRate = 0;
};

static void testCallback(const float* samples, int32_t num_samples,
                          int32_t sample_rate, void* user_data) {
    auto* data = static_cast<CallbackData*>(user_data);
    data->callCount++;
    data->totalSamples += num_samples;
    data->sampleRate = sample_rate;
}

TEST_F(CApiIntegrationTest, StreamingCallbackInvoked) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusSynthOptions opts = piper_plus_default_options();
    CallbackData cbData;

    int32_t rc = piper_plus_synthesize_streaming(
        engine, "Hello world.", &opts,
        testCallback, &cbData);

    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GE(cbData.callCount, 1) << "Callback should be invoked at least once";
    EXPECT_GT(cbData.totalSamples, 0) << "Expected audio samples in callback";
    EXPECT_GT(cbData.sampleRate, 0);

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, StreamingUserDataPassthrough) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusSynthOptions opts = piper_plus_default_options();

    // Use a specific magic number to verify user_data passthrough
    int32_t magicValue = 0;
    auto callback = [](const float*, int32_t, int32_t, void* user_data) {
        auto* val = static_cast<int32_t*>(user_data);
        *val = 42;
    };

    int32_t rc = piper_plus_synthesize_streaming(
        engine, "Hello.", &opts,
        reinterpret_cast<PiperPlusAudioCallback>(+callback),
        &magicValue);

    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_EQ(magicValue, 42) << "user_data should be passed through to callback";

    piper_plus_free(engine);
}
```

#### グループ 4: クエリ API

```cpp
TEST_F(CApiIntegrationTest, QuerySampleRate) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    int32_t sr = piper_plus_sample_rate(engine);
    EXPECT_GT(sr, 0);
    // Common sample rates: 16000, 22050, 44100
    EXPECT_TRUE(sr == 16000 || sr == 22050 || sr == 44100 || sr == 48000)
        << "Unexpected sample rate: " << sr;

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, QueryNumSpeakers) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    int32_t ns = piper_plus_num_speakers(engine);
    EXPECT_GE(ns, 0);  // 0 for single-speaker, >0 for multi-speaker

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, QueryNumLanguages) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    int32_t nl = piper_plus_num_languages(engine);
    EXPECT_GE(nl, 1);  // At least 1 language

    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, LanguageIdLookup) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    // Test model is multilingual-test-medium, which should have "ja"
    int32_t jaId = piper_plus_language_id(engine, "ja");
    EXPECT_GE(jaId, 0) << "Japanese should be a valid language in test model";

    // Non-existent language should return -1
    int32_t xxId = piper_plus_language_id(engine, "xx");
    EXPECT_EQ(xxId, -1) << "Non-existent language should return -1";

    piper_plus_free(engine);
}
```

#### グループ 5: 排他制御

```cpp
TEST_F(CApiIntegrationTest, BusyDuringIterator) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusSynthOptions opts = piper_plus_default_options();

    // Start iterator
    int32_t rc = piper_plus_synth_start(engine, "Hello world.", &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK);

    // Try one-shot while iterator active -> should be BUSY
    float* samples = nullptr;
    int32_t num_samples = 0;
    int32_t sample_rate = 0;
    rc = piper_plus_synthesize(engine, "Another text.", &opts,
                                &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_BUSY);
    EXPECT_EQ(samples, nullptr);

    // Try streaming while iterator active -> should be BUSY
    CallbackData cbData;
    rc = piper_plus_synthesize_streaming(
        engine, "Third text.", &opts, testCallback, &cbData);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_BUSY);

    // Try another synth_start while iterator active -> should be BUSY
    rc = piper_plus_synth_start(engine, "Fourth text.", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_ERR_BUSY);

    // Drain iterator to completion
    while (true) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // After iterator completes, one-shot should work again
    rc = piper_plus_synthesize(engine, "Hello again.", &opts,
                                &samples, &num_samples, &sample_rate);
    EXPECT_EQ(rc, PIPER_PLUS_OK);
    EXPECT_GT(num_samples, 0);

    piper_plus_free_audio(samples);
    piper_plus_free(engine);
}

TEST_F(CApiIntegrationTest, IteratorReuse) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    PiperPlusSynthOptions opts = piper_plus_default_options();

    // First iteration
    int32_t rc = piper_plus_synth_start(engine, "First.", &opts);
    ASSERT_EQ(rc, PIPER_PLUS_OK);

    while (true) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    // Second iteration on same engine
    rc = piper_plus_synth_start(engine, "Second.", &opts);
    EXPECT_EQ(rc, PIPER_PLUS_OK);

    int32_t totalSamples = 0;
    while (true) {
        PiperPlusAudioChunk chunk = {};
        rc = piper_plus_synth_next(engine, &chunk);
        totalSamples += chunk.num_samples;
        if (rc == PIPER_PLUS_DONE) break;
        ASSERT_NE(rc, PIPER_PLUS_ERR);
    }

    EXPECT_GT(totalSamples, 0);

    piper_plus_free(engine);
}
```

#### グループ 6: speaker_id / language 変更

```cpp
TEST_F(CApiIntegrationTest, SpeakerIdChange) {
    PiperPlusEngine* engine = createEngine();
    ASSERT_NE(engine, nullptr);

    int32_t numSpeakers = piper_plus_num_speakers(engine);
    if (numSpeakers < 2) {
        GTEST_SKIP() << "Test model has fewer than 2 speakers";
    }

    PiperPlusSynthOptions opts0 = piper_plus_default_options();
    opts0.speaker_id = 0;

    PiperPlusSynthOptions opts1 = piper_plus_default_options();
    opts1.speaker_id = 1;

    float *samples0 = nullptr, *samples1 = nullptr;
    int32_t count0 = 0, count1 = 0;
    int32_t rate0 = 0, rate1 = 0;

    piper_plus_synthesize(engine, "Hello.", &opts0, &samples0, &count0, &rate0);
    piper_plus_synthesize(engine, "Hello.", &opts1, &samples1, &count1, &rate1);

    ASSERT_GT(count0, 0);
    ASSERT_GT(count1, 0);

    // Different speakers should produce different audio
    // Compare a subset of samples (they won't be identical)
    bool anyDifference = false;
    int32_t compareLen = std::min({count0, count1, (int32_t)100});
    for (int32_t i = 0; i < compareLen; i++) {
        if (std::abs(samples0[i] - samples1[i]) > 1e-6f) {
            anyDifference = true;
            break;
        }
    }
    EXPECT_TRUE(anyDifference)
        << "Different speaker IDs should produce different audio";

    piper_plus_free_audio(samples0);
    piper_plus_free_audio(samples1);
    piper_plus_free(engine);
}
```

#### グループ 7: シンボル可視性 (Linux/macOS のみ)

```cpp
#if !defined(_WIN32)
TEST_F(CApiIntegrationTest, SymbolVisibility) {
    // This test verifies that the shared library only exports piper_plus_* symbols.
    // Implementation: run nm/otool on the built library and check output.
    //
    // This is more of a build verification than a runtime test, so it's
    // implemented as a shell command check. In CI, this is also verified
    // by the CI step (M2-6).
    //
    // The test itself just verifies the library file exists.
    std::vector<std::string> libPaths = {
        "libpiper_plus.so",
        "../lib/libpiper_plus.so",
        "libpiper_plus.dylib",
        "../lib/libpiper_plus.dylib",
    };

    bool found = false;
    for (const auto& path : libPaths) {
        if (fs::exists(path)) {
            found = true;
            break;
        }
    }

    if (!found) {
        GTEST_SKIP() << "Shared library not found in expected locations";
    }

    // If library exists, this test passes.
    // Actual symbol checking is done in CI via nm/otool commands (M2-6).
    SUCCEED();
}
#endif
```

### 2.4 CMakeLists.txt への統合

```cmake
# src/cpp/tests/CMakeLists.txt に追加

add_executable(test_c_api_integration test_c_api_integration.cpp)
target_link_libraries(test_c_api_integration PRIVATE
    piper_plus   # 共有ライブラリにリンク
    GTest::gtest_main
)
target_include_directories(test_c_api_integration PRIVATE
    ${CMAKE_SOURCE_DIR}/src/cpp  # piper_plus.h
)

add_test(NAME test_c_api_integration COMMAND test_c_api_integration)

# Set working directory to project root for model path resolution
set_tests_properties(test_c_api_integration PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
)
```

### 2.5 テストモデルの要件

| 項目 | 値 |
|------|-----|
| モデルパス | `test/models/multilingual-test-medium.onnx` |
| config パス | `test/models/multilingual-test-medium.onnx.json` |
| 言語数 | >= 2 (ja, en 含む) |
| 話者数 | >= 1 (マルチスピーカー推奨) |
| モデル不在時 | 全テスト `GTEST_SKIP()` |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テスト実装者 | 1 | test_c_api_integration.cpp 新規作成 (~350 行) + CMakeLists.txt 更新 |
| レビュアー | 1 | テストカバレッジの網羅性、モデル依存テストの SKIP 条件確認 |

---

## 4. 提供範囲とテスト項目

### 4.1 テストケース一覧

| カテゴリ | テスト数 | モデル必要 | 内容 |
|---------|---------|----------|------|
| ワンショット合成 | 2 | Yes | 英語/日本語テキスト -> 音声出力確認 |
| Iterator パターン | 2 | Yes | チャンク生成 + ワンショットとのサンプル数比較 |
| コールバック合成 | 2 | Yes | コールバック呼び出し + user_data 転送 |
| クエリ API | 4 | Yes | sample_rate, num_speakers, num_languages, language_id |
| 排他制御 | 2 | Yes | BUSY チェック + Iterator 再利用 |
| speaker_id 変更 | 1 | Yes | 異なる話者で異なる音声 |
| シンボル可視性 | 1 | Partial | ライブラリファイル存在確認 (nm はCI で) |
| **合計** | **14** | | |

### 4.2 受け入れ基準

- テストモデル存在時: 全 14 テストが PASS
- テストモデル非存在時: 全テスト SKIP (CI ではモデルをキャッシュ)
- 3 プラットフォームで CI GREEN
- テスト実行時間: 30 秒以内 (モデルロード 1 回、合成は短文のみ)

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| 懸念 | リスク | 対策 |
|------|--------|------|
| テストモデルのサイズ (git 管理) | 中 | ONNX モデルは `test/models/` に配置。`.gitignore` で除外し、CI ではキャッシュから取得。ローカルでは手動コピー |
| テストモデルの辞書依存 | 中 | `dict_dir` を `PiperPlusConfig` で明示指定し、CI 環境でも辞書が見つかるようにする |
| `IteratorTotalSamplesMatchOneShot` の 10% 許容が厳しすぎる可能性 | 低 | 短文 ("Hello world.") は文分割されず 1 文のため、差異は最小。長文では文分割の境界効果で差が出る可能性があるが、10% は十分な余裕 |
| `SpeakerIdChange` テストが単一話者モデルでスキップ | 低 | テストモデルがマルチスピーカーでない場合は `GTEST_SKIP` で対応 |
| ラムダの関数ポインタキャスト (`+callback`) | 低 | stateless ラムダのみ。`user_data` 経由で状態を管理 |

### 5.2 レビュー項目

- [ ] 全テストがモデル非存在時に `GTEST_SKIP()` すること (FAIL ではない)
- [ ] `createEngine()` が辞書パスを正しく設定していること
- [ ] `piper_plus_free_audio()` が全テストで正しく呼ばれていること (メモリリークなし)
- [ ] `piper_plus_free()` が全テストの最後に呼ばれていること
- [ ] 排他制御テストで Iterator が最後まで drain されていること (inProgress リーク防止)
- [ ] UTF-8 日本語テキストがコンパイラに正しく処理されること (u8 プレフィックス)

---

## 6. 一から作り直すとしたら

**1. テストフィクスチャの再設計:**
現在の `SetUpTestSuite` でモデルパスを 1 回検索する方式は合理的だが、エンジンの作成/破棄が各テストで繰り返される。テストモデルのロードに 2-3 秒かかる場合、テストスイート全体で 30 秒以上になりうる。

改善案: `static PiperPlusEngine*` を `SetUpTestSuite()` で 1 回だけ作成し、全テストで共有する。ただし、排他制御テストでは Iterator の状態がテスト間でリークしないよう注意が必要。

```cpp
class CApiIntegrationTest : public ::testing::Test {
    static PiperPlusEngine* sharedEngine;
    static void SetUpTestSuite() {
        // Create engine once
        sharedEngine = createEngine();
    }
    static void TearDownTestSuite() {
        piper_plus_free(sharedEngine);
    }
};
```

排他制御テストなど状態を変更するテストは別のフィクスチャクラスで独自のエンジンを使用する。

**2. ゴールデンオーディオ比較:**
現在のテストは「サンプル数 > 0」「範囲 [-1, 1]」のスモークテストのみ。将来的にはゴールデンオーディオ (事前生成した参照音声) との比較テストを追加し、合成結果の回帰を検出できるようにする。ただし、ONNX Runtime のバージョンやプラットフォーム差でビット一致は期待できないため、PESQ/STOI 等の音声品質メトリクスを使う必要がある。Phase 4 の候補。

---

## 7. 後続タスクへの連絡事項

### M2-6 (CI 統合) への申し送り

- **テストモデルのキャッシュ:** `test/models/multilingual-test-medium.onnx` を CI アーティファクトまたは cache としてダウンロード/保存するステップが必要。HuggingFace (`ayousanz/piper-plus-base`) から取得するか、GitHub Release アセットから取得する方式を検討。
- **辞書のキャッシュ:** テストモデルが日本語を含む場合、OpenJTalk 辞書が必要。`dict_dir` を CI 環境で正しく設定するか、テスト時に辞書を自動ダウンロードする仕組みが必要。
- **テスト実行コマンド:**
  ```bash
  ctest -R "^test_c_api_integration$" --output-on-failure -V --timeout 120
  ```
- **シンボル可視性テスト (CI 側):**
  ```bash
  # Linux
  nm -D libpiper_plus.so | grep ' T ' | grep -v '^piper_plus_' && exit 1 || true
  # macOS
  nm -gU libpiper_plus.dylib | grep -v '^_piper_plus_' | grep ' T ' && exit 1 || true
  # Windows
  dumpbin /EXPORTS piper_plus.dll | findstr /V "piper_plus_" | findstr "    " && exit 1 || true
  ```
  このシェルコマンドベースの検証は CI ステップで直接実行する (テストコード内ではなく)。

### Phase 3 への申し送り

- 統合テストが安定稼働していれば、Phase 3 の配布テスト (install 先からの動的リンク + 合成テスト) の基盤として再利用可能。
- `test_c_api_integration.cpp` を `examples/c-api/basic.c` のベースとしても活用できる。
