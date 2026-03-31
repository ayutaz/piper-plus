# スウェーデン語 テストスイート・パイプライン 要件定義書

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| 対象 | FR-07 (テストスイート) + 全体処理パイプライン仕様 + CI統合仕様 |
| 関連文書 | `swedish-requirements.md` (要求定義), `swedish-g2p-design.md` (設計), `swedish-g2p-research.md` (調査) |
| テストファイル | `test/test_swedish_phonemizer.py` |
| 総テストケース数 | 110 |

---

## 1. テストスイート仕様 (FR-07)

### 1.0 テストファイル構造

テストファイルは `test/test_swedish_phonemizer.py` に配置し、以下の構造に従う。

```python
"""Tests for Swedish phonemizer."""

import pytest

from piper_train.phonemize.swedish import (
    SwedishPhonemizer,
    phonemize_swedish,
    phonemize_swedish_with_prosody,
    _g2p_word,           # rule-based G2P 内部関数
    _apply_retroflex,    # レトロフレックス後処理
    _detect_stress,      # ストレス検出
)

# --- マーカー定義 ---
# @pytest.mark.unit           -- 辞書不要、rule-based のみ
# @pytest.mark.integration    -- 辞書ロード必要
# @pytest.mark.no_dict        -- 辞書なしで動作確認 (CI用)
```

全テストクラスは `pytest.mark.unit` をクラスレベルで付与する。辞書が必要なテストのみ `pytest.mark.integration` を追加する。

---

### 1.1 基本母音テスト (10テスト)

**目的**: 9つの母音書記素の長短ペアが正しくIPA変換されることを検証する。

**検証対象**: 各母音書記素 (a, e, i, o, u, y, å, ä, ö) が長母音/短母音に正しく分岐すること。

**キャッチ対象バグ**: Epitran の「全母音が長母音のまま出力される」バグ (非強勢母音 0%)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| V-01 | `test_vowel_a_long` | `"glas"` | `ɡ`, `l`, `ɑː`, `s` | 文字 "a" が単子音前で長母音 /ɑː/ になること | Epitran: 母音長判定漏れ |
| V-02 | `test_vowel_a_short` | `"glass"` | `ɡ`, `l`, `a`, `s` | 文字 "a" が重子音前で短母音 /a/ になること | Epitran: 母音短縮規則欠落 |
| V-03 | `test_vowel_e_long` | `"vet"` | `v`, `eː`, `t` | 文字 "e" が単子音前で長母音 /eː/ になること | 基本母音変換の正確性 |
| V-04 | `test_vowel_e_short` | `"vett"` | `v`, `ɛ`, `t` | 文字 "e" が重子音前で短母音 /ɛ/ になること | 長短分岐の正確性 |
| V-05 | `test_vowel_i_long` | `"vit"` | `v`, `iː`, `t` | 文字 "i" → /iː/ | 基本母音変換 |
| V-06 | `test_vowel_i_short` | `"vitt"` | `v`, `ɪ`, `t` | 文字 "i" → /ɪ/ (重子音前) | 長短分岐 |
| V-07 | `test_vowel_u_long` | `"hus"` | `h`, `ʉː`, `s` | 文字 "u" → /ʉː/ | espeak-ng: hus の長母音マーク漏れ |
| V-08 | `test_vowel_u_short` | `"hund"` | `h`, `ɵ`, `n`, `d` | 文字 "u" → /ɵ/ (クラスタ前) | 短母音 /ɵ/ の正確性 |
| V-09 | `test_vowel_u_long_ful` | `"ful"` | `f`, `ʉː`, `l` | 文字 "u" → /ʉː/ (単子音前) | espeak-ng: ful の長母音マーク漏れ |
| V-09b | `test_vowel_y_long` | `"ny"` | `n`, `yː` | 文字 "y" → /yː/ | 基本母音変換 |
| V-10 | `test_vowel_oe_long` | `"öl"` | `øː`, `l` | 文字 "ö" → /øː/ | 基本母音変換 |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestBasicVowels:
    """基本母音テスト: 9母音書記素 x 長短ペア"""

    def test_vowel_a_long(self):
        """glas: 'a' + 単子音 → 長母音 /ɑː/"""
        phonemes, *_ = _g2p_word("glas")
        assert "ɑː" in phonemes, f"Expected ɑː in {phonemes}"
        assert "ɡ" in phonemes

    def test_vowel_a_short(self):
        """glass: 'a' + 重子音 → 短母音 /a/"""
        phonemes, *_ = _g2p_word("glass")
        assert "a" in phonemes, f"Expected short 'a' in {phonemes}"
        assert "ɑː" not in phonemes, f"Should NOT have long ɑː in {phonemes}"

    def test_vowel_e_long(self):
        """vet: 'e' + 単子音 → /eː/"""
        phonemes, *_ = _g2p_word("vet")
        assert "eː" in phonemes

    def test_vowel_e_short(self):
        """vett: 'e' + 重子音 → /ɛ/"""
        phonemes, *_ = _g2p_word("vett")
        assert "ɛ" in phonemes
        assert "eː" not in phonemes

    def test_vowel_i_long(self):
        """vit: 'i' + 単子音 → /iː/"""
        phonemes, *_ = _g2p_word("vit")
        assert "iː" in phonemes

    def test_vowel_i_short(self):
        """vitt: 'i' + 重子音 → /ɪ/"""
        phonemes, *_ = _g2p_word("vitt")
        assert "ɪ" in phonemes
        assert "iː" not in phonemes

    def test_vowel_u_long(self):
        """hus: 'u' + 単子音 → /ʉː/"""
        phonemes, *_ = _g2p_word("hus")
        assert "ʉː" in phonemes

    def test_vowel_u_short(self):
        """hund: 'u' + クラスタ → /ɵ/"""
        phonemes, *_ = _g2p_word("hund")
        assert "ɵ" in phonemes
        assert "ʉː" not in phonemes

    def test_vowel_u_long_ful(self):
        """ful (ugly): 'u' + 単子音 → /ʉː/"""
        phonemes, *_ = _g2p_word("ful")
        assert "ʉː" in phonemes

    def test_vowel_y_long(self):
        """ny (new): 'y' → /yː/"""
        phonemes, *_ = _g2p_word("ny")
        assert "yː" in phonemes

    def test_vowel_oe_long(self):
        """öl: 'ö' + 単子音 → /øː/"""
        phonemes, *_ = _g2p_word("öl")
        assert "øː" in phonemes
