# M3-3: prosody 抽出の統合

> **マイルストーン**: M3
> **前提チケット**: M3-1, M3-2
> **後続チケット**: M3-4, M3-5
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`src/wasm/openjtalk-web/src/index.js` の `_extractProsodyFromLabels()` メソッド (336-368 行目) を削除し、prosody 抽出を `G2P.encode()` の返り値 (`prosodyFlat`) に完全に委譲する。M3-2 で `_textToPhonemeIds()` が `G2P.encode()` からの `prosodyFlat` を直接使うよう変更されたため、手動での OpenJTalk ラベル解析は不要となる。

## 実装する内容の詳細

### 現状

`_extractProsodyFromLabels()` (336-368 行目) は OpenJTalk の full-context ラベルから A1/A2/A3 prosody 値を手動で正規表現パースしている:

```javascript
_extractProsodyFromLabels(labels, phonemeCount) {
  const reA1 = /\/A:([\d-]+)\+/;
  const reA2 = /\+([0-9]+)\+/;
  const reA3 = /\+([0-9]+)\//;
  // ... BOS/EOS パディング、phonemeCount へのトリム
}
```

M3-2 の完了後、`_textToPhonemeIds()` は既に `G2P.encode()` の返り値から `prosodyFlat` を取得しているため、このメソッドは呼び出されなくなっている。

### 変更内容

1. **`_extractProsodyFromLabels()` メソッドの削除** (336-368 行目)
   - M3-2 完了後、このメソッドへの参照は存在しない
   - 33 行のデッドコード除去

2. **`_infer()` メソッドの prosody 入力確認**
   - `_infer()` が受け取る `prosodyFeatures` のフォーマットが `G2P.encode()` の `prosodyFlat` と一致していることを確認
   - 必要に応じてフォーマット変換を追加 (prosodyFlat が `[a1, a2, a3, a1, a2, a3, ...]` のフラット配列か、`[[a1, a2, a3], ...]` のネスト配列かの差異)

3. **prosody アライメント検証の追加**
   - `prosodyFlat` の長さが `phonemeIds` の長さと一致することのアサーション
   - 不一致時はパディングまたはトリムで対応 (既存の `_extractProsodyFromLabels()` と同じ方針)

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/wasm/openjtalk-web/src/index.js` | `_extractProsodyFromLabels()` 削除、`_infer()` の prosody 入力フォーマット調整 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| JS 開発者 | 1 | メソッド削除、prosody フォーマット整合性確認、_infer() の調整 |

## 提供範囲とテスト

### 提供範囲

- `src/wasm/openjtalk-web/src/index.js` の `_extractProsodyFromLabels()` 削除と `_infer()` の prosody 入力調整

### テスト項目

- `_extractProsodyFromLabels()` メソッドが存在しないこと
- JA テキストの synthesize で prosody features が正しく ONNX 入力に渡されること
- prosody 非対応言語 (EN/ZH/KO/ES/FR/PT/SV) で prosody が null のまま正常動作すること

### Unit テスト

- `G2P.encode()` が返す `prosodyFlat` の値が、旧 `_extractProsodyFromLabels()` の出力と一致することを検証 (回帰テスト)
- prosodyFlat の長さが phonemeIds の長さと一致することを検証
- prosodyFlat が phonemeIds より短い場合のパディング動作を検証
- prosodyFlat が phonemeIds より長い場合のトリム動作を検証

### E2E テスト

- JA: prosody 付きモデルで音声合成し、prosody_features テンソルが正しい shape `[1, seq_len, 3]` で構築されることを確認
- JA: 同一テキストで移行前後の prosody 値を比較し、一致することを確認

## 懸念事項とレビュー項目

### 懸念事項

1. **prosody アライメント**: `G2P.encode()` の `prosodyFlat` の長さは `phonemeIds` の長さと必ず一致するか。BOS/EOS トークン分のパディングが正しく含まれているか確認が必要。旧実装では `_extractProsodyFromLabels()` 内で BOS/EOS 分のパディングとトリムを行っていた
2. **prosodyFlat のフォーマット**: フラット配列 `[a1, a2, a3, a1, a2, a3, ...]` かネスト配列 `[[a1, a2, a3], ...]` かで `_infer()` のテンソル構築コードが変わる
3. **prosodyFlat フォーマット不整合リスク**: 現行の `_extractProsodyFromLabels()` は nested 配列 `[[a1, a2, a3], ...]` を返す。G2P の `prosodyFlat` が flat 配列 `[a1, a2, a3, a1, a2, a3, ...]` の場合、`_infer()` での ONNX テンソル構築ロジックの変更が必要。実装前に G2P の `Encoder.encodeWithProsody()` (`src/wasm/g2p/src/encode.js`) の戻り値フォーマットを確認すること

### レビュー項目

1. `_extractProsodyFromLabels()` への参照が完全に除去されていること
2. `_infer()` の prosody テンソル構築コードが新しい prosodyFlat フォーマットに対応していること
3. prosody アライメントの検証ロジック (パディング/トリム) が適切に移行されていること

## 一から作り直すとしたら

prosody 抽出は G2P レイヤーの責務であり、推論エンジン側で OpenJTalk ラベルをパースするのは関心の分離に反する。G2P パッケージが `encode()` の返り値として phonemeIds と一緒に prosody を返す設計は正しく、最初からこの方式にすべきだった。

## 後続タスクへの連絡事項

- M3-4 のテスト更新では、prosody 関連のテストを `_extractProsodyFromLabels()` から `G2P.encode()` の `prosodyFlat` ベースに変更する必要がある
- M3-5 で `japanese_phoneme_extract.js` (155 行) も削除対象。このファイルには prosody 抽出のヘルパー関数が含まれている可能性があるため、M3-5 の削除時に確認すること
- `_infer()` の prosody テンソル構築コードは変更しない方針。フォーマット変換は `_textToPhonemeIds()` 内で吸収する
