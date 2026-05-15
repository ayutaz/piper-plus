# C++ — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

## 1. 実装ファイル

| 用途 | パス |
|------|------|
| Phonemizer | `src/cpp/chinese_phonemize.cpp` (1,130 行) |
| ヘッダ | `src/cpp/chinese_phonemize.hpp` (公開関数 2 つ) |
| 辞書データ | `src/cpp/data/zh_en_loanword.json` |
| Multilingual | `src/cpp/language_detector.cpp` で言語セグメント分割、`piper.cpp:2589-2597` で dispatch |
| C API | `src/cpp/piper_plus.h` / `piper_plus_c_api.cpp` (中国語用 C API は **未エクスポート**) |
| テスト | `src/cpp/tests/test_multilingual_g2p.cpp` (中国語 2 ケースのみ — 拡充が必要) |

## 2. 現状調査

| 項目 | 状態 |
|------|------|
| pinyin → IPA | 完全実装、PUA 0xE020-0xE04A 使用 |
| データロード | `nlohmann/json` + `std::ifstream`、リソース埋め込みなし |
| ZH-EN dispatch | **❌ 未実装** |
| iOS/Android | xcframework / Android 用リソース同梱パターン要確認 |

**追加 LOC 見込み**: ~500 行 + iOS/Android リソース対応

**特殊な難所**:

1. C API export 追加 (`piper_plus_phonemize_embedded_english`)
2. iOS xcframework / Android のリソース同梱 (`PrivacyInfo.xcprivacy` 周辺)
3. テストフレーム自体の拡充 (現状 2 ケースしかない)
4. CMake への JSON データファイル追加 (`PiperPlusShared.cmake`)

## 3. iOS/Android リソース同梱戦略

**問題**: デスクトップ (Linux/macOS/Windows) は `std::ifstream` で実行時読込で OK だが、iOS xcframework / Android aar は別パターン。既存パターンの調査結果:

- 現状の G2P 辞書 (`cmudict_data.json` 3.7MB, `pinyin_single.json` 704KB 等) は **Linux/macOS/Windows のみ** `share/piper/dicts/` にインストール (`PiperPlusShared.cmake:263-273`)
- iOS/Android では `NOT PIPER_APPLE_EMBEDDED` 条件で **インストール対象外**
- C API (`piper_plus.h:PiperPlusConfig.dict_dir`) は **呼び出し側責任**でパス指定する設計

**3 案比較**:

| 案 | 手法 | バイナリサイズ | 起動時間 | メンテ性 |
|---|---|---|---|---|
| **A** | `xxd -i` で C 配列に変換、`.h` 化して static 埋め込み | +2KB (gzip 後) | 不要 | ★★★ |
| **B** | iOS bundle / Android assets 経由でファイル配信 | ほぼ 0 | +5-10ms | ★★ |
| **C** | shared lib にシンボル埋め込み (`incbin` 系) | +5KB | 不要 | ★ (iOS 非対応) |

**推奨**: **案 A (xxd 埋め込み)** — JSON サイズが小さい (5KB) ため埋め込みコスト低、既存パターンとの一貫性、ファイル I/O 不要、ABI 破壊なし

**実装スケッチ**:

```cmake
# src/cpp/CMakeLists.txt
if(PIPER_APPLE_EMBEDDED OR ANDROID)
    add_custom_command(
        OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/zh_en_loanword_data.h
        COMMAND xxd -i -n zh_en_loanword_json
                "${CMAKE_CURRENT_SOURCE_DIR}/data/zh_en_loanword.json"
                > "${CMAKE_CURRENT_BINARY_DIR}/zh_en_loanword_data.h"
        DEPENDS data/zh_en_loanword.json
    )
    target_sources(piper_plus PRIVATE
        ${CMAKE_CURRENT_BINARY_DIR}/zh_en_loanword_data.h)
    target_compile_definitions(piper_plus PRIVATE PIPER_PLUS_EMBEDDED_LOANWORD)
endif()
```

```cpp
// chinese_loanword.cpp
#ifdef PIPER_PLUS_EMBEDDED_LOANWORD
#include "zh_en_loanword_data.h"
LoanwordData loadDefaultLoanwordData() {
    return parseLoanwordJson(std::string(
        reinterpret_cast<const char*>(zh_en_loanword_json),
        zh_en_loanword_json_len
    ));
}
#else
LoanwordData loadDefaultLoanwordData(const std::string& jsonPath) {
    std::ifstream f(jsonPath);
    json j;
    f >> j;
    return parseLoanwordJson(j);
}
#endif
```

C API への影響: `PiperPlusConfig` 拡張不要 (デスクトップは従来通り `dict_dir` で指定、モバイルは埋め込みデータを使用)

## 4. Cross-Compile (xxd 代替)

**既存 build matrix** (`release-shared-lib.yml`):

