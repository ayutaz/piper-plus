# スウェーデン語対応 詳細要件定義書 (FR-04 / FR-05 / FR-06)

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| 対象要件 | FR-04 (音素インベントリ), FR-05 (Phonemizer ABC 準拠), FR-06 (マルチリンガル統合) |
| 親文書 | `swedish-requirements.md` (要求定義書) |
| 設計文書 | `swedish-g2p-design.md` (設計書 S10, S11) |
| ブランチ | `feature/swedish-language-support` |
| Issue | #296 |

---

## 1. FR-04: 音素インベントリ

### 1.1 概要

スウェーデン語の音素体系を `sv_id_map.py` として定義し、多文字トークンに対する PUA (Private Use Area) コードポイント割り当てを `token_mapper.py` に追加する。既存 6 言語 (JA/EN/ZH/KO/ES/FR/PT) との音素共有・重複排除を正しく行い、学習済みモデルとの後方互換性を維持する。

### 1.2 新規ファイル: `sv_id_map.py`

**ファイルパス**: `src/python/piper_train/phonemize/sv_id_map.py`

#### 1.2.1 `SWEDISH_PHONEMES` リスト仕様

`SWEDISH_PHONEMES` は、スウェーデン語の音素化出力に現れうる全音素を定義する。他言語の `*_id_map.py` と同様に、JA/EN 等の既存インベントリと共有される音素も含む (重複排除は `multilingual_id_map.py` の `get_multilingual_id_map()` が `seen` セットで自動処理する)。

```python
"""Swedish phoneme inventory for Piper TTS.

Phonemes shared with existing inventories (JA/EN/ZH/ES/FR/PT) are
listed here for completeness.  Deduplication is handled by
multilingual_id_map.py which assigns a single ID to each unique
symbol across all languages.
"""

from .token_mapper import register


__all__ = ["SWEDISH_PHONEMES"]

# -----------------------------------------------------------------------
# Swedish phoneme inventory (Central Standard Swedish / Rikssvenska)
# -----------------------------------------------------------------------
# Shared with existing inventories (deduplicated by multilingual_id_map):
#   a, e, i, o, u         -- vowels (JA)
#   b, d, f, h, k, l, m,  -- consonants (JA/EN)
#   n, p, s, t, v, j, r, w
#   ɡ (U+0261)            -- voiced velar plosive (EN)
#   ŋ (U+014B)            -- velar nasal (EN)
#   ɪ (U+026A)            -- near-close near-front unrounded (EN)
#   ʊ (U+028A)            -- near-close near-back rounded (EN)
#   ɛ (U+025B)            -- open-mid front unrounded (EN)
#   ɔ (U+0254)            -- open-mid back rounded (EN/FR)
#   ʃ (U+0283)            -- voiceless postalveolar fricative (EN)
#   ʂ (U+0282)            -- voiceless retroflex fricative (ZH)
#   ɕ (U+0255)            -- voiceless alveolo-palatal fricative (ZH)
#   ː (U+02D0)            -- length marker (EN)
#   ˈ (U+02C8)            -- primary stress (EN)
#   ˌ (U+02CC)            -- secondary stress (EN)
#   " " (U+0020)          -- word boundary (EN)
#   , . ; : !              -- punctuation (EN)
#
# Swedish-UNIQUE phonemes that need new IDs:
SWEDISH_PHONEMES: list[str] = [
    # === 単一コードポイント音素 (PUA 不要) ===
    # レトロフレックス子音
    "ɖ",       # U+0256 -- retroflex voiced plosive (rd → ɖ)
    "ʈ",       # U+0288 -- retroflex voiceless plosive (rt → ʈ)
    "ɳ",       # U+0273 -- retroflex nasal (rn → ɳ)
    "ɭ",       # U+026D -- retroflex lateral approximant (rl → ɭ)
    # スウェーデン語固有摩擦音
    "ɧ",       # U+0267 -- sj-sound (voiceless dorso-palatal/velar fricative)
    # 母音 (短母音)
    "ɵ",       # U+0275 -- close-mid central rounded (短い u: hund)
    "ʏ",       # U+028F -- near-close near-front rounded (短い y: full)
    "œ",       # U+0153 -- open-mid front rounded (短い ö: öst)
    "ɑ",       # U+0251 -- open back unrounded (短い a: already in EN but listed for coverage)
    "ø",       # U+00F8 -- close-mid front rounded (already in FR but listed for coverage)
    # === 多文字トークン (PUA 割り当て必要) ===
    # 長母音 (9 音素)
    "iː",      # 長い前舌非円唇 (vit)
    "yː",      # 長い前舌円唇 (ful)
    "eː",      # 長い半閉前舌 (vet)
    "ɛː",      # 長い半開前舌 (säl)
    "øː",      # 長い半閉前舌円唇 (öl)
    "ɑː",      # 長い開後舌 (glas)
    "oː",      # 長い半閉後舌 (åt)
    "uː",      # 長い閉後舌 (bok)
    "ʉː",      # 長い閉中舌円唇 (hus)
]

# Register multi-character tokens to get PUA codepoints
for _token in SWEDISH_PHONEMES:
    register(_token)
```

#### 1.2.2 音素分類表

| # | 音素 | Unicode | 文字数 | PUA 必要 | カテゴリ | 説明 | 共有言語 |
|---|------|---------|--------|----------|---------|------|---------|
| 1 | ɖ | U+0256 | 1 | 不要 | レトロフレックス子音 | 有声レトロフレックス破裂音 | SV 固有 |
| 2 | ʈ | U+0288 | 1 | 不要 | レトロフレックス子音 | 無声レトロフレックス破裂音 | SV 固有 |
| 3 | ɳ | U+0273 | 1 | 不要 | レトロフレックス子音 | レトロフレックス鼻音 | SV 固有 |
| 4 | ɭ | U+026D | 1 | 不要 | レトロフレックス子音 | レトロフレックス側面音 | SV 固有 |
| 5 | ɧ | U+0267 | 1 | 不要 | 摩擦音 | sj-sound (SV 固有) | SV 固有 |
| 6 | ɵ | U+0275 | 1 | 不要 | 短母音 | 閉中舌円唇 (短い u) | SV 固有 |
| 7 | ʏ | U+028F | 1 | 不要 | 短母音 | 近閉前舌円唇 (短い y) | SV 固有 |
| 8 | œ | U+0153 | 1 | 不要 | 短母音 | 半開前舌円唇 (短い ö) | FR と共有 |
| 9 | ɑ | U+0251 | 1 | 不要 | 短母音 | 開後舌非円唇 (短い a) | EN と共有 |
| 10 | ø | U+00F8 | 1 | 不要 | 短母音 | 半閉前舌円唇 | FR と共有 |
| 11 | iː | U+0069 U+02D0 | 2 | **必要** | 長母音 | 閉前舌非円唇 (長) | SV 固有 |
| 12 | yː | U+0079 U+02D0 | 2 | **必要** | 長母音 | 閉前舌円唇 (長) | SV 固有 |
| 13 | eː | U+0065 U+02D0 | 2 | **必要** | 長母音 | 半閉前舌非円唇 (長) | SV 固有 |
| 14 | ɛː | U+025B U+02D0 | 2 | **必要** | 長母音 | 半開前舌非円唇 (長) | SV 固有 |
| 15 | øː | U+00F8 U+02D0 | 2 | **必要** | 長母音 | 半閉前舌円唇 (長) | SV 固有 |
| 16 | ɑː | U+0251 U+02D0 | 2 | **必要** | 長母音 | 開後舌非円唇 (長) | SV 固有 |
| 17 | oː | U+006F U+02D0 | 2 | **必要** | 長母音 | 半閉後舌円唇 (長) | SV 固有 |
| 18 | uː | U+0075 U+02D0 | 2 | **必要** | 長母音 | 閉後舌円唇 (長) | SV 固有 |
| 19 | ʉː | U+0289 U+02D0 | 2 | **必要** | 長母音 | 閉中舌円唇 (長) | SV 固有 |

