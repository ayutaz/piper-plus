# Japanese WASM G2P Integration — 技術調査・対応方針

## 現状の問題

`PiperPlus._init()` が `G2P.create({ languages })` を呼ぶ際、日本語 G2P に必要な `openjtalkModule` を渡していない。現在の回避策として `'ja'` を言語リストから除外しているが、日本語が動作しない。

## アーキテクチャ概要

### 2つの G2P パス

| パス | 技術 | 対応言語 | 辞書 | 状態 |
|------|------|----------|------|------|
| **JS G2P** (`@piper-plus/g2p`) | ルールベース JS | EN, ZH, KO, ES, FR, PT, SV | 不要 | 動作中 |
| **JS G2P (JA)** (`JapaneseG2P`) | OpenJTalk C WASM (Emscripten) | JA | 外部注入必須 | 未統合 |
| **Rust WASM** (`WasmPhonemizer`) | jpreprocess (Rust) | JA + 全8言語 | バンドル済み (~30MB) | ビルド済み・未統合 |

### デプロイ先の構成

```
deploy/
├── dist/rust-wasm/              # Rust WASM (wasm-pack ビルド済み)
│   ├── piper_plus_wasm.js       # ES module wrapper
│   └── piper_plus_wasm_bg.wasm  # バイナリ (~60MB, ~19MB gzip)
├── src/index.js                 # PiperPlus (G2P.create 呼び出し元)
├── g2p/src/                     # @piper-plus/g2p (JapaneseG2P 含む)
└── index.html                   # デモページ
```

## Rust WASM API

### 初期化

```javascript
import init, { WasmPhonemizer } from './dist/rust-wasm/piper_plus_wasm.js';
await init();  // WASM バイナリをロード (1回のみ)
const phonemizer = new WasmPhonemizer(JSON.stringify(config));
```

### phonemize()

```javascript
const result = phonemizer.phonemize('こんにちは', 'ja');
// result.phonemeIds:      Int32Array — BOS/PAD/EOS 付き、ONNX 推論可能
// result.prosodyFeatures: Int32Array — [a1,a2,a3, a1,a2,a3, ...] フラット
// result.phonemeCount:    number
```

**重要**: Rust WASM は `phonemize()` 1回で phonemeIds (エンコード済み) を返す。JS G2P は phonemize → encode の2ステップ。

### detect_language() / get_supported_languages()

```javascript
phonemizer.detectLanguage('こんにちは');       // → 'ja'
phonemizer.getSupportedLanguages();             // → ['ja', 'en', 'zh', ...]
```

## PiperPlus の合成データフロー

```
text → _textToPhonemeIds(text, language)
       │
       ├─ G2P.encode(text, phonemeIdMap, { language })
       │  └─ returns { phonemeIds: number[], prosodyFlat: number[] | null }
       │
       └─ prosodyFlat → prosodyFeatures: number[][] (3要素ずつグループ化)
       
    → _infer(phonemeIds, prosodyFeatures, scales)
       │
       ├─ inputTensor:    int64 [1, seq_len]  — BigInt64Array に変換
       ├─ lengthTensor:   int64 [1]
       ├─ scalesTensor:   float32 [3]
       └─ prosodyTensor:  int64 [1, seq_len, 3] (optional)
       
    → audioData: Float32Array
```

## 対応方針

### 方針: PiperPlus._init() で Rust WASM を自動ロード

`@piper-plus/g2p` の `JapaneseG2P` (C WASM) は使わず、Rust WASM の `WasmPhonemizer` を日本語 G2P として直接使う。

### 変更箇所

#### 1. `src/wasm/openjtalk-web/src/index.js` (PiperPlus)

`_init()` の G2P 初期化部分を変更:

