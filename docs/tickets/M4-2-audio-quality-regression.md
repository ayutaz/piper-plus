# M4-2: 音声品質の回帰テスト

> **マイルストーン**: M4
> **前提チケット**: M4-1 (ベースライン生成は M0 完了後に先行実施)
> **後続チケット**: なし
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

G2P 移行前後で音声品質に回帰がないことを、phoneme_ids のビット完全一致比較で保証する。

**重要**: ベースライン JSON (`audio-regression-baseline.json`) は M1/M2/M3 の作業開始前に現行コードから生成する必要がある。本チケットの「ベースライン生成」ステップは M0 完了直後、M1/M2/M3 着手前に実行すること。回帰テスト（比較検証）自体は M4 フェーズで実行する。ONNX 推論は deterministic であるため、phoneme_ids が同一であれば音声出力も同一になる。つくよみちゃん 6lang モデルがサポートする 6 言語 (JA/EN/ZH/ES/FR/PT) のテストテキストで比較を実施する。

## 実装する内容の詳細

### テスト方針

**核心**: phoneme_ids が同一 → 音声出力が同一 (deterministic ONNX 推論の性質)

移行前後で以下を比較:
1. 同一テキスト → 同一 phoneme_ids が生成されることを検証
2. phoneme_ids が一致すれば音声の bit-exact 一致は自明のため、音声波形の比較は不要

### 1. ベースライン phoneme_ids の生成

移行前 (現行コード) で各テストテキストの phoneme_ids を生成し、ベースラインとして保存:

**ファイル**: `data/test-fixtures/audio-regression-baseline.json`

```json
{
  "model": "tsukuyomi-6lang-v2",
  "generated_at": "2026-04-XX",
  "generated_by": "pre-migration SimpleUnifiedPhonemizer",
  "tests": [
    {
      "language": "ja",
      "text": "こんにちは、つくよみちゃんです。",
      "phoneme_ids": [1, 45, 63, ...],
      "prosody_features": [[0, 0, 0], [5, 1, 5], ...]
    },
    {
      "language": "en",
      "text": "Hello, how are you today?",
      "phoneme_ids": [1, 28, 12, ...]
    }
  ]
}
```

### 2. 回帰テスト実行

移行後のコードで同一テキストの phoneme_ids を生成し、ベースラインと比較:

**テストテキスト** (6 言語):

| 言語 | テキスト |
|------|---------|
| JA | 「こんにちは、つくよみちゃんです。」 |
| EN | "Hello, how are you today?" |
| ZH | "你好，今天天气很好。" |
| ES | "¿Hola, cómo estás hoy?" |
| FR | "Bonjour, comment allez-vous?" |
| PT | "Olá, como você está hoje?" |

### 3. テスト実装

**ファイル**: `src/wasm/openjtalk-web/test/js/test-audio-regression.js` (新規)

- `audio-regression-baseline.json` を読み込み
- `G2P.encode()` で各テキストの phoneme_ids を生成
- ベースラインの phoneme_ids とビット完全一致を検証
- JA の場合は prosody_features も比較

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `data/test-fixtures/audio-regression-baseline.json` | 新規作成: 移行前の phoneme_ids ベースライン |
| `src/wasm/openjtalk-web/test/js/test-audio-regression.js` | 新規作成: phoneme_ids 回帰テスト |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テスト担当 | 1 | ベースライン生成、回帰テスト実装、結果分析 |

## 提供範囲とテスト

### 提供範囲

- ベースライン JSON ファイル (移行前の phoneme_ids)
- JS 回帰テストファイル

### テスト項目

- 6 言語の全テストテキストで phoneme_ids がベースラインとビット完全一致すること
- JA の prosody_features がベースラインと一致すること

### Unit テスト

- 各言語のテストテキスト (6 ケース) で phoneme_ids の完全一致を検証
- JA の prosody_features の完全一致を検証
- 不一致発生時に差分を読みやすく出力する (どのインデックスで乖離したか)

### E2E テスト

- つくよみちゃん 6lang モデルで実際に音声合成を実行し、移行前と同一の WAV が出力されることを確認 (手動検証)

## 懸念事項とレビュー項目

### 懸念事項

1. **ベースライン生成のタイミング**: 移行前のコードでベースラインを生成する必要がある。M3 作業開始前にベースラインを確保しておくこと
2. **deterministic 推論の前提**: ONNX runtime の `noise_scale` / `noise_scale_w` パラメータが同一であることが前提。テスト時に明示的に指定する
3. **prosody_features の浮動小数点比較**: prosody は整数値 (A1/A2/A3) のため完全一致で問題ないが、将来的に浮動小数点値が導入された場合は epsilon 比較が必要

### レビュー項目

1. ベースライン JSON の phoneme_ids が移行前コードで正しく生成されたものであること
2. テストテキストが CLAUDE.md の推論テスト結果と同一であること (検証済みテキストの再利用)
3. 回帰テストの失敗メッセージが十分に informative であること (diff の可視化)
4. ベースラインの更新手順がドキュメント化されていること

## 一から作り直すとしたら

回帰テストのベースラインを Git で管理し、CI パイプラインに「ベースライン更新 PR 自動生成」機能を組み込む。G2P ルールの意図的な変更時にベースラインが自動更新され、レビュアーが差分を確認できるワークフローが理想的。

## 後続タスクへの連絡事項

- このチケットは M4 の最終検証の一部。後続タスクなし
- ベースライン JSON は M3 作業開始前に生成しておく必要があるため、実際の作成タイミングは M3 開始前の準備作業として実施する
- 回帰テストで不一致が検出された場合は、M3 のいずれかのチケットにバグとして報告する
