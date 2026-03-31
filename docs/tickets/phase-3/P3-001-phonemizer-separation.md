# P3-001: SimpleUnifiedPhonemizer 分離

> Phase: 3 (JS/WASM)
> マイルストーン: v0.1.0
> 対応要求: FR-300
> 依存チケット: なし (Phase 3 の起点チケット)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

現在の `SimpleUnifiedPhonemizer` は OpenJTalk WASM 初期化、辞書パス解決、GitHub Pages 対応、推論パイプライン向けの phoneme_id_map 参照など、G2P 本来の責務を超える機能が密結合している。これを `onnxruntime-web` に一切依存しない純粋な G2P レイヤーとして分離し、`@piper-plus/g2p` パッケージのコアクラス `G2P` を確立する。

### ゴール

- `G2P` クラスが `onnxruntime-web` への依存ゼロで動作する
- `G2P.create()` → `phonemize()` → `dispose()` のライフサイクルが独立して完結する
- 全 6 言語 (JA/EN/ZH/ES/FR/PT) の音素化が新 API でカバーされる
- `phonemize()` の戻り値が IPA トークン列 (`PhonemizeResult`) に統一される
- OpenJTalk WASM モジュールがコンストラクタ経由で外部注入可能 (P3-002 の準備)
- 既存の `piper-plus` パッケージからの利用パスが維持される (P3-005 で正式統合)

---

## 2. 実装詳細

### 作成/変更するファイル

