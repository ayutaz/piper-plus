# T-M4-02: ストレス・Prosody・PUA・統合テスト

## メタ情報

| 項目 | 値 |
|---|---|
| マイルストーン | M4: テストスイート |
| 依存チケット | T-M4-01 (基本規則テスト), T-M3 (後処理 + Phonemizer統合) |
| 後続チケット | T-M5 (マルチリンガル統合 + レジストリ + ドキュメント) |
| 対象ファイル | `src/go/phonemize/swedish_test.go` (T-M4-01 で作成したファイルに追記) |
| 推定行数 | ~700行 (T-M4-01 の ~800行に追加、合計 ~1,500行) |

## 1. タスク目的とゴール

M3 で実装した後処理パイプライン (ストレス検出、Prosody 構築、PUA マッピング) および文レベルの統合テストを ~60 テストケースで検証する。T-M4-01 の基本規則テストと合わせて合計 ~140 テストとなり、M4 マイルストーンの完了基準を満たす。

カバー範囲:
- ストレス検出 (15テスト)
- ローンワード接尾辞 (10テスト)
- "o" 曖昧性 (10テスト)
- Prosody 整合性 (5テスト)
- PUA マッピング (10テスト)
- 文レベル統合テスト (10テスト)

## 2. 実装する内容の詳細

### 2.1 追加ヘルパー関数

T-M4-01 で定義した `svWordPhonemes`, `svContains` に加え、以下のヘルパーを追加する。

```go
// svPhonemizeResult は PhonemizeWithProsody の完全な結果を返す。
func svPhonemizeResult(text string) *PhonemizeResult {
    p := NewSwedishPhonemizer()
    result, _ := p.PhonemizeWithProsody(text)
    return result
}

// svDetectStress はストレス検出関数を直接テストするためのラッパー。
// パッケージ内関数 svDetectStress を直接呼び出す。
func testSvDetectStress(word string) int {
    return svDetectStress(word)
}

// svDetectLoanword はローンワード接尾辞検出を直接テストする。
func testSvDetectLoanword(word string) (stem string, found bool) {
    return svDetectLoanwordSuffix(word)
}
```

### 2.2 ストレス検出テスト (15テスト): TestSvStress

ストレス検出の5段階優先度を検証する。

#### 機能語 (ストレスなし, -1) (3テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| ST-01 | `TestSvStress_FunctionWord_Och` | `"och"` | `detectStress == -1`, `ˈ` 含まない | 機能語はストレスなし | `test_function_word_no_stress`: `detect_stress("och") == -1` | `test_no_stress_function_word` |
| ST-02 | `TestSvStress_FunctionWord_Att` | `"att"` | `detectStress == -1`, `ˈ` 含まない | 機能語 "att" | `test_function_word_att` | -- |
| ST-03 | `TestSvStress_FunctionWord_Det` | `"det"` | `detectStress == -1`, `ˈ` 含まない | 機能語 "det" | `test_function_word_det` | `test_no_stress_function_word` |

#### 単音節 (第1音節, 0) (3テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| ST-04 | `TestSvStress_Monosyllable_Hus` | `"hus"` | `detectStress == 0` | 単音節はデフォルト第1音節 | `test_monosyllable_stressed`: `detect_stress("hus") == 0` | -- |
| ST-05 | `TestSvStress_Monosyllable_Bil` | `"bil"` | `ˈ` 含む | 単音節内容語にストレスマーカー | `test_stressed_monosyllable` | -- |
| ST-06 | `TestSvStress_NoStress_Som` | `"som"` | `ˈ` 含まない | 機能語 "som" | `test_no_stress_in_function_word` | -- |

#### ストレス吸引接尾辞 (4テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| ST-07 | `TestSvStress_Suffix_Tion` | `"station"` | `detectStress > 0` | -tion がストレスを吸引 | `test_tion_suffix_attracts`: `detect_stress("station") > 0` | `test_stress_attracting_suffix` |
| ST-08 | `TestSvStress_Suffix_Eri` | `"bageri"` | `detectStress > 0` | -eri がストレスを吸引 | `test_eri_suffix_attracts`: `detect_stress("bageri") > 0` | -- |
| ST-09 | `TestSvStress_Suffix_Itet` | `"universitet"` | `detectStress > 0` | -itet がストレスを吸引 | `test_universitet_itet_suffix` | -- |
| ST-10 | `TestSvStress_Suffix_Ist` | `"turist"` | `detectStress > 0` | -ist がストレスを吸引 | `test_turist_ist_suffix` | -- |

