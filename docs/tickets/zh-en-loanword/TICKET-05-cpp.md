# TICKET-05: C++ ZH-EN Code-Switching 実装

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-05 |
| **マイルストーン** | Phase 5 (Day 10-12) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §2.5 / §4.1 P1-P6 / §8.1 (iOS/Android リソース) / §8.6 (テスト拡充) / §8.14 (thread safety) / §8.23 (cross-compile) |
| **ステータス** | 📝 Draft |
| **依存元** | なし (TICKET-01〜04 と並列可) |
| **依存先** | TICKET-06 (CI Sync), TICKET-07 (Docs) |
| **追加 LOC** | ~810 (実装 ~580 + テスト ~200 + CMake ~30) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: C++ ランタイム (`src/cpp/`) に ZH-EN code-switching を実装。デスクトップ (Linux/macOS/Windows) では JSON ファイル経由、iOS xcframework / Android aar では **CMake `file(READ HEX)` による static 埋め込み**で配信。Python 実装と byte-for-byte 一致する出力を返す。

**ゴール**:
- `phonemizeEmbeddedEnglish(text, out, data)` C++ 関数が動作。
- `phonemizeChineseMixed(text, out, dicts, data)` で `[zh, en, *]` パターン dispatch。
- C API `piper_plus_phonemizeEmbeddedEnglish()` を export (Dart / Godot / Unity 利用者向け)。
- iOS xcframework / Android .aar に JSON が **同梱される** (xxd 不要、CMake 純正)。
- Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件が Python と byte 一致。
- マルチスレッド読込で race / data corruption ゼロ (`std::shared_ptr<const>` + `std::call_once`)。
- iOS / Android / Linux / macOS / Windows 全 platform の CI build green。
- 既存テスト (~31 件) にリグレッションなし。

---

## 2. 実装する内容の詳細

### P1. `chinese_loanword.hpp/cpp` 新規

```
src/cpp/
├── chinese_loanword.hpp                  (新規 ~50 LOC)
├── chinese_loanword.cpp                  (新規 ~250 LOC)
├── data/
│   └── zh_en_loanword.json               (新規、Python source からコピー)
└── tests/
    ├── test_zh_en_loanword.cpp           (新規 ~150 LOC, gtest)
    └── test_c_api_zh_en.cpp              (新規 ~50 LOC, gtest)
```

**header (`chinese_loanword.hpp`)**:

```cpp
#pragma once
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

namespace piper {

struct LoanwordData {
    int version = 0;
    std::unordered_map<std::string, std::vector<std::string>> acronyms;
    std::unordered_map<std::string, std::vector<std::string>> loanwords;
    std::unordered_map<std::string, std::vector<std::string>> letter_fallback;
};

// Singleton, thread-safe, immutable
std::shared_ptr<const LoanwordData> getDefaultLoanwordData();
std::shared_ptr<const LoanwordData> loadLoanwordDataFromPath(const std::string& path);
void validateLoanwordData(const LoanwordData& data);  // throws std::invalid_argument

// メイン関数
void phonemizeEmbeddedEnglish(
    const std::string& text,
    std::vector<std::vector<Phoneme>>& out,
    const LoanwordData& data
);

}  // namespace piper_plus
```

**implementation (`chinese_loanword.cpp`)** の主要箇所:

```cpp
namespace piper {

#ifdef PIPER_PLUS_EMBEDDED_LOANWORD
#include "zh_en_loanword_data.h"  // CMake が生成
static const std::string loadEmbeddedJson() {
    return std::string(
        reinterpret_cast<const char*>(zh_en_loanword_json),
        zh_en_loanword_json_len);
}
#endif

std::shared_ptr<const LoanwordData> getDefaultLoanwordData() {
    static std::shared_ptr<const LoanwordData> cached;
    static std::once_flag init_flag;
    std::call_once(init_flag, []() {
        LoanwordData data;
#ifdef PIPER_PLUS_EMBEDDED_LOANWORD
        data = parseLoanwordJson(loadEmbeddedJson());
#else
        // デスクトップ: dict_dir/zh_en_loanword.json を読む
        data = loadLoanwordDataFromPath_internal(
            getDefaultDictPath() + "/zh_en_loanword.json");
#endif
        validateLoanwordData(data);
        cached = std::make_shared<const LoanwordData>(std::move(data));
    });
    return cached;
}
```

### P2. `phonemizeEmbeddedEnglish()` C++ 実装 (~150 LOC)

Lookup priority (Python と一致):

