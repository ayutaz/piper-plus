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

### 8.7 テストデータ統一フォーマット

**問題**: 5 ランタイム × 20 ケース = **100 テスト**を独立に書くと、メンテ時に整合性ずれが起きる。一元管理したい。

**既存パターン**:
- `tests/fixtures/g2p/phoneme_test_cases.json` — Python/Rust/JS 共有 fixture (15+ ケース実例あり)
- `docs/spec/pua-contract.toml` — 6 ランタイム PUA mapping spec
- `scripts/check_pua_consistency.py` — entry-by-entry 比較
- `.github/workflows/g2p-cross-platform-ci.yml` — 全ランタイム同時実行

**推奨**: **共有 JSON fixture + 各ランタイム loader (案 B+D ハイブリッド)** — PUA で実証済みのパターンを踏襲

```json
// tests/fixtures/g2p/zh_en_test_matrix.json (新規)
{
  "version": 1,
  "description": "ZH-EN code-switching test matrix: 20 cases × 5 runtimes",
  "test_matrix": [
    {
      "id": "zh_en_001_basic",
      "category": "basic",
      "input": "请打开 GPS",
      "language": "zh-en",
      "expected_segments": [
        {"type": "zh", "text": "请打开"},
        {"type": "en", "text": "GPS", "loanword_match": "acronym", "expected_syllable_count": 4}
      ],
      "expected_properties": {"all_single_codepoint": true}
    },
    ...
  ]
}
```

**各ランタイム loader (例)**:

```python
# Python: tests/test_zh_en_unified.py
@pytest.mark.parametrize("case", load_matrix())
def test_case(case):
    p = get_phonemizer(case["language"])
    tokens, _ = p.phonemize_with_prosody(case["input"])
    # expected_syllable_count、expected_properties をアサート
```

```rust
// Rust: piper-plus-g2p/tests/test_zh_en_unified.rs
#[test]
fn test_zh_en_matrix() {
    let matrix: Vec<TestCase> = load_fixture(".../zh_en_test_matrix.json");
    for case in matrix { run_case(&case); }
}
```

**新規 CI ジョブ**:

```yaml
# .github/workflows/zh-en-cross-platform-ci.yml
zh-en-cross-platform:
  steps:
    - name: Python ZH-EN tests
    - name: Rust ZH-EN tests (cargo test)
    - name: JS/WASM ZH-EN tests (node:test)
    - name: Cross-runtime IPA comparison
      run: python scripts/compare_zh_en_outputs.py
```

**工数見積**: Fixture JSON 4h + 各ランタイム loader (5 × 2h) + CI 統合 3h = **~17h** (一度切り)、将来 case 追加は **+1h/case**

### 8.8 Multilingual Dispatcher のエッジケース動作確定

**確定したエッジケース動作テーブル** (Python 現状実装ベース):

| ケース | 入力例 | セグメント | 動作 | テスト要否 |
|--------|-------|----------|-----|----------|
| A | `你好 Hello 世界` | `[zh,en,zh]` | embedded | ✓ 既存 |
| B | `请打开 GPS` | `[zh,en]` | embedded | ✓ 既存 |
| C | `GPS 在哪里` | `[en,zh]` | embedded | ✓ 既存 |
| D | `Hello world` | `[en]` | English path | ✓ 既存 |
| E | `こんにちは Hello 北京` | `[ja,en,zh]`* | **English path** (kana で zh が ja 化) | ⚠ 新規必須 |
| F | `你好 Hello World 世界` | `[zh,en,zh]`** | embedded (連続 en は 1 segment 化) | ⚠ 新規 |
| G | `你好 English 日本` | `[zh,en,ja]` | **English path** (next が ja) | ⚠ 新規必須 |
| H | `日本 English 日本` | `[ja,en,ja]` (kana ctx) | English path | ⚠ 新規 |
| I | `UsB` | `[en]` (1 token) | letter_fallback | - |
| J | `请 GPS USB 打开` | `[zh,en,zh]`** (連続 en 統合) | embedded (両 token) | ⚠ 新規 |
| K | `123` のみ | `[en]` (default fallback) | English fallback | ✓ 既存 |
| L | `http://test.com` | `[en]` (1 segment) | English path | ⚠ 新規 |
| M | `Ｐｙｔｈｏｎ` (全角英数) | `[en]` | English/embedded | ⚠ 新規 |
| N | `A/B` (スラッシュ) | `[en]` (neutral 吸収) | letter_fallback | ⚠ 新規 |

