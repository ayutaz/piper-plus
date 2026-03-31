# P3-002: OpenJTalk WASM の DI 化

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: FR-301
> 依存チケット: P3-001
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

現在の `SimpleUnifiedPhonemizer.initializeOpenJTalk()` は OpenJTalk WASM モジュールの読み込みパス (`jsPath`, `wasmPath`) を内部で自動解決しており、GitHub Pages 対応のハードコードされたロジック (`window.location.hostname.includes('github.io')`) が含まれている。この結合を排除し、OpenJTalk WASM モジュールをコンストラクタ経由で外部注入可能にする。

### ゴール

- `G2P.create({ openjtalkModule })` で事前ロード済みの OpenJTalk WASM モジュールを注入できる
- OpenJTalk WASM の自動パス解決ロジック (jsPath/wasmPath) を G2P パッケージ内部から排除する
- テスト時にモック OpenJTalk モジュールを注入できる
- OpenJTalk WASM なしの初期化 (`languages: ['en']`) が正常に動作する
- 辞書データ (`JaDictData`) の注入と OpenJTalk モジュールの注入が独立している

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 変更 | `src/wasm/g2p/src/ja/index.js` | OpenJTalk モジュールをコンストラクタ引数として受け取る |
| 変更 | `src/wasm/g2p/src/index.js` | `G2POptions.openjtalkModule` を JA G2P に伝搬する |
| 新規 | `src/wasm/g2p/src/ja/openjtalk-adapter.js` | OpenJTalk WASM のラッパーアダプタ (メモリ管理、エラー変換) |
| 変更 | `src/wasm/g2p/src/ja/index.js` | `OpenJTalkAdapter` 経由で WASM 呼び出しを行う |

### 実装手順

1. **`OpenJTalkAdapter` の作成**: OpenJTalk WASM モジュールの低レベル呼び出し (`allocateUTF8`, `_openjtalk_synthesis_labels`, `_free`, `FS.writeFile`, `FS.mkdir`) をラップする薄いアダプタを作成する。これにより:
   - WASM モジュールの具体的なインターフェースが 1 箇所に集約される
   - テスト時にアダプタのモックが容易になる
   - メモリリーク防止 (free の確実な呼び出し) が保証される

2. **JapaneseG2P のリファクタリング**: 現在の `initializeOpenJTalk()` から以下を分離:
   - WASM モジュール読み込み (jsPath/wasmPath 解決) → **呼び出し側の責務** (G2P パッケージ外部)
   - FS 操作 (辞書ファイル書き込み) → `OpenJTalkAdapter.loadDictionary(dictData)`
   - OpenJTalk 初期化 (`_openjtalk_initialize`) → `OpenJTalkAdapter.initialize()`
   - ラベル取得 (`_openjtalk_synthesis_labels`) → `OpenJTalkAdapter.synthesizeLabels(text)`

3. **GitHub Pages ロジックの除去**: `adjustPathForDeployment()`, `adjustPathForGitHubPages()`, `window.location.hostname.includes('github.io')` のチェックを全て除去する。これらはアプリケーション層の責務であり G2P パッケージには含めない。

4. **初期化フロー**:
   ```
   // アプリケーション側 (piper-plus または直接利用)
   const OpenJTalkModule = (await import('./openjtalk.js')).default;
   const module = await OpenJTalkModule({ locateFile: ... });

   // G2P パッケージ側
   const g2p = await G2P.create({
       openjtalkModule: module,  // 事前ロード済み
       jaDict: dictData,          // DictLoader から取得済み
   });
   ```

### API / インターフェース

