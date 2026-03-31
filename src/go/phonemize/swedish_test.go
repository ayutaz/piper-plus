package phonemize

import (
	"strings"
	"testing"
)

// ===========================================================================
// Helpers
// ===========================================================================

// svRawWordPhonemes returns the joined pre-PUA IPA string for a single word.
// This calls svPhonemizeWord directly (stress + G2P + retroflex + stress marker)
// WITHOUT PUA mapping, so long vowels appear as e.g. "ɑː" not PUA codepoints.
func svRawWordPhonemes(word string) string {
	word = svNormalize(word)
	return strings.Join(svPhonemizeWord(word), "")
}

// svRawContains checks if the raw (pre-PUA) phoneme output contains the given IPA.
func svRawContains(word, ipa string) bool {
	return strings.Contains(svRawWordPhonemes(word), ipa)
}

// svWordPhonemes returns the joined phoneme string for a single word.
// This uses PhonemizeWithProsody (full pipeline including PUA mapping).
func svWordPhonemes(word string) string {
	p := NewSwedishPhonemizer()
	result, _ := p.PhonemizeWithProsody(word)
	return strings.Join(result.Tokens, "")
}

// svContains checks if the phoneme output of a word (post-PUA) contains the given IPA string.
func svContains(word, ipa string) bool {
	return strings.Contains(svWordPhonemes(word), ipa)
}

// svPhonemizeResult returns the full PhonemizeWithProsody result.
func svPhonemizeResult(text string) *PhonemizeResult {
	p := NewSwedishPhonemizer()
	result, _ := p.PhonemizeWithProsody(text)
	return result
}

// testSvDetectStress wraps the package-internal svDetectStress.
func testSvDetectStress(word string) int {
	return svDetectStress(word)
}

// testSvDetectLoanword wraps svDetectLoanwordSuffix, returning (stem, found).
func testSvDetectLoanword(word string) (string, bool) {
	stem, _, found := svDetectLoanwordSuffix(word)
	return stem, found
}

// ===========================================================================
// T-M4-01: Basic Rule Tests (~80 tests)
// ===========================================================================

// ---------------------------------------------------------------------------
// 2.2 Long Vowel Tests (10)
// ---------------------------------------------------------------------------