*\* CJK + kana 干渉**: `UnicodeLanguageDetector.detect_char` の規則で `kana ありの場合 CJK は ja 化`。**結果として ja-en-zh modeでは zh segment が出ず、embedded path 不発動**。これは設計上の制約として明記。

**\*\* 連続 en の neutral 吸収**: `_segment_text_multilingual` は空白を直前言語に absorption するため `Hello World` は 1 segment。

**dispatch decision tree (各ランタイム共通)**:

```
IF current_lang == "en" AND zh ∈ supported_languages:
    prev_is_zh = i > 0 AND segments[i-1].lang == "zh"
    next_is_zh = i+1 < len AND segments[i+1].lang == "zh"
    IF prev_is_zh OR next_is_zh:
        → embedded_english_path
    ELSE:
        → english_phonemizer_path
ELSE:
    → get_phonemizer(current_lang)
```

**設計上の制約 (明示すべき)**:

> ja-en-zh のように **kana を含む 3 言語 mode** では、kana の存在で CJK 全体が ja 化するため、zh セグメントが生成されず embedded English の dispatch が発動しない。これは現状の `UnicodeLanguageDetector` の仕様に従う動作で、本 PR では **変更しない**。将来的に解決するなら段落単位の kana スキャン or 言語切替トークン (issue A3) が必要。

**新規必須テスト** (各ランタイムで実装):
- E: ja-en-zh で kana 化を確認
- G: zh-en-ja で next が ja の時に English path
- L: URL は drop されず English path
- M: 全角英数の挙動

### 8.9 エラーハンドリング統一仕様

**メッセージテンプレート統一**:

```
{path}: '{section}.{key}' must be list[str], got {actual_type}
```

**各ランタイムのエラー型対応**:

| ランタイム | エラー型 | 例 |
|-----------|---------|-----|
| Python | `ValueError` | 既存実装どおり |
| Rust | `G2pError::LoanwordSchema { .. }` (`thiserror` 拡張) | `Err(G2pError::LoanwordSchema { path, section, key })` |
| Go | wrapped `error` (`fmt.Errorf("%w", ...)`) | `return fmt.Errorf("zh-en loanword: '%s.%s' must be list[str]: %w", ...)` |
| C# | `FormatException` | `throw new FormatException($"zh-en loanword: '{section}.{key}' must be list[str], got {valueType}")` |
| JS/WASM | `Error` with `code='SCHEMA_ERROR'` | Rust 側 `JsValue::from_str("SCHEMA_ERROR: ...")` |
| C++ | `PiperPlusStatus` enum + thread-local message | 新規 `PIPER_PLUS_ERR_LOANWORD_SCHEMA = -7` |

**ケース別の挙動統一**:

| ケース | 全ランタイム共通の挙動 |
|-------|---------------------|
| **default file 欠損** | warning ログ + 空辞書 fallback (silent degrade) |
| **override file 欠損** | error / 例外 (呼び出し側に明示) |
| **malformed JSON** | error / 例外 (parse error wrap) |
| **schema violation** | error / 例外 (パス + 違反箇所を含むメッセージ) |
| **空 sections** | OK (空辞書として扱う) |

**C API 拡張**:

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

**ログレベルガイドライン**:

| 状況 | ログレベル |
|------|----------|
| default file 欠損 | warning |
| override file 欠損 | warning |
| 空セクション | debug |
| 正常ロード成功 | debug |
| schema violation | (例外メッセージで十分、log 不要) |

---

### 8.10 Go の `//go:embed` + JSON tag 戦略

**既存パターン**: 現状 `src/go/` 配下で `//go:embed` 使用例なし (全て外部ファイル参照)。`custom_dict.go` で `encoding/json` + `json:""` tag による snake_case → CamelCase mapping は確立。

**推奨**:

