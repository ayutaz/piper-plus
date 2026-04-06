# M1-M3 再設計レトロスペクティブ — 一から作り直すとしたら

> 現在の実装 (M1-1〜M2-3) が完了した時点でのレビュー。  
> 4つの観点 (アーキテクチャ / テスト / API 設計 / DevOps・DX) から  
> 「一から作り直すとしたら」の設計思想を議論した結果をまとめる。

---

## 1. アーキテクチャ: PiperPlus の責務と条件分岐の解消

### 現在の問題

PiperPlus クラスは TTS オーケストレーター (`text → phonemize → infer → audio`) であるべきだが、G2P の実装詳細を直接知っている。

**条件分岐の散在 (Shotgun Surgery)**:

| メソッド | 条件 |
|---------|------|
| `_init()` | `languages.includes('ja')` → WASM ロード |
| `_textToPhonemeIds()` | `language === 'ja' && this._wasmPhonemizer` |
| `_detectLanguage()` | `if (this._wasmPhonemizer)` |
| `dispose()` | `if (this._wasmPhonemizer)` |

新しい WASM 対応言語を追加するたびに 4 箇所を修正する必要がある (Open-Closed Principle 違反)。

### 再設計: Strategy + Adapter パターン

```
PiperPlus
  └── CompositePhonemizer (PhonemizerInterface)
        ├── RustWasmPhonemizerAdapter (JA + 全言語)
        └── JsG2pPhonemizerAdapter (EN, ZH, ES, FR, PT)
```

#### 統一インターフェース

```javascript
/**
 * @typedef {Object} PhonemizeOutput
 * @property {number[]} phonemeIds - BOS/EOS/PAD 挿入済み
 * @property {number[][]|null} prosodyFeatures - [[a1, a2, a3], ...]
 */

/** @interface PhonemizerInterface */
class PhonemizerInterface {
  /** @returns {string[]} */
  get supportedLanguages() {}

  /** @returns {PhonemizeOutput} */
  encode(text, language) {}

  /** @returns {string} */
  detectLanguage(text) {}

  dispose() {}
}
```

PiperPlus が必要とするのは `encode(text, language) → { phonemeIds, prosodyFeatures }` のみ。中間トークン列、`phonemeIdMap` の受け渡し、`result.free()` の呼び出しは全てアダプター内部に隠蔽される。

#### RustWasmPhonemizerAdapter

```javascript
class RustWasmPhonemizerAdapter {
  constructor(wasmPhonemizer) { this._wasm = wasmPhonemizer; }

  encode(text, language) {
    const result = this._wasm.phonemize(text, language);
    try {
      const phonemeIds = Array.from(result.phonemeIds);
      let prosodyFeatures = null;
      const flat = result.prosodyFeatures;
      if (flat && flat.length > 0) {
        prosodyFeatures = [];
        for (let i = 0; i < flat.length; i += 3) {
          prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
        }
      }
      return { phonemeIds, prosodyFeatures };
    } finally {
      result.free(); // WASM メモリ解放をここでカプセル化
    }
  }

  // ... detectLanguage, dispose も同様にラップ
}
```

#### JsG2pPhonemizerAdapter

```javascript
class JsG2pPhonemizerAdapter {
  constructor(g2p, phonemeIdMap) {
    this._g2p = g2p;
    this._phonemeIdMap = phonemeIdMap;
  }

  encode(text, language) {
    const result = this._g2p.encode(text, this._phonemeIdMap, { language });
    // prosodyFlat → prosodyFeatures 変換をここで行う
    // ...
    return { phonemeIds: result.phonemeIds, prosodyFeatures };
  }
}
```

#### CompositePhonemizer (言語ルーティング)

```javascript
class CompositePhonemizer {
  constructor({ phonemizers, fallback }) {
    this._routeMap = phonemizers; // Map<string, PhonemizerInterface>
    this._fallback = fallback;
  }

  encode(text, language) {
    const lang = language || this.detectLanguage(text);
    const p = this._routeMap.get(lang) || this._fallback;
    return p.encode(text, lang);
  }

  dispose() {
    const disposed = new Set();
    for (const p of this._routeMap.values()) {
      if (!disposed.has(p)) { p.dispose(); disposed.add(p); }
    }
  }
}
```

#### リファクタリング後の PiperPlus

```javascript
// _textToPhonemeIds: 条件分岐が消える
async _textToPhonemeIds(text, language) {
  return this._phonemizer.encode(text, language);
}

// _detectLanguage: 条件分岐が消える
_detectLanguage(text) {
  return this._phonemizer.detectLanguage(text);
}

// dispose: 条件分岐が消える
dispose() {
  if (this._session) { this._session.release(); this._session = null; }
  if (this._phonemizer) { this._phonemizer.dispose(); this._phonemizer = null; }
  this._initialized = false;
}
```

### DI (Dependency Injection) と WASM ローダーの分離

