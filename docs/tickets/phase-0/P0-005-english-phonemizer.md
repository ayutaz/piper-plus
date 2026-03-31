# [P0-005] EnglishPhonemizer (IPA 出力)

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: FR-004
> 依存チケット: P0-003
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
g2p-en ベースの英語 G2P を `piper_g2p.EnglishPhonemizer` として提供する。現在の `piper_train.phonemize.english` は既に IPA トークン列を返しているため、移植は最小限の変更で済む。

### ゴール
- `get_phonemizer("en").phonemize("Hello world")` が IPA トークン列を返す
- ストレスマーカー (`"ˈ"`, `"ˌ"`) が IPA 規約通りに含まれる
- 機能語 (97 語) のストレス除去が適用される
- `phonemize_with_prosody()` が `ProsodyInfo(a1=0, a2=stress_level, a3=word_phoneme_count)` を返す
- `g2p-en` 未インストール時は `import piper_g2p` が成功し、`get_phonemizer("en")` で `ValueError` になる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/english.py` | EnglishPhonemizer 実装 |

### 実装手順

1. **現在の実装を移植**

   ソース: `src/python/piper_train/phonemize/english.py`

   現在の EnglishPhonemizer は既に IPA トークン列を返しており、BOS/EOS/PUA 変換は含まれていない。主な変更点:
   - import パスの変更 (`piper_train.phonemize.base` -> `piper_g2p.base`)
   - `get_phoneme_id_map()` メソッドの削除 (新 ABC に含まれないため)
   - モジュールレベル関数 (`phonemize_english()`, `phonemize_english_with_prosody()`) は内部実装として保持

2. **移植するコンポーネント** (変更なし)
   - `ARPABET_TO_IPA` マッピング (39 エントリ)
   - `_FUNCTION_WORDS` セット (97 語)
   - `_g2p_en_to_arpabet_tokens()`: g2p-en のワード分割
   - `_arpabet_to_ipa()`: ARPAbet -> IPA 変換
   - `_convert_word_to_ipa()`: コンテキスト依存ルール (AA+R -> ɑːɹ, stressed ER -> ɜː)
   - `phonemize_english_with_prosody()`: ストレスマーカー挿入、機能語ストレス除去

3. **クラス定義**

   ```python
   class EnglishPhonemizer(Phonemizer):
       """English phonemizer using g2p-en."""

       def phonemize(self, text: str) -> list[str]:
           tokens, _ = phonemize_english_with_prosody(text)
           return tokens

       def phonemize_with_prosody(
           self, text: str
       ) -> tuple[list[str], list[ProsodyInfo | None]]:
           return phonemize_english_with_prosody(text)
   ```

### API / インターフェース

```python
from piper_g2p import get_phonemizer

en = get_phonemizer("en")

# 基本的な音素化
tokens = en.phonemize("Hello world")
# -> ["h", "ʌ", "ˈ", "l", "oʊ", " ", "ˈ", "w", "ɜː", "l", "d"]

# ストレスマーカー
tokens = en.phonemize("record")  # 名詞
# -> ["ˈ", "ɹ", "ɛ", "k", "ɚ", "d"] (primary stress on first syllable)

# 機能語ストレス除去
tokens = en.phonemize("I am happy")
# -> "I" と "am" のストレスが除去される
# 結果: ["ˈ", "aɪ", " ", "æ", "m", " ", "ˈ", "h", "æ", "p", "iː"]
# ("I" は function word だが g2p-en が1音節のためストレス位置は変化しない場合がある)

# 韻律情報付き
tokens, prosody = en.phonemize_with_prosody("Hello world")
# prosody: [ProsodyInfo(a1=0, a2=0, a3=5), ..., ProsodyInfo(a1=0, a2=2, a3=5), ...]
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| G2P 実装 | 1 | english.py の移植 |
| テスト | 1 | IPA 出力の検証、ストレスマーカー、機能語テスト |

---

## 4. テスト計画

### 提供範囲
EnglishPhonemizer の `phonemize()` と `phonemize_with_prosody()` の全機能。

### Unit テスト (6+ ケース)