```cpp
void phonemizeEmbeddedEnglish(
    const std::string& text,
    std::vector<std::vector<Phoneme>>& out,
    const LoanwordData& data)
{
    auto words = tokenizeEnglishWords(text);
    for (const auto& raw : words) {
        std::string stripped = stripTrailingPunctuation(raw);
        const std::vector<std::string>* syllables = nullptr;

        // 1. case-sensitive loanwords
        auto it = data.loanwords.find(stripped);
        if (it != data.loanwords.end()) syllables = &it->second;

        // 2. uppercase acronyms
        if (!syllables) {
            std::string upper = toUpperAscii(stripped);
            auto it2 = data.acronyms.find(upper);
            if (it2 != data.acronyms.end()) syllables = &it2->second;
        }

        // 3. letter_fallback (char-by-char, digits drop)
        if (!syllables) {
            for (char ch : stripped) {
                if (std::isdigit(static_cast<unsigned char>(ch))) continue;
                std::string key(1, std::toupper(static_cast<unsigned char>(ch)));
                auto it3 = data.letter_fallback.find(key);
                if (it3 != data.letter_fallback.end()) {
                    appendPinyinToIpa(it3->second, out);
                }
            }
            continue;
        }

        // syllables を pinyin → IPA 変換
        for (const auto& syl : *syllables) {
            auto split = splitPinyin(syl);
            auto ipa = pinyinToIpa(split);  // 既存関数 (chinese_phonemize.cpp:670 周辺)
            out.emplace_back(std::move(ipa));
        }
    }
}
```

### P3. `piper.cpp` dispatch 拡張 (~50 LOC)

`piper.cpp:2589-2597` 周辺の既存 multilingual dispatch に追加:

```cpp
for (size_t i = 0; i < segments.size(); ++i) {
    const auto& seg = segments[i];
    if (seg.lang == "en" && hasZh) {
        bool prevIsZh = i > 0 && segments[i-1].lang == "zh";
        bool nextIsZh = i+1 < segments.size() && segments[i+1].lang == "zh";
        if (prevIsZh || nextIsZh) {
            std::vector<std::vector<Phoneme>> embedded_phonemes;
            phonemizeEmbeddedEnglish(seg.text, embedded_phonemes, *loanwordData);
            out.insert(out.end(), embedded_phonemes.begin(), embedded_phonemes.end());
            continue;
        }
    }
    // 既存の英語経路
    phonemizeEnglish(seg.text, out, ...);
}
```

### P4. C API export 追加

`piper_plus.h` / `piper_plus_c_api.cpp`:

```c
// piper_plus.h
typedef struct PiperLoanwordHandle PiperLoanwordHandle;

PIPER_PLUS_EXPORT PiperLoanwordHandle* piper_plus_loanword_load_default(void);
PIPER_PLUS_EXPORT PiperLoanwordHandle* piper_plus_loanword_load_from_path(const char* path);
PIPER_PLUS_EXPORT void piper_plus_loanword_free(PiperLoanwordHandle* handle);

PIPER_PLUS_EXPORT int piper_plus_phonemizeEmbeddedEnglish(
    const char* text,
    const PiperLoanwordHandle* loanword,
    char* out_buffer,
    size_t out_buffer_size,
    size_t* out_actual_size
);
```

エラーは `g_last_error` thread_local string で取得 (`piper_plus_get_last_error()` 既存)。

### P5. iOS/Android リソース同梱

**設計書 §8.1 + §8.23** に従い、**xxd ではなく CMake `file(READ HEX)`** を採用 (Windows MSVC でも動作):

```cmake
# src/cpp/CMakeLists.txt

function(embed_json_as_header INPUT_JSON OUTPUT_HEADER VAR_NAME)
    file(READ "${INPUT_JSON}" hex_content HEX)
    string(REGEX REPLACE "([0-9a-f][0-9a-f])" "0x\\1," c_array "${hex_content}")
    # 末尾のコンマ削除
    string(REGEX REPLACE ",$" "" c_array "${c_array}")
    file(WRITE "${OUTPUT_HEADER}"
        "// Auto-generated by CMake. Do not edit.\n"
        "#pragma once\n"
        "#include <cstddef>\n"
        "static const unsigned char ${VAR_NAME}[] = { ${c_array} };\n"
        "static const std::size_t ${VAR_NAME}_len = sizeof(${VAR_NAME});\n"
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
else()
    # デスクトップ: PiperPlusShared.cmake の install rule で share/piper/dicts/ にコピー
    install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/data/zh_en_loanword.json
            DESTINATION share/piper/dicts)
endif()
```

### P6. テスト追加 (~200 LOC)

