# [P0-003] コア抽象 (Phonemizer ABC + ProsodyInfo + Registry)

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-001, FR-002
> 依存チケット: P0-002
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
`piper-g2p` のコア抽象を定義する。全言語 Phonemizer の基底クラス (ABC)、韻律情報の型 (`ProsodyInfo`)、言語レジストリを提供する。この 3 つが後続の言語別 Phonemizer (P0-004, P0-005) とエンコーダ (P0-006) の土台となる。

### ゴール
- `from piper_g2p import Phonemizer, ProsodyInfo` でインポートできる
- `Phonemizer` は `phonemize()` と `phonemize_with_prosody()` の 2 メソッドのみを `@abstractmethod` として持つ
- `get_phoneme_id_map()` および `post_process_ids()` は ABC に含まれない
- `ProsodyInfo` は `a1: int, a2: int, a3: int` を持つ dataclass
- `get_phonemizer("ja")` が pyopenjtalk インストール時に `JapanesePhonemizer` を返す
- 依存未インストールの言語はレジストリ自動登録時にスキップされ、`ImportError` にならない
- `register_language("custom", my_phonemizer)` でユーザ定義 Phonemizer を登録できる
- `available_languages()` がインストール済み言語のリストを返す

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/base.py` | Phonemizer ABC + ProsodyInfo |
| `src/python/g2p/piper_g2p/registry.py` | レジストリ (get_phonemizer, register_language, available_languages) |
| `src/python/g2p/piper_g2p/__init__.py` | re-export 更新 (P0-002 で作成済み) |

### 実装手順

1. **`base.py` の実装**

   現在の `src/python/piper_train/phonemize/base.py` から `get_phoneme_id_map()` と `post_process_ids()` を除去した純粋な ABC を作成する。

   ```python
   # piper_g2p/base.py
   from abc import ABC, abstractmethod
   from dataclasses import dataclass

   @dataclass
   class ProsodyInfo:
       """韻律情報。言語によって a1/a2/a3 の意味が異なる。

       日本語:
           a1: アクセント核からの相対位置
           a2: アクセント句内のモーラ位置 (1-based)
           a3: アクセント句内の総モーラ数
       英語:
           a1: 0 (未使用)
           a2: ストレスレベル (0=なし, 1=secondary, 2=primary)
           a3: 単語内の音素数
       """
       a1: int
       a2: int
       a3: int

   class Phonemizer(ABC):
       """G2P 抽象基底クラス。

       phonemize() は IPA トークン列を返す。
       BOS/EOS/パディング/PUA エンコードは含めない。
       """

       @abstractmethod
       def phonemize(self, text: str) -> list[str]:
           """テキストを IPA トークン列に変換する。"""

       @abstractmethod
       def phonemize_with_prosody(
           self, text: str
       ) -> tuple[list[str], list[ProsodyInfo | None]]:
           """テキストを IPA トークン列 + 韻律情報に変換する。"""
   ```

2. **`registry.py` の実装**

   現在の `src/python/piper_train/phonemize/registry.py` から MultilingualPhonemizer/BilingualPhonemizer 自動生成ロジックを除去し、シンプルなレジストリのみ実装する。

   ```python
   # piper_g2p/registry.py
   import logging
   from .base import Phonemizer

   _REGISTRY: dict[str, Phonemizer] = {}
   _LOGGER = logging.getLogger(__name__)

   def register_language(code: str, phonemizer: Phonemizer) -> None:
       _REGISTRY[code] = phonemizer

   def get_phonemizer(language: str) -> Phonemizer:
       if language in _REGISTRY:
           return _REGISTRY[language]
       raise ValueError(
           f"Unsupported language: {language}. "
           f"Available: {list(_REGISTRY.keys())}"
       )

   def available_languages() -> list[str]:
       return list(_REGISTRY.keys())

   def _auto_register() -> None:
       try:
           from .japanese import JapanesePhonemizer
           register_language("ja", JapanesePhonemizer())
       except ImportError:
           pass
       try:
           from .english import EnglishPhonemizer
           register_language("en", EnglishPhonemizer())
       except ImportError:
           pass

   _auto_register()
   ```

3. **`__init__.py` の更新**: P0-002 で作成済みの re-export が正しく機能することを確認。

### API / インターフェース

```python
from piper_g2p import Phonemizer, ProsodyInfo
from piper_g2p import get_phonemizer, register_language, available_languages

# サードパーティによるカスタム Phonemizer 登録
class MyPhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]:
        return list(text)
    def phonemize_with_prosody(self, text):
        tokens = list(text)
        return tokens, [None] * len(tokens)

register_language("custom", MyPhonemizer())
ph = get_phonemizer("custom")
ph.phonemize("test")  # -> ["t", "e", "s", "t"]
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| コア実装 | 1 | base.py + registry.py の実装 |
| テスト | 1 | ABC のサブクラス化テスト、レジストリのエッジケーステスト |