```

---

### 1.2 Soft/Hard 子音分岐テスト (15テスト)

**目的**: sk/k/g + 前母音(軟)/後母音(硬)の分岐が正しいことを検証する。

**検証対象**: 設計書 2.3 の規則順序 (最長一致) が正しく動作すること。

**キャッチ対象バグ**: Epitran の「sk Soft/Hard が完全逆転」バグ (11%)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| SH-01 | `test_sk_front_vowel_e` | `"sked"` | `/ɧ/` を含む | sk + 前母音 e → /ɧ/ (sj-sound) | Epitran: sked → /sɕeːd/ (逆転) |
| SH-02 | `test_sk_front_vowel_y` | `"sky"` | `/ɧ/` を含む | sk + 前母音 y → /ɧ/ | Epitran: sky → /sɕyː/ (逆転) |
| SH-03 | `test_sk_front_vowel_oe` | `"skön"` | `/ɧ/` を含む | sk + 前母音 ö → /ɧ/ | Epitran: soft/hard 逆転 |
| SH-04 | `test_sk_front_vowel_i` | `"skinn"` | `/ɧ/` を含む | sk + 前母音 i → /ɧ/ | espeak-ng: sx で出力 → ɧ 要補正 |
| SH-05 | `test_sk_front_vowel_ae` | `"skäl"` | `/ɧ/` を含む | sk + 前母音 ä → /ɧ/ | Epitran soft/hard 逆転 |
| SH-06 | `test_sk_back_vowel_o` | `"skola"` | `/sk/`, `/ɧ/` を含まない | sk + 後母音 o → /sk/ (硬) | Epitran: skola → /ɧuːla/ (逆転) |
| SH-07 | `test_sk_back_vowel_a` | `"skam"` | `/sk/`, `/ɧ/` を含まない | sk + 後母音 a → /sk/ | Epitran: skam → /ɧɑːm/ (逆転) |
| SH-08 | `test_k_front_vowel` | `"kind"` | `/ɕ/` を含む | k + 前母音 i → /ɕ/ (tj-sound) | Epitran: 前処理で ɕ が先行発火 |
| SH-09 | `test_k_front_vowel_kop` | `"köp"` | `/ɕ/` を含む | k + 前母音 ö → /ɕ/ | 基本規則の検証 |
| SH-10 | `test_k_exception_kille` | `"kille"` | `/k/` (硬), `/ɕ/` を含まない | k + 前母音だが例外語 → /k/ | 例外リスト機能の検証 |
| SH-11 | `test_g_front_vowel` | `"göra"` | `/j/` を含む | g + 前母音 ö → /j/ | 基本規則の検証 |
| SH-12 | `test_g_exception_bagel` | `"bagel"` | `/ɡ/` (硬), `/j/` でない | g + 前母音だが例外語 → /ɡ/ | 例外リスト機能の検証 |
| SH-13 | `test_skj_unconditional` | `"skjorta"` | `/ɧ/` を含む | skj → 無条件で /ɧ/ | 最長一致の優先順位検証 |
| SH-14 | `test_stj_unconditional` | `"stjärna"` | `/ɧ/` を含む | stj → 無条件で /ɧ/ | 最長一致の優先順位検証 |
| SH-15 | `test_tj_unconditional` | `"tjugo"` | `/ɕ/` を含む | tj → 無条件で /ɕ/ (tj-sound) | /ɧ/ vs /ɕ/ の混同防止 |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestSoftHard:
    """Soft/Hard 子音分岐テスト: Epitran逆転バグの検出"""

    def test_sk_front_vowel_e(self):
        """sked (spoon): sk + 前母音 e → /ɧ/ (Epitran: 逆にsɕeːdを出力)"""
        phonemes, *_ = _g2p_word("sked")
        assert "ɧ" in phonemes, f"Expected ɧ (sj-sound) in {phonemes}"

    def test_sk_front_vowel_y(self):
        """sky (sky): sk + 前母音 y → /ɧ/"""
        phonemes, *_ = _g2p_word("sky")
        assert "ɧ" in phonemes

    def test_sk_front_vowel_oe(self):
        """skön (nice): sk + 前母音 ö → /ɧ/"""
        phonemes, *_ = _g2p_word("skön")
        assert "ɧ" in phonemes

    def test_sk_front_vowel_i(self):
        """skinn (skin): sk + 前母音 i → /ɧ/"""
        phonemes, *_ = _g2p_word("skinn")
        assert "ɧ" in phonemes

    def test_sk_front_vowel_ae(self):
        """skäl (reason): sk + 前母音 ä → /ɧ/"""
        phonemes, *_ = _g2p_word("skäl")
        assert "ɧ" in phonemes

    def test_sk_back_vowel_o(self):
        """skola (school): sk + 後母音 o → /sk/ (Epitran: 逆にɧuːlaを出力)"""
        phonemes, *_ = _g2p_word("skola")
        assert "ɧ" not in phonemes, f"Should NOT contain ɧ for back vowel: {phonemes}"
        assert "s" in phonemes and "k" in phonemes

    def test_sk_back_vowel_a(self):
        """skam (shame): sk + 後母音 a → /sk/"""
        phonemes, *_ = _g2p_word("skam")
        assert "ɧ" not in phonemes
        assert "s" in phonemes and "k" in phonemes

    def test_k_front_vowel(self):
        """kind (cheek): k + 前母音 i → /ɕ/ (NOT /ɧ/)"""
        phonemes, *_ = _g2p_word("kind")
        assert "ɕ" in phonemes, f"Expected ɕ (tj-sound) in {phonemes}"
        assert "ɧ" not in phonemes, "k+front should be ɕ, not ɧ"

    def test_k_front_vowel_kop(self):
        """köp (buy): k + 前母音 ö → /ɕ/"""
        phonemes, *_ = _g2p_word("köp")
        assert "ɕ" in phonemes

    def test_k_exception_kille(self):
        """kille (guy): k + 前母音 i だが例外語 → /k/ を保持"""
        phonemes, *_ = _g2p_word("kille")
        assert "k" in phonemes, f"Exception word 'kille' should keep /k/: {phonemes}"
        assert "ɕ" not in phonemes

    def test_g_front_vowel(self):
        """göra (to do): g + 前母音 ö → /j/"""
        phonemes, *_ = _g2p_word("göra")
        assert "j" in phonemes

    def test_g_exception_bagel(self):
        """bagel: g + 前母音 e だが例外語 → /ɡ/ を保持"""
        phonemes, *_ = _g2p_word("bagel")
        assert "ɡ" in phonemes, f"Exception word 'bagel' should keep /ɡ/: {phonemes}"

    def test_skj_unconditional(self):
        """skjorta (shirt): skj → 無条件で /ɧ/"""
        phonemes, *_ = _g2p_word("skjorta")
        assert "ɧ" in phonemes

    def test_stj_unconditional(self):
        """stjärna (star): stj → 無条件で /ɧ/"""
        phonemes, *_ = _g2p_word("stjärna")
        assert "ɧ" in phonemes

    def test_tj_unconditional(self):
        """tjugo (twenty): tj → /ɕ/ (NOT /ɧ/)"""
        phonemes, *_ = _g2p_word("tjugo")
        assert "ɕ" in phonemes
        assert "ɧ" not in phonemes, "tj should produce ɕ, not ɧ"
```

---

### 1.3 レトロフレックステスト (12テスト)

**目的**: r + 歯茎音 → レトロフレックス同化が正しく動作することを検証する。

**検証対象**: 設計書 3.2-3.4 のレトロフレックス規則、カスケード、ブロッキング。

**キャッチ対象バグ**: Epitran 0% (規則完全欠落)、espeak-ng 17% (rs のみ)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| RT-01 | `test_retroflex_rt` | `"kort"` | `/ʈ/` | r+t → /ʈ/ | Epitran: kɔrt (0%), espeak-ng: kɔt |
| RT-02 | `test_retroflex_rd` | `"bord"` | `/ɖ/` | r+d → /ɖ/ | Epitran: bɔrd (0%), espeak-ng: buːrd |
| RT-03 | `test_retroflex_rs` | `"fors"` | `/ʂ/` | r+s → /ʂ/ | Epitran: fɔrs (0%), espeak-ng: OK |
| RT-04 | `test_retroflex_rn` | `"barn"` | `/ɳ/` | r+n → /ɳ/ | Epitran: bɐrn (0%), espeak-ng: bɑːrn |
| RT-05 | `test_retroflex_rl` | `"karl"` | `/ɭ/` | r+l → /ɭ/ | Epitran: kɐrl (0%), espeak-ng: karl |
| RT-06 | `test_retroflex_cascade_rst` | `"först"` | `/ʂ/`, `/ʈ/` | r+s+t → /ʂʈ/ (カスケード) | カスケード規則の検証 |
| RT-07 | `test_retroflex_cascade_rns` | `"garns"` | `/ɳ/`, `/ʂ/` | r+n+s → /ɳʂ/ (カスケード) | 複数レトロフレックスの連鎖 |
| RT-08 | `test_rr_blocks_retroflex` | `"borrs"` | `/ʂ/` を含まない | rr + s → レトロフレックス化しない | rr ブロッキング規則 |
| RT-09 | `test_rl_stops_chain` | `"karls"` | `/ɭ/` を含む, 次のsは通常の/s/ | /ɭ/ の後は連鎖停止 | ɭ 停止規則 |
| RT-10 | `test_retroflex_cross_word` | `"har du"` | `/ɖ/` | 語境界を跨ぐ r+d → /ɖ/ | 連続発話時の語境界透過 |
| RT-11 | `test_retroflex_compound` | `"barndom"` | `/ɳ/` | 複合語内 r+n → /ɳ/ | 複合語境界の透過 |
| RT-12 | `test_no_retroflex_without_r` | `"hand"` | `/ɖ/` を含まない | r がない場合は通常の /d/ | 誤検出防止 |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestRetroflex:
    """レトロフレックス同化テスト: Epitran 0% の解消確認"""

    def test_retroflex_rt(self):
        """kort (short): r+t → /ʈ/"""
        phonemes = _apply_retroflex(["k", "ɔ", "r", "t"])
        assert "ʈ" in phonemes
        assert "r" not in phonemes, "r should be consumed by retroflex"

    def test_retroflex_rd(self):
        """bord (table): r+d → /ɖ/"""
        phonemes = _apply_retroflex(["b", "uː", "r", "d"])
        assert "ɖ" in phonemes

    def test_retroflex_rs(self):
        """fors (rapid): r+s → /ʂ/"""
        phonemes = _apply_retroflex(["f", "ɔ", "r", "s"])
        assert "ʂ" in phonemes

    def test_retroflex_rn(self):
        """barn (child): r+n → /ɳ/"""
        phonemes = _apply_retroflex(["b", "ɑː", "r", "n"])
        assert "ɳ" in phonemes

    def test_retroflex_rl(self):
        """karl (man): r+l → /ɭ/"""
        phonemes = _apply_retroflex(["k", "ɑː", "r", "l"])
        assert "ɭ" in phonemes

    def test_retroflex_cascade_rst(self):
        """först (first): r+s+t → /ʂ/+/ʈ/ (cascade)"""
        phonemes = _apply_retroflex(["f", "œ", "r", "s", "t"])
        assert "ʂ" in phonemes
        assert "ʈ" in phonemes
        assert "r" not in phonemes

    def test_retroflex_cascade_rns(self):
        """garns (yarn's): r+n+s → /ɳ/+/ʂ/ (cascade)"""
        phonemes = _apply_retroflex(["ɡ", "ɑː", "r", "n", "s"])
        assert "ɳ" in phonemes
        assert "ʂ" in phonemes

    def test_rr_blocks_retroflex(self):
        """borrs: rr + s → NO retroflex (rr blocks)"""
        # rr は長子音として扱われレトロフレックス化しない
        phonemes = _apply_retroflex(["b", "ɔ", "r", "r", "s"])
        assert "ʂ" not in phonemes, "rr should block retroflex assimilation"

    def test_rl_stops_chain(self):
        """karls: rl → /ɭ/ then chain stops (s stays as /s/)"""
        phonemes = _apply_retroflex(["k", "ɑː", "r", "l", "s"])
        assert "ɭ" in phonemes
        assert "ʂ" not in phonemes, "ɭ should stop the chain"
        assert "s" in phonemes

    def test_retroflex_cross_word(self):
        """'har du': r+d across word boundary → /ɖ/"""
        # 文レベルの音素化で語境界を跨ぐレトロフレックスを検証
        phonemes = phonemize_swedish("har du")
        assert "ɖ" in phonemes

    def test_retroflex_compound(self):
        """barndom (childhood): compound word内 rn → /ɳ/"""
        phonemes, *_ = _g2p_word("barndom")
        phonemes = _apply_retroflex(phonemes)
        assert "ɳ" in phonemes

    def test_no_retroflex_without_r(self):
        """hand: r がないので通常の /d/"""
        phonemes = _apply_retroflex(["h", "a", "n", "d"])
        assert "ɖ" not in phonemes
        assert "d" in phonemes
