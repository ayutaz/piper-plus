# M3-2: _textToPhonemeIds() 統一

> **マイルストーン**: M3
> **前提チケット**: M3-1
> **後続チケット**: M3-4, M3-5
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/wasm/openjtalk-web/src/index.js` の `_textToPhonemeIds()` メソッド (282-329 行目) を、言語ごとの分岐ロジックから `G2P.encode()` への単一呼び出しに統一する。現在は JA/EN がトークン列を返して `_phonemesToIds()` で ID 変換し、ZH/KO/ES/FR/PT/SV が直接 ID を返すという二系統の処理パスが存在するが、これを `G2P.encode()` の統一インターフェースに置き換える。

## 実装する内容の詳細

### 現状

`_textToPhonemeIds()` (282-302 行目) は言語によって処理パスが分岐:

```javascript
// ZH/KO/ES/FR/PT/SV: phonemizer が ID を直接返す
if (['zh', 'ko', 'es', 'fr', 'pt', 'sv'].includes(language)) {
  const ids = await this._phonemizer.textToPhonemes(text, language);
  return { phonemeIds: ids, prosodyFeatures: null };
}

// JA/EN: phonemizer がトークン列を返し、_phonemesToIds() で変換
const rawOutput = await this._phonemizer.textToPhonemes(text, language);
const phonemes = this._phonemizer.extractPhonemes(rawOutput, language);
const phonemeIds = this._phonemesToIds(phonemes, language);
```

`_phonemesToIds()` (309-329 行目) は `phoneme_id_map` を使ってトークン → ID 変換を行う独立メソッド。

### 変更内容

1. **`_textToPhonemeIds()` の書き換え** (282-302 行目)
   - 言語分岐ロジックを全て削除
   - `G2P.encode(text, phonemeIdMap, { language })` への単一呼び出しに置き換え
   - 返り値: `{ phonemeIds, prosodyFlat }` — prosodyFlat は JA の場合のみ値が入り、他言語は null

2. **`_phonemesToIds()` メソッドの削除** (309-329 行目)
   - `G2P.encode()` が内部でトークン → ID 変換を行うため、不要になる
   - このメソッドは `_textToPhonemeIds()` からのみ呼ばれているため、安全に削除可能

3. **prosody 処理の調整**
   - 現状: `_textToPhonemeIds()` が `_extractProsodyFromLabels()` を別途呼び出し
   - 変更後: `G2P.encode()` が `prosodyFlat` を直接返すため、`_extractProsodyFromLabels()` の呼び出しも不要に (M3-3 で削除)
   - このチケットでは `G2P.encode()` の返り値から `prosodyFlat` を取り出す処理を実装

### 変更後のコード (概要)

```javascript
async _textToPhonemeIds(text, language) {
  const result = await this._g2p.encode(text, this._encoder, { language });
  return {
    phonemeIds: result.phonemeIds,
    prosodyFeatures: result.prosodyFlat || null,
  };
}
```

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/wasm/openjtalk-web/src/index.js` | `_textToPhonemeIds()` 書き換え、`_phonemesToIds()` 削除 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| JS 開発者 | 1 | _textToPhonemeIds() の書き換え、_phonemesToIds() の削除 |
| レビュアー | 1 | 全 8 言語での phonemeIds 出力の正当性確認 |

## 提供範囲とテスト

### 提供範囲

- `src/wasm/openjtalk-web/src/index.js` の `_textToPhonemeIds()` と `_phonemesToIds()` の変更

### テスト項目

- 全 8 言語 (JA/EN/ZH/KO/ES/FR/PT/SV) で `_textToPhonemeIds()` が正しい phonemeIds を返すこと
- JA の場合に prosodyFeatures が返されること
- JA 以外の言語で prosodyFeatures が null であること

### Unit テスト

- 各言語のテストテキストで `G2P.encode()` が正しいパラメータで呼び出されることを検証 (モック)
- `G2P.encode()` の返り値 (`phonemeIds`, `prosodyFlat`) が正しく `_textToPhonemeIds()` の返り値にマッピングされることを検証
- `_phonemesToIds()` が存在しないことを検証 (削除確認)

### E2E テスト

- 各言語で synthesize を実行し、音声出力が得られることを確認
- 特に JA: prosody 付きモデルで prosodyFeatures が ONNX 入力に正しく渡されることを確認

## 懸念事項とレビュー項目

### 懸念事項

1. **韓国語 Jamo 分解の差異**: `SimpleUnifiedPhonemizer` の韓国語処理と `G2P` パッケージの韓国語処理で Jamo 分解のロジックが異なる可能性がある。phonemeIds の出力を比較テストで確認する必要がある
2. **phonemeIds のフォーマット**: `G2P.encode()` が返す `phonemeIds` は `Int32Array` / `Array<number>` のどちらか。ONNX テンソル構築時の型変換に注意
3. **BOS/EOS トークン**: `_phonemesToIds()` は暗黙的に BOS (^) / EOS ($) を含めていたか確認。`G2P.encode()` 側の挙動と一致させる必要がある
4. **`G2P.encode()` の実際のシグネチャと戻り値フォーマットを `src/wasm/g2p/src/index.js` で確認すること**。本チケットは `encode(text, phonemeIdMap, { language })` → `{ phonemeIds, prosodyFlat }` を前提としているが、実装が異なる場合はインターフェースの調整が必要

### レビュー項目

1. `G2P.encode()` の返り値の型が `_infer()` の期待する形式と一致しているか
2. prosodyFlat の形式 (配列構造) が `_infer()` の prosody テンソル構築と互換か
3. エラーハンドリング: 未知の言語コードが渡された場合の挙動
4. `_phonemesToIds()` への参照が他に存在しないことの確認

## 一から作り直すとしたら

最初から全言語を統一的な `encode()` インターフェースで処理する設計にすべきだった。JA/EN がトークン列を返し、ZH/KO/ES/FR/PT/SV が ID を直接返すという二系統のインターフェースは、言語追加のたびに分岐を増やす必要があり保守性が低い。`G2P.encode()` の「テキスト → phonemeIds + prosody」という統一インターフェースがこれを解決する。

## 後続タスクへの連絡事項

- M3-3 は `G2P.encode()` が `prosodyFlat` を返すことを前提として `_extractProsodyFromLabels()` を削除する
- M3-4 のテスト更新では、`_phonemesToIds()` を直接テストしていた boundary テスト (test-piper-plus-boundary.js) を `Encoder` ベースのテストに書き換える必要がある
- `_phonemesToIds()` は削除済みのため、テストから参照を除去すること