```javascript
// src/wasm/g2p/src/ja/openjtalk-adapter.js

export class OpenJTalkAdapter {
    /**
     * @param {Object} wasmModule - Emscripten で生成された OpenJTalk WASM モジュール
     */
    constructor(wasmModule) { ... }

    /**
     * 辞書ファイルと voice ファイルを WASM FS に書き込み、OpenJTalk を初期化する。
     * @param {Record<string, ArrayBuffer>} dictFiles - 8 辞書ファイル
     * @param {ArrayBuffer} [voiceData] - HTS voice (G2P のみなら省略可)
     */
    async initialize(dictFiles, voiceData) { ... }

    /**
     * テキストから full-context ラベルを取得する。
     * @param {string} text
     * @returns {string} full-context labels (改行区切り)
     * @throws {Error} OpenJTalk エラー時
     */
    synthesizeLabels(text) { ... }

    /**
     * OpenJTalk リソースを解放する。
     */
    dispose() { ... }
}
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| リードエンジニア | 1 | OpenJTalkAdapter 設計、DI パターン設計 |
| フロントエンドエンジニア | 1 | WASM モジュール注入の実装、パス解決ロジックの除去 |
| テストエンジニア | 1 | モック OpenJTalk モジュールの作成、DI テスト |

---

## 4. テスト計画

### 提供範囲

- 事前ロード済み OpenJTalk WASM モジュールの注入
- 辞書データの注入と初期化
- OpenJTalk なし (EN のみ) の初期化
- モック OpenJTalk モジュールによるテスト
- メモリリーク防止 (dispose 後の状態検証)

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| DI 注入 | `G2P.create({openjtalkModule})` で JA G2P が動作 | 2 |
| モック注入 | `synthesizeLabels()` をモック化して JA 音素化テスト | 3 |
| OpenJTalk なし | `G2P.create({languages: ['en']})` で WASM 不要 | 2 |
| アダプタ初期化 | 辞書ファイル書き込み + `_openjtalk_initialize` 成功 | 2 |
| アダプタエラー | `_openjtalk_synthesis_labels` がエラーを返す場合 | 2 |
| メモリ管理 | `allocateUTF8` / `_free` の正しいペアリング | 2 |
| dispose | dispose 後に `synthesizeLabels()` がエラー | 1 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| フル DI | 外部で WASM ロード → DictLoader で辞書取得 → `G2P.create()` → `phonemize("こんにちは")` |
| パス解決なし | G2P パッケージ内に `window.location` や `import.meta.url` のパス解決が含まれないことを静的検証 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **voice ファイルの必要性**: 現在の OpenJTalk 初期化は `_openjtalk_initialize(dictPtr, voicePtr)` で辞書と voice の両方を要求する。G2P 用途では voice は不要だが、WASM 側の C 実装が voice なしの初期化をサポートするか確認が必要。サポートしない場合、ダミー voice ファイルの埋め込み or voice の必須化が必要になる。
2. **Emscripten モジュールのインターフェース安定性**: `allocateUTF8`, `_free`, `UTF8ToString`, `FS.writeFile`, `FS.mkdir` は Emscripten の標準 API だが、バージョンによって微妙な差異がある。`OpenJTalkAdapter` でこれらを抽象化することで、Emscripten バージョン差を吸収できる。
3. **同期 API の保証**: `_openjtalk_synthesis_labels` は同期的な WASM 呼び出しであり、初期化完了後は `synthesizeLabels()` を同期関数として提供できる。ただし `asyncify` 対応の WASM バイナリでは非同期になる可能性がある。現在のバイナリが `asyncify` を使っていないことを確認する。

### レビュー項目

- [ ] `window.location`, `import.meta.url` のパス解決コードが G2P パッケージ内にない
- [ ] `OpenJTalkAdapter` がメモリ管理 (allocate/free) を正しくペアリングしている
- [ ] voice ファイルなしの初期化が可能か、C 側の制約を確認済み
- [ ] モック OpenJTalk モジュールのテストが実際の WASM モジュールと同じインターフェースで動作する
- [ ] `G2POptions.openjtalkModule` が省略された場合のフォールバック動作が明確

---

## 6. 一から作り直すとしたら

OpenJTalk WASM の初期化ロジックを振り返ると、パス自動解決 (jsPath, wasmPath) + GitHub Pages 対応 + 辞書ロード + WASM 初期化 + FS 操作が `initializeOpenJTalk()` 1 メソッドに詰め込まれていた。一から作り直すなら:

- **WASM モジュールのロードはフレームワーク (Vite/webpack) やアプリケーション層に任せる**。G2P パッケージは「ロード済みモジュール」を受け取るだけにする。
- **辞書データと WASM モジュールのライフサイクルを分離する**。辞書は IndexedDB キャッシュ (DictLoader)、WASM モジュールはアプリケーション管理。G2P はどちらも外部から受け取る。
- **アダプタパターンを最初から採用する**。WASM の低レベル API (ポインタ操作、メモリ管理) を直接呼ばず、型安全なアダプタ経由で操作する。

---

## 7. 後続タスクへの連絡事項

- **P3-003 (DictLoader 分離)**: `OpenJTalkAdapter.initialize()` が受け取る `dictFiles` の形式 (`Record<string, ArrayBuffer>`, 8 ファイル) は `DictLoader.loadJaDict()` の返す `JaDictData.dictFiles` と一致させる。
- **P3-004 (phonemizeWithProsody)**: `OpenJTalkAdapter.synthesizeLabels()` が返す full-context labels は A1/A2/A3 の抽出に必要。P3-004 ではこのアダプタ経由でラベルを取得する。
- **P3-005 (互換レイヤー)**: `piper-plus` 側の `SimpleUnifiedPhonemizer` は内部で `OpenJTalkAdapter` ではなく、既存の WASM モジュール直接呼び出しを維持してもよい (互換レイヤーの実装戦略に依存)。
- **P3-007 (CI)**: OpenJTalk WASM モジュールのビルド済みバイナリをテスト用にどこから取得するか (npm パッケージ内蔵 or CI アーティファクト) を P3-007 で決定する。
