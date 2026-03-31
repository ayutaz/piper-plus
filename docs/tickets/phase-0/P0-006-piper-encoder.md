# [P0-006] PiperEncoder (encode モジュール)

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-005
> 依存チケット: P0-003
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
IPA トークン列を Piper TTS の `phoneme_ids` に変換するエンコーダを `piper_g2p.encode` モジュールとして提供する。現在 `token_mapper.py`, `*_id_map.py`, `Phonemizer.post_process_ids()` に分散しているエンコーディングロジックを `PiperEncoder` クラスに統合する。

### ゴール
- `from piper_g2p.encode import PiperEncoder` でインポートできる
- `PiperEncoder(phoneme_id_map)` でインスタンス化できる
- `encoder.encode(tokens)` が `list[int]` (phoneme_ids) を返す
- `encoder.encode_with_prosody(tokens, prosody_list)` が `(list[int], list[dict | None])` を返す
- PUA マッピング (87 エントリ) が組み込みテーブルとして利用可能
- `get_phoneme_id_map("ja")`, `get_phoneme_id_map("en")` で言語別 ID マップを取得できる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/encode/__init__.py` | PiperEncoder, FIXED_PUA_MAPPING, get_phoneme_id_map の re-export |
| `src/python/g2p/piper_g2p/encode/encoder.py` | PiperEncoder クラス |
| `src/python/g2p/piper_g2p/encode/pua.py` | FIXED_PUA_MAPPING (87 エントリ), TOKEN2CHAR, CHAR2TOKEN |
| `src/python/g2p/piper_g2p/encode/id_maps.py` | get_phoneme_id_map(), JA/EN の ID マップ定義 |

### 実装手順

1. **`pua.py` の作成**

   ソース: `src/python/piper_train/phonemize/token_mapper.py` の `FIXED_PUA_MAPPING` をそのまま移植。動的割り当て (`register()`) も移植する。

   ```python
   # piper_g2p/encode/pua.py
   FIXED_PUA_MAPPING: dict[str, int] = {
       "a:": 0xE000,
       "i:": 0xE001,
       # ... (87 エントリ全て)
       "ɔ̃": 0xE058,
   }

   TOKEN2CHAR: dict[str, str] = {}
   CHAR2TOKEN: dict[str, str] = {}

   for token, codepoint in FIXED_PUA_MAPPING.items():
       ch = chr(codepoint)
       TOKEN2CHAR[token] = ch
       CHAR2TOKEN[ch] = token

   def map_token(token: str) -> str:
       """多文字トークンを PUA 1 文字にマッピングする。"""
       if token in TOKEN2CHAR:
           return TOKEN2CHAR[token]
       if len(token) == 1:
           return token
       # 動的割り当て
       # ...
   ```

2. **`id_maps.py` の作成**

   ソース: `src/python/piper_train/phonemize/jp_id_map.py` (JA) とconfig.json ベースの EN マップ。

   ```python
   # piper_g2p/encode/id_maps.py
   from .pua import map_token

   def get_phoneme_id_map(language: str) -> dict[str, list[int]]:
       """言語別の phoneme_id_map を返す。"""
       if language == "ja":
           return _get_japanese_id_map()
       elif language == "en":
           return _get_english_id_map()
       raise ValueError(f"No ID map for language: {language}")
   ```

3. **`encoder.py` の作成**

   現在の `Phonemizer.post_process_ids()` ロジックを移植・統合する。

   ```python
   # piper_g2p/encode/encoder.py
   from __future__ import annotations
   from .pua import FIXED_PUA_MAPPING, map_token

   class PiperEncoder:
       def __init__(
           self,
           phoneme_id_map: dict[str, list[int]],
           pua_table: dict[str, int] | None = None,
       ):
           self._id_map = phoneme_id_map
           self._pua = pua_table or FIXED_PUA_MAPPING

       def encode(
           self,
           tokens: list[str],
           eos_token: str = "$",
       ) -> list[int]:
           """IPA トークン列 -> phoneme_ids 変換。

           1. 多文字トークン -> PUA 1 文字
           2. PUA/IPA 文字 -> phoneme_id_map で ID 変換
           3. BOS/EOS/inter-phoneme パディング挿入
           """
           ids = self._tokens_to_ids(tokens)
           ids = self._add_padding_and_boundaries(ids, eos_token)
           return ids

       def encode_with_prosody(
           self,
           tokens: list[str],
           prosody_list: list[ProsodyInfo | None],
           eos_token: str = "$",
       ) -> tuple[list[int], list[dict | None]]:
           """IPA トークン列 + 韻律情報 -> (phoneme_ids, prosody_features) 変換。"""
           # ...

       def _tokens_to_ids(self, tokens: list[str]) -> list[int]:
           """各トークンを PUA 変換 -> ID 変換。"""
           ids = []
           for token in tokens:
               mapped = map_token(token)
               if mapped in self._id_map:
                   ids.extend(self._id_map[mapped])
               else:
                   # 1 文字ずつフォールバック
                   for ch in mapped:
                       if ch in self._id_map:
                           ids.extend(self._id_map[ch])
           return ids

       def _add_padding_and_boundaries(
           self, phoneme_ids: list[int], eos_token: str
       ) -> list[int]:
           """BOS/EOS/パディング挿入。post_process_ids() 相当。"""
           # ...
   ```

### API / インターフェース

```python
from piper_g2p import get_phonemizer
from piper_g2p.encode import PiperEncoder, get_phoneme_id_map, FIXED_PUA_MAPPING

