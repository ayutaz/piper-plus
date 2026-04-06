# M1-1: `_init()` に Rust WASM ローダー追加

**マイルストーン**: M1 (PiperPlus に Rust WASM phonemizer を統合)
**依存チケット**: なし
**後続チケット**: M1-2, M1-3, M1-4

## タスク目的とゴール

現在 `PiperPlus._init()` は日本語 G2P に必要な `openjtalkModule` が外部注入されない限り `'ja'` を言語リストから除外しており、日本語音声合成が動作しない。このチケットでは、`_init()` 内で Rust WASM (`WasmPhonemizer`) を `dynamic import()` で自動ロードし、`this._wasmPhonemizer` に保持する。

**完了条件:**
- Rust WASM がある環境で `_init()` 完了後に `this._wasmPhonemizer` が non-null
- Rust WASM がない環境 (ローカル開発等) で `_init()` がエラーなく完了し `this._wasmPhonemizer` が null、`'ja'` が除外されてフォールバック
- JS G2P (`G2P.create()`) は `'ja'` を除いた言語リストで初期化される

## 実装する内容の詳細

### 変更ファイル: `src/wasm/openjtalk-web/src/index.js`

#### 1. コンストラクタに `_wasmPhonemizer` フィールド追加 (L46-52)

```javascript
constructor() {
  this._session = null;
  this._config = null;
  this._g2p = null;
  this._wasmPhonemizer = null;  // 追加
  this._ort = null;
  this._initialized = false;
  this._warmupPromise = null;
}
```

#### 2. `_init()` の phonemizer 初期化セクション書き換え (L247-267)

現在の `openjtalkModule` 注入パターン (L257-263) を Rust WASM 自動ロードに置換:

```javascript
// --- 3. Initialise phonemizer --------------------------

progress({ stage: 'phonemizer', progress: 0, message: 'Initializing phonemizer...' });

let languages = this._config.language_id_map
  ? Object.keys(this._config.language_id_map)
  : undefined;

// Rust WASM phonemizer をロード (日本語 + 全言語対応)
let wasmPhonemizer = null;
if (languages && languages.includes('ja')) {
  try {
    const wasmModule = await import('../dist/rust-wasm/piper_plus_wasm.js');
    await wasmModule.default();  // init() — WASM バイナリロード
    wasmPhonemizer = new wasmModule.WasmPhonemizer(JSON.stringify(this._config));
  } catch (err) {
    console.warn('[piper-plus] Rust WASM G2P failed to load, excluding ja:', err.message);
    languages = languages.filter(l => l !== 'ja');
  }
}

// 非 JA 言語は JS G2P で初期化
const g2pLanguages = languages?.filter(l => l !== 'ja');
this._g2p = await G2P.create({ languages: g2pLanguages });
this._wasmPhonemizer = wasmPhonemizer;

progress({ stage: 'phonemizer', progress: 1, message: 'Phonemizer ready.' });
```

#### 3. 旧 `openjtalkModule` 関連コードの削除

`options.openjtalkModule` / `options.jaDict` の分岐 (L258-261) は Rust WASM に置き換えるため削除。`PiperPlus.initialize()` の JSDoc から `openjtalkModule`/`jaDict` パラメータも削除。

## エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装者 | 1 | `_init()` の書き換え、コンストラクタ変更、旧コード削除 |
| レビュアー | 1 | import パス、エラーハンドリング、既存テストとの整合性確認 |

## 提供範囲

**提供するもの:**
- `_init()` での Rust WASM ローダー実装
- ロード失敗時のフォールバック (ja 除外)
- `this._wasmPhonemizer` の初期化

**提供しないもの:**
- `_textToPhonemeIds()` の日本語分岐 (M1-2)
- `dispose()` でのリソース解放 (M1-4)
- 言語検出の統合 (M1-3)
- テスト (M2)

## テスト項目

### ユニットテスト

