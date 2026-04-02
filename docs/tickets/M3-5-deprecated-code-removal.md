# M3-5: deprecated コード削除

> **マイルストーン**: M3
> **前提チケット**: M3-4
> **後続チケット**: M3-6, M4-4
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

M3-1 ~ M3-4 で `@piper-plus/g2p` への移行が完了した後、不要となった旧音素化モジュール 6 ファイル (約 1200 行) を削除し、`index.js` の公開 export から `SimpleUnifiedPhonemizer` を除去する。これは **BREAKING CHANGE** であり、`SimpleUnifiedPhonemizer` を直接使用している下流ユーザーに影響する。

## 実装する内容の詳細

### 削除対象ファイル

| # | ファイル | 行数 | 説明 |
|---|---------|------|------|
| 1 | `src/wasm/openjtalk-web/src/simple_unified_api.js` | 692 | `SimpleUnifiedPhonemizer` 本体 (既に `@deprecated` マーク済み) |
| 2 | `src/wasm/openjtalk-web/src/simple_english_phonemizer.js` | 157 | 英語 IPA 音素化 (SimpleUnifiedPhonemizer が内部使用) |
| 3 | `src/wasm/openjtalk-web/src/japanese_phoneme_extract.js` | 155 | OpenJTalk ラベル → phoneme トークン抽出 |
| 4 | `src/wasm/openjtalk-web/src/phonemizer.js` | 63 | レガシー phonemizer インターフェース |
| 5 | `src/wasm/openjtalk-web/src/unified_api.js` | 100+ | レガシー統合 API |
| 6 | `src/wasm/openjtalk-web/src/unified_api_with_espeak.js` | 36 | eSpeak-ng 連携 (未使用レガシー) |

**合計**: 約 1200 行の削除

### 追加変更

1. **`index.js` の export 除去**
   - `SimpleUnifiedPhonemizer` を `export` / `module.exports` から削除
   - 関連する import 文の除去

2. **`package.json` の `files` フィールド確認**
   - 削除したファイルが `files` に明示列挙されていないか確認
   - `src/` ワイルドカードの場合は変更不要

3. **CHANGELOG への BREAKING CHANGE 記載**
   - `SimpleUnifiedPhonemizer` が公開 export から削除されたことを記録
   - 移行先: `@piper-plus/g2p` パッケージの `G2P` クラス

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/wasm/openjtalk-web/src/simple_unified_api.js` | 削除 |
| `src/wasm/openjtalk-web/src/simple_english_phonemizer.js` | 削除 |
| `src/wasm/openjtalk-web/src/japanese_phoneme_extract.js` | 削除 |
| `src/wasm/openjtalk-web/src/phonemizer.js` | 削除 |
| `src/wasm/openjtalk-web/src/unified_api.js` | 削除 |
| `src/wasm/openjtalk-web/src/unified_api_with_espeak.js` | 削除 |
| `src/wasm/openjtalk-web/src/index.js` | `SimpleUnifiedPhonemizer` の export 除去、関連 import 削除 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| JS 開発者 | 1 | ファイル削除、index.js の export 整理、CHANGELOG 更新 |
| レビュアー | 1 | 削除漏れの確認、公開 API の破壊的変更のドキュメント検証 |

## 提供範囲とテスト

### 提供範囲

- 6 ファイルの削除
- `index.js` の export 整理
- CHANGELOG への BREAKING CHANGE 記載

### テスト項目

- 削除したファイルへの import がプロジェクト全体に残っていないこと
- `node --test test/js/test-*.js` で全テストが pass すること (M3-4 で更新済み)
- `npm pack` でパッケージビルドが成功すること

### Unit テスト

- 削除対象ファイルの import が存在しないことを grep で検証
- `index.js` の export に `SimpleUnifiedPhonemizer` が含まれないことを検証

### E2E テスト

- `npm pack` → パッケージ内容に削除ファイルが含まれないことを確認
- パッケージサイズが削減されていることを確認 (約 1200 行 = 数十 KB の削減)

## 懸念事項とレビュー項目

### 懸念事項

1. **公開 API の BREAKING CHANGE**: `SimpleUnifiedPhonemizer` は `piper-plus` npm パッケージの公開 export であり、直接使用している下流ユーザーに影響する。npm publish 時にメジャーバージョンアップまたは明確な migration guide が必要
2. **隠れた参照**: テスト以外の場所 (demo ページ、ドキュメント、型定義ファイル) に `SimpleUnifiedPhonemizer` への参照が残っている可能性がある
3. **`unified_api.js` / `unified_api_with_espeak.js` の依存関係**: これらのレガシーファイルが他のファイルから import されていないか事前に確認が必要
4. **BREAKING CHANGE の semver 戦略**: `SimpleUnifiedPhonemizer` は public export であるため、削除は BREAKING CHANGE となる。package.json の version を semver major bump (e.g., 0.x → 1.0.0 or 0.2.0) するか、deprecation period を設けるか方針を決定すること。CHANGELOG.md に breaking change を記載する

### レビュー項目

1. 削除対象 6 ファイルへの参照がプロジェクト全体でゼロであること (`grep -r` で確認)
2. `index.js` の export リストが正しく更新されていること
3. `types/index.d.ts` (TypeScript 型定義) から `SimpleUnifiedPhonemizer` の型が削除されていること
4. CHANGELOG の BREAKING CHANGE 記載が正確であること
5. `package.json` の `version` フィールドの更新方針 (semver)

## 一から作り直すとしたら

最初から G2P ロジックを別パッケージ (`@piper-plus/g2p`) として設計し、`piper-plus` npm パッケージは推論エンジンのみを提供する構成にすべきだった。音素化ロジックを npm パッケージの公開 API として露出させたことで、内部実装の変更が BREAKING CHANGE になってしまった。

## 後続タスクへの連絡事項

- M3-6 (CI 対応) では、削除されたファイルがテスト・ビルドプロセスで参照されていないことを確認する
- M4-1 (クロスプラットフォーム互換テスト) では、JS 側の G2P が `@piper-plus/g2p` 経由であることを前提とする
- M4-4 (最終確認) では、JS の削除ファイル数が 6 ファイル (約 1200 行) であることを検証する
- npm publish 時のバージョニング方針 (メジャーバージョンアップの要否) を M3-6 完了前に決定する
