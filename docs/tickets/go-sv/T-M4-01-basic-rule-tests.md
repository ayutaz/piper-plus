# T-M4-01: 基本規則テスト (母音/子音/レトロフレックス/ローンワード)

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M4: テストスイート |
| 依存チケット | T-M3 (後処理 + Phonemizer統合) |
| 後続チケット | T-M4-02 (ストレス・Prosody・PUA・統合テスト) |
| 対象ファイル | `src/go/phonemize/swedish_test.go` (新規) |
| 推定行数 | ~800行 |

## 1. タスク目的とゴール

M2/M3 で実装したスウェーデン語 G2P コアエンジンの基本規則を ~80 テストケースで検証する。テストケースは Python (`test_swedish_phonemizer.py`, `test_swedish_m1_1_m1_2.py`) および Rust (`swedish.rs` `#[cfg(test)]`) の既存テストと同じ入出力ペアを使用し、全プラットフォームで一貫した結果を保証する。

カバー範囲:
- 基本母音の長短 (20テスト)
- 子音規則 (3文字/2文字/1文字パターン) (30テスト)
- k/g 軟硬例外語 (15テスト)
- レトロフレックス同化 (15テスト)

## 2. 実装する内容の詳細

### 2.1 テストファイルの基本構造

Go 既存テスト (`french_test.go`, `spanish_test.go`) に倣い、テーブル駆動テストを使用する。

```go
package phonemize

import (
    "strings"
    "testing"
)

// svWordPhonemes は単語レベルの G2P 結果を返すヘルパー。
// PUA マッピング前の生音素列を返す。
func svWordPhonemes(word string) string {
    p := NewSwedishPhonemizer()
    result, _ := p.PhonemizeWithProsody(word)
    return strings.Join(result.Tokens, "")
}

// svContains は音素列に指定の IPA 記号が含まれるか判定する。
func svContains(word, ipa string) bool {
    return strings.Contains(svWordPhonemes(word), ipa)
}
```

### 2.2 基本母音テスト (20テスト): TestSvLongVowels / TestSvShortVowels

全 10 母音文字 (a, e, i, o, u, y, a, ae, oe) の長/短バリアントを検証する。

#### 長母音テスト (10テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| V-01 | `TestSvLongVowel_A_Gata` | `"gata"` | `ɑː` を含む | a + 単子音 -> 長母音 ɑː (0xE05E) | `test_long_a`: `_join("gata") == "ˈɡɑːta"` | `test_glas_long_a` |
| V-02 | `TestSvLongVowel_E_Vet` | `"vet"` | `eː` を含む | e + 単子音 -> eː (0xE05B) | `test_vowel_e_long` | `test_vet_long_e` |
| V-03 | `TestSvLongVowel_I_Fin` | `"fin"` | `iː` を含む | i + 単子音 -> iː (0xE059) | `test_long_i`: `"iː" in _join("fin")` | `test_vit_long_i` |
| V-04 | `TestSvLongVowel_O_Sol` | `"sol"` | `uː` を含む | o (デフォルト) + 単子音 -> uː (0xE060) | `test_o_default_long_u` | `test_o_sol_long_u` |
| V-05 | `TestSvLongVowel_U_Hus` | `"hus"` | `ʉː` を含む | u + 単子音 -> ʉː (0xE061) | `test_long_u`: `"ʉː" in _join("hus")` | (PUA E061) |
| V-06 | `TestSvLongVowel_Y_Syn` | `"syn"` | `yː` を含む | y + 単子音 -> yː (0xE05A) | `test_long_y`: `"yː" in _join("syn")` | -- |
| V-07 | `TestSvLongVowel_AE_Sal` | `"säl"` | `ɛː` を含む | ae + 単子音 -> ɛː (0xE05C) | `test_long_ae`: `"ɛː" in _join("säl")` | -- |
| V-08 | `TestSvLongVowel_OE_Ol` | `"öl"` | `øː` を含む | oe + 単子音 -> øː (0xE05D) | `test_long_oe`: `"øː" in _join("öl")` | -- |
| V-09 | `TestSvLongVowel_AA_Aar` | `"år"` | `oː` を含む | aa + 単子音 -> oː (0xE05F) | -- | -- |
| V-10 | `TestSvLongVowel_Glas` | `"glas"` | `ɑː` を含む | glas: 単子音後 -> 長 ɑː | `test_glas_long_a` | `test_glas_long_a` |

