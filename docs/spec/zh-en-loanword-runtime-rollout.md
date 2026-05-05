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
| R1 | Rust | `chinese.rs` に `phonemize_embedded_english` 関数追加 | ~150 | 中 |
| R2 | Rust | `LoanwordData` struct + `load_loanword_data()` (schema validation) | ~80 | 低 |
| R3 | Rust | `multilingual.rs` で `[zh,en,*]` パターン dispatch | ~50 | 低 |
| R4 | Rust | `data/zh_en_loanword.json` 同梱 (`include_str!`) | ~5 | 低 |
| R5 | Rust | テスト追加 (unit + integration) | ~120 | 中 |
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

## 8. 改訂履歴

| 日付 | バージョン | 変更内容 | 著者 |
|------|---------|---------|------|
| 2026-05-06 | Draft | 初版作成 (調査結果 + 対応計画) | Claude |