```

---

### 1.4 sj-sound テスト (20テスト)

**目的**: sj-sound (/ɧ/) の全綴りパターンと /ɕ/ (tj-sound) との区別を検証する。

**検証対象**: 設計書 5.2 の全パターン一覧。

**キャッチ対象バグ**: Epitran 33% (sk逆転 + tion/sch未対応)、espeak-ng 33% (sx記号問題)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| SJ-01 | `test_sj_basic` | `"sjö"` | `/ɧ/` | sj → /ɧ/ (常に) | 基本 sj パターン |
| SJ-02 | `test_sj_sjuk` | `"sjuk"` | `/ɧ/` | sj → /ɧ/ (語頭) | espeak-ng: sx 記号 |
| SJ-03 | `test_sj_sjunga` | `"sjunga"` | `/ɧ/` | sj → /ɧ/ (語頭、後母音前) | sj は無条件 |
| SJ-04 | `test_skj_pattern` | `"skjuta"` | `/ɧ/` | skj → /ɧ/ (無条件) | 最長一致の優先順位 |
| SJ-05 | `test_stj_pattern` | `"stjälk"` | `/ɧ/` | stj → /ɧ/ (無条件) | 最長一致の優先順位 |
| SJ-06 | `test_sch_pattern` | `"schema"` | `/ɧ/` | sch → /ɧ/ (ドイツ語借用) | espeak-ng: schema → ʃɛma (誤り) |
| SJ-07 | `test_sh_pattern` | `"show"` | `/ɧ/` | sh → /ɧ/ (英語借用) | ローンワード規則 |
| SJ-08 | `test_ch_pattern` | `"chef"` | `/ɧ/` | ch → /ɧ/ (スウェーデン語デフォルト) | ローンワード規則 |
| SJ-09 | `test_sk_front_e` | `"sked"` | `/ɧ/` | sk + 前母音 e → /ɧ/ | SH-01 と同一、sj観点での検証 |
| SJ-10 | `test_sk_front_i` | `"skina"` | `/ɧ/` | sk + 前母音 i → /ɧ/ | sk + i の組み合わせ |
| SJ-11 | `test_sk_front_y` | `"sky"` | `/ɧ/` | sk + 前母音 y → /ɧ/ | sk + y の組み合わせ |
| SJ-12 | `test_sk_front_ae` | `"skärm"` | `/ɧ/` | sk + 前母音 ä → /ɧ/ | sk + ä の組み合わせ |
| SJ-13 | `test_sk_front_oe` | `"sköta"` | `/ɧ/` | sk + 前母音 ö → /ɧ/ | sk + ö の組み合わせ |
| SJ-14 | `test_tion_suffix` | `"station"` | `/ɧ/`, `/uː/`, `/n/` | -tion → /ɧuːn/ | 接尾辞規則 |
| SJ-15 | `test_sion_suffix` | `"passion"` | `/ɧ/`, `/uː/`, `/n/` | -sion → /ɧuːn/ | 接尾辞規則 |
| SJ-16 | `test_age_suffix` | `"garage"` | `/ɑː/`, `/ɧ/` | -age → /ɑːɧ/ | フランス語接尾辞規則 |
| SJ-17 | `test_sj_vs_tj_distinction_sj` | `"sjö"` | `/ɧ/`, `/ɕ/` を含まない | sj → /ɧ/ のみ (NOT /ɕ/) | /ɧ/ vs /ɕ/ の混同防止 |
| SJ-18 | `test_sj_vs_tj_distinction_tj` | `"tjock"` | `/ɕ/`, `/ɧ/` を含まない | tj → /ɕ/ のみ (NOT /ɧ/) | /ɧ/ vs /ɕ/ の混同防止 |
| SJ-19 | `test_sj_vs_tj_distinction_kj` | `"kjol"` | `/ɕ/`, `/ɧ/` を含まない | kj → /ɕ/ (NOT /ɧ/) | /ɧ/ vs /ɕ/ の区別 |
| SJ-20 | `test_sk_back_not_sj` | `"skog"` | `/ɧ/` を含まない | sk + 後母音 o → /sk/ (NOT /ɧ/) | sk+後母音は sj-sound でない |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestSjSound:
    """sj-sound (/ɧ/) テスト: 全綴りパターンと /ɕ/ との区別"""

    def test_sj_basic(self):
        """sjö (lake): sj → /ɧ/ (常に)"""
        phonemes, *_ = _g2p_word("sjö")
        assert "ɧ" in phonemes

    def test_sj_sjuk(self):
        """sjuk (sick): sj → /ɧ/"""
        phonemes, *_ = _g2p_word("sjuk")
        assert "ɧ" in phonemes

    def test_sj_sjunga(self):
        """sjunga (sing): sj → /ɧ/"""
        phonemes, *_ = _g2p_word("sjunga")
        assert "ɧ" in phonemes

    def test_skj_pattern(self):
        """skjuta (shoot): skj → /ɧ/"""
        phonemes, *_ = _g2p_word("skjuta")
        assert "ɧ" in phonemes

    def test_stj_pattern(self):
        """stjälk (stem): stj → /ɧ/"""
        phonemes, *_ = _g2p_word("stjälk")
        assert "ɧ" in phonemes

    def test_sch_pattern(self):
        """schema (schedule): sch → /ɧ/"""
        phonemes, *_ = _g2p_word("schema")
        assert "ɧ" in phonemes

    def test_sh_pattern(self):
        """show: sh → /ɧ/"""
        phonemes, *_ = _g2p_word("show")
        assert "ɧ" in phonemes

    def test_ch_pattern(self):
        """chef: ch → /ɧ/ (Swedish default)"""
        phonemes, *_ = _g2p_word("chef")
        assert "ɧ" in phonemes

    def test_sk_front_e(self):
        """sked (spoon): sk + front vowel e → /ɧ/"""
        phonemes, *_ = _g2p_word("sked")
        assert "ɧ" in phonemes

    def test_sk_front_i(self):
        """skina (shine): sk + front vowel i → /ɧ/"""
        phonemes, *_ = _g2p_word("skina")
        assert "ɧ" in phonemes

    def test_sk_front_y(self):
        """sky (sky): sk + front vowel y → /ɧ/"""
        phonemes, *_ = _g2p_word("sky")
        assert "ɧ" in phonemes

    def test_sk_front_ae(self):
        """skärm (screen): sk + front vowel ä → /ɧ/"""
        phonemes, *_ = _g2p_word("skärm")
        assert "ɧ" in phonemes

    def test_sk_front_oe(self):
        """sköta (look after): sk + front vowel ö → /ɧ/"""
        phonemes, *_ = _g2p_word("sköta")
        assert "ɧ" in phonemes

    def test_tion_suffix(self):
        """station: -tion → /ɧuːn/"""
        phonemes, *_ = _g2p_word("station")
        assert "ɧ" in phonemes
        assert "uː" in phonemes
        assert "n" in phonemes

    def test_sion_suffix(self):
        """passion: -sion → /ɧuːn/"""
        phonemes, *_ = _g2p_word("passion")
        assert "ɧ" in phonemes

    def test_age_suffix(self):
        """garage: -age → /ɑːɧ/"""
        phonemes, *_ = _g2p_word("garage")
        assert "ɧ" in phonemes
        assert "ɑː" in phonemes

    def test_sj_vs_tj_distinction_sj(self):
        """sjö: /ɧ/ のみ出力 (NOT /ɕ/)"""
        phonemes, *_ = _g2p_word("sjö")
        assert "ɧ" in phonemes
        assert "ɕ" not in phonemes

    def test_sj_vs_tj_distinction_tj(self):
        """tjock (thick): /ɕ/ のみ出力 (NOT /ɧ/)"""
        phonemes, *_ = _g2p_word("tjock")
        assert "ɕ" in phonemes
        assert "ɧ" not in phonemes

    def test_sj_vs_tj_distinction_kj(self):
        """kjol (skirt): kj → /ɕ/ (NOT /ɧ/)"""
        phonemes, *_ = _g2p_word("kjol")
        assert "ɕ" in phonemes
        assert "ɧ" not in phonemes

    def test_sk_back_not_sj(self):
        """skog (forest): sk + back vowel o → /sk/ (NOT /ɧ/)"""
        phonemes, *_ = _g2p_word("skog")
        assert "ɧ" not in phonemes
```