**注意**: 英語の長母音 (例: `ɔː`, `ɜː`) は `ɔ` + `ː` の 2 トークンとして表現される (EN は長さマーカー `ː` を独立トークンとして使用)。スウェーデン語では長母音を 1 トークンとして扱う (例: `ɑː` は PUA 1 文字に置換)。この差異は設計判断であり、SV の母音長の対立が音韻的に重要であるため、長母音を独立トークンとして学習させる。

#### 1.2.3 設計判断: 長母音のトークン化方式

| 方式 | 説明 | 利点 | 欠点 |
|------|------|------|------|
| **A. 1 トークン (PUA)** | `ɑː` → PUA 1 文字 | 長短対立を 1 トークンで明示。Duration Predictor が学習しやすい | PUA 9 個消費 |
| B. 2 トークン | `ɑ` + `ː` | PUA 不要。EN と一貫性あり | DP が長さマーカーを無視するリスク |

**採用**: 方式 A。スウェーデン語の Complementary Quantity (母音長と子音長の補完的関係) は音韻的に重要であり、1 トークンとしてモデルに入力することで DP の学習負荷を軽減する。ES/FR/PT の規則ベース言語は長母音を持たないため、SV 固有の設計として許容される。

### 1.3 PUA コードポイント割り当て

#### 1.3.1 既存 PUA 割り当て状況 (衝突回避確認)

現在の `token_mapper.py` の `FIXED_PUA_MAPPING` の使用状況:

| 範囲 | 用途 | 最終使用 |
|------|------|---------|
| 0xE000 - 0xE015 | JA (長母音, 促音, 拗音, 撥音バリアント等) | 0xE015 (ry) |
| 0xE016 - 0xE018 | JA (疑問詞マーカー ?!, ?., ?~) | 0xE018 |
| 0xE019 - 0xE01C | JA (N バリアント N_m, N_n, N_ng, N_uvular) | 0xE01C |
| 0xE01D - 0xE01E | 多言語共有 (rr, y_vowel) | 0xE01E |
| 0xE01F | 未使用 (reserved gap) | -- |
| 0xE020 - 0xE04A | ZH (声母, 韻母, 声調) | 0xE04A (tone5) |
| 0xE04B - 0xE052 | KO (硬音, 内破音) | 0xE052 (p̚) |
| 0xE053 | 未使用 (reserved gap) | -- |
| 0xE054 - 0xE055 | ES/PT (tʃ, dʒ) | 0xE055 |
| 0xE056 - 0xE058 | FR (鼻母音 ɛ̃, ɑ̃, ɔ̃) | 0xE058 |
| **0xE059 以降** | **動的割り当て領域 (`_PUA_START`)** | -- |

**現在の `_PUA_START`**: `0xE059`

#### 1.3.2 新規 PUA 割り当て (SV)

| トークン | PUA コードポイント | 16 進 | 説明 |
|---------|-------------------|-------|------|
| `iː` | 0xE059 | `\uE059` | SV 長母音: 閉前舌非円唇 |
| `yː` | 0xE05A | `\uE05A` | SV 長母音: 閉前舌円唇 |
| `eː` | 0xE05B | `\uE05B` | SV 長母音: 半閉前舌 |
| `ɛː` | 0xE05C | `\uE05C` | SV 長母音: 半開前舌 |
| `øː` | 0xE05D | `\uE05D` | SV 長母音: 半閉前舌円唇 |
| `ɑː` | 0xE05E | `\uE05E` | SV 長母音: 開後舌 |
| `oː` | 0xE05F | `\uE05F` | SV 長母音: 半閉後舌 |
| `uː` | 0xE060 | `\uE060` | SV 長母音: 閉後舌 |
| `ʉː` | 0xE061 | `\uE061` | SV 長母音: 閉中舌円唇 |

**予備枠**:

| 予備 | PUA コードポイント | 説明 |
|------|-------------------|------|
| (reserved) | 0xE062 | SV 将来拡張用 (例: ʊː) |
| (reserved) | 0xE063 | SV 将来拡張用 (例: œː) |

**更新後の `_PUA_START`**: `0xE064`

#### 1.3.3 衝突検証

以下の条件を全て満たすことを検証する:

1. **固定 PUA 範囲内で重複がないこと**: 0xE059-0xE061 は全て新規割り当てであり、既存の `FIXED_PUA_MAPPING` の全キーと値が異なることを確認。
2. **予備枠 (0xE062-0xE063) は `FIXED_PUA_MAPPING` に追加しないこと**: 動的割り当てで使用される可能性があるため、予約のみ。
3. **動的割り当て開始位置 `_PUA_START = 0xE064`**: 予備枠の次から開始。
4. **Unicode PUA 上限 (0xF8FF) まで十分な余裕**: 0xE064 から 0xF8FF まで 3,739 個利用可能。

### 1.4 `token_mapper.py` 変更仕様

**ファイルパス**: `src/python/piper_train/phonemize/token_mapper.py`

#### 1.4.1 変更箇所 1: `FIXED_PUA_MAPPING` への追加

**変更位置**: `FIXED_PUA_MAPPING` 辞書の末尾 (FR セクションの後)

**変更前** (138 行目付近):
```python
    "\u0254\u0303": 0xE058,  # ɔ̃  nasal open-mid back rounded (bon, nom)
}
```

**変更後**:
```python
    "\u0254\u0303": 0xE058,  # ɔ̃  nasal open-mid back rounded (bon, nom)
    # =======================================================================
    # Swedish (SV)
    # =======================================================================
    # --- Long vowels ---
    "i\u02D0": 0xE059,  # iː  close front unrounded long (vit, bil)
    "y\u02D0": 0xE05A,  # yː  close front rounded long (ful, hus→archaic)
    "e\u02D0": 0xE05B,  # eː  close-mid front unrounded long (vet, se)
    "\u025B\u02D0": 0xE05C,  # ɛː  open-mid front unrounded long (säl, bär)
    "\u00F8\u02D0": 0xE05D,  # øː  close-mid front rounded long (öl, dör)
    "\u0251\u02D0": 0xE05E,  # ɑː  open back unrounded long (glas, mat)
    "o\u02D0": 0xE05F,  # oː  close-mid back rounded long (åt, stor)
    "u\u02D0": 0xE060,  # uː  close back rounded long (bok, sol)
    "\u0289\u02D0": 0xE061,  # ʉː  close central rounded long (hus, ljus)
    # 0xE062-0xE063 reserved for SV future expansion
}
```

**コードポイント表記の根拠**:

| トークン文字列 | Unicode エスケープ | 根拠 |
|--------------|-------------------|------|
| `iː` | `"i\u02D0"` | `i` (U+0069) + `ː` (U+02D0) |
| `yː` | `"y\u02D0"` | `y` (U+0079) + `ː` (U+02D0) |
| `eː` | `"e\u02D0"` | `e` (U+0065) + `ː` (U+02D0) |
| `ɛː` | `"\u025B\u02D0"` | `ɛ` (U+025B) + `ː` (U+02D0) |
| `øː` | `"\u00F8\u02D0"` | `ø` (U+00F8) + `ː` (U+02D0) |
| `ɑː` | `"\u0251\u02D0"` | `ɑ` (U+0251) + `ː` (U+02D0) |
| `oː` | `"o\u02D0"` | `o` (U+006F) + `ː` (U+02D0) |
| `uː` | `"u\u02D0"` | `u` (U+0075) + `ː` (U+02D0) |
| `ʉː` | `"\u0289\u02D0"` | `ʉ` (U+0289) + `ː` (U+02D0) |

#### 1.4.2 変更箇所 2: `_PUA_START` 更新

**変更位置**: 151-152 行目

**変更前**:
```python
# Private Use Area for dynamic allocation (starting after the last FIXED codepoint)
# 0xE058 is the last used fixed codepoint (FR ɔ̃), so dynamic starts at 0xE059.
_PUA_START = 0xE059
```