WASM のロードロジックを PiperPlus から分離する:

```javascript
// _init() 内: factory を DI で注入可能にする
const factory = options._wasmPhonemizerFactory || defaultWasmFactory;
const wasmAdapter = await factory(wasmUrl, config);
```

これによりテスト時に `dynamic import()` のモック不要でモック phonemizer を注入できる。

### 遅延ロードの判断

初期化時のロード (現在の設計) は正しい判断:
- WASM ロードは重い (~30MB NAIST-JDIC) → 合成呼び出しの初回レイテンシが許容不可
- `_init()` は既に async であり、ここでの待機はユーザー期待に沿う
- フェイルファスト: WASM が壊れている場合、初期化時にフォールバック可能

ただし `CompositePhonemizer` に遅延ロード機能を追加することで将来対応可能。

---

## 2. テスト戦略: mock の限界と統合テストの必要性

### 現在のテストピラミッド

| レイヤー | テスト数 | 評価 |
|---------|---------|------|
| Rust wasm_bindgen_test | 21 | **良好**: 実 WASM バイナリで検証 |
| JS ユニット (mock WASM) | 20 | **問題あり**: mock と実 WASM の乖離リスク |
| JS 統合テスト | 10 | 中程度: ja 含む config の WASM ロードパス未検証 |
| E2E | 0 | **欠如**: ブラウザ動作は手動テストのみ |

### 問題点

#### A. mock WasmPhonemizer の信頼性

`createMockWasmPhonemizer()` は以下で実際の Rust WASM と乖離:
- `phonemize()` 戻り値: mock は固定 `Int32Array` を返すが、実際は wasm-bindgen のプロパティ getter 経由
- `free()` 後アクセス: mock はフラグ制御、実際は WASM ヒープ解放でパニック
- `detectLanguage()`: mock は JS 正規表現、実際は Unicode Script ベース + 辞書ヒント

#### B. dynamic import() のモック困難

Node.js の `node:test` では `import()` を差し替える標準的な方法がない。テストは「WASM ロード失敗 → フォールバック」パスしか検証できない。

#### C. テストされていないケース

- 混合テキスト「Hello、こんにちは world」での言語検出
- WASM メモリリーク (長時間使用シナリオ)
- 並行 `synthesize()` 呼び出しの安全性
- prosodyFeatures の長さが 3 の倍数でない場合
- 大規模テキスト (数千文字) の処理

### 再設計: 4層テスト戦略

#### Layer 1: Rust 単体テスト (維持 + 拡充)

既存の 21 テストは十分。追加すべきは混合テキスト・大規模テキスト・辞書エラーケース。

#### Layer 2: JS ユニットテスト (DI ベースに移行)

private フィールド代入を避け、`_wasmPhonemizerFactory` DI で注入:

```javascript
const piper = await PiperPlus.initialize({
  model: 'test', ort: mockOrt,
  _wasmPhonemizerFactory: async () => createMockWasmPhonemizer(),
});
```

#### Layer 3: JS-WASM 統合テスト (新設)

CI で `wasm-pack build` → 実 WASM バイナリでテスト:

```javascript
import { initSync, WasmPhonemizer } from '../../dist/rust-wasm/piper_plus_wasm.js';
const wasmBytes = readFileSync('dist/rust-wasm/piper_plus_wasm_bg.wasm');
initSync(wasmBytes);
const phonemizer = new WasmPhonemizer(JSON.stringify(config));
const result = phonemizer.phonemize('こんにちは', 'ja');
// ... 実際の戻り値の型・内容を検証
```

#### Layer 4: Playwright E2E テスト (新設)

**Phase 1 (smoke test)**: WASM ロード → phonemize → synthesize → AudioResult
**Phase 2 (ブラウザ互換性)**: Chrome/Firefox/Safari + ネットワーク障害
**Phase 3 (パフォーマンス)**: phonemize 処理時間のベースライン比較

#### 推奨テスト配分

| レイヤー | テスト数 | 実行頻度 |
|---------|---------|---------|
| Rust unit | 25-30 | PR ごと |
| JS unit (mock) | 15-20 | PR ごと |
| JS-WASM 統合 (real) | 10-15 | WASM rebuild 時 |
| Playwright E2E | 5-10 | dev push 時 |

---

## 3. API 設計: PhonemizerInterface の統一

### 現在の API の非対称性

| 項目 | JS G2P | Rust WASM |
|------|--------|-----------|
| 初期化 | `G2P.create()` (async factory) | `new WasmPhonemizer(json)` |
| phonemize | `encode(text, phonemeIdMap, {language})` | `phonemize(text, lang)` |
| 戻り値型 | `{phonemeIds: number[], prosodyFlat}` | `{phonemeIds: Int32Array, prosodyFeatures: Int32Array}` |
| メモリ管理 | GC (`dispose()`) | WASM heap (`free()` 必須) |
| 言語検出 | G2P のメソッド | WasmPhonemizer のメソッド |