| 操作 | パス | 説明 |
|------|------|------|
| 新規 | `src/wasm/g2p/src/index.js` | `G2P` クラス (統合エントリ) |
| 新規 | `src/wasm/g2p/src/detect.js` | `UnicodeLanguageDetector` (既存 `detectLanguage()` を独立モジュール化) |
| 新規 | `src/wasm/g2p/src/encode.js` | phoneme ID エンコーダー (BOS/PAD/EOS 挿入) |
| 新規 | `src/wasm/g2p/src/pua-map.js` | PUA マッピングテーブル (87 entries、Python/Rust/C# と同一) |
| 新規 | `src/wasm/g2p/src/ja/index.js` | `JapaneseG2P` モジュール (JA 固有ロジック) |
| 新規 | `src/wasm/g2p/src/en/index.js` | `EnglishG2P` モジュール |
| 新規 | `src/wasm/g2p/src/zh/index.js` | `ChineseG2P` モジュール |
| 新規 | `src/wasm/g2p/src/es/index.js` | `SpanishG2P` モジュール |
| 新規 | `src/wasm/g2p/src/fr/index.js` | `FrenchG2P` モジュール |
| 新規 | `src/wasm/g2p/src/pt/index.js` | `PortugueseG2P` モジュール |
| 新規 | `src/wasm/g2p/package.json` | パッケージ定義 (`@piper-plus/g2p`) |
| 参照 | `src/wasm/openjtalk-web/src/simple_unified_api.js` | 移植元 (SimpleUnifiedPhonemizer) |
| 参照 | `src/wasm/openjtalk-web/src/japanese_phoneme_extract.js` | 移植元 (JA phoneme 抽出) |
| 参照 | `src/wasm/openjtalk-web/src/simple_english_phonemizer.js` | 移植元 (EN phonemizer) |

### 実装手順

1. **`detect.js` の切り出し**: `SimpleUnifiedPhonemizer.detectLanguage()` を独立モジュール `UnicodeLanguageDetector` として抽出。Hiragana/Katakana (JA) > CJK without Kana (ZH) > Latin (EN default) の判定ロジックをそのまま移植。

2. **言語別 G2P モジュールの作成**:
   - `ja/index.js`: `japanese_phoneme_extract.js` の `extractPhonemesFromLabels()`, `applyNPhonemeRules()`, `mapToPUA()` を移植。OpenJTalk WASM への呼び出しは外部注入された `openjtalkModule` 経由。
   - `en/index.js`: `simple_english_phonemizer.js` の `SimpleEnglishPhonemizer` を移植。辞書ベースの簡易 G2P + IPA 変換。
   - `zh/index.js`, `es/index.js`, `fr/index.js`, `pt/index.js`: 文字ベースフォールバック。`phonemeIdMap` を受け取り、各文字を phoneme_id_map 経由で ID 列に変換。

3. **`encode.js` の作成**: `PiperPlus._phonemesToIds()` と `PiperPlus._extractProsodyFromLabels()` のエンコーディングロジックを抽出。BOS(1)/PAD(0)/EOS(2) 挿入、PUA マッピング後の phoneme_id_map 変換を担当。

4. **`G2P` クラスの作成**: ファクトリメソッド `G2P.create(options)` で非同期初期化。内部で言語別 G2P モジュールを組み立て、`phonemize()` / `phonemizeWithProsody()` / `encode()` / `segmentText()` / `detectLanguage()` / `dispose()` を公開。

5. **`pua-map.js` の作成**: Python `token_mapper.py` の `FIXED_PUA_MAPPING` (87 エントリ) をそのまま移植。JA (24 entries in `japanese_phoneme_extract.js` の `PUA_MAP`) を含む全言語分。

### API / インターフェース

```javascript
// @piper-plus/g2p - src/index.js

export class G2P {
    /**
     * @param {G2POptions} [options]
     * @returns {Promise<G2P>}
     */
    static async create(options) { ... }

    /**
     * @param {string} text
     * @param {PhonemizeOptions} [options]
     * @returns {PhonemizeResult}
     */
    phonemize(text, options) { ... }

    /**
     * @param {string} text
     * @param {PhonemizeOptions} [options]
     * @returns {PhonemizeResult}
     */
    phonemizeWithProsody(text, options) { ... }

    /**
     * @param {string} text
     * @param {Record<string, number[]>} phonemeIdMap
     * @param {PhonemizeOptions} [options]
     * @returns {EncodeResult}
     */
    encode(text, phonemeIdMap, options) { ... }

    /**
     * @param {string} text
     * @returns {Language}
     */
    detectLanguage(text) { ... }

    /**
     * @param {string} text
     * @returns {Array<{language: Language, text: string}>}
     */
    segmentText(text) { ... }

    dispose() { ... }
}

// G2POptions
// {
//   languages?: Language[],         // 有効にする言語
//   openjtalkModule?: any,          // 外部注入の OpenJTalk WASM モジュール
//   jaDict?: JaDictData,            // 日本語辞書データ
//   customDicts?: CustomDictionary[],
// }

// PhonemizeResult
// {
//   tokens: string[],              // IPA トークン配列
//   prosody: (ProsodyInfo | null)[],
//   language: Language,
// }

// EncodeResult
// {
//   phonemeIds: number[],          // BOS/PAD/EOS 挿入済み ID 列
//   prosodyFlat: number[] | null,  // [a1,a2,a3, ...] or null
// }
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| リードエンジニア | 1 | G2P クラス設計、言語別モジュール分割、API 設計レビュー |
| フロントエンドエンジニア | 1 | 言語別 G2P モジュールの移植、detect.js / encode.js 実装 |
| テストエンジニア | 1 | 全言語の音素化テスト、Python/Rust 実装との一致検証 |

---

## 4. テスト計画

### 提供範囲

- `G2P.create()` が正常に初期化を完了する
- 全 6 言語で `phonemize()` が正しい IPA トークン列を返す
- `encode()` が BOS/PAD/EOS を含む正しい phoneme_ids を返す
- `detectLanguage()` が JA/ZH/EN を正しく判定する
- `dispose()` 後のメソッド呼び出しがエラーになる
- `onnxruntime-web` が存在しない環境でも動作する

### Unit テスト

| テスト | 内容 | ケース数 |
|--------|------|---------|
| JA 音素化 | `phonemize("こんにちは", {language: "ja"})` のトークン列検証 | 5+ |
| EN 音素化 | `phonemize("Hello world", {language: "en"})` のトークン列検証 | 5+ |
| ZH/ES/FR/PT フォールバック | 文字ベース phonemize のトークン列検証 | 4+ |
| 言語検出 | JA (かな), ZH (漢字のみ), EN (ASCII), 混合テキスト | 6+ |
| エンコード | BOS/PAD/EOS 挿入、PUA マッピング | 5+ |
| PUA マッピング | 87 エントリが Python `FIXED_PUA_MAPPING` と一致 | 1 |
| N 変異 | N_m/N_n/N_ng/N_uvular の 4 パターン | 4+ |

### E2E テスト

| テスト | 内容 |
|--------|------|
| フルパイプライン | `G2P.create()` → `phonemize()` → `encode()` で phoneme_ids 取得 |
| JA なし初期化 | `G2P.create({languages: ['en']})` で WASM なしの軽量初期化 |
| dispose 後のエラー | `dispose()` 後に `phonemize()` を呼ぶとエラー |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

1. **OpenJTalk WASM の同期/非同期境界**: 現在 `textToPhonemesJapanese()` は `async` だが、実際の WASM 呼び出し (`_openjtalk_synthesis_labels`) は同期的。新 API で `phonemize()` を同期関数にするか非同期にするかの判断が必要。FR-300 は「初期化後に同期的に呼び出せる」を要求している。
2. **ZH/ES/FR/PT の戻り値の型**: 現在は `phonemizeChinese()` / `phonemizeLatinFallback()` が `number[]` (phoneme_ids) を直接返している。新 API では IPA トークン列 (`string[]`) に統一する必要があるが、文字ベースフォールバックでは meaningful な IPA トークンがない。`tokens` に入力文字列の個々の文字を返し、`encode()` で phoneme_id_map 変換するアプローチが妥当。
3. **パッケージ配置**: `src/wasm/g2p/` に新パッケージを配置するか、`src/wasm/openjtalk-web/` 内にサブディレクトリとして配置するか。独立 npm パッケージとしての公開を考慮すると `src/wasm/g2p/` が適切。

### レビュー項目

- [ ] `G2P` クラスの API が FR-300 の受入条件を全て満たしている
- [ ] PUA マッピングテーブル (87 entries) が Python `token_mapper.py` と完全一致
- [ ] JA の N 変異ロジックが `japanese_phoneme_extract.js` と同一
- [ ] `onnxruntime-web` への参照がコード内に一切ない
- [ ] `package.json` の `peerDependencies` に `onnxruntime-web` が含まれていない

---

## 6. 一から作り直すとしたら

`SimpleUnifiedPhonemizer` の設計を振り返ると、推論パイプラインの内部モジュールとして成長したため G2P とエンコーディング (phoneme_id_map 変換) の境界が曖昧になった。一から作り直すなら:

- **G2P 層** (IPA トークン列を返す) と **エンコード層** (phoneme_ids を返す) を最初から分離する
- OpenJTalk WASM 初期化は必ず DI パターンにし、パス解決ロジック (GitHub Pages 対応等) を G2P クラスに含めない
- ZH/ES/FR/PT のような文字ベースフォールバックは G2P 層ではなくエンコード層の責務とし、G2P 層は「音素化可能な言語」のみを対象とする
- 言語検出は別モジュール (`detect.js`) として最初から分離する

---

## 7. 後続タスクへの連絡事項

- **P3-002 (OpenJTalk WASM DI 化)**: 本チケットで `G2POptions.openjtalkModule` の注入口を用意するが、実際の DI パターン実装 (自動パス解決の排除、テスト用モック注入) は P3-002 で行う。
- **P3-003 (DictLoader 分離)**: 本チケットでは `jaDict` を `G2POptions` で受け取る口を用意するのみ。`DictLoader` クラスの実装は P3-003。
- **P3-004 (phonemizeWithProsody)**: 本チケットで `phonemizeWithProsody()` メソッドのスタブ (prosody 常に null) を実装する。実際の A1/A2/A3 抽出は P3-004。
- **P3-005 (互換レイヤー)**: 本チケットでは既存 `SimpleUnifiedPhonemizer` は変更しない。P3-005 で新 `G2P` クラスへの委譲に切り替える。
- **P3-006 (TypeScript 型定義)**: 本チケットの API が確定した段階で P3-006 の型定義を開始できる。
- **全後続チケット**: `src/wasm/g2p/` パッケージの基本ディレクトリ構造とエントリポイントは本チケットで確定する。後続チケットはこの構造に従う。