---

## 4. テスト計画

### 提供範囲
Phonemizer ABC、ProsodyInfo、レジストリの基本動作。

### Unit テスト

```python
# test_base.py

def test_prosody_info_creation():
    p = ProsodyInfo(a1=-2, a2=3, a3=5)
    assert p.a1 == -2
    assert p.a2 == 3
    assert p.a3 == 5

def test_phonemizer_is_abstract():
    """Phonemizer を直接インスタンス化できないこと。"""
    with pytest.raises(TypeError):
        Phonemizer()

def test_phonemizer_subclass():
    """phonemize() と phonemize_with_prosody() を実装すればインスタンス化できること。"""
    class DummyPhonemizer(Phonemizer):
        def phonemize(self, text):
            return list(text)
        def phonemize_with_prosody(self, text):
            return list(text), [None] * len(text)
    ph = DummyPhonemizer()
    assert ph.phonemize("ab") == ["a", "b"]

def test_phonemizer_missing_method():
    """phonemize_with_prosody() を実装しないとエラーになること。"""
    class IncompletePhonemizer(Phonemizer):
        def phonemize(self, text):
            return list(text)
    with pytest.raises(TypeError):
        IncompletePhonemizer()
```

```python
# test_registry.py

def test_register_and_get():
    register_language("test", DummyPhonemizer())
    ph = get_phonemizer("test")
    assert ph.phonemize("x") == ["x"]

def test_get_unknown_raises():
    with pytest.raises(ValueError, match="Unsupported language"):
        get_phonemizer("nonexistent")

def test_available_languages_includes_registered():
    register_language("test2", DummyPhonemizer())
    assert "test2" in available_languages()

def test_auto_register_skips_missing_deps():
    """pyopenjtalk が未インストールでも ImportError にならないこと。"""
    # registry.py のモジュールインポートが成功すること自体がテスト
    from piper_g2p import registry  # noqa: F401
```

### E2E テスト
なし (P0-004/P0-005 で言語別の E2E テストを実施)。

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **`_auto_register()` のタイミング**: `registry.py` のモジュールレベルで呼ばれるため、`import piper_g2p` の時点で pyopenjtalk / g2p-en の import を試みる。大量の言語が追加された場合、初回 import のオーバーヘッドが増加する。ただし Phase 0 は 2 言語のみなので問題ない。
- **レジストリのスレッドセーフティ**: グローバル `_REGISTRY` dict は threading 非対応。Phase 0 では問題にならないが、Phase 1 で検討が必要。

### レビュー項目
- ABC に `get_phoneme_id_map()` や `post_process_ids()` が混入していないこと (責務分離)
- `ProsodyInfo` の docstring に日本語/英語それぞれの a1/a2/a3 の意味が記載されていること
- `get_phonemizer()` のエラーメッセージに利用可能な言語リストが含まれていること

---

## 6. 一から作り直すとしたら

- **Protocol ベース (structural subtyping)**: ABC (nominal subtyping) の代わりに `typing.Protocol` を使えば、サードパーティが `Phonemizer` を継承しなくても duck typing で使える。ただし `isinstance()` チェックが必要な場面 (レジストリのバリデーション等) では ABC のほうが安全。Phase 0 は ABC を採用し、Protocol は Phase 1 で `@runtime_checkable` と併用する案を検討する。
- **レジストリを class ベースにする**: 現在のモジュールレベル dict ではなく `LanguageRegistry` クラスにすると、テスト時にインスタンスを切り替えやすい。ただし API の簡潔さ (`get_phonemizer("ja")`) を優先し、モジュールレベル関数を採用する。
- **遅延登録 (entry_points)**: `pyproject.toml` の `[project.entry-points."piper_g2p.languages"]` を使い、言語 Phonemizer をプラグインとして自動発見する仕組み。Phase 1 以降の拡張性に有用だが、Phase 0 では overengineering。

---

## 7. 後続タスクへの連絡事項

- **P0-004, P0-005**: `Phonemizer` ABC を継承して `JapanesePhonemizer`, `EnglishPhonemizer` を実装すること。`get_phoneme_id_map()` は実装不要 (ABC に含まれない)。
- **P0-006**: `ProsodyInfo` 型は `piper_g2p.base` から import すること。encode モジュールは Phonemizer ABC に依存しない (IPA トークン列を受け取るだけ)。
- **P0-007**: 互換シムは `piper_g2p.Phonemizer` を継承する形ではなく、ラッパーとして実装すること (既存の `piper_train.phonemize.base.Phonemizer` とは別の ABC)。
- **Phase 1**: 複合言語コード (`"ja-en"`) による MultilingualPhonemizer 自動生成はこのチケットの registry には含まれていない。Phase 1 で追加すること。
