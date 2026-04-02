# M1-1: piper-g2p 依存関係の追加

> **マイルストーン**: M1
> **前提チケット**: M0 完了
> **後続チケット**: M1-2, M1-3, M1-4, M1-5 (M1-2〜M1-5 がこのチケットに依存)
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`src/python/pyproject.toml` に `piper-g2p` パッケージを依存関係として追加し、piper_train が piper-g2p 経由で全言語の G2P 機能を利用できるようにする。現在 piper_train は各言語の依存 (pyopenjtalk-plus, g2p-en, pypinyin 等) を個別に管理しているが、これを piper-g2p の extras 機構に委譲する。

## 実装する内容の詳細

### 現状

`src/python/pyproject.toml` の依存構成:

- **必須依存**: numpy<2.3, onnxruntime 等
- **train extras**: pyopenjtalk-plus, g2p-en, pypinyin, g2pk2 等の言語別 G2P ライブラリを個別に列挙

### 変更内容

1. **`dependencies`** セクションに `piper-g2p` を追加
   - バージョン制約: piper-g2p の安定リリースバージョンを指定 (例: `piper-g2p>=0.1.0`)
2. **`[project.optional-dependencies]` の `train`** セクションに `piper-g2p[all]` を追加
   - `piper-g2p[all]` は全言語 (JA/EN/ZH/KO/ES/FR/PT/SV) の依存をまとめてインストールする extras
   - 既存の個別言語依存 (pyopenjtalk-plus, g2p-en 等) は M1 完了まで残す (段階的移行)
3. **既存の個別言語依存の削除は M1-7 (最終削除チケット) で実施** -- このチケットでは追加のみ

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/python/pyproject.toml` | `dependencies` に `piper-g2p` 追加、`train` extras に `piper-g2p[all]` 追加 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 設定担当 | 1 | pyproject.toml の編集、依存解決の確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/pyproject.toml` の変更のみ

### テスト項目

- `uv sync` が正常に完了すること
- `uv run python -c "import piper_plus_g2p"` が成功すること
- `uv run python -c "from piper_plus_g2p import get_phonemizer, get_phoneme_id_map"` が成功すること
- 既存の個別言語 import (`import pyopenjtalk`, `import g2p_en` 等) が引き続き動作すること

### Unit テスト

- `piper_plus_g2p` のインポートが成功することを確認するスモークテスト
- `piper_plus_g2p` の主要公開 API (`get_phonemizer`, `get_phoneme_id_map`, `PiperEncoder`) が存在することを確認

### E2E テスト

- `uv sync --extra train` 後に既存の学習パイプライン (`piper_train`) が正常に動作すること (依存衝突がないことの確認)

## 懸念事項とレビュー項目

### 懸念事項

1. **依存バージョン衝突**: piper-g2p が依存する pyopenjtalk-plus / g2p-en 等のバージョンと、piper_train が直接指定するバージョンが衝突する可能性がある。衝突が発生した場合は piper_train 側のバージョン制約を緩和する
2. **numpy バージョン制約**: piper_train は `numpy<2.3` を要求している。piper-g2p 側の numpy 制約と互換性があることを確認する

### レビュー項目

1. バージョン制約が適切か (下限・上限)
2. `piper-g2p` と `piper-g2p[all]` の使い分けが正しいか
3. 既存の個別言語依存が残っていること (段階的移行のため)
4. `uv lock` で依存解決が成功すること

## 一から作り直すとしたら

最初から piper-g2p を唯一の G2P 依存として設計し、各言語の依存を個別に pyproject.toml に列挙しない構成にする。piper-g2p の extras (`piper-g2p[ja]`, `piper-g2p[en]` 等) で必要な言語のみをインストールできるようにし、piper_train 側は言語固有の依存を一切知らない状態にする。

## 後続タスクへの連絡事項

- M1-2 以降のチケットは、このチケットの完了後に `from piper_plus_g2p import ...` が利用可能であることを前提とする
- 既存の個別言語 import パスは M1 完了まで並行して動作する。M1-7 で最終削除を行う
- piper-g2p のバージョンが確定したら、後続チケットの実装者に共有すること