```go
func TestSvLongVowels(t *testing.T) {
    tests := []struct {
        word string
        want string // 含まれるべき IPA
    }{
        {"gata", "ɑː"},
        {"vet", "eː"},
        {"fin", "iː"},
        {"sol", "uː"},
        {"hus", "ʉː"},
        {"syn", "yː"},
        {"säl", "ɛː"},
        {"öl", "øː"},
        {"år", "oː"},
        {"glas", "ɑː"},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            if !svContains(tt.word, tt.want) {
                t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q",
                    tt.word, svWordPhonemes(tt.word), tt.want)
            }
        })
    }
}
```

#### 短母音テスト (10テスト)

| # | テスト名 | 入力 | 期待出力 (含む / 含まない) | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|-------------------------|---------|-----------|---------|
| V-11 | `TestSvShortVowel_A_Katt` | `"katt"` | `a` 含む, `ɑː` 含まない | ダブル子音 -> 短 a | `test_short_a` | `test_short_vowel_geminate` |
| V-12 | `TestSvShortVowel_E_Fest` | `"fest"` | `ɛ` 含む, `eː` 含まない | クラスタ -> 短 ɛ | `test_short_e_cluster`: `_join("fest") == "ˈfɛst"` | `test_vett_short_e` |
| V-13 | `TestSvShortVowel_I_Flicka` | `"flicka"` | `ɪ` 含む | HARD_K例外 + 短 ɪ | `test_short_i` | -- |
| V-14 | `TestSvShortVowel_O_Kort` | `"kort"` | `ɔ` 含む | o + 2子音 -> 短 ɔ | `test_o_short` | `test_o_kort_short` |
| V-15 | `TestSvShortVowel_U_Hund` | `"hund"` | `ɵ` 含む, `ʉː` 含まない | クラスタ -> 短 ɵ | -- | -- |
| V-16 | `TestSvShortVowel_Y_Mygg` | `"mygg"` | `ʏ` 含む | ダブル子音 -> 短 ʏ | -- | -- |
| V-17 | `TestSvShortVowel_OE_Host` | `"höst"` | `œ` 含む | クラスタ -> 短 œ | `test_short_oe` | -- |
| V-18 | `TestSvShortVowel_Glass` | `"glass"` | `ɑː` 含まない | ダブル s -> 短 a | `test_glass_short_a` | `test_glass_short_a` |
| V-19 | `TestSvShortVowel_Tack` | `"tack"` | `ɑː` 含まない | ck -> 短 a | `test_tack_short_a` | `test_tack_short_a` |
| V-20 | `TestSvShortVowel_Vett` | `"vett"` | `ɛ` 含む, `eː` 含まない | ダブル t -> 短 ɛ | `test_vett_short_e` | `test_vett_short_e` |

```go
func TestSvShortVowels(t *testing.T) {
    tests := []struct {
        word    string
        want    string // 含まれるべき IPA
        exclude string // 含まれてはいけない IPA ("" なら不問)
    }{
        {"katt", "a", "ɑː"},
        {"fest", "ɛ", "eː"},
        {"flicka", "ɪ", ""},
        {"kort", "ɔ", ""},
        {"hund", "ɵ", "ʉː"},
        {"mygg", "ʏ", ""},
        {"höst", "œ", ""},
        {"glass", "a", "ɑː"},
        {"tack", "a", "ɑː"},
        {"vett", "ɛ", "eː"},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            ph := svWordPhonemes(tt.word)
            if !strings.Contains(ph, tt.want) {
                t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q", tt.word, ph, tt.want)
            }
            if tt.exclude != "" && strings.Contains(ph, tt.exclude) {
                t.Errorf("svWordPhonemes(%q) = %q, should NOT contain %q", tt.word, ph, tt.exclude)
            }
        })
    }
}
```

### 2.3 子音規則テスト (30テスト): TestSvConsonantRules

3段階の子音変換パターン (3文字 -> 2文字 -> 1文字) を網羅。

#### 3文字パターン (5テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| C-01 | `TestSvConsonant_SKJ` | `"skjorta"` | `ɧ` 含む | skj -> ɧ | `test_skj` | `test_sj_sound_skj` |
| C-02 | `TestSvConsonant_STJ` | `"stjärna"` | `ɧ` 含む | stj -> ɧ | `test_stj` | -- |
| C-03 | `TestSvConsonant_SCH` | `"schema"` | `ɧ` 含む | sch -> ɧ | `test_sch` | -- |
| C-04 | `TestSvConsonant_SNG` | `"sång"` | `s` 含む, `ŋ` 含む | sng -> s + n (ngは別途処理) | -- | -- |
| C-05 | `TestSvConsonant_CKJ` | `"ckj"テスト語` | `ɕ` 含む | ckj -> ɕ | -- | -- |