設計書 §8.6 に従い `test_multilingual_g2p.cpp` に追記、専用 `class ZhEnLoanwordTest` を導入。

#### Unit テスト (`test_zh_en_loanword.cpp`、gtest `TEST_F`)

| テスト | 内容 |
|------|------|
| `AcronymGPS_HitsAcronymTable` | `GPS` → tone marker 含む |
| `LoanwordPython_CaseSensitive` | `Python` ≠ `PYTHON` |
| `ChatGPT_FiveSyllables` | 5 syllable |
| `LetterFallback_ZZ` | 2 回 |
| `Empty_ReturnsEmpty` | edge |
| `LookupPriority_LoanwordBeatsAcronym` | override |
| `LookupPriority_AcronymBeatsFallback` | override |
| `Punctuation_TrailingComma` | `GPS,` 等価 |
| `Digits_Z2Z9_EqualsZZ` | digit drop |
| `AcronymWithDigits_MP3` | `MP3` 直接 |
| `MultiSegment_TwoEmbeddedEn` | `ChatGPT 和 Python` |
| `LoadDefault_NotNull` | embedded vs file 経路両方 |
| `LoadFromPath_FileNotFound_Throws` | 欠損 path |
| `Validate_InvalidSchema_Throws` | bad schema |
| `LoadDefault_OnceOnly_SameInstance` | `std::call_once` で同一 instance |
| `IssueExample_PleaseOpenGps` | Issue 例 1 |
| `IssueExample_IUsePython` | Issue 例 2 |
| `IssueExample_LetMeUseChatGpt` | Issue 例 3 |
| `JsonMatchesPythonSource` | byte 比較 (file 経路時のみ実行) |
| `Multilingual_ZhEnZh_Pattern` | `请打开 GPS 系统` |
| `Multilingual_PureZh_Unaffected` | regression |
| `Multilingual_PureEn_Unaffected` | regression |

#### Multi-thread テスト (設計書 §8.14)

```cpp
TEST(ZhEnLoanwordTest, ConcurrentAccess) {
    auto data = getDefaultLoanwordData();
    std::vector<std::thread> threads;
    for (int i = 0; i < 16; ++i) {
        threads.emplace_back([data]() {
            for (int j = 0; j < 1000; ++j) {
                std::vector<std::vector<Phoneme>> out;
                phonemizeEmbeddedEnglish("GPS", out, *data);
            }
        });
    }
    for (auto& t : threads) t.join();
    SUCCEED();  // race condition があれば AddressSanitizer / ThreadSanitizer で検出
}
```

#### C API テスト (`test_c_api_zh_en.cpp`)

| テスト | 内容 |
|------|------|
| `CApi_LoadDefault_ReturnsHandle` | `piper_plus_loanword_load_default` |
| `CApi_LoadFromPath_FileNotFound_NullReturn` | 欠損で null + `get_last_error` 確認 |
| `CApi_PhonemizeEmbeddedEnglish_GPS` | 出力 buffer サイズ確認 |
| `CApi_BufferTooSmall_ReturnsRequiredSize` | partial fill + true size |

合計 **27 テスト**。設計書 §8.6 で設定した「現状 2 ケース → 27 ケース」目標に到達。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | 全体統括、5 platform CI 確認、TICKET-06 への引き継ぎ |
| **C++ Dev #1** | 1 | P1-P3 実装 (loanword.hpp/cpp、`phonemize_embedded_english`、dispatch) |
| **C++ Dev #2** | 1 | P4 C API export、P6 ユニットテスト + マルチスレッドテスト |
| **Mobile Engineer** | 1 | P5 CMake `embed_json_as_header` 関数、iOS xcframework / Android .aar ビルド検証 |
| **QA / Test** | 1 | P6 全テスト、cross-platform CI (Linux / macOS / Windows / iOS / Android) green 確認 |

**並列化**: P1+P2+P3 は逐次、P4 と P5 は並列、P6 は P1-P5 完了後。

**コミット推奨**:
- `feat(cpp): P1+P2 chinese_loanword.hpp/cpp と phonemize_embedded_english 実装`
- `feat(cpp): P3 piper.cpp に [zh,en,*] dispatch 追加`
- `feat(cpp): P4 C API export piper_plus_phonemize_embedded_english`
- `feat(cpp): P5 CMake embed_json_as_header (iOS/Android xxd 不要)`
- `test(cpp): P6 ZH-EN テスト追加 (27 件 + multi-thread)`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- C++ namespace `piper_plus` の公開 API
- C API export 4 関数 (load_default / load_from_path / free / phonemize_embedded_english)
- iOS xcframework / Android .aar 同梱 JSON
- 5 platform (Linux / macOS / Windows / iOS / Android) cross-compile 対応