| テスト名 | 検証内容 | モック方針 |
|---------|---------|-----------|
| `init sets _wasmPhonemizer when WASM is available` | `language_id_map` に `'ja'` がある場合、`_wasmPhonemizer` が non-null になる | `import()` をモックし `{ default: async () => {}, WasmPhonemizer: class { constructor() {} } }` を返す |
| `init falls back when WASM import fails` | `import()` が例外を投げた場合、`_wasmPhonemizer` が null で `_init()` は正常完了 | `import()` が `throw new Error('not found')` するモック |
| `init skips WASM when ja not in language_id_map` | `language_id_map` に `'ja'` がない場合、`import()` が呼ばれない | `import()` 呼び出しカウンターで検証 |
| `G2P.create receives languages without ja` | JS G2P が `'ja'` を除いた言語リストで初期化される | `G2P.create` のスパイで引数を検証 |

### E2E テスト

1. `dist/rust-wasm/` に WASM ビルド成果物がある状態でデモページを開く
2. コンソールに `[piper-plus] Rust WASM G2P failed to load` が表示されないこと
3. 初期化完了後、開発者ツールで `instance._wasmPhonemizer !== null` を確認

## 懸念事項

- **import パスの環境差**: `../dist/rust-wasm/piper_plus_wasm.js` はソースツリーとデプロイ後で同じ相対パスだが、バンドラー (webpack/vite等) を使う場合はパス解決が異なる可能性がある。`try/catch` で保護しているが、将来的にはパスを設定可能にすることを検討
- **WASM バイナリサイズ**: `piper_plus_wasm_bg.wasm` は ~60MB (gzip ~19MB)。初回ロードに数秒かかるため、`progress` コールバックで WASM ロード中であることをユーザーに通知すべき
- **`openjtalkModule` オプションの後方互換**: このチケットで `openjtalkModule` を削除するため、既存ユーザーがこのオプションを渡している場合は無視される。破壊的変更として CHANGELOG に記載が必要

## レビュー項目

- [ ] `import()` パスが `src/index.js` からの相対パスとして正しいか
- [ ] `try/catch` でキャッチされる例外の範囲 (ネットワークエラー、パースエラー等)
- [ ] `WasmPhonemizer` コンストラクタに渡す `config` の JSON 文字列化が正しいか
- [ ] `G2P.create()` に渡す言語リストから `'ja'` が確実に除外されているか
- [ ] `openjtalkModule` 関連コードが完全に削除されているか
- [ ] `dispose()` での部分初期化クリーンアップ (L274-279) が `_wasmPhonemizer` を考慮しているか

## 一から作り直すとしたら

現在の設計では `PiperPlus._init()` が内部で Rust WASM を `dynamic import()` する。これは「使いやすさ」を優先した設計だが、分離の観点では改善の余地がある。

**理想形**: `PiperPlus.initialize()` の `options` に `wasmPhonemizer` を受け取るインターフェースにする:

```javascript
// ユーザーが事前にロードした phonemizer を注入
const wasmModule = await import('./dist/rust-wasm/piper_plus_wasm.js');
await wasmModule.default();
const phonemizer = new wasmModule.WasmPhonemizer(configJson);

const piper = await PiperPlus.initialize({
  model: 'ayousanz/piper-plus-tsukuyomi-chan',
  wasmPhonemizer: phonemizer,  // 外部注入
});
```

**メリット**: PiperPlus が WASM ローダーの詳細 (パス、初期化順序) を知る必要がなくなり、テストでもモックが容易になる。バンドラー環境でのパス問題も発生しない。

**現在の方式の妥協点**: ユーザーの手間を減らすために自動ロードを選択。ただし将来的に `options.wasmPhonemizer` による外部注入も並行してサポートすることを推奨する。

## 後続タスクへの連絡事項

- **M1-2 への連絡**: `this._wasmPhonemizer` は `WasmPhonemizer` インスタンスまたは `null`。`null` の場合は Rust WASM が利用不可であることを意味する。`_textToPhonemeIds()` で `this._wasmPhonemizer` の存在チェックを行うこと
- **M1-3 への連絡**: `this._wasmPhonemizer` が non-null の場合、`detectLanguage()` メソッドが利用可能。`null` の場合は既存の `this._g2p.detectLanguage()` にフォールバック
- **M1-4 への連絡**: `this._wasmPhonemizer` は `free()` メソッドでリソース解放が必要。`dispose()` で呼び出すこと
- **M2 への連絡**: `import()` のモックは Node.js テスト環境で `import()` を差し替える必要がある。テストヘルパーの検討を推奨
