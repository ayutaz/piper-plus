# Rust — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

## 1. 実装ファイル

| ファイル | パス | 役割 |
|---------|------|------|
| Phonemizer (WASM 対応) | `src/rust/piper-plus-g2p/src/chinese.rs` (1,314 行、関数 60 個) | crates.io 公開、WASM ビルド経路 |
| Phonemizer (non-WASM) | `src/rust/piper-core/src/phonemize/chinese.rs` (1,462 行) | デスクトップ CLI / Python binding 用 |
| Multilingual | `src/rust/piper-plus-g2p/src/multilingual.rs` (1,015 行) | `UnicodeLanguageDetector` + `segment_text` |
| 辞書データ | `src/rust/piper-plus-g2p/data/zh_en_loanword.json` + `src/rust/piper-core/data/zh_en_loanword.json` | byte-for-byte 同期 |
| テスト | `piper-plus-g2p/src/chinese.rs:#[cfg(test)]` (unit 30+) + `piper-core/tests/test_chinese.rs` (373 行) | integration test |

## 2. 現状調査

| 項目 | 状態 |
|------|------|
| pinyin → IPA 関数 | `split_pinyin()` / `pinyin_to_ipa()` / `normalize_pinyin()` / `apply_tone_sandhi()` |
| 公開構造体 | `ChinesePhonemizer { dict: ZhDictRef }` |
| データロード | `serde_json::from_str` / `OnceLock` キャッシュ、`include_str!` 未使用 (実行時ファイル読込) |
| ZH-EN dispatch | **❌ 未実装 (本 PR で実装)** |
| `phonemize_embedded_english` | **❌ 未実装** |
| `_load_loanword_data` | **❌ 未実装** |
| `zh_en_loanword.json` | **❌ 未同梱** |

**追加 LOC 見込み**: ~400 行 (`phonemize_embedded_english` 実装 + LoanwordData struct + multilingual dispatch)

## 3. crate 重複問題と実装場所決定

**重要発見**: 中国語 phonemizer 実装が **2 箇所に存在**:

```text
src/rust/
├── piper-plus-g2p/src/chinese.rs    (1,314 行) — WASM 対応版、crates.io 公開
└── piper-core/src/phonemize/chinese.rs (1,462 行) — non-WASM、ProsodyInfo 統合
```

**依存関係グラフ**:

```text
piper-cli       → piper-core
piper-python    → piper-core
piper-wasm      → piper-core + piper-plus-g2p (feature-gated)
piper-core      → piper-plus-g2p (依存先、ただし phonemize は独自実装あり)
piper-plus-g2p  → 独立 (crates.io 公開)
```

**両者の差分**:

| 項目 | `piper-plus-g2p` | `piper-core` |
|------|----------------|--------------|
| WASM 対応 | ◯ (`from_json_bytes()`) | ✗ (`cfg!(not(target_arch = "wasm32"))`) |
| `ProsodyInfo` (a1/a2/a3) | △ (基本のみ) | ◯ 統合 |
| crates.io 公開 | ◯ | ◯ |
| 利用元 | piper-wasm のみ | piper-cli / piper-python / piper-wasm 全て |
| コールドスタート最適化 (#302) | 未適用 | 適用済 |

**結論**: **両方に実装する必要がある**

- **`piper-core/src/phonemize/chinese.rs`**: デスクトップ用 CLI / Python binding が使う、`ProsodyInfo` 統合済 → **ここで主実装**
- **`piper-plus-g2p/src/chinese.rs`**: WASM ビルド時の経路 → **同等実装をミラー** (将来 v0.5.0 で統合予定だが本 PR では並列維持)

**両者を一致させるため**:

- 実装の core ロジック (lookup priority、token tokenize 等) を 1 つの module 化検討 (例: `piper-plus-g2p::chinese::loanword` を `piper-core` から re-export)
- ただし `ProsodyInfo` の差で完全 re-export 困難なら、コミット内で同期確認テストを追加

**推奨アプローチ**:

```text
1. piper-core/src/phonemize/chinese.rs に embedded_english_phonemize() を主実装
2. piper-plus-g2p/src/chinese.rs にも同等関数を実装 (WASM 経路用)
3. 両方の実装が同じ JSON データから同じ結果を生むテストを追加
4. v0.5.0 でいずれか統合 (本 PR の Out of Scope)
```

**Rust 工数の修正**: 当初見積 ~400 行 → **~600 行** (2 箇所実装のため +50%)

## 4. メモリ管理戦略

**推奨パターン**: `OnceLock<Arc<LoanwordData>>` + `Arc::clone()` で zero-copy 共有

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

100 インスタンス共有でも default は 1 つだけ → **総メモリ ~20 KB** (Arc 共有の効果)。

## 5. エラーハンドリング

`thiserror` 拡張で `G2pError::LoanwordSchema { .. }` を追加:

```rust
Err(G2pError::LoanwordSchema { path, section, key })
```

メッセージテンプレート (全ランタイム共通):

```text
{path}: '{section}.{key}' must be list[str], got {actual_type}
```

## 6. テスト戦略

`src/rust/piper-plus-g2p/tests/test_zh_en_unified.rs` を新規作成し、共有 fixture (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) からロードして parametrize:

```rust
// Rust: piper-plus-g2p/tests/test_zh_en_unified.rs
#[test]
fn test_zh_en_matrix() {
    let matrix: Vec<TestCase> = load_fixture(".../zh_en_test_matrix.json");
    for case in matrix { run_case(&case); }
}
```

## 7. ベンチマーク

| フレーム | ファイル |
|--------|--------|
| `criterion` | `src/rust/piper-plus-g2p/benches/bench_chinese_embedded.rs` |