```
src/go/phonemize/
├── data/
│   └── zh_en_loanword.json    ← Python から copy
├── loanword.go                 ← embed + struct + sync.Once
└── loanword_test.go
```

**実装スケッチ**:

```go
package phonemize

import (
    "embed"
    "encoding/json"
    "fmt"
    "sync"
)

//go:embed data/zh_en_loanword.json
var loanwordFS embed.FS

type LoanwordData struct {
    Version        int                 `json:"version"`
    Acronyms       map[string][]string `json:"acronyms"`
    Loanwords      map[string][]string `json:"loanwords"`
    LetterFallback map[string][]string `json:"letter_fallback"`
}

var (
    loanwordOnce sync.Once
    loanwordData *LoanwordData
    loanwordErr  error
)

func LoadLoanwordData() (*LoanwordData, error) {
    loanwordOnce.Do(func() {
        data, err := loanwordFS.ReadFile("data/zh_en_loanword.json")
        if err != nil {
            loanwordErr = fmt.Errorf("read embedded loanword data: %w", err)
            return
        }
        ld := &LoanwordData{}
        if err := json.Unmarshal(data, ld); err != nil {
            loanwordErr = fmt.Errorf("parse loanword JSON: %w", err)
            return
        }
        if err := ld.Validate(); err != nil {
            loanwordErr = fmt.Errorf("validate loanword data: %w", err)
            return
        }
        loanwordData = ld
    })
    return loanwordData, loanwordErr
}

func (ld *LoanwordData) Validate() error {
    if ld.Version < 1 {
        return fmt.Errorf("invalid loanword version: %d", ld.Version)
    }
    for section, m := range map[string]map[string][]string{
        "acronyms":        ld.Acronyms,
        "loanwords":       ld.Loanwords,
        "letter_fallback": ld.LetterFallback,
    } {
        for k, v := range m {
            if len(v) == 0 {
                return fmt.Errorf("'%s.%s' must be non-empty list[str]", section, k)
            }
        }
    }
    return nil
}
```

**設計判断**:

| 項目 | 採用 | 理由 |
|------|-----|------|
| `embed.FS` (vs `[]byte`) | ✓ | バイナリサイズ同等、型安全、拡張性 |
| `sync.Once` lazy load | ✓ | init() オーバーヘッド回避、エラー処理明示 |
| `json:""` snake_case tag | ✓ | 既存 `custom_dict.go` 慣例 |
| `Validate()` メソッド | ✓ | schema 整合性、早期エラー検出 |
| `fmt.Errorf("%w", err)` wrap | ✓ | 既存コード慣習、エラーチェーン |

### 8.11 リリース戦略

**現状バージョン**:

| Registry | パッケージ | 現行版 | 推奨 bump | bump 後 |
|----------|----------|-------|---------|--------|
| PyPI | `piper-plus-g2p` | 0.2.0 | minor | **0.3.0** |
| crates.io | `piper-plus`, `piper-plus-g2p`, `piper-plus-cli` | 0.4.0 | minor | **0.5.0** |
| NuGet | `PiperPlus.Core`, `PiperPlus.Cli` | 0.3.0 | minor | **0.4.0** |
| npm | `@piper-plus/g2p` | 0.4.0 | minor | **0.5.0** |
| Go module | tag-based | latest | リポジトリ tag | **v1.13.0** |
| C API | `libpiper_plus` | v1.13.0+ | リリースタグ連動 | **v1.13.0** |

**全ランタイム共通: minor bump** (新規 API 追加、breaking change なし)

**配信順序の依存関係**:

```
1. CHANGELOG 更新 (リポジトリルート + src/python/g2p/)
2. Rust crates.io   (cargo publish: g2p → core → cli の順)
3. git tag push     (Go module 自動解決 + release-shared-lib.yml 自動実行)
4. npm registry     (Rust 0.5.0 完了待ち)
5. PyPI             (piper-plus-g2p 0.3.0)
6. NuGet            (PiperPlus.Core/Cli 0.4.0、手動 dotnet nuget push)
7. GitHub Release 確認 (Package.swift checksum 検証済み)
```

**チェックリスト** (PR マージ後):