**変更後**:
```python
# Private Use Area for dynamic allocation (starting after the last FIXED codepoint)
# 0xE061 is the last used fixed codepoint (SV ʉː), so dynamic starts at 0xE064.
# 0xE062-0xE063 are reserved for SV future expansion.
_PUA_START = 0xE064
```

#### 1.4.3 後方互換性

| 観点 | 影響 | 対策 |
|------|------|------|
| 既存学習済みモデル (6lang) | 影響なし | 既存の固定 PUA (0xE000-0xE058) は変更しない |
| 動的割り当て済みトークン | **影響あり** | 動的割り当ては学習時に毎回実行されるため、`_PUA_START` 変更は新規学習にのみ影響。既存モデルの `config.json` に保存された `phoneme_id_map` はそのまま有効 |
| C++/Rust/C# 実装 | Phase 2 で対応 | 新規 PUA 定数を C++/Rust/C# に追加する必要がある (Phase 2 スコープ) |

**重要**: `FIXED_PUA_MAPPING` に追加した 9 エントリのコードポイントは、一度学習に使用されたら**変更禁止**。ファイル先頭のコメント「Do NOT change assigned codepoints -- they are baked into trained models.」に準拠。

### 1.5 テストケース (FR-04)

```python
# test/test_sv_id_map.py

import pytest
from piper_train.phonemize.sv_id_map import SWEDISH_PHONEMES
from piper_train.phonemize.token_mapper import (
    FIXED_PUA_MAPPING,
    TOKEN2CHAR,
    CHAR2TOKEN,
    register,
    _PUA_START,
)


class TestSwedishPhonemes:
    """FR-04: 音素インベントリの検証。"""

    def test_swedish_phonemes_not_empty(self):
        """SWEDISH_PHONEMES リストが空でないこと。"""
        assert len(SWEDISH_PHONEMES) > 0

    def test_swedish_phonemes_count(self):
        """SV 固有音素が 19 個であること (10 単一CP + 9 PUA)。"""
        assert len(SWEDISH_PHONEMES) == 19

    def test_single_codepoint_phonemes_no_pua(self):
        """単一コードポイント音素は PUA 割り当てが不要であること。"""
        single_cp = ["ɖ", "ʈ", "ɳ", "ɭ", "ɧ", "ɵ", "ʏ", "œ", "ɑ", "ø"]
        for ph in single_cp:
            assert len(ph) == 1, f"{ph} should be a single codepoint"
            # register() should return the same character for single CP
            assert register(ph) == ph

    def test_long_vowels_have_pua(self):
        """長母音 9 音素が全て PUA にマッピングされること。"""
        long_vowels = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for lv in long_vowels:
            assert len(lv) == 2, f"{lv} should be 2 characters"
            mapped = register(lv)
            assert len(mapped) == 1, f"{lv} should map to a single PUA char"
            assert 0xE059 <= ord(mapped) <= 0xE061, (
                f"{lv} PUA {ord(mapped):#x} outside expected range 0xE059-0xE061"
            )

    def test_pua_assignments_are_unique(self):
        """全 PUA 割り当てにコードポイントの重複がないこと。"""
        values = list(FIXED_PUA_MAPPING.values())
        assert len(values) == len(set(values)), "Duplicate PUA codepoints found"

    def test_pua_assignments_no_key_conflict(self):
        """全 PUA 割り当てにトークンキーの重複がないこと。"""
        keys = list(FIXED_PUA_MAPPING.keys())
        assert len(keys) == len(set(keys)), "Duplicate PUA token keys found"

    def test_pua_start_updated(self):
        """_PUA_START が 0xE064 に更新されていること。"""
        assert _PUA_START == 0xE064

    def test_sv_pua_range(self):
        """SV の PUA が 0xE059-0xE061 の範囲にあること。"""
        sv_entries = {
            "iː": 0xE059, "yː": 0xE05A, "eː": 0xE05B,
            "ɛː": 0xE05C, "øː": 0xE05D, "ɑː": 0xE05E,
            "oː": 0xE05F, "uː": 0xE060, "ʉː": 0xE061,
        }
        for token, expected_cp in sv_entries.items():
            assert token in FIXED_PUA_MAPPING, f"{token} not in FIXED_PUA_MAPPING"
            assert FIXED_PUA_MAPPING[token] == expected_cp, (
                f"{token}: expected {expected_cp:#x}, got {FIXED_PUA_MAPPING[token]:#x}"
            )

    def test_no_conflict_with_existing_languages(self):
        """SV の PUA が既存言語のコードポイントと衝突しないこと。"""
        existing_max = 0xE058  # FR ɔ̃
        sv_min = 0xE059        # SV iː
        assert sv_min > existing_max

    def test_bidirectional_mapping(self):
        """TOKEN2CHAR と CHAR2TOKEN が双方向で一貫していること。"""
        sv_tokens = ["iː", "yː", "eː", "ɛː", "øː", "ɑː", "oː", "uː", "ʉː"]
        for token in sv_tokens:
            char = TOKEN2CHAR[token]
            assert CHAR2TOKEN[char] == token
```

---

## 2. FR-05: Phonemizer ABC 準拠

### 2.1 概要

`SwedishPhonemizer` クラスは `base.py` の `Phonemizer` ABC (Abstract Base Class) を完全に実装する。既存の SpanishPhonemizer / FrenchPhonemizer と同じパターンに準拠し、`phonemize()`, `phonemize_with_prosody()`, `get_phoneme_id_map()` の 3 つの抽象メソッドを実装する。`post_process_ids()` はデフォルト実装を使用する。

### 2.2 クラス仕様: `SwedishPhonemizer`

**ファイルパス**: `src/python/piper_train/phonemize/swedish.py`

#### 2.2.1 クラスシグネチャ

```python
class SwedishPhonemizer(Phonemizer):
    """Rule-based Swedish G2P with optional NST dictionary lookup.

    Processing pipeline:
      1. Normalize & tokenize
      2. NST dictionary lookup (if loaded)
      3. Loanword suffix rules (-tion, -sion, -age)
      4. Loanword prefix rules (sch-, ch-, sh-, ph-, th-)
      5. Native G2P rules (soft/hard, vowel length, sj-sound)
      6. Post-processing (retroflex assimilation)
      7. Stress assignment
      8. ProsodyInfo construction (a1=0, a2=stress, a3=count)

    Parameters
    ----------
    dict_path : str | None
        Path to NST dictionary JSON file. If None, only rule-based
        G2P is used (suitable for testing and CI).
    """

    def __init__(self, dict_path: str | None = None):
        ...
```

#### 2.2.2 コンストラクタ仕様

```python
def __init__(self, dict_path: str | None = None):
    """Initialize the Swedish phonemizer.

    Parameters
    ----------
    dict_path : str | None
        Path to JSON dictionary file (NST SAMPA->IPA converted).
        Format: {"word": "ipa_transcription", ...}
        If None, rule-based G2P only (no dictionary lookup).
    """
    self._dict: dict[str, str] = {}
    if dict_path is not None:
        self._load_dict(dict_path)
```

**内部状態**:

| フィールド | 型 | 初期値 | 説明 |
|-----------|-----|--------|------|
| `self._dict` | `dict[str, str]` | `{}` | NST 辞書 (小文字単語 -> IPA 文字列) |

**`_load_dict()` 仕様**:
```python
def _load_dict(self, path: str) -> None:
    """Load NST dictionary from JSON file.

    Expects format: {"word": "ipa_string", ...}
    All keys are lowercase.
    """
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    self._dict = data
```

#### 2.2.3 `phonemize(text)` 仕様

