# [P0-007] piper_train 互換シム

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-007
> 依存チケット: P0-004, P0-005, P0-006
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper_g2p` パッケージへの移行後も、既存の `piper_train.phonemize` からの import パスを維持する互換レイヤーを提供する。`piper_train` の学習パイプライン、推論スクリプト、データセット準備ツールが変更なしで動作し続けることを保証する。

### ゴール
- `from piper_train.phonemize import get_phonemizer, Phonemizer, ProsodyInfo` が動作する
- `from piper_train.phonemize.japanese import phonemize_japanese` が BOS/EOS/PUA 含む従来の出力形式を返す
- `from piper_train.phonemize.english import phonemize_english` が従来通り動作する
- 既存テスト (`tests/`) が変更なしで pass する
- `DeprecationWarning` は Phase 0 では発行しない

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 変更内容 |
|---------|---------|
| `src/python/piper_train/phonemize/base.py` | `piper_g2p` から ABC/ProsodyInfo を re-import + 互換メソッド維持 |
| `src/python/piper_train/phonemize/japanese.py` | 内部で `piper_g2p.JapanesePhonemizer` + `PiperEncoder` を使用し従来出力に変換 |
| `src/python/piper_train/phonemize/english.py` | 内部で `piper_g2p.EnglishPhonemizer` を使用 |
| `src/python/piper_train/phonemize/registry.py` | 内部で `piper_g2p.registry` に委譲 |
| `src/python/piper_train/phonemize/token_mapper.py` | 内部で `piper_g2p.encode.pua` に委譲 |

### 実装手順

1. **`base.py` の互換ラッパー**

   ```python
   # src/python/piper_train/phonemize/base.py (変更後)
   """Compatibility shim: re-exports from piper_g2p + legacy methods."""

   from piper_g2p import ProsodyInfo  # noqa: F401 -- re-export

   # piper_train の Phonemizer ABC は get_phoneme_id_map() + post_process_ids() を持つ
   # piper_g2p の Phonemizer ABC はこれらを持たない
   # -> 互換のため piper_train 版を維持する

   from abc import ABC, abstractmethod

   class Phonemizer(ABC):
       """piper_train 互換 Phonemizer ABC.

       piper_g2p.Phonemizer に加えて get_phoneme_id_map() と
       post_process_ids() を持つ。
       """

       @abstractmethod
       def phonemize(self, text: str) -> list[str]: ...

       @abstractmethod
       def phonemize_with_prosody(self, text, ...): ...

       @abstractmethod
       def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...

       def post_process_ids(self, phoneme_ids, prosody_features,
                            phoneme_id_map, eos_token="$"):
           """BOS/EOS/パディング挿入 (従来互換)."""
           # 現在の実装をそのまま維持
           ...
   ```

2. **`japanese.py` の互換ラッパー**

   ```python
   # src/python/piper_train/phonemize/japanese.py (変更後)

   import piper_g2p
   from piper_g2p.encode import PiperEncoder, get_phoneme_id_map
   from piper_g2p.encode.pua import map_token as _map_token

   # 内部で piper_g2p を使用し、従来の出力形式に変換
   _ja_phonemizer = None

   def _get_ja():
       global _ja_phonemizer
       if _ja_phonemizer is None:
           _ja_phonemizer = piper_g2p.get_phonemizer("ja")
       return _ja_phonemizer

   def phonemize_japanese(text, custom_dict=None):
       """従来互換: BOS/EOS/PUA 含む出力を返す。"""
       ja = _get_ja()
       tokens = ja.phonemize(text)  # IPA トークン列 (BOS/EOS なし)

       # BOS を先頭に追加
       tokens = ["^"] + tokens

       # EOS を末尾に追加
       q_type = _get_question_type(text)
       tokens.append(q_type)

       # PUA 変換
       from .token_mapper import map_sequence
       return map_sequence(tokens)
   ```

   注: `CustomDictionary` の処理は Phase 0 では piper_g2p に含まれないため、既存の `CustomDictionary` コードパスをそのまま残す。`piper_g2p.JapanesePhonemizer` がカスタム辞書非対応の場合は、テキスト前処理として `CustomDictionary.apply_to_text()` を先に適用する。

3. **影響ファイルの確認**

   以下のファイルが `piper_train.phonemize` に依存している:

   | ファイル | import 内容 |
   |---------|-----------|
   | `preprocess.py` | `phonemize_japanese_with_prosody`, `get_japanese_id_map`, `MultilingualPhonemizer` |
   | `update_model_config.py` | `FIXED_PUA_MAPPING`, `TOKEN2CHAR` |
   | `vits/lightning.py` | (間接的に preprocess.py 経由) |
   | `tools/add_prosody_features.py` | `phonemize_japanese_with_prosody`, `get_japanese_id_map` |
   | `tools/prepare_multilingual_dataset.py` | `MultilingualPhonemizer`, `get_phonemizer` |
   | `tools/prepare_bilingual_dataset.py` | `BilingualPhonemizer`, `get_bilingual_id_map` |
   | `infer_onnx.py` | `get_phonemizer`, `UnicodeLanguageDetector` |
   | `inference_utils.py` | `phonemize_japanese`, `JapaneseAccentProcessor` |

   これらは全て `piper_train.phonemize.*` 経由で import しているため、互換シムが正しく動作すれば変更不要。

### API / インターフェース

既存 API と完全互換。新規 API は追加しない。

```python
# 以下が全て変更なしで動作すること