#### 非ストレスプレフィックス (3テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| ST-11 | `TestSvStress_Prefix_Be` | `"betala"` | `detectStress == 1` | be- プレフィックス | `test_be_prefix_stress_after`: `detect_stress("betala") == 1` | -- |
| ST-12 | `TestSvStress_Prefix_For` | `"förstå"` | `detectStress == 1` | för- プレフィックス | `test_foer_prefix_stress_after`: `detect_stress("förstå") == 1` | -- |
| ST-13 | `TestSvStress_Prefix_Betala_Marker` | `"betala"` | `ˈ` の位置が先頭でない | ストレスマーカーが先頭以外 | `test_unstressed_prefix_be`: `idx > 0` | -- |

#### デフォルト (2テスト)

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| ST-14 | `TestSvStress_Default_Flicka` | `"flicka"` | `detectStress == 0`, `ˈ` が先頭 | デフォルト第1音節 | `test_default_first_syllable`: `detect_stress("flicka") == 0` | `test_stress_default_first_syllable` |
| ST-15 | `TestSvStress_Default_Lampa` | `"lampa"` | `detectStress == 0` | デフォルト第1音節 | `test_multisyllable_default`: `detect_stress("lampa") == 0` | -- |

```go
func TestSvStressFunctionWords(t *testing.T) {
    tests := []struct {
        word string
    }{
        {"och"}, {"att"}, {"det"},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            if s := testSvDetectStress(tt.word); s != -1 {
                t.Errorf("detectStress(%q) = %d, want -1", tt.word, s)
            }
            if strings.Contains(svWordPhonemes(tt.word), "ˈ") {
                t.Errorf("svWordPhonemes(%q) should NOT contain stress marker", tt.word)
            }
        })
    }
}
```

### 2.3 ローンワード接尾辞テスト (10テスト): TestSvLoanwords

7種の接尾辞と AGE_NATIVE 除外を検証する。

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| LW-01 | `TestSvLoanword_Tion` | `"station"` | stem=`"sta"`, found=true, `ɧ` 含む | -tion -> ɧuːn | `test_tion_detected`: `result[0] == "sta"` | `test_loanword_tion` |
| LW-02 | `TestSvLoanword_Sion` | `"passion"` | found=true, `ɧ` 含む | -sion -> ɧuːn | `test_sion_detected`, `test_loanword_sion` | -- |
| LW-03 | `TestSvLoanword_Ssion` | `"mission"` | found=true, `ɧ` 含む | -ssion -> ɧuːn | `test_loanword_ssion` | -- |
| LW-04 | `TestSvLoanword_Age_Garage` | `"garage"` | found=true, `ɧ` 含む | -age -> ɑːɧ | `test_age_detected`, `test_loanword_age` | `test_loanword_age_french` |
| LW-05 | `TestSvLoanword_Age_NativeMage` | `"mage"` | found=false, `ɧ` 含まない | AGE_NATIVE除外 | `test_native_age_excluded`: `result is None` | `test_native_age_not_loanword` |
| LW-06 | `TestSvLoanword_Eur` | `"friseur"` | found=true | -eur -> øːr | -- | -- |
| LW-07 | `TestSvLoanword_Eum` | `"museum"` | found=true | -eum -> eːɵm | `test_eum_suffix` | -- |
| LW-08 | `TestSvLoanword_Ium` | `"stadium"` | found=true, stem=`"stad"` | -ium -> ɪɵm | `test_ium_loanword`: `result[0] == "stad"` | -- |
| LW-09 | `TestSvLoanword_CH_Chef` | `"chef"` | `ɧ` 含む | ch -> ɧ (ローンワード的) | `test_ch_as_sj` | `test_ch_loanword_sj_sound` |
| LW-10 | `TestSvLoanword_TH` | `"theme"` | 先頭が `ˈt` | th -> t | `test_th_as_t` | -- |