```python
def phonemize(self, text: str) -> list[str]:
    """Convert Swedish text to a list of phoneme tokens.

    Returns phoneme tokens (single characters or PUA-mapped).
    BOS/EOS/PAD markers are NOT included -- they are added by
    post_process_ids() in the training pipeline.

    Parameters
    ----------
    text : str
        Input Swedish text.

    Returns
    -------
    list[str]
        Phoneme tokens. Multi-character phonemes (long vowels)
        are PUA-mapped to single characters.
    """
    phonemes, _ = self.phonemize_with_prosody(text)
    return phonemes
```

**実装パターン**: SpanishPhonemizer / FrenchPhonemizer と同一。`phonemize_with_prosody()` に委譲し、prosody 情報を捨てる。

#### 2.2.4 `phonemize_with_prosody(text)` 仕様

```python
def phonemize_with_prosody(
    self, text: str
) -> tuple[list[str], list[ProsodyInfo | None]]:
    """Convert Swedish text to phoneme tokens with prosody info.

    Processing pipeline:
      1. _normalize(text) -> str
      2. _tokenize(text) -> list[str]  (words + punctuation)
      3. For each word token:
         a. _lookup_dict(word) -> str | None
         b. If miss: _g2p_word(word) -> (phonemes, stress_info)
      4. _apply_retroflex_assimilation(phonemes)
      5. _assign_stress(phonemes)
      6. Build ProsodyInfo for each token
      7. map_sequence(phonemes) -> PUA-mapped list

    Returns
    -------
    tuple[list[str], list[ProsodyInfo | None]]
        (phoneme_tokens, prosody_list) where each phoneme has
        a corresponding ProsodyInfo with:
          a1 = 0  (unused, reserved for future tone accent)
          a2 = stress level (0=none, 1=secondary, 2=primary)
          a3 = word phoneme count (excluding stress markers)
    """
```

**処理フロー詳細**:

```
入力: "Barnen gick till skolan."

Step 1: _normalize()
  → "barnen gick till skolan."

Step 2: _tokenize()
  → ["barnen", "gick", "till", "skolan", "."]

Step 3: 各単語の音素化
  "barnen" → _lookup_dict("barnen")
    → ヒット: "ˈbɑːɳɛn"  → ["ˈ", "b", "ɑː", "ɳ", "ɛ", "n"]
  "gick"   → _lookup_dict("gick")
    → ミス → _g2p_word("gick") → ["j", "ɪ", "k"]  (g+前母音→/j/)
    → _assign_stress() → ["ˈ", "j", "ɪ", "k"]
  "till"   → _lookup_dict("till")
    → 機能語、ストレスなし → ["t", "ɪ", "l"]
  "skolan" → _lookup_dict("skolan")
    → ヒット: "ˈskuːlan" → ["ˈ", "s", "k", "uː", "l", "a", "n"]
  "."      → ["."]

Step 4: ProsodyInfo 構築
  各音素に ProsodyInfo(a1=0, a2=stress, a3=word_count) を付与

Step 5: map_sequence()
  多文字トークン ("ɑː", "uː" 等) を PUA 文字にマッピング

返却: (mapped_phonemes, prosody_list)
```

#### 2.2.5 `get_phoneme_id_map()` 仕様

```python
def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
    """Return None to delegate ID map to multilingual_id_map.

    Swedish is designed for multilingual use, where the ID map
    is managed by the unified multilingual ID map builder
    (multilingual_id_map.py). For standalone SV models, callers
    should use sv_id_map.SWEDISH_PHONEMES directly with the
    multilingual builder.
    """
    return None
```

**根拠**: ES/FR/PT と同じパターン。`get_phoneme_id_map()` が `None` を返すことで、呼び出し元 (`multilingual_id_map.py` の `get_multilingual_id_map()`) が統一 ID マップを構築する責務を持つ。

#### 2.2.6 `post_process_ids()` 仕様

`Phonemizer` ABC のデフォルト実装をそのまま使用する (オーバーライドしない)。

**デフォルト動作**:
1. 各 `phoneme_id` の間に `pad_ids` (ID 0) を挿入
2. 先頭に BOS (`^`) + pad を追加
3. 末尾に EOS (`$`) を追加

**根拠**: SpanishPhonemizer / FrenchPhonemizer / PortuguesePhonemizer と同一の動作。MultilingualPhonemizer が `eos_token` を動的に設定する場合のみオーバーライドが必要だが、SV は JA のような EOS バリアント (`?!`, `?.`, `?~`) を持たないため不要。

### 2.3 ProsodyInfo マッピング仕様

#### 2.3.1 次元定義

| 次元 | 名称 | SV での意味 | 値の範囲 | 例 |
|------|------|-----------|---------|-----|
| `a1` | (未使用) | Phase 2 で声調アクセント型に拡張予定 | 常に `0` | `0` |
| `a2` | ストレスレベル | 主ストレス / 副ストレス / 非ストレス | `0`, `1`, `2` | `ˈ` → `2`, `ˌ` → `1`, その他 → `0` |
| `a3` | 単語音素数 | ストレスマーカーを除いた音素数 | 正整数 | `"barn"` → `["b","ɑː","ɳ"]` → `3` |

#### 2.3.2 ストレスマーカーと ProsodyInfo の対応

```python
# ストレスマーカー自体:
"ˈ" → ProsodyInfo(a1=0, a2=2, a3=word_phoneme_count)

# ストレスマーカー直後の母音:
"ɑː" (after ˈ) → ProsodyInfo(a1=0, a2=2, a3=word_phoneme_count)

# 副ストレスマーカー:
"ˌ" → ProsodyInfo(a1=0, a2=1, a3=word_phoneme_count)

# その他の音素:
"b", "n", etc → ProsodyInfo(a1=0, a2=0, a3=word_phoneme_count)

# 句読点:
".", "," → ProsodyInfo(a1=0, a2=0, a3=0)

# スペース:
" " → ProsodyInfo(a1=0, a2=0, a3=0)
```

**注意**: この設計は EN (EnglishPhonemizer) と ES (SpanishPhonemizer) の ProsodyInfo マッピングと完全に一貫する。`a1=0` 固定、`a2` はストレス情報、`a3` は単語音素数。

#### 2.3.3 設計判断: a2 にストレスレベルを使用する根拠

| 選択肢 | 説明 | 採否 |
|--------|------|------|
| **a2=ストレス** | EN/ES/FR/PT と一貫。DP が共通パターンで学習可能 | **採用** |
| a2=声調アクセント | SV 固有の accent 1/2 を a2 に割り当て | Phase 2 で a1 に割り当て |
| a2=母音長 | 長/短を明示 | 不要 (PUA トークンで区別済み) |

### 2.4 内部メソッド仕様

#### 2.4.1 `_normalize(text) -> str`

```python
def _normalize(self, text: str) -> str:
    """Normalize text for G2P processing.

    Operations:
      1. Unicode NFC normalization
      2. Lowercase
      3. Replace typographic quotes with ASCII equivalents
      4. Normalize whitespace (collapse multiple spaces)

    Note: Swedish-specific characters (å, ä, ö) are preserved.
    """
```

**入力/出力例**:

| 入力 | 出力 |
|------|------|
| `"Hej, Världen!"` | `"hej, världen!"` |
| `"  Hej   Hej  "` | `"hej hej"` |
| `"Stockholm\u2019s"` | `"stockholm's"` |

#### 2.4.2 `_tokenize(text) -> list[str]`

```python
def _tokenize(self, text: str) -> list[str]:
    """Split normalized text into word tokens and punctuation.

    Uses regex pattern matching to separate:
      - Word tokens: sequences of Swedish letters (a-z, å, ä, ö, é, -)
      - Punctuation tokens: ., ,, ;, :, !, ?

    Returns
    -------
    list[str]
        Mixed list of word and punctuation tokens.
    """
```

**正規表現パターン**: `r"([a-zåäöéàü]+(?:-[a-zåäöéàü]+)*|[,.;:!?]+)"`

**入力/出力例**:

| 入力 | 出力 |
|------|------|
| `"hej, världen!"` | `["hej", ",", "världen", "!"]` |
| `"barn gick"` | `["barn", "gick"]` |
| `"sj-sound"` | `["sj-sound"]` |

#### 2.4.3 `_g2p_word(word) -> tuple[list[str], list[ProsodyInfo]]`

```python
def _g2p_word(self, word: str) -> tuple[list[str], list[ProsodyInfo]]:
    """Convert a single word to phonemes with prosody.

    Pipeline:
      1. Loanword suffix check (-tion, -sion, -age)
      2. Loanword prefix check (sch-, ch-, sh-, ph-, th-)
      3. Native G2P rules (soft/hard, vowel length, sj-sound)
      4. Retroflex assimilation (r+C → retroflex)
      5. Unstressed vowel reduction
      6. Stress assignment

    Parameters
    ----------
    word : str
        Normalized (lowercase) Swedish word.

    Returns
    -------
    tuple[list[str], list[ProsodyInfo]]
        (phonemes, prosody_list) for the word.
    """
```

**注意**: 辞書ルックアップは `_g2p_word` の外で行う。`phonemize_with_prosody()` が先に辞書を検索し、ミス時のみ `_g2p_word()` を呼ぶ。

#### 2.4.4 `_lookup_dict(word) -> str | None`

```python
def _lookup_dict(self, word: str) -> str | None:
    """Look up word in NST dictionary.

    Parameters
    ----------
    word : str
        Lowercase word to look up.

    Returns
    -------
    str | None
        IPA transcription string (with stress markers) if found,
        None if not in dictionary.
    """
    return self._dict.get(word)
```

**仕様**:
- 入力は小文字正規化済みの単語
- 辞書ヒット時は IPA 文字列を返す (例: `"ˈbɑːɳ"`)
- ミス時は `None` を返す
- 複数発音がある場合は辞書作成時に最初の発音のみ保持しているため、ルックアップは常に 1 件

#### 2.4.5 `_rule_based_g2p(word) -> str`

```python
def _rule_based_g2p(self, word: str) -> str:
    """Rule-based G2P for OOV words.

    Applies rules in the following order:
      1. Loanword suffix rules (-tion/-sion/-age)
      2. Loanword prefix rules (sch-/ch-/sh-/ph-/th-)
      3. Native grapheme-to-phoneme conversion
         - sk/k/g soft/hard splitting
         - sj-sound patterns
         - Basic consonant and vowel mappings
      4. Retroflex assimilation (r+t→ʈ, r+d→ɖ, etc.)
      5. Vowel length assignment (complementary quantity)
      6. Unstressed vowel reduction
      7. Stress assignment

    Parameters
    ----------
    word : str
        Lowercase word.

    Returns
    -------
    str
        IPA transcription string (with stress markers).
    """
```

### 2.5 テストケース (FR-05)

```python
# test/test_swedish_phonemizer.py (FR-05 関連部分)

import pytest
from piper_train.phonemize.swedish import SwedishPhonemizer
from piper_train.phonemize.base import Phonemizer, ProsodyInfo


class TestPhonemizerABCCompliance:
    """FR-05: Phonemizer ABC 準拠の検証。"""

    def test_is_phonemizer_subclass(self):
        """SwedishPhonemizer が Phonemizer のサブクラスであること。"""
        assert issubclass(SwedishPhonemizer, Phonemizer)

    def test_instantiation_without_dict(self):
        """辞書なしでインスタンス化できること。"""
        sv = SwedishPhonemizer()
        assert sv is not None

    def test_phonemize_returns_list_of_str(self):
        """phonemize() が list[str] を返すこと。"""
        sv = SwedishPhonemizer()
        result = sv.phonemize("hej")
        assert isinstance(result, list)
        assert all(isinstance(x, str) for x in result)

    def test_phonemize_with_prosody_returns_tuple(self):
        """phonemize_with_prosody() が (list[str], list[...]) を返すこと。"""
        sv = SwedishPhonemizer()
        phonemes, prosody = sv.phonemize_with_prosody("hej")
        assert isinstance(phonemes, list)
        assert isinstance(prosody, list)
        assert len(phonemes) == len(prosody)

    def test_get_phoneme_id_map_returns_none(self):
        """get_phoneme_id_map() が None を返すこと。"""
        sv = SwedishPhonemizer()
        assert sv.get_phoneme_id_map() is None

    def test_phonemize_empty_string(self):
        """空文字列に対して空リストを返すこと。"""
        sv = SwedishPhonemizer()
        assert sv.phonemize("") == []
        assert sv.phonemize("   ") == []

    def test_phonemize_punctuation_only(self):
        """句読点のみの入力が正しく処理されること。"""
        sv = SwedishPhonemizer()
        result = sv.phonemize("...")
        assert "." in result


class TestProsodyInfo:
    """FR-05: ProsodyInfo マッピングの検証。"""

    def test_a1_always_zero(self):
        """a1 が常に 0 であること。"""
        sv = SwedishPhonemizer()
        _, prosody = sv.phonemize_with_prosody("barn")
        for p in prosody:
            if p is not None:
                assert p.a1 == 0

    def test_a2_stress_on_primary(self):
        """主ストレスマーカー直後の母音で a2=2 であること。"""
        sv = SwedishPhonemizer()
        _, prosody = sv.phonemize_with_prosody("barn")
        # "barn" の主ストレス母音は a2=2 を持つべき
        stress_values = [p.a2 for p in prosody if p is not None]
        assert 2 in stress_values

    def test_a3_word_phoneme_count(self):
        """a3 が単語の音素数を正しく反映すること。"""
        sv = SwedishPhonemizer()
        _, prosody = sv.phonemize_with_prosody("ja")
        # "ja" → ["j", "ɑː"] → 2 音素
        word_prosody = [p for p in prosody if p is not None and p.a3 > 0]
        assert len(word_prosody) > 0
        assert all(p.a3 > 0 for p in word_prosody)

    def test_punctuation_prosody(self):
        """句読点の ProsodyInfo が (0, 0, 0) であること。"""
        sv = SwedishPhonemizer()
        phonemes, prosody = sv.phonemize_with_prosody("hej.")
        # 末尾の "." に対応する prosody
        for ph, pr in zip(phonemes, prosody):
            if ph == ".":
                assert pr == ProsodyInfo(a1=0, a2=0, a3=0)


class TestPostProcessIds:
    """FR-05: post_process_ids() デフォルト動作の検証。"""

    def test_bos_eos_padding(self):
        """BOS/EOS/PAD が正しく挿入されること。"""
        sv = SwedishPhonemizer()
        # 簡易テスト: phoneme_id_map を手動構築
        phoneme_id_map = {
            "_": [0], "^": [1], "$": [2],
            "h": [3], "ɛ": [4], "j": [5],
        }
        phoneme_ids = [3, 4, 5]  # h, ɛ, j
        prosody = [
            {"a1": 0, "a2": 0, "a3": 3},
            {"a1": 0, "a2": 0, "a3": 3},
            {"a1": 0, "a2": 0, "a3": 3},
        ]
        result_ids, result_prosody = sv.post_process_ids(
            phoneme_ids, prosody, phoneme_id_map
        )
        # BOS (^=1) + pad + h + pad + ɛ + pad + j + pad + EOS ($=2)
        assert result_ids[0] == 1   # BOS
        assert result_ids[1] == 0   # pad
        assert result_ids[-1] == 2  # EOS
```

---

## 3. FR-06: マルチリンガル統合

### 3.1 概要

スウェーデン語を既存のマルチリンガルフレームワークに統合する。変更対象は以下の 4 ファイル:

1. `registry.py` -- SwedishPhonemizer の自動登録
2. `multilingual.py` -- ラテン文字言語セットへの追加
3. `multilingual_id_map.py` -- 音素インベントリ登録
4. `token_mapper.py` -- (FR-04 で既述)

### 3.2 `registry.py` 変更仕様

**ファイルパス**: `src/python/piper_train/phonemize/registry.py`

