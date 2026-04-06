# M1-3: 言語検出の統合

**マイルストーン**: M1 (PiperPlus に Rust WASM phonemizer を統合)
**依存チケット**: M1-1
**後続チケット**: M2-1, M2-2

## タスク目的とゴール

現在の `synthesize()` と `synthesizeStreaming()` は `this._g2p.detectLanguage(text)` で言語検出を行っている。しかし M1-1 で `'ja'` が JS G2P の言語リストから除外されるため、JS G2P の `detectLanguage()` は日本語テキストを検出できなくなる。このチケットでは、`_wasmPhonemizer` がある場合に Rust WASM の `detectLanguage()` を言語検出に使用する。

**完了条件:**
- `_wasmPhonemizer` が non-null の場合、`_wasmPhonemizer.detectLanguage(text)` が使われる
- `_wasmPhonemizer` が null の場合、既存の `_g2p.detectLanguage(text)` にフォールバック
- 「こんにちは」→ `'ja'`、"Hello" → `'en'`、「你好」→ `'zh'` が正しく検出される

## 実装する内容の詳細

### 変更ファイル: `src/wasm/openjtalk-web/src/index.js`

#### 1. `synthesize()` の言語検出 (L105)

現在:
```javascript
const language = options.language || this._g2p.detectLanguage(text);
```

変更後:
```javascript
const language = options.language
  || (this._wasmPhonemizer
      ? this._wasmPhonemizer.detectLanguage(text)
      : this._g2p.detectLanguage(text));
```

#### 2. `synthesizeStreaming()` の言語検出 (L141)

現在:
```javascript
const language = options.language || this._g2p.detectLanguage(text);
```

変更後:
```javascript
const language = options.language
  || (this._wasmPhonemizer
      ? this._wasmPhonemizer.detectLanguage(text)
      : this._g2p.detectLanguage(text));
```

#### 3. (推奨) ヘルパーメソッドの抽出

同じロジックが2箇所に重複するため、プライベートヘルパーの抽出を推奨:

```javascript
/**
 * Detect language of text, preferring Rust WASM detector when available.
 * @private
 */
_detectLanguage(text) {
  if (this._wasmPhonemizer) {
    return this._wasmPhonemizer.detectLanguage(text);
  }
  return this._g2p.detectLanguage(text);
}
```

`synthesize()` と `synthesizeStreaming()` の両方でこのヘルパーを呼ぶ:
```javascript
const language = options.language || this._detectLanguage(text);
```

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装者 | 1 | 言語検出の分岐実装、ヘルパーメソッド抽出 |
| レビュアー | 1 | 2つの検出器の優先順位、エッジケース (混合言語テキスト) の確認 |

## 提供範囲

**提供するもの:**
- `synthesize()` / `synthesizeStreaming()` の言語検出分岐
- `_detectLanguage()` ヘルパーメソッド

**提供しないもの:**
- Rust WASM の `detectLanguage()` の実装改善 (上流の `piper-wasm` クレートの管轄)
- 混合言語テキスト (例: 「Hello、こんにちは」) の分割処理
- ユーザー向けの言語検出 API の公開

## テスト項目

### ユニットテスト

| テスト名 | 検証内容 | モック方針 |
|---------|---------|-----------|
| `detectLanguage uses wasmPhonemizer when available` | `_wasmPhonemizer` あり → `_wasmPhonemizer.detectLanguage()` が呼ばれる | `detectLanguage` をスパイ化 |
| `detectLanguage falls back to g2p when wasmPhonemizer is null` | `_wasmPhonemizer` なし → `_g2p.detectLanguage()` が呼ばれる | `_g2p.detectLanguage` をスパイ化 |
| `synthesize uses detected language for phonemization` | 自動検出された言語が `_textToPhonemeIds` に渡される | `_textToPhonemeIds` をスパイ化して引数を検証 |
| `explicit language option bypasses detection` | `options.language` が指定された場合、検出メソッドは呼ばれない | 両方の `detectLanguage` のスパイで呼び出しなしを検証 |
| `Japanese text detected as ja` | 「こんにちは」→ `'ja'` | Rust WASM の `detectLanguage` モックが `'ja'` を返す |
| `English text detected as en` | "Hello" → `'en'` | 同上 |
| `Chinese text detected as zh` | 「你好」→ `'zh'` | 同上 |