```go
func TestSvLoanwordSuffixDetection(t *testing.T) {
    tests := []struct {
        word     string
        wantStem string
        wantOk   bool
    }{
        {"station", "sta", true},
        {"passion", "pas", true},
        {"mission", "mis", true},
        {"garage", "gar", true},
        {"mage", "", false},      // AGE_NATIVE excluded
        {"friseur", "fris", true},
        {"museum", "mus", true},
        {"stadium", "stad", true},
    }
    for _, tt := range tests {
        t.Run(tt.word, func(t *testing.T) {
            stem, ok := testSvDetectLoanword(tt.word)
            if ok != tt.wantOk {
                t.Errorf("detectLoanwordSuffix(%q) found=%v, want %v", tt.word, ok, tt.wantOk)
            }
            if tt.wantOk && stem != tt.wantStem {
                t.Errorf("detectLoanwordSuffix(%q) stem=%q, want %q", tt.word, stem, tt.wantStem)
            }
        })
    }
}
```

### 2.4 "o" 曖昧性テスト (10テスト): TestSvOAmbiguity

"o" の3分岐 (uː デフォルト / oː O_LONG_AS_OO / ɔ 短) を検証する。

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| O-01 | `TestSvO_Sol_LongU` | `"sol"` | `uː` 含む | デフォルト: o -> uː | `test_o_long_u_sol` | `test_o_sol_long_u` |
| O-02 | `TestSvO_Son_LongOO` | `"son"` | `oː` 含む | O_LONG_AS_OO: o -> oː | `test_o_long_oo_son` | `test_o_son_long_oo` |
| O-03 | `TestSvO_Kort_Short` | `"kort"` | `ɔ` 含む | 2子音 -> 短 ɔ | `test_o_short_kort` | `test_o_kort_short` |
| O-04 | `TestSvO_Mor_LongOO` | `"mor"` | `oː` 含む | O_LONG_AS_OO | `test_o_long_oo_mor` | `test_o_mor_long_oo` |
| O-05 | `TestSvO_Bror_LongOO` | `"bror"` | `oː` 含む | O_LONG_AS_OO | `test_o_long_oo_bror` | `test_o_bror_long_oo` |
| O-06 | `TestSvO_Ton_LongOO` | `"ton"` | `oː` 含む | O_LONG_AS_OO | `test_o_long_oo_ton` | `test_o_ton_long_oo` |
| O-07 | `TestSvO_Bok_LongU` | `"bok"` | `uː` 含む | デフォルト (not in O_LONG_AS_OO) | `test_o_long_u_bok` | `test_o_bok_long_u` |
| O-08 | `TestSvO_God_LongOO` | `"god"` | `oː` 含む | O_LONG_AS_OO | `test_o_long_oo_god` | `test_o_god_long_oo` |
| O-09 | `TestSvO_Bott_Short` | `"bott"` | `ɔ` 含む | ダブル t -> 短 ɔ | `test_o_short_bott` | `test_o_bott_short` |
| O-10 | `TestSvO_Ord_Short` | `"ord"` | `ɔ` 含む | o+rd (2子音) -> 短 ɔ (規則ベース) | `test_o_short_ord_rule_based` | -- |

```go
func TestSvOAmbiguity(t *testing.T) {
    tests := []struct {
        word    string
        want    string // 含まれるべき IPA
        exclude string // 含まれてはいけない IPA ("" なら不問)
        desc    string
    }{
        {"sol", "uː", "", "o default -> uː"},
        {"son", "oː", "", "O_LONG_AS_OO -> oː"},
        {"kort", "ɔ", "", "2 consonants -> short ɔ"},
        {"mor", "oː", "", "O_LONG_AS_OO"},
        {"bror", "oː", "", "O_LONG_AS_OO"},
        {"ton", "oː", "", "O_LONG_AS_OO"},
        {"bok", "uː", "oː", "not in O_LONG_AS_OO -> uː"},
        {"god", "oː", "", "O_LONG_AS_OO"},
        {"bott", "ɔ", "", "geminate -> short ɔ"},
        {"ord", "ɔ", "", "o+rd (2C) -> short ɔ"},
    }
    for _, tt := range tests {
        t.Run(tt.word+"_"+tt.desc, func(t *testing.T) {
            ph := svWordPhonemes(tt.word)
            if !strings.Contains(ph, tt.want) {
                t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q (%s)",
                    tt.word, ph, tt.want, tt.desc)
            }
            if tt.exclude != "" && strings.Contains(ph, tt.exclude) {
                t.Errorf("svWordPhonemes(%q) = %q, should NOT contain %q (%s)",
                    tt.word, ph, tt.exclude, tt.desc)
            }
        })
    }
}
```