- [ ] CHANGELOG.md (root) [Unreleased] → [0.5.0] / [Date] に bump
- [ ] src/python/g2p/CHANGELOG.md [Unreleased] → [0.3.0]
- [ ] src/rust/Cargo.toml workspace version → 0.5.0
- [ ] src/csharp/*.csproj Version → 0.4.0
- [ ] src/wasm/g2p/package.json version → 0.5.0
- [ ] `cargo publish` (3 crates、依存順)
- [ ] `git tag v1.13.0 && git push --tags` (Go module + GitHub Release 自動)
- [ ] `npm publish` (Rust crates 完了後)
- [ ] `pip install piper-plus-g2p==0.3.0` で動作確認
- [ ] `dotnet nuget push PiperPlus.Core.0.4.0.nupkg`
- [ ] Package.swift checksum 自動検証 (CI 出力確認)

**Migration guide**: **不要** (新機能のみ、既存 API 非変更)。各 README の "What's New" セクションに記載で十分。

**リリース時間目安**: マニュアル工程 5-10 分 (cargo publish ~3 分 + npm publish ~1 分 + pip publish ~2 分 + dotnet nuget push ~2 分、並列可)

### 8.12 後方互換性戦略

**Breaking change 評価**: **なし** (詳細分析済)

| 既存ユースケース | 影響 | 対策 |
|----------------|------|------|
| ZH のみ使用 | ✓ なし | 設定不要、既存挙動維持 |
| EN のみ使用 | ✓ なし | 設定不要、既存挙動維持 |
| ZH-EN mixed (新機能歓迎) | ✓ 改善 | デフォルト有効 |
| ZH-EN mixed (英語発音維持希望) | ⚠ 影響あり | **opt-out flag が必要** |

**Python (PR #397) で確認済み**:
- `test_multilingual_pure_zh_unaffected`: 純 ZH は同一出力 ✓
- `test_multilingual_pure_english_uses_english_path`: 純 EN は EnglishPhonemizer 経路 ✓
- 既存 g2p テスト 791 件全 PASS、リグレッションなし

**opt-out flag 設計**:

各ランタイムに `enable_zh_en_dispatch` (default `True`) を追加し、既存ユーザーが旧挙動 (英語発音) を維持できる経路を提供する:

```python
# Python
MultilingualPhonemizer(
    languages=["zh", "en"],
    default_latin_language="en",
    enable_zh_en_dispatch=True,        # NEW: opt-out 用 flag (default ON)
    zh_en_loanword_dict_paths=None,    # NEW: カスタム辞書
)
```

```rust
// Rust
MultilingualPhonemizer::builder()
    .languages(vec!["zh", "en"])
    .enable_zh_en_dispatch(true)       // NEW: builder pattern 推奨
    .build()
```

```go
// Go
func NewMultilingualPhonemizer(opts ...Option) *MultilingualPhonemizer
WithZhEnDispatch(enabled bool) Option   // NEW: functional options
```

```csharp
// C#
new MultilingualPhonemizer(
    languages: new[] { "zh", "en" },
    enableZhEnDispatch: true            // NEW
);
```

```typescript
// TypeScript
new G2P({ languages: ["zh", "en"], enableZhEnDispatch: true })
```

**Phase 戦略**:

| Phase | 内容 | 期間 |
|-------|------|------|
| **Phase 1 (本 PR)** | 全ランタイムに default-on で機能展開、opt-out flag は Python のみ追加 (リファレンス) | 本 PR |
| **Phase 2** | 各ランタイムに opt-out flag 追加 (互換性 100% 保証) | フォローアップ |
| **Phase 3** | Beta 期間 (1 minor version) でフィードバック収集 | 1-2 ヶ月 |

**API ドキュメント更新ガイドライン**:

```markdown
#### ZH-EN Code-Switching (v0.5.0+)

MultilingualPhonemizer で中国語に隣接する英単語を自動検出し、
英語発音ではなく Mandarin pinyin で発音します。

例:
  p.phonemize("请打开 GPS")
    → GPS = "ji4 pi4 ai1 si4" (pinyin via tone markers)

カスタマイズ:
  - 無効化: enable_zh_en_dispatch=False
  - カスタム辞書: zh_en_loanword_dict_paths=[Path("my_dict.json")]
```

**将来機能との API 整合性**:

| Phase | 機能 | API 追加 | 既存影響 |
|-------|------|---------|--------|
| A1 (本 PR) | ZH-EN code-switching | `enable_zh_en_dispatch` | なし |
| A2 | プロソディ平滑化 | `prosody_smooth=True` | 独立 |
| A3 | 言語切替トークン | `insert_language_tags=True` | 独立 |
| B | Fine-tuning コーパス | (新規パイプライン) | 独立 |

設計原則: **新規機能は opt-in flag で統一、既存 API 非修飾**。

---

### 8.13 パフォーマンス・ベンチマーク戦略

**目標値**:

| 項目 | 目標 |
|------|------|
| 1 token あたりの latency | **< 100 μs** |
| `phonemize_chinese` 全体への増分 | **< 5%** |
| WASM バンドルサイズ増加 | **+2-5 KB** (gzip 後) |
| メモリ固定オーバーヘッド | **< 100 KB** (3 辞書合計) |

**ホットパス分析** (Python ベース、1 token "GPS"):

```
tokenize (re.findall)        ~1 μs
loanword lookup (dict miss)  ~0.5 μs
acronym lookup (dict hit)    ~0.5 μs
pinyin → IPA (4 syllables)   ~30 μs
prosody build                ~5 μs
─────────────────────────────────────
Total                        ~37 μs/token  ← 目標 100μs 内
```

**各ランタイムのベンチマーク実装**:

| ランタイム | フレーム | ファイル |
|-----------|--------|--------|
| Python | `time.perf_counter()` | `src/python/g2p/benchmarks/bench_zh_en.py` |
| Rust | `criterion` | `src/rust/piper-plus-g2p/benches/bench_chinese_embedded.rs` |
| Go | `testing.B` | `src/go/phonemize/bench_test.go` |
| C# | `BenchmarkDotNet` | `src/csharp/PiperPlus.Benchmarks/ChineseEmbeddedEnglishBench.cs` |
| C++ | Google Benchmark | `src/cpp/benchmarks/bench_chinese_embedded.cpp` |
| JS/WASM | `mitata` | `src/wasm/g2p/bench/bench-zh-en.js` |

**キャッシュ戦略 (全ランタイム共通)**: app lifetime 中 1 回のみロード
- Python: `@functools.cache` (実装済)
- Rust: `OnceLock` / `LazyLock`
- Go: `sync.Once` (8.10 で確定)
- C#: static field + lazy init
- C++: C++11 magic statics + `std::call_once`
- WASM: JS の `setChineseLoanwordData()` で 1 回注入

**新規 CI ジョブ**:

```yaml
# .github/workflows/g2p-phonemize-perf.yml
name: G2P Phonemize Performance
on: [pull_request]
jobs:
  benchmark:
    strategy:
      matrix:
        runtime: [python, rust, go, csharp, wasm]
    steps:
      - run: # ランタイム毎の bench コマンド
      - name: Latency regression check
        run: # < 100 μs 検証
```

**工数**: ベンチ実装 ~3-4 日、CI 統合 ~1 日 = **~5 日**

### 8.14 C++ Thread Safety

**既存実装の評価**:

| 既存箇所 | 状態 | 根拠 |
|---------|------|------|
| `english_phonemize.cpp:74-117` の static テーブル | ✅ Thread-safe | C++11 magic statics |
| `piper_plus_c_api.cpp:45` の `thread_local g_last_error` | ✅ Thread-safe | thread-local 保証 |
| `Voice` 構造体の dict (`pinyinSingleDict` 等) | ⚠️ 部分的 | 同一 engine を複数スレッドが共有する場合は要対策 |

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

### 8.15 CI ジョブ整合性

**既存 CI 構成**: 41 workflow、`ci-required` が branch protection 必須

**本 PR の CI 影響見積**:

| Workflow | 現行 | 追加 | 新計 | 備考 |
|---------|------|------|------|------|
| python-lint | 2 分 | +10 秒 | 2:10 | ruff format (新ファイル) |
| python-tests | 7 分 | +45 秒 | 7:45 | 3 OS × 3 Python、pytest +35 ケース |
| g2p-cross-platform | 20 分 | +2 分 | 22 分 | JSON 同期 step + ZH-EN 検証 |
| Rust tests | (matrix) | +1-2 分 | — | cargo test +20 ケース |
| Go tests | — | +30 秒 | — | go test +20 ケース |
| C# tests | (matrix) | +30 秒 | — | xUnit +20 ケース |
| WASM tests | — | +30 秒 | — | node:test +20 ケース |
| C++ tests | (matrix) | +1 分 | — | gtest +20 ケース |
| **PR 全体 (critical path)** | **~28 分** | **+2 分** | **~30 分** | 並列実行で許容範囲 |

**新規 CI ジョブ**: `zh-en-loanword-sync.yml`

```yaml
name: ZH-EN Loanword Sync
on:
  pull_request:
    paths:
      - '**/zh_en_loanword.json'
