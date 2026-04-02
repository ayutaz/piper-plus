# M0-2: JapanesePhonemizer に `custom_dict` パラメータ追加

> **マイルストーン**: M0
> **前提チケット**: なし
> **後続チケット**: M1-4 (preprocess.py リファクタリング)
> **見積り**: 小
> **リスク**: 低

## タスク目的とゴール

`piper_train` の `preprocess.py:733` は `phonemize_japanese_with_prosody(text, custom_dict=custom_dict)` を呼び出すが、`piper_g2p` の `JapanesePhonemizer` には `custom_dict` パラメータが存在しない。
`piper_g2p/custom_dict.py` に `CustomDictionary` クラスは既に実装済みだが、`JapanesePhonemizer.phonemize()` / `phonemize_with_prosody()` に統合されていない。

**ゴール**: `JapanesePhonemizer` の `phonemize()` と `phonemize_with_prosody()` が `custom_dict` を受け取り、音素化前にカスタム辞書によるテキスト置換を適用する。preprocess.py から `piper_g2p` への移行時にカスタム辞書機能が失われないようにする。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/python/g2p/piper_g2p/japanese.py:207-233`

#### 1. `JapanesePhonemizer` にコンストラクタを追加

> **注意**: 現在の `JapanesePhonemizer` にはコンストラクタ (`__init__`) が存在しない。
> `Phonemizer` ABC にも `__init__` は定義されていないため、新規にコンストラクタを追加する必要がある。
> `super().__init__()` の呼び出しは不要 (ABC 側にコンストラクタがないため)。

```python
class JapanesePhonemizer(Phonemizer):
    def __init__(self, custom_dict: "CustomDictionary | None" = None):
        self._custom_dict = custom_dict
```

#### 2. `phonemize()` に `custom_dict` 適用を追加 (L220-225)

```python
def phonemize(self, text: str) -> list[str]:
    text = self._sanitize_input(text)
    if not text:
        return []
    if self._custom_dict is not None:
        text = self._custom_dict.apply_to_text(text)
    tokens, _prosody = _phonemize_core(text)
    return tokens
```

#### 3. `phonemize_with_prosody()` に同様の追加 (L227-233)

```python
def phonemize_with_prosody(
    self, text: str
) -> tuple[list[str], list[ProsodyInfo | None]]:
    text = self._sanitize_input(text)
    if not text:
        return [], []
    if self._custom_dict is not None:
        text = self._custom_dict.apply_to_text(text)
    return _phonemize_core(text)
```

#### 4. import 追加

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piper_g2p.custom_dict import CustomDictionary
```

`TYPE_CHECKING` ガードにより、実行時の循環 import を回避する。

### 変更しない箇所

- `Phonemizer` ABC (`base.py`) のシグネチャは変更しない。`custom_dict` は `JapanesePhonemizer` 固有のコンストラクタ引数とする
- 他の言語の Phonemizer は変更しない
- `CustomDictionary` クラス自体は変更しない

### 確認事項

