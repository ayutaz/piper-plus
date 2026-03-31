# P3-005: piper-plus 互換レイヤー

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: NFR-301
> 依存チケット: P3-001, P3-002, P3-003, P3-004
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

`@piper-plus/g2p` パッケージの導入後も、既存の `piper-plus` npm パッケージ (282 テスト) の公開 API に破壊的変更を加えないことを保証する。`PiperPlus.initialize()` → `PiperPlus.synthesize()` のワークフローは維持しつつ、内部で `@piper-plus/g2p` の `G2P` クラスに委譲する。

### ゴール

- `piper-plus` の既存 282 テストが変更なしで全て pass する
- `PiperPlus.initialize()`, `PiperPlus.synthesize()`, `PiperPlus.synthesizeStreaming()` の API シグネチャに変更なし
- `SimpleUnifiedPhonemizer` が内部で `@piper-plus/g2p` の `G2P` クラスに委譲する
- `piper-plus` の `package.json` に `"@piper-plus/g2p": "^1.0.0"` が dependencies として追加される
- `PiperPlus.synthesize()` を `phonemize()` / `synthesize()` / `text_to_speech()` に分割可能な API が追加される (オプション)
- `DictManager` が内部で `DictLoader` を利用する (キャッシュ共有)

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 変更 | `src/wasm/openjtalk-web/package.json` | `@piper-plus/g2p` を dependencies に追加 |
| 変更 | `src/wasm/openjtalk-web/src/simple_unified_api.js` | 内部で `G2P` クラスに委譲 |
| 変更 | `src/wasm/openjtalk-web/src/dict-manager.js` | 内部で `DictLoader` に委譲 |
| 変更 | `src/wasm/openjtalk-web/src/index.js` | re-export に `@piper-plus/g2p` を追加 |
| 新規 | `src/wasm/openjtalk-web/src/phonemize-api.js` | 分離 API (`phonemize()` / `synthesize()` / `text_to_speech()`) |

### 実装手順

1. **SimpleUnifiedPhonemizer のリファクタリング**: 既存の `SimpleUnifiedPhonemizer` を `G2P` クラスのファサードに変換。内部で `G2P.create()` を呼び、`textToPhonemes()`, `extractPhonemes()`, `detectLanguage()` 等のメソッドを `G2P` のメソッドに委譲する。

   ```javascript
   // simple_unified_api.js (変更後)
   import { G2P } from '@piper-plus/g2p';

   export class SimpleUnifiedPhonemizer {
       constructor(options = {}) {
           this._g2p = null;
           // 既存のフィールドを維持
           this.initialized = false;
           this.phonemeIdMap = options.phonemeIdMap || null;
           this.deploymentConfig = options.deploymentConfig || { ... };
       }

       async initialize(config) {
           this._g2p = await G2P.create({
               openjtalkModule: config.openjtalk?._module, // 互換のため
               jaDict: config.openjtalk ? {
                   dictData: config.openjtalk.dictData,
                   voiceData: config.openjtalk.voiceData,
               } : undefined,
           });
           this.initialized = true;
       }

       async textToPhonemes(text, language = null) {
           // 既存の返り値型を維持
           // JA: string (labels), EN: string (IPA), ZH/ES/FR/PT: number[]
           // ...
       }
       // ...
   }
   ```

2. **DictManager のリファクタリング**: `DictManager` を `DictLoader` のファサードに変換。`loadDictionary()` が `DictLoader.loadJaDict({includeVoice: true})` に委譲し、戻り値型 (`{dictFiles, voiceData}`) を維持する。キャッシュの `cachePrefix` を `'piper-plus-dict'` のまま維持し、既存キャッシュとの互換性を保つ。

   ```javascript
   // dict-manager.js (変更後)
   import { DictLoader } from '@piper-plus/g2p/dict';

   export class DictManager {
       constructor(options = {}) {
           this._loader = new DictLoader({
               cachePrefix: options.cachePrefix || 'piper-plus-dict',
           });
       }

       async loadDictionary(options = {}) {
           return this._loader.loadJaDict({
               dictUrl: options.dictUrl,
               voiceUrl: options.voiceUrl,
               includeVoice: true, // piper-plus は voice が必要
               onProgress: options.onProgress,
           });
       }
       // ...
   }
   ```

3. **分離 API の追加** (オプション): `PiperPlus` に `phonemize()`, `infer()` メソッドを追加し、ユーザーが音素化と推論を独立して呼び出せるようにする。既存の `synthesize()` は内部でこれらを順次呼ぶ。

   ```javascript
   // phonemize-api.js
   export class PiperPlusPhonemizeAPI {
       /**
        * テキストから phoneme_ids + prosody を取得。
        * 推論なしで G2P のみ実行する。
        */
       async phonemize(text, options = {}) { ... }

       /**
        * phoneme_ids から音声を生成。
        * G2P なしで推論のみ実行する。
        */
       async infer(phonemeIds, options = {}) { ... }

       /**
        * phonemize() + infer() を順次実行 (= 既存の synthesize())。
        */
       async textToSpeech(text, options = {}) { ... }
   }
   ```

4. **re-export の追加**: `piper-plus` の `index.js` に `@piper-plus/g2p` からの re-export を追加:

   ```javascript
   // index.js (追加)
   export { G2P, DictLoader } from '@piper-plus/g2p';
   ```

### API / インターフェース

既存 API (変更なし):
```javascript
// 変更なし - 完全互換
const piper = await PiperPlus.initialize({ model: '...' });
const result = await piper.synthesize("こんにちは");
result.play();
piper.dispose();
```

