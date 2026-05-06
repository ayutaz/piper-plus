# TICKET-01: Rust ZH-EN Code-Switching 実装

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-01 |
| **マイルストーン** | Phase 1 (Day 1-3) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §2.1 / §4.1 R1-R5 / §8.5 (crate 重複問題) / §8.14 (thread safety) |
| **ステータス** | 📝 Draft |
| **依存元** | なし |
| **依存先** | TICKET-04 (JS/WASM, Rust 完了が前提) |
| **追加 LOC** | ~600 (`piper-plus-g2p` ~300 + `piper-core` ~300) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: Rust 製 G2P (`piper-plus-g2p`) および推論コア (`piper-core`) で `[zh, en, *]` / `[en, zh]` / `[zh, en, zh]` パターンを検出し、英単語を Mandarin pinyin に変換できるようにする。Python 実装 ([#397](https://github.com/ayutaz/piper-plus/pull/397)) と byte-for-byte 一致する出力を返す。

**ゴール**:
- `phonemize_embedded_english(text: &str, data: &LoanwordData) -> Vec<String>` が公開 API として動作する。
- `MultilingualPhonemizer` が `[zh, en, *]` パターンを自動 dispatch する。
- `data/zh_en_loanword.json` を `include_str!` で同梱、`OnceLock` でロード。
- Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件が Python と同一の IPA 列を返す。
- 純中国語経路の性能劣化が **<5%**。

---

## 2. 実装する内容の詳細

### R1. `chinese.rs` に `phonemize_embedded_english` 関数追加 (2 箇所)

設計書 §8.5 で確定済みの「**重複実装やむなし**」方針:

| ファイル | 役割 | 実装内容 |
|---------|------|---------|
| `src/rust/piper-plus-g2p/src/chinese.rs` | crates.io 公開 + WASM | `phonemize_embedded_english()` 主実装 |
| `src/rust/piper-core/src/phonemize/chinese.rs` | デスクトップ + ProsodyInfo | 同等関数を重複実装、両者が同じ結果を返すテスト追加 |

実装ロジック:

```rust
pub fn phonemize_embedded_english(
    text: &str,
    data: &LoanwordData,
) -> Vec<String> {
    let mut tokens = Vec::new();
    for raw in tokenize_english_words(text) {
        let stripped = strip_trailing_punctuation(&raw);
        if let Some(syllables) = lookup(&stripped, data) {
            for s in syllables {
                let pinyin_split = split_pinyin(s);
                let ipa = pinyin_to_ipa(&pinyin_split);
                tokens.extend(ipa);
            }
        }
    }
    tokens
}
```

**Lookup 優先度** (Python と一致):
1. `data.loanwords[stripped]`            — case-sensitive
2. `data.acronyms[stripped.to_uppercase()]` — uppercase
3. `data.letter_fallback[ch.to_uppercase()]` — char-by-char、`is_ascii_digit()` は drop

### R2. `LoanwordData` struct + `load_loanword_data()`

```rust
#[derive(Debug, Clone, Deserialize)]
pub struct LoanwordData {
    pub version: u32,
    pub acronyms: HashMap<String, Vec<String>>,
    pub loanwords: HashMap<String, Vec<String>>,
    pub letter_fallback: HashMap<String, Vec<String>>,
}

pub fn load_default_loanword_data() -> &'static LoanwordData {
    static CACHE: OnceLock<LoanwordData> = OnceLock::new();
    CACHE.get_or_init(|| {
        let raw = include_str!("../data/zh_en_loanword.json");
        let parsed: LoanwordData = serde_json::from_str(raw)
            .expect("zh_en_loanword.json: invalid schema");
        validate_schema(&parsed).expect("schema validation failed");
        parsed
    })
}
```

**Schema validation**: Python 側と同じく「`list[str]` でない値があれば `f"{path}: '{section}.{key}' must be list[str]"`」相当のエラーを `Result<(), String>` で返す。Python 側のテスト (`TestSchemaValidation`) と同等のエラーメッセージ書式に合わせる。

### R3. `multilingual.rs` で `[zh, en, *]` パターン dispatch

```rust
for (i, segment) in segments.iter().enumerate() {
    if segment.lang == "en" && has_zh_in_text {
        let prev_is_zh = i > 0 && segments[i - 1].lang == "zh";
        let next_is_zh = i + 1 < segments.len() && segments[i + 1].lang == "zh";
        if prev_is_zh || next_is_zh {
            let tokens = chinese_phonemizer.phonemize_embedded_english(
                &segment.text, &loanword_data,
            );
            result.extend(tokens);
            continue;
        }
    }
    // 既存の英語経路
    result.extend(english_phonemizer.phonemize(&segment.text));
}
```

### R4. `data/zh_en_loanword.json` 同梱

両 crate にコピーを配置:
- `src/rust/piper-plus-g2p/data/zh_en_loanword.json`
- `src/rust/piper-core/data/zh_en_loanword.json`

`include_str!("../data/zh_en_loanword.json")` で埋め込み。Python 側 `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` と byte-for-byte 一致させる。

### R5. テスト追加

#### Unit テスト (`#[cfg(test)] mod tests`、両 crate に対称配置)

| テスト名 | 内容 |
|---------|------|
| `test_acronym_gps` | `phonemize_embedded_english("GPS", &data)` が `ji4-pi4-ai1-si4` 相当の IPA + tone marker を返す |
| `test_loanword_python` | `Python` (case-sensitive) → `pai4-sen1` |
| `test_loanword_chatgpt` | `ChatGPT` → 5 syllable |
| `test_letter_fallback_zz` | `ZZ` → `letter_fallback['Z']` が 2 回 |
| `test_empty_input` | `""` → `vec![]` |
| `test_loanword_beats_acronym` | override で loanword 優先確認 |
| `test_acronym_beats_fallback` | override で acronym 優先確認 |
| `test_python_vs_PYTHON` | case sensitivity |
| `test_trailing_punctuation` | `GPS,` `GPS.` `GPS` が等しい結果 |
| `test_two_embedded_en` | `ChatGPT 和 Python` で 7 syllable |
| `test_digits_dropped` | `Z2Z9` == `ZZ` |
| `test_acronym_with_digits` | `MP3` が acronym 直接ヒット |
| `test_schema_validation_invalid_type` | 不正な schema で `validate_schema` がエラーを返す |

#### Integration テスト (`piper-core/tests/test_chinese.rs` 拡張)

| テスト名 | 内容 |
|---------|------|
| `test_zh_en_zh_pattern` | `请打开 GPS 系统` 全体 phonemize |
| `test_zh_en_pattern` | Issue 例 `请打开 GPS` |
| `test_en_zh_pattern` | `Hello 世界` で en が zh 文脈を取得 |
| `test_pure_zh_unaffected` | regression: 純中国語に影響なし |
| `test_pure_en_uses_english` | regression: 純英語は g2p-en 経路 |
| `test_issue_example_python` | `我喜欢用 Python 写代码` |
| `test_issue_example_chatgpt` | `让我用 ChatGPT 写代码` |
| `test_two_crate_consistency` | **`piper-plus-g2p` と `piper-core` で同じ入力に対して同じ出力** (重要) |
| `test_json_matches_python_source` | `data/zh_en_loanword.json` を Python source とバイト比較 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 主な責任 | 主な担当 |
|------|------|---------|---------|
| **Phase Lead** | 1 | チケット全体統括、レビュー後の修正可否判断、INDEX 進捗更新 | レビュー連絡、TICKET-04 への引き継ぎ |
| **Rust Core Dev** | 2 | `piper-plus-g2p` / `piper-core` に並行で `phonemize_embedded_english()` 実装、`LoanwordData` + `load_default_loanword_data()` | R1-R4 |
| **QA / Test** | 1 | Unit / Integration テスト 22 ケース、Python source との byte 比較、性能ベンチ | R5 |

**並列化**:
- Dev #1 → `piper-plus-g2p` (主実装)
- Dev #2 → `piper-core` (ミラー実装、Dev #1 のコミットを参考)
- QA → 両 crate の同期テスト + 既存 fixture 増強

**コミットの分け方**: `feat(rust): R1-R4 実装` / `test(rust): R5 テスト` の 2 コミット推奨。

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- `piper-plus-g2p` の Rust 公開 API: `ChinesePhonemizer::phonemize_embedded_english()`, `LoanwordData`, `load_default_loanword_data()`, `validate_schema()`
- `piper-core` 内部 API (同等関数、ProsodyInfo 統合経路で利用)
- `MultilingualPhonemizer` の dispatch 拡張
- `data/zh_en_loanword.json` 同梱 (両 crate)

### Out of scope

- WASM ビルド成果物の更新 (TICKET-04 で対応)
- v0.5.0 で計画している `piper-plus-g2p` と `piper-core` の chinese 統合 (本 PR では並列維持)
- crates.io 公開 (TICKET-07)

### テスト項目

設計書 §4.3 の統一テストマトリックス全件 + 重複 crate 同期テスト。最低 **22 テスト/crate × 2 = 44 テスト**。

---

## 5. Unit テスト

セクション 2 の R5 表を参照。両 crate に対称配置。`assert_eq!` で IPA 列を直接比較。Python 側との比較は **fixture 比較関数** を `tests/fixtures/zh_en_test_matrix.json` (TICKET-06 で導入予定) から共通読込。

**テスト fixture 用意**:

```json
{
  "issue_examples": [
    {"input": "请打开 GPS", "expected_tokens": ["t͡ɕʰ", "ˈ", "i", "ŋ", ...]}
  ],
  "lookups": [
    {"input": "Python", "expected_tokens": [...]}
  ]
}
```

---

## 6. E2E テスト

`piper-cli` バイナリで Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件を実音声合成し、Python (`piper-plus`) で生成した参照音声と **音素列が完全一致**することを確認。

```bash
# 期待動作: phoneme dump が一致
cargo run --release --bin piper-cli -- \
  --model multilingual-test-medium.onnx \
  --text "请打开 GPS" \
  --language zh-en \
  --output-phonemes  # JSON dump
diff <python_phonemes.json> <rust_phonemes.json>
```

**E2E ケース**:
1. 请打开 GPS → 4 syllable tone を含む phoneme 列が Python と byte 一致
2. 我喜欢用 Python 写代码 → `Python` が `pai4-sen1` IPA で展開
3. 让我用 ChatGPT 写代码 → `ChatGPT` が 5 syllable

---

## 7. 実装に関する懸念事項

### 懸念 1: 2 crate の実装ずれ
- **影響**: WASM ビルドとデスクトップ CLI で出力が異なる致命傷。
- **緩和**: `test_two_crate_consistency` を必須化、CI で両方を回す。
- **責任**: QA。

### 懸念 2: `OnceLock` のスレッド安全性 (§8.14)
- **影響**: 並行読込時の reordering / data race。
- **緩和**: `OnceLock` は `'static` 前提で safe。`Arc<LoanwordData>` を返すパターンも検討するが、今回は `&'static` で十分。
- **責任**: Rust Core Dev #1。

### 懸念 3: `serde_json` cold start
- **影響**: 初回呼出で 5-10ms のオーバーヘッド。
- **緩和**: `OnceLock` で 1 回だけパース、warmup 時に load 済みであれば runtime path に影響なし。
- **責任**: Rust Core Dev。

### 懸念 4: ProsodyInfo 経路の互換
- **影響**: `piper-core` 側の embedded en 出力に prosody_features 0 fill が必要。
- **緩和**: 設計書 §8.5 の「prosody features は 0 fill する」原則を維持、テストで a1/a2/a3 が `[0, 0, 0]` であることを確認。
- **責任**: Rust Core Dev #2。

### 懸念 5: WASM ビルドサイズ増加 (§8.22)
- **影響**: JSON 同梱で wasm bundle が ~30KB 増。
- **緩和**: `feature = "zh-en"` で gate 可能にする (デフォルト on、必要なら off にできる)。本 PR ではデフォルト on のみ。
- **責任**: Rust Core Dev #1。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] `phonemize_embedded_english` のシグネチャが `&str + &LoanwordData → Vec<String>` で固定されている
- [ ] `LoanwordData` が `Send + Sync` (実装が `derive(Clone, Debug, Deserialize)` 経由で自動)
- [ ] `OnceLock<LoanwordData>` で初回ロードのみ、その後は `&'static` 参照を返す
- [ ] `include_str!("../data/zh_en_loanword.json")` で埋め込み、ランタイム I/O なし
- [ ] schema validation エラーが Python 側と書式一致 (`{path}: '{section}.{key}' must be list[str]`)
- [ ] dispatch 条件 `[zh,en,*]` / `[en,zh]` / `[zh,en,zh]` のロジックが Python と一致
- [ ] tokenize 時 trailing punctuation を strip
- [ ] digits を `letter_fallback` で drop (例: `Z2Z9` == `ZZ`)
- [ ] 既存 PUA mapping (`0xE020-0xE04A`) と整合 (`docs/spec/pua-contract.toml` を参照)
- [ ] テストが 2 crate で対称
- [ ] `tests/fixtures/zh_en_test_matrix.json` (もし TICKET-06 で導入されていれば) を読み込む経路を持つ

### ドキュメントレビュー

- [ ] `src/rust/piper-plus-g2p/README.md` に ZH-EN code-switching 例追加
- [ ] `src/rust/piper-core/CHANGELOG.md` に "added: ZH-EN code-switching support" 一行
- [ ] crate-level docstring (`//!`) 更新

---

## 9. 一から作り直すとしたら

> **前提**: ここでの再設計案は **v1.0.0 (major bump)** をリリース対象とする。本 PR (TICKET-01) は §8.11 確定通り **0.5.0 (minor bump)** で進めるため、Section 9 は将来の v1.0.0 設計入り口として記録する。

### 9.0 思想 (不変条件 → 設計原則の順)

| # | 原則 | 説明 |
|---|------|------|
| 1 | **PUA 出力 byte 一致** | 既存学習済モデルが PUA 0xE020-0xE04A を tone marker として学習済 ([pua-contract.toml](../../spec/pua-contract.toml))。再設計でも codepoint と発火順序は **絶対に変えない**。 |
| 2 | **Default-on, opt-out 可** | `enable_zh_en_dispatch: bool` を builder pattern に必須化。後方互換のため default は `true`。設計書 §8.12。 |
| 3 | **Graceful failure** | default loanword 欠損 → warning + 空辞書で動作継続。override 欠損 → `Error`。schema 違反 → Python と byte 一致のエラー文言。設計書 §8.9。 |
| 4 | **Single source of truth** | Python 側 JSON が canonical、Rust は consumer。CI で byte-for-byte ガード (`scripts/check_loanword_consistency.py`)。 |
| 5 | **コンパイル時生成 > ランタイムロード** | エントリ数が閾値 (1,000) を超えたら phf 化、未満なら `OnceLock` + `serde_json` 維持。cold start 数値で判断。 |
| 6 | **Trait ベース、データソース差替可** | `trait EmbeddedEnglishPhonemizer`、JSON / DB / gRPC を差し替え可能に。 |
| 7 | **クロス言語 fixture で振る舞い同期** | `tests/fixtures/g2p/zh_en_loanword_matrix.json` を 5 ランタイムで読む。`schema_version` field 必須。 |

### 9.1 データ層

**現状の判断**: 131 entries (acronyms 65 + loanwords 40 + letter_fallback 26) では `OnceLock + serde_json` で十分。phf 化は **将来 letter_fallback を CJK 全字に拡張 (10,000+ entries) する場合の保険**。

| 採用パス | トリガー | 実装 |
|---------|---------|------|
| `OnceLock + serde_json` | エントリ数 < 1,000 | 現行案そのまま (R2)。schema validation はランタイムエラー (`G2pError::LoanwordSchema`)。cold start 5-10ms。 |
| `build.rs + phf_codegen` | エントリ数 ≥ 1,000 OR cold start p99 < 1ms 要件 | `build.rs` が `OUT_DIR/loanword_generated.rs` に `phf::Map<&'static str, &'static [&'static str]>` を 3 個吐き、`include!` で取り込む。schema 違反は **build time `panic!`** で compile error 化、ランタイム error 不要。`LoanwordData` は互換ラッパとして残す。WASM target も `phf 0.11+` で動作確認済 (`no_std + alloc` 対応)。ビルド時間増分 +0.3-0.5s。 |

### 9.2 API 層

```rust
// builder pattern + opt-out
let phonemizer = ChinesePhonemizerBuilder::new()
    .enable_zh_en_dispatch(true)               // Default-on
    .loanword_data(LoanwordSource::Default)    // or Custom(path), or Embedded(&'static)
    .build()?;

trait EmbeddedEnglishPhonemizer {
    fn phonemize(&self, text: &str) -> Result<Vec<String>, G2pError>;
}
```

- error 型は `enum G2pError { LoanwordSchema { path, section, key, expected }, LoanwordIo(io::Error), .. }`、`Display` impl で Python と同一書式 (`{path}: '{section}.{key}' must be list[str]`)。
- 現行 `pub fn load_default_loanword_data() -> &'static LoanwordData` は **互換 alias として残す** (phf 化後は `&'static LoanwordTable` を返すラッパに転送)。
- `phonemize_embedded_english(&str, &LoanwordData)` は free fn として現行 API を温存、内部で trait 実装を呼ぶ。

### 9.3 Dispatcher (段階導入)

**Day 1 (本 PR)**: 現行の `prev_is_zh / next_is_zh` 直書き (R3) のまま。pattern table は導入しない。

**v1.0.0 (将来)**:
```rust
static PATTERNS: &[CodeSwitchPattern] = &[
    CodeSwitchPattern { src: "zh", embedded: "en", phonemizer: PhonemizerKind::ZhLoanword },
    // 将来追加 (JA-EN, KO-EN 等):
    // CodeSwitchPattern { src: "ja", embedded: "en", phonemizer: PhonemizerKind::JaLoanword },
];
```
- table を data 化することで **JA-EN / KO-EN 拡張は config 追加 1 行**で済む。
- 現状 ZH-EN 1 行のみなので、抽象化のメリットが出るのは設計書 §8.17 Phase 2 (6 ヶ月後) 以降。Day 1 で先回り実装するとデッドコードになるため **「JA-EN 追加 PR で refactor」を確約**。

### 9.4 Crate 構成 (major bump 必須)

| 変更 | SemVer 影響 | 移行戦略 |
|------|-----------|---------|
| `LoanwordData` の field を `&'static phf::Map<...>` に変更 | **Breaking** (struct layout 変更) | 0.5.x で `LoanwordTable` (新型) を **追加**、`LoanwordData` は `#[deprecated]` なしで併存 → 1.0.0 で `LoanwordData` 削除 |
| `ChinesePhonemizer` を Trait 化 | **Breaking** (inherent → trait dispatch) | 0.5.x で trait を `impl ChinesePhonemizer` の隣に追加 → 1.0.0 で inherent impl 削除 |
| `piper-core::phonemize::chinese` を `pub use piper_plus_g2p::core::chinese::*;` に置換 | **Breaking** (private 型露出) | 1.0.0 で実施。0.x では §8.5 の 2 crate 重複維持 |
| `phonemize_embedded_english` の free fn シグネチャ温存 | **Non-breaking** | `pub use` 再 export で吸収可能 |

### 9.5 Failure mode

設計書 §8.9 を Rust 用に具体化:

| ケース | 動作 | エラー型 |
|-------|------|---------|
| default loanword JSON 欠損 (build 時) | **build error** (phf 採用時) / runtime warn + 空辞書 (OnceLock 採用時) | — / `G2pError::LoanwordIo` |
| override path 指定で file 欠損 | `Result::Err` | `G2pError::LoanwordIo(io::Error)` |
| schema 違反 (list[str] 以外の値) | phf: build panic / OnceLock: runtime error | `G2pError::LoanwordSchema { path, section, key, expected: "list[str]" }` |
| runtime JSON parse error (override) | `Result::Err`、Python の文言を踏襲 | `G2pError::LoanwordParse(serde_json::Error)` |
| `enable_zh_en_dispatch=false` | 既存 EnglishPhonemizer 経路、loanword は touch しない | — |

### 9.6 i18n 拡張パス

設計書 §8.17 の 3 phase を Rust crate 構成に投影:

| Phase | 内容 | 必要な変更 |
|-------|------|-----------|
| Phase 1 (本 PR) | ZH-EN のみ | `data/zh_en_loanword.json` 1 ファイル |
| Phase 2 (6 ヶ月後) | JA-EN / KO-EN 追加 | `data/loanword/{ja_en, ko_en}.json` 追加 + pattern table 拡張。9.3 の table 化が活きる |
| Phase 3 (1 年後) | 任意言語ペア API | `LoanwordRegistry::register(src, tgt, data)` 動的登録 |

### 9.7 テスト戦略

- fixture: `tests/fixtures/g2p/zh_en_loanword_matrix.json`、`schema_version: 1` 必須。**major schema 変更時は全ランタイム loader の同時 PR を CI で強制** (TICKET-06 で実装)。
- ループ式テスト: `for case in fixture.cases { assert_eq!(phonemize(&case.input), case.expected) }`。
- `pretty_assertions` で diff 表示、`cargo nextest` 採用は本 PR では out of scope (別 PR で workspace-wide に導入)。
- PUA 同期パターン (`scripts/check_pua_consistency.py`) を踏襲し、`scripts/check_loanword_consistency.py` で entry-by-entry 検証 (設計書 §8.7 line 505)。

### 9.8 Observability

- `tracing 0.1` (既に dependency) で `tracing::debug!(target: "piper.loanword", "hit acronym: {} → {:?}", token, syllables)` 相当をリトリガー位置 3 箇所 (loanword hit / acronym hit / fallback hit) に追加。
- `RUST_LOG=piper=debug,piper.loanword=trace` で動作トレース可能。
- 設計書 §8.20 の `PIPER_DEBUG_ZH_EN=1` env var との関係: env var がセットされていたら `tracing` レベルを `trace` に上書きするブートストラップを 1 箇所に集約。

---

## 10. 後続タスクへの連絡内容

### TICKET-04 (JS/WASM) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **WASM 経路の起点** | `piper-plus-g2p::ChinesePhonemizer::phonemize_embedded_english` を `wasm-bindgen` で公開済み (TICKET-01 R1) |
| **必要な FFI 追加** | `setChineseLoanwordData(data: JsValue)` を `piper-wasm/src/lib.rs` に追加 (TICKET-04 W2) |
| **JSON 同梱方法** | `piper-plus-g2p` 側に `include_str!` 済み、JS 側は default で fetch 不要 |
| **テスト fixture** | `tests/fixtures/zh_en_test_matrix.json` を JS 側でも参照可能にする (TICKET-06 で確定) |
| **wasm-pack build 影響** | bundle size +30KB、TICKET-04 で feature gate 検討 |

### TICKET-06 (CI Sync) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JSON 配置パス** | `src/rust/piper-plus-g2p/data/zh_en_loanword.json`, `src/rust/piper-core/data/zh_en_loanword.json` |
| **比較対象** | Python source `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` と byte 一致 |
| **CI workflow 想定名** | `.github/workflows/zh-en-loanword-sync.yml` |
| **追加チェック** | `validate_schema` 通過確認 (各ランタイムで) |

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **README 追加** | `src/rust/piper-plus-g2p/README.md` に ZH-EN 例 3 つ |
| **CHANGELOG** | `[Unreleased]` セクションに "Added: ZH-EN code-switching" |
| **crate-level docstring** | `//!` で機能説明追加、`docs.rs` ビルド確認 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §2.1 / §4.1 / §8.5 から派生) |