#### 2文字パターン — sk コンテキスト依存 (7テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| C-06 | `TestSvConsonant_SK_FrontE` | `"sked"` | `ɧ` 含む | sk + e -> ɧ | `test_sk_front_e` | `test_sj_sound_sk_front_vowel` |
| C-07 | `TestSvConsonant_SK_FrontI` | `"skinn"` | `ɧ` 含む | sk + i -> ɧ | `test_sk_front_i` | -- |
| C-08 | `TestSvConsonant_SK_FrontY` | `"sky"` | `ɧ` 含む | sk + y -> ɧ | `test_sk_front_y` | -- |
| C-09 | `TestSvConsonant_SK_FrontAE` | `"skäl"` | `ɧ` 含む | sk + ae -> ɧ | `test_sk_front_ae` | -- |
| C-10 | `TestSvConsonant_SK_FrontOE` | `"sköld"` | `ɧ` 含む | sk + oe -> ɧ | `test_sk_front_oe` | -- |
| C-11 | `TestSvConsonant_SK_BackA` | `"ska"` | `ɧ` 含まない | sk + a -> sk (硬) | `test_sk_back_a` | `test_sk_back_vowel_no_sj` |
| C-12 | `TestSvConsonant_SK_BackO` | `"skog"` | `ɧ` 含まない | sk + o -> sk (硬) | `test_sk_back_o` | -- |

#### 2文字パターン — その他 (10テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| C-13 | `TestSvConsonant_SJ` | `"sjuk"` | `ɧ` 含む | sj -> ɧ | `test_sj_basic` | `test_sj_sound_sj` |
| C-14 | `TestSvConsonant_SH` | `"show"` | `ɧ` 含む | sh -> ɧ | `test_sh` | -- |
| C-15 | `TestSvConsonant_CH_Default` | `"chef"` | `ɧ` 含む | ch -> ɧ (デフォルト) | `test_ch_chef` | `test_ch_loanword_sj_sound` |
| C-16 | `TestSvConsonant_CH_Exception` | `"och"` | `ɧ` 含まない | ch -> k (CH_EXCEPTIONS_K) | `test_ch_och_exception` | `test_ch_exception_och` |
| C-17 | `TestSvConsonant_TJ` | `"tjuv"` | `ɕ` 含む | tj -> ɕ | `test_tj_sound` | `test_tj_sound` |
| C-18 | `TestSvConsonant_KJ` | `"kjol"` | `ɕ` 含む | kj -> ɕ | `test_kj_sound` | -- |
| C-19 | `TestSvConsonant_NG` | `"kung"` | `ŋ` 含む | ng -> ŋ | `test_ng_phoneme` | `test_ng_produces_eng` |
| C-20 | `TestSvConsonant_NK` | `"bank"` | `ŋ` 含む | nk -> ŋ + k | `test_nk_digraph` | -- |
| C-21 | `TestSvConsonant_CK` | `"docka"` | `ɔ` 含む | ck -> k (母音は短) | `test_ck_geminate` | -- |
| C-22 | `TestSvConsonant_PH` | `"photo"` | `f` 含む | ph -> f | `test_ph_as_f` | -- |

#### 1文字パターン + 語頭2文字 (8テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| C-23 | `TestSvConsonant_GJ` | `"gjord"` | `j` 含む, 先頭に `ɡ` 含まない | 語頭 gj -> j | `test_gj_word_initial` | `test_gj_word_initial` |
| C-24 | `TestSvConsonant_DJ` | `"djur"` | 先頭が `ˈj` | 語頭 dj -> j | `test_dj_word_initial` | `test_dj_word_initial` |
| C-25 | `TestSvConsonant_HJ` | `"hjälp"` | 先頭が `ˈj` | 語頭 hj -> j | `test_hj_word_initial` | `test_hj_word_initial` |
| C-26 | `TestSvConsonant_LJ` | `"ljus"` | 先頭が `ˈj` | 語頭 lj -> j | `test_lj_word_initial` | `test_lj_word_initial` |
| C-27 | `TestSvConsonant_C_BeforeE` | `"center"` | 先頭が `ˈs` | c + e -> s | `test_c_before_e` | -- |
| C-28 | `TestSvConsonant_C_BeforeA` | `"camping"` | 先頭が `ˈk` | c + a -> k | `test_c_before_a` | -- |
| C-29 | `TestSvConsonant_GN_Initial` | `"gnaga"` | `ɡ` 含む | 語頭 gn -> ɡ + n | `test_gn_word_initial` | -- |
| C-30 | `TestSvConsonant_GN_Medial` | `"signal"` | `ŋ` 含む | 語中 gn -> ŋ + n | `test_gn_medial` | -- |