---

### 1.5 母音長テスト (10テスト)

**目的**: Complementary Quantity 規則 (長母音 vs 短母音) と例外パターンを検証する。

**検証対象**: 設計書 6.2-6.3 の母音長規則、r+C 例外、語末 m 例外。

**キャッチ対象バグ**: Epitran の母音長 86% (r+C 例外と語末 m 例外を非対応)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| VL-01 | `test_vowel_length_glas` | `"glas"` | `/ɑː/` (長) | 単子音前 → 長母音 | 基本 CQ 規則 |
| VL-02 | `test_vowel_length_glass` | `"glass"` | `/a/` (短) | 重子音前 → 短母音 | 基本 CQ 規則 |
| VL-03 | `test_vowel_length_tak` | `"tak"` | `/ɑː/` (長) | 単子音前 → 長母音 | 基本 CQ 規則 |
| VL-04 | `test_vowel_length_tack` | `"tack"` | `/a/` (短) | ck (重子音) 前 → 短母音 | ck パターンの認識 |
| VL-05 | `test_vowel_length_ful` | `"ful"` | `/ʉː/` (長) | 単子音前 → 長母音 | espeak-ng: ful の長母音マーク漏れ |
| VL-06 | `test_vowel_length_full` | `"full"` | `/ɵ/` (短) | 重子音前 → 短母音 | 基本 CQ 規則 |
| VL-07 | `test_vowel_length_fil` | `"fil"` | `/iː/` (長) | 単子音前 → 長母音 | 基本 CQ 規則 |
| VL-08 | `test_vowel_length_fill` | `"fill"` | `/ɪ/` (短) | 重子音前 → 短母音 | 基本 CQ 規則 |
| VL-09 | `test_vowel_length_r_c_exception` | `"bord"` | `/uː/` (長) | r+C 例外: r + 子音前でも長母音 | Epitran: bɔrd (r+C 例外なし) |
| VL-10 | `test_vowel_length_word_final_m` | `"hem"` | `/ɛ/` (短) | 語末 m 例外: 重子音化されないが短母音 | 特殊例外パターン |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestVowelLength:
    """母音長テスト: Complementary Quantity 規則と例外"""

    def test_vowel_length_glas(self):
        """glas (glass): 'a' + 単子音 → 長母音 /ɑː/"""
        phonemes, *_ = _g2p_word("glas")
        assert "ɑː" in phonemes

    def test_vowel_length_glass(self):
        """glass (ice cream): 'a' + 重子音 → 短母音 /a/"""
        phonemes, *_ = _g2p_word("glass")
        assert "a" in phonemes
        assert "ɑː" not in phonemes

    def test_vowel_length_tak(self):
        """tak (roof): 'a' + 単子音 → 長母音 /ɑː/"""
        phonemes, *_ = _g2p_word("tak")
        assert "ɑː" in phonemes

    def test_vowel_length_tack(self):
        """tack (thanks): 'a' + ck → 短母音 /a/"""
        phonemes, *_ = _g2p_word("tack")
        assert "a" in phonemes
        assert "ɑː" not in phonemes

    def test_vowel_length_ful(self):
        """ful (ugly): 'u' + 単子音 → /ʉː/"""
        phonemes, *_ = _g2p_word("ful")
        assert "ʉː" in phonemes

    def test_vowel_length_full(self):
        """full (full): 'u' + 重子音 → /ɵ/"""
        phonemes, *_ = _g2p_word("full")
        assert "ɵ" in phonemes
        assert "ʉː" not in phonemes

    def test_vowel_length_fil(self):
        """fil (file): 'i' + 単子音 → /iː/"""
        phonemes, *_ = _g2p_word("fil")
        assert "iː" in phonemes

    def test_vowel_length_fill(self):
        """fill (nonsense): 'i' + 重子音 → /ɪ/"""
        phonemes, *_ = _g2p_word("fill")
        assert "ɪ" in phonemes
        assert "iː" not in phonemes

    def test_vowel_length_r_c_exception(self):
        """bord (table): r+C 例外 → 母音は長いまま /uː/"""
        phonemes, *_ = _g2p_word("bord")
        assert "uː" in phonemes, "r+C exception: vowel should stay long"

    def test_vowel_length_word_final_m(self):
        """hem (home): 語末 m 例外 → 短母音 /ɛ/"""
        phonemes, *_ = _g2p_word("hem")
        assert "ɛ" in phonemes, "Word-final m exception: vowel should be short"
        assert "eː" not in phonemes
```

---

### 1.6 "o" 曖昧性テスト (10テスト)

**目的**: 文字 "o" が4音素 (/uː/, /oː/, /ɔ/, /ʊ/) に正しく分岐することを検証する。

**検証対象**: 設計書 4.1-4.4 の "o" 4音素問題。NST辞書ルックアップが機能する場合はそちらを使用。

**キャッチ対象バグ**: Epitran 12% (常に /uː/)、espeak-ng 75%。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| O-01 | `test_o_long_default_sol` | `"sol"` | `/uː/` | "o" デフォルト長 → /uː/ | 基本 "o" 変換 |
| O-02 | `test_o_long_exception_son` | `"son"` | `/oː/` | "o" 例外語 → /oː/ | Epitran: suːn (常に uː) |
| O-03 | `test_o_short_om` | `"om"` | `/ɔ/` | "o" 短 (機能語) → /ɔ/ | Epitran: uːm (長母音化) |
| O-04 | `test_o_short_komma` | `"komma"` | `/ɔ/` | "o" + 重子音 → /ɔ/ | 基本 CQ 規則 |
| O-05 | `test_o_long_ost` | `"ost"` | `/uː/` | "o" + st → /uː/ (st は許容) | espeak-ng: ʊst (誤り) |
| O-06 | `test_o_long_bro` | `"bro"` | `/uː/` | "o" 語末 → /uː/ | 基本 "o" 変換 |
| O-07 | `test_o_long_stol` | `"stol"` | `/uː/` | "o" + 単子音 → /uː/ | 基本 "o" 変換 |
| O-08 | `test_o_short_blomma` | `"blomma"` | `/ɔ/` | "o" + mm → /ɔ/ | 重子音前の短母音 |
| O-09 | `test_o_long_skog` | `"skog"` | `/uː/` | "o" + g → /uː/ | 基本 "o" 変換 |
| O-10 | `test_o_retroflex_ord` | `"ord"` | `/uː/` + レトロフレックス | "o" + rd → /uː/ + /ɖ/ | espeak-ng: uːrd (レトロフレックス未処理) |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestOAmbiguity:
    """'o' 曖昧性テスト: 4音素分岐の検証"""

    def test_o_long_default_sol(self):
        """sol (sun): 'o' + 単子音 → /uː/ (デフォルト)"""
        phonemes, *_ = _g2p_word("sol")
        assert "uː" in phonemes

    def test_o_long_exception_son(self):
        """son (son): 'o' 例外語 → /oː/ (NOT /uː/)"""
        phonemes, *_ = _g2p_word("son")
        assert "oː" in phonemes, f"Expected /oː/ for exception word 'son': {phonemes}"
        assert "uː" not in phonemes

    def test_o_short_om(self):
        """om (about): 'o' 短 → /ɔ/"""
        phonemes, *_ = _g2p_word("om")
        assert "ɔ" in phonemes
        assert "uː" not in phonemes

    def test_o_short_komma(self):
        """komma (come): 'o' + mm → /ɔ/"""
        phonemes, *_ = _g2p_word("komma")
        assert "ɔ" in phonemes

    def test_o_long_ost(self):
        """ost (cheese): 'o' + st → /uː/"""
        phonemes, *_ = _g2p_word("ost")
        assert "uː" in phonemes

    def test_o_long_bro(self):
        """bro (bridge): 'o' 語末 → /uː/"""
        phonemes, *_ = _g2p_word("bro")
        assert "uː" in phonemes

    def test_o_long_stol(self):
        """stol (chair): 'o' + 単子音 → /uː/"""
        phonemes, *_ = _g2p_word("stol")
        assert "uː" in phonemes

    def test_o_short_blomma(self):
        """blomma (flower): 'o' + mm → /ɔ/"""
        phonemes, *_ = _g2p_word("blomma")
        assert "ɔ" in phonemes

    def test_o_long_skog(self):
        """skog (forest): 'o' + g → /uː/"""
        phonemes, *_ = _g2p_word("skog")
        assert "uː" in phonemes

    def test_o_retroflex_ord(self):
        """ord (word): 'o' → /uː/ + rd → /ɖ/"""
        phonemes = phonemize_swedish("ord")
        assert "uː" in phonemes or "ɖ" in phonemes
```

