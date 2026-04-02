# M4-3: CLAUDE.md 更新

> **マイルストーン**: M4
> **前提チケット**: M1-7 (Python 最終削除), M2-7 (Rust 最終削除), M3-5 (JS deprecated コード削除)
> **後続チケット**: なし
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`CLAUDE.md` を G2P 移行完了後の状態に更新する。旧音素化モジュールのファイルパスを削除し、`piper_g2p` パッケージへの依存関係を追記し、「多言語 Phonemizer」セクションの実装パスを新しい構成に合わせて更新する。

## 実装する内容の詳細

### 1. 「実装済み機能 > 多言語 Phonemizer (8言語)」セクションの更新

現状:
```
**実装:** `phonemize/multilingual.py`, `phonemize/multilingual_id_map.py`, ...
**Phonemizer ABC:** `phonemize/base.py` (抽象基底), `phonemize/registry.py` (言語レジストリ)
```

変更後:
- 実装パスを `piper_g2p` パッケージに変更
- `piper_g2p` パッケージが全プラットフォーム (Python/Rust/JS) で共通の G2P 基盤を提供することを記載

### 2. 「重要なファイルパス > ソースコード」テーブルの更新

削除するパス (M1-7 で削除済み):
- 各言語の Phonemizer: `phonemize/english.py`, `phonemize/chinese.py`, `phonemize/korean.py`, `phonemize/spanish.py`, `phonemize/portuguese.py`, `phonemize/french.py`, `phonemize/swedish.py`
- ID マップ: `phonemize/jp_id_map.py`, `phonemize/{zh,ko,es,pt,fr,sv}_id_map.py`
- その他: `phonemize/base.py`, `phonemize/registry.py`, `phonemize/token_mapper.py`, `phonemize/multilingual.py`, `phonemize/multilingual_id_map.py`, `phonemize/bilingual.py`, `phonemize/bilingual_id_map.py`

追加するパス:
- `piper_g2p` パッケージへの参照 (パッケージ構成とインポートパス)

### 3. 「重要なファイルパス > npm パッケージ ソースコード」テーブルの更新

削除するパス (M3-5 で削除済み):
- `simple_unified_api.js`, `simple_english_phonemizer.js`, `japanese_phoneme_extract.js` 等

追加するパス:
- `@piper-plus/g2p` パッケージへの参照

### 4. 「重要なファイルパス > Rust ソースコード」テーブルの更新

削除するパス (M2-7 で削除済み):
- `src/rust/piper-core/src/phonemize/` 以下の各言語ファイル

追加するパス:
- `piper_g2p` クレートへの参照

### 5. `piper_g2p` 依存関係の追記

「実装済み機能」セクションまたは新セクションとして:
- `piper_g2p` パッケージの概要 (スタンドアロン G2P パッケージ)
- 対応プラットフォーム: Python (PyPI), Rust (crates.io), JS (npm @piper-plus/g2p)
- 依存関係の構成 (piper_train → piper_g2p, piper-core → piper_g2p, openjtalk-web → @piper-plus/g2p)

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `CLAUDE.md` | 多言語 Phonemizer セクション更新、ファイルパステーブル更新、piper_g2p 依存追記 |

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| ドキュメント担当 | 1 | CLAUDE.md の更新、削除パスの確認、新パスの追記 |

## 提供範囲とテスト

### 提供範囲

- `CLAUDE.md` の更新のみ

### テスト項目

- CLAUDE.md に記載されたファイルパスが実際に存在すること (削除済みパスが残っていないこと)
- piper_g2p の依存関係記述が正確であること

### Unit テスト

- テスト不要 (ドキュメント変更のみ)

### E2E テスト

- テスト不要 (ドキュメント変更のみ)

## 懸念事項とレビュー項目

### 懸念事項

1. **ファイルパスの網羅性**: M1/M2/M3 で削除された全ファイルが CLAUDE.md から除去されていること。削除リストとの突合せが必要
2. **CLAUDE.md の他セクションへの影響**: 「トラブルシューティング」「基本コマンド」等のセクションに旧モジュールへの参照が含まれていないか確認

### レビュー項目

1. 削除済みファイルパスが CLAUDE.md に残っていないこと
2. 新規追加パス (`piper_g2p` 関連) が正確であること
3. セクション間の整合性 (「実装済み機能」と「ファイルパス」が一致)
4. マークダウンの書式が壊れていないこと

## 一から作り直すとしたら

CLAUDE.md のファイルパステーブルを自動生成するスクリプトを用意する。`find` + ファイルパターンマッチングで実在するファイルのみをテーブルに列挙し、削除漏れや存在しないパスの記載を防止する。

## 後続タスクへの連絡事項

- このチケットは M4 の最終段階。後続タスクなし
- M4-4 (最終確認) で CLAUDE.md の更新内容も含めて最終チェックを行う
