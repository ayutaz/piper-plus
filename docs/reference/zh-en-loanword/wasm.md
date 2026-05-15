# JS/WASM — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

## 1. 実装ファイル

| 用途 | パス |
|------|------|
| JS 中国語実装 | `src/wasm/g2p/src/zh/index.js` (140 行、character pass-through のみ) |
| Rust WASM | `src/rust/piper-wasm/src/lib.rs` (`setChineseDictionary()` FFI 公開) |
| pinyin → IPA | Rust 側 (`piper-plus-g2p/src/chinese.rs`) で実装、JS 経由で呼出 |
| 辞書データ | `src/wasm/g2p/data/zh_en_loanword.json` |
| Multilingual | `src/wasm/g2p/src/detect.js` (294 行、`segmentText` 完備) |
| テスト | `src/wasm/g2p/test/test-chinese.js` (463 行、mock 中心) |

## 2. 現状調査

| 項目 | 状態 |
|------|------|
| データロード | Rust 側で JSON load、JS は薄い |
| ZH-EN dispatch | **❌ 未実装** |
| 二層問題 | **JS と Rust の両方を更新する必要があるか判断必要** |

**追加 LOC 見込み**: ~250 行 (Rust 完了が前提、JS 側は薄ラッパ + テスト追加で済む)

**実装場所判断**: Rust 側で `phonemize_embedded_english()` を実装すれば、WASM ビルドだけで JS 側にも自動的に展開される。JS 側は新 FFI (`setChineseLoanwordData()`) の薄ラッパとテストのみ。

## 3. 二層 FFI 設計

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

## 4. WASM サイズ最適化

**現状サイズ**:

| 成果物 | サイズ |
|--------|------|
| `piper_plus_wasm.wasm` (release、全言語+JA 辞書込み) | 59 MB |
| `@piper-plus/g2p` npm package (実装コードのみ) | 684 KB |
| 既存 `g2p-wasm-ci.yml` の **size-check 制限** | **1 MB** (npm package) |

**JSON を JS 側に bundle 済** (8.4 で確定) のため WASM サイズへのデータ影響は **+0**。

**コード追加によるサイズ影響**:

| 項目 | 影響 |
|------|------|
| `phonemize_embedded_english` (~150 行) | +5-8 KB |
| `LoanwordData` struct + serde derive | (serde_json 既存依存、追加なし) |
| Multilingual dispatcher 拡張 | +2-3 KB |
| **合計** | **+8-12 KB** (圧縮後) |

**最適化戦略**:

```toml
# src/rust/piper-wasm/Cargo.toml
[features]
default = ["zh", "ja", "en"]
zh = ["piper-plus-g2p/chinese"]
zh-en = ["zh", "piper-plus-g2p/zh-en-loanword"]   # ← 新規 opt-in
en = ["piper-plus-g2p/english"]
```

**feature gate の意義**:

- ZH-EN 機能を必要としないアプリ (例: 日本語専用 TTS) は `default-features = false` で除外可能
- ABI 安定性: feature gate により API は cargo level で制御

**既存 wasm-opt 設定** (`piper-wasm/Cargo.toml`):

```toml
[package.metadata.wasm-pack.profile.release]
wasm-opt = ['-Os']  # サイズ重視最適化
```

**目標**:

| 項目 | 目標 | 実績見込み |
|------|------|----------|
| WASM サイズ増分 | < +25 KB | +8-12 KB ◯ |
| npm package size | < 1 MB (CI 既存ガード) | 684 KB → ~700 KB ◯ |
| feature gate | `zh-en` 新規追加 | 必須 |

**CI size regression 検出**: 既存 `g2p-wasm-ci.yml` の **1 MB ガード**で監視継続 (新規ジョブ不要)

## 5. メモリ管理

Rust 側で byte copy → 内部保持。JS 側からは fire-and-forget。

## 6. エラーハンドリング

JS/WASM `Error` with `code='SCHEMA_ERROR'`、Rust 側 `JsValue::from_str("SCHEMA_ERROR: ...")`:

```rust
.map_err(|e| JsValue::from_str(&format!("CONFIG_PARSE_ERROR: {e}")))?;
```

## 7. ベンチマーク

| フレーム | ファイル |
|--------|--------|
| `mitata` | `src/wasm/g2p/bench/bench-zh-en.js` |

## 8. カバレッジ

`vitest --coverage` (c8) で計測 (CI 新規追加が必要)。

## 9. JSON parser 安全性

JS `JSON.parse` は stack-based。サイズ check + `try/catch` でガード。