jobs:
  json-sync:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v6
      - name: Verify all 6 copies match (sha256)
        run: |
          SOURCE=src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
          HASH=$(sha256sum "$SOURCE" | cut -d' ' -f1)
          for copy in \
            src/python_run/piper/phonemize/data/zh_en_loanword.json \
            src/rust/piper-plus-g2p/data/zh_en_loanword.json \
            src/go/phonemize/data/zh_en_loanword.json \
            src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json \
            src/wasm/g2p/data/zh_en_loanword.json \
            src/cpp/data/zh_en_loanword.json; do
            [ -f "$copy" ] || { echo "MISSING: $copy"; exit 1; }
            COPY_HASH=$(sha256sum "$copy" | cut -d' ' -f1)
            [ "$HASH" = "$COPY_HASH" ] || { echo "MISMATCH: $copy"; exit 1; }
          done
      - name: Schema validation (Python)
        run: |
          python3 -c "
          import json
          with open('src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json') as f:
              d = json.load(f)
          for s in ('acronyms','loanwords','letter_fallback'):
              assert isinstance(d[s], dict), f'{s} must be dict'
              for k, v in d[s].items():
                  assert isinstance(v, list) and all(isinstance(e,str) for e in v), \
                      f'{s}.{k} must be list[str]'
          print(f'✓ {len(d[\"acronyms\"])} acronyms, {len(d[\"loanwords\"])} loanwords, {len(d[\"letter_fallback\"])} letters')
          "