### 2.5 Prosody 整合性テスト (5テスト): TestSvProsody

Prosody 出力 (A1/A2/A3) の構造的整合性を検証する。

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| PR-01 | `TestSvProsody_LengthMatch` | `"flicka"` | `len(Tokens) == len(Prosody)` | Tokens と Prosody の長さが一致 | `test_prosody_length_match` | `test_prosody_length_matches_phonemes` |
| PR-02 | `TestSvProsody_StressA2` | `"flicka"` | ˈ の Prosody で A2==2 | ストレスマーカーの A2 は 2 | `test_stress_marker_a2`: `pr.a2 == 2` | `test_prosody_stress_a2` |
| PR-03 | `TestSvProsody_A1AlwaysZero` | `"flickan gick"` | 全 Prosody で A1==0 | SV では A1 は常に 0 | `test_a1_always_zero` | -- |
| PR-04 | `TestSvProsody_A3WordPhonemeCount` | `"hus"` | A3 >= 3 (h, ʉː, s) | A3 は単語内の音素数 | `test_a3_word_phoneme_count`: `pr.a3 >= 3` | -- |
| PR-05 | `TestSvProsody_MultiWord` | `"hej världen"` | `len(Tokens) == len(Prosody)` | 複数単語でも整合 | -- | `test_prosody_length_matches_phonemes` (hej varlden) |

```go
func TestSvProsody(t *testing.T) {
    t.Run("LengthMatch", func(t *testing.T) {
        r := svPhonemizeResult("flicka")
        if len(r.Tokens) != len(r.Prosody) {
            t.Errorf("len(Tokens)=%d != len(Prosody)=%d for 'flicka'",
                len(r.Tokens), len(r.Prosody))
        }
    })

    t.Run("StressA2", func(t *testing.T) {
        r := svPhonemizeResult("flicka")
        for i, tok := range r.Tokens {
            if tok == "ˈ" {
                if r.Prosody[i].A2 != 2 {
                    t.Errorf("stress marker at %d has A2=%d, want 2", i, r.Prosody[i].A2)
                }
            }
        }
    })

    t.Run("A1AlwaysZero", func(t *testing.T) {
        r := svPhonemizeResult("flickan gick")
        for i, pr := range r.Prosody {
            if pr.A1 != 0 {
                t.Errorf("Prosody[%d].A1=%d, want 0 for SV", i, pr.A1)
            }
        }
    })

    t.Run("A3WordPhonemeCount", func(t *testing.T) {
        r := svPhonemizeResult("hus")
        for _, pr := range r.Prosody {
            if pr.A3 > 0 && pr.A3 < 3 {
                t.Errorf("Prosody.A3=%d, expected >= 3 for 'hus' (h, ʉː, s)", pr.A3)
            }
        }
    })

    t.Run("MultiWord", func(t *testing.T) {
        r := svPhonemizeResult("hej världen")
        if len(r.Tokens) != len(r.Prosody) {
            t.Errorf("len(Tokens)=%d != len(Prosody)=%d for 'hej världen'",
                len(r.Tokens), len(r.Prosody))
        }
    })
}
```

### 2.6 PUA マッピングテスト (10テスト): TestSvPUA

9 長母音の PUA 変換と MapSequence 統合を検証する。