```go
func TestSvConsonant3Char(t *testing.T) {
    tests := []struct {
        word string
        want string
        desc string
    }{
        {"skjorta", "ɧ", "skj -> ɧ"},
        {"stjärna", "ɧ", "stj -> ɧ"},
        {"schema", "ɧ", "sch -> ɧ"},
    }
    for _, tt := range tests {
        t.Run(tt.desc, func(t *testing.T) {
            if !svContains(tt.word, tt.want) {
                t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q",
                    tt.word, svWordPhonemes(tt.word), tt.want)
            }
        })
    }
}
```

### 2.4 k/g 軟硬例外テスト (15テスト): TestSvSoftHardKG

#### Soft k/g (デフォルト動作) (4テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| KG-01 | `TestSvSoftK_Kop` | `"köp"` | `ɕ` 含む | k + oe -> ɕ (soft) | `test_k_before_front_vowel_soft` | `test_soft_k_before_front_vowel` |
| KG-02 | `TestSvSoftK_BackVowel` | `"katt"` | 先頭が `ˈk` | k + a -> k (hard, 後舌母音) | `test_k_before_back_vowel_hard` | -- |
| KG-03 | `TestSvSoftG_Gora` | `"göra"` | `j` 含む | g + oe -> j (soft) | `test_g_before_front_vowel_soft` | `test_soft_g_before_front_vowel` |
| KG-04 | `TestSvHardG_BackVowel` | `"gata"` | `ɡ` 含む | g + a -> ɡ (hard, 後舌母音) | `test_g_before_back_vowel_hard` | -- |

#### HARD_K 例外語 (5テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| KG-05 | `TestSvHardK_Flicka` | `"flicka"` | `k` 含む, `ɕ` 含まない | HARD_K_WORDS | `test_hard_k_exception_flicka` | `test_hard_k_exception` (kille) |
| KG-06 | `TestSvHardK_Pojke` | `"pojke"` | `k` 含む | HARD_K_WORDS | `test_hard_k_exception_pojke` | -- |
| KG-07 | `TestSvHardK_Socker` | `"socker"` | `k` 含む | HARD_K_WORDS | `test_hard_k_exception_socker` | -- |
| KG-08 | `TestSvHardK_Kille` | `"kille"` | `k` 含む | HARD_K_WORDS | -- | `test_hard_k_exception` |
| KG-09 | `TestSvHardK_Soker` | `"söker"` | `k` 含む | HARD_K_WORDS | `test_soeker_er_suffix` | -- |

#### HARD_G 例外語 (6テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| KG-10 | `TestSvHardG_Finger` | `"finger"` | `isHardG` が true | HARD_G_WORDS | `test_hard_g_exception_finger` | -- |
| KG-11 | `TestSvHardG_Ger` | `"ger"` | `isHardG` が true | HARD_G_WORDS | `test_hard_g_exception_ger` | -- |
| KG-12 | `TestSvHardG_Ge` | `"ge"` | `ɡ` 含む | HARD_G_WORDS | -- | `test_hard_g_exception` |
| KG-13 | `TestSvHardG_Agera` | `"agera"` | `isHardG` が true | -era verb -> hard g | `test_era_verb_hard_g` | `test_era_verb_hard_g` |
| KG-14 | `TestSvHardG_Berg` | `"berg"` | `isHardG` が true | 語末 -erg -> hard g | `test_berg_hard_g` | `test_berg_hard_g` |
| KG-15 | `TestSvHardG_Borg` | `"borg"` | `isHardG` が true | 語末 -org -> hard g | `test_borg_hard_g` | `test_borg_hard_g` |

### 2.5 レトロフレックス同化テスト (15テスト): TestSvRetroflex