| Platform | Architecture | Toolchain |
|----------|------------|-----------|
| Linux | x86_64 | GCC (`ubuntu-latest`) |
| macOS | aarch64 | Apple Clang (`macos-latest`) |
| Windows | x64 | MSVC (`windows-latest`) |
| Android | arm64-v8a, armeabi-v7a, x86_64 | NDK 26.1 |
| iOS | arm64 + simulator (x86_64/arm64) | `cmake/ios.toolchain.cmake` |

**xxd 互換性問題**:

- xxd は **GNU/Linux/macOS でデフォルト**、**Windows MSVC では非デフォルト**
- Windows CI runner では Git Bash / WSL 経由で利用可能だが、確実性に欠ける

**推奨代替案**: **CMake `file(READ HEX)` で MSVC 互換実装**

```cmake
# src/cpp/CMakeLists.txt
function(embed_json_as_header INPUT_JSON OUTPUT_HEADER VAR_NAME)
    file(READ "${INPUT_JSON}" hex_content HEX)
    # hex_content を 0x__ 形式の C 配列に変換
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," c_array "${hex_content}")
    file(WRITE "${OUTPUT_HEADER}"
        "// Auto-generated, do not edit\n"
        "#pragma once\n"
        "static const unsigned char ${VAR_NAME}[] = { ${c_array} };\n"
        "static const unsigned int ${VAR_NAME}_len = sizeof(${VAR_NAME});\n"
    )
endfunction()

if(PIPER_APPLE_EMBEDDED OR ANDROID)
    set(LOANWORD_HEADER ${CMAKE_CURRENT_BINARY_DIR}/zh_en_loanword_data.h)
    embed_json_as_header(
        ${CMAKE_CURRENT_SOURCE_DIR}/data/zh_en_loanword.json
        ${LOANWORD_HEADER}
        zh_en_loanword_json
    )
    target_sources(piper_plus PRIVATE ${LOANWORD_HEADER})
    target_compile_definitions(piper_plus PRIVATE PIPER_PLUS_EMBEDDED_LOANWORD)
endif()
```

**メリット**: xxd 依存なし、全 platform の CMake で動作 (3.10+)

**Platform 別配信戦略**:

| Platform | 戦略 | 実装 |
|----------|------|------|
| iOS xcframework | static embed | CMake `file(READ HEX)` → `.h` |
| Android .aar | static embed | 同上 |
| Linux/macOS/Windows | runtime load | `std::ifstream` (`share/piper/dicts/` 既存パターン) |

**ARM 系の注意点**:

| 項目 | 影響 |
|------|------|
| エンディアン | JSON はテキスト → **影響なし** |
| 32/64-bit サイズ差 | pointer 型のみ、struct layout 同一 |
| emulator vs native | ABI 一致なら動作同一、Android emulator は実機テスト必要 |

**CI matrix の追加**: **既存 matrix で全 platform カバー可能**、新規 job 不要

**Windows xxd 不要化の追加メリット**:

- Git Bash / WSL のセットアップステップ削減
- CI ステップ簡素化

## 5. Thread Safety

**既存実装の評価**:

| 既存箇所 | 状態 | 根拠 |
|---------|------|------|
| `english_phonemize.cpp:74-117` の static テーブル | Thread-safe | C++11 magic statics |
| `piper_plus_c_api.cpp:45` の `thread_local g_last_error` | Thread-safe | thread-local 保証 |
| `Voice` 構造体の dict (`pinyinSingleDict` 等) | 部分的 | 同一 engine を複数スレッドが共有する場合は要対策 |

**推奨パターン**: **immutable shared_ptr 共有** (mutex 不要)

```cpp
// chinese_loanword.hpp
struct LoanwordData {
    std::unordered_map<std::string, std::vector<std::string>> acronyms;
    std::unordered_map<std::string, std::vector<std::string>> loanwords;
    std::unordered_map<std::string, std::vector<std::string>> letter_fallback;
};

// 初期化は std::call_once で 1 度だけ
std::shared_ptr<const LoanwordData> getDefaultLoanwordData() {
    static std::shared_ptr<const LoanwordData> cached;
    static std::once_flag init_flag;
    std::call_once(init_flag, []() {
        cached = std::make_shared<const LoanwordData>(loadAndValidate());
    });
    return cached;
}

// phonemize 時は const 参照のみ → ロック不要
void phonemize_embedded_english(
    const std::string& text,
    std::vector<std::vector<Phoneme>>& out,
    const LoanwordData& data  // const 参照渡し
);
```

**設計判断**:

- **`std::shared_ptr<const T>`**: 読み取り専用なら mutex 不要、複数スレッドから安全に読める
- **`std::call_once`**: C++11 magic statics でも代替可能だが、loanword data の初期化は明示的に `call_once` で行う方が意図が明確
- **C API**: engine ポインタ単位で独立すれば自然に thread-safe (現状パターン継続)

**マルチスレッドテスト追加**:

