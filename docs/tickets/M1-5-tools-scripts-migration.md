# M1-5: tools/ スクリプト移行

> **マイルストーン**: M1
> **前提チケット**: M1-1, M1-3
> **後続チケット**: M1-7
> **見積り**: 中
> **リスク**: 中

## タスク目的とゴール

`src/python/piper_train/tools/` 配下の 3 つのデータセット準備スクリプトが `piper_train.phonemize` を直接 import している。これらを `piper_g2p` 経由の import に書き換え、旧 phonemize ディレクトリへの依存を解消する。また、PiperEncoder が代替するヘルパー関数 (ID リマップ・パディング挿入) を削除する。

## 実装する内容の詳細

### 1. `tools/prepare_multilingual_dataset.py`

以下の import を書き換える:

| 箇所 | 旧 import | 新 import |
|------|----------|----------|
| L279-281 | `from piper_train.phonemize.multilingual import MultilingualPhonemizer` | `from piper_g2p.multilingual import MultilingualPhonemizer` |
| L282 | `from piper_train.phonemize.registry import get_phonemizer` | `from piper_g2p.registry import get_phonemizer` |
| L374-376 | `from piper_train.phonemize.multilingual import MultilingualPhonemizer` | `from piper_g2p.multilingual import MultilingualPhonemizer` |
| L390 | `from piper_train.phonemize.chinese import phonemize_from_pinyin_syllables` | `from piper_g2p.chinese import phonemize_from_pinyin_syllables` |
| L1213-1215 | `from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map` | `from piper_g2p.encode.id_maps import get_phoneme_id_map` |

API 変更:
- `get_multilingual_id_map(languages)` を `get_phoneme_id_map("ja-en-zh-es-fr-pt")` に変更 (リスト引数からハイフン区切り文字列に)

### 2. `tools/prepare_bilingual_dataset.py`

以下の import を書き換える:

| 箇所 | 旧 import | 新 import |
|------|----------|----------|
| L23 | `from piper_train.phonemize.bilingual import BilingualPhonemizer` | `from piper_g2p.multilingual import MultilingualPhonemizer` |
| L24-26 | `from piper_train.phonemize.bilingual_id_map import get_bilingual_id_map` | `from piper_g2p.encode.id_maps import get_phoneme_id_map` |
| L27-29 | `from piper_train.phonemize.jp_id_map import get_japanese_id_map` | `from piper_g2p.encode.id_maps import get_phoneme_id_map` |

削除する関数:
- `remap_ja_phoneme_ids()` (L43-67): PiperEncoder が ID マッピングを一貫して処理するため不要
- `_add_inter_phoneme_padding()` (L70-127): PiperEncoder の `post_process_ids` が BOS/EOS 付与とインターフォネームパディングを処理するため不要

### 3. `tools/add_prosody_features.py`

以下の import を書き換える:

| 箇所 | 旧 import | 新 import |
|------|----------|----------|
| L14 | `from piper_train.phonemize.japanese import phonemize_japanese_with_prosody` | `from piper_g2p.japanese import phonemize_japanese_with_prosody` |
| L15 | `from piper_train.phonemize.jp_id_map import get_japanese_id_map` | `from piper_g2p.encode.id_maps import get_phoneme_id_map` |

API 変更:
- `get_japanese_id_map()` を `get_phoneme_id_map("ja")` に変更

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装担当 | 1 | 3 スクリプトの import 書き換え、ヘルパー関数削除、動作確認 |
| レビュー担当 | 1 | API 互換性の確認、エッジケースの検証 |

## 提供範囲とテスト

### 提供範囲

- `src/python/piper_train/tools/prepare_multilingual_dataset.py` の import 書き換え
- `src/python/piper_train/tools/prepare_bilingual_dataset.py` の import 書き換え + ヘルパー関数削除
- `src/python/piper_train/tools/add_prosody_features.py` の import 書き換え

### テスト項目

- 各スクリプトが `import` エラーなく読み込めること
- `get_phoneme_id_map()` の戻り値が旧 `get_multilingual_id_map()` / `get_bilingual_id_map()` と互換であること
- PiperEncoder 経由の phoneme_ids が旧ヘルパー関数の出力と一致すること

### Unit テスト

- 各ツールの import が成功することを確認:
  - `from piper_train.tools.prepare_multilingual_dataset import main`
  - `from piper_train.tools.prepare_bilingual_dataset import main`
  - `from piper_train.tools.add_prosody_features import main`
- `get_phoneme_id_map("ja-en-zh-es-fr-pt")` が `get_multilingual_id_map(["ja","en","zh","es","fr","pt"])` と同一の結果を返すこと

### E2E テスト

- `prepare_multilingual_dataset.py --dry-run` (小規模サンプル) が正常終了すること
- `add_prosody_features.py` を小規模データセットで実行し、prosody_features が正しく生成されること

## 懸念事項とレビュー項目

### 懸念事項

1. **`remap_ja_phoneme_ids()` と `_add_inter_phoneme_padding()` の完全代替**: PiperEncoder がこれらの関数のすべてのエッジケース (空リスト、BOS/EOS ストリッピング、既存パディングのスキップ等) をカバーしているか検証が必要。`remap_ja_phoneme_ids()` と `_add_inter_phoneme_padding()` の挙動が PiperEncoder で完全に再現されることを、実装前に手動テストで確認すること。具体的には、同一入力に対して旧関数と PiperEncoder の出力 (phoneme_ids, prosody_features) を比較し、完全一致することを検証する。差異がある場合は PiperEncoder 側の修正を M0 に追加する。
2. **AISHELL-3 pinyin ショートカット**: `_phonemize_zh_pinyin_single` が `piper_g2p.chinese.phonemize_from_pinyin_syllables` を使用可能か (関数シグネチャの互換性)
3. **Worker プロセスの初期化**: `ProcessPoolExecutor` の worker 内で `piper_g2p` の import が正常に動作すること (マルチプロセス環境でのモジュール初期化)
4. **行番号の参照値について**: 行番号は調査時点の参照値。実装時は関数名で grep して最新位置を確認すること。

### レビュー項目

1. すべての旧 import パスが新パスに置き換わっていること (grep で `piper_train.phonemize` が tools/ 内に残っていないこと)
2. 削除した `remap_ja_phoneme_ids()` と `_add_inter_phoneme_padding()` の呼び出し元がすべて更新されていること
3. `get_phoneme_id_map()` の API 変更 (引数形式) が正しく適用されていること

## 一から作り直すとしたら

tools/ スクリプトは piper_g2p が最初に作られた時点で真っ先に移行すべきだった。データセット準備ツールは G2P パイプラインの主要な消費者であり、piper_g2p の設計段階でこれらのユースケースを考慮していれば、`remap_ja_phoneme_ids()` のような中間的なヘルパー関数は最初から不要だった。

## 後続タスクへの連絡事項

- M1-7 (旧 phonemize 削除) の前提として、本チケット完了後に tools/ 配下から `piper_train.phonemize` への参照が完全に除去されていることを確認すること
- `prepare_bilingual_dataset.py` のヘルパー関数削除により、テストコードに影響がある場合は M1-8 で対応すること
- Worker 初期化関数 (`_init_phonemize_worker`, `_init_zh_pinyin_worker`) の import パスも書き換え済みであることを M1-7 担当者に連絡すること