from piper_train.phonemize import get_phonemizer, Phonemizer, ProsodyInfo
from piper_train.phonemize.japanese import phonemize_japanese, phonemize_japanese_with_prosody
from piper_train.phonemize.english import phonemize_english, EnglishPhonemizer
from piper_train.phonemize.registry import get_phonemizer, available_languages
from piper_train.phonemize.token_mapper import FIXED_PUA_MAPPING, map_sequence
from piper_train.phonemize.jp_id_map import get_japanese_id_map
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 互換レイヤー実装 | 1 | base.py, japanese.py, english.py, registry.py のラッパー作成 |
| リグレッションテスト | 1 | 既存テストの全パス確認、互換性検証 |

---

## 4. テスト計画

### 提供範囲
既存 import パスの後方互換性。出力の数値的一致。

### Unit テスト (4+ ケース)

```python
# test_compat_shim.py

def test_import_phonemizer_from_piper_train():
    """piper_train.phonemize からの import が動作すること。"""
    from piper_train.phonemize import Phonemizer, ProsodyInfo
    from piper_train.phonemize import get_phonemizer
    assert Phonemizer is not None
    assert ProsodyInfo is not None

def test_phonemize_japanese_output_format():
    """phonemize_japanese() が BOS/EOS/PUA 含む従来形式を返すこと。"""
    from piper_train.phonemize.japanese import phonemize_japanese
    tokens = phonemize_japanese("こんにちは")
    # BOS が先頭にある
    assert tokens[0] == "^" or ord(tokens[0]) < 0xF900
    # EOS が末尾にある ("$" の PUA 表現)
    # PUA 文字が含まれる (ch -> U+E00E 等)
    has_pua = any(0xE000 <= ord(t) <= 0xF8FF for t in tokens for t_ch in t if len(t) == 1)
    # 注: map_sequence 後は各トークンが 1 文字

def test_phonemize_japanese_matches_original():
    """互換シム経由の出力が従来実装と完全一致すること。"""
    # このテストは移行前の出力をスナップショットとして保存し比較する
    from piper_train.phonemize.japanese import phonemize_japanese
    tokens = phonemize_japanese("テスト文です。")
    # スナップショットとの比較 (具体的な期待値は実装時に確定)
    assert isinstance(tokens, list)
    assert len(tokens) > 0

def test_existing_tests_pass():
    """既存の tests/ ディレクトリのテストが全て pass すること。"""
    # uv run pytest tests/ で確認 (CI で実行)
    pass
```

