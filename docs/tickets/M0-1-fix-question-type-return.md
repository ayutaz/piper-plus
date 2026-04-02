# M0-1: `_get_question_type()` 非疑問文の戻り値を `"$"` に修正

> **マイルストーン**: M0
> **前提チケット**: なし
> **後続チケット**: M1-4 (preprocess.py リファクタリング)
> **見積り**: 小
> **リスク**: 中

## タスク目的とゴール

`piper_g2p` の `_get_question_type()` が非疑問文に対して空文字列 `""` を返す。
一方 `piper_train` 側では非疑問文の EOS マーカーとして `"$"` を返す。
この不一致により、`MultilingualPhonemizer` が EOS トークンを正しく追跡できない。

**ゴール**: `_get_question_type()` が非疑問文に対して `"$"` を返すようにする。
piper_train と piper_g2p の EOS 動作が完全に一致し、`MultilingualPhonemizer` の
EOS 追跡が正常に機能する状態。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/python/g2p/piper_g2p/japanese.py:77`

```python
# 変更前 (L77)
return ""  # Not a question

# 変更後
return "$"  # Not a question — declarative EOS
```

1行変更のみ。ただし以下を確認すること:

- `_get_question_type()` の呼び出し元を全て検索し、空文字列に依存するロジックがないか確認する
- `piper_g2p/japanese.py` 内の `_phonemize_core()` で `_get_question_type()` の戻り値がどのように使われるか確認する
- `_SKIP_TOKENS` (L81) には既に `"$"` が含まれているため、N phoneme ルール等への影響はない

### 影響確認

`_get_question_type()` の呼び出し箇所 (`src/python/g2p/piper_g2p/japanese.py` 内):

- `_phonemize_core()` 内で呼ばれ、戻り値が空文字列でない場合にトークンリストに追加される
- 空文字列 `""` を返す場合、EOS マーカーが追加されない動作になっている
- `"$"` を返す場合でも、EOS の付与はエンコーダ (`PiperEncoder`) の責務であるため、Phonemizer レベルでは `"$"` がトークンリストの末尾に追加されるかどうかを確認する必要がある

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|---|---|---|
| 実装者 | 1 | 1行修正 + 呼び出し元の影響調査 |
| レビュアー | 1 | piper_train との一貫性検証、テスト結果確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/g2p/piper_g2p/japanese.py` の `_get_question_type()` 修正 (1行)
- ユニットテスト追加
- 既存テストの通過確認

### テスト項目

1. 非疑問文が `"$"` を返すことを確認
2. 疑問文 5 バリアント全ての戻り値が正しいことを確認
3. `MultilingualPhonemizer` で JA 非疑問文テキストを処理し、EOS が `"$"` であることを確認

### Unit テスト

`src/python/g2p/tests/test_japanese.py` に追加 (または新規テストファイル):

```python
class TestGetQuestionType:
    def test_declarative_returns_dollar(self):
        """非疑問文は '$' を返す"""
        assert _get_question_type("今日は良い天気です。") == "$"

    def test_question_returns_question_mark(self):
        """通常疑問文は '?' を返す"""
        assert _get_question_type("元気ですか？") == "?"

    def test_exclamatory_question(self):
        """強調疑問文は '?!' を返す"""
        assert _get_question_type("本当ですか？！") == "?!"

    def test_declarative_question(self):
        """平叙疑問文は '?.' を返す"""
        assert _get_question_type("これでいいの？。") == "?."

    def test_confirmation_question(self):
        """確認疑問文は '?~' を返す"""
        assert _get_question_type("そうですか？〜") == "?~"
```

### E2E テスト

`src/python/g2p/tests/test_compat.py` に追加:

```python
def test_ja_declarative_eos_is_dollar(self):
    """MultilingualPhonemizer で JA 非疑問文を処理し、
    EOS トークンが '$' であることを確認"""
    # piper_g2p の JapanesePhonemizer で非疑問文を処理
    # tokens の末尾が "$" であることを検証
    # piper_train の phonemize_japanese() と一致することを検証
```

#### `_phonemize_core()` 経由の統合テスト

`src/python/g2p/tests/test_japanese.py` に追加:

```python
class TestPhonemizeCoreEosIntegration:
    @requires_ja
    def test_declarative_eos_via_phonemize_with_prosody(self):
        """非疑問文 → phonemize_with_prosody() → トークン列末尾が '$'"""
        p = JapanesePhonemizer()
        tokens, _prosody = p.phonemize_with_prosody("今日は良い天気です。")
        assert len(tokens) > 0
        assert tokens[-1] == "$", f"Expected '$' but got '{tokens[-1]}'"

    @requires_ja
    def test_question_eos_via_phonemize_with_prosody(self):
        """疑問文 → phonemize_with_prosody() → トークン列末尾が '?'"""
        p = JapanesePhonemizer()
        tokens, _prosody = p.phonemize_with_prosody("元気ですか？")
        assert len(tokens) > 0
        assert tokens[-1] == "?", f"Expected '?' but got '{tokens[-1]}'"

    @requires_ja
    def test_exclamatory_question_eos_via_phonemize_with_prosody(self):
        """強調疑問文 → phonemize_with_prosody() → トークン列末尾が '?!'"""
        p = JapanesePhonemizer()
        tokens, _prosody = p.phonemize_with_prosody("本当ですか？！")
        assert len(tokens) > 0
        assert tokens[-1] == "?!", f"Expected '?!' but got '{tokens[-1]}'"

    @requires_ja
    def test_declarative_eos_via_phonemize(self):
        """非疑問文 → phonemize() → トークン列末尾が '$'"""
        p = JapanesePhonemizer()
        tokens = p.phonemize("今日は良い天気です。")
        assert len(tokens) > 0
        assert tokens[-1] == "$", f"Expected '$' but got '{tokens[-1]}'"
```

## 懸念事項とレビュー項目

### 懸念事項

- **空文字列への依存**: `_get_question_type()` の戻り値が空文字列であることに依存するコードが存在する可能性がある。`_phonemize_core()` 内で `if question_type:` のような真偽値チェックをしている場合、`"$"` は truthy なのでトークンリストに `"$"` が追加される。これが意図通りかを確認する必要がある
- **二重 EOS 問題**: `PiperEncoder` が BOS/EOS を付与する設計であるため、Phonemizer が `"$"` を返し、かつ `PiperEncoder` も `"$"` を追加すると二重 EOS になる可能性がある。`PiperEncoder.encode_with_prosody()` の挙動を確認すること

### レビュー項目

- [ ] `_get_question_type()` の全呼び出し箇所で空文字列依存がないこと
- [ ] `_phonemize_core()` 内の分岐で `"$"` が正しく処理されること
- [ ] `PiperEncoder` との組み合わせで二重 EOS にならないこと
- [ ] piper_train の `phonemize_japanese()` と同一の出力になること
- [ ] 既存テスト全件パス

## 一から作り直すとしたら

`_get_question_type()` の戻り値を最初から `Optional[str]` ではなく、常に EOS マーカー文字列を返す設計にしていれば、空文字列問題は起きなかった。Phonemizer ABC に `get_eos_marker(text) -> str` メソッドを定義し、各言語で実装させる設計が理想的だった。

## 後続タスクへの連絡事項

- M1-4 (preprocess.py リファクタリング) は、この修正により `_get_question_type()` が常に有効な EOS マーカーを返すことを前提とする
- テスト結果 (特に二重 EOS の有無) をチケット完了時に記載すること
- `piper_train` 側の `_get_question_type()` と `piper_g2p` 側の出力が完全一致することの確認結果を記載すること