```

**`ci-required` への追加**: `needs: [zh-en-loanword-sync, ...]`

**CI 失敗時の切り分け**:

```
JSON hash mismatch    → 6 copy のいずれかを編集し忘れ
Schema fail          → loanword.json が malformed
{lang}-tests fail    → 各ランタイム実装ロジック問題
g2p-cross-platform   → ランタイム間で出力が分岐
zh-en-loanword-sync  → JSON 同期忘れ (gate)
```

---

### 8.16 メモリ管理戦略

**各ランタイムの推奨パターン**:

| ランタイム | 推奨 lifecycle | 共有方式 | IDisposable |
|-----------|--------------|--------|-----------|
| Rust | `OnceLock<Arc<LoanwordData>>` | `Arc::clone()` で zero-copy 共有 | — |
| Go | package-level `sync.Once` + global var | immutable design、各 instance が参照 | — |
| C# | `static Lazy<LoanwordData>` | thread-safe 自動共有 | **不要** (managed dict のみ) |
| C++ | `std::shared_ptr<const LoanwordData>` | factory 関数で reference 増加 | — |
| WASM/JS | Rust 側で byte copy → 内部保持 | JS 側からは fire-and-forget | — |

**実装スケッチ**:

```rust
// Rust: 推奨パターン
static BUILTIN_LOANWORD: OnceLock<Arc<LoanwordData>> = OnceLock::new();

pub fn default_loanword_data() -> Arc<LoanwordData> {
    Arc::clone(BUILTIN_LOANWORD.get_or_init(|| {
        Arc::new(load_and_validate_default())
    }))
}