### E2E テスト

```bash
# 既存テストスイートの全パス
cd src/python && uv run pytest tests/ -v

# 学習パイプラインの smoke test
uv run python -m piper_train.preprocess --help
# -> エラーなく help が表示されること

# 推論スクリプトの smoke test
uv run python -m piper_train.infer_onnx --help
# -> エラーなく help が表示されること
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **循環 import**: `piper_train.phonemize` が `piper_g2p` を import し、`piper_g2p` が (間接的に) `piper_train` を import する循環が発生しないよう注意。`piper_g2p` は `piper_train` に依存しない一方向の依存にする。
- **pyopenjtalk の import パス**: `piper_g2p.japanese` と `piper_train.phonemize.japanese` の両方が `pyopenjtalk` を import する場合、モジュールレベルの副作用 (辞書ロード等) が二重に発生しないか確認。
- **`CustomDictionary` の扱い**: Phase 0 では `piper_g2p` に `CustomDictionary` は含まれない。互換シムで `phonemize_japanese(text, custom_dict=...)` を呼ばれた場合、従来の `CustomDictionary` コードパスにフォールバックする必要がある。
- **パフォーマンスオーバーヘッド**: 互換シムは piper_g2p を呼び出した後に BOS/EOS/PUA 変換を追加するため、直接呼び出しより若干遅い。ただし G2P 処理自体のコスト (pyopenjtalk の fullcontext 解析) が支配的なので、シムのオーバーヘッドは無視可能。

### レビュー項目
- `from piper_train.phonemize.japanese import phonemize_japanese` の戻り値が移行前と完全一致すること
- `from piper_train.phonemize.token_mapper import FIXED_PUA_MAPPING` が同一オブジェクトを返すこと
- 既存テストが 1 件も失敗しないこと
- `piper_g2p` -> `piper_train` の方向に import が存在しないこと

---

## 6. 一から作り直すとしたら

- **互換シムを作らず、piper_train を直接 piper_g2p に依存させる**: `piper_train` の `pyproject.toml` に `piper-g2p` を依存追加し、各ファイルの import を `piper_g2p` に書き換える方式。クリーンだが、一度に全ファイルを変更する必要があり、レビュー/テストの負荷が高い。互換シムは段階的移行を可能にするため、Phase 0 では安全な選択。
- **互換シムを独立パッケージにする**: `piper-g2p-compat` のようなブリッジパッケージとして切り出し、`piper_train` の依存に追加する方式。過度なパッケージ分割なので不採用。
- **`DeprecationWarning` を Phase 0 から出す**: 互換シム経由の呼び出しに `DeprecationWarning` を出して移行を促進する案。ただし既存ユーザの学習パイプラインで warning ノイズが大量に出るため、Phase 0 では見送り。Phase 1 で検討。

---

## 7. 後続タスクへの連絡事項

- **P0-008 (テスト)**: 互換シムのテストとして、既存テスト (`tests/`) の全パスを CI で検証すること。追加で互換シム固有のテスト (import パス、出力形式) を 4+ ケース追加。
- **P0-009 (CI)**: CI ワークフローで `piper_g2p` と `piper_train` の両方をインストールした状態でテストを実行する必要がある。`uv pip install ./src/python/g2p[ja,en] && uv pip install -e ./src/python/piper_train` の順序でインストール。
- **Phase 1**: 互換シムに `DeprecationWarning` を追加し、`piper_g2p` への直接移行を推奨するメッセージを表示する。移行ガイドドキュメントも作成する。
- **Phase 1 以降**: `MultilingualPhonemizer`, `BilingualPhonemizer`, `CustomDictionary` の互換シムも必要になる。Phase 0 ではこれらは既存コードをそのまま維持する。