# 日本語の phonemize -> encode
ja = get_phonemizer("ja")
tokens = ja.phonemize("こんにちは")
# -> ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]

id_map = get_phoneme_id_map("ja")
encoder = PiperEncoder(id_map)
phoneme_ids = encoder.encode(tokens)
# -> [1, 0, 26, 0, 36, 0, 85, 0, 30, 0, 43, 0, 21, 0, 30, 0, 24, 0, 10, 0, 2]
#    ^  _  k   _  o   _  N_n _  n   _  i   _  ch  _  i   _  h   _  a   _  $

# prosody 付きエンコード
tokens, prosody = ja.phonemize_with_prosody("こんにちは")
ids, prosody_features = encoder.encode_with_prosody(tokens, prosody)

# 疑問文の EOS トークン指定
tokens = ja.phonemize("何？")
# -> ["n", "a", "N_uvular", "i", "?"]
phoneme_ids = encoder.encode(tokens, eos_token="?")

# PUA テーブルへのアクセス
print(len(FIXED_PUA_MAPPING))  # 87
print(FIXED_PUA_MAPPING["ch"])  # 0xE00E
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| エンコーダ実装 | 1 | encoder.py, pua.py, id_maps.py の実装 |
| テスト | 1 | PUA 変換、BOS/EOS 挿入、パディング、ID 変換のテスト |

---

## 4. テスト計画

### 提供範囲
PiperEncoder の `encode()` と `encode_with_prosody()`、PUA マッピング、ID マップ。

### Unit テスト (8+ ケース)

```python
# test_encode.py

# --- PUA 変換 ---

def test_pua_mapping_count():
    """固定 PUA マッピングが 87 エントリであること。"""
    from piper_g2p.encode import FIXED_PUA_MAPPING
    assert len(FIXED_PUA_MAPPING) == 87  # 仕様通り

def test_pua_single_char_passthrough():
    """1 文字トークンはそのままパススルーされること。"""
    from piper_g2p.encode.pua import map_token
    assert map_token("k") == "k"
    assert map_token("a") == "a"

def test_pua_multi_char_mapping():
    """多文字トークンが PUA 1 文字に変換されること。"""
    from piper_g2p.encode.pua import map_token
    mapped = map_token("ch")
    assert len(mapped) == 1
    assert ord(mapped) == 0xE00E

# --- BOS/EOS 挿入 ---

def test_bos_eos_insertion():
    """エンコード結果に BOS と EOS が含まれること。"""
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    ids = encoder.encode(["k", "a"])
    # BOS (^) の ID が先頭に、EOS ($) の ID が末尾にあること
    bos_id = id_map["^"][0] if "^" in id_map else None
    eos_id = id_map["$"][0] if "$" in id_map else None
    if bos_id is not None:
        assert ids[0] == bos_id
    if eos_id is not None:
        assert ids[-1] == eos_id

def test_custom_eos_token():
    """eos_token パラメータで EOS トークンを変更できること。"""
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    # "?" トークンが id_map に存在する場合
    ids_q = encoder.encode(["k", "a"], eos_token="?")
    ids_default = encoder.encode(["k", "a"])
    assert ids_q[-1] != ids_default[-1]  # EOS が異なる

# --- パディング ---

def test_inter_phoneme_padding():
    """音素間にパディング (ID=0) が挿入されること。"""
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    ids = encoder.encode(["k", "a"])
    # k と a の間に pad (ID=0) があること
    assert 0 in ids

# --- ID マップ変換 ---

def test_japanese_id_map():
    """日本語 ID マップが正しいフォーマットであること。"""
    id_map = get_phoneme_id_map("ja")
    assert isinstance(id_map, dict)
    assert "_" in id_map  # パディングトークン
    assert "^" in id_map  # BOS
    assert "$" in id_map  # EOS

def test_english_id_map():
    """英語 ID マップが正しいフォーマットであること。"""
    id_map = get_phoneme_id_map("en")
    assert isinstance(id_map, dict)

# --- prosody 付きエンコード ---

def test_encode_with_prosody():
    """encode_with_prosody() が ids と prosody_features を返すこと。"""
    from piper_g2p import ProsodyInfo
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    tokens = ["k", "a"]
    prosody = [ProsodyInfo(a1=-1, a2=1, a3=2), ProsodyInfo(a1=-1, a2=1, a3=2)]
    ids, features = encoder.encode_with_prosody(tokens, prosody)
    assert len(ids) == len(features)
    # パディング位置は None
    pad_positions = [i for i, f in enumerate(features) if f is None]
    assert len(pad_positions) > 0
```