### Out of scope

- Dart / Godot / Unity bindings の更新 (利用側 PR)
- iOS Swift Package 公開 (TICKET-07)
- Android Maven Central 公開 (TICKET-07)

### テスト項目

合計 27 テスト + マルチスレッド 1 件。設計書 §8.24 のカバレッジ目標 (line 90% / branch 90% / error 100%) を達成。

---

## 5. Unit テスト

セクション 2 P6 の表 27 件。`test_zh_en_loanword.cpp` で `class ZhEnLoanwordTest : public ::testing::Test` を fixture とし、`makeTestLoanwordData()` で inline test data を生成。`tests/fixtures/g2p/zh_en_loanword_matrix.json` (TICKET-06 で導入) を `nlohmann/json` で読み込み、ループ式テストも併用。

```cpp
class ZhEnLoanwordTest : public ::testing::Test {
protected:
    LoanwordData loanwordData = makeTestLoanwordData();
    std::unordered_map<int, std::string> singleCharDict = makeTestSingleCharDict();
    std::unordered_map<std::string, std::string> phraseDict = makeTestPhraseDict();
};

TEST_F(ZhEnLoanwordTest, AcronymGPS_HitsAcronymTable) {
    std::vector<std::vector<Phoneme>> phonemes;
    phonemizeEmbeddedEnglish("GPS", phonemes, loanwordData);
    ASSERT_FALSE(phonemes.empty());
    bool hasTone = false;
    for (const auto& v : phonemes)
        for (auto ph : v)
            if (ph >= 0xE046 && ph <= 0xE04A) { hasTone = true; break; }
    EXPECT_TRUE(hasTone);
}
```

---

## 6. E2E テスト

### Cross-platform build verification

| Platform | Toolchain | 検証内容 |
|----------|----------|---------|
| Linux x86_64 | GCC | `cmake --build` + ctest 全件 |
| macOS arm64 | Apple Clang | 同上 |
| Windows x64 | MSVC | `cmake --build` + ctest (xxd 不要パスで動作確認) |
| Android arm64-v8a | NDK 26.1 | xcframework 風 .aar build、JSON 同梱確認 |
| Android armeabi-v7a | NDK 26.1 | 同上 |
| Android x86_64 | NDK 26.1 | 同上 |
| iOS arm64 | `cmake/ios.toolchain.cmake` | xcframework build、JSON 同梱確認 |
| iOS simulator (x86_64/arm64) | 同上 | 同上 |

### Issue 例 byte 一致

`piper-cli` (C++) で `请打开 GPS` → phoneme dump → Python と diff ゼロ。

### iOS xcframework 確認 (3 層)

**注意**: stripped release `.a` には symbol が残らない (visibility=hidden + strip)。`strings` も `file(READ HEX)` 由来の生 byte 列にはヒットしない。**3 層で検証**する:

#### Layer 1: CMake build-time print

`embed_json_as_header` 関数末尾で `message(STATUS "Embedded ${VAR_NAME}: ${json_size} bytes")` を出力。CI で `grep "Embedded zh_en_loanword_json: 5012 bytes" build.log` 確認。

#### Layer 2: Symbol 検証 (visibility=default の internal build)

PR triggered CI で `-DPIPER_PLUS_DEBUG_SYMBOLS=ON` を一時有効化、stripped 前 archive を検証:

```bash
nm -a libpiper_plus.a | grep zh_en_loanword_json | awk '{print strtonum("0x"$3)}'
# JSON byte 数と一致確認
```

#### Layer 3: Runtime API check (推奨、最も信頼できる)

```objc
// tests/ios/E2ELoanwordTests.m
- (void)testLoanwordDataIsEmbedded {
    PiperLoanwordHandle* h = piper_plus_loanword_load_default();
    XCTAssertNotEqual(h, NULL);
    // C++ test_helper の getter (test build のみ export):
    XCTAssertEqual(piper_plus_loanword_get_acronyms_count(h), 65);
    XCTAssertEqual(piper_plus_loanword_get_loanwords_count(h), 40);
    XCTAssertEqual(piper_plus_loanword_get_fallback_count(h), 26);
    piper_plus_loanword_free(h);
}
```

CI 組込: `release-shared-lib.yml` の iOS build job 後に runtime smoke test step を追加。Android .aar は `androidTest/` で同等の Java 経由テスト。

---

## 7. 実装に関する懸念事項