// 複数 ChinesePhonemizer インスタンスで共有
let phonemizer1 = ChinesePhonemizer::new(default_loanword_data());
let phonemizer2 = ChinesePhonemizer::new(default_loanword_data());
// → 内部 Arc<LoanwordData> は同一 (zero-copy 共有)
```

```csharp
// C#: 推奨パターン
public class ChinesePhonemizer {
    private static readonly Lazy<LoanwordData> s_default =
        new(() => LoanwordDataLoader.LoadDefault(), LazyThreadSafetyMode.ExecutionAndPublication);
    
    public ChinesePhonemizer(string? customPath = null) {
        _data = customPath == null ? s_default.Value : LoadAndMerge(customPath);
    }
}
// → IDisposable 不要 (LoanwordData は managed のみ、GC で解放)
```

**カスタム辞書のメモリ overhead**:

- default + override マージ後は **インスタンス毎に独立コピー** (~10-50 KB/インスタンス)
- 実用上は server プロセスで 1-2 個程度なので問題なし
- 大量インスタンス生成シナリオ (test 等) では LRU cache の実装余地あり (Phase 2)

**メモリ overhead 見積**:

```
LoanwordData (default):
  acronyms (65)        ~3 KB
  loanwords (40)       ~2 KB
  letter_fallback (26) ~1 KB
  ───────────────────────
  Total                ~6 KB (struct 化後 ~20 KB)
```

100 インスタンス共有でも default は 1 つだけ → **総メモリ ~20 KB** (Arc 共有の効果)

### 8.17 i18n / 多言語ペア拡張性

**現状**: ZH-EN のみ対応。将来 JA-EN / KO-EN / ES-EN 等に拡張する可能性。

**3 段階拡張ロードマップ**:

| Phase | 対象 | ファイル構成 | スキーマ |
|-------|-----|-----------|---------|
| **本 PR (現在)** | ZH-EN | `data/zh_en_loanword.json` | v1 (現行) |
| **6 ヶ月後 (フォローアップ)** | JA-EN 等追加 | `data/loanword/{src}_{tgt}.json` | v1 (構造同一) |
| **2 年後+ (必要なら)** | 多ペア統合 | `data/loanword.json` (`pairs: { ... }`) | v2 (構造変更) |

**推奨**: **Phase 1 (本 PR) は現状の `zh_en_loanword.json` 維持**、Phase 2 で必要に応じて `data/loanword/` ディレクトリ化

**スキーマに `language_pair` field 追加 (任意、Phase 2 で必須化)**:

```json
{
  "version": 1,
  "language_pair": "zh-en",        // ← 推奨: 早期に追加 (option)
  "description": "...",
  "acronyms": { ... },
  "loanwords": { ... },
  "letter_fallback": { ... }
}
```

**既存 `swedish.py` の `loanword_suffix` との概念衝突**: なし (スウェーデン語の loanword は外来語の発音規則、本機能は外来語 → 中国語発音、スコープが異なる)

**他言語処理の現状**:

| 言語 | 現状 | 同種機能の必要性 |
|------|------|-----------------|
| 日本語 (ja) | OpenJTalk が外来語 (カタカナ) を自動処理 | 個別の英単語埋め込み辞書あれば改善余地 (将来課題) |
| 韓国語 (ko) | g2pk2 + Hangul 分解 | 英単語特別処理なし、JA-EN 同様 (将来課題) |
| ES/PT/FR/SV | 規則ベース | 各言語で同様の loanword 辞書を作る余地あり |

### 8.18 セキュリティ考慮事項

**脅威モデル**:

| 脅威 | 影響 | 緩和策 |
|------|------|--------|
| 巨大 JSON (DoS) | メモリ枯渇 | サイズ上限 **1 MB** |
| ネスト過深 (parser DoS) | stack overflow | depth 制限 **100** |
| symbolic link (path traversal) | ファイル領域外アクセス | `resolve()` + warning log |
| 大量エントリ (10K+) | hash table 巨大化 | エントリ数上限 **10,000** |
| 不正な pinyin syllable | IPA 変換失敗 | schema validation (8.9 で対応済) |
| PUA codepoint 注入 | token encoding 破損 | input sanitization |

**既存パターンの踏襲**: `custom_dict.py:13` の `MAX_DICT_FILE_SIZE = 10 * 1024 * 1024` (10 MB) と同等のガードを zh_en_loanword にも適用。

**推奨ガード値**:

```python
# 全ランタイム共通仕様
MAX_LOANWORD_FILE_SIZE = 1 * 1024 * 1024   # 1 MB (default JSON は ~6 KB)
MAX_LOANWORD_ENTRIES = 10_000               # default 合計 ~131 entries
MAX_LOANWORD_DEPTH = 100                    # default 最深 3 層
```

**各ランタイム JSON parser 安全性**:

| ランタイム | デフォルト nest 制限 | 追加対策 |
|-----------|------------------|---------|
| Python `json` | 1,000 | サイズ check |
| Rust `serde_json` | 安全 | サイズ check |
| Go `encoding/json` | 10,000 | `io.LimitReader` でサイズ check |
| C# `System.Text.Json` | 64 | `JsonSerializerOptions.MaxDepth` 設定 |
| C++ `nlohmann/json` | **無制限** ⚠️ | recursion 制限を明示的に設定 |
| JS `JSON.parse` | stack-based | サイズ check + try/catch |

**実装スケッチ (Python 共通モジュール案)**:

```python
def _safe_load_json(
    path: str,
    *,
    max_size_bytes: int = MAX_LOANWORD_FILE_SIZE,
    max_entries: int = MAX_LOANWORD_ENTRIES,
) -> dict:
    p = Path(path).resolve()
    if str(p) != str(Path(path).absolute()):
        _LOGGER.warning("Path resolved via symlink: %s -> %s", path, p)
    size = p.stat().st_size
    if size > max_size_bytes:
        raise ValueError(f"{path}: file too large: {size} > {max_size_bytes}")
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    total = sum(len(data.get(s, {})) for s in ("acronyms","loanwords","letter_fallback"))
    if total > max_entries:
        raise ValueError(f"{path}: too many entries: {total} > {max_entries}")
    return data
