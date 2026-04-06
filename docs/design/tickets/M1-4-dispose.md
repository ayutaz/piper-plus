# M1-4: `dispose()` でのリソース解放

**マイルストーン**: M1 (PiperPlus に Rust WASM phonemizer を統合)
**依存チケット**: M1-1
**後続チケット**: M2-1

## タスク目的とゴール

M1-1 で追加された `this._wasmPhonemizer` は Rust WASM のヒープメモリを保持している。`dispose()` で `free()` を呼ばないとメモリリークが発生する。このチケットでは `dispose()` に `_wasmPhonemizer` のリソース解放を追加する。

**完了条件:**
- `dispose()` 呼び出し後に `this._wasmPhonemizer` が `null`
- `_wasmPhonemizer.free()` が呼ばれること
- `dispose()` を2回呼んでもエラーにならない (冪等性)
- `_wasmPhonemizer` が元々 `null` の場合もエラーにならない

## 実装する内容の詳細

### 変更ファイル: `src/wasm/openjtalk-web/src/index.js`

#### `dispose()` メソッドの変更 (L166-180)

現在:
```javascript
dispose() {
  if (this._session) {
    if (typeof this._session.release === 'function') {
      this._session.release();
    }
    this._session = null;
  }
  if (this._g2p) {
    this._g2p.dispose();
    this._g2p = null;
  }
  this._warmupPromise = null;
  this._initialized = false;
}
```

変更後:
```javascript
dispose() {
  if (this._session) {
    if (typeof this._session.release === 'function') {
      this._session.release();
    }
    this._session = null;
  }
  if (this._wasmPhonemizer) {
    this._wasmPhonemizer.free();
    this._wasmPhonemizer = null;
  }
  if (this._g2p) {
    this._g2p.dispose();
    this._g2p = null;
  }
  this._warmupPromise = null;
  this._initialized = false;
}
```

### 変更量

追加: 4行 (null チェック + `free()` + null 代入 + 閉じ括弧)。

### `_init()` エラー時のクリーンアップ

`_init()` の `catch` ブロック (L274-279) で `this.dispose()` が呼ばれる。M1-1 で `_wasmPhonemizer` がコンストラクタで `null` 初期化されるため、部分初期化状態でも `dispose()` は安全に動作する (`if (this._wasmPhonemizer)` で null チェック済み)。

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装者 | 1 | `dispose()` への4行追加 |
| レビュアー | 1 | 冪等性、部分初期化時の安全性確認 |

## 提供範囲

**提供するもの:**
- `dispose()` での `_wasmPhonemizer.free()` 呼び出し
- null チェックによる安全なクリーンアップ

**提供しないもの:**
- `Symbol.dispose` / `Symbol.asyncDispose` 対応 (TC39 Explicit Resource Management)
- `_textToPhonemeIds()` 内の `result.free()` (M1-2 のスコープ)
- WeakRef / FinalizationRegistry による自動解放

## テスト項目

### ユニットテスト

| テスト名 | 検証内容 | モック方針 |
|---------|---------|-----------|
| `dispose calls wasmPhonemizer.free()` | `_wasmPhonemizer` が non-null → `free()` が呼ばれる | `free` をスパイ化してカウント検証 |
| `dispose sets wasmPhonemizer to null` | `dispose()` 後に `_wasmPhonemizer === null` | プロパティを直接検証 |
| `dispose is idempotent` | `dispose()` を2回呼んでも例外が発生しない | 2回目の `dispose()` が例外なく完了 |
| `dispose handles null wasmPhonemizer` | `_wasmPhonemizer` が `null` → エラーなし | `_wasmPhonemizer` を null のまま `dispose()` 呼び出し |
| `dispose cleans up on partial init failure` | `_init()` 途中で例外 → `dispose()` が呼ばれ `_wasmPhonemizer` が解放される | `G2P.create()` で例外を投げるモック。`_wasmPhonemizer.free()` が呼ばれることを検証 |

### E2E テスト

1. デモページで音声合成を実行した後、`instance.dispose()` を呼ぶ
2. 開発者ツールの Memory タブで WASM ヒープが解放されていることを確認
3. `dispose()` 後に `instance.synthesize()` を呼ぶと `'PiperPlus is not initialized'` エラーが返ること

## 懸念事項

- **`free()` 後の use-after-free**: `dispose()` 後に `_textToPhonemeIds()` が呼ばれると `_wasmPhonemizer` は `null` なので JS G2P フォールバックに入る。しかし `_g2p` も `null` なため例外が発生する。`_assertReady()` ガードで保護されるが、非同期の race condition に注意
- **`free()` が例外を投げる可能性**: Rust WASM の `free()` がダブルフリーで panic する可能性がある。null チェック (`if (this._wasmPhonemizer)`) で防御しているが、外部から `_wasmPhonemizer.free()` が直接呼ばれた場合は検出できない

## レビュー項目

- [ ] `_wasmPhonemizer` の null チェックが `free()` 呼び出しの前にあるか
- [ ] `free()` 後に `this._wasmPhonemizer = null` が設定されているか
- [ ] `_init()` の `catch` → `dispose()` パスで `_wasmPhonemizer` が正しく解放されるか
- [ ] `dispose()` のリソース解放順序が適切か (session → wasmPhonemizer → g2p)

## 一から作り直すとしたら

現在の `dispose()` は手動のリソース管理パターン。モダン JavaScript では TC39 Explicit Resource Management (`Symbol.dispose` / `using` 宣言) が利用可能。

**理想形**:

```javascript
class PiperPlus {
  [Symbol.dispose]() {
    this.dispose();
  }

  // あるいは Symbol.asyncDispose
  async [Symbol.asyncDispose]() {
    this.dispose();
  }
}

// 利用側
{
  using piper = await PiperPlus.initialize({ model: '...' });
  await piper.synthesize('こんにちは');
} // スコープ終了時に自動 dispose
```

**現在の方式で十分な理由**: `Symbol.dispose` はまだブラウザサポートが限定的 (2026年4月時点)。`dispose()` の手動呼び出しパターンは広く使われており、互換性が高い。将来的に `Symbol.dispose` を追加しても `dispose()` メソッドとの共存は容易。

## 後続タスクへの連絡事項

- **M2-1 への連絡**: テストでは `_wasmPhonemizer` に `{ free: spy, phonemize: stub, detectLanguage: stub }` 形式のモックを使用すること。`dispose()` テストでは `free` スパイの呼び出し回数を検証
- **M2 への連絡 (重要)**: `dispose()` の冪等性テストでは、2回目の `dispose()` 呼び出しで `free()` が再度呼ばれないことを検証すること (null チェックにより防御)
- **将来の拡張**: `FinalizationRegistry` を使った GC ベースの自動解放も検討可能だが、`dispose()` の明示的呼び出しを推奨するドキュメントを維持すべき