### 懸念 1: Windows MSVC で xxd 不可
- **影響**: 設計書 §8.1 の元案 (`xxd -i`) は Windows CI で fail。
- **緩和**: §8.23 の `file(READ HEX)` パターン採用、CMake 純正で全 platform 動作。
- **責任**: Mobile Engineer。

### 懸念 2: `std::call_once` の例外伝播
- **挙動仕様** (cppref [thread.once.callonce]/2): `f()` が例外で exit した場合、`once_flag` は **未完了** 状態に残り、次回 `call_once` 呼出で関数が再実行される。`cached` 変数 (lambda 外の `static`) は assignment されないが、関数が throw する以上、戻り値は使われない。
- **デスクトップ経路**: file 欠損 → `LoanwordIoError`、schema 違反 → `LoanwordValidationError` が伝播。call_once は再実行可能。利用者がファイルを修正後 retry すれば成功する。
- **Embedded 経路**: build 時に CMake が validate (P5、所見 7 参照)。runtime 失敗は理論上ゼロ。
- **テスト**: `LoadDefault_FailureRetryAfterFix` を追加 (path 経路で 1 回失敗 → ファイル作成 → 2 回目成功で `once_flag` 再実行確認)。
- **責任**: C++ Dev #1。

### 懸念 3: iOS xcframework のシンボル衝突
- **影響**:
  1. iOS xcframework は app 最終 binary に **静的に組み込まれる**。同名シンボル他 framework との merge で衝突 risk。
  2. `static const unsigned char zh_en_loanword_json[]` は file-local だが、debug symbol には残る → crash report の symbolication で他 framework と紛らわしい。
- **緩和** (3 段階):
  1. **C++ namespace prefix**: `namespace piper::loanword::detail { static const unsigned char zh_en_loanword_json[]; }` で mangled name を `_ZN5piper8loanword6detail19zh_en_loanword_jsonE` 化。
  2. **`-fvisibility=hidden`**: iOS slice で `target_compile_options(piper_plus PRIVATE -fvisibility=hidden)`。`PIPER_PLUS_API` macro で明示 export した symbol だけを公開。
  3. **inline namespace**: `inline namespace piper_loanword_v1 {}` で ABI version を symbol に焼き込み、binary 不整合の誤解決を防止。
- **CI 検証**: iOS slice build 後 `nm -gU libpiper_plus.a | grep -v _piper_plus_ | grep -v _Ort` がほぼ空 (既存 `release-shared-lib.yml` 同等チェック実装済)。
- **責任**: Mobile Engineer。

### 懸念 4: gtest 31 件 → 27 件追加の CI 時間
- **影響**: 全 platform で +27 テスト × 5 platform = 135 ケース実行、CI 時間 +1-2 分。
- **緩和**: ctest --parallel `$(nproc)` で並列実行。テスト時間短縮 (各 < 10ms 想定)。
- **責任**: QA。

### 懸念 5: C API の buffer size handling
- **影響**: 利用者が小さい buffer を渡した場合、partial fill + required size を返す pattern が必要。
- **緩和**: 既存 `piper_plus_phonemize` の実装 pattern (`out_actual_size`) を流用。バッファが NULL なら required size のみ返す convention を採用。
- **責任**: C++ Dev #2。

### 懸念 6: Android .aar への JSON 同梱パス
- **影響**: gradle build で .aar が生成される際、`assets/` への JSON 配置が必要かどうか。
- **緩和**: 本機能は **C++ static 埋め込み**のため、`assets/` 経由は不要。.aar 内の `.so` バイナリに JSON が組み込まれる。Java 側からアクセス不要。
- **責任**: Mobile Engineer。

### 懸念 7: pinyin → IPA の既存関数依存
- **影響**: 既存 `chinese_phonemize.cpp` の `splitPinyin` / `pinyinToIPA` は **anonymous namespace 内 `static`** で内部リンケージ。`chinese_loanword.cpp` から呼べない。
- **緩和**: `chinese_phonemize.hpp` に **export 必須** (anonymous namespace から取り出して `namespace piper` 内 public に移動)。Python からの再実装は **禁止** (重複維持コスト + 出力差分 risk)。
  ```cpp
  // chinese_phonemize.hpp
  namespace piper {
  std::vector<Phoneme> pinyinToIPA(const std::string& syllable, int tone);
  PinyinSplit splitPinyin(const std::string& pinyin);
  }
  ```
