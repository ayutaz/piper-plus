# [P0-004] JapanesePhonemizer (IPA 出力)

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-003
> 依存チケット: P0-003
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
OpenJTalk ベースの日本語 G2P を `piper_g2p.JapanesePhonemizer` として提供する。現在の `piper_train.phonemize.japanese` の音素化ロジックを移植し、IPA-first 方針に従って BOS/EOS/PUA 変換を行わないクリーンな IPA トークン列を返す。

### ゴール
- `get_phonemizer("ja").phonemize("こんにちは")` が IPA トークン列 `["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]` を返す
- BOS (`"^"`)、EOS (`"$"`)、PUA 文字を含まない
- 韻律記号 (`"#"`, `"["`, `"]"`) は含む
- 疑問詞マーカー (`"?"`, `"?!"`, `"?."`, `"?~"`) は含む
- 文脈依存 N 音素変異 (`N_m`, `N_n`, `N_ng`, `N_uvular`) が適用される
- `phonemize_with_prosody()` が `(tokens, prosody_list)` を返す
- `pyopenjtalk` / `pyopenjtalk-plus` 未インストール時は `import piper_g2p` が成功し、`get_phonemizer("ja")` で `ValueError` になる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/japanese.py` | JapanesePhonemizer 実装 |

### 実装手順

1. **現在の実装を元にリファクタリング**

   ソース: `src/python/piper_train/phonemize/japanese.py`

   主な変更点:
   - `map_sequence()` (PUA 変換) の呼び出しを削除
   - BOS (`"^"`) / EOS (`"$"`, `"?"` 等) の挿入を削除
   - `_` (short pause) は IPA の pause marker としてそのまま保持
   - `CustomDictionary` 対応は Phase 0 では含めない (Phase 1)
   - `_apply_n_phoneme_rules()` はそのまま移植
   - `_get_question_type()` はそのまま移植 (疑問詞マーカー出力用)

2. **`phonemize()` の実装**

   ```python
   def phonemize(self, text: str) -> list[str]:
       labels = pyopenjtalk.extract_fullcontext(text)
       tokens: list[str] = []

       for idx, label in enumerate(labels):
           m_ph = _RE_PHONEME.search(label)
           if not m_ph:
               continue
           phoneme = m_ph.group(1)

           # sil はスキップ (BOS/EOS を出力しない)
           if phoneme == "sil":
               # 末尾 sil の場合、疑問詞マーカーを付与
               if idx == len(labels) - 1:
                   q_type = _get_question_type(text)
                   if q_type != "$":  # 疑問文のみマーカーを出力
                       tokens.append(q_type)
               continue

           if phoneme == "pau":
               tokens.append("_")
               continue

           tokens.append(phoneme)

           # 韻律記号の挿入 (], #, [)
           # ... (現行実装と同一ロジック)

       tokens = _apply_n_phoneme_rules(tokens)
       return tokens
   ```

3. **`phonemize_with_prosody()` の実装**

   現在の `phonemize_japanese_with_prosody()` をベースに、同様に BOS/EOS/PUA 変換を除去。`ProsodyInfo(a1, a2, a3)` を各トークンに対応付ける。

4. **pyopenjtalk import フォールバック**

   ```python
   try:
       import pyopenjtalk_plus as pyopenjtalk
   except ImportError:
       try:
           import pyopenjtalk
       except ImportError:
           raise ImportError(
               "Japanese G2P requires pyopenjtalk-plus or pyopenjtalk. "
               "Install with: pip install piper-g2p[ja]"
           ) from None
   ```

### API / インターフェース

```python
from piper_g2p import get_phonemizer

ja = get_phonemizer("ja")

# 基本的な音素化
tokens = ja.phonemize("こんにちは")
# -> ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]

# 韻律情報付き
tokens, prosody = ja.phonemize_with_prosody("こんにちは")
# tokens: ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
# prosody: [ProsodyInfo(a1=-3, a2=1, a3=5), ProsodyInfo(a1=-3, a2=1, a3=5), ...]

# 韻律記号を含む例
tokens = ja.phonemize("今日は良い天気ですね。")
# -> ["ky", "o", "]", ":", "w", "a", "#", "[", "i", "]", "i", "#", ...]
# (# = アクセント句境界, [ = 上昇, ] = 下降)

# 疑問文
tokens = ja.phonemize("お元気ですか？")
# -> ["o", "g", "e", "N_ng", "k", "i", "d", "e", "s", "U", "k", "a", "?"]

# N 音素変異
tokens = ja.phonemize("新聞")
# -> ["sh", "i", "N_m", "b", "u", "N_uvular"]
# N_m: 「ん」の後に b (両唇音) が続く
# N_uvular: 語末の「ん」
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| G2P 実装 | 1 | japanese.py のリファクタリングと移植 |
| テスト | 1 | 音素化の入出力検証、N 変異・疑問詞マーカーのテスト |

---

## 4. テスト計画

### 提供範囲
JapanesePhonemizer の `phonemize()` と `phonemize_with_prosody()` の全機能。

### Unit テスト (10+ ケース)