| # | テスト名 | 入力 | 期待PUA | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|--------|---------|-----------|---------|
| PUA-01 | `TestSvPUA_LongI` | `"fin"` | `\uE059` (iː) | iː -> PUA 0xE059 | (M1.2 test) | `test_long_vowel_pua_mapping` 類 |
| PUA-02 | `TestSvPUA_LongY` | `"syn"` | `\uE05A` (yː) | yː -> PUA 0xE05A | (M1.2 test) | -- |
| PUA-03 | `TestSvPUA_LongE` | `"vet"` | `\uE05B` (eː) | eː -> PUA 0xE05B | (M1.2 test) | -- |
| PUA-04 | `TestSvPUA_LongAE` | `"säl"` | `\uE05C` (ɛː) | ɛː -> PUA 0xE05C | (M1.2 test) | -- |
| PUA-05 | `TestSvPUA_LongOE` | `"öl"` | `\uE05D` (øː) | øː -> PUA 0xE05D | (M1.2 test) | -- |
| PUA-06 | `TestSvPUA_LongA` | `"gata"` | `\uE05E` (ɑː) | ɑː -> PUA 0xE05E | (M1.2 test) | `test_long_vowel_single_consonant` |
| PUA-07 | `TestSvPUA_LongAA` | `"år"` | `\uE05F` (oː) | oː -> PUA 0xE05F (å) | (M1.2 test) | -- |
| PUA-08 | `TestSvPUA_LongO_Default` | `"sol"` | `\uE060` (uː) | uː -> PUA 0xE060 (o default) | (M1.2 test) | `test_long_vowel_pua_mapping` |
| PUA-09 | `TestSvPUA_LongU` | `"hus"` | `\uE061` (ʉː) | ʉː -> PUA 0xE061 | (M1.2 test) | -- |
| PUA-10 | `TestSvPUA_OLongAsOO` | `"son"` | `\uE05F` (oː) | O_LONG_AS_OO -> PUA 0xE05F | (M1.2 test) | `test_o_long_as_oo` |

```go
func TestSvPUAMapping(t *testing.T) {
    tests := []struct {
        word    string
        wantPUA rune
        desc    string
    }{
        {"fin", 0xE059, "iː -> PUA"},
        {"syn", 0xE05A, "yː -> PUA"},
        {"vet", 0xE05B, "eː -> PUA"},
        {"säl", 0xE05C, "ɛː -> PUA"},
        {"öl", 0xE05D, "øː -> PUA"},
        {"gata", 0xE05E, "ɑː -> PUA"},
        {"år", 0xE05F, "oː -> PUA (å)"},
        {"sol", 0xE060, "uː -> PUA (o default)"},
        {"hus", 0xE061, "ʉː -> PUA"},
        {"son", 0xE05F, "oː -> PUA (O_LONG_AS_OO)"},
    }
    for _, tt := range tests {
        t.Run(tt.desc, func(t *testing.T) {
            r := svPhonemizeResult(tt.word)
            joined := strings.Join(r.Tokens, "")
            if !strings.ContainsRune(joined, tt.wantPUA) {
                t.Errorf("PhonemizeWithProsody(%q) tokens=%v, expected PUA U+%04X (%s)",
                    tt.word, r.Tokens, tt.wantPUA, tt.desc)
            }
        })
    }
}
```

### 2.7 文レベル統合テスト (10テスト): TestSvIntegration

複数単語の文、句読点、EOS 追跡を含む E2E テスト。

| # | テスト名 | 入力 | 期待出力 | 検証内容 | Python参照 | Rust参照 |
|---|---------|------|---------|---------|-----------|---------|
| INT-01 | `TestSvIntegration_Punctuation` | `"hej!"` | `!` 含む | 句読点がパススルー | `test_punctuation_passthrough` | `test_punctuation_preserved` |
| INT-02 | `TestSvIntegration_MultiWord` | `"hej du"` | 空白 ` ` 含む | 複数単語の間にスペース | `test_multiple_words` | `test_space_between_words` |
| INT-03 | `TestSvIntegration_EmptyString` | `""` | Tokens が空 | 空入力のエラーなし | `test_empty_string` | `test_empty_text` |
| INT-04 | `TestSvIntegration_Uppercase` | `"HEJ"` | `svWordPhonemes("hej")` と一致 | 大文字の正規化 | -- | `test_uppercase_normalized` |
| INT-05 | `TestSvIntegration_SkedFullOutput` | `"sked"` | `ˈɧeːd` の構成要素含む | 単語レベルの完全パイプライン | Python: `_join("sked") == "ˈɧeːd"` | `test_sj_sound_sk_front_vowel` |
| INT-06 | `TestSvIntegration_Question` | `"är det sant?"` | EOS = `?` | EOS追跡が疑問符を捕捉 | -- | -- |
| INT-07 | `TestSvIntegration_Period` | `"jag går hem."` | EOS = `$` (または `.`) | EOS追跡がピリオドを捕捉 | -- | -- |
| INT-08 | `TestSvIntegration_Exclamation` | `"stopp!"` | EOS = `!` | EOS追跡が感嘆符を捕捉 | -- | -- |
| INT-09 | `TestSvIntegration_LanguageCode` | -- | `LanguageCode() == "sv"` | インターフェース準拠 | -- | `test_language_code` |
| INT-10 | `TestSvIntegration_MixedSentence` | `"flickan och katten"` | `ˈ` が2回以上, 空白含む | 内容語にストレス、機能語になし | -- | -- |