- **責任**: C++ Dev #1。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] `LoanwordData` が `std::shared_ptr<const>` で返される (immutable shared)
- [ ] `std::call_once` で初期化、複数スレッド safe
- [ ] `embed_json_as_header` CMake 関数が xxd 非依存
- [ ] `PIPER_APPLE_EMBEDDED OR ANDROID` で条件分岐、デスクトップでは `std::ifstream` 経路
- [ ] dispatch 条件 `[zh,en,*]` / `[en,zh]` / `[zh,en,zh]` が Python と一致
- [ ] tokenize 時 trailing punctuation を strip
- [ ] digits を `letter_fallback` で drop (`std::isdigit`)
- [ ] PUA mapping (0xE020-0xE04A) と整合
- [ ] C API のシグネチャが `piper_plus.h` で `extern "C"` 内
- [ ] Multi-thread テスト (`ConcurrentAccess`) PASS
- [ ] `cmake --build` が全 5 platform で warning ゼロ
- [ ] `clang-format` 通過
- [ ] gtest 全 27 件 + 既存 31 件 PASS

### ドキュメントレビュー

- [ ] `src/cpp/README.md` (もしくは `docs/guides/c-api.md`) に ZH-EN 例
- [ ] `docs/guides/ios-integration.md` に「JSON 自動同梱」追記
- [ ] C API doxygen comment を追加 4 関数に付与

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 (libpiper_plus 1.0、ABI 安定保証) を対象。本 PR は §8.11 通り `libpiper_plus 0.x.0`。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **PUA 出力 byte 一致** | 既存学習済みモデル PUA 0xE020-0xE04A を絶対変えない。 |
| 2 | **Default-on, opt-out 可** | `phonemizeChineseMixed(..., enable_zh_en_dispatch=true)` で制御。default true。 |
| 3 | **Graceful failure** | デスクトップ: file 欠損 → exception。Embedded: build-time 保証で **runtime 失敗なし**。 |
| 4 | **Single source of truth** | Python JSON が canonical、C++ は consumer。 |
| 5 | **Platform-agnostic embedding** | xxd ではなく CMake `file(READ HEX)` で全 platform 純正動作。 |
| 6 | **Immutable shared via `shared_ptr<const>`** | mutex なしのスレッド安全、reference 共有のみ。 |
| 7 | **C ABI 互換性 (opaque handle)** | C API は `PiperLoanwordHandle*` opaque pointer で公開、struct layout 変更が ABI breaking にならない。 |
| 8 | **C++ 慣習を守る** | RAII、`std::shared_ptr`、`std::call_once`、`namespace`。Rust の `Arc` や Go の `sync.Once` を直輸入しない (C++ には標準パターンがある)。 |
| 9 | **Mobile-first design** | iOS xcframework / Android .aar が **設定変更ゼロ**で動作するように設計から考慮。 |

### 9.1 データ層

| 採用パス | トリガー | 実装 |
|---------|---------|------|
| デスクトップ: `std::ifstream` (現行案) | エントリ数 < 100,000 | P1 のまま |
| Mobile: CMake `file(READ HEX)` static embed (現行案) | iOS / Android | P5 のまま |
| `cppfront` / `std::embed` (C++26) | 標準 `#embed` directive 利用可能になり次第 | xxd / file(READ HEX) を全廃 |

**v1.0.0 採用条件 (3 軸 AND)**:
1. GCC ≥ 15.1 / Clang ≥ 19.0 / MSVC ≥ 17.x の `#embed` 実装が **全て stable channel に入った状態で 12 ヶ月経過**
2. piper-plus 要求 CMake 最低バージョンが **CMake 3.31+** (`#embed` を `try_compile` 検査可能)
3. **iOS Xcode toolchain (Apple Clang)** が `#embed` 対応 (歴史的に upstream LLVM から 6-12 ヶ月遅れ)

**fallback 削除タイミング**: 上記 3 軸 + `release-shared-lib.yml` の全 platform で `#embed` が PASS した PR をマージしてから、CMake `embed_json_as_header` 関数を `[[deprecated]]` 化、さらに 1 リリース後に削除。

**実装**: `target_compile_features(piper_plus PUBLIC cxx_std_26)` + `check_cxx_source_compiles("#embed \"test.txt\"" HAS_CXX_EMBED)` で機械判定可能化。

### 9.2 API 層

```cpp
// Builder pattern (C++17)
class ChinesePhonemizerBuilder {
public:
    ChinesePhonemizerBuilder& with_zh_en_dispatch(bool enabled);
    ChinesePhonemizerBuilder& with_loanword_data(std::shared_ptr<const LoanwordData> data);
    std::unique_ptr<ChinesePhonemizer> build();
};

// 利用例
auto phonemizer = ChinesePhonemizerBuilder{}
    .with_zh_en_dispatch(true)
    .with_loanword_data(getDefaultLoanwordData())
    .build();
```