#### 3.2.1 変更箇所: `_auto_register()` 関数

**変更位置**: French の登録ブロック (134-138 行目) の直後、BilingualPhonemizer 登録 (140 行目) の前

**変更前** (134-140 行目):
```python
    try:
        from .french import FrenchPhonemizer  # noqa: PLC0415

        register_language("fr", FrenchPhonemizer())
    except ImportError:
        pass
    # Register ja-en bilingual combo (backward compatibility)
```

**変更後**:
```python
    try:
        from .french import FrenchPhonemizer  # noqa: PLC0415

        register_language("fr", FrenchPhonemizer())
    except ImportError:
        pass
    try:
        from .swedish import SwedishPhonemizer  # noqa: PLC0415

        register_language("sv", SwedishPhonemizer())
    except ImportError:
        pass
    # Register ja-en bilingual combo (backward compatibility)
```

#### 3.2.2 変更箇所: `_detect_default_latin()` 関数

**変更位置**: 83 行目

**変更前**:
```python
    latin_langs = ["en", "es", "pt", "fr"]
```

**変更後**:
```python
    latin_langs = ["en", "es", "pt", "fr", "sv"]
```

**根拠**: スウェーデン語はラテン文字を使用する。`en-sv` の組み合わせでは `en` が優先される (リスト順序による)。`sv` のみの場合は `sv` がデフォルトラテン言語になる。

#### 3.2.3 import 追加

新規 import は不要。`_auto_register()` 内のローカル import で対応。

### 3.3 `multilingual.py` 変更仕様

**ファイルパス**: `src/python/piper_train/phonemize/multilingual.py`

#### 3.3.1 変更箇所: `UnicodeLanguageDetector.__init__()` の `_latin_languages`

**変更位置**: 76 行目

**変更前**:
```python
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr")
        }
```

**変更後**:
```python
        self._latin_languages = {
            lang for lang in languages if lang in ("en", "es", "pt", "fr", "sv")
        }
```

**根拠**: スウェーデン語はラテン文字を使用し、`detect_char()` の `_RE_LATIN` パターンでマッチするため、`_latin_languages` に含める必要がある。

#### 3.3.2 言語検出: スウェーデン語固有文字 (å, ä, ö) の活用

現行の `detect_char()` は、ラテン文字を `_RE_LATIN` (拡張ラテン U+00C0-U+00FF 含む) でマッチさせ、`default_latin_language` に割り当てる。スウェーデン語固有文字 å (U+00E5), ä (U+00E4), ö (U+00F6) はこの範囲に含まれるが、`en-sv` の組み合わせでは `default_latin_language = "en"` となるため、スウェーデン語テキストが英語として誤判定されるリスクがある。

**設計判断**: Phase 1 では `detect_char()` の変更は行わない。

| 選択肢 | 説明 | 採否 |
|--------|------|------|
| A. å/ä/ö ヒント追加 | `detect_char()` で å/ä/ö を検出したら `"sv"` を返す | Phase 2 |
| **B. 変更なし** | `en-sv` では英語がデフォルト。SV テキストは英語として音素化される | **Phase 1 採用** |
| C. 文脈ベース判定 | 単語レベルでスウェーデン語辞書を参照 | Phase 3 |

**根拠**: `en-sv` の組み合わせにおけるラテン文字判別は制約事項 C-05 として認識済み。Phase 1 では、以下の制限を受け入れる:

- `ja-sv` ではカナ/CJK が JA、ラテン文字が SV として正しく分離される (SV が唯一のラテン言語)
- `en-sv` では全ラテン文字が EN として処理される (SV は辞書に存在しない英語の OOV として処理される)
- `sv` 単独ではラテン文字が SV として正しく処理される

**将来対応 (Phase 2)**: `detect_char()` に以下の分岐を追加:

```python
# Phase 2: Swedish-specific character hints
_RE_SWEDISH_SPECIFIC = re.compile(r"[åäöÅÄÖ]")

def detect_char(self, ch: str, context_has_kana: bool = False) -> str | None:
    # ... existing logic ...

    # Swedish-specific characters (å, ä, ö)
    if self._RE_SWEDISH_SPECIFIC.match(ch):
        if "sv" in self.languages:
            return "sv"
    # ... continue to _RE_LATIN ...
```

### 3.4 `multilingual_id_map.py` 変更仕様

**ファイルパス**: `src/python/piper_train/phonemize/multilingual_id_map.py`

#### 3.4.1 変更箇所: `_register_builtin_phonemes()` 関数

**変更位置**: French の登録ブロック (69-75 行目) の直後

**変更前** (69-78 行目):
```python
    # French
    try:
        from .fr_id_map import FRENCH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["fr"] = FRENCH_PHONEMES
    except ImportError:
        pass


_register_builtin_phonemes()
```

**変更後**:
```python
    # French
    try:
        from .fr_id_map import FRENCH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["fr"] = FRENCH_PHONEMES
    except ImportError:
        pass

    # Swedish
    try:
        from .sv_id_map import SWEDISH_PHONEMES  # noqa: PLC0415

        LANGUAGE_PHONEMES["sv"] = SWEDISH_PHONEMES
    except ImportError:
        pass


_register_builtin_phonemes()
```

#### 3.4.2 import 追加

新規 import は不要。`_register_builtin_phonemes()` 内のローカル import で対応 (既存パターンと同一)。

#### 3.4.3 音素重複排除の動作検証

`get_multilingual_id_map()` は `seen` セットで重複排除を行う。SV の音素が既存言語と重複する場合、最初に登録した言語の ID が使用される。

**重複排除テーブル**:

| SV 音素 | 最初の登録言語 | 理由 |
|---------|--------------|------|
| ɑ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ɔ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ɛ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ɪ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ʊ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ŋ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ʃ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ʂ | ZH (`CHINESE_PHONEMES`) | ZH が先に登録される |
| ɕ | ZH (`CHINESE_PHONEMES`) | ZH が先に登録される |
| ø | FR (`FRENCH_PHONEMES`) | FR が先に登録される |
| œ | FR (`FRENCH_PHONEMES`) | FR が先に登録される |
| ː | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| ˈ, ˌ | EN (`ENGLISH_PHONEMES`) | EN が先に登録される |
| a, e, i, o, u | JA (`JAPANESE_PHONEMES`) | JA が先に登録される |
| b, d, f, h, k, l, m, n, p, s, t, v, j, r, w | JA (`JAPANESE_PHONEMES`) | JA が先に登録される |

**SV 固有 (新規 ID が付与される音素)**:

| 音素 | 説明 |
|------|------|
| ɖ | レトロフレックス有声破裂 |
| ʈ | レトロフレックス無声破裂 |
| ɳ | レトロフレックス鼻音 |
| ɭ | レトロフレックス側面音 |
| ɧ | sj-sound |
| ɵ | 短い閉中舌円唇母音 |
| ʏ | 短い近閉前舌円唇母音 |
| iː | 長い閉前舌非円唇 (PUA) |
| yː | 長い閉前舌円唇 (PUA) |
| eː | 長い半閉前舌 (PUA) |
| ɛː | 長い半開前舌 (PUA) |
| øː | 長い半閉前舌円唇 (PUA) |
| ɑː | 長い開後舌 (PUA) |
| oː | 長い半閉後舌 (PUA) |
| uː | 長い閉後舌 (PUA) |
| ʉː | 長い閉中舌円唇 (PUA) |

**合計**: SV は 16 個の新規 ID を追加する (既存言語との共有分は重複排除される)。

### 3.5 config.json スキーマ

スウェーデン語を含むモデルの `config.json` に必要なエントリ。

#### 3.5.1 `language_id_map` エントリ

**SV 単独モデル**:
```json
{
  "language_id_map": {
    "sv": 0
  }
}
```

**en-sv バイリンガルモデル**:
```json
{
  "language_id_map": {
    "en": 0,
    "sv": 1
  }
}
```