新規 API (追加):
```javascript
// 分離呼び出し (P3-005 で追加)
const { phonemeIds, prosodyFlat } = await piper.phonemize("こんにちは");
const audioData = await piper.infer(phonemeIds, { prosodyFlat });

// G2P 単体利用 (re-export)
import { G2P } from 'piper-plus';
const g2p = await G2P.create({ ... });
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| リードエンジニア | 1 | 互換性設計、既存テスト通過の確認 |
| フロントエンドエンジニア | 1 | SimpleUnifiedPhonemizer / DictManager のリファクタリング |
| QA エンジニア | 1 | 既存 282 テストの全通過確認、回帰テスト |

---

## 4. テスト計画

### 提供範囲

- 既存 282 テストが全て pass する (回帰テスト)
- 新 API (`phonemize()`, `infer()`) が正しく動作する
- `DictManager` → `DictLoader` 委譲でキャッシュが正常動作する
- re-export (`import { G2P } from 'piper-plus'`) が動作する

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| 既存テスト | 282 テスト全通過 (変更なし) | 282 |
| SimpleUnifiedPhonemizer 互換 | 既存メソッド (textToPhonemes, extractPhonemes, detectLanguage 等) の出力が変更前と一致 | 10 |
| DictManager 互換 | loadDictionary() の戻り値型が変更前と一致 | 3 |
| キャッシュ互換 | 既存 IndexedDB キャッシュ (piper-plus-dict) が新実装でも読める | 2 |
| 分離 API | `phonemize()` → `infer()` が `synthesize()` と同一結果 | 3 |
| re-export | `import { G2P } from 'piper-plus'` が動作 | 1 |

### E2E テスト

| テスト | 内容 |
|--------|------|
| フル互換 | 既存デモ (demo/index.html) が変更なしで動作 |
| 分離呼び出し | `phonemize()` → `infer()` → `AudioResult.play()` |
| G2P 単体 | `piper-plus` 経由で `G2P` を利用し、推論なしで phoneme_ids 取得 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **textToPhonemes() の戻り値型の差異**: 現在の `SimpleUnifiedPhonemizer.textToPhonemes()` は JA で `string` (full-context labels)、EN で `string` (IPA)、ZH/ES/FR/PT で `number[]` (phoneme_ids) を返す。新 `G2P.phonemize()` は全言語で `PhonemizeResult` を返す。互換レイヤーでは旧形式への変換が必要。
2. **OpenJTalk WASM の二重ロード回避**: `SimpleUnifiedPhonemizer` が内部で `G2P` に委譲する場合、OpenJTalk WASM の初期化パスが変わる。`PiperPlus.initialize()` → `DictManager` → `SimpleUnifiedPhonemizer` の順序を維持しつつ、`G2P.create()` に正しく渡す必要がある。
3. **ZH/ES/FR/PT の phoneme_id_map 依存**: 現在 `SimpleUnifiedPhonemizer` は `setPhonemeIdMap()` で model config の `phoneme_id_map` を受け取る。新 `G2P` クラスでは `encode()` メソッドで `phoneme_id_map` を受け取る設計。互換レイヤーで `setPhonemeIdMap()` を `G2P` に橋渡しする方法を検討する。
4. **パッケージサイズの増加**: `@piper-plus/g2p` を dependencies に追加すると `piper-plus` のインストールサイズが増加する。tree-shaking が効くか、バンドラー設定の確認が必要。

### レビュー項目

- [ ] 既存 282 テストが全て pass する
- [ ] `PiperPlus.initialize()`, `synthesize()`, `synthesizeStreaming()`, `dispose()` のシグネチャに変更がない
- [ ] `SimpleUnifiedPhonemizer` の各メソッドの戻り値型が変更前と一致
- [ ] `DictManager.loadDictionary()` の戻り値型が `{dictFiles, voiceData}` のまま
- [ ] IndexedDB キャッシュ名 (`piper-plus-dict`) が変更されていない
- [ ] `@piper-plus/g2p` を import しても `onnxruntime-web` が必要にならない

---

## 6. 一から作り直すとしたら

`piper-plus` パッケージの設計を振り返ると、`PiperPlus.synthesize()` が G2P + 推論 + 音声出力をモノリシックに結合していた。一から作り直すなら:

- **最初から G2P / 推論 / 音声出力を 3 パッケージに分離する**。`@piper-plus/g2p` (G2P)、`@piper-plus/inference` (ONNX 推論)、`@piper-plus/audio` (音声出力)。`piper-plus` はこれらを統合するメタパッケージ。
- **戻り値型を全言語で統一する**。`textToPhonemes()` が JA は string、ZH は number[] を返す現在の設計は互換性維持を複雑にしている。
- **phoneme_id_map は G2P パッケージではなく encode 層の責務とする**。現在の `setPhonemeIdMap()` のようなステートフルな API は避ける。

---

## 7. 後続タスクへの連絡事項

- **P3-006 (TypeScript 型定義)**: 互換レイヤーの新 API (`phonemize()`, `infer()`) の型定義を `types/index.d.ts` に追加する。
- **P3-007 (CI)**: 既存 282 テストの実行を CI に組み込む。`@piper-plus/g2p` の変更が `piper-plus` のテストに影響しないことを確認するため、両パッケージのテストを CI で実行する。
- **P3-008 (安定版リリース)**: 互換レイヤーが安定し、既存ユーザーからの回帰報告がないことを確認してから v1.0.0 をリリースする。
- **全後続チケット**: `piper-plus` の `package.json` の `dependencies` に `"@piper-plus/g2p"` が追加される。monorepo 構成 (workspaces) の導入を検討する。
