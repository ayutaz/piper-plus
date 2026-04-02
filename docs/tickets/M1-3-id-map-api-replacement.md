# M1-3: ID マップ API 置換

> **マイルストーン**: M1
> **前提チケット**: M0-3 (互換テストで旧新マップ一致を検証済み), M1-1
> **後続チケット**: M1-7 (旧コード削除)
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

言語別に分散している ID マップ取得関数 (`get_japanese_id_map()`, `get_bilingual_id_map()`, `get_multilingual_id_map()`) を、piper_g2p の統一 API `get_phoneme_id_map()` に置き換える。これにより言語構成の変更時にコード修正が不要になり、新言語追加のコストが大幅に削減される。

## 実装する内容の詳細

### API 置換マッピング

| 現在の API | 置換後の API | 備考 |
|-----------|-------------|------|
| `get_japanese_id_map()` | `get_phoneme_id_map("ja")` | 日本語モノリンガル |
| `get_bilingual_id_map()` | `get_phoneme_id_map("ja-en")` | バイリンガル (後方互換) |
| `get_multilingual_id_map(["ja","en","zh","es","fr","pt"])` | `get_phoneme_id_map("ja-en-zh-es-fr-pt")` | 引数形式がリスト → ハイフン区切り文字列に変更 |

### 変更対象ファイル一覧

**注意**: 以下の行番号は調査時点のものであり、他チケットの変更により変動する可能性がある。実装時は `grep -n` で最新の行番号を確認すること。

変更対象は関数の呼び出し箇所だけでなく、ファイル冒頭の import 文も含む。

| ファイル | 行 | 現在のコード | 置換後のコード |
|---------|-----|-------------|---------------|
| `preprocess.py` | 76 | `from .phonemize.jp_id_map import get_japanese_id_map` | `from piper_g2p import get_phoneme_id_map` |
| `preprocess.py` | 230 | `id_map = get_japanese_id_map()` | `id_map = get_phoneme_id_map("ja")` |
| `preprocess.py` | 244 | `id_map = get_multilingual_id_map(languages)` | `id_map = get_phoneme_id_map("-".join(languages))` |
| `tools/prepare_bilingual_dataset.py` | 25-30 | `from ..phonemize.bilingual_id_map import get_bilingual_id_map` | `from piper_g2p import get_phoneme_id_map` |
| `tools/prepare_bilingual_dataset.py` | (呼び出し箇所) | `get_bilingual_id_map()` | `get_phoneme_id_map("ja-en")` |
| `tools/add_prosody_features.py` | 16 | `from ..phonemize.jp_id_map import get_japanese_id_map` | `from piper_g2p import get_phoneme_id_map` |
| `tools/add_prosody_features.py` | (呼び出し箇所) | `get_japanese_id_map()` | `get_phoneme_id_map("ja")` |
| `tools/prepare_multilingual_dataset.py` | 1213 | `get_multilingual_id_map(languages)` | `get_phoneme_id_map("-".join(languages))` |

### 変更の詳細

1. **import 文の置換**: 各ファイルの言語別 import を `from piper_g2p import get_phoneme_id_map` に統一
2. **関数呼び出しの置換**: 上記マッピングに従い呼び出しを置換
3. **引数形式の変換**: `get_multilingual_id_map` はリスト引数だが、`get_phoneme_id_map` はハイフン区切り文字列。`"-".join(languages)` で変換する
4. **バイリンガル後方互換**: `get_phoneme_id_map("ja-en")` が旧 `get_bilingual_id_map()` と同一のマップを返すことは M0-3 の互換テストで検証済み

### 注意点: 言語キーの正規化

`get_phoneme_id_map()` は内部で言語キーをソートする (例: `"en-ja"` → `"ja-en"`)。呼び出し側は言語の順序を気にする必要がない。ただし、既存コードが特定の順序を前提としている箇所がないか確認が必要。

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | 4 ファイルの API 置換 |
| レビュアー | 1 | マップ一致の検証、後方互換性の確認 |

## 提供範囲とテスト

### 提供範囲