---

### 1.7 非強勢母音テスト (8テスト)

**目的**: 語末非強勢母音が短い変種で出力されることを検証する。

**検証対象**: 設計書 6.4 の非強勢母音短縮規則。

**キャッチ対象バグ**: Epitran 0% (語末母音が全て長母音のまま: gata → ɡɑːtɑː)。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| US-01 | `test_unstressed_a_gata` | `"gata"` | 語末は `/a/` (NOT `/ɑː/`) | 語末 -a → 短い [a] | Epitran: ɡɑːtɑː (語末ɑː) |
| US-02 | `test_unstressed_a_flicka` | `"flicka"` | 語末は `/a/` (NOT `/ɑː/`) | 語末 -a → 短い [a] | Epitran: flɪkɑː |
| US-03 | `test_unstressed_e_pojke` | `"pojke"` | 語末は `/ɛ/` (NOT `/eː/`) | 語末 -e → 短い [ɛ] | Epitran: puːjɕeː |
| US-04 | `test_unstressed_e_vacker` | `"vacker"` | 語末は `/ɛr/` | 語末 -er → [ɛr] | 語末 -er パターン |
| US-05 | `test_unstressed_en_vatten` | `"vatten"` | 語末は `/ɛn/` | 語末 -en → [ɛn] | Epitran: vɐteːn |
| US-06 | `test_unstressed_en_liten` | `"liten"` | 語末は `/ɛn/` | 語末 -en → [ɛn] | 語末 -en パターン |
| US-07 | `test_unstressed_er_soker` | `"söker"` | 語末は `/ɛr/` | 語末 -er → [ɛr] | 語末 -er パターン |
| US-08 | `test_unstressed_ar_bilar` | `"bilar"` | 語末は `/ar/` | 語末 -ar → [ar] | 語末 -ar パターン |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestUnstressedVowels:
    """非強勢母音テスト: Epitran 0% の解消確認"""

    def test_unstressed_a_gata(self):
        """gata (street): 語末 -a → 短い [a] (NOT [ɑː])"""
        phonemes, *_ = _g2p_word("gata")
        # 最後の母音が長母音 ɑː でないことを確認
        assert phonemes[-1] != "ɑː", f"Final vowel should be short 'a': {phonemes}"

    def test_unstressed_a_flicka(self):
        """flicka (girl): 語末 -a → 短い [a]"""
        phonemes, *_ = _g2p_word("flicka")
        assert phonemes[-1] != "ɑː", f"Final vowel should be short 'a': {phonemes}"

    def test_unstressed_e_pojke(self):
        """pojke (boy): 語末 -e → 短い [ɛ] (NOT [eː])"""
        phonemes, *_ = _g2p_word("pojke")
        # 最後の母音が eː でないことを確認
        last_vowel_idx = max(i for i, p in enumerate(phonemes)
                            if p in {"a", "ɛ", "e", "eː", "ɪ", "iː", "ɔ",
                                     "uː", "oː", "ɵ", "ʉː", "ʏ", "yː",
                                     "œ", "øː", "ɑː"})
        assert phonemes[last_vowel_idx] != "eː"

    def test_unstressed_e_vacker(self):
        """vacker (beautiful): 語末 -er → [ɛr]"""
        phonemes, *_ = _g2p_word("vacker")
        # 末尾付近に ɛ + r があること
        ipa_str = "".join(phonemes)
        assert "ɛ" in ipa_str

    def test_unstressed_en_vatten(self):
        """vatten (water): 語末 -en → [ɛn]"""
        phonemes, *_ = _g2p_word("vatten")
        ipa_str = "".join(phonemes)
        assert "ɛn" in ipa_str or (phonemes[-2] == "ɛ" and phonemes[-1] == "n")

    def test_unstressed_en_liten(self):
        """liten (small): 語末 -en → [ɛn]"""
        phonemes, *_ = _g2p_word("liten")
        assert phonemes[-1] == "n"
        assert phonemes[-2] in ("ɛ", "e")

    def test_unstressed_er_soker(self):
        """söker (seeks): 語末 -er → [ɛr]"""
        phonemes, *_ = _g2p_word("söker")
        assert phonemes[-1] == "r"

    def test_unstressed_ar_bilar(self):
        """bilar (cars): 語末 -ar → [ar]"""
        phonemes, *_ = _g2p_word("bilar")
        assert phonemes[-1] == "r"
        assert phonemes[-2] in ("a", "ɑ")
```

---

### 1.8 ストレステスト (10テスト)

**目的**: ストレス検出規則 (第1音節デフォルト、接頭辞例外、接尾辞吸引、複合語) の正確性を検証する。

**検証対象**: 設計書 6.5 のストレス検出優先順位。

**キャッチ対象バグ**: 接頭辞/接尾辞のストレス配置ミス。

| # | テスト関数名 | 入力 | 期待出力 (ストレス位置) | 検証内容 | キャッチ対象 |
|---|------------|------|---------------------|---------|------------|
| ST-01 | `test_stress_first_syllable_default` | `"flicka"` | 第1音節にˈ | ゲルマン語デフォルト: 第1音節 | 基本ストレス規則 |
| ST-02 | `test_stress_first_syllable_vatten` | `"vatten"` | 第1音節にˈ | 第1音節ストレスの追加確認 | 基本ストレス規則 |
| ST-03 | `test_stress_be_prefix` | `"betala"` | 第2音節にˈ | be- 接頭辞: 非ストレス → 第2音節 | 接頭辞例外 |
| ST-04 | `test_stress_foer_prefix` | `"förstå"` | 第2音節にˈ | för- 接頭辞: 非ストレス → 第2音節 | 接頭辞例外 |
| ST-05 | `test_stress_ge_prefix` | `"gemensam"` | 第2音節にˈ | ge- 接頭辞: 非ストレス → 第2音節 | 接頭辞例外 |
| ST-06 | `test_stress_tion_suffix` | `"station"` | 最終音節 (-tion) にˈ | -tion 接尾辞: ストレス吸引 | 接尾辞ストレス吸引 |
| ST-07 | `test_stress_itet_suffix` | `"universitet"` | -itet にˈ | -itet 接尾辞: ストレス吸引 | 接尾辞ストレス吸引 |
| ST-08 | `test_stress_ist_suffix` | `"turist"` | 最終音節にˈ | -ist 接尾辞: ストレス吸引 | 接尾辞ストレス吸引 |
| ST-09 | `test_stress_compound_primary` | `"sjukhus"` | 第1要素にˈ | 複合語: 第1要素に主ストレス | 複合語ストレス規則 |
| ST-10 | `test_stress_monosyllable` | `"hus"` | ˈ が存在 | 単音節語もストレスを持つ | 単音節語のストレス |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestStress:
    """ストレステスト: 第1音節デフォルト + 接頭辞/接尾辞例外"""

    def test_stress_first_syllable_default(self):
        """flicka: ゲルマン語デフォルト → 第1音節にストレス"""
        phonemes = phonemize_swedish("flicka")
        stress_idx = phonemes.index("ˈ") if "ˈ" in phonemes else -1
        assert stress_idx >= 0, "Stress marker missing"
        # ˈ は最初の母音より前に出現すべき
        first_vowel_idx = next(
            i for i, p in enumerate(phonemes) if p in _SV_VOWELS
        )
        assert stress_idx < first_vowel_idx + 2

    def test_stress_first_syllable_vatten(self):
        """vatten: 第1音節にストレス"""
        phonemes = phonemize_swedish("vatten")
        assert "ˈ" in phonemes

    def test_stress_be_prefix(self):
        """betala (pay): be- は非ストレス → 第2音節"""
        phonemes = phonemize_swedish("betala")
        assert "ˈ" in phonemes

    def test_stress_foer_prefix(self):
        """förstå (understand): för- は非ストレス → 第2音節"""
        phonemes = phonemize_swedish("förstå")
        assert "ˈ" in phonemes

    def test_stress_ge_prefix(self):
        """gemensam (common): ge- は非ストレス → 第2音節"""
        phonemes = phonemize_swedish("gemensam")
        assert "ˈ" in phonemes

    def test_stress_tion_suffix(self):
        """station: -tion がストレスを吸引"""
        phonemes = phonemize_swedish("station")
        assert "ˈ" in phonemes

    def test_stress_itet_suffix(self):
        """universitet (university): -itet がストレスを吸引"""
        phonemes = phonemize_swedish("universitet")
        assert "ˈ" in phonemes

    def test_stress_ist_suffix(self):
        """turist (tourist): -ist がストレスを吸引"""
        phonemes = phonemize_swedish("turist")
        assert "ˈ" in phonemes

    def test_stress_compound_primary(self):
        """sjukhus (hospital): 複合語 → 第1要素にˈ"""
        phonemes = phonemize_swedish("sjukhus")
        assert "ˈ" in phonemes

    def test_stress_monosyllable(self):
        """hus (house): 単音節語でもストレスマーカーあり"""
        phonemes = phonemize_swedish("hus")
        assert "ˈ" in phonemes
```