```python
# test_japanese.py

# --- 基本音素化 ---

def test_basic_phonemize():
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("こんにちは")
    assert "k" in tokens
    assert "o" in tokens
    assert "ch" in tokens
    assert "^" not in tokens  # BOS なし
    assert "$" not in tokens  # EOS なし

def test_no_pua_characters():
    """PUA 文字 (U+E000-U+F8FF) が含まれないこと。"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("テスト文です。")
    for token in tokens:
        for ch in token:
            assert not (0xE000 <= ord(ch) <= 0xF8FF), f"PUA character found: {token}"

# --- N 音素変異 (4 パターン) ---

def test_n_before_bilabial():
    """N + m/b/p -> N_m"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("新聞")  # しんぶん
    assert "N_m" in tokens  # ん + ぶ

def test_n_before_alveolar():
    """N + n/t/d/ts/ch -> N_n"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("こんにちは")  # ん + に
    assert "N_n" in tokens

def test_n_before_velar():
    """N + k/g -> N_ng"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("漢字")  # ん + じ... ※ 適切な例を選択
    # 「ん」の後に k/g が続く例
    tokens2 = ja.phonemize("文化")  # ぶんか
    assert "N_ng" in tokens2

def test_n_at_end():
    """語末の N -> N_uvular"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("本")  # ほん
    assert "N_uvular" in tokens

# --- 疑問詞マーカー (4 パターン) ---

def test_question_generic():
    tokens = get_phonemizer("ja").phonemize("何？")
    assert "?" in tokens

def test_question_emphatic():
    tokens = get_phonemizer("ja").phonemize("何？！")
    assert "?!" in tokens

def test_question_neutral():
    tokens = get_phonemizer("ja").phonemize("何。？")
    assert "?." in tokens

def test_question_tag():
    tokens = get_phonemizer("ja").phonemize("何～？")
    assert "?~" in tokens

# --- 韻律記号 ---

def test_prosody_symbols_present():
    """韻律記号 (#, [, ]) がトークンに含まれること。"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("今日は良い天気ですね。")
    prosody_symbols = {"#", "[", "]"}
    found = {t for t in tokens if t in prosody_symbols}
    assert len(found) > 0, "韻律記号が見つからない"

# --- prosody 情報 ---

def test_phonemize_with_prosody():
    ja = get_phonemizer("ja")
    tokens, prosody = ja.phonemize_with_prosody("こんにちは")
    assert len(tokens) == len(prosody)
    # 音素トークンには ProsodyInfo が付与される
    non_none = [p for p in prosody if p is not None]
    assert len(non_none) > 0
```

### E2E テスト

```python
def test_roundtrip_ja():
    """phonemize -> encode -> phoneme_ids の一気通貫テスト (P0-006 完了後に実施)。"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("テスト")
    assert isinstance(tokens, list)
    assert all(isinstance(t, str) for t in tokens)
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **宣言文の BOS/EOS 除去後の互換性**: 現在の `phonemize_japanese()` は BOS (`"^"`) で始まり EOS (`"$"` or `"?"`) で終わる。新 API では両方とも出力しないため、P0-007 互換シムで正しく補完される必要がある。
- **pause トークン `"_"` の扱い**: IPA 規約では pause に標準記法がない。`"_"` を独自記法として維持するか、IPA の pause 記号 (`|` or `‖`) に変えるか。piper-g2p ユーザの多くが Piper TTS と組み合わせることを考慮し、`"_"` を維持する。
- **`CustomDictionary` の除外**: Phase 0 では custom dict 非対応。Phase 1 で追加するが、API 変更 (引数追加) が必要になる。

### レビュー項目
- `phonemize()` の戻り値に PUA 文字が含まれていないこと
- `phonemize()` の戻り値に `"^"`, `"$"` が含まれていないこと
- N 音素変異の分類ロジックが `piper_train` 版と一致すること
- 疑問詞マーカーの判定ロジックが `piper_train` 版と一致すること
- `pyopenjtalk` import フォールバックが正しく機能すること

---

## 6. 一から作り直すとしたら

- **OpenJTalk の fullcontext ラベルパーサーを独立モジュール化**: 正規表現ベースのラベル解析 (`_RE_PHONEME`, `_RE_A1`, `_RE_A2`, `_RE_A3`) を `jtalk_label_parser.py` に分離すると、テスタビリティが向上する。現在は `phonemize_japanese()` 内に inline で使用しているため、ラベル解析のみの単体テストが書きにくい。
- **N 音素変異をルールテーブル化**: 現在の if/elif チェーンではなく、`dict[frozenset[str], str]` のルールテーブルにすると、ルール追加・変更が容易になる。ただし 4 パターンのみなので、現行の明示的な分岐のほうが可読性が高い。
- **疑問詞マーカーを phonemize() の引数で制御**: `phonemize("何？", question_markers=True)` のように、疑問詞マーカーの出力をオプショナルにすると、Piper 以外の TTS で不要な場合に柔軟に対応できる。

---

## 7. 後続タスクへの連絡事項

- **P0-006 (PiperEncoder)**: JapanesePhonemizer が返す多文字トークン (`"ch"`, `"sh"`, `"N_m"` 等) は PiperEncoder が PUA マッピングで 1 文字に変換する責務を持つ。JapanesePhonemizer 側では変換しない。
- **P0-007 (互換シム)**: 互換シムは `JapanesePhonemizer.phonemize()` の出力に BOS/EOS を追加し、`map_sequence()` (PUA 変換) を適用して、現在の `phonemize_japanese()` と同じ出力を再現する必要がある。
- **Phase 1**: `CustomDictionary` サポートは Phase 1 で `phonemize(text, custom_dict=...)` 引数として追加する。Phase 0 の API との後方互換性を維持すること (キーワード引数のみ追加)。