- `preprocess.py` -- import と呼び出し 3 箇所の変更
- `tools/prepare_bilingual_dataset.py` -- import と呼び出しの変更
- `tools/add_prosody_features.py` -- import と呼び出しの変更
- `tools/prepare_multilingual_dataset.py` -- 呼び出しの変更

### テスト項目

- 各言語構成で `get_phoneme_id_map()` が旧関数と同一のマップを返すこと
- preprocess.py の日本語モノリンガル/マルチリンガル両パスで正しい ID マップが使用されること
- 言語キーの順序に依存しないことの確認

### Unit テスト

1. **マップ一致検証 (日本語モノリンガル)**:
   ```python
   old_map = get_japanese_id_map()
   new_map = get_phoneme_id_map("ja")
   assert old_map == new_map
   ```
2. **マップ一致検証 (バイリンガル)**:
   ```python
   old_map = get_bilingual_id_map()
   new_map = get_phoneme_id_map("ja-en")
   assert old_map == new_map
   ```
3. **マップ一致検証 (マルチリンガル 6 言語)**:
   ```python
   old_map = get_multilingual_id_map(["ja","en","zh","es","fr","pt"])
   new_map = get_phoneme_id_map("ja-en-zh-es-fr-pt")
   assert old_map == new_map
   ```
4. **言語キー順序の正規化**: `get_phoneme_id_map("en-ja")` と `get_phoneme_id_map("ja-en")` が同一マップを返すこと

### E2E テスト

1. **preprocess マルチリンガル**: 小規模データセット (10 発話) を前処理し、生成される `phoneme_ids` が置換前の出力と完全一致することを確認
2. **prepare_bilingual_dataset**: バイリンガルデータセット作成スクリプトが正常に動作すること
3. **add_prosody_features**: 既存データセットへの prosody_features 追加が正常に動作すること

## 懸念事項とレビュー項目

### 懸念事項

1. **バイリンガル後方互換性**: `get_bilingual_id_map()` は JA+EN 固有の最適化 (シンボル数 97) を含んでいた。`get_phoneme_id_map("ja-en")` が同一の 97 シンボルマップを返すことは M0-3 で検証済みだが、エッジケース (特殊記号、PUA 文字) の一致を再確認する
2. **preprocess.py の `languages` 変数の型**: 現在リスト型だが、ハイフン区切り文字列への変換 (`"-".join(languages)`) で言語コードにハイフンが含まれるケース (例: `zh-CN`) がないか確認が必要。現状の言語コードは全て 2 文字 (ja, en, zh, ko, es, fr, pt, sv) なので問題ないが、将来の拡張性を考慮する
3. **既存データセットとの互換性**: 既に前処理済みのデータセット (`config.json` 内の `phoneme_id_map`) は変更されない。新規前処理時のみ影響する

### レビュー項目

1. 全置換箇所で旧 API と新 API の戻り値が完全一致すること
2. `"-".join(languages)` の変換が全箇所で正しいこと
3. import の残骸 (旧モジュールの import) がないこと
4. preprocess.py の日本語モノリンガルパスとマルチリンガルパスの両方がテストされていること

## 一から作り直すとしたら

言語別の ID マップ関数 (`get_japanese_id_map`, `get_bilingual_id_map`, `get_multilingual_id_map`) を最初から作らず、`get_phoneme_id_map(language_key)` の統一 API のみを提供する。言語構成は文字列キー (例: `"ja-en-zh"`) で指定し、内部で動的にマップを構築する設計にする。バイリンガル専用の最適化は不要 -- マルチリンガル API が 2 言語にも対応すれば十分。

## 後続タスクへの連絡事項

- 旧 ID マップモジュール (`jp_id_map.py`, `bilingual_id_map.py`, `multilingual_id_map.py`, `zh_id_map.py` 等) は M1-7 の削除対象に含まれる。ただし、M1-4 の preprocess.py リファクタが完了するまで削除しないこと
- `get_phoneme_id_map()` の戻り値は `dict[str, int]` (トークン文字列 → ID) であり、旧 API と同一の型。M1-4 でこの戻り値を使う際に型変換は不要
- 言語キーの正規化ルール (アルファベット順ソート) を M1-4 の実装者に共有すること