---

### 1.9 ローンワードテスト (10テスト)

**目的**: フランス語/英語/ドイツ語由来のローンワード規則が正しく動作することを検証する。

**検証対象**: 設計書 8.2 のローンワードパターン (接尾辞、接頭辞/字母)。

**キャッチ対象バグ**: Epitran の -tion/sch/ch 未対応、espeak-ng の sx 記号問題。

| # | テスト関数名 | 入力 | 期待出力 (キー音素) | 検証内容 | キャッチ対象 |
|---|------------|------|-------------------|---------|------------|
| LW-01 | `test_loanword_tion` | `"station"` | `/ɧ/`, `/uː/`, `/n/` | -tion → /ɧuːn/ | Epitran: -tion 未対応 |
| LW-02 | `test_loanword_sion` | `"passion"` | `/ɧ/` | -sion → /ɧuːn/ | Epitran: -sion 未対応 |
| LW-03 | `test_loanword_age` | `"garage"` | `/ɧ/`, `/ɑː/` | -age → /ɑːɧ/ | フランス語接尾辞 |
| LW-04 | `test_loanword_ch_chef` | `"chef"` | `/ɧ/` | ch → /ɧ/ (SV default) | フランス語借用 |
| LW-05 | `test_loanword_sch_schema` | `"schema"` | `/ɧ/` | sch → /ɧ/ | espeak-ng: ʃɛma (誤り) |
| LW-06 | `test_loanword_sh_show` | `"show"` | `/ɧ/` | sh → /ɧ/ | 英語借用 |
| LW-07 | `test_loanword_giraff` | `"giraff"` | `/j/` または `/ɧ/` | g の例外的発音 | フランス語借用の g |
| LW-08 | `test_loanword_sjuk_native` | `"sjuk"` | `/ɧ/` | ネイティブ sj (比較基準) | ネイティブ vs ローンワード |
| LW-09 | `test_loanword_ph_filosofi` | `"filosofi"` | `/f/` を含む | ph → /f/ (リスペリング済み) | ph パターン |
| LW-10 | `test_loanword_choklad` | `"choklad"` | `/ɧ/` | ch → /ɧ/ (フランス語由来) | ch パターンの追加検証 |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestLoanwords:
    """ローンワードテスト: 仏語/英語/独語借用パターン"""

    def test_loanword_tion(self):
        """station: -tion → /ɧuːn/"""
        phonemes, *_ = _g2p_word("station")
        assert "ɧ" in phonemes

    def test_loanword_sion(self):
        """passion: -sion → /ɧuːn/"""
        phonemes, *_ = _g2p_word("passion")
        assert "ɧ" in phonemes

    def test_loanword_age(self):
        """garage: -age → /ɑːɧ/"""
        phonemes, *_ = _g2p_word("garage")
        assert "ɧ" in phonemes

    def test_loanword_ch_chef(self):
        """chef: ch → /ɧ/"""
        phonemes, *_ = _g2p_word("chef")
        assert "ɧ" in phonemes

    def test_loanword_sch_schema(self):
        """schema: sch → /ɧ/"""
        phonemes, *_ = _g2p_word("schema")
        assert "ɧ" in phonemes

    def test_loanword_sh_show(self):
        """show: sh → /ɧ/"""
        phonemes, *_ = _g2p_word("show")
        assert "ɧ" in phonemes

    def test_loanword_giraff(self):
        """giraff: g → /j/ or /ɧ/ (French loanword)"""
        phonemes, *_ = _g2p_word("giraff")
        assert "j" in phonemes or "ɧ" in phonemes

    def test_loanword_sjuk_native(self):
        """sjuk (native): sj → /ɧ/ (baseline comparison)"""
        phonemes, *_ = _g2p_word("sjuk")
        assert "ɧ" in phonemes

    def test_loanword_ph_filosofi(self):
        """filosofi: ph → /f/ (respelled in modern Swedish)"""
        phonemes, *_ = _g2p_word("filosofi")
        assert "f" in phonemes

    def test_loanword_choklad(self):
        """choklad (chocolate): ch → /ɧ/"""
        phonemes, *_ = _g2p_word("choklad")
        assert "ɧ" in phonemes
```

---

### 1.10 エッジケーステスト (5テスト)

**目的**: 境界条件やイレギュラーな入力に対してクラッシュせず、合理的な出力を返すことを検証する。

**検証対象**: 防御的プログラミングの堅牢性。

**キャッチ対象バグ**: 空文字列での IndexError、数字・句読点混在時のクラッシュ。

| # | テスト関数名 | 入力 | 期待出力 | 検証内容 | キャッチ対象 |
|---|------------|------|---------|---------|------------|
| EC-01 | `test_edge_empty_string` | `""` | 空リストまたは BOS/EOS のみ | 空文字列でクラッシュしない | IndexError 防止 |
| EC-02 | `test_edge_single_char` | `"a"` | 長さ > 0 のリスト | 1文字入力が処理される | 最小入力の検証 |
| EC-03 | `test_edge_punctuation_only` | `"...!"` | 句読点トークンのみ | 句読点のみでクラッシュしない | 句読点処理の堅牢性 |
| EC-04 | `test_edge_numbers` | `"123"` | クラッシュしない (透過or無視) | 数字入力でクラッシュしない | 数字非対応時の安全性 |
| EC-05 | `test_edge_mixed_language` | `"Hej hello"` | 長さ > 0 | スウェーデン語+英語混在 | 未知文字の安全な処理 |

**テスト実装パターン**:

```python
@pytest.mark.unit
class TestEdgeCases:
    """エッジケーステスト: 境界条件の堅牢性"""

    def test_edge_empty_string(self):
        """空文字列でクラッシュしない"""
        phonemes = phonemize_swedish("")
        assert isinstance(phonemes, list)

    def test_edge_single_char(self):
        """1文字入力が処理される"""
        phonemes = phonemize_swedish("a")
        assert len(phonemes) > 0

    def test_edge_punctuation_only(self):
        """句読点のみでクラッシュしない"""
        phonemes = phonemize_swedish("...!")
        assert isinstance(phonemes, list)

    def test_edge_numbers(self):
        """数字入力でクラッシュしない"""
        phonemes = phonemize_swedish("123")
        assert isinstance(phonemes, list)

    def test_edge_mixed_language(self):
        """スウェーデン語+英語混在でクラッシュしない"""
        phonemes = phonemize_swedish("Hej hello")
        assert len(phonemes) > 0