```python
# test_english.py

# --- 基本音素化 ---

def test_basic_phonemize():
    en = get_phonemizer("en")
    tokens = en.phonemize("Hello")
    assert "h" in tokens
    assert "ˈ" in tokens  # ストレスマーカーあり
    assert "^" not in tokens  # BOS なし
    assert "$" not in tokens  # EOS なし

def test_word_boundary():
    """単語間にスペーストークンが入ること。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("Hello world")
    assert " " in tokens

# --- ストレスマーカー ---

def test_primary_stress():
    """primary stress (ˈ) が母音の前に挿入されること。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("happy")
    assert "ˈ" in tokens
    idx = tokens.index("ˈ")
    # ˈ の次は母音
    assert tokens[idx + 1] in {"h", "æ", "ɛ", "ɑ", "ʌ", "ɪ", "iː", "uː", "oʊ", "aɪ", "aʊ", "eɪ", "ɔɪ", "ɔː", "ɚ", "ɜː"}

def test_secondary_stress():
    """secondary stress (ˌ) が存在する単語で挿入されること。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("multiplication")
    assert "ˌ" in tokens

# --- 機能語ストレス除去 ---

def test_function_word_stress_removed():
    """機能語 (the, a, is 等) のストレスが除去されること。"""
    en = get_phonemizer("en")
    # "the" は機能語なので stress=0 になるはず
    tokens_full = en.phonemize("the cat")
    tokens_prosody, prosody = en.phonemize_with_prosody("the cat")
    # "the" 部分の prosody は a2=0 (ストレスなし) であること
    # 最初のトークンが "the" の一部
    assert prosody[0].a2 == 0  # ストレスなし

def test_content_word_stress_preserved():
    """内容語のストレスが保持されること。"""
    en = get_phonemizer("en")
    tokens, prosody = en.phonemize_with_prosody("happy")
    # "happy" にはストレスありの音素が存在するはず
    stressed = [p for p in prosody if p is not None and p.a2 == 2]
    assert len(stressed) > 0

# --- prosody 情報 ---

def test_prosody_length_matches():
    """tokens と prosody の長さが一致すること。"""
    en = get_phonemizer("en")
    tokens, prosody = en.phonemize_with_prosody("Hello world")
    assert len(tokens) == len(prosody)

def test_prosody_a1_always_zero():
    """英語の a1 は常に 0 であること。"""
    en = get_phonemizer("en")
    _, prosody = en.phonemize_with_prosody("This is a test sentence.")
    for p in prosody:
        if p is not None:
            assert p.a1 == 0
```

### E2E テスト

```python
def test_roundtrip_en():
    """phonemize -> encode -> phoneme_ids の一気通貫テスト (P0-006 完了後に実施)。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("Test")
    assert isinstance(tokens, list)
    assert all(isinstance(t, str) for t in tokens)
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **g2p-en のバージョン互換性**: `g2p-en>=2.1.0` を要求するが、2.1 以降でトークン出力フォーマットが変わる可能性がある。CI で最新版と最小版の両方をテストすべき。
- **g2p-en の初回ロード時間**: `G2p()` のインスタンス化に 100-500ms かかる。`_g2p_instance` のモジュールレベルキャッシュで対応済みだが、マルチプロセス環境では注意が必要。
- **ARPAbet -> IPA マッピングの網羅性**: 39 エントリのマッピングテーブルが全ての g2p-en 出力をカバーしているか。不明なシンボルは warning ログ + as-is パススルーで対応済み。

### レビュー項目
- `ARPABET_TO_IPA` マッピングが `piper_train` 版と完全に一致すること
- `_FUNCTION_WORDS` セット (97 語) が `piper_train` 版と完全に一致すること
- `_convert_word_to_ipa()` のコンテキスト依存ルール (AA+R, stressed ER) が `piper_train` 版と一致すること
- `get_phoneme_id_map()` メソッドが削除されていること

---

## 6. 一から作り直すとしたら

- **g2p-en 以外の英語 G2P バックエンド対応**: `EnglishPhonemizer(backend="g2p-en")` のようにバックエンド切り替え可能にすると、将来的に espeak-ng-free な別実装 (例: Misaki の EN 部分) に差し替えやすい。ただし Phase 0 では g2p-en 一択なので overengineering。
- **ARPAbet 中間表現の公開**: `phonemize_arpabet(text) -> list[str]` を公開 API として提供すると、IPA ではなく ARPAbet が必要なユーザ (CMU dict 互換 TTS) にも対応できる。Phase 0 では IPA-first 方針を優先。
- **ストレスマーカー位置の制御**: IPA 規約ではストレスマーカーは音節の前 (not 母音の前) に置くが、espeak-ng 互換のため母音の直前に配置している。`stress_position="syllable_onset"` オプションで切り替え可能にする案。

---

## 7. 後続タスクへの連絡事項

- **P0-006 (PiperEncoder)**: EnglishPhonemizer の出力には多文字トークン (`"oʊ"`, `"ɑːɹ"`, `"tʃ"`, `"dʒ"` 等) が含まれるが、これらの多くは 1 IPA 文字に分解されてトークン列に入るため、PUA 変換は不要。ただし `"oʊ"` 等が 1 トークンとして出力される場合、PiperEncoder が正しく処理する必要がある。
- **P0-007 (互換シム)**: 現在の `EnglishPhonemizer` は既に IPA を返しているため、互換シムの変換処理は最小限。ただし `get_phoneme_id_map()` メソッドの互換が必要。
- **P0-008 (テスト)**: テストで使用する英語テキストは g2p-en のバージョンによって出力が微妙に異なる場合がある。テストケースは安定した一般的な単語 (Hello, world, happy 等) を使用すること。