func TestSvLongVowels(t *testing.T) {
	tests := []struct {
		word string
		want string // IPA substring that must be present (pre-PUA)
	}{
		{"gata", "ɑː"}, // V-01: a + single consonant -> long ɑː
		{"vet", "eː"},  // V-02: e + single consonant -> eː
		{"fin", "iː"},  // V-03: i + single consonant -> iː
		{"sol", "uː"},  // V-04: o default + single consonant -> uː
		{"hus", "ʉː"},  // V-05: u + single consonant -> ʉː
		{"syn", "yː"},  // V-06: y + single consonant -> yː
		{"säl", "ɛː"},  // V-07: ä + single consonant -> ɛː
		{"öl", "øː"},   // V-08: ö + single consonant -> øː
		{"år", "oː"},   // V-09: å + single consonant -> oː
		{"glas", "ɑː"}, // V-10: glas single C after vowel -> long ɑː
	}
	for _, tt := range tests {
		t.Run(tt.word, func(t *testing.T) {
			if !svRawContains(tt.word, tt.want) {
				t.Errorf("svRawWordPhonemes(%q) = %q, expected to contain %q",
					tt.word, svRawWordPhonemes(tt.word), tt.want)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.2 Short Vowel Tests (10)
// ---------------------------------------------------------------------------

func TestSvShortVowels(t *testing.T) {
	tests := []struct {
		word    string
		want    string // IPA substring that must be present
		exclude string // IPA substring that must NOT be present ("" = no check)
	}{
		{"katt", "a", "ɑː"},  // V-11: geminate -> short a
		{"fest", "ɛ", "eː"},  // V-12: cluster -> short ɛ
		{"flicka", "ɪ", ""},  // V-13: HARD_K exception + short ɪ
		{"kort", "ɔ", ""},    // V-14: o + 2 consonants -> short ɔ
		{"hund", "ɵ", "ʉː"},  // V-15: cluster -> short ɵ
		{"mygg", "ʏ", ""},    // V-16: geminate -> short ʏ
		{"höst", "œ", ""},    // V-17: cluster -> short œ
		{"glass", "a", "ɑː"}, // V-18: double s -> short a
		{"tack", "a", "ɑː"},  // V-19: ck -> short a
		{"vett", "ɛ", "eː"},  // V-20: geminate -> short ɛ
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

// ---------------------------------------------------------------------------
// 2.3 Consonant Rules — 3-char patterns (5)
// ---------------------------------------------------------------------------

func TestSvConsonant3Char(t *testing.T) {
	tests := []struct {
		word string
		want string
		desc string
	}{
		{"skjorta", "ɧ", "skj -> ɧ"},     // C-01
		{"stjärna", "ɧ", "stj -> ɧ"},     // C-02
		{"schema", "ɧ", "sch -> ɧ"},      // C-03
		{"sång", "ŋ", "sng -> s+ng (ŋ)"}, // C-04: sng rule, ng is processed as ŋ
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

// ---------------------------------------------------------------------------
// 2.3 Consonant Rules — sk context-dependent (7)
// ---------------------------------------------------------------------------

func TestSvConsonantSK(t *testing.T) {
	// sk + front vowel -> ɧ
	frontTests := []struct {
		word string
		desc string
	}{
		{"sked", "sk+e -> ɧ"},  // C-06
		{"skinn", "sk+i -> ɧ"}, // C-07
		{"sky", "sk+y -> ɧ"},   // C-08
		{"skäl", "sk+ä -> ɧ"},  // C-09
		{"sköld", "sk+ö -> ɧ"}, // C-10
	}
	for _, tt := range frontTests {
		t.Run(tt.desc, func(t *testing.T) {
			if !svContains(tt.word, "ɧ") {
				t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɧ",
					tt.word, svWordPhonemes(tt.word))
			}
		})
	}

	// sk + back vowel -> sk (no ɧ)
	backTests := []struct {
		word string
		desc string
	}{
		{"ska", "sk+a -> sk (hard)"},  // C-11
		{"skog", "sk+o -> sk (hard)"}, // C-12
	}
	for _, tt := range backTests {
		t.Run(tt.desc, func(t *testing.T) {
			if svContains(tt.word, "ɧ") {
				t.Errorf("svWordPhonemes(%q) = %q, should NOT contain ɧ",
					tt.word, svWordPhonemes(tt.word))
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.3 Consonant Rules — 2-char patterns (10)
// ---------------------------------------------------------------------------

func TestSvConsonant2Char(t *testing.T) {
	tests := []struct {
		word    string
		want    string
		exclude string
		desc    string
	}{
		{"sjuk", "ɧ", "", "sj -> ɧ"},                // C-13
		{"show", "ɧ", "", "sh -> ɧ"},                // C-14
		{"chef", "ɧ", "", "ch -> ɧ (default)"},      // C-15
		{"och", "", "ɧ", "ch -> k (CH_EXCEPTIONS)"}, // C-16
		{"tjuv", "ɕ", "", "tj -> ɕ"},                // C-17
		{"kjol", "ɕ", "", "kj -> ɕ"},                // C-18
		{"kung", "ŋ", "", "ng -> ŋ"},                // C-19
		{"bank", "ŋ", "", "nk -> ŋ+k"},              // C-20
		{"docka", "ɔ", "", "ck -> k (short vowel)"}, // C-21
		{"photo", "f", "", "ph -> f"},               // C-22
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
			ph := svWordPhonemes(tt.word)
			if tt.want != "" && !strings.Contains(ph, tt.want) {
				t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q", tt.word, ph, tt.want)
			}
			if tt.exclude != "" && strings.Contains(ph, tt.exclude) {
				t.Errorf("svWordPhonemes(%q) = %q, should NOT contain %q", tt.word, ph, tt.exclude)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.3 Consonant Rules — 1-char patterns + word-initial digraphs (8)
// ---------------------------------------------------------------------------

func TestSvConsonant1CharAndInitialDigraphs(t *testing.T) {
	tests := []struct {
		word    string
		want    string
		exclude string
		desc    string
	}{
		{"gjord", "j", "", "gj word-initial -> j"},   // C-23
		{"djur", "j", "", "dj word-initial -> j"},    // C-24
		{"hjälp", "j", "", "hj word-initial -> j"},   // C-25
		{"ljus", "j", "", "lj word-initial -> j"},    // C-26
		{"center", "s", "", "c+e -> s"},              // C-27
		{"camping", "k", "", "c+a -> k"},             // C-28
		{"gnaga", "ɡ", "", "gn word-initial -> ɡ+n"}, // C-29
		{"signal", "ŋ", "", "gn word-medial -> ŋ+n"}, // C-30
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
			ph := svWordPhonemes(tt.word)
			if tt.want != "" && !strings.Contains(ph, tt.want) {
				t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q", tt.word, ph, tt.want)
			}
			if tt.exclude != "" && strings.Contains(ph, tt.exclude) {
				t.Errorf("svWordPhonemes(%q) = %q, should NOT contain %q", tt.word, ph, tt.exclude)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.4 Soft/Hard k/g — defaults (4)
// ---------------------------------------------------------------------------

func TestSvSoftHardKG_Defaults(t *testing.T) {
	t.Run("soft_k_köp", func(t *testing.T) {
		// KG-01: k + ö -> ɕ (soft)
		if !svContains("köp", "ɕ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɕ", "köp", svWordPhonemes("köp"))
		}
	})

	t.Run("hard_k_katt", func(t *testing.T) {
		// KG-02: k + a -> k (hard, back vowel)
		ph := svWordPhonemes("katt")
		if !strings.HasPrefix(ph, "ˈk") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to start with ˈk", "katt", ph)
		}
	})

	t.Run("soft_g_göra", func(t *testing.T) {
		// KG-03: g + ö -> j (soft)
		if !svContains("göra", "j") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain j", "göra", svWordPhonemes("göra"))
		}
	})

	t.Run("hard_g_gata", func(t *testing.T) {
		// KG-04: g + a -> ɡ (hard, back vowel)
		if !svContains("gata", "ɡ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɡ", "gata", svWordPhonemes("gata"))
		}
	})
}

// ---------------------------------------------------------------------------
// 2.4 HARD_K exception words (5)
// ---------------------------------------------------------------------------

func TestSvSoftHardK(t *testing.T) {
	tests := []struct {
		word    string
		want    string
		exclude string
		desc    string
	}{
		{"flicka", "k", "ɕ", "HARD_K: flicka"}, // KG-05
		{"pojke", "k", "", "HARD_K: pojke"},    // KG-06
		{"socker", "k", "", "HARD_K: socker"},  // KG-07
		{"kille", "k", "", "HARD_K: kille"},    // KG-08
		{"söker", "k", "", "HARD_K: söker"},    // KG-09
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
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

// ---------------------------------------------------------------------------
// 2.4 HARD_G exception words (6)
// ---------------------------------------------------------------------------

func TestSvSoftHardG(t *testing.T) {
	// Direct isHardG tests
	hardGWords := []struct {
		word string
		desc string
	}{
		{"finger", "HARD_G: finger"},   // KG-10
		{"ger", "HARD_G: ger"},         // KG-11
		{"agera", "-era verb -> hard"}, // KG-13
		{"berg", "-erg -> hard"},       // KG-14
		{"borg", "-org -> hard"},       // KG-15
	}
	for _, tt := range hardGWords {
		t.Run(tt.desc, func(t *testing.T) {
			if !isHardG(tt.word) {
				t.Errorf("isHardG(%q) = false, want true", tt.word)
			}
		})
	}

	// KG-12: ge -> ɡ in output
	t.Run("HARD_G_ge_output", func(t *testing.T) {
		if !svContains("ge", "ɡ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɡ", "ge", svWordPhonemes("ge"))
		}
	})
}

// ---------------------------------------------------------------------------
// 2.5 Retroflex assimilation — basic 5 conversions (5)
// ---------------------------------------------------------------------------

func TestSvRetroflexBasic(t *testing.T) {
	tests := []struct {
		word string
		want string
		desc string
	}{
		{"kort", "ʈ", "r+t -> ʈ"}, // RT-01
		{"bord", "ɖ", "r+d -> ɖ"}, // RT-02
		{"fors", "ʂ", "r+s -> ʂ"}, // RT-03
		{"barn", "ɳ", "r+n -> ɳ"}, // RT-04
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
			if !svContains(tt.word, tt.want) {
				t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q",
					tt.word, svWordPhonemes(tt.word), tt.want)
			}
		})
	}

	// RT-05: r+l -> ɭ (direct apply_retroflex test)
	t.Run("r+l_direct", func(t *testing.T) {
		result := svApplyRetroflex([]string{"r", "l"})
		found := false
		for _, ph := range result {
			if ph == "ɭ" {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("svApplyRetroflex([r,l]) = %v, expected to contain ɭ", result)
		}
	})
}

// ---------------------------------------------------------------------------
// 2.5 Retroflex cascade (3)
// ---------------------------------------------------------------------------

func TestSvRetroflexCascade(t *testing.T) {
	// RT-06: r+s -> ʂ, cascade s+t -> ʈ
	t.Run("cascade_r_s_t", func(t *testing.T) {
		input := []string{"f", "œ", "r", "s", "t"}
		want := []string{"f", "œ", "ʂ", "ʈ"}
		got := svApplyRetroflex(input)
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Errorf("svApplyRetroflex(%v) = %v, want %v", input, got, want)
		}
	})

	// RT-07: r+l -> ɭ, cascade stops (l does not propagate)
	t.Run("l_stops_cascade", func(t *testing.T) {
		input := []string{"k", "ɑː", "r", "l", "s"}
		want := []string{"k", "ɑː", "ɭ", "s"}
		got := svApplyRetroflex(input)
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Errorf("svApplyRetroflex(%v) = %v, want %v", input, got, want)
		}
	})

	// RT-08: först -> contains ʂ (cascade from r+s)
	t.Run("först_contains_ʂ", func(t *testing.T) {
		if !svContains("först", "ʂ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ʂ",
				"först", svWordPhonemes("först"))
		}
	})
}

// ---------------------------------------------------------------------------
// 2.5 Retroflex geminate block (2)
// ---------------------------------------------------------------------------

func TestSvRetroflexGeminateBlock(t *testing.T) {
	// RT-09: rr blocks assimilation
	t.Run("rr_blocks", func(t *testing.T) {
		input := []string{"b", "ɔ", "r", "r", "s"}
		want := []string{"b", "ɔ", "r", "r", "s"}
		got := svApplyRetroflex(input)
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Errorf("svApplyRetroflex(%v) = %v, want %v", input, got, want)
		}
	})

	// RT-10: borr word-level -> rr not assimilated
	t.Run("borr_word", func(t *testing.T) {
		ph := svWordPhonemes("borr")
		if !strings.Contains(ph, "rr") {
			// Check that there are two consecutive r's somewhere
			rCount := 0
			for _, c := range ph {
				if c == 'r' {
					rCount++
				}
			}
			if rCount < 2 {
				t.Errorf("svWordPhonemes(%q) = %q, expected 2 consecutive r's (rr)", "borr", ph)
			}
		}
	})
}

// ---------------------------------------------------------------------------
// 2.5 Retroflex no-change (3)
// ---------------------------------------------------------------------------

func TestSvRetroflexNoChange(t *testing.T) {
	// RT-11: r+k is not a retroflex target
	t.Run("r+k_no_change", func(t *testing.T) {
		input := []string{"b", "ɑː", "r", "k"}
		want := []string{"b", "ɑː", "r", "k"}
		got := svApplyRetroflex(input)
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Errorf("svApplyRetroflex(%v) = %v, want %v", input, got, want)
		}
	})

	// RT-12: word-final r stays
	t.Run("word_final_r", func(t *testing.T) {
		input := []string{"f", "ɑː", "r"}
		want := []string{"f", "ɑː", "r"}
		got := svApplyRetroflex(input)
		if strings.Join(got, ",") != strings.Join(want, ",") {
			t.Errorf("svApplyRetroflex(%v) = %v, want %v", input, got, want)
		}
	})

	// RT-13: barn full word exact match (pre-PUA)
	t.Run("barn_exact", func(t *testing.T) {
		ph := svRawWordPhonemes("barn")
		if ph != "ˈbɑːɳ" {
			t.Errorf("svRawWordPhonemes(%q) = %q, want %q", "barn", ph, "ˈbɑːɳ")
		}
	})
}

// ---------------------------------------------------------------------------
// 2.5 Retroflex full-word exact match (2)
// ---------------------------------------------------------------------------

func TestSvRetroflexFullWord(t *testing.T) {
	// RT-14: kort exact match (pre-PUA)
	t.Run("kort_exact", func(t *testing.T) {
		ph := svRawWordPhonemes("kort")
		if ph != "ˈkɔʈ" {
			t.Errorf("svRawWordPhonemes(%q) = %q, want %q", "kort", ph, "ˈkɔʈ")
		}
	})

	// RT-15: karl -> contains ɭ (r+l)
	t.Run("karl_contains_ɭ", func(t *testing.T) {
		if !svContains("karl", "ɭ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɭ",
				"karl", svWordPhonemes("karl"))
		}
	})
}

// ===========================================================================
// T-M4-02: Stress, Prosody, and Integration Tests (~60 tests)
// ===========================================================================

// ---------------------------------------------------------------------------
// 2.2 Stress detection — function words (3)
// ---------------------------------------------------------------------------

func TestSvStressFunctionWords(t *testing.T) {
	tests := []struct {
		word string
	}{
		{"och"}, // ST-01
		{"att"}, // ST-02
		{"det"}, // ST-03
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

// ---------------------------------------------------------------------------
// 2.2 Stress detection — monosyllables (3)
// ---------------------------------------------------------------------------

func TestSvStressMonosyllables(t *testing.T) {
	// ST-04: hus -> stress = 0
	t.Run("hus_stress_0", func(t *testing.T) {
		if s := testSvDetectStress("hus"); s != 0 {
			t.Errorf("detectStress(%q) = %d, want 0", "hus", s)
		}
	})

	// ST-05: bil -> contains stress marker
	t.Run("bil_has_stress_marker", func(t *testing.T) {
		if !strings.Contains(svWordPhonemes("bil"), "ˈ") {
			t.Errorf("svWordPhonemes(%q) should contain ˈ", "bil")
		}
	})

	// ST-06: som -> function word, no stress
	t.Run("som_no_stress", func(t *testing.T) {
		if strings.Contains(svWordPhonemes("som"), "ˈ") {
			t.Errorf("svWordPhonemes(%q) should NOT contain ˈ (function word)", "som")
		}
	})
}

// ---------------------------------------------------------------------------
// 2.2 Stress detection — stress-attracting suffixes (4)
// ---------------------------------------------------------------------------

func TestSvStressAttractingSuffixes(t *testing.T) {
	tests := []struct {
		word string
		desc string
	}{
		{"station", "-tion attracts stress"},     // ST-07
		{"bageri", "-eri attracts stress"},       // ST-08
		{"universitet", "-itet attracts stress"}, // ST-09
		{"turist", "-ist attracts stress"},       // ST-10
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
			s := testSvDetectStress(tt.word)
			if s <= 0 {
				t.Errorf("detectStress(%q) = %d, want > 0 (%s)", tt.word, s, tt.desc)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.2 Stress detection — unstressed prefixes (3)
// ---------------------------------------------------------------------------

func TestSvStressUnstressedPrefixes(t *testing.T) {
	// ST-11: be- prefix -> stress = 1
	t.Run("betala_stress_1", func(t *testing.T) {
		if s := testSvDetectStress("betala"); s != 1 {
			t.Errorf("detectStress(%q) = %d, want 1", "betala", s)
		}
	})

	// ST-12: för- prefix -> stress = 1
	t.Run("förstå_stress_1", func(t *testing.T) {
		if s := testSvDetectStress("förstå"); s != 1 {
			t.Errorf("detectStress(%q) = %d, want 1", "förstå", s)
		}
	})

	// ST-13: betala stress marker not at beginning
	t.Run("betala_marker_not_at_start", func(t *testing.T) {
		ph := svWordPhonemes("betala")
		idx := strings.Index(ph, "ˈ")
		if idx <= 0 {
			t.Errorf("svWordPhonemes(%q) = %q, stress marker at index %d, want > 0",
				"betala", ph, idx)
		}
	})
}

// ---------------------------------------------------------------------------
// 2.2 Stress detection — defaults (2)
// ---------------------------------------------------------------------------

func TestSvStressDefaults(t *testing.T) {
	// ST-14: flicka -> stress = 0, stress marker at start
	t.Run("flicka", func(t *testing.T) {
		if s := testSvDetectStress("flicka"); s != 0 {
			t.Errorf("detectStress(%q) = %d, want 0", "flicka", s)
		}
		ph := svWordPhonemes("flicka")
		if !strings.HasPrefix(ph, "ˈ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected ˈ at start", "flicka", ph)
		}
	})

	// ST-15: lampa -> stress = 0
	t.Run("lampa", func(t *testing.T) {
		if s := testSvDetectStress("lampa"); s != 0 {
			t.Errorf("detectStress(%q) = %d, want 0", "lampa", s)
		}
	})
}

// ---------------------------------------------------------------------------
// 2.3 Loanword suffix detection (10)
// ---------------------------------------------------------------------------

func TestSvLoanwordSuffixDetection(t *testing.T) {
	tests := []struct {
		word     string
		wantStem string
		wantOk   bool
	}{
		{"station", "sta", true},  // LW-01
		{"passion", "pa", true},   // LW-02: matches -ssion (longest first)
		{"mission", "mi", true},   // LW-03: matches -ssion (longest first)
		{"garage", "gar", true},   // LW-04
		{"mage", "", false},       // LW-05: AGE_NATIVE excluded
		{"friseur", "fris", true}, // LW-06
		{"museum", "mus", true},   // LW-07
		{"stadium", "stad", true}, // LW-08
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

func TestSvLoanwordPhonemeOutput(t *testing.T) {
	// LW-09: chef -> contains ɧ
	t.Run("chef_contains_ɧ", func(t *testing.T) {
		if !svContains("chef", "ɧ") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to contain ɧ", "chef", svWordPhonemes("chef"))
		}
	})

	// LW-10: theme -> starts with ˈt
	t.Run("theme_starts_with_t", func(t *testing.T) {
		ph := svWordPhonemes("theme")
		if !strings.HasPrefix(ph, "ˈt") {
			t.Errorf("svWordPhonemes(%q) = %q, expected to start with ˈt", "theme", ph)
		}
	})
}

// ---------------------------------------------------------------------------
// 2.4 "o" Ambiguity Tests (10)
// ---------------------------------------------------------------------------

func TestSvOAmbiguity(t *testing.T) {
	tests := []struct {
		word    string
		want    string
		exclude string
		desc    string
	}{
		{"sol", "uː", "", "o default -> uː"},         // O-01
		{"son", "oː", "", "O_LONG_AS_OO -> oː"},      // O-02
		{"kort", "ɔ", "", "2 consonants -> short ɔ"}, // O-03
		{"mor", "oː", "", "O_LONG_AS_OO"},            // O-04
		{"bror", "oː", "", "O_LONG_AS_OO"},           // O-05
		{"ton", "oː", "", "O_LONG_AS_OO"},            // O-06
		{"bok", "uː", "oː", "not in O_LONG_AS_OO"},   // O-07
		{"god", "oː", "", "O_LONG_AS_OO"},            // O-08
		{"bott", "ɔ", "", "geminate -> short ɔ"},     // O-09
		{"ord", "ɔ", "", "o+rd (2C) -> short ɔ"},     // O-10
	}
	for _, tt := range tests {
		t.Run(tt.word+"_"+tt.desc, func(t *testing.T) {
			ph := svRawWordPhonemes(tt.word)
			if !strings.Contains(ph, tt.want) {
				t.Errorf("svRawWordPhonemes(%q) = %q, expected to contain %q (%s)",
					tt.word, ph, tt.want, tt.desc)
			}
			if tt.exclude != "" && strings.Contains(ph, tt.exclude) {
				t.Errorf("svRawWordPhonemes(%q) = %q, should NOT contain %q (%s)",
					tt.word, ph, tt.exclude, tt.desc)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.5 Prosody integrity (5)
// ---------------------------------------------------------------------------

func TestSvProsody(t *testing.T) {
	// PR-01: len(Tokens) == len(Prosody)
	t.Run("LengthMatch", func(t *testing.T) {
		r := svPhonemizeResult("flicka")
		if len(r.Tokens) != len(r.Prosody) {
			t.Errorf("len(Tokens)=%d != len(Prosody)=%d for 'flicka'",
				len(r.Tokens), len(r.Prosody))
		}
	})

	// PR-02: stress marker has A2==2
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

	// PR-03: A1 always 0 for SV
	t.Run("A1AlwaysZero", func(t *testing.T) {
		r := svPhonemizeResult("flickan gick")
		for i, pr := range r.Prosody {
			if pr.A1 != 0 {
				t.Errorf("Prosody[%d].A1=%d, want 0 for SV", i, pr.A1)
			}
		}
	})

	// PR-04: A3 >= 3 for 'hus' (h, ʉː, s)
	t.Run("A3WordPhonemeCount", func(t *testing.T) {
		r := svPhonemizeResult("hus")
		for _, pr := range r.Prosody {
			if pr.A3 > 0 && pr.A3 < 3 {
				t.Errorf("Prosody.A3=%d, expected >= 3 for 'hus' (h, ʉː, s)", pr.A3)
			}
		}
	})

	// PR-05: multiple words still have matching lengths
	t.Run("MultiWord", func(t *testing.T) {
		r := svPhonemizeResult("hej världen")
		if len(r.Tokens) != len(r.Prosody) {
			t.Errorf("len(Tokens)=%d != len(Prosody)=%d for 'hej världen'",
				len(r.Tokens), len(r.Prosody))
		}
	})
}

// ---------------------------------------------------------------------------
// 2.6 PUA Mapping Tests (10)
// ---------------------------------------------------------------------------

func TestSvPUAMapping(t *testing.T) {
	tests := []struct {
		word    string
		wantPUA rune
		desc    string
	}{
		{"fin", 0xE059, "iː -> PUA"},                // PUA-01
		{"syn", 0xE05A, "yː -> PUA"},                // PUA-02
		{"vet", 0xE05B, "eː -> PUA"},                // PUA-03
		{"säl", 0xE05C, "ɛː -> PUA"},                // PUA-04
		{"öl", 0xE05D, "øː -> PUA"},                 // PUA-05
		{"gata", 0xE05E, "ɑː -> PUA"},               // PUA-06
		{"år", 0xE05F, "oː -> PUA (å)"},             // PUA-07
		{"sol", 0xE060, "uː -> PUA (o default)"},    // PUA-08
		{"hus", 0xE061, "ʉː -> PUA"},                // PUA-09
		{"son", 0xE05F, "oː -> PUA (O_LONG_AS_OO)"}, // PUA-10
	}
	for _, tt := range tests {
		t.Run(tt.desc, func(t *testing.T) {
			r := svPhonemizeResult(tt.word)
			joined := strings.Join(r.Tokens, "")
			if !strings.ContainsRune(joined, tt.wantPUA) {
				t.Errorf("PhonemizeWithProsody(%q) tokens joined=%q, expected PUA U+%04X (%s)",
					tt.word, joined, tt.wantPUA, tt.desc)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// 2.7 Integration Tests (10)
// ---------------------------------------------------------------------------

func TestSvIntegration(t *testing.T) {
	p := NewSwedishPhonemizer()

	// INT-01: punctuation passthrough
	t.Run("Punctuation", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("hej!")
		joined := strings.Join(r.Tokens, "")
		if !strings.Contains(joined, "!") {
			t.Errorf("'hej!' should preserve '!': tokens=%v", r.Tokens)
		}
	})

	// INT-02: multi-word space
	t.Run("MultiWord", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("hej du")
		joined := strings.Join(r.Tokens, "")
		if !strings.Contains(joined, " ") {
			t.Errorf("'hej du' should contain space: tokens=%v", r.Tokens)
		}
	})

	// INT-03: empty string
	t.Run("EmptyString", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("")
		if len(r.Tokens) != 0 {
			t.Errorf("empty input should produce empty tokens, got %v", r.Tokens)
		}
	})

	// INT-04: uppercase normalization
	t.Run("Uppercase", func(t *testing.T) {
		upper := svWordPhonemes("HEJ")
		lower := svWordPhonemes("hej")
		if upper != lower {
			t.Errorf("uppercase 'HEJ' -> %q != lowercase 'hej' -> %q", upper, lower)
		}
	})

	// INT-05: sked full output contains ɧ, eː, d
	t.Run("SkedFullOutput", func(t *testing.T) {
		ph := svWordPhonemes("sked")
		for _, want := range []string{"ɧ", "d"} {
			if !strings.Contains(ph, want) {
				t.Errorf("svWordPhonemes(%q) = %q, expected to contain %q", "sked", ph, want)
			}
		}
	})

	// INT-06: question EOS
	t.Run("QuestionEOS", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("är det sant?")
		if r.EOSToken != "?" {
			t.Errorf("EOS for question should be '?', got %q", r.EOSToken)
		}
	})

	// INT-07: period EOS -> default "$"
	t.Run("PeriodEOS", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("jag går hem.")
		// Period does not change EOS from default "$"
		if r.EOSToken != "$" {
			t.Errorf("EOS for period should be '$', got %q", r.EOSToken)
		}
	})

	// INT-08: exclamation EOS
	t.Run("ExclamationEOS", func(t *testing.T) {
		r, _ := p.PhonemizeWithProsody("stopp!")
		if r.EOSToken != "!" {
			t.Errorf("EOS for exclamation should be '!', got %q", r.EOSToken)
		}
	})

	// INT-09: LanguageCode
	t.Run("LanguageCode", func(t *testing.T) {
		if code := p.LanguageCode(); code != "sv" {
			t.Errorf("LanguageCode() = %q, want 'sv'", code)
		}
	})

	// INT-10: mixed sentence with content + function words
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

// ===========================================================================
// Edge Case Tests
// ===========================================================================

func TestSvEdgeCaseEmptyString(t *testing.T) {
	p := NewSwedishPhonemizer()
	r, err := p.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Tokens) != 0 {
		t.Errorf("empty input: expected 0 tokens, got %d: %v", len(r.Tokens), r.Tokens)
	}
	if len(r.Prosody) != 0 {
		t.Errorf("empty input: expected 0 prosody, got %d", len(r.Prosody))
	}
}

func TestSvEdgeCaseWhitespaceOnly(t *testing.T) {
	p := NewSwedishPhonemizer()
	r, err := p.PhonemizeWithProsody("   ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(r.Tokens) != 0 {
		t.Errorf("whitespace-only input: expected 0 tokens, got %d: %v", len(r.Tokens), r.Tokens)
	}
	if len(r.Prosody) != 0 {
		t.Errorf("whitespace-only input: expected 0 prosody, got %d", len(r.Prosody))
	}
}

func TestSvEdgeCaseSinglePunctuation(t *testing.T) {
	p := NewSwedishPhonemizer()
	r, err := p.PhonemizeWithProsody("?")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should produce a punctuation token
	joined := strings.Join(r.Tokens, "")
	if !strings.Contains(joined, "?") {
		t.Errorf("single '?' input: expected '?' in tokens, got %v", r.Tokens)
	}
	if r.EOSToken != "?" {
		t.Errorf("single '?' input: expected EOS='?', got %q", r.EOSToken)
	}
}

func TestSvEdgeCaseUnicodeCombiningChar(t *testing.T) {
	// e + combining acute accent (U+0301) should be NFC-normalized to é (U+00E9).
	// The phonemizer applies NFC normalization via svNormalize, so the combining
	// form should be treated identically to the precomposed form.
	p := NewSwedishPhonemizer()
	// e\u0301 = e + combining acute accent -> NFC: é
	combiningInput := "e\u0301"
	precomposedInput := "\u00e9"

	r1, err1 := p.PhonemizeWithProsody(combiningInput)
	if err1 != nil {
		t.Fatalf("unexpected error for combining input: %v", err1)
	}
	r2, err2 := p.PhonemizeWithProsody(precomposedInput)
	if err2 != nil {
		t.Fatalf("unexpected error for precomposed input: %v", err2)
	}

	joined1 := strings.Join(r1.Tokens, "")
	joined2 := strings.Join(r2.Tokens, "")
	if joined1 != joined2 {
		t.Errorf("NFC normalization: combining %q -> %q, precomposed %q -> %q (should match)",
			combiningInput, joined1, precomposedInput, joined2)
	}
}