```go
func TestSvIntegration(t *testing.T) {
    p := NewSwedishPhonemizer()

    t.Run("Punctuation", func(t *testing.T) {
        r, _ := p.PhonemizeWithProsody("hej!")
        joined := strings.Join(r.Tokens, "")
        if !strings.Contains(joined, "!") {
            t.Errorf("'hej!' should preserve '!': tokens=%v", r.Tokens)
        }
    })

    t.Run("MultiWord", func(t *testing.T) {
        r, _ := p.PhonemizeWithProsody("hej du")
        joined := strings.Join(r.Tokens, "")
        if !strings.Contains(joined, " ") {
            t.Errorf("'hej du' should contain space: tokens=%v", r.Tokens)
        }
    })

    t.Run("EmptyString", func(t *testing.T) {
        r, _ := p.PhonemizeWithProsody("")
        if len(r.Tokens) != 0 {
            t.Errorf("empty input should produce empty tokens, got %v", r.Tokens)
        }
    })

    t.Run("Uppercase", func(t *testing.T) {
        upper := svWordPhonemes("HEJ")
        lower := svWordPhonemes("hej")
        if upper != lower {
            t.Errorf("uppercase 'HEJ' -> %q != lowercase 'hej' -> %q", upper, lower)
        }
    })

    t.Run("LanguageCode", func(t *testing.T) {
        if code := p.LanguageCode(); code != "sv" {
            t.Errorf("LanguageCode() = %q, want 'sv'", code)
        }
    })

    t.Run("MixedSentence", func(t *testing.T) {
        r, _ := p.PhonemizeWithProsody("flickan och katten")
        joined := strings.Join(r.Tokens, "")
        stressCount := strings.Count(joined, "ˈ")
        if stressCount < 2 {
            t.Errorf("'flickan och katten': expected >= 2 stress markers, got %d in %q",
                stressCount, joined)
        }
        if !strings.Contains(joined, " ") {
            t.Errorf("'flickan och katten' should contain spaces: %q", joined)
        }
    })
}
```

## 3. エージェントチームの役割と人数

| # | 役割 | 担当内容 | 人数 |
|---|------|---------|------|
| 1 | テスト実装者 | T-M4-01 の `swedish_test.go` にストレス/Prosody/PUA/統合テスト ~60件を追記 | 1 |
| 2 | CI検証者 | `go test ./phonemize/ -run Sv -count=1` で全 ~140テスト (T-M4-01 + T-M4-02) が PASS すること、既存言語テストへの非影響を確認 | 1 |

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

- `src/go/phonemize/swedish_test.go` に以下のテスト関数群を追加:
  - `TestSvStressFunctionWords` (3ケース)
  - `TestSvStressMonosyllable` (3ケース)
  - `TestSvStressAttractingSuffix` (4ケース)
  - `TestSvStressUnstressedPrefix` (3ケース)
  - `TestSvStressDefault` (2ケース)
  - `TestSvLoanwordSuffixDetection` (8ケース)
  - `TestSvLoanwordPhonemes` (2ケース)
  - `TestSvOAmbiguity` (10ケース)
  - `TestSvProsody` (5サブテスト)
  - `TestSvPUAMapping` (10ケース)
  - `TestSvIntegration` (10サブテスト)
- 追加ヘルパー関数 (`svPhonemizeResult`, `testSvDetectStress`, `testSvDetectLoanword`)

### 4.2 テスト項目

