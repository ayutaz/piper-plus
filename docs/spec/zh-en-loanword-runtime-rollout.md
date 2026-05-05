# ZH-EN Code-Switching: 全ランタイム展開設計書

**ステータス**: Draft
**対象ブランチ**: `feat/zh-en-loanword-runtimes`
**前提 PR**: [#397](https://github.com/ayutaz/piper-plus/pull/397) (Python 学習側 + Python ランタイム側完了)
**フォローアップ Issue**: #384 の Out of Scope で予告

---

## 1. 背景

PR #397 で **Python (学習側 + ランタイム側)** の ZH-EN code-switching が実装された:

- 中国語コンテキスト中の英単語 (acronym/loanword) を Mandarin pinyin で発音
- 辞書: `acronyms` 65, `loanwords` 40, `letter_fallback` 26 (A-Z)
- `MultilingualPhonemizer` が `[zh,en,zh] / [zh,en] / [en,zh]` パターンを検出して dispatch
- 学習側 + Python ランタイム両方で同等動作

しかし、**他 5 ランタイム (Rust / Go / C# / JS-WASM / C++) は未対応**。実プロダクト環境 (iOS / Android / Unity / Web / CLI) は Python 以外を主に使うため、本機能の効果が見えず、機能ギャップが発生している。

本書は **5 ランタイム同時展開** (1 ブランチ / 1 PR) のための調査結果と対応計画をまとめる。

---

## 2. 各ランタイム現状調査

### 2.1 Rust (`src/rust/piper-plus-g2p/`)

| 項目 | 状態 |
|------|------|
| 中国語実装 | `chinese.rs` 1,314 行、関数 60 個 |
| pinyin → IPA 関数 | `split_pinyin()` / `pinyin_to_ipa()` / `normalize_pinyin()` / `apply_tone_sandhi()` |
| 公開構造体 | `ChinesePhonemizer { dict: ZhDictRef }` |
| データロード | `serde_json::from_str` / `OnceLock` キャッシュ、`include_str!` 未使用 (実行時ファイル読込) |
| Multilingual | `multilingual.rs` 1,015 行、`UnicodeLanguageDetector` + `segment_text` 完備 |
| ZH-EN dispatch | **❌ 未実装** |
| `phonemize_embedded_english` | **❌ 未実装** |
| `_load_loanword_data` | **❌ 未実装** |
| `zh_en_loanword.json` | **❌ 未同梱** |
| テスト | unit 30+ (chinese.rs 内 `#[cfg(test)]`) + integration (`piper-core/tests/test_chinese.rs` 373 行) |

**追加 LOC 見込み**: ~400 行 (`phonemize_embedded_english` 実装 + LoanwordData struct + multilingual dispatch)

### 2.2 Go (`src/go/phonemize/`)

| 項目 | 状態 |
|------|------|
| 中国語実装 | `chinese.go` 662 行 |
| pinyin → IPA 関数 | `zhSplitPinyin()` / `zhPinyinToIPA()` / `zhNormalizePinyin()` / `zhApplyToneSandhi()` |
| 公開関数 | `NewChinesePhonemizer(...)`, `PhonemizeWithProsody(...)` |
| データロード | embed なし、`map[rune]string` をプログラム的に注入 |
| Multilingual | `multilingual.go` + `unicode_detect.go`、`SegmentText` 完備 |
| ZH-EN dispatch | **❌ 未実装** |
| 関連実装 | **❌ 全て未実装** |
| テスト | `chinese_test.go` 25+ 関数、500+ ケース、golden test あり |

**追加 LOC 見込み**: ~300 行 (新規 `chinese_loanword.go` + `multilingual.go` 拡張)

### 2.3 C# (`src/csharp/PiperPlus.Core/`, `PiperPlus.Cli/`)

| 項目 | 状態 |
|------|------|
| 中国語実装 (Core) | `ChinesePhonemizer.cs` **113 行** (薄ラッパ) |
| Engine | `IChineseG2PEngine` interface、実装は `DotNetChineseG2PEngine` (Cli 側、NuGet `DotNetG2P.Chinese 1.8.0` をラップ) |
| pinyin → IPA | NuGet 内部、`ToPuaPhonemes()` / `ToIpaWithProsody()` |
| データロード | csproj に `<EmbeddedResource>` 設定なし |
| Multilingual | `MultilingualPhonemizer.cs` 完備、`UnicodeLanguageDetector.SegmentText()` あり |
| ZH-EN dispatch | **❌ 未実装** (line 220 付近に追加余地あり) |
| Engine 拡張 | **NuGet 改修不可なので Core/Cli 側で独立実装が必要** |
| テスト | `ChinesePhonemizerTests.cs` 401 行 (StubEngine 利用)、`ChinesePhonemizerPuaTests.cs` あり |

**追加 LOC 見込み**: ~400 行 (Engine 経由でなく独立した embedded English 経路を Core 側に実装)

**特殊な制約**: `DotNetG2P.Chinese` (NuGet) は外部ライブラリでビルド不可。**ZH-EN 用の pinyin → IPA を C# 側に独立実装する必要あり** (一部のロジックは Python から移植)。

### 2.4 JS/WASM (`src/wasm/g2p/`, `src/rust/piper-wasm/`)

| 項目 | 状態 |
|------|------|
| JS 中国語実装 | `wasm/g2p/src/zh/index.js` **140 行** (character pass-through のみ) |
| Rust WASM | `piper-wasm/src/lib.rs` で `setChineseDictionary()` FFI 公開 |
| pinyin → IPA | Rust 側 (`piper-plus-g2p/src/chinese.rs`) で実装、JS 経由で呼出 |
| データロード | Rust 側で JSON load、JS は薄い |
| Multilingual | `wasm/g2p/src/detect.js` 294 行、`segmentText` 完備 |
| ZH-EN dispatch | **❌ 未実装** |
| 二層問題 | **JS と Rust の両方を更新する必要があるか判断必要** |
| テスト | `test/test-chinese.js` 463 行 (mock 中心) |

**追加 LOC 見込み**: ~250 行 (Rust 完了が前提、JS 側は薄ラッパ + テスト追加で済む)

**実装場所判断**: Rust 側で `phonemize_embedded_english()` を実装すれば、WASM ビルドだけで JS 側にも自動的に展開される。JS 側は新 FFI (`setChineseLoanwordData()`) の薄ラッパとテストのみ。

### 2.5 C++ (`src/cpp/`)

| 項目 | 状態 |
|------|------|
| 中国語実装 | `chinese_phonemize.cpp` **1,130 行** |
| ヘッダ | `chinese_phonemize.hpp` (公開関数 2 つ) |
| pinyin → IPA | 完全実装、PUA 0xE020-0xE04A 使用 |
| データロード | `nlohmann/json` + `std::ifstream`、リソース埋め込みなし |
| Multilingual | `language_detector.cpp` で言語セグメント分割、`piper.cpp:2589-2597` で dispatch |
| ZH-EN dispatch | **❌ 未実装** |
| C API | `piper_plus.h` / `piper_plus_c_api.cpp`、中国語用 C API は **未エクスポート** |
| テスト | `test_multilingual_g2p.cpp` で中国語 2 ケースのみ (薄い) |
| iOS/Android | xcframework / Android 用リソース同梱パターン要確認 |

**追加 LOC 見込み**: ~500 行 + iOS/Android リソース対応

**特殊な難所**:
1. C API export 追加 (`piper_plus_phonemize_embedded_english`)
2. iOS xcframework / Android のリソース同梱 (`PrivacyInfo.xcprivacy` 周辺)
3. テストフレーム自体の拡充 (現状 2 ケースしかない)
4. CMake への JSON データファイル追加 (`PiperPlusShared.cmake`)

---

## 3. 共通の実装パターン

全ランタイムで **同一の 4 ステップ**:

```
Step 1. zh_en_loanword.json を各ランタイムに同梱
        - Python 側 (src/python/g2p/.../data/zh_en_loanword.json) が source of truth
        - 各ランタイムに byte-for-byte コピーを配置 (CI で同期ガード)

Step 2. phonemize_embedded_english(text, loanword_data) 相当を追加
        - 既存の split_pinyin / pinyin_to_ipa を再利用
        - tokenize → loanwords lookup → acronyms lookup → letter_fallback
        - schema validation 付きの load 関数

Step 3. multilingual dispatcher に [zh,en,*] / [en,zh] / [zh,en] パターン検出
        - en セグメントの前後に zh があれば embedded path
        - そうでなければ既存 EnglishPhonemizer 経路 (リグレッション防止)

Step 4. ユニットテスト + CI 同期ガード
        - Python 側との JSON 一致確認 (byte-for-byte)
        - 各ランタイムで Issue 例 3 つ (请打开 GPS, 我喜欢用 Python 写代码, 让我用 ChatGPT 写代码)
```

### Lookup priority (全ランタイム共通)

```
1. case-sensitive loanwords (例: "Python", "iPhone")
   ↓ ヒットなければ
2. uppercase acronyms (例: "GPS" → "gps".upper() = "GPS")
   ↓ ヒットなければ
3. letter_fallback (A-Z, char-by-char、digits は drop)
```

### JSON スキーマ (全ランタイム共通)

```json
{
  "version": 1,
  "acronyms": { "GPS": ["ji4","pi4","ai1","si4"], ... },
  "loanwords": { "Python": ["pai4","sen1"], ... },
  "letter_fallback": { "A": ["ei1"], "B": ["bi4"], ... }
}
```

---

## 4. 対応する必要がある課題リスト

### 4.1 ランタイム別の必須タスク

| # | ランタイム | タスク | 行数目安 | 難易度 |
|---|----------|-------|---------|-------|
| R1 | Rust | `chinese.rs` に `phonemize_embedded_english` 関数追加 (2 箇所 †1) | ~300 | 中 |
| R2 | Rust | `LoanwordData` struct + `load_loanword_data()` (schema validation) | ~80 | 低 |
| R3 | Rust | `multilingual.rs` で `[zh,en,*]` パターン dispatch | ~50 | 低 |
| R4 | Rust | `data/zh_en_loanword.json` 同梱 (`include_str!`) | ~5 | 低 |
| R5 | Rust | テスト追加 (unit + integration、2 箇所同期確認含む) | ~150 | 中 |

> **†1 Rust の重要な制約**: 中国語実装が `piper-plus-g2p/src/chinese.rs` (WASM 用) と `piper-core/src/phonemize/chinese.rs` (デスクトップ + ProsodyInfo 統合) の **2 箇所に存在** (詳細: §8.5)。両方に実装が必要なため、当初見積 ~400 行 → **~600 行**。同期テストを追加して整合性を担保する。
| G1 | Go | `chinese_loanword.go` 新規 (Loanword struct + load) | ~120 | 低 |
| G2 | Go | `chinese.go` の `PhonemizeEmbeddedEnglish` 関数追加 | ~100 | 中 |
| G3 | Go | `multilingual.go` dispatch 追加 | ~50 | 低 |
| G4 | Go | `//go:embed` で JSON 埋め込み | ~5 | 低 |
| G5 | Go | テスト追加 | ~80 | 中 |
| C1 | C# | `Core/Phonemize/ChineseEmbeddedEnglish.cs` 新規 | ~250 | 高 (NuGet 経由しない pinyin→IPA を C# 側に再実装) |
| C2 | C# | `Core/Resources/zh_en_loanword.json` を `<EmbeddedResource>` で同梱 | ~10 (csproj) | 低 |
| C3 | C# | `MultilingualPhonemizer.cs` の dispatch 拡張 | ~50 | 低 |
| C4 | C# | テスト追加 (xUnit) | ~150 | 中 |
| W1 | JS/WASM | Rust 側の R1-R5 完了が前提 (Rust WASM 経由) | — | — |
| W2 | JS/WASM | Rust に `setChineseLoanwordData()` FFI 追加 | ~30 | 低 |
| W3 | JS/WASM | JS 側 `ChineseG2P` に薄ラッパ追加 | ~80 | 低 |
| W4 | JS/WASM | TypeScript 型定義 (`types/index.d.ts`) 更新 | ~20 | 低 |
| W5 | JS/WASM | テスト追加 (`test-chinese.js`) | ~120 | 中 |
| P1 | C++ | `chinese_loanword.hpp/cpp` 新規 | ~300 | 中 |
| P2 | C++ | `phonemize_embedded_english()` C++ 実装 | ~150 | 中 |
| P3 | C++ | `piper.cpp` dispatch 拡張 | ~50 | 低 |
| P4 | C++ | C API export 追加 (`piper_plus_phonemize_embedded_english`) | ~80 | 中 |
| P5 | C++ | iOS/Android リソース同梱 (`PiperPlusShared.cmake` / `ios.toolchain.cmake`) | ~30 | 高 |
| P6 | C++ | テスト追加 (現状 2 ケースのみ → 拡充必要) | ~200 | 中 |

**合計**: 約 **2,300 行** (テスト含む)

### 4.2 横断的な課題

| # | 課題 | 詳細 | 対応方針 |
|---|------|------|---------|
| X1 | **Source of truth の JSON 同期** | 6 箇所に同じ JSON が分散する (Python 学習 / Python ランタイム / Rust / Go / C# / WASM-data / C++) | CI 同期ガードを各ランタイムで追加、git pre-commit hook 検討 |
| X2 | **PUA mapping の一貫性** | 中国語 PUA codepoint (0xE020-0xE04A) が全ランタイムで同じ tone marker を出すか確認 | 既存の `docs/spec/pua-contract.toml` で担保済み、新規追加なし |
| X3 | **Schema validation の方針統一** | Python 側の `_load_loanword_data` は厳格 validation (list[str] 型チェック)。各ランタイムで同等のエラーメッセージ形式を出す | `f"{path}: '{section}.{key}' must be list[str]"` 形式を標準化 |
| X4 | **テストケースの統一** | Issue 例 3 つ + 各 priority/punctuation/digits ケースを全ランタイムでカバー | 統一テストマトリックス (後述) |
| X5 | **同期 CI ジョブ** | 6 JSON が一致しているかの byte-for-byte 比較 CI | 既存 `python-tests` workflow に拡張 or 新規 `zh-en-loanword-sync` job |
| X6 | **C++ iOS/Android リソース** | xcframework / aar に JSON を含める手段の確立 | `cmake/PrivacyInfo.xcprivacy` と同パターンで JSON を bundle |
| X7 | **C# DotNetG2P.Chinese 制約** | NuGet 外部ライブラリは改修不可、独立 pinyin→IPA を C# に実装 | Python の `pinyin_to_ipa` を C# に移植 (~200 行) |
| X8 | **JS/WASM の二層** | JS 側と Rust 側どちらに loanword ロジックを置くか | **Rust 側に集約**、JS は FFI 薄ラッパに留める |

### 4.3 統一テストマトリックス

各ランタイムで以下を網羅:

```
[基本]
- test_acronym_gps              (GPS が acronym テーブルにヒット)
- test_loanword_python          (Python が loanword、case-sensitive)
- test_loanword_chatgpt         (ChatGPT 5 syllables)
- test_letter_fallback_zz       (ZZ → letter_fallback)
- test_empty_input

[priority]
- test_loanword_beats_acronym   (override で loanword 優先)
- test_acronym_beats_fallback   (override で acronym 優先)
- test_python_vs_PYTHON         (case sensitivity)

[punctuation]
- test_trailing_punctuation     (GPS, GPS, GPS. all equal)

[multi-segment]
- test_two_embedded_en          (ChatGPT 和 Python = 7 syllables added)

[digits]
- test_digits_dropped           (Z2Z9 == ZZ)
- test_acronym_with_digits      (MP3 が acronym 直接ヒット)

[dispatch]
- test_zh_en_zh_pattern
- test_zh_en_pattern            (request example: 请打开 GPS)
- test_en_zh_pattern            (en at start)
- test_pure_zh_unaffected       (regression)
- test_pure_en_uses_english     (regression)

[issue examples]
- test_issue_example_gps        (请打开 GPS)
- test_issue_example_python     (我喜欢用 Python 写代码)
- test_issue_example_chatgpt    (让我用 ChatGPT 写代码)

[sync]
- test_json_matches_python_source  (byte-for-byte 比較)
```

合計 **20 テスト/ランタイム × 5 ランタイム = 100 テスト**追加。

---

## 5. 1 ブランチ戦略のリスクと対策

ユーザー要望により **1 ブランチで 5 ランタイム同時対応** する。リスクと対策:

| リスク | 対策 |
|-------|------|
| PR が巨大化 (~2,300 行) でレビュー困難 | コミットを **ランタイム単位**で分割 (5 commit + 統合 commit)、PR description に章立て |
| 1 ランタイムの問題で全体 block | **ランタイム間に依存なし**にする (W1 のみ R 完了が前提)、独立コミット化 |
| CI 並列実行時間が長くなる | CI は元々全ランタイムを回しているので追加コストなし |
| マージコンフリクト確率上昇 | 短期間でマージ完了を目指す (作業期間 1-2 週間目標)、可能なら毎日 dev からリベース |
| テスト失敗の切り分け困難 | 各ランタイムの実装は **ファイル分離** で行い、失敗ログで即特定可能に |

---

## 6. ロールアウト計画

### 6.1 実装順序 (依存関係を考慮)

```
Day 1-3: Rust    (パターン確立、後続のリファレンス)
Day 4-5: Go     (Rust と類似、移植ベース)
Day 6-8: C#     (NuGet 制約があるため独立実装、ロジック分量多)
Day 9:    JS/WASM (Rust 完了済みなので薄ラッパ + WASM rebuild)
Day 10-12: C++ (最大の難所、iOS/Android リソース対応含む)
Day 13: 統合テスト + CI 同期ガード追加 + ドキュメント更新
Day 14: PR レビュー対応
```

### 6.2 コミット粒度

```
1. docs(spec): zh-en loanword runtime rollout 設計書追加 (本書)
2. feat(rust): ZH-EN code-switching 実装 (R1-R5)
3. feat(go): ZH-EN code-switching 実装 (G1-G5)
4. feat(csharp): ZH-EN code-switching 実装 (C1-C4)
5. feat(wasm): ZH-EN code-switching 実装 (W2-W5)
6. feat(cpp): ZH-EN code-switching 実装 (P1-P6)
7. ci: zh_en_loanword.json 同期ガード追加 (X5)
8. docs: 各ランタイムの README/CHANGELOG 更新
```

### 6.3 受け入れ基準

PR マージの最低条件:

- [ ] 5 ランタイムすべてで Issue #384 例 3 つが期待 IPA 列を出す
- [ ] 各ランタイムで上記テストマトリックス全件 PASS
- [ ] `zh_en_loanword.json` が 6 箇所すべてで byte-for-byte 一致 (CI ガード)
- [ ] 既存の純中国語 / 純英語 / `[ja,en]` パターンにリグレッションなし
- [ ] CI 全 job green (lint, ruff format, build matrix, runtime tests)
- [ ] 各ランタイムの README/CHANGELOG 更新
- [ ] iOS xcframework / Android aar ビルドで JSON 同梱確認

---

## 7. 関連ドキュメント

- 親 PR (Python): [#397](https://github.com/ayutaz/piper-plus/pull/397)
- 元 Issue: [#384](https://github.com/ayutaz/piper-plus/issues/384)
- PUA 仕様: `docs/spec/pua-contract.toml`
- Phoneme Timing 仕様: `docs/spec/phoneme-timing-contract.toml`
- iOS shared lib 仕様: `docs/spec/ios-shared-lib.md`

---

## 8. 深堀り調査結果

主要な実装ブロッカーになり得る 3 項目について個別調査を実施。各項目で推奨案を確定した。

### 8.1 C++ iOS/Android リソース同梱戦略

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

### 8.2 C# 独立実装方針

**問題**: `DotNetG2P.Chinese 1.8.0` (NuGet) は外部ライブラリで改修不可。Python 側の `_pinyin_to_ipa()` 相当を C# 側に独立実装する必要がある。

**Python 移植量見積**:

| Python 関数/データ | LOC | C# 移植要否 |
|------------------|-----|------------|
| `_pinyin_to_ipa()` | ~40 | ✓ 必須 |
| `_split_pinyin()` | ~20 | ✓ 必須 |
| `_normalize_pinyin()` | ~20 | ✓ 必須 |
| `_INITIAL_TO_IPA` (dict) | ~25 | ✓ 必須 (静的辞書として) |
| `_FINAL_TO_IPA` (dict) | ~55 | ✓ 必須 (静的辞書として) |
| `_apply_tone_sandhi()` | ~75 | ✗ **不要** (loanword は単独 syllable で sandhi 不要) |
| `phonemize_embedded_english()` | ~60 | ✓ 必須 |
| **合計** | **~295 行** | **~120 行** (sandhi 除外) |

**3 案比較**:

| 案 | 実装場所 | メリット | デメリット |
|---|---------|--------|-----------|
| **A** | `IChineseG2PEngine` 拡張 + `DotNetChineseG2PEngine` で実装 | Engine 一貫性 | NuGet 経由しない経路を Engine 内に持つ違和感 |
| **B** | `Core/Phonemize/ChineseEmbeddedEnglishConverter` 独立 class | シンプル、Engine 不要 | Engine 経路と独立しすぎる |
| **C** | `MultilingualPhonemizer` 内に直接実装 | 局所的 | 汎用性低、テスト困難 |

**推奨**: **案 A (`IChineseG2PEngine` 拡張)** — Engine interface に `ConvertEmbeddedEnglish(text, loanwordData)` を追加、`DotNetChineseG2PEngine` 内に Python 移植版実装。ロジックは NuGet 経由しないが、interface としては統一。

**csproj 設定 (EmbeddedResource)**:

```xml
<!-- PiperPlus.Core.csproj -->
<ItemGroup>
  <EmbeddedResource Include="Phonemize/Data/zh_en_loanword.json" />
</ItemGroup>
```

```csharp
// PiperPlus.Core/Phonemize/Data/LoanwordDataLoader.cs
internal static class LoanwordDataLoader {
    public static LoanwordData LoadDefault() {
        var asm = typeof(LoanwordDataLoader).Assembly;
        using var stream = asm.GetManifestResourceStream(
            "PiperPlus.Core.Phonemize.Data.zh_en_loanword.json");
        // schema validation 込みでパース
        return ParseAndValidate(stream);
    }
}
```

**実装規模**: 合計 **~340 LOC** (実装 ~140 + テスト ~200)、想定 1.5 週間。

### 8.3 JSON 同期 CI 戦略

**問題**: 6 箇所 (Python 学習側 / Python ランタイム側 / Rust / Go / C# / WASM / C++) に同じ JSON が分散する。

**既存パターン**: `pua.json` の同期は `check_pua_consistency.py` + `/check-pua` skill + pre-commit hook で実現済み (commit `3a38a61f`, `96138922`, `90ff6390`)。これを踏襲する。

**4 案比較**:

| 案 | 工数 | CI 速度 | 開発体験 | Windows 対応 |
|---|-----|---------|---------|------------|
| **A** | 各ランタイム側 unit test で byte 比較 | ★★ | 手動同期必要 | ◯ |
| **B** | 専用 CI job で sha256 比較 | ★ | CI 報告のみ | ◯ |
| **C** | 自動 sync スクリプト + pre-commit hook | ★★★ | ベスト | △ (CRLF 注意) |
| **D** | symlink で single source 化 | ★ | ベスト | ✗ (Windows 非対応) |

**推奨**: **案 A + B のハイブリッド** — 既存 PUA 同期戦略を踏襲しつつ、CI で hash 比較を最終ガード

**段階構成**:

```
段階 1: Python 既存テスト保持 (TestRuntimeBundleSync) - 0.5h
段階 2: 各ランタイムに schema 検証 + byte 比較テスト追加 - 3h
段階 3: 専用 CI job で sha256 hash 比較 - 1h
段階 4: ドキュメント / QA - 1h

合計: ~5.5h
```

**新規 CI job (案)**:

```yaml
# .github/workflows/loanword-consistency.yml
name: Loanword Dictionary Sync
on:
  pull_request:
    paths:
      - '**/zh_en_loanword.json'
      - '.github/workflows/loanword-consistency.yml'
jobs:
  hash-consistency:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Verify byte-for-byte sync
        run: |
          SOURCE=src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
          HASH=$(sha256sum "$SOURCE" | cut -d' ' -f1)
          COPIES=(
            src/python_run/piper/phonemize/data/zh_en_loanword.json
            src/rust/piper-plus-g2p/data/zh_en_loanword.json
            src/go/phonemize/data/zh_en_loanword.json
            src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json
            src/wasm/g2p/data/zh_en_loanword.json
            src/cpp/data/zh_en_loanword.json
          )
          for copy in "${COPIES[@]}"; do
            [ -f "$copy" ] || { echo "MISSING: $copy"; exit 1; }
            COPY_HASH=$(sha256sum "$copy" | cut -d' ' -f1)
            [ "$HASH" = "$COPY_HASH" ] || {
              echo "MISMATCH: $copy"
              echo "Expected: $HASH"
              echo "Got:      $COPY_HASH"
              exit 1
            }
          done
          echo "All 6 copies match $SOURCE"
```

**新規 helper script (PUA パターン踏襲)**:

```python
# scripts/check_loanword_consistency.py (PUA 同等)
# 使い方: python scripts/check_loanword_consistency.py [--fix]
# --fix オプションで Python source から自動コピー
```

これで `/check-loanword` skill 化して開発者体験を向上できる (将来課題)。

---

### 8.4 JS/WASM 二層 FFI 設計

**問題**: ZH-EN loanword data を Rust WASM 側と JS 側のどちらに置くか。WASM バンドルサイズ影響を最小化したい。

**既存 FFI パターン**:

```rust
// src/rust/piper-wasm/src/lib.rs:473
#[wasm_bindgen(js_name = setChineseDictionary)]
pub fn set_chinese_dictionary(
    &mut self,
    single_json: &[u8],     // JSON bytes (JS から渡す)
    phrase_json: &[u8],
) -> Result<(), JsValue>
```

JS 側 → Rust 側に **JSON bytes** を渡す形 (`&[u8]`) で、Rust 内部で `serde` パース。一度 set すれば永続。**これと同じパターンを踏襲**。

**3 案比較**:

| 案 | データ位置 | WASM サイズ | JS bundle サイズ | メンテ性 |
|---|-----------|------------|----------------|---------|
| **A** | Rust 内 `include_bytes!` | +5KB (圧縮 +2KB) | 不変 | △ (WASM 再ビルド必要) |
| **B** | JS 側に bundle、`setChineseLoanwordData()` で inject | 不変 | +5KB | ★★★ (JSON 差し替え容易) |
| **C** | npm 公開時 `fetch()` で外部取得 | 不変 | 不変 | ✗ (オフライン NG) |

**推奨**: **案 B (JS 側 bundle + Rust 注入)** — 既存 `setChineseDictionary` と完全に同じパターンで一貫性確保、WASM 再ビルド不要、bundler は JSON import を最適化済み

**実装スケッチ**:

```rust
// piper-wasm/src/lib.rs に追加
#[wasm_bindgen(js_name = setChineseLoanwordData)]
pub fn set_chinese_loanword_data(
    &mut self,
    loanword_json: &[u8],
) -> Result<(), JsValue> {
    let data = serde_json::from_slice::<LoanwordData>(loanword_json)
        .map_err(|e| JsValue::from_str(&format!("CONFIG_PARSE_ERROR: {e}")))?;
    self.chinese_phonemizer.set_loanword_data(data);
    Ok(())
}
```

```typescript
// src/wasm/g2p/types/index.d.ts に追加
export interface LoanwordData {
    version: number;
    acronyms: Record<string, string[]>;
    loanwords: Record<string, string[]>;
    letter_fallback: Record<string, string[]>;
}

export class ChineseG2P {
    setLoanwordData(data: LoanwordData): void;
}
```

```javascript
// src/wasm/g2p/src/zh/index.js
import loanwordData from '../../data/zh_en_loanword.json' assert { type: 'json' };

class ChineseG2P {
    setLoanwordData(data) {
        this._loanwordData = data;
        if (this._wasmPhonemizer) {
            const bytes = new TextEncoder().encode(JSON.stringify(data));
            this._wasmPhonemizer.setChineseLoanwordData(bytes);
        }
    }
}
```

**テストフレーム**: 既存の `node:test` (`src/wasm/g2p/test/test-chinese.js` 463 行で使用) を継続。新規ケース ~120 行追加。

### 8.5 Rust crate 重複問題と実装場所決定

**重要発見**: 中国語 phonemizer 実装が **2 箇所に存在**:

```
src/rust/
├── piper-plus-g2p/src/chinese.rs    (1,314 行) — WASM 対応版、crates.io 公開
└── piper-core/src/phonemize/chinese.rs (1,462 行) — non-WASM、ProsodyInfo 統合
```

**依存関係グラフ**:

```
piper-cli       → piper-core
piper-python    → piper-core
piper-wasm      → piper-core + piper-plus-g2p (feature-gated)
piper-core      → piper-plus-g2p (依存先、ただし phonemize は独自実装あり)
piper-plus-g2p  → 独立 (crates.io 公開)
```

**両者の差分**:

| 項目 | `piper-plus-g2p` | `piper-core` |
|------|----------------|--------------|
| WASM 対応 | ✓ (`from_json_bytes()`) | ✗ (`cfg!(not(target_arch = "wasm32"))`) |
| `ProsodyInfo` (a1/a2/a3) | △ (基本のみ) | ✓ 統合 |
| crates.io 公開 | ✓ | ✓ |
| 利用元 | piper-wasm のみ | piper-cli / piper-python / piper-wasm 全て |
| コールドスタート最適化 (#302) | 未適用 | 適用済 |

**結論**: **両方に実装する必要がある**

- **`piper-core/src/phonemize/chinese.rs`**: デスクトップ用 CLI / Python binding が使う、`ProsodyInfo` 統合済 → **ここで主実装**
- **`piper-plus-g2p/src/chinese.rs`**: WASM ビルド時の経路 → **同等実装をミラー** (将来 v0.5.0 で統合予定だが本 PR では並列維持)

**両者を一致させるため**:
- 実装の core ロジック (lookup priority、token tokenize 等) を 1 つの module 化検討 (例: `piper-plus-g2p::chinese::loanword` を `piper-core` から re-export)
- ただし `ProsodyInfo` の差で完全 re-export 困難なら、コミット内で同期確認テストを追加

**推奨アプローチ**:

```
1. piper-core/src/phonemize/chinese.rs に embedded_english_phonemize() を主実装
2. piper-plus-g2p/src/chinese.rs にも同等関数を実装 (WASM 経路用)
3. 両方の実装が同じ JSON データから同じ結果を生むテストを追加
4. v0.5.0 でいずれか統合 (本 PR の Out of Scope)
```

**Rust 工数の修正**: 当初見積 ~400 行 → **~600 行** (2 箇所実装のため +50%)

### 8.6 C++ テストフレーム拡充戦略

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

---

## 9. 改訂履歴

| 日付 | バージョン | 変更内容 | 著者 |
|------|---------|---------|------|
| 2026-05-06 | Draft v1 | 初版作成 (調査結果 + 対応計画) | Claude |
| 2026-05-06 | Draft v2 | 深堀り調査 3 項目追加 (C++ iOS/Android リソース、C# 独立実装、JSON 同期 CI) | Claude |
| 2026-05-06 | Draft v3 | 深堀り調査 3 項目追加 (JS/WASM 二層 FFI、Rust crate 重複問題、C++ テストフレーム拡充) — 重要発見: Rust は 2 箇所実装必要、工数 ~400→~600 行に修正 | Claude |