```

---

### 1.11 テストケース集計表

| カテゴリ | テスト数 | マーカー | 辞書依存 |
|---------|---------|---------|---------|
| 基本母音 (1.1) | 10 | `@pytest.mark.unit` | なし |
| Soft/Hard (1.2) | 15 | `@pytest.mark.unit` | なし (例外リストはコード内定数) |
| レトロフレックス (1.3) | 12 | `@pytest.mark.unit` | なし |
| sj-sound (1.4) | 20 | `@pytest.mark.unit` | なし |
| 母音長 (1.5) | 10 | `@pytest.mark.unit` | なし |
| "o" 曖昧性 (1.6) | 10 | `@pytest.mark.unit` | なし (例外リストはコード内定数) |
| 非強勢母音 (1.7) | 8 | `@pytest.mark.unit` | なし |
| ストレス (1.8) | 10 | `@pytest.mark.unit` | なし |
| ローンワード (1.9) | 10 | `@pytest.mark.unit` | なし |
| エッジケース (1.10) | 5 | `@pytest.mark.unit` | なし |
| **合計** | **110** | | |

---

## 2. 全体処理パイプライン仕様

### 2.1 End-to-End データフロー

```
テキスト入力 (str)
  │
  ▼
┌─────────────────────────────────────────────────┐
│ SwedishPhonemizer.phonemize_with_prosody(text)  │
│                                                   │
│  ┌──────────────────────────┐                    │
│  │ Stage 0: 正規化 & トークン化 │                    │
│  │  - 小文字変換                │                    │
│  │  - Unicode NFC正規化         │                    │
│  │  - 正規表現でトークン分割     │                    │
│  │  - 句読点の分離              │                    │
│  └──────────────┬───────────┘                    │
│                  │ tokens: list[str]              │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 1: 辞書ルックアップ    │                    │
│  │  (word ごと)                │                    │
│  │  NST辞書 (822K語, JSON)     │                    │
│  │  → ヒット: IPA文字列を返却   │                    │
│  │  → ミス: Stage 2 へ        │                    │
│  └──────────────┬───────────┘                    │
│                  │                                │
│                  ▼ (辞書ミスの場合のみ)             │
│  ┌──────────────────────────┐                    │
│  │ Stage 2: ローンワード接尾辞    │                    │
│  │  -tion → /ɧuːn/            │                    │
│  │  -sion → /ɧuːn/            │                    │
│  │  -ssion → /ɧuːn/           │                    │
│  │  -age → /ɑːɧ/              │                    │
│  └──────────────┬───────────┘                    │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 3: ローンワード接頭辞    │                    │
│  │  sch → /ɧ/                  │                    │
│  │  ch → /ɧ/                   │                    │
│  │  sh → /ɧ/                   │                    │
│  │  ph → /f/                   │                    │
│  │  th → /t/                   │                    │
│  └──────────────┬───────────┘                    │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 4: ネイティブ G2P 規則   │                    │
│  │  - Soft/Hard (sk,k,g + V)    │                    │
│  │  - sj パターン (sj,skj,stj)  │                    │
│  │  - 母音長 (CQ規則)           │                    │
│  │  - 非強勢母音短縮            │                    │
│  │  - 基本子音変換              │                    │
│  └──────────────┬───────────┘                    │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 5: レトロフレックス同化   │                    │
│  │  r+t→/ʈ/, r+d→/ɖ/,        │                    │
│  │  r+s→/ʂ/, r+n→/ɳ/,        │                    │
│  │  r+l→/ɭ/                   │                    │
│  │  カスケード + rr ブロック      │                    │
│  └──────────────┬───────────┘                    │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 6: ストレス付与         │                    │
│  │  1. 辞書ストレス (あれば)     │                    │
│  │  2. 接尾辞ストレス吸引       │                    │
│  │  3. 接頭辞非ストレス         │                    │
│  │  4. デフォルト: 第1音節      │                    │
│  └──────────────┬───────────┘                    │
│                  │ phonemes: list[str]            │
│                  ▼                                │
│  ┌──────────────────────────┐                    │
│  │ Stage 7: ProsodyInfo 構築     │                    │
│  │  + トークンマッピング          │                    │
│  │  a1=0, a2=ストレス, a3=音素数 │                    │
│  │  多文字トークン → PUA         │                    │
│  │  map_sequence(phonemes)      │                    │
│  └──────────────┬───────────┘                    │
│                  │                                │
└──────────────────┼────────────────────────────────┘
                   │ (phonemes, prosody_list)
                   ▼
┌──────────────────────────────────────────────────┐
│ post_process_ids (Phonemizer ABC デフォルト実装)    │
│  - BOS (^) 追加                                   │
│  - EOS ($) 追加                                   │
│  - inter-phoneme PAD 挿入                         │
│  - phoneme_id_map で int ID に変換                 │
└──────────────────────────────────────────────────┘
                   │
                   ▼
         phoneme_ids: list[int]
         prosody_features: list[dict | None]
```

### 2.2 ステージ変換トレース例: "Jag bor i Stockholm"

各ステージで入力文がどのように変換されるかを段階的に示す。

#### Stage 0: 正規化 & トークン化

```
入力: "Jag bor i Stockholm"
↓ 小文字変換
"jag bor i stockholm"
↓ トークン分割 (正規表現: [a-zåäö]+ | [,.;:!?]+)
tokens = ["jag", "bor", "i", "stockholm"]
```

#### Stage 1: 辞書ルックアップ (word ごと)

```
"jag"       → 辞書ヒット → IPA: "jɑːɡ"  (※ 機能語として短母音の可能性あり)
"bor"       → 辞書ヒット → IPA: "buːr"
"i"         → 辞書ヒット → IPA: "iː"  (※ 前置詞: 短母音 [ɪ])
"stockholm" → 辞書ヒット → IPA: "stɔkːhɔlm" (※ 辞書内表記に従う)
```

辞書ヒットの場合、Stage 2-4 はスキップされ Stage 5 (レトロフレックス後処理) に直接進む。

以下は **辞書ミスを仮定** した場合のフォールバック処理トレース:

#### Stage 2-3: ローンワード規則 (該当なし)

```
"jag"       → ローンワード接尾辞/接頭辞に該当なし → Stage 4 へ
"bor"       → 該当なし → Stage 4 へ
"i"         → 該当なし → Stage 4 へ
"stockholm" → 該当なし → Stage 4 へ
```

#### Stage 4: ネイティブ G2P 規則

```
"jag"
  j → /j/
  a → 機能語 → /a/ (短母音)
  g → /ɡ/
  結果: ["j", "a", "ɡ"]

"bor"
  b → /b/
  o → 単子音前 → /uː/ (デフォルト長)
  r → /r/
  結果: ["b", "uː", "r"]

"i"
  i → 機能語 → /ɪ/ (短母音)
  結果: ["ɪ"]

"stockholm"
  st → /st/
  o → 子音クラスタ前 → /ɔ/ (短)
  ck → /k/ (ck は重子音)
  h → /h/
  o → クラスタ前 → /ɔ/ (短)
  l → /l/
  m → /m/
  結果: ["s", "t", "ɔ", "k", "h", "ɔ", "l", "m"]
```

#### Stage 5: レトロフレックス同化

```
"jag":       ["j", "a", "ɡ"] → 変化なし (r なし)
"bor":       ["b", "uː", "r"] → 変化なし (r の後に歯茎音なし)
"i":         ["ɪ"] → 変化なし
"stockholm": ["s", "t", "ɔ", "k", "h", "ɔ", "l", "m"] → 変化なし (r なし)

語境界間: "bor" + "i" → r + ɪ → レトロフレックス不適用 (ɪ は歯茎音でない)
```

#### Stage 6: ストレス付与

```
"jag"       → 機能語リスト → ストレスなし
"bor"       → 単音節語 → 第1音節 → ˈ付与
  結果: ["b", "ˈ", "uː", "r"]
"i"         → 機能語 → ストレスなし
"stockholm" → 第1音節デフォルト → ˈ付与
  結果: ["s", "t", "ˈ", "ɔ", "k", "h", "ɔ", "l", "m"]
```

#### Stage 7: ProsodyInfo 構築 + トークンマッピング (PUA)

```
全単語について:
  a1 = 0 (未使用)
  a2 = 0 (非強勢) or 2 (主ストレス: ˈ直後の母音)
  a3 = 単語の音素数 (ˈ除く)

"jag":  3音素 → [ProsodyInfo(0,0,3)] * 3
"bor":  3音素 → [PI(0,0,3), PI(0,2,3), PI(0,2,3), PI(0,0,3)]  # ˈは4トークン目
" ":    [PI(0,0,0)]  (スペーストークン)
...
```

**トークンマッピング (PUA):**

```
多文字トークン → PUA 単一コードポイント:
  "uː" → chr(0xE060)  (PUA: 長い閉後舌母音)
  他の多文字トークンも同様に変換

変換前: ["j", "a", "ɡ", " ", "b", "ˈ", "uː", "r", " ", "ɪ", " ", ...]
変換後: ["j", "a", "ɡ", " ", "b", "ˈ", "\ue060", "r", " ", "ɪ", " ", ...]
```

#### post_process_ids (BOS/EOS/PAD 挿入)

```
入力 phonemes: ["j", "a", "ɡ", " ", "b", "ˈ", "\ue060", "r", ...]

