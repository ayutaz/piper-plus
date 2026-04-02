# M1-6: dead code 削除

> **マイルストーン**: M1
> **前提チケット**: なし (独立タスク)
> **後続チケット**: M1-7
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`src/python/piper_train/inference_utils.py` に存在する dead code を特定・削除する。このファイルは存在しないモジュール (`piper_train.phonemize.accent_processor`) に依存しており、実行時に必ず ImportError になる。コードベースの grep 結果から、このファイル内の関数・クラスは他のどこからも参照されていないことが確認されている。

## 実装する内容の詳細

### 調査結果

`inference_utils.py` の内容:

| 箇所 | 要素 | 状態 |
|------|------|------|
| L7 | `from .phonemize.accent_processor import JapaneseAccentProcessor` | 存在しないモジュール参照 -- 必ず ImportError |
| L8 | `from .phonemize.japanese import phonemize_japanese` | 旧 phonemize 依存 |
| L14-65 | `prepare_text_for_inference()` | `JapaneseAccentProcessor` に依存、呼び出し元なし |
| L68-107 | `apply_accent_modifications()` | `AccentController` からのみ呼ばれる、外部呼び出し元なし |
| L110-189 | `AccentController` クラス | `JapaneseAccentProcessor` に依存、呼び出し元なし |

### grep 確認結果

`inference_utils`、`AccentController`、`prepare_text_for_inference`、`apply_accent_modifications` のいずれも `inference_utils.py` 自身以外からの参照がない。

### 変更内容

1. **`src/python/piper_train/inference_utils.py` を削除する**
   - ファイル全体が dead code であり、存在しないモジュールへの依存により実行不可能
   - 外部からの参照が一切ないことを grep で確認済み

2. **(任意) アクセント処理の将来対応 Issue を作成する**
   - `accent_processor.py` は計画的な機能であった可能性がある
   - 削除にあたり、将来のアクセント制御機能の実装予定がある場合は別途 Issue を起票する

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/inference_utils.py` | ファイル削除 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 調査・実装担当 | 1 | codebase 全体の grep による参照調査、ファイル削除、CI 確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/piper_train/inference_utils.py` の削除

### テスト項目

- 削除後に `piper_train` パッケージ全体の import が正常に動作すること
- 既存の全テストスイートが pass すること

### Unit テスト

- なし (コード削除のため新規テスト不要)
- 既存テストに `inference_utils` を参照するものがないことを grep で確認

### E2E テスト

- `uv run python -c "import piper_train"` が成功すること
- 既存 CI テストマトリクスが全 pass すること

## 懸念事項とレビュー項目

### 懸念事項

1. **計画的機能の可能性**: `accent_processor.py` とそれに依存する `inference_utils.py` は、アクセント制御機能の実装途中であった可能性がある。現在は prosody_features (A1/A2/A3) による prosody 制御が実装済みであり、`AccentController` のアプローチ (テキスト置換による `↑`/`↓`/`→`/`⤴` マーカー挿入) とは設計思想が異なる。将来のアクセント制御機能が必要な場合は、prosody_features ベースのアプローチで再設計すべき
2. **リポジトリ外からの参照**: `inference_utils` をリポジトリ外のスクリプトやノートブックから参照している可能性がゼロではないが、`JapaneseAccentProcessor` が存在しない以上、現時点でも動作していない

### レビュー項目

1. `inference_utils` への参照がリポジトリ全体に存在しないことの grep 確認
2. `accent_processor` への参照が `inference_utils.py` 以外に存在しないことの確認
3. 将来のアクセント制御機能について Issue を起票する必要があるかの判断

## 一から作り直すとしたら

実装が完了していないモジュール (`accent_processor.py`) への依存を持つファイルはそもそもコミットすべきではなかった。プロトタイプコードは別ブランチで管理し、動作可能な状態になるまで main/dev にマージしないルールを設ける。

## 後続タスクへの連絡事項

- M1-7 (旧 phonemize 削除) にとって、`inference_utils.py` が削除済みであることで `phonemize/accent_processor.py` (存在しないファイル) への参照がなくなり、削除がクリーンになる
- `phonemize/` ディレクトリ内に `accent_processor.py` は実際には存在しないが、念のため M1-7 実行前に確認すること
