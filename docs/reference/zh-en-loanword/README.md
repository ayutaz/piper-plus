# ZH-EN Code-Switching: 全ランタイム展開設計書

**ステータス**: Implemented (Issue #384, PR #399 / dev に merge 済み)
**前提 PR**: [#397](https://github.com/ayutaz/piper-plus/pull/397) (Python 学習側 + Python ランタイム側)
**親 Issue**: [#384](https://github.com/ayutaz/piper-plus/issues/384) (Out of Scope で予告された全ランタイム同期実装)

> **注**: 本書は実装着手前の調査・設計記録。ロードマップ (タスク表 / ブランチ戦略 / Day 1-14 計画) と改訂履歴は実装完了に伴い削除済み (詳細は git log)。残置されているのは設計判断の根拠・運用 SOP・将来拡張の参考として価値あるセクションのみ。

---

## 1. 背景

PR #397 で **Python (学習側 + ランタイム側)** の ZH-EN code-switching が実装された:

- 中国語コンテキスト中の英単語 (acronym/loanword) を Mandarin pinyin で発音
- 辞書: `acronyms` 66, `loanwords` 40, `letter_fallback` 26 (A-Z)
- `MultilingualPhonemizer` が `[zh,en,zh] / [zh,en] / [en,zh]` パターンを検出して dispatch
- 学習側 + Python ランタイム両方で同等動作

しかし、**他 5 ランタイム (Rust / Go / C# / JS-WASM / C++) は未対応**。実プロダクト環境 (iOS / Android / Unity / Web / CLI) は Python 以外を主に使うため、本機能の効果が見えず、機能ギャップが発生している。

本書は **5 ランタイム同時展開** (1 ブランチ / 1 PR) のための調査結果と対応計画をまとめる。

---

## 2. 各ランタイム別設計書

Python (canonical) が main source of truth で、他 5 ランタイムが Python からの byte-for-byte 同期で動作する構造。各ランタイム固有の設計判断・制約は以下を参照:

| ランタイム | ファイル | 概要 |
|-----------|---------|------|
| **Python (canonical)** | [`python.md`](python.md) | source of truth、後方互換性戦略、JSON 同期 CI 戦略、データセット拡張運用フロー |
| **Rust** | [`rust.md`](rust.md) | 2 crate (`piper-plus-g2p` + `piper-core`) 並列実装、`Arc<LoanwordData>` 共有 |
| **Go** | [`go.md`](go.md) | `//go:embed` + `sync.Once` lazy load、`encoding/json` tag |
| **C#** | [`csharp.md`](csharp.md) | `DotNetG2P.Chinese` NuGet 制約、独立 pinyin→IPA 実装、`EmbeddedResource` |
| **JS/WASM** | [`wasm.md`](wasm.md) | 二層 FFI 設計 (JS bundle + Rust 注入)、WASM サイズ最適化 |
| **C++** | [`cpp.md`](cpp.md) | iOS/Android リソース同梱、xxd 代替、thread safety、テストフレーム拡充 |

---

## 3. 共通の実装パターン

全ランタイムで **同一の 4 ステップ**:

```text
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

```text
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

## 4. 横断的な設計課題

> ランタイム別の実装タスク表 (R1-R5 / G1-G5 / C1-C4 / W1-W5 / P1-P6) は git log と PR #399 / #392 / #393 / #394 / #395 / #396 に履歴を引き継ぎ、本書からは削除した。

### 4.1 横断的な課題

| # | 課題 | 詳細 | 対応方針 |
|---|------|------|---------|
| X1 | **Source of truth の JSON 同期** | **7 箇所**に同じ JSON が分散する (Python 学習 / Python ランタイム / Rust 2 crate (`piper-plus-g2p` + `piper-core`) / Go / C# / WASM-data / C++) | CI 同期ガードを各ランタイムで追加、git pre-commit hook 検討 |
| X2 | **PUA mapping の一貫性** | 中国語 PUA codepoint (0xE020-0xE04A) が全ランタイムで同じ tone marker を出すか確認 | 既存の `docs/spec/pua-contract.toml` で担保済み、新規追加なし |
| X3 | **Schema validation の方針統一** | Python 側の `_load_loanword_data` は厳格 validation (list[str] 型チェック)。各ランタイムで同等のエラーメッセージ形式を出す | `f"{path}: '{section}.{key}' must be list[str]"` 形式を標準化 |
| X4 | **テストケースの統一** | Issue 例 3 つ + 各 priority/punctuation/digits ケースを全ランタイムでカバー | 統一テストマトリックス (後述) |
| X5 | **同期 CI ジョブ** | 6 JSON が一致しているかの byte-for-byte 比較 CI | 既存 `python-tests` workflow に拡張 or 新規 `zh-en-loanword-sync` job |
| X6 | **C++ iOS/Android リソース** | xcframework / aar に JSON を含める手段の確立 | `cmake/PrivacyInfo.xcprivacy` と同パターンで JSON を bundle |
| X7 | **C# DotNetG2P.Chinese 制約** | NuGet 外部ライブラリは改修不可、独立 pinyin→IPA を C# に実装 | Python の `pinyin_to_ipa` を C# に移植 (~200 行) |
| X8 | **JS/WASM の二層** | JS 側と Rust 側どちらに loanword ロジックを置くか | **Rust 側に集約**、JS は FFI 薄ラッパに留める |

### 4.2 統一テストマトリックス

各ランタイムで以下を網羅:

```text
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

### 4.3 Multilingual Dispatcher のエッジケース動作

**確定したエッジケース動作テーブル** (Python 現状実装ベース):

| ケース | 入力例 | セグメント | 動作 | テスト要否 |
|--------|-------|----------|-----|----------|
| A | `你好 Hello 世界` | `[zh,en,zh]` | embedded | 既存 |
| B | `请打开 GPS` | `[zh,en]` | embedded | 既存 |
| C | `GPS 在哪里` | `[en,zh]` | embedded | 既存 |
| D | `Hello world` | `[en]` | English path | 既存 |
| E | `こんにちは Hello 北京` | `[ja,en,zh]`* | **English path** (kana で zh が ja 化) | 新規必須 |
| F | `你好 Hello World 世界` | `[zh,en,zh]`** | embedded (連続 en は 1 segment 化) | 新規 |
| G | `你好 English 日本` | `[zh,en,ja]` | **English path** (next が ja) | 新規必須 |
| H | `日本 English 日本` | `[ja,en,ja]` (kana ctx) | English path | 新規 |
| I | `UsB` | `[en]` (1 token) | letter_fallback | - |
| J | `请 GPS USB 打开` | `[zh,en,zh]`** (連続 en 統合) | embedded (両 token) | 新規 |
| K | `123` のみ | `[en]` (default fallback) | English fallback | 既存 |
| L | `http://test.com` | `[en]` (1 segment) | English path | 新規 |
| M | `Ｐｙｔｈｏｎ` (全角英数) | `[en]` | English/embedded | 新規 |
| N | `A/B` (スラッシュ) | `[en]` (neutral 吸収) | letter_fallback | 新規 |

*\* CJK + kana 干渉**: `UnicodeLanguageDetector.detect_char` の規則で `kana ありの場合 CJK は ja 化`。**結果として ja-en-zh modeでは zh segment が出ず、embedded path 不発動**。これは設計上の制約として明記。

**\*\* 連続 en の neutral 吸収**: `_segment_text_multilingual` は空白を直前言語に absorption するため `Hello World` は 1 segment。

**dispatch decision tree (各ランタイム共通)**:

```text
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

### 4.4 エラーハンドリング統一仕様

**メッセージテンプレート統一**:

```text
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

### 4.5 テストデータ統一フォーマット

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
    }
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

### 4.6 パフォーマンス・ベンチマーク戦略

**目標値**:

| 項目 | 目標 |
|------|------|
| 1 token あたりの latency | **< 100 μs** |
| `phonemize_chinese` 全体への増分 | **< 5%** |
| WASM バンドルサイズ増加 | **+2-5 KB** (gzip 後) |
| メモリ固定オーバーヘッド | **< 100 KB** (3 辞書合計) |

**ホットパス分析** (Python ベース、1 token "GPS"):

```text
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
- Go: `sync.Once`
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

### 4.7 メモリ管理戦略

**各ランタイムの推奨パターン**:

| ランタイム | 推奨 lifecycle | 共有方式 | IDisposable |
|-----------|--------------|--------|-----------|
| Rust | `OnceLock<Arc<LoanwordData>>` | `Arc::clone()` で zero-copy 共有 | — |
| Go | package-level `sync.Once` + global var | immutable design、各 instance が参照 | — |
| C# | `static Lazy<LoanwordData>` | thread-safe 自動共有 | **不要** (managed dict のみ) |
| C++ | `std::shared_ptr<const LoanwordData>` | factory 関数で reference 増加 | — |
| WASM/JS | Rust 側で byte copy → 内部保持 | JS 側からは fire-and-forget | — |

**カスタム辞書のメモリ overhead**:

- default + override マージ後は **インスタンス毎に独立コピー** (~10-50 KB/インスタンス)
- 実用上は server プロセスで 1-2 個程度なので問題なし
- 大量インスタンス生成シナリオ (test 等) では LRU cache の実装余地あり (Phase 2)

**メモリ overhead 見積**:

```text
LoanwordData (default):
  acronyms (66)        ~3 KB
  loanwords (40)       ~2 KB
  letter_fallback (26) ~1 KB
  ───────────────────────
  Total                ~6 KB (struct 化後 ~20 KB)
```

100 インスタンス共有でも default は 1 つだけ → **総メモリ ~20 KB** (Arc 共有の効果)

### 4.8 i18n / 多言語ペア拡張性

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
  "language_pair": "zh-en",
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

### 4.9 セキュリティ考慮事項

**脅威モデル**:

| 脅威 | 影響 | 緩和策 |
|------|------|--------|
| 巨大 JSON (DoS) | メモリ枯渇 | サイズ上限 **1 MB** |
| ネスト過深 (parser DoS) | stack overflow | depth 制限 **100** |
| symbolic link (path traversal) | ファイル領域外アクセス | `resolve()` + warning log |
| 大量エントリ (10K+) | hash table 巨大化 | エントリ数上限 **10,000** |
| 不正な pinyin syllable | IPA 変換失敗 | schema validation (4.4 で対応済) |
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
| C++ `nlohmann/json` | **無制限** | recursion 制限を明示的に設定 |
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

### 4.10 API ドキュメンテーション統一

**各ランタイムの既存ドキュメント品質**:

| ランタイム | 形式 | 既存品質 |
|-----------|------|---------|
| Rust | rustdoc (`///`) | 高品質 (japanese.rs に詳細例あり) |
| C# | XML doc (`<summary>`) | 高品質 (`IChineseG2PEngine` で `<list type="table">` 等使用) |
| TypeScript | JSDoc + `.d.ts` | 高品質 (`types/index.d.ts` 400+ 行) |
| Python | Google docstring | 高品質 |
| Go | godoc | 簡潔 |
| C++ | doxygen | 現状最小限、要拡充 |

**共通の必須要件** (各ランタイムの慣例を尊重しつつ統一):

1. **概要** (1-2 文): 機能説明 + 用途
2. **パラメータ**: 型 + 意味
3. **戻り値**: 型 + フィールド説明
4. **エッジケース注記**: kana 干渉、opt-out flag
5. **使用例**: コード snippet
6. **クロスリファレンス**: 関連関数 / 型

**共通用語集** (全ランタイムで統一):

| 用語 | 統一定義 |
|------|---------|
| **embedded English** | 中国語コンテキスト中の英単語、ピンイン経由で発音 |
| **loanword** | `loanwords` 辞書のエントリ (case-sensitive、例: Python) |
| **acronym** | `acronyms` 辞書のエントリ (uppercase、例: GPS) |
| **letter_fallback** | A-Z 文字単位フォールバック |
| **zh_en_dispatch** | `MultilingualPhonemizer` が `[zh,en,*]` 検出時に embedded path を使う挙動 |
| **kana 干渉** | ja-en-zh モードで kana 存在時に zh が ja 化される制約 |
| **opt-out flag** | `enable_zh_en_dispatch=False` で従来挙動に戻すパラメータ |

**テンプレート例 (Rust)**:

```rust
/// Phonemizes English text embedded in Chinese context as Mandarin pinyin.
///
/// Applies the ZH-EN code-switching rule: when the multilingual dispatcher
/// detects `[zh,en,*]` or `[en,zh]` patterns, embedded English words are
/// pronounced via Mandarin pinyin (e.g., "Python" → ["pai4", "sen1"]).
///
/// # Arguments
/// * `text` - English text segment (already split from Chinese context).
/// * `loanword_data` - Loanword dictionary with acronyms/loanwords/letter_fallback.
///
/// # Returns
/// Token array (IPA strings, no PUA encoding). Multi-char tokens like "tɕʰ"
/// are returned as-is for subsequent PUA mapping by the encoder.
///
/// # Example
/// ```
/// let ld = LoanwordData::default();
/// let result = phonemize_embedded_english("GPS Python", &ld);
/// ```
///
/// # Notes
/// Set `enable_zh_en_dispatch = false` in `MultilingualPhonemizer` to
/// skip this path and use standard English phonemization.
pub fn phonemize_embedded_english(
    text: &str,
    loanword_data: &LoanwordData,
) -> Vec<String> { ... }
```

**ドキュメント生成 CI**:

| ランタイム | 生成コマンド | 既存 CI |
|-----------|-----------|--------|
| Rust | `cargo doc --no-deps` | (検討中、`rust-tests.yml` 拡張) |
| C# | docfx | (未設定、Phase 2) |
| TypeScript | `typedoc` | (未設定、Phase 2) |
| Python | `sphinx-build` | (一部) |
| C++ | `doxygen` | **未設定 → 新規追加検討** |
| Go | godoc (組込) | (組込) |

### 4.11 デバッグ・トレース戦略

**統一 log level ガイドライン**:

| Level | 用途 |
|-------|------|
| **DEBUG** | dispatch 発動、loanword/acronym/letter_fallback hit、lookup count |
| **INFO** | phonemizer 初期化完了 |
| **WARN** | スキーマ違反、スキップされたセグメント、symbolic link 検出 |
| **ERROR** | ファイル not found、致命的エラー |

**統一フォーマット**: `[runtime:component] op=value key=value ...`

**各ランタイムの実装パターン**:

```python
# Python (logging)
_LOGGER.debug("zh_en dispatch: type=%s text=%r count=%d", "acronym", "GPS", 4)
```

```rust
// Rust (log crate)
log::debug!("zh_en dispatch: type={} text={:?} count={}", "acronym", "GPS", 4);
```

```go
// Go (slog)
slog.Debug("zh_en dispatch", "type", "acronym", "text", "GPS", "count", 4)
```

```csharp
// C# (Microsoft.Extensions.Logging)
logger.LogDebug("zh_en dispatch: type={Type} text={Text} count={Count}", "acronym", "GPS", 4);
```

```cpp
// C++ (spdlog)
spdlog::debug("zh_en dispatch: type={} text={} count={}", "acronym", "GPS", 4);
```

```javascript
// JS/WASM (console)
console.debug("[zh_en] dispatch", { type: "acronym", text: "GPS", count: 4 });
```

**デバッグフラグ**: `PIPER_DEBUG_ZH_EN=1` (全ランタイム共通の環境変数)

```python
# Python
import os
if os.environ.get("PIPER_DEBUG_ZH_EN"):
    logging.getLogger("piper_plus_g2p.chinese").setLevel(logging.DEBUG)
```

```rust
// Rust: 既存 RUST_LOG=debug でも有効
// 追加: PIPER_DEBUG_ZH_EN=1 で当該モジュールのみ DEBUG
```

**性能影響対策**:

- production build では debug log を出さない (各ランタイムの conditional logging)
- Python: `_LOGGER.isEnabledFor(logging.DEBUG)` でガード
- C++: `NDEBUG` macro で compile-time に削除可能
- WASM: `process.env.NODE_ENV !== 'production'` でガード

### 4.12 テストカバレッジ目標

**カバレッジ目標値**:

| 項目 | 目標 | 根拠 |
|------|------|------|
| 全体 line coverage | **80%+** | 業界標準 |
| ZH-EN 機能 line coverage | **90%+** | 新機能、厳格 |
| ZH-EN 機能 branch coverage | **90%+** | 3 経路 (loanword/acronym/fallback) 全網羅 |
| エラーパス coverage | **100%** | schema violation / file not found |

**必須 branch 経路**:

```text
phonemize_embedded_english():
├─ loanword_hit (case-sensitive)        ← test_loanword_python_case_sensitive
├─ acronym_hit (case-insensitive)       ← test_acronym_gps
├─ letter_fallback (未知語)             ← test_letter_fallback_for_unknown
└─ digits_dropped (数字混じり)          ← test_digits_dropped_in_letter_fallback

_load_loanword_data():
├─ valid JSON                           ← test_valid_json_accepted
├─ string instead of list (schema)      ← test_string_value_rejected
├─ non-string in list (schema)          ← test_non_string_inside_list_rejected
└─ section is not dict (schema)         ← test_section_not_mapping_rejected
```

**各ランタイムの計測ツール**:

| Runtime | ツール | 既存 CI 統合 |
|---------|------|------------|
| Python | `pytest-cov` + coverage.py | 既存 (codecov アップロード済) |
| Rust | `cargo-tarpaulin` (or `cargo-llvm-cov`) | **新規追加が必要** |
| Go | `go test -coverprofile` | **新規追加が必要** |
| C# | `coverlet` (`XPlat Code Coverage`) | 既存 (cobertura.xml artifact) |
| JS/TS | `vitest --coverage` (c8) | **新規追加が必要** |
| C++ | `gcov` + `lcov` | **新規追加が必要** |

**新規 CI ワークフロー** (`.github/workflows/coverage-unified.yml`):

```yaml
name: Unified Coverage
on: [pull_request]
jobs:
  python-coverage:
    steps:
      - run: |
          cd src/python/g2p
          uv run pytest --cov=piper_plus_g2p --cov-report=xml --cov-fail-under=80
  rust-coverage:
    steps:
      - run: |
          cargo install cargo-tarpaulin
          cargo tarpaulin -p piper-plus-g2p --out Xml --fail-under 80
  go-coverage:
    steps:
      - run: |
          cd src/go
          go test -coverprofile=coverage.out ./phonemize/...
          go tool cover -func=coverage.out | grep total | awk '{print $3}'
          # < 80% で fail
  csharp-coverage:
    steps:
      - run: |
          dotnet test --collect:"XPlat Code Coverage" --results-directory coverage
  upload:
    needs: [python-coverage, rust-coverage, go-coverage, csharp-coverage]
    steps:
      - uses: codecov/codecov-action@v5
        with:
          flags: python,rust,go,csharp
          fail-ci-if-error: false
```

**Phase 戦略**:

| Phase | 範囲 | 内容 |
|-------|------|------|
| Phase 1 (本 PR) | Python + 既存 C# | 既存ツールで ZH-EN を 90%+ に引上 |
| Phase 2 (フォローアップ) | Rust / Go / JS-WASM | カバレッジ計測ツール導入 + CI 追加 |
| Phase 3 (将来) | C++ | gcov/lcov + 統合ダッシュボード |

**実装工数**:

- Phase 1: 既存基盤利用 → ~2 時間
- Phase 2: 各ランタイムで CI 設定 → ~5 時間
- Phase 3: gcov 統合 → ~3 時間

---

## 5. 関連ドキュメント

- 親 PR (Python): [#397](https://github.com/ayutaz/piper-plus/pull/397)
- 元 Issue: [#384](https://github.com/ayutaz/piper-plus/issues/384)
- PUA 仕様: `docs/spec/pua-contract.toml`
- Phoneme Timing 仕様: `docs/spec/phoneme-timing-contract.toml`
- iOS shared lib 仕様: `docs/reference/ios-shared-lib.md`
- 同期 mirror 一覧: `docs/spec/loanword-mirrors.toml`