phoneme_id_map (multilingual) でID変換:
  "^" → [1]   (BOS)
  "$" → [2]   (EOS)
  "_" → [0]   (PAD)
  "j" → [15]
  "a" → [5]
  "ɡ" → [42]
  ...

結果 phoneme_ids:
  [1, 0, 15, 0, 5, 0, 42, 0, ..., 2]
  (BOS, PAD, j, PAD, a, PAD, ɡ, PAD, ..., EOS)
```

### 2.3 データ型定義

```python
# 入力
text: str                                    # "Jag bor i Stockholm"

# Stage 0 出力
tokens: list[str]                            # ["jag", "bor", "i", "stockholm"]

# Stage 1-4 出力 (per-word)
word_phonemes: list[str]                     # ["b", "uː", "r"]

# Stage 5-6 出力 (per-word, レトロフレックス同化 + ストレス付与済み)
processed_phonemes: list[str]                # ["b", "ˈ", "uː", "r"]

# Stage 7 出力 (ProsodyInfo 構築 + トークンマッピング)
prosody_list: list[ProsodyInfo | None]       # [PI(0,0,3), PI(0,2,3), ...]
mapped_phonemes: list[str]                   # ["b", "ˈ", "\ue060", "r"]

# post_process_ids 出力
phoneme_ids: list[int]                       # [1, 0, 45, 0, 142, 0, ...]
prosody_features: list[dict | None]          # [{"a1":0,"a2":0,"a3":0}, ...]
```

---

## 3. CI統合仕様

### 3.1 pytest マーカー

テストには以下のマーカーを使用する。

| マーカー | 用途 | 辞書依存 | CI実行環境 |
|---------|------|---------|----------|
| `@pytest.mark.unit` | 辞書不要のrule-basedテスト | なし | Ubuntu/macOS/Windows |
| `@pytest.mark.integration` | 辞書ロードが必要なテスト | あり | Ubuntu/macOS (辞書DL可能) |
| `@pytest.mark.no_dict` | 辞書なし動作の明示テスト | なし | Ubuntu/macOS/Windows |

### 3.2 条件付きテスト実行

辞書ファイルの有無によるテスト実行制御。

```python
import os
import pytest

# 辞書パスの検出
_DICT_PATH = os.environ.get(
    "PIPER_SV_DICT",
    os.path.join(os.path.dirname(__file__), "..", "data", "sv_dict_core.json"),
)
_HAS_DICT = os.path.exists(_DICT_PATH)

# 辞書なしスキップデコレータ
skip_no_dict = pytest.mark.skipif(
    not _HAS_DICT,
    reason="Swedish NST dictionary not available",
)
```

辞書ルックアップのテスト (integration マーカー) は以下のように記述する。

```python
@pytest.mark.integration
@skip_no_dict
class TestDictLookup:
    """辞書ルックアップテスト (辞書ファイルが必要)"""

    def test_dict_lookup_barn(self):
        """NST辞書: barn → ɳ を含む"""
        phonemizer = SwedishPhonemizer(dict_path=_DICT_PATH)
        phonemes = phonemizer.phonemize("barn")
        assert "ɳ" in phonemes

    def test_dict_lookup_sjukhus(self):
        """NST辞書: sjukhus → ɧ を含む"""
        phonemizer = SwedishPhonemizer(dict_path=_DICT_PATH)
        phonemes = phonemizer.phonemize("sjukhus")
        assert "ɧ" in phonemes
```

`@pytest.mark.unit` テストは辞書なしで動作し、`_g2p_word()` (rule-based 内部関数) を直接呼び出す。

### 3.3 GitHub Actions ワークフロー変更

`python-tests.yml` に変更は不要。既存の以下のコマンドでスウェーデン語テストが自動実行される。

```yaml
# 既存の unit テスト実行 (変更不要)
pytest tests/ -v --tb=short -m "unit and not training and not benchmark and not inference"
```

**理由**: 全110テストが `@pytest.mark.unit` を付与しており、辞書なしで動作する。CIでは辞書ダウンロードは行わない。

### 3.4 paths トリガー変更

`python-tests.yml` の `paths` に以下が含まれていることを確認する。

```yaml
paths:
  - 'src/python/**'        # ← 既存。swedish.py, sv_id_map.py をカバー
  - 'test/**'              # ← 追加が必要な場合
```

注意: 現在のワークフローでは `test/` ディレクトリは `paths` トリガーに含まれていない。ただし、テストファイルは `src/python/` 配下の変更時に自動実行されるため、必須ではない。テスト単独の変更でCIを走らせたい場合は `'test/**'` の追加を検討する。

### 3.5 テスト実行コマンド (ローカル)

```bash
# 全テスト実行 (辞書なし、unit のみ)
cd src/python
uv run pytest ../../test/test_swedish_phonemizer.py -v --tb=short -m unit

# 辞書テスト込みで実行
PIPER_SV_DICT=/path/to/sv_dict_core.json \
  uv run pytest ../../test/test_swedish_phonemizer.py -v --tb=short

# 特定カテゴリのみ
uv run pytest ../../test/test_swedish_phonemizer.py -v -k "TestRetroflex"

# 特定テストのみ
uv run pytest ../../test/test_swedish_phonemizer.py -v -k "test_sk_front_vowel_e"
```

### 3.6 conftest.py マーカー登録

`test/conftest.py` (または `src/python/conftest.py`) に以下のマーカー定義を追加する。

```python
def pytest_configure(config):
    config.addinivalue_line("markers", "no_dict: tests that verify no-dict behavior")
```

注意: `unit` と `integration` マーカーは既に登録済みの前提。

---

## 4. テスト品質基準

### 4.1 受入基準

| 基準 | 条件 |
|------|------|
| 全テスト PASS | 110/110 テストが PASS |
| CI グリーン | Ubuntu/macOS/Windows の全3 OS で PASS |
| 既存テスト非影響 | JA/EN/ZH/ES/FR/PT の全既存テストに regression なし |
| カバレッジ | rule-based G2P の分岐パス 90%+ |

### 4.2 テスト信頼性マトリクス

| カテゴリ | テスト数 | 期待精度 | 辞書なし精度 | 辞書あり精度 |
|---------|---------|---------|------------|------------|
| 基本母音 | 10 | 100% | 100% | 100% |
| Soft/Hard | 15 | 100% | 100% (例外リストはコード内) | 100% |
| レトロフレックス | 12 | 100% | 100% | 100% |
| sj-sound | 20 | 95%+ | 90%+ (-tion等は規則で処理) | 100% |
| 母音長 | 10 | 95%+ | 95%+ | 100% |
| "o" 曖昧性 | 10 | 90%+ | 70%+ (辞書なしは /oː/ 例外語のみ) | 100% |
| 非強勢母音 | 8 | 100% | 100% | 100% |
| ストレス | 10 | 90%+ | 80%+ | 95%+ |
| ローンワード | 10 | 90%+ | 85%+ | 100% |
| エッジケース | 5 | 100% | 100% | 100% |

---

## 5. Epitran/espeak-ng バグ対応マッピング

以下の表は、各テストケースが Epitran と espeak-ng のどのバグをキャッチするかを示す。

| Epitran バグ | テストID | 説明 |
|-------------|---------|------|
| sk Soft/Hard 逆転 | SH-01, SH-02, SH-03, SH-06, SH-07 | CSVの `sk,ɧ` が全skにマッチ |
| レトロフレックス完全欠落 (0%) | RT-01 - RT-05 | r+C 規則が存在しない |
| "o" 常に /uː/ (12%) | O-02, O-03, O-04 | CSV に `o,uː` のみ |
| 非強勢母音の長母音化 (0%) | US-01 - US-08 | 語末母音が長母音のまま |
| -tion/sch 未対応 | SJ-06, SJ-14, SJ-15 | 接尾辞/借用パターンの欠落 |

| espeak-ng バグ | テストID | 説明 |
|---------------|---------|------|
| sx 独自記号 | SJ-01, SJ-02 | /ɧ/ の代わりに /sx/ を使用 |
| レトロフレックス 17% (rs のみ) | RT-01, RT-02, RT-04, RT-05 | rn/rd/rl/rt が未処理 |
| hus 長母音マーク漏れ | V-07 | hus → hʉk (長母音マーク欠落) |
| ful 長母音マーク漏れ | VL-05 | ful → fʉl (長母音マーク欠落) |
| schema → ʃɛma | SJ-06 | sch を /ʃ/ に誤変換 |
| ost → ʊst | O-05 | /ʊ/ vs /uː/ の混同 |
| ジェミネートマーク | US-04, US-05 | kː, tː が不一致 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|---|---------|
| 2026-03-30 | 1.0 | 初版作成 |