### 再設計: 統一メソッド `encode(text, language)`

PiperPlus の `_infer()` が必要とするのは `{ phonemeIds: number[], prosodyFeatures: number[][] | null }` のみ。

`encode()` を統一メソッドにする理由:
- `phonemize()` (中間トークン列) は推論パスでは不要
- `phonemeIdMap` の受け渡しはアダプター内部で完結すべき
- WASM の `result.free()` はアダプターの `try/finally` で確実に呼ぶ

```typescript
interface PhonemizerInterface {
  encode(text: string, language?: string): PhonemizeOutput;
  detectLanguage(text: string): string;
  readonly supportedLanguages: readonly string[];
  dispose(): void;
}

interface PhonemizeOutput {
  phonemeIds: number[];
  prosodyFeatures: [number, number, number][] | null;
}
```

### 将来の拡張性

新しい G2P エンジン (ONNX ベース Neural G2P 等) を追加する場合:
1. `PhonemizerInterface` を実装するアダプターを作成
2. `CompositePhonemizer` の Map に登録
3. PiperPlus のコード変更なし

---

## 4. DevOps / DX: デプロイとローカル開発体験

### 現在の問題

| 問題 | 影響 |
|------|------|
| WASM (57MB raw / 19MB gzip) が GitHub Pages に直置き | 帯域制限 100GB/月 ≈ 1,750回/月で上限 |
| ローカルに `dist/rust-wasm/` が存在しない | ローカルで日本語テスト不可 |
| sed 書き換え 30 行超 | デプロイの最大リスク |
| 実 WASM の統合テストが CI にない | mock と実挙動の乖離が検出不可 |

### 再設計

#### A. WASM バイナリサイズ最適化 (最優先)

`ja-lite` (外部辞書) をデモのデフォルトにする:
- `ja-external` feature で辞書を除外 → WASM 10MB 以下
- 辞書は CDN から遅延ダウンロード + IndexedDB キャッシュ
- 既に `setJapaneseDictionary()` API が存在するため実装コスト低

#### B. ローカル DX 改善

```bash
# Rust toolchain 不要で WASM バイナリをセットアップ
npm run setup:wasm
# → GitHub Releases から最新 WASM をダウンロード → dist/rust-wasm/ に配置
```

#### C. sed 書き換えの撲滅

HTML テンプレートにプレースホルダーを使用:
```html
<script type="importmap">
{"imports": {"@piper-plus/g2p": "__BASE_URL__/g2p/src/index.js"}}
</script>
```
デプロイ時に 1 行で置換: `sed -i 's|__BASE_URL__|.|g' deploy/index.html`

#### D. CI パイプラインの理想形

```
Stage 1: wasm-build → artifact upload
Stage 2: test-wasm-integration → artifact download → 実 WASM で統合テスト
Stage 3: deploy (条件分岐)
  → main マージ → GitHub Pages
  → タグ push → npm publish + GitHub Release
```

#### E. ホスティング

Cloudflare Pages を推奨:
- 帯域無制限 (無料プラン)
- 自動 Brotli 圧縮 (57MB → ~15MB)
- カスタム `Cache-Control` ヘッダー設定可能

---

## 改善ロードマップ (優先度順)

| 優先度 | 施策 | 効果 | 工数 |
|--------|------|------|------|
| P0 | PhonemizerInterface + Adapter パターン | 条件分岐解消、拡張性向上 | 中 |
| P0 | `ja-lite` デモデフォルト化 + 辞書遅延ロード | ページロード 57MB → ~5MB | 中 |
| P0 | sed → プレースホルダー方式 | デプロイ安定性向上 | 小 |
| P1 | DI パターンでテスタビリティ向上 | private フィールド代入撲滅 | 小 |
| P1 | 実 WASM バイナリ統合テスト CI | mock 乖離の検出 | 中 |
| P1 | `npm run setup:wasm` スクリプト | ローカル DX 大幅改善 | 小 |
| P2 | Playwright E2E テスト | デプロイ後の動作保証 | 大 |
| P2 | Cloudflare Pages 移行 | 帯域問題解消 + Brotli | 中 |

---

## まとめ: 設計思想の転換

**現在の思想**: 「PiperPlus が全てを知っている」  
→ WASM ロード、言語判定、型変換、メモリ管理が PiperPlus に集中

**再設計の思想**: 「PiperPlus は phonemize の結果だけを知る」  
→ PhonemizerInterface を通じて全ての G2P 実装を統一的に扱い、  
　条件分岐・型変換・メモリ管理はアダプター層に委譲

この転換により:
- 新言語追加: 4箇所修正 → Adapter 1つ追加
- テスト: private フィールド代入 → DI でモック注入
- `_textToPhonemeIds()`: 25行の分岐 → `return this._phonemizer.encode(text, language)` の1行