**7 言語モデル (ja-en-zh-es-fr-pt-sv)**:
```json
{
  "language_id_map": {
    "ja": 0,
    "en": 1,
    "zh": 2,
    "es": 3,
    "fr": 4,
    "pt": 5,
    "sv": 6
  }
}
```

**注意**: `language_id_map` のキー順序は `sorted()` 後のアルファベット順。値は 0 から連番。この順序は `multilingual_id_map.py` の `get_multilingual_id_map(languages)` の入力 `languages` リストと一致する必要がある。

#### 3.5.2 `phoneme_id_map` 構造

`phoneme_id_map` は `get_multilingual_id_map()` の出力。単一文字 (PUA 含む) → `[id]` のマッピング。

```json
{
  "phoneme_id_map": {
    "_": [0],
    "^": [1],
    "$": [2],
    "?": [3],
    ...
    "ɧ": [N],
    "ɖ": [N+1],
    "ʈ": [N+2],
    "\uE059": [N+3],
    "\uE05A": [N+4],
    ...
  }
}
```

**ID 付与順序**:
1. SPECIAL_TOKENS (10 個): `_`, `^`, `$`, `?`, `?!`, `?.`, `?~`, `#`, `[`, `]`
2. JAPANESE_PHONEMES
3. ENGLISH_PHONEMES (JA と重複するものは skip)
4. CHINESE_PHONEMES (JA/EN と重複するものは skip)
5. KOREAN_PHONEMES (重複 skip)
6. SPANISH_PHONEMES (重複 skip)
7. PORTUGUESE_PHONEMES (重複 skip)
8. FRENCH_PHONEMES (重複 skip)
9. **SWEDISH_PHONEMES (重複 skip)** -- 新規追加

### 3.6 マルチリンガルキーの動作

`registry.py` の `get_phonemizer()` はハイフン区切りの言語コードを自動的にソートし、`MultilingualPhonemizer` を生成する。

| 入力キー | canonical キー | 動作 |
|---------|---------------|------|
| `"sv"` | `"sv"` | `SwedishPhonemizer()` 単独 |
| `"en-sv"` | `"en-sv"` | `MultilingualPhonemizer(["en", "sv"])` |
| `"sv-en"` | `"en-sv"` | 上と同じインスタンス (canonical sort) |
| `"ja-sv"` | `"ja-sv"` | `MultilingualPhonemizer(["ja", "sv"])` |
| `"ja-en-zh-es-fr-pt-sv"` | `"en-es-fr-ja-pt-sv-zh"` | 7 言語 `MultilingualPhonemizer` |

### 3.7 テストケース (FR-06)

```python
# test/test_swedish_phonemizer.py (FR-06 関連部分)

import pytest
from piper_train.phonemize.registry import get_phonemizer, available_languages
from piper_train.phonemize.multilingual import (
    MultilingualPhonemizer,
    UnicodeLanguageDetector,
)
from piper_train.phonemize.multilingual_id_map import (
    get_multilingual_id_map,
    LANGUAGE_PHONEMES,
)


class TestRegistryIntegration:
    """FR-06: registry.py 統合の検証。"""

    def test_sv_registered(self):
        """'sv' がレジストリに登録されていること。"""
        assert "sv" in available_languages()

    def test_get_sv_phonemizer(self):
        """get_phonemizer('sv') が SwedishPhonemizer を返すこと。"""
        sv = get_phonemizer("sv")
        assert sv is not None
        from piper_train.phonemize.swedish import SwedishPhonemizer
        assert isinstance(sv, SwedishPhonemizer)

    def test_en_sv_creates_multilingual(self):
        """'en-sv' が MultilingualPhonemizer を生成すること。"""
        ensv = get_phonemizer("en-sv")
        assert isinstance(ensv, MultilingualPhonemizer)

    def test_sv_en_canonical_sort(self):
        """'sv-en' が 'en-sv' と同じインスタンスを返すこと。"""
        ensv1 = get_phonemizer("en-sv")
        ensv2 = get_phonemizer("sv-en")
        assert ensv1 is ensv2

    def test_ja_sv_creates_multilingual(self):
        """'ja-sv' が MultilingualPhonemizer を生成すること。"""
        jasv = get_phonemizer("ja-sv")
        assert isinstance(jasv, MultilingualPhonemizer)

    def test_7lang_combo(self):
        """7言語コンボが正しく動作すること。"""
        combo = get_phonemizer("ja-en-zh-es-fr-pt-sv")
        assert isinstance(combo, MultilingualPhonemizer)


class TestMultilingualDetector:
    """FR-06: multilingual.py 言語検出の検証。"""

    def test_sv_in_latin_languages(self):
        """SV が _latin_languages に含まれること。"""
        detector = UnicodeLanguageDetector(
            ["en", "sv"], default_latin_language="en"
        )
        assert "sv" in detector._latin_languages

    def test_ja_sv_latin_default(self):
        """'ja-sv' で SV がデフォルトラテン言語になること。"""
        # ja-sv では _detect_default_latin が sv を返す
        from piper_train.phonemize.registry import _detect_default_latin
        assert _detect_default_latin(["ja", "sv"]) == "sv"

    def test_en_sv_english_default(self):
        """'en-sv' で EN がデフォルトラテン言語になること。"""
        from piper_train.phonemize.registry import _detect_default_latin
        assert _detect_default_latin(["en", "sv"]) == "en"


class TestMultilingualIdMap:
    """FR-06: multilingual_id_map.py 統合の検証。"""

    def test_sv_in_language_phonemes(self):
        """LANGUAGE_PHONEMES に 'sv' が登録されていること。"""
        assert "sv" in LANGUAGE_PHONEMES

    def test_sv_phonemes_list(self):
        """SV の音素リストが空でないこと。"""
        assert len(LANGUAGE_PHONEMES["sv"]) > 0

    def test_sv_id_map_generation(self):
        """SV を含む ID マップが生成できること。"""
        id_map = get_multilingual_id_map(["sv"])
        assert len(id_map) > 0

    def test_en_sv_id_map_no_duplicates(self):
        """en-sv ID マップに重複 ID がないこと。"""
        id_map = get_multilingual_id_map(["en", "sv"])
        all_ids = [v[0] for v in id_map.values()]
        assert len(all_ids) == len(set(all_ids))

    def test_shared_phonemes_single_id(self):
        """ZH と共有する ʂ, ɕ が同一 ID を持つこと。"""
        id_map = get_multilingual_id_map(["zh", "sv"])
        # ʂ is registered first by ZH, SV reuses the same ID
        from piper_train.phonemize.token_mapper import register
        sh_retro = register("ʂ")
        assert sh_retro in id_map  # Single codepoint, direct lookup

    def test_sv_unique_phonemes_get_new_ids(self):
        """SV 固有音素 (ɧ, ɖ, ʈ, ɳ, ɭ 等) が新規 ID を得ること。"""
        id_map_no_sv = get_multilingual_id_map(["ja", "en"])
        id_map_sv = get_multilingual_id_map(["ja", "en", "sv"])
        # SV adds new phonemes, so sv map should have more entries
        assert len(id_map_sv) > len(id_map_no_sv)

    def test_7lang_id_map_includes_sv(self):
        """7言語 ID マップが SV 固有音素を含むこと。"""
        id_map = get_multilingual_id_map(
            ["ja", "en", "zh", "es", "fr", "pt", "sv"]
        )
        from piper_train.phonemize.token_mapper import register
        # Check SV-unique phonemes
        assert register("ɧ") in id_map  # sj-sound
        assert register("ɖ") in id_map  # retroflex d
        assert register("ʈ") in id_map  # retroflex t
        assert register("ɳ") in id_map  # retroflex n
        assert register("ɭ") in id_map  # retroflex l
        assert register("ɵ") in id_map  # close-mid central rounded
        assert register("ʏ") in id_map  # near-close near-front rounded
        # PUA-mapped long vowels
        assert register("iː") in id_map
        assert register("ɑː") in id_map
        assert register("ʉː") in id_map


class TestMultilingualPhonemizerIntegration:
    """FR-06: マルチリンガル音素化の統合検証。"""

    def test_ja_sv_phonemize(self):
        """ja-sv でカナとラテン文字が分離されること。"""
        jasv = get_phonemizer("ja-sv")
        result = jasv.phonemize("こんにちは、hej")
        assert len(result) > 0

    def test_sv_standalone_phonemize(self):
        """SV 単独で音素化が動作すること。"""
        sv = get_phonemizer("sv")
        result = sv.phonemize("hej")
        assert len(result) > 0

    def test_existing_languages_unaffected(self):
        """既存 6 言語の動作に変更がないこと (regression)。"""
        # JA
        ja = get_phonemizer("ja")
        ja_result = ja.phonemize("こんにちは")
        assert len(ja_result) > 0

        # EN
        en = get_phonemizer("en")
        en_result = en.phonemize("hello")
        assert len(en_result) > 0

        # ES
        es = get_phonemizer("es")
        es_result = es.phonemize("hola")
        assert len(es_result) > 0

    def test_6lang_combo_still_works(self):
        """既存 6 言語コンボ (ja-en-zh-es-fr-pt) が引き続き動作すること。"""
        combo = get_phonemizer("ja-en-zh-es-fr-pt")
        result = combo.phonemize("こんにちは hello")
        assert len(result) > 0
```