- 例外型: `class LoanwordValidationError : public std::invalid_argument`、`class LoanwordIoError : public std::runtime_error`。
- 既存 `phonemizeChineseMixed()` (現行 free fn) は v1.0.0 で `[[deprecated]]` alias、内部で builder 経由に転送。
- C API: `extern "C"` で opaque handle を提供、struct layout を ABI から隠蔽。

### 9.3 Dispatcher

**Day 1 (本 PR)**: `prevIsZh / nextIsZh` 直書き。

**v1.0.0**: `static const std::array<CodeSwitchPattern, N> patterns` で declarative 化。JA-EN / KO-EN は array 1 行追加で対応可能。

### 9.4 Library 構成

```
src/cpp/
├── piper_plus.h                          (C API、ABI stable)
├── piper_plus_c_api.cpp                  (C API impl)
├── piper.cpp                             (multilingual dispatcher)
├── chinese_phonemize.{hpp,cpp}            (既存)
├── chinese_loanword.{hpp,cpp}             (新規 - 本 PR)
├── data/
│   └── zh_en_loanword.json
└── tests/
    ├── test_zh_en_loanword.cpp
    └── test_c_api_zh_en.cpp
```

**Sub-library 化はしない**: header-only 化や `piper_plus_loanword.so` 分離は ABI 管理コストに見合わない。同じ shared lib 内で namespace 分離すれば十分。

### 9.5 Failure mode

| ケース | デスクトップ | Mobile (Embedded) | エラー型 |
|-------|------------|------------------|---------|
| default JSON 欠損 | `LoanwordIoError` (file not found) | **build 失敗** (CMake `file(READ HEX)` でファイル必須) | — |
| schema 違反 | `LoanwordValidationError` | 同左 (init 時) | inherits `std::invalid_argument` |
| JSON parse error | `nlohmann::json::parse_error` | 同左 | nlohmann |
| C API 経由 | `nullptr` 返却 + `g_last_error` 設定 | 同左 | string |
| `enable_zh_en_dispatch=false` | 既存 `phonemize_chinese` 経路 | 同左 | — |

### 9.6 i18n 拡張パス

| Phase | 内容 | 必要な変更 |
|-------|------|-----------|
| Phase 1 (本 PR) | ZH-EN | `data/zh_en_loanword.json` 1 個 |
| Phase 2 | JA-EN / KO-EN | `data/{ja_en, ko_en}_loanword.json` + CMake で複数 embed + pattern table 拡張 |
| Phase 3 | 任意ペア | `LoanwordRegistry::register(src, tgt, data)` API |

### 9.7 テスト戦略

- **gtest** で 27 unit + 1 multi-thread (Day 1 の現行案)。
- **Cross-runtime fixture** (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) を CI sync で `src/cpp/tests/fixtures/` にコピー (TICKET-06)。`nlohmann::json` でループ実行。
- **5 platform CI** (Linux/macOS/Windows/iOS/Android) で全件 PASS 必須。
- **JSON 同梱検証**: stripped binary では `nm` / `strings` 不可、**Section 6 の 3 層検証** (build print + symbol check + runtime API) を CI 組込。

#### Sanitizer CI 統合計画 (段階導入)

| フェーズ | 対象 | 実装 | 期待効果 |
|---------|------|------|---------|
| Phase 1 (本 PR) | `ConcurrentAccess` テストのみ ASan + TSan で **local 実行** | 開発者の `cmake -DENABLE_ASAN=ON` | race 検出 (PR 前) |
| Phase 2 (TICKET-06) | nightly CI に sanitizer job 追加 | `.github/workflows/cpp-sanitizers.yml` (新規) を `schedule: cron 0 3 * * *` で起動 | 累積回帰検出 |
| Phase 3 (v1.0.0) | PR triggered で **ZH-EN テストのみ** sanitizer 実行 | `cpp-tests.yml` matrix 追加、`-DENABLE_ASAN=ON -DTESTS_ZH_EN_ONLY=1` で範囲限定 | PR ごとの早期検出 |

**コスト**:
- Phase 2: nightly のみ → 1 日 1 回 × 30 分 = ~15 hr/月 (GitHub Actions free tier 内)
- Phase 3: PR ごと +5 min (ZH-EN 限定) → 許容範囲

`PIPER_PLUS_LOANWORD_SAN=1` env var で CMake が `-fsanitize=address,thread` を append する option を `cmake/CompilerSettings.cmake` に追加。