#### 基本5変換 (5テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| RT-01 | `TestSvRetroflex_RT` | `"kort"` | `ʈ` 含む | r+t -> ʈ (U+0288) | `test_r_plus_t`: `"ʈ" in _join("kort")` | `test_retroflex_rt` |
| RT-02 | `TestSvRetroflex_RD` | `"bord"` | `ɖ` 含む | r+d -> ɖ (U+0256) | `test_r_plus_d`: `"ɖ" in _join("bord")` | `test_retroflex_rd` |
| RT-03 | `TestSvRetroflex_RS` | `"fors"` | `ʂ` 含む | r+s -> ʂ (U+0282) | `test_r_plus_s`: `"ʂ" in _join("fors")` | `test_retroflex_rs` |
| RT-04 | `TestSvRetroflex_RN` | `"barn"` | `ɳ` 含む | r+n -> ɳ (U+0273) | `test_r_plus_n`: `"ɳ" in _join("barn")` | -- |
| RT-05 | `TestSvRetroflex_RL` | apply_retroflex `["r","l"]` | `ɭ` 含む | r+l -> ɭ (U+026D) | `test_r_plus_l`: `"ɭ" in apply_retroflex(["r","l"])` | -- |

#### カスケード (3テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| RT-06 | `TestSvRetroflex_Cascade_RST` | apply_retroflex `["f","œ","r","s","t"]` | `== ["f","œ","ʂ","ʈ"]` | r+s -> ʂ, カスケード s+t -> ʈ | `test_cascade_r_s_t`: `== ["f","œ","ʂ","ʈ"]` | `test_retroflex_cascade` |
| RT-07 | `TestSvRetroflex_L_StopsCascade` | apply_retroflex `["k","ɑː","r","l","s"]` | `== ["k","ɑː","ɭ","s"]` | r+l -> ɭ, カスケード停止 | `test_l_stops_cascade`: `== ["k","ɑː","ɭ","s"]` | -- |
| RT-08 | `TestSvRetroflex_Forst` | `"först"` | `ʂ` 含む | カスケード: r+s -> ʂ | (impl-plan 12.2) | -- |

#### ジェミネートブロック (2テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| RT-09 | `TestSvRetroflex_RR_Blocks` | apply_retroflex `["b","ɔ","r","r","s"]` | `== ["b","ɔ","r","r","s"]` | rr ジェミネートが同化をブロック | `test_rr_blocks`: `== ["b","ɔ","r","r","s"]` | -- |
| RT-10 | `TestSvRetroflex_RR_Word` | `"borr"` | `r` が2つ連続 | 単語レベルの rr ブロック | (impl-plan 6.3) | -- |

#### 非レトロフレックス (3テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| RT-11 | `TestSvRetroflex_RK_NoChange` | apply_retroflex `["b","ɑː","r","k"]` | `== ["b","ɑː","r","k"]` | r+k は非対象、変化なし | `test_r_plus_k_no_change`: `== ["b","ɑː","r","k"]` | -- |
| RT-12 | `TestSvRetroflex_WordFinalR` | apply_retroflex `["f","ɑː","r"]` | `== ["f","ɑː","r"]` | 語末 r はそのまま | `test_word_final_r`: `== ["f","ɑː","r"]` | -- |
| RT-13 | `TestSvRetroflex_InBarn` | `"barn"` | `== "ˈbɑːɳ"` | 単語レベルの完全一致 | `test_retroflex_in_barn`: `_join("barn") == "ˈbɑːɳ"` | -- |

#### 単語レベルの完全一致 (2テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| RT-14 | `TestSvRetroflex_InKort` | `"kort"` | `== "ˈkɔʈ"` | kort の完全一致 | `test_retroflex_in_kort`: `_join("kort") == "ˈkɔʈ"` | -- |
| RT-15 | `TestSvRetroflex_Karl` | `"karl"` | `ɭ` 含む | r+l -> ɭ (単語レベル) | (impl-plan 6.3) | -- |

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | テスト実装者 | `swedish_test.go` にヘルパー関数とテーブル駆動テスト ~80件を実装。Python/Rust の期待値と照合 | 1 |
| 2 | 相互検証者 | Python (`pytest`) と Rust (`cargo test`) のテスト結果を Go テストの期待値と突合。不一致があれば仕様を確認 | 1 |

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