---

## 4. ファイル変更一覧

### 4.1 新規作成ファイル

| # | ファイルパス | 行数目安 | 説明 |
|---|------------|---------|------|
| 1 | `src/python/piper_train/phonemize/sv_id_map.py` | ~50 行 | SWEDISH_PHONEMES リスト + register() 呼び出し |

### 4.2 変更ファイル

| # | ファイルパス | 変更箇所 | 変更量 |
|---|------------|---------|--------|
| 1 | `src/python/piper_train/phonemize/token_mapper.py` | `FIXED_PUA_MAPPING` に 9 エントリ追加, `_PUA_START` を 0xE064 に更新 | +15 行 |
| 2 | `src/python/piper_train/phonemize/registry.py` | `_auto_register()` に SV 登録, `_detect_default_latin()` に `"sv"` 追加 | +7 行 |
| 3 | `src/python/piper_train/phonemize/multilingual.py` | `_latin_languages` に `"sv"` 追加 | +1 行 (1 行変更) |
| 4 | `src/python/piper_train/phonemize/multilingual_id_map.py` | `_register_builtin_phonemes()` に SV 登録 | +7 行 |

### 4.3 テストファイル

| # | ファイルパス | テスト数 | 説明 |
|---|------------|---------|------|
| 1 | `test/test_sv_id_map.py` | 10 | FR-04: PUA 割り当て、衝突検証 |
| 2 | `test/test_swedish_phonemizer.py` (FR-05 部分) | 9 | ABC 準拠、ProsodyInfo、post_process_ids |
| 3 | `test/test_swedish_phonemizer.py` (FR-06 部分) | 14 | レジストリ、検出器、ID マップ、統合 |
| **合計** | | **33** | FR-04/05/06 のみ (FR-01/02/03/07 は別文書) |

---

## 5. 受入基準チェックリスト

### FR-04: 音素インベントリ

- [ ] `sv_id_map.py` が `SWEDISH_PHONEMES` リスト (19 音素) をエクスポートする
- [ ] 単一コードポイント音素 (10 個) が PUA なしで `register()` を通過する
- [ ] 多文字トークン (9 個) が `FIXED_PUA_MAPPING` に固定 PUA (0xE059-0xE061) で登録される
- [ ] `_PUA_START` が `0xE064` に更新される
- [ ] 全 PUA コードポイントがユニーク (既存言語との衝突なし)
- [ ] `TOKEN2CHAR` / `CHAR2TOKEN` の双方向マッピングが一貫する
- [ ] テスト 10 件全て PASS

### FR-05: Phonemizer ABC 準拠

- [ ] `SwedishPhonemizer` が `Phonemizer` ABC のサブクラスである
- [ ] `phonemize(text)` が `list[str]` を返す
- [ ] `phonemize_with_prosody(text)` が `tuple[list[str], list[ProsodyInfo | None]]` を返す
- [ ] `get_phoneme_id_map()` が `None` を返す
- [ ] `post_process_ids()` がデフォルト実装 (BOS/EOS/PAD) を使用する
- [ ] ProsodyInfo の a1=0 (全トークン), a2=ストレス (0/1/2), a3=単語音素数
- [ ] 空文字列入力で空リストを返す
- [ ] 句読点のみの入力が処理される
- [ ] テスト 9 件全て PASS

### FR-06: マルチリンガル統合

- [ ] `registry.py` で `"sv"` が自動登録される
- [ ] `_detect_default_latin()` が `"sv"` を含む
- [ ] `multilingual.py` の `_latin_languages` に `"sv"` が含まれる
- [ ] `multilingual_id_map.py` の `LANGUAGE_PHONEMES["sv"]` が登録される
- [ ] `get_phonemizer("sv")` が `SwedishPhonemizer` を返す
- [ ] `get_phonemizer("en-sv")` が `MultilingualPhonemizer` を返す
- [ ] `get_phonemizer("ja-en-zh-es-fr-pt-sv")` が 7 言語 MultilingualPhonemizer を返す
- [ ] `get_multilingual_id_map(["ja", "en", "zh", "es", "fr", "pt", "sv"])` が重複のない ID マップを返す
- [ ] ZH と共有する ʂ, ɕ が同一 ID を持つ
- [ ] 既存 6 言語 (JA/EN/ZH/ES/FR/PT) の動作に変更がない
- [ ] テスト 14 件全て PASS

---

## 6. 付録

### 6.1 PUA 割り当て全体マップ (更新後)

```
0xE000-0xE015  JA 基本 (長母音, 促音, 拗音等)        16 個
0xE016-0xE018  JA 疑問詞マーカー                      3 個
0xE019-0xE01C  JA N バリアント                        4 個
0xE01D-0xE01E  多言語共有 (rr, y_vowel)               2 個
0xE01F         (reserved gap)                         1 個
0xE020-0xE04A  ZH (声母, 韻母, 声調)                  43 個
0xE04B-0xE052  KO (硬音, 内破音)                      8 個
0xE053         (reserved gap)                         1 個
0xE054-0xE055  ES/PT (tʃ, dʒ)                        2 個
0xE056-0xE058  FR (鼻母音 ɛ̃, ɑ̃, ɔ̃)                  3 個
0xE059-0xE061  SV (長母音 iː-ʉː)                     9 個  ← 新規
0xE062-0xE063  SV (reserved for future)               2 個  ← 予約
0xE064-        動的割り当て (_PUA_START)               ← 更新
```

**合計固定割り当て**: 91 個 (0xE000-0xE061, gap 2 個を除く)
**予約枠**: 4 個 (0xE01F, 0xE053, 0xE062-0xE063)
**動的割り当て開始**: 0xE064
**利用可能残量**: 0xE064-0xF8FF = 6,300 個

### 6.2 音素 ID 番号の見積もり (7 言語モデル)

| 言語 | 新規音素数 (重複排除後) |
|------|----------------------|
| SPECIAL_TOKENS | 10 |
| JA | ~55 |
| EN | ~35 (JA 重複分除外) |
| ZH | ~48 |
| KO | ~15 |
| ES | ~9 |
| PT | ~10 |
| FR | ~15 |
| **SV** | **~16** |
| **合計** | **~213** |

**注意**: 現在の 6 言語モデルは 173 シンボル。SV 追加で約 40 シンボル増加し、~213 シンボルとなる見込み。これは VITS モデルのエンベディング層サイズに影響するため、学習時の `config.json` で `num_symbols` を更新する必要がある。