### E2E テスト

1. デモページで `options.language` を指定せずに「こんにちは」を合成 → 日本語音声が生成される
2. 同様に "Hello, how are you?" → 英語音声が生成される
3. コンソールに言語検出関連のエラーが出ないこと

## 懸念事項

- **2つの検出器の不一致**: Rust WASM と JS G2P の `detectLanguage()` は異なるアルゴリズムを使用する。Rust は Unicode スクリプトベースの `UnicodeLanguageDetector` を使い、JS G2P も同様だが実装の微細な差異がある可能性。`_wasmPhonemizer` の有無で検出結果が変わると、テスト環境とプロダクション環境で挙動が異なるリスク
- **混合言語テキスト**: 「Hello、こんにちは」のような混合テキストで、最初に検出された言語が全体に適用される。現状のアーキテクチャの制約であり、文分割による多言語対応は別スコープ
- **`_wasmPhonemizer` が JA 以外も検出可能**: Rust WASM の `detectLanguage()` は8言語すべてを検出できる。JA のみ Rust WASM パスで処理するが、検出は全言語で Rust WASM が使われる点に注意 (意図的な設計判断)

## レビュー項目

- [ ] `_detectLanguage()` ヘルパーメソッドが `synthesize()` と `synthesizeStreaming()` の両方で使われているか
- [ ] `options.language` 指定時に検出がスキップされること (短絡評価)
- [ ] Rust WASM の `detectLanguage()` が返す言語コードが `language_id_map` のキーと一致するか (例: `'ja'` vs `'ja-JP'`)
- [ ] `_wasmPhonemizer` が null の場合のフォールバックパスが正しく動作するか

## 一から作り直すとしたら

現在の設計では `_wasmPhonemizer` の有無で使用する検出器が切り替わる。これは2つのコードパスが存在し、テストとデバッグの複雑さが増す。

**理想形**: 言語検出を単一の統一検出器に集約する:

```javascript
// 統一言語検出器 — 常に同じアルゴリズム
class UnifiedLanguageDetector {
  detect(text) {
    // Unicode スクリプトベースの検出 (JS 実装)
    // Rust WASM の有無に依存しない
  }
}
```

JS 側に軽量な Unicode スクリプト検出器を実装し、Rust WASM / JS G2P のどちらが利用可能かに関わらず同じ検出結果を返す設計。ただし現時点では Rust WASM の検出器が既に高品質であり、JS G2P にも `detectLanguage()` が存在するため、追加実装のコストに見合わない。

**現在の方式で十分な理由**: Unicode スクリプトベースの検出はどちらの実装も同じ原理 (ひらがな/カタカナ → JA、漢字 → ZH) なので、実用上の差異は極めて小さい。

## 後続タスクへの連絡事項

- **M2 への連絡**: テストでは `_wasmPhonemizer.detectLanguage()` のモックを設定すること。戻り値は言語コード文字列 (`'ja'`, `'en'` 等)。`_wasmPhonemizer` が null のケースと non-null のケースの両方をテストすること
- **M2 への連絡 (重要)**: `_wasmPhonemizer` が存在する場合、JS G2P から `'ja'` が除外されているため、JS G2P の `detectLanguage()` は日本語を返さない。フォールバックパスのテストでは `'ja'` が検出されないことが正常動作
- **将来の拡張**: ストリーミングパスでは文ごとに言語が変わる可能性がある。現在は最初の検出結果を全体に適用しているが、文単位の検出は `TextChunker` との統合で対応可能