T-M4-01 と合わせて全 ~140 テストケースが `go test ./phonemize/ -run Sv -count=1` で PASS すること。

### 4.3 Unitテスト

ストレス検出 (15テスト)、ローンワード接尾辞 (10テスト)、"o" 曖昧性 (10テスト)、PUA マッピング (10テスト) は全て Unit テスト。

### 4.4 E2Eテスト

文レベル統合テスト (10テスト) が E2E テストとして機能する。`PhonemizeWithProsody` の全パイプライン (正規化 -> トークン化 -> G2P -> レトロフレックス -> ストレス -> PUA -> Result) を通しで検証する。Prosody 整合性テスト (5テスト) も構造的な E2E 検証。

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

1. **PhonemizeResult 構造体の Prosody フィールド**: Go の `PhonemizeResult` 構造体の Prosody フィールドの型 (例: `[]ProsodyInfo` or `[]*ProsodyInfo`) が確定していること。Python では `namedtuple(a1, a2, a3)`、Rust では `Option<ProsodyInfo>` を使用。Go ではポインタまたは構造体値のスライスを想定。
2. **EOS トークンのアクセス方法**: `PhonemizeResult.EOSToken` が設計通り公開されているか。統合テスト INT-06~INT-08 は EOS 追跡に依存する。
3. **ストレス検出関数の直接テスト**: `svDetectStress` はパッケージ非公開関数の可能性がある。`_test.go` ファイルは同一パッケージなので直接呼び出し可能だが、関数名の正確な一致を確認すること。
4. **MapSequence 後の PUA 検証**: PUA テストでは `MapSequence()` 適用済みのトークン列を検証する。`PhonemizeWithProsody` が内部で `MapSequence()` を呼び出す前提。もし未呼び出しの場合は IPA 文字列 (例: `"ɑː"`) のままとなり、PUA コードポイント検証が失敗する。

### 5.2 レビューチェックリスト

- [ ] T-M4-01 + T-M4-02 合わせて ~140 テストが `go test ./phonemize/ -run Sv -count=1` で PASS
- [ ] 既存言語テスト (EN/JA/ZH/ES/FR/PT) に影響なし (`go test ./phonemize/ -count=1`)
- [ ] `go vet ./phonemize/...` エラーなし
- [ ] テストケースの入出力ペアが Python/Rust 参照テストと一致 (特にストレス検出値、PUA コードポイント)
- [ ] Prosody テストが A1=0, A2=0/2, A3=音素数 の SV 仕様に準拠
- [ ] PUA テストが 0xE059-0xE061 の9エントリ全てをカバー
- [ ] 統合テストが空入力、大文字入力、句読点、複数単語を含む
- [ ] 全テスト関数名が Go 命名規約に従っている

## 6. 一から作り直すとしたら

Prosody テストは Python の `phonemize_swedish_with_prosody` と完全に同じ JSON 出力を比較する方式が理想的。現状は A1/A2/A3 の値を個別に検証しているが、JSON 形式で期待出力を定義し、構造体全体を比較する方が堅牢。また、PUA テストは Phenemizer の内部実装ではなく、最終的な phoneme_ids 列 (ID マップ適用後) で検証する方が実用に近い。ただし、ID マップは M5 で統合されるため、M4 の段階では IPA/PUA レベルの検証が妥当。

## 7. 後続タスクへの連絡事項

- T-M5 (マルチリンガル統合) では `unicode_detect_test.go` に SV 言語検出テスト (5-10ケース)、`multilingual_test.go` に SV 混在テスト (3-5ケース) を追加する。これらは本チケットのスコープ外。
- M4 完了基準: T-M4-01 (~80テスト) + T-M4-02 (~60テスト) = ~140テスト全 PASS、`go vet` / `golangci-lint` エラーなし、他言語テスト非影響。
- `swedish_test.go` の最終行数は ~1,500行を見込む。既存の `french_test.go` (~400行) や `spanish_test.go` (~500行) より大きいが、SV の規則数 (10例外語リスト、3状態レトロフレックス等) に比例しており妥当。
- 統合テストの EOS 追跡 (INT-06~INT-08) は `PhonemizeResult.EOSToken` フィールドに依存する。M3 で EOSToken の設計が変わった場合はテストを更新すること。