- `src/go/phonemize/swedish_test.go` に以下のテスト関数群を追加:
  - `TestSvLongVowels` (10ケース)
  - `TestSvShortVowels` (10ケース)
  - `TestSvConsonant3Char` (5ケース)
  - `TestSvConsonantSK` (7ケース)
  - `TestSvConsonant2Char` (10ケース)
  - `TestSvConsonant1CharAndInitialDigraphs` (8ケース)
  - `TestSvSoftHardK` (5ケース)
  - `TestSvSoftHardG` (6ケース)
  - `TestSvSoftHardKG_Defaults` (4ケース)
  - `TestSvRetroflexBasic` (5ケース)
  - `TestSvRetroflexCascade` (3ケース)
  - `TestSvRetroflexGeminateBlock` (2ケース)
  - `TestSvRetroflexNoChange` (3ケース)
  - `TestSvRetroflexFullWord` (2ケース)
- ヘルパー関数 (`svWordPhonemes`, `svContains`)

### 4.2 テスト項目

全 ~80 テストケースが `go test ./phonemize/ -run Sv -count=1` で PASS すること。

### 4.3 Unitテスト

本チケットのテスト全体が Unit テストとなる。各テスト関数は単一の規則カテゴリをカバーし、テーブル駆動で入力と期待出力のペアを検証する。

### 4.4 E2Eテスト

E2E テストは T-M4-02 の文レベル統合テストでカバーする。本チケットでは単語レベルの規則テストに集中する。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **apply_retroflex のエクスポート**: レトロフレックスのカスケード/ブロックテスト (RT-06~RT-12) は内部関数 `svApplyRetroflex` を直接呼び出す必要がある。同一パッケージ (`phonemize`) 内のテストファイルなのでエクスポートは不要だが、関数シグネチャが Python (`apply_retroflex(List[str]) -> List[str]`) と一致することを確認すること。
2. **PUA マッピング前後の検証**: 長母音テストは PUA 変換後の文字列で検証する場合、PUA コードポイント (例: `\uE05E` for ɑː) を直接比較する必要がある。ヘルパー関数がどの段階の出力を返すか統一すること。
3. **Unicode 正規化**: テスト入力の `ä`, `ö`, `å` が NFC 形式であることを確認。NFD 入力のテストは別途追加を検討。
4. **isHardG/isHardK のテスト方法**: Go ではパッケージ内関数として直接テスト可能 (`_test.go` は同一パッケージ)。Python の `_is_hard_g()` / Rust の `is_hard_g()` と同等の直接テストを含める。

### 5.2 レビューチェックリスト

- [ ] 全 ~80 テストケースが `go test ./phonemize/ -run Sv -count=1` で PASS
- [ ] 既存言語テスト (EN/JA/ZH/ES/FR/PT) に影響なし (`go test ./phonemize/ -count=1`)
- [ ] テストケースの入出力ペアが Python/Rust 参照テストと一致
- [ ] `go vet ./phonemize/...` エラーなし
- [ ] テスト名が Go 命名規約に従っている (`TestSvXxx_YyyZzz`)
- [ ] 各テスト関数に意図を示すコメントまたは description フィールドがある

## 6. 一から作り直すとしたら

テストケースの入出力ペアを JSON/YAML の共有データファイルとして管理し、Python/Rust/Go/C# の全プラットフォームから読み込む方式を検討する。現状は各言語のテストファイルに直接記述しているため、ペア追加時に全ファイルの同期が必要。ただし、言語固有のテストパターン (Go のテーブル駆動、Python の parametrize、Rust の #[test]) への適合コストもあるため、現段階では各言語で直接記述する方針が現実的。

## 7. 後続タスクへの連絡事項

- T-M4-02 ではこのファイルの末尾にストレス/Prosody/PUA/統合テストを追加する。ヘルパー関数 (`svWordPhonemes`, `svContains`) は T-M4-02 でも共用する。
- テストヘルパーの `svWordPhonemes` は `PhonemizeWithProsody` を呼び出すため、M3 の `PhonemizeWithProsody` 実装が前提。M2 の単語レベル G2P だけでテスト可能にする場合は、低レベルヘルパー (`svPhonemizeWord` 等) を直接呼び出すテストも別途用意すること。
- `apply_retroflex` のスライス入出力テスト (RT-06~RT-12) は Go 内部関数 `svApplyRetroflex` を直接呼び出す。この関数のシグネチャは `func svApplyRetroflex(phonemes []string) []string` を想定。
