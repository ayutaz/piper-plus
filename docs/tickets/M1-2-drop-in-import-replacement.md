# M1-2: 低リスク import 置換

> **マイルストーン**: M1
> **前提チケット**: M1-1
> **後続チケット**: M1-7 (旧コード削除)
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

API が完全に同一である 4 箇所の import を piper_g2p 経由に切り替える。いずれも関数シグネチャ・戻り値が同一のドロップイン置換であり、ロジック変更は不要。

## 実装する内容の詳細

### 置換対象一覧

| ファイル | 行 | 現在の import | 置換後の import | 対象シンボル |
|---------|-----|--------------|----------------|-------------|
| `infer_onnx.py` | 31, 62 | `from .phonemize.multilingual import UnicodeLanguageDetector` | `from piper_g2p import UnicodeLanguageDetector` | `UnicodeLanguageDetector` |
| `infer_onnx.py` | 106 | `from .phonemize.registry import get_phonemizer` | `from piper_g2p import get_phonemizer` | `get_phonemizer` |
| `vits/lightning.py` | 177 | `from ..phonemize.registry import get_phonemizer` | `from piper_g2p import get_phonemizer` | `get_phonemizer` |
| `update_model_config.py` | 16 | `from .phonemize.token_mapper import FIXED_PUA_MAPPING, TOKEN2CHAR` | `from piper_g2p.encode.pua import FIXED_PUA_MAPPING, TOKEN2CHAR` | `FIXED_PUA_MAPPING`, `TOKEN2CHAR` |

### 変更手順

1. 各ファイルの import 文を置換
2. ローカルの旧 import パスはコメントアウトではなく完全に削除 (旧コード自体は M1-7 で削除)
3. 全テストを実行して既存動作が維持されることを確認

### 変更しないもの

- 旧モジュールファイル (`phonemize/multilingual.py`, `phonemize/registry.py`, `phonemize/token_mapper.py`) -- M1-7 で削除
- 呼び出し側のロジック -- API 同一のため変更不要

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装者 | 1 | 4 ファイルの import 置換 |
| レビュアー | 1 | 置換の正確性、テスト結果の確認 |

## 提供範囲とテスト

### 提供範囲

- `infer_onnx.py` -- import 2 箇所の変更
- `vits/lightning.py` -- import 1 箇所の変更
- `update_model_config.py` -- import 1 箇所の変更

### テスト項目

- 各ファイルが import エラーなく読み込めること
- 置換したシンボルが旧シンボルと同一オブジェクトであること (`is` または `==` で比較)

### Unit テスト

1. **import 検証**: 各置換後のシンボルが正しく import できることを確認
   ```python
   from piper_g2p import UnicodeLanguageDetector
   from piper_g2p import get_phonemizer
   from piper_g2p import FIXED_PUA_MAPPING, TOKEN2CHAR
   ```
2. **関数呼び出し検証**: `get_phonemizer("ja")` が JapanesePhonemizer インスタンスを返すことを確認
3. **定数一致検証**: `FIXED_PUA_MAPPING` と `TOKEN2CHAR` の値が旧実装と完全一致することを確認

### E2E テスト

1. **infer_onnx `--text` フラグ動作確認**: `--text "こんにちは"` での推論が置換前と同じ音声を生成すること
   ```bash
   CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
     --model test/models/multilingual-test-medium.onnx \
     --config test/models/config.json \
     --output-dir /tmp/test \
     --text "こんにちは" --language ja-en-zh-es-fr-pt --speaker-id 0
   ```
2. **lightning.py 経由の phonemizer 取得**: 学習スクリプトの初期化で get_phonemizer が正しく動作すること

## 懸念事項とレビュー項目

### 懸念事項

1. **piper_g2p の公開 API 名の差異**: piper_g2p 側で `UnicodeLanguageDetector` 等がトップレベル `__init__.py` から公開されていることを事前に確認する必要がある。M0 の API 設計で確定済みの前提だが、念のため確認する
2. **循環 import**: piper_g2p が piper_train の何かを import している場合に循環が発生する可能性。piper_g2p は独立パッケージなので通常は問題ないが確認する

### レビュー項目

1. 全 4 箇所の import パスが正しいこと
2. import 以外のコード変更がないこと (ドロップイン置換であることの確認)
3. 旧 import パスのコメント残骸がないこと
4. テスト結果が全てパスしていること

## 一から作り直すとしたら

piper_train 内部に G2P コードを持たず、最初から piper_g2p を外部依存として参照する設計にする。そうすれば import 置換作業自体が不要になる。

## 後続タスクへの連絡事項

- このチケットで置換した 4 ファイルの旧 import パス元モジュールは、M1-7 の削除対象候補に含まれる
- `get_phonemizer` が piper_g2p 側に切り替わったことにより、M1-4 の preprocess.py リファクタでも同じ piper_g2p 版を使用すること
- `UnicodeLanguageDetector`, `FIXED_PUA_MAPPING`, `TOKEN2CHAR` は他のファイルからも参照される可能性があるため、M1-7 の削除前に全参照箇所を再確認すること