### E2E テスト

```python
def test_ja_full_pipeline():
    """日本語: テキスト -> phonemize -> encode の一気通貫テスト。"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("テスト")
    id_map = get_phoneme_id_map("ja")
    encoder = PiperEncoder(id_map)
    ids = encoder.encode(tokens)
    assert isinstance(ids, list)
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) > len(tokens)  # BOS/EOS/パディングにより長くなる

def test_en_full_pipeline():
    """英語: テキスト -> phonemize -> encode の一気通貫テスト。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("Hello")
    id_map = get_phoneme_id_map("en")
    encoder = PiperEncoder(id_map)
    ids = encoder.encode(tokens)
    assert isinstance(ids, list)
    assert all(isinstance(i, int) for i in ids)
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **ID マップの互換性**: `get_phoneme_id_map("ja")` が返す ID マップは、現在の `jp_id_map.get_japanese_id_map()` と数値的に一致する必要がある。既に学習済みモデルがこの ID マッピングに依存しているため、変更は不可。
- **動的 PUA 割り当て**: `token_mapper.py` には固定マッピング外のトークンに動的に PUA コードポイントを割り当てる `register()` がある。この動的割り当ては実行ごとに結果が変わる可能性があるため、encode モジュールでの扱いを明確にする必要がある。固定マッピング (87 エントリ) のみを使い、未知トークンは warning + 文字単位フォールバックとするのが安全。
- **EN の ID マップ**: 英語は config.json 由来の ID マップを使用しているため、`get_phoneme_id_map("en")` の実装はどのように ID マップを定義するか要検討。bilingual/multilingual の config.json からの抽出が必要か、独立した定義を作るか。

### レビュー項目
- `FIXED_PUA_MAPPING` が `piper_train` 版の `token_mapper.py` と完全に一致すること (87 エントリ全て)
- `encode()` の出力が `post_process_ids()` の出力と数値的に一致すること
- BOS/EOS/パディングの挿入順序が正しいこと
- `encode_with_prosody()` の prosody_features のパディング位置が正しいこと

---

## 6. 一から作り直すとしたら

- **PUA 変換をなくす**: PUA マッピングは Piper TTS の config.json が「1 文字 = 1 phoneme ID」前提で設計されているための workaround。ID マップを `dict[str, list[int]]` (キーが多文字文字列) に拡張すれば PUA 変換は不要になる。ただし既存モデルとの互換性を維持するため、Phase 0 では PUA 変換を維持する。
- **Encoder を stateless 関数にする**: `PiperEncoder` クラスではなく `encode(tokens, id_map)` 関数にするとシンプルだが、pua_table のカスタマイズや将来の設定拡張 (padding strategy 等) を考慮するとクラスが適切。
- **ID マップをファイルから読む**: `get_phoneme_id_map("ja")` がハードコードされた ID マップを返すのではなく、`piper_g2p/data/ja_id_map.json` のようなデータファイルから読む方式。拡張性は高いがパッケージサイズが増加する。

---

## 7. 後続タスクへの連絡事項

- **P0-007 (互換シム)**: 互換シムは `PiperEncoder.encode()` を内部で使用して、現在の `Phonemizer.post_process_ids()` の出力を再現する。`encode()` の出力が `post_process_ids()` と数値的に一致することを E2E テストで検証すること。
- **P0-008 (テスト)**: `encode()` の出力を現行実装 (`phonemize_japanese()` + `post_process_ids()`) と比較するリグレッションテストを追加すること。
- **Phase 1**: 残り 5 言語 (ZH, KO, ES, PT, FR) の ID マップを `id_maps.py` に追加する。`get_phoneme_id_map()` の対応言語が拡張される。
- **Phase 1**: `MultilingualPhonemizer` が使用する多言語統合 ID マップ (`multilingual_id_map.py` 相当) も `id_maps.py` に追加する。