### 9.8 Observability

C++ には標準 logging が無いため:

- 本 PR (Day 1): `std::cerr` への debug 出力 (`PIPER_DEBUG_ZH_EN=1` env var で有効化)。
  ```cpp
  if (std::getenv("PIPER_DEBUG_ZH_EN")) {
      std::cerr << "[zh-en hit] loanword token=" << token
                << " syllables=" << join(syllables) << "\n";
  }
  ```
- v1.0.0 候補: `spdlog` 等の structured logging library を optional dependency として追加。利用者が好きな sink (file / syslog / journald) に流せる。

**Privacy 配慮**: debug 出力に入力テキストを含めない (token は変換結果のみ)。

### 9.9 ABI 戦略 (struct layout 編)

| 変更 | ABI impact |
|------|-----------|
| 新 C API 4 関数追加 | **non-breaking** (関数追加のみ) |
| `PiperLoanwordHandle` opaque struct | **non-breaking** (struct layout 隠蔽) |
| `phonemizeChineseMixed` シグネチャ変更 (param 追加) | **breaking** → v1.0.0 で実施、Phase 1 では新 free fn 追加で吸収 |
| C++ namespace 内 struct (`LoanwordData`) field 追加 | **C++ ABI breaking 可能性** | 内部使用のみで C ABI に露出させない |

**opaque pointer の保証**:
- `PiperLoanwordHandle*` は **常に `void*` 等価サイズ**。32/64-bit 切替で関数シグネチャ ABI は変わらない (calling convention 経由で sizeof(pointer) は処理される)。
- 内部 C++ struct (`LoanwordData`) は **C ABI から完全に隠蔽**。`std::unordered_map` を含む型を C 側に露出しない (libstdc++/libc++/MSVC STL で layout 異なるため)。

**将来 stats struct 追加時のルール** (例: `piper_plus_loanword_stats`):
```c
typedef struct PiperLoanwordStats {
    uint32_t version;          // 必ず先頭、layout migration tag
    uint32_t struct_size;      // sizeof(PiperLoanwordStats)
    uint32_t acronyms_count;
    uint32_t loanwords_count;
    uint32_t fallback_count;
    uint8_t  _reserved[40];    // 64-byte total, future fields
} PiperLoanwordStats;
_Static_assert(sizeof(PiperLoanwordStats) == 64, "ABI: stats struct must be 64 bytes");
```
- **明示的 padding** + `_Static_assert` で 32/64-bit 共通の sizeof 保証。
- **Endianness**: piper-plus 対象 platform はすべて little-endian (x86, ARM、Windows ARM64 含む)。big-endian 対応は v2.0.0 以降。
- **ABI snapshot**: `nm --dynamic libpiper_plus.so | sort > abi-snapshot.txt` を release ごとに記録、minor version bump で diff チェック。

### 9.10 Mobile distribution

| Platform | 配信方法 | 検証 |
|----------|---------|------|
| iOS | Swift Package Manager (`Package.swift`) → xcframework | `swift package resolve` 動作確認 |
| Android | Maven Central .aar | gradle 経由 import 確認 |
| Linux/macOS/Windows | tar.gz / .zip release artifact (`release-shared-lib.yml`) | 既存パイプライン |

**重要**: iOS / Android の **JSON 同梱が `.a` / `.so` バイナリに含まれる**ため、配信物に追加ファイル不要。利用者は `dict_dir` 引数を NULL で OK。

---

## 10. 後続タスクへの連絡内容

### TICKET-06 (CI Sync) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JSON 配置パス** | `src/cpp/data/zh_en_loanword.json` |
| **比較対象** | Python source と byte 一致 |
| **CI matrix** | 既存 `release-shared-lib.yml` で全 platform カバー、追加 job 不要 |
| **Sanitizers** | `ASAN=1` `TSAN=1` で `ConcurrentAccess` テストを CI に追加 |
| **iOS .xcframework / Android .aar 検証** | `nm` / `strings` で JSON 同梱確認 |

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **README** | `src/cpp/README.md` に C API 例と CMake オプション追加 |
| **CHANGELOG** | "Added: ZH-EN code-switching, C API export, iOS/Android JSON auto-embed" |
| **iOS guide** | `docs/guides/ios-integration.md` に「dict_dir NULL でも動作」追記 |
| **C API doxygen** | 4 関数の `///<` doc comment、`docs/api-reference/c-api.md` 自動生成 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §2.5 / §4.1 P1-P6 / §8.1 / §8.6 / §8.14 / §8.23 から派生) |