- `CustomDictionary.apply_to_text(text)` メソッドが存在し、テキスト置換を行うことを確認する (`src/python/g2p/piper_g2p/custom_dict.py`)
- 実際のメソッド名は `apply_to_text()` である (`apply()` ではない)

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|---|---|---|
| 実装者 | 1 | JapanesePhonemizer の修正 (~10行) + テスト作成 |
| レビュアー | 1 | ABC との整合性確認、テスト結果確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/g2p/piper_g2p/japanese.py` の `JapanesePhonemizer` クラス修正 (~10行追加)
- ユニットテスト追加
- 既存テストの通過確認 (`custom_dict=None` がデフォルトなので後方互換性あり)

### テスト項目

1. `custom_dict=None` (デフォルト) で既存動作が変わらないことを確認
2. `custom_dict` を渡した場合、テキスト置換が音素化前に適用されることを確認
3. `phonemize()` と `phonemize_with_prosody()` の両方で `custom_dict` が機能することを確認

### Unit テスト

`src/python/g2p/tests/test_japanese.py` に追加:

```python
class TestJapanesePhonemizer CustomDict:
    @requires_ja
    def test_phonemize_without_custom_dict(self):
        """custom_dict=None でデフォルト動作と同一"""
        p = JapanesePhonemizer()
        tokens = p.phonemize("こんにちは")
        assert len(tokens) > 0

    @requires_ja
    def test_phonemize_with_custom_dict(self):
        """custom_dict で 'API' -> 'エーピーアイ' を置換後に音素化"""
        from piper_g2p.custom_dict import CustomDictionary
        d = CustomDictionary(load_defaults=False)
        d.add_entry("API", "エーピーアイ")
        p = JapanesePhonemizer(custom_dict=d)
        tokens = p.phonemize("APIを使う")
        # 'エーピーアイ' の音素が含まれることを確認
        assert any("e" in t for t in tokens)  # 'エ' -> 'e'

    @requires_ja
    def test_phonemize_with_prosody_custom_dict(self):
        """phonemize_with_prosody でも custom_dict が適用される"""
        from piper_g2p.custom_dict import CustomDictionary
        d = CustomDictionary(load_defaults=False)
        d.add_entry("API", "エーピーアイ")
        p = JapanesePhonemizer(custom_dict=d)
        tokens, prosody = p.phonemize_with_prosody("APIを使う")
        assert len(tokens) > 0
        assert len(tokens) == len(prosody)
```

### E2E テスト

```python
@requires_ja
def test_custom_dict_full_pipeline(self):
    """custom_dict -> phonemize -> encode -> phoneme_ids の全パイプライン"""
    from piper_g2p.custom_dict import CustomDictionary
    from piper_g2p.encode import PiperEncoder, get_phoneme_id_map

    d = CustomDictionary(load_defaults=False)
    d.add_entry("API", "エーピーアイ")
    p = JapanesePhonemizer(custom_dict=d)
    tokens = p.phonemize("APIを使う")
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    ids = encoder.encode(tokens)
    assert len(ids) > 0
    assert ids[0] == id_map["^"][0]  # BOS
    assert ids[-1] == id_map["$"][0]  # EOS
```

## 懸念事項とレビュー項目

### 懸念事項

- **ABC シグネチャとの不整合**: `Phonemizer` ABC の `phonemize()` / `phonemize_with_prosody()` のシグネチャを変更しない設計としたが、将来的に他の言語でもカスタム辞書が必要になった場合、各言語で個別実装する必要がある。ABC に `custom_dict` を追加するかは設計判断
- **`CustomDictionary` のメソッド名**: 実際のメソッド名は `apply_to_text()` である (`apply()` ではない)。このチケットのコード例は全て `apply_to_text()` を使用している
- **置換順序**: カスタム辞書の置換は `_sanitize_input()` の後、`_phonemize_core()` の前に行う。サニタイズで制御文字が除去された後のテキストに対して辞書置換を適用する

### レビュー項目

- [ ] `custom_dict=None` がデフォルトで後方互換性があること
- [ ] `TYPE_CHECKING` ガードにより実行時 import が発生しないこと
- [ ] `phonemize()` と `phonemize_with_prosody()` の両方で辞書が適用されること
- [ ] `CustomDictionary.apply_to_text()` メソッドが使用されていること
- [ ] 既存テスト全件パス

## 一から作り直すとしたら

`Phonemizer` ABC のコンストラクタに `custom_dict: CustomDictionary | None = None` を含め、`_sanitize_input()` の直後に自動適用する `_apply_custom_dict(text)` メソッドを ABC に実装する。各言語 Phonemizer はコンストラクタで `super().__init__(custom_dict=custom_dict)` を呼ぶだけで済む設計。

## 後続タスクへの連絡事項

- M1-4 (preprocess.py リファクタリング) は `JapanesePhonemizer(custom_dict=custom_dict)` でインスタンスを生成し、`p.phonemize_with_prosody(text)` を呼ぶ形式に移行する
- `CustomDictionary.apply_to_text()` を使用していることをチケット完了時に確認すること
- コンストラクタ引数方式を採用したことを記載し、メソッド引数方式を選ばなかった理由を記録すること