```cpp
TEST(ZhEnLoanwordTest, ConcurrentAccess) {
    auto data = getDefaultLoanwordData();
    std::vector<std::thread> threads;
    for (int i = 0; i < 16; ++i) {
        threads.emplace_back([data]() {
            for (int j = 0; j < 1000; ++j) {
                std::vector<std::vector<Phoneme>> out;
                phonemize_embedded_english("GPS", out, *data);
            }
        });
    }
    for (auto& t : threads) t.join();
}
```

## 6. テストフレーム拡充戦略

**問題**: 中国語テストが現状 `test_multilingual_g2p.cpp` で 2 ケースしかない (`NiHao` / `SentenceWithPunctuation`)。設計書の統一テストマトリックス 20 ケースを追加する必要がある。

**既存テスト構造**:

- フレームワーク: **Google Test (gtest)**
- ファイル: `src/cpp/tests/test_multilingual_g2p.cpp` (31 テスト、`TEST_F` 形式)
- パラメータ化テスト (`TEST_P`/`INSTANTIATE_TEST_SUITE_P`) は **未使用**
- fixture: inline `makeTestXxxDict()` で十分、外部 JSON 不要
- CMake: `src/cpp/tests/CMakeLists.txt:607` で `add_test()` 登録、`gtest_discover_tests` 使用

**推奨拡充戦略**:

| 項目 | 推奨 | 理由 |
|------|-----|------|
| ファイル戦略 | **既存 `test_multilingual_g2p.cpp` に追記** (新規ファイル不要) | CMake 修正最小、既存 fixture 流用可 |
| クラス | 新規 `class ZhEnLoanwordTest : public ::testing::Test` | 中国語専用 fixture を持たせる |
| パターン | `TEST_F` で 20 ケース直書き、`TEST_P` 不使用 | ロジック差異が大きく、パラメータ化のメリット薄い |
| C API テスト | 別ファイル `test_c_api_zh_en.cpp` 推奨 | C ABI 経由のテストは責務分離 |
| fixture | inline `makeTestLoanwordData()` で配列リテラル | 外部 JSON 依存しない、自己完結 |

**テストコード例**:

```cpp
class ZhEnLoanwordTest : public ::testing::Test {
protected:
    LoanwordData loanwordData = makeTestLoanwordData();
    std::unordered_map<int, std::string> singleCharDict = makeTestSingleCharDict();
    std::unordered_map<std::string, std::string> phraseDict = makeTestPhraseDict();
};

TEST_F(ZhEnLoanwordTest, AcronymGPS_HitsAcronymTable) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_embedded_english("GPS", phonemes, loanwordData);
    ASSERT_FALSE(phonemes.empty());
    // tone marker (PUA 0xE046-0xE04A) が含まれることを検証
    bool hasTone = false;
    for (auto ph : phonemes[0]) {
        if (ph >= 0xE046 && ph <= 0xE04A) { hasTone = true; break; }
    }
    EXPECT_TRUE(hasTone);
}

TEST_F(ZhEnLoanwordTest, IssueExample_PleaseOpenGPS) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemize_chinese_mixed(
        "请打开 GPS",
        phonemes,
        singleCharDict, phraseDict, loanwordData
    );
    // GPS が 4 syllable 分の tone marker を持つことを検証
    int toneCount = countTones(phonemes);
    EXPECT_GE(toneCount, 4);
}
```

**工数見積**:

| 項目 | 工数 |
|------|------|
| 20 テストケース実装 | 2-3 時間 |
| CMake 修正 (不要、既存枠) | 10 分 |
| fixture data の C++ リテラル化 | 30 分 |
| C API テスト別ファイル | 1 時間 |
| **合計** | **4-5 時間** |

**CI 影響**: ビルド時間 +3-5 秒、CI 全体で +2-3 秒程度 (影響軽微)

## 7. メモリ管理

`std::shared_ptr<const LoanwordData>` を factory 関数で reference 増加。

## 8. エラーハンドリング

`PiperPlusStatus` enum + thread-local message:

```c
// piper_plus.h に追加
typedef enum PiperPlusStatus {
    PIPER_PLUS_OK = 0,
    /* 既存 */
    PIPER_PLUS_ERR_LOANWORD_SCHEMA = -7,  // schema violation
    PIPER_PLUS_ERR_LOANWORD_IO = -8,       // file missing/unreadable
} PiperPlusStatus;

PIPER_PLUS_API const char* piper_plus_get_last_error(void);
```

## 9. JSON parser 安全性

C++ `nlohmann/json` のデフォルト nest 制限は **無制限**。recursion 制限を明示的に設定する必要あり。

## 10. ベンチマーク

| フレーム | ファイル |
|--------|--------|
| Google Benchmark | `src/cpp/benchmarks/bench_chinese_embedded.cpp` |

## 11. カバレッジ

`gcov` + `lcov` で計測 (CI 新規追加が必要、Phase 3)。

## 12. API ドキュメント

C++ doxygen — 現状最小限、`/// @brief` / `@param` / `@return` テンプレで拡充。`doxygen` CI **未設定 → 新規追加検討**。
