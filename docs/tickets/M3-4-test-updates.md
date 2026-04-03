# M3-4: テスト更新 (11 ファイル)

> **マイルストーン**: M3
> **前提チケット**: M3-1, M3-2, M3-3
> **後続チケット**: M3-5, M3-6
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

M3-1 ~ M3-3 の変更に伴い、`SimpleUnifiedPhonemizer` を参照しているテストファイル群を `G2P` / `Encoder` ベースの新 API に更新する。モックヘルパーの刷新と合わせて、全 47 openjtalk-web テストファイルが引き続き pass することを保証する。

## 実装する内容の詳細

### 変更対象ファイル一覧

| # | ファイル | 主な変更内容 |
|---|---------|-------------|
| 1 | `test/helpers/create-mock-phonemizer.js` | `SimpleUnifiedPhonemizer` モック → `G2P` / `Encoder` モックに全面書き換え |
| 2 | `test/js/test-piper-plus.js` | export チェックの対象を `SimpleUnifiedPhonemizer` → `G2P` に更新 |
| 3 | `test/js/test-piper-plus-boundary.js` | `_phonemesToIds()` の直接テスト (13+ テスト) → `Encoder` 経由のテストに書き換え |
| 4 | `test/js/test-korean.js` | `SimpleUnifiedPhonemizer` → `G2P` API でのテスト |
| 5 | `test/js/test-swedish.js` | `SimpleUnifiedPhonemizer` → `G2P` API でのテスト |
| 6 | `test/js/test-streaming-pipeline.js` | パイプライン内の phonemization モック更新 |
| 7 | `test/js/test-piper-plus-init-success.js` | 初期化スタブを `G2P.create()` ベースに変更 |
| 8 | `test/js/test-piper-plus-synthesize-flow.js` | 合成フローのモックを `G2P.encode()` ベースに変更 |
| 9-11 | その他影響テストファイル | `SimpleUnifiedPhonemizer` / `_phonemesToIds` への参照を検索して更新 |

> **影響テストファイルの確定は実装前に以下で行う:**
> ```bash
> grep -rln "SimpleUnifiedPhonemizer\|textToPhonemes\|_phonemesToIds\|extractPhonemes" src/wasm/openjtalk-web/test/
> ```
> 上記の結果に基づきファイルリストを確定する。

### 詳細な変更内容

#### 1. モックヘルパーの刷新 (`create-mock-phonemizer.js`)

現状の `createMockPhonemizer()` は `SimpleUnifiedPhonemizer` 互換のモックを返す。これを以下に変更:

- `createMockG2P()`: `G2P.create()` 互換のモック。`encode(text, encoder, options)` → `{ phonemeIds, prosodyFlat }` を返す
- `createMockEncoder()`: `Encoder` 互換のモック。`phonemeIdMap` を保持する

#### 2. boundary テストの書き換え (`test-piper-plus-boundary.js`)

`_phonemesToIds()` を直接呼び出す 13+ テストケースを、`Encoder` / `G2P.encode()` 経由のテストに変更:
- 未知 phoneme のフォールバック動作
- BOS/EOS トークン
- 空文字列入力
- 特殊文字のハンドリング

#### 3. 言語別テストの更新 (`test-korean.js`, `test-swedish.js`)

`new SimpleUnifiedPhonemizer()` → `G2P.create()` のファクトリ呼び出しに変更。テスト対象のアサーション (phonemeIds の内容) は変更しない。

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `test/helpers/create-mock-phonemizer.js` | モック全面書き換え |
| `test/js/test-piper-plus.js` | export チェック更新 |
| `test/js/test-piper-plus-boundary.js` | _phonemesToIds テスト → Encoder テスト |
| `test/js/test-korean.js` | SimpleUnifiedPhonemizer → G2P |
| `test/js/test-swedish.js` | SimpleUnifiedPhonemizer → G2P |
| `test/js/test-streaming-pipeline.js` | phonemization モック更新 |
| `test/js/test-piper-plus-init-success.js` | 初期化スタブ更新 |
| `test/js/test-piper-plus-synthesize-flow.js` | 合成フロー モック更新 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テスト担当 | 1 | モックヘルパー書き換え、全テストファイルの更新 |
| レビュアー | 1 | テストカバレッジの確認、モック API の正当性検証 |

## 提供範囲とテスト

### 提供範囲

- テストヘルパーとテストファイルの更新 (本体コードの変更なし)
- 全 47 openjtalk-web テストファイルの pass 確認

### テスト項目

- `node --test test/js/test-*.js` で全テストが pass すること
- `SimpleUnifiedPhonemizer` への参照がテストコード内に残っていないこと (`_phonemesToIds` への参照も同様)
- テストカバレッジが M3 変更前と同等以上であること

### Unit テスト

- `createMockG2P()` の返すモックが `G2P.create()` の API 仕様を満たすこと
- `createMockEncoder()` の返すモックが `Encoder` の API 仕様を満たすこと
- 各テストファイルが新 API 経由で同等のアサーションを行っていること

### E2E テスト

- CI 環境 (ci.yml) で全テストスイートが pass すること

## 懸念事項とレビュー項目

### 懸念事項

1. **テスト数の増減**: `_phonemesToIds()` の 13+ 直接テストを `Encoder` テストに変換する際、テスト粒度が変わる可能性がある。テスト数が大幅に減少しないよう注意
2. **モック精度**: `G2P` / `Encoder` のモックが実装と乖離すると、テストが pass しても実際の統合で失敗する可能性がある。モックの API 仕様を `@piper-plus/g2p` の実際の型定義に基づいて構築する
3. **テスト実行順序**: テストファイル間の暗黙的な依存が存在しないか確認

### レビュー項目

1. モックヘルパーの API が `@piper-plus/g2p` の実際の API と一致していること
2. 削除された `_phonemesToIds()` のテストケースが `Encoder` テストで網羅されていること
3. `SimpleUnifiedPhonemizer` / `_phonemesToIds` への grep 結果がゼロであること
4. テスト実行結果のスクリーンショットまたはログの添付

## 一から作り直すとしたら

テストヘルパー (`create-mock-phonemizer.js`) を `@piper-plus/g2p` パッケージの型定義から自動生成するアプローチが理想的。モックと実装の乖離を防ぐため、TypeScript の `jest.mocked()` や `vitest.mock()` のような型安全なモッキングを採用する。

## 後続タスクへの連絡事項

- M3-5 (deprecated コード削除) の後にテストが壊れないよう、このチケットの完了時点で `SimpleUnifiedPhonemizer` をインポートしているテストが存在しないことを保証する
- M3-6 (CI 対応) ではテストコマンドの変更が不要であることを確認する (テストファイル名は変更しない方針)
- 新しいモックヘルパーの使い方を M4 のテスト担当者に共有する