```javascript
// --- 3. Initialise phonemizer ---

// Rust WASM phonemizer をロード (日本語 + 全言語対応)
let wasmPhonemizer = null;
if (languages && languages.includes('ja')) {
  try {
    const wasmModule = await import('../dist/rust-wasm/piper_plus_wasm.js');
    await wasmModule.default();  // init()
    wasmPhonemizer = new wasmModule.WasmPhonemizer(JSON.stringify(this._config));
  } catch (err) {
    console.warn('[piper-plus] Rust WASM G2P failed to load, excluding ja:', err.message);
    languages = languages.filter(l => l !== 'ja');
  }
}

// 非 JA 言語は JS G2P で初期化
const g2pLanguages = languages?.filter(l => l !== 'ja');
const g2p = await G2P.create({ languages: g2pLanguages });

this._g2p = g2p;
this._wasmPhonemizer = wasmPhonemizer;
```

#### 2. `_textToPhonemeIds()` の変更

```javascript
async _textToPhonemeIds(text, language) {
  // 日本語: Rust WASM を直接使用
  if (language === 'ja' && this._wasmPhonemizer) {
    const result = this._wasmPhonemizer.phonemize(text, 'ja');
    const phonemeIds = Array.from(result.phonemeIds);
    
    let prosodyFeatures = null;
    const flat = result.prosodyFeatures;
    if (flat && flat.length > 0) {
      prosodyFeatures = [];
      for (let i = 0; i < flat.length; i += 3) {
        prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
      }
    }
    result.free();
    return { phonemeIds, prosodyFeatures };
  }

  // 他言語: 既存の JS G2P パス
  const phonemeIdMap = this._config.phoneme_id_map;
  const result = this._g2p.encode(text, phonemeIdMap, { language });
  // ... (既存のコード)
}
```

#### 3. `dispose()` の変更

```javascript
dispose() {
  // ... 既存のコード ...
  if (this._wasmPhonemizer) {
    this._wasmPhonemizer.free();
    this._wasmPhonemizer = null;
  }
}
```

#### 4. `detectLanguage()` の変更

`synthesize()` 内の言語検出で、`_wasmPhonemizer` がある場合はそちらを優先:

```javascript
const language = options.language
  || (this._wasmPhonemizer
      ? this._wasmPhonemizer.detectLanguage(text)
      : this._g2p.detectLanguage(text));
```

### テスト方針

| テスト | 内容 |
|--------|------|
| ユニットテスト | Rust WASM ロード失敗時に ja が除外されフォールバック |
| ユニットテスト | `_wasmPhonemizer` が `_textToPhonemeIds` で使われる |
| 統合テスト | `phonemize()` の戻り値形式が `_infer()` の期待と一致 |
| E2E (ブラウザ) | デモページで日本語テキスト → 音声合成 |

### Rust WASM と JS G2P の phonemeIds 互換性

| 項目 | Rust WASM | JS G2P |
|------|-----------|--------|
| 型 | `Int32Array` | `number[]` |
| BOS/EOS | 含む | 含む |
| PAD | 含む | 含む |
| エンコーディング | `phoneme_id_map` ベース | 同じ |
| prosody | `Int32Array` (flat) | `number[]` (flat) |

→ `Array.from()` で変換すれば互換。

### import パスの考慮

`src/index.js` から Rust WASM を `import()` する場合のパス:
- ソースツリー: `../dist/rust-wasm/piper_plus_wasm.js`
- デプロイ後: `../dist/rust-wasm/piper_plus_wasm.js` (同じ相対パス)

`dist/rust-wasm/` はローカルでは存在しない (CI でビルド) ため、`import()` は `try/catch` で囲んで失敗時にフォールバックする。

### リスクと対策

| リスク | 対策 |
|--------|------|
| WASM バイナリが大きい (~19MB gzip) | 初回ロード後はブラウザキャッシュ |
| ローカル開発で dist/rust-wasm がない | try/catch + ja 除外フォールバック |
| phonemeIds の互換性問題 | テストで Rust WASM と JS G2P の出力を比較 |
| メモリリーク | `result.free()` + `dispose()` で解放 |
