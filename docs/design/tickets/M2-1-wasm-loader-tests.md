# M2-1: Rust WASM ローダーのユニットテスト

**マイルストーン**: M2
**依存チケット**: M1-1, M1-4
**後続チケット**: M2-3, M3-1

## タスク目的とゴール

M1-1 で実装した `_init()` 内の Rust WASM ローダーと、M1-4 の `dispose()` リソース解放が正しく動作することをユニットテストで検証する。WASM バイナリが存在しない CI/ローカル環境でもテストが実行可能なように、`dynamic import()` をモックする戦略を採用する。

## 実装する内容の詳細

新規テストファイル `src/wasm/openjtalk-web/test/js/test-piper-plus-wasm-g2p.js` を作成する。

### テストケース

1. **WASM ロード成功**: `import()` が正常に解決した場合、`_init()` 完了後に `_wasmPhonemizer` が non-null になること
2. **WASM ロード失敗フォールバック**: `import()` が reject した場合、`console.warn` が出力され `'ja'` が言語リストから除外されること。`_wasmPhonemizer` は null であること
3. **JA 非含有時のスキップ**: `language_id_map` に `'ja'` がない場合、`import()` が呼ばれず WASM ロードがスキップされること
4. **dispose() リソース解放**: `dispose()` 呼び出しで `_wasmPhonemizer.free()` が呼ばれ、`_wasmPhonemizer` が null にリセットされること
5. **dispose() 二重呼び出し安全性**: `dispose()` を2回呼んでもエラーにならないこと

### モック戦略

`dynamic import()` をモックして、以下のスタブを返す:

```javascript
const fakeWasmModule = {
  default: async () => {},  // init()
  WasmPhonemizer: class {
    constructor(configJson) { this._config = configJson; }
    phonemize(text, lang) {
      return {
        phonemeIds: new Int32Array([1, 42, 43, 2]),
        prosodyFeatures: new Int32Array([-2, 1, 5, -2, 1, 5]),
        phonemeCount: 2,
        free() {},
      };
    }
    detectLanguage(text) { return 'ja'; }
    getSupportedLanguages() { return ['ja', 'en', 'zh']; }
    free() {}
  },
};
```

既存テスト (`test-piper-plus-g2p-init.js`) のパターンに従い、`globalThis.fetch` と `globalThis.ort` もモックする。

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| テストライター | 1 | テストファイルの作成、モック設計、全テストケースの実装 |

## 提供範囲

- `src/wasm/openjtalk-web/test/js/test-piper-plus-wasm-g2p.js` (新規作成)
- M1-1 (WASM ローダー) と M1-4 (dispose) に対応するテストのみ。`_textToPhonemeIds` 分岐テストは M2-2 で実装する

## テスト項目

### ユニットテスト

| # | テストケース | 検証内容 |
|---|------------|----------|
| 1 | WASM ロード成功 | `_wasmPhonemizer !== null` |
| 2 | WASM ロード失敗 | `_wasmPhonemizer === null` かつ `console.warn` 呼び出し |
| 3 | JA 非含有時スキップ | `import()` が呼ばれない |
| 4 | dispose() 正常 | `free()` 呼び出し + `_wasmPhonemizer === null` |
| 5 | dispose() 二重呼び出し | エラーが発生しない |

### E2E テスト

M2-1 では E2E テストは対象外。M3-1 でブラウザ環境の E2E を実施する。

## 懸念事項

- **`_wasmPhonemizer` のアクセス**: プライベートフィールド (`#wasmPhonemizer`) の場合、テストから直接アクセスできない。既存の `create-initialized-piper.js` ヘルパーのように、内部状態を公開するアクセサか、`dispose()` 後の動作変化で間接検証する方法が必要
- **`import()` のモック方法**: Node.js の `--test` ランナーでは `import()` を直接モックできない。M1-1 実装時にモック可能な設計 (例: ローダー関数の分離、テスト用フックの注入) を考慮する必要がある
- **既存テストとの競合**: `globalThis` のモックが他テストに影響しないよう `beforeEach` / `afterEach` で確実にリストアすること

## レビュー項目

- [ ] 全5テストケースが実装されていること
- [ ] モックのリストアが `afterEach` で確実に行われていること
- [ ] `node --test test/js/test-piper-plus-wasm-g2p.js` で全テストパスすること
- [ ] 既存テスト (`npm test`) が壊れていないこと
- [ ] テストが CI (Node.js 20) で実行可能であること

## 一から作り直すとしたら

テストヘルパーファクトリの設計を再検討すべきである。既存の `create-initialized-piper.js` は `_init()` をバイパスして内部状態を直接設定するパターンだが、これでは `_init()` 内のロジック (今回の WASM ローダー含む) がテストされない。

改善案:
- **WasmPhonemizer モック専用ファクトリ**: `createMockWasmPhonemizer()` を共通ヘルパーとして切り出し、M2-1 と M2-2 で共有する
- **`_init()` をテスト可能にする設計**: ローダー関数を依存注入可能にする (例: `_init({ wasmLoader })`) ことで、テスト時にモックを渡しやすくする
- **`create-initialized-piper.js` の改善**: `_init()` を実際に呼ぶモードを追加し、内部状態の直接設定パターンから脱却する

## 後続タスクへの連絡事項

- M2-2 で同じテストファイルに `_textToPhonemeIds` のテストを追加する。モック (`fakeWasmModule`) の定義は共通化してファイル上部に配置すること
- M2-3 で CI ワークフローにこのテストファイルを追加する必要がある
- `WasmPhonemizer` モックのインターフェース (`phonemize`, `detectLanguage`, `free`) は M1 実装の API に合わせて調整すること