```

**`custom_dict.py` の既存パターンとの共通化**:

将来 `_safe_load_json` を共通モジュール化検討 (Phase 2)。本 PR では各ランタイムで個別実装。

**実装優先度**:

| Tier | 項目 | 必須度 |
|------|------|--------|
| Tier 1 (本 PR) | サイズ上限、symbolic link 警告、schema validation | **必須** |
| Tier 2 (本 PR) | エントリ数上限、JSON depth 制限 | **必須** |
| Tier 3 (フォローアップ) | 共通 `_safe_load_json` モジュール化 | 任意 |

---

## 9. 改訂履歴

| 日付 | バージョン | 変更内容 | 著者 |
|------|---------|---------|------|
| 2026-05-06 | Draft v1 | 初版作成 (調査結果 + 対応計画) | Claude |
| 2026-05-06 | Draft v2 | 深堀り 3 項目追加 (C++ iOS/Android リソース、C# 独立実装、JSON 同期 CI) | Claude |
| 2026-05-06 | Draft v3 | 深堀り 3 項目追加 (JS/WASM 二層 FFI、Rust crate 重複、C++ テストフレーム) — Rust 2 箇所実装必要 | Claude |
| 2026-05-06 | Draft v4 | 深堀り 3 項目追加 (テストデータ統一、dispatcher エッジケース、エラーハンドリング統一) | Claude |
| 2026-05-06 | Draft v5 | 深堀り 3 項目追加 (Go embed/JSON tag、リリース戦略、後方互換性 + opt-out flag) — 計 12 項目で実装フェーズ移行可能 | Claude |
| 2026-05-07 | Draft v6 | 深堀り 3 項目追加 (パフォーマンス目標 <100μs、C++ thread safety with shared_ptr<const>、CI ジョブ整合性 +2分) | Claude |
| 2026-05-07 | Draft v7 | 深堀り 3 項目追加 (メモリ管理: Arc/Lazy/shared_ptr、i18n 拡張: data/loanword/ ディレクトリ化、セキュリティ: 1MB/10K entry/depth 100 のガード) | Claude |
