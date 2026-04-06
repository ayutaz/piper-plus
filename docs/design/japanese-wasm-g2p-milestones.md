# Japanese WASM G2P Integration — マイルストーン

> 参照: [技術調査・対応方針](./japanese-wasm-g2p-integration.md)

---

## M1: PiperPlus に Rust WASM phonemizer を統合

**目標**: `PiperPlus._init()` で Rust WASM (`WasmPhonemizer`) を自動ロードし、日本語 G2P として使用する。他言語は既存の JS G2P (`@piper-plus/g2p`) をそのまま使う。

### タスク

#### M1-1: `_init()` に Rust WASM ローダー追加

- **ファイル**: `src/wasm/openjtalk-web/src/index.js`
- **内容**:
  - `language_id_map` に `'ja'` が含まれる場合、`dynamic import()` で `dist/rust-wasm/piper_plus_wasm.js` をロード
  - `await init()` → `new WasmPhonemizer(JSON.stringify(config))` で初期化
  - `this._wasmPhonemizer` に保持
  - ロード失敗時は `console.warn` + `'ja'` を除外してフォールバック
  - JS G2P (`G2P.create()`) は `'ja'` を除いた言語リストで初期化
- **受け入れ基準**:
  - Rust WASM がある環境で `_init()` 完了後 `this._wasmPhonemizer` が non-null
  - Rust WASM がない環境で `_init()` がエラーなく完了し `this._wasmPhonemizer` が null

#### M1-2: `_textToPhonemeIds()` に日本語分岐追加

- **ファイル**: `src/wasm/openjtalk-web/src/index.js`
- **内容**:
  - `language === 'ja' && this._wasmPhonemizer` の場合、Rust WASM の `phonemize()` を直接呼ぶ
  - `result.phonemeIds` (Int32Array) → `Array.from()` で number[] に変換
  - `result.prosodyFeatures` (Int32Array, flat) → 3要素ずつグループ化して number[][] に変換
  - `result.free()` でメモリ解放
  - 他言語は既存の `this._g2p.encode()` パスをそのまま使用
- **受け入れ基準**:
  - 日本語テキスト → phonemeIds が BOS で始まり EOS で終わる
  - prosodyFeatures が phonemeIds と同じ長さの [a1,a2,a3] 配列
  - 他言語のパスが変更なく動作

#### M1-3: 言語検出の統合

- **ファイル**: `src/wasm/openjtalk-web/src/index.js`
- **内容**:
  - `synthesize()` / `synthesizeStreaming()` 内の言語検出で:
    - `_wasmPhonemizer` がある場合: `_wasmPhonemizer.detectLanguage(text)` を使用
    - ない場合: 既存の `_g2p.detectLanguage(text)` を使用
  - 日本語テキスト (ひらがな/カタカナ含む) で確実に `'ja'` が返ること
- **受け入れ基準**:
  - `'こんにちは'` → `'ja'` が検出される
  - `'Hello'` → `'en'` が検出される
  - `'你好'` → `'zh'` が検出される

#### M1-4: `dispose()` でのリソース解放

- **ファイル**: `src/wasm/openjtalk-web/src/index.js`
- **内容**:
  - `dispose()` に `_wasmPhonemizer.free()` を追加
  - `_wasmPhonemizer = null` でリセット
- **受け入れ基準**:
  - `dispose()` 後に `_wasmPhonemizer` が null
  - `dispose()` を2回呼んでもエラーにならない

---

## M2: テスト

**目標**: M1 の全変更をテストでカバーし、CI で事前検知できるようにする。

### タスク

#### M2-1: Rust WASM ローダーのユニットテスト

- **ファイル**: `src/wasm/openjtalk-web/test/js/test-piper-plus-wasm-g2p.js` (新規)
- **テストケース**:
  1. `_init()` で `_wasmPhonemizer` が設定される (WASM import をモック)
  2. Rust WASM ロード失敗時に `'ja'` が除外されフォールバック
  3. `language_id_map` に `'ja'` がない場合は WASM ロードをスキップ
  4. `dispose()` で `_wasmPhonemizer.free()` が呼ばれる
- **モック方針**:
  - `import()` をモックして WasmPhonemizer のスタブを返す
  - phonemize() は `{ phonemeIds: Int32Array, prosodyFeatures: Int32Array, phonemeCount, free() }` を返す

#### M2-2: `_textToPhonemeIds()` の分岐テスト

- **ファイル**: 同上 (M2-1 と同じファイル)
- **テストケース**:
  1. JA + wasmPhonemizer あり → Rust WASM phonemize() が呼ばれる
  2. JA + wasmPhonemizer なし → JS G2P encode() にフォールバック
  3. EN + wasmPhonemizer あり → JS G2P encode() が使われる (WASM は JA のみ)
  4. phonemize() の戻り値が `_infer()` の期待する形式に変換される
  5. `result.free()` が呼ばれる (メモリリーク防止)

#### M2-3: CI にテスト追加

- **ファイル**: `.github/workflows/test-webassembly.yml`
- **内容**: M2-1, M2-2 のテストファイルを実行ステップに追加
- **受け入れ基準**: CI で全テストパス

---

## M3: デモページの動作確認

**目標**: GitHub Pages のデモページで日本語テキスト → 音声合成が動作する。

### タスク

#### M3-1: デモページの動作確認

- **確認手順**:
  1. https://ayutaz.github.io/piper-plus/ にアクセス
  2. 初期化完了 (「準備完了！」表示)
  3. 日本語テキスト「こんにちは、つくよみちゃんです。」を入力
  4. 「音声合成」ボタン → 音声が再生される
  5. コンソールにエラーなし
- **受け入れ基準**:
  - `openjtalkModule is required` エラーが出ない
  - `is not a function` エラーが出ない
  - 日本語・英語・中国語の3言語で音声合成が動作

#### M3-2: 他言語の回帰テスト

- **確認手順**: デモページで以下のテキストを合成
  - EN: "Hello, how are you today?"
  - ZH: "你好，今天天气很好。"
  - ES: "¿Hola, cómo estás hoy?"
  - FR: "Bonjour, comment allez-vous?"
  - PT: "Olá, como você está hoje?"
- **受け入れ基準**: 全言語で音声が生成され、以前と同等の品質

---

## 依存関係

```
M1-1 (WASM ローダー)
  ↓
M1-2 (_textToPhonemeIds 分岐)
  ↓
M1-3 (言語検出) ← M1-1 に依存
  ↓
M1-4 (dispose)
  ↓
M2-1, M2-2, M2-3 (テスト) ← M1 全タスクに依存
  ↓
M3-1, M3-2 (動作確認) ← M2 に依存
```

## 見積もり

| マイルストーン | タスク数 | 規模 |
|--------------|---------|------|
| M1 (実装) | 4 | `index.js` 1ファイルの変更 (~50行追加) |
| M2 (テスト) | 3 | テスト1ファイル新規 + CI 更新 |
| M3 (確認) | 2 | デプロイ + ブラウザ確認 |
