package phonemize

import (
	"strings"
	"testing"
)

// ===========================================================================
// 1. Pinyin normalization (y/w conventions, v→ü)
// ===========================================================================

func TestZhNormalizePinyin(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		// y- initial normalization
		{"yi -> i", "yi", "i"},
		{"yin -> in", "yin", "in"},
		{"ying -> ing", "ying", "ing"},
		{"ya -> ia", "ya", "ia"},
		{"ye -> ie", "ye", "ie"},
		{"yan -> ian", "yan", "ian"},
		{"yang -> iang", "yang", "iang"},
		{"yao -> iao", "yao", "iao"},
		{"you -> iou", "you", "iou"},
		{"yu -> ü", "yu", "ü"},
		{"yue -> üe", "yue", "üe"},
		{"yuan -> üan", "yuan", "üan"},
		{"yun -> ün", "yun", "ün"},
		{"yong -> iong", "yong", "iong"},

		// w- initial normalization
		{"wu -> u", "wu", "u"},
		{"wa -> ua", "wa", "ua"},
		{"wo -> uo", "wo", "uo"},
		{"wai -> uai", "wai", "uai"},
		{"wei -> uei", "wei", "uei"},
		{"wan -> uan", "wan", "uan"},
		{"wen -> uen", "wen", "uen"},
		{"wang -> uang", "wang", "uang"},
		{"weng -> ueng", "weng", "ueng"},

		// v -> ü replacement
		{"lv -> lü", "lv", "lü"},
		{"nv -> nü", "nv", "nü"},
		{"lve -> lüe", "lve", "lüe"},

		// Identity (no change needed)
		{"ma stays ma", "ma", "ma"},
		{"hao stays hao", "hao", "hao"},
		{"guo stays guo", "guo", "guo"},
		{"er stays er", "er", "er"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := zhNormalizePinyin(tc.input)
			if got != tc.want {
				t.Errorf("zhNormalizePinyin(%q) = %q, want %q", tc.input, got, tc.want)
			}
		})
	}
}

// ===========================================================================
// 2. Split pinyin into (initial, final)
// ===========================================================================

func TestZhSplitPinyin(t *testing.T) {
	tests := []struct {
		name      string
		input     string
		wantInit  string
		wantFinal string
	}{
		// Basic initials
		{"ba -> b+a", "ba", "b", "a"},
		{"ma -> m+a", "ma", "m", "a"},
		{"da -> d+a", "da", "d", "a"},
		{"la -> l+a", "la", "l", "a"},
		{"ga -> g+a", "ga", "g", "a"},
		{"ha -> h+a", "ha", "h", "a"},
		{"fa -> f+a", "fa", "f", "a"},

		// Aspirated initials
		{"pa -> p+a", "pa", "p", "a"},
		{"ta -> t+a", "ta", "t", "a"},
		{"ka -> k+a", "ka", "k", "a"},

		// Retroflex initials (two-char match first)
		{"zhi -> zh+-i_retroflex", "zhi", "zh", "-i_retroflex"},
		{"chi -> ch+-i_retroflex", "chi", "ch", "-i_retroflex"},
		{"shi -> sh+-i_retroflex", "shi", "sh", "-i_retroflex"},
		{"ri -> r+-i_retroflex", "ri", "r", "-i_retroflex"},

		// Alveolar initials with bare 'i'
		{"zi -> z+-i_alveolar", "zi", "z", "-i_alveolar"},
		{"ci -> c+-i_alveolar", "ci", "c", "-i_alveolar"},
		{"si -> s+-i_alveolar", "si", "s", "-i_alveolar"},

		// Alveolo-palatal initials
		{"ji -> j+i", "ji", "j", "i"},
		{"qi -> q+i", "qi", "q", "i"},
		{"xi -> x+i", "xi", "x", "i"},

		// j/q/x + u -> ü
		{"ju -> j+ü", "ju", "j", "ü"},
		{"qu -> q+ü", "qu", "q", "ü"},
		{"xu -> x+ü", "xu", "x", "ü"},
		{"jue -> j+üe", "jue", "j", "üe"},
		{"quan -> q+üan", "quan", "q", "üan"},
		{"xun -> x+ün", "xun", "x", "ün"},

		// Compound finals
		{"zhong -> zh+ong", "zhong", "zh", "ong"},
		{"shuang -> sh+uang", "shuang", "sh", "uang"},
		{"chuang -> ch+uang", "chuang", "ch", "uang"},

		// Zero-initial syllables
		{"a -> +a (no initial)", "a", "", "a"},
		{"e -> +e (no initial)", "e", "", "e"},
		{"o -> +o (no initial)", "o", "", "o"},
		{"ai -> +ai (no initial)", "ai", "", "ai"},
		{"er -> +er (no initial)", "er", "", "er"},
		{"ou -> +ou (no initial)", "ou", "", "ou"},
		{"an -> +an (no initial)", "an", "", "an"},
		{"ang -> +ang (no initial)", "ang", "", "ang"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			gotInit, gotFinal := zhSplitPinyin(tc.input)
			if gotInit != tc.wantInit || gotFinal != tc.wantFinal {
				t.Errorf("zhSplitPinyin(%q) = (%q, %q), want (%q, %q)",
					tc.input, gotInit, gotFinal, tc.wantInit, tc.wantFinal)
			}
		})
	}
}

// ===========================================================================
// 3. Pinyin -> IPA conversion
// ===========================================================================

func TestZhPinyinToIPA(t *testing.T) {
	tests := []struct {
		name     string
		syllable string
		tone     int
		want     []string
	}{
		// Simple initials + finals
		{"ma1", "ma", 1, []string{"m", "a", "tone1"}},
		{"ba4", "ba", 4, []string{"p", "a", "tone4"}},
		{"pa2", "pa", 2, []string{"pʰ", "a", "tone2"}},
		{"da4", "da", 4, []string{"t", "a", "tone4"}},
		{"ta4", "ta", 4, []string{"tʰ", "a", "tone4"}},
		{"ga1", "ga", 1, []string{"k", "a", "tone1"}},
		{"ka3", "ka", 3, []string{"kʰ", "a", "tone3"}},
		{"ha3", "ha", 3, []string{"x", "a", "tone3"}},

		// Retroflex initials
		{"zhi1 (syllabic)", "zhi", 1, []string{"tʂ", "ɻ̩", "tone1"}},
		{"chi1 (syllabic)", "chi", 1, []string{"tʂʰ", "ɻ̩", "tone1"}},
		{"shi2 (syllabic)", "shi", 2, []string{"ʂ", "ɻ̩", "tone2"}},
		{"ri4 (syllabic)", "ri", 4, []string{"ɻ", "ɻ̩", "tone4"}},

		// Alveolar initials with bare i (syllabic)
		{"zi4 (syllabic)", "zi", 4, []string{"ts", "ɨ", "tone4"}},
		{"ci2 (syllabic)", "ci", 2, []string{"tsʰ", "ɨ", "tone2"}},
		{"si1 (syllabic)", "si", 1, []string{"s", "ɨ", "tone1"}},

		// Alveolo-palatal
		{"ji1", "ji", 1, []string{"tɕ", "i", "tone1"}},
		{"qi2", "qi", 2, []string{"tɕʰ", "i", "tone2"}},
		{"xi3", "xi", 3, []string{"ɕ", "i", "tone3"}},

		// ü compounds after j/q/x (pre-split, so ü is already in the final)
		{"jü -> tɕ + y_vowel", "jü", 1, []string{"tɕ", "y_vowel", "tone1"}},

		// Compound finals
		{"ai", "ai", 2, []string{"aɪ", "tone2"}},
		{"ei", "ei", 4, []string{"eɪ", "tone4"}},
		{"ao", "ao", 3, []string{"aʊ", "tone3"}},
		{"ou", "ou", 1, []string{"oʊ", "tone1"}},

		// Nasal finals
		{"an", "an", 1, []string{"an", "tone1"}},
		{"en", "en", 2, []string{"ən", "tone2"}},
		{"ang", "ang", 1, []string{"aŋ", "tone1"}},
		{"eng", "eng", 2, []string{"əŋ", "tone2"}},
		{"ong", "ong", 1, []string{"uŋ", "tone1"}},

		// Retroflex final (standalone)
		{"er2", "er", 2, []string{"ɚ", "tone2"}},

		// i-compound finals
		{"ian", "ian", 2, []string{"iɛn", "tone2"}},
		{"iang", "iang", 2, []string{"iaŋ", "tone2"}},
		{"iao", "iao", 3, []string{"iaʊ", "tone3"}},
		{"ie", "ie", 4, []string{"iɛ", "tone4"}},
		{"ing", "ing", 2, []string{"iŋ", "tone2"}},
		{"iong", "iong", 3, []string{"iuŋ", "tone3"}},

		// u-compound finals
		{"uan", "uan", 2, []string{"uan", "tone2"}},
		{"uang", "uang", 2, []string{"uaŋ", "tone2"}},
		{"uo", "uo", 3, []string{"uo", "tone3"}},
		{"ui", "ui", 4, []string{"ueɪ", "tone4"}},

		// ü-compound finals
		{"üe", "üe", 4, []string{"yɛ", "tone4"}},
		{"üan", "üan", 2, []string{"yɛn", "tone2"}},
		{"ün", "ün", 2, []string{"yn", "tone2"}},

		// Zero-initial
		{"a1 (no initial)", "a", 1, []string{"a", "tone1"}},
		{"e4 (no initial)", "e", 4, []string{"ɤ", "tone4"}},
		{"o2 (no initial)", "o", 2, []string{"o", "tone2"}},

		// Neutral tone (tone 5)
		{"ma5 (neutral)", "ma", 5, []string{"m", "a", "tone5"}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := zhPinyinToIPA(tc.syllable, tc.tone)
			if !sliceEqual(got, tc.want) {
				t.Errorf("zhPinyinToIPA(%q, %d) = %v, want %v",
					tc.syllable, tc.tone, got, tc.want)
			}
		})
	}
}

// ===========================================================================
// 4. Tone extraction
// ===========================================================================

func TestZhExtractTone(t *testing.T) {
	tests := []struct {
		input    string
		wantBase string
		wantTone int
	}{
		{"ma1", "ma", 1},
		{"ni3", "ni", 3},
		{"hao3", "hao", 3},
		{"de5", "de", 5},
		{"zhong1", "zhong", 1},
		{"er2", "er", 2},
		// No tone digit -> default 5
		{"ma", "ma", 5},
		// Empty string
		{"", "", 5},
	}
	for _, tc := range tests {
		t.Run(tc.input, func(t *testing.T) {
			gotBase, gotTone := zhExtractTone(tc.input)
			if gotBase != tc.wantBase || gotTone != tc.wantTone {
				t.Errorf("zhExtractTone(%q) = (%q, %d), want (%q, %d)",
					tc.input, gotBase, gotTone, tc.wantBase, tc.wantTone)
			}
		})
	}
}

// ===========================================================================
// 5. Tone sandhi rules
// ===========================================================================

func TestZhApplyToneSandhi(t *testing.T) {
	tests := []struct {
		name  string
		input []syllableTone
		want  []int // expected tones after sandhi
	}{
		// Rule 1: T3 + T3 -> T2 + T3 (你好 nǐhǎo)
		{
			"T3+T3 -> T2+T3",
			[]syllableTone{{"ni", 3}, {"hao", 3}},
			[]int{2, 3},
		},
		// Rule 1: Chain of three T3 (展览馆): should apply left-to-right
		{
			"T3+T3+T3 chain",
			[]syllableTone{{"zhan", 3}, {"lan", 3}, {"guan", 3}},
			[]int{2, 2, 3},
		},
		// Rule 2: 一 before T4 -> T2 (一定 yī dìng -> yí dìng)
		{
			"yi T1 before T4 -> T2",
			[]syllableTone{{"i", 1}, {"ding", 4}},
			[]int{2, 4},
		},
		// Rule 3: 一 before T1 -> T4 (一般 yī bān -> yì bān)
		{
			"yi T1 before T1 -> T4",
			[]syllableTone{{"i", 1}, {"ban", 1}},
			[]int{4, 1},
		},
		// Rule 3: 一 before T2 -> T4
		{
			"yi T1 before T2 -> T4",
			[]syllableTone{{"i", 1}, {"tiao", 2}},
			[]int{4, 2},
		},
		// Rule 3: 一 before T3 -> T4
		{
			"yi T1 before T3 -> T4",
			[]syllableTone{{"i", 1}, {"qi", 3}},
			[]int{4, 3},
		},
		// Rule 4: 不 before T4 -> T2 (不对 bù duì -> bú duì)
		{
			"bu T4 before T4 -> T2",
			[]syllableTone{{"bu", 4}, {"tui", 4}},
			[]int{2, 4},
		},
		// 不 before non-T4 -> no change
		{
			"bu T4 before T2 -> no change",
			[]syllableTone{{"bu", 4}, {"xing", 2}},
			[]int{4, 2},
		},
		// No sandhi: T1 + T2
		{
			"T1+T2 -> no change",
			[]syllableTone{{"zhong", 1}, {"guo", 2}},
			[]int{1, 2},
		},
		// Non-yi syllable with T1 before T4 -> no change
		{
			"non-yi T1 before T4 -> no change",
			[]syllableTone{{"ba", 1}, {"la", 4}},
			[]int{1, 4},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Make a copy to avoid mutating the test input
			st := make([]syllableTone, len(tc.input))
			copy(st, tc.input)
			zhApplyToneSandhi(st)
			for i, wantTone := range tc.want {
				if st[i].tone != wantTone {
					t.Errorf("tone[%d] = %d, want %d (input: %v)",
						i, st[i].tone, wantTone, tc.input)
				}
			}
		})
	}
}

// ===========================================================================
// 6. Punctuation mapping
// ===========================================================================

func TestZhPunctMap(t *testing.T) {
	// Verify Chinese punctuation maps match Python _ZH_PUNCT_MAP exactly
	expectedMappings := map[rune]rune{
		'\u3002': '.',  // 。
		'\uff0c': ',',  // ，
		'\uff01': '!',  // ！
		'\uff1f': '?',  // ？
		'\u3001': ',',  // 、
		'\uff1b': ';',  // ；
		'\uff1a': ':',  // ：
		'\u2026': '.',  // …
		'\u2014': ',',  // —
		'\u201c': '"',  // "
		'\u201d': '"',  // "
		'\u2018': '\'', // '
		'\u2019': '\'', // '
	}
	if len(zhPunctMap) != len(expectedMappings) {
		t.Errorf("zhPunctMap has %d entries, want %d", len(zhPunctMap), len(expectedMappings))
	}
	for zh, wantAscii := range expectedMappings {
		gotAscii, ok := zhPunctMap[zh]
		if !ok {
			t.Errorf("zhPunctMap missing key U+%04X (%c)", zh, zh)
			continue
		}
		if gotAscii != wantAscii {
			t.Errorf("zhPunctMap[U+%04X] = %q, want %q", zh, string(gotAscii), string(wantAscii))
		}
	}
}

// ===========================================================================
// 7. CJK detection
// ===========================================================================

func TestIsCJK(t *testing.T) {
	tests := []struct {
		r    rune
		want bool
	}{
		{'你', true},
		{'好', true},
		{'中', true},
		{'\u4E00', true}, // CJK first
		{'\u9FFF', true}, // CJK last (basic)
		{'\u3400', true}, // CJK Extension A first
		{'\u4DBF', true}, // CJK Extension A last
		{'a', false},
		{'1', false},
		{'。', false},      // punctuation, not CJK
		{'\u3000', false}, // ideographic space
	}
	for _, tc := range tests {
		got := isCJK(tc.r)
		if got != tc.want {
			t.Errorf("isCJK(%q U+%04X) = %v, want %v", string(tc.r), tc.r, got, tc.want)
		}
	}
}

// ===========================================================================
// 8. Initial-to-IPA mapping consistency with Python
// ===========================================================================

func TestZhInitialToIPA_MatchesPython(t *testing.T) {
	// Python _INITIAL_TO_IPA has exactly 21 entries
	pythonInitials := map[string]string{
		"b": "p", "p": "pʰ", "m": "m", "f": "f",
		"d": "t", "t": "tʰ", "n": "n", "l": "l",
		"g": "k", "k": "kʰ", "h": "x",
		"j": "tɕ", "q": "tɕʰ", "x": "ɕ",
		"zh": "tʂ", "ch": "tʂʰ", "sh": "ʂ", "r": "ɻ",
		"z": "ts", "c": "tsʰ", "s": "s",
	}
	if len(zhInitialToIPA) != len(pythonInitials) {
		t.Errorf("zhInitialToIPA has %d entries, Python has %d",
			len(zhInitialToIPA), len(pythonInitials))
	}
	for init, wantIPA := range pythonInitials {
		gotIPA, ok := zhInitialToIPA[init]
		if !ok {
			t.Errorf("zhInitialToIPA missing key %q", init)
			continue
		}
		if gotIPA != wantIPA {
			t.Errorf("zhInitialToIPA[%q] = %q, want %q (Python ref)", init, gotIPA, wantIPA)
		}
	}
}

// ===========================================================================
// 9. Final-to-IPA mapping consistency with Python
// ===========================================================================

func TestZhFinalToIPA_MatchesPython(t *testing.T) {
	// Python _FINAL_TO_IPA (matching Go keys)
	pythonFinals := map[string]string{
		"a": "a", "o": "o", "e": "ɤ", "i": "i", "u": "u",
		"ü": "y_vowel", "v": "y_vowel",
		"ai": "aɪ", "ei": "eɪ", "ao": "aʊ", "ou": "oʊ",
		"an": "an", "en": "ən", "ang": "aŋ", "eng": "əŋ", "ong": "uŋ",
		"er": "ɚ",
		"ia": "ia", "ie": "iɛ", "iao": "iaʊ",
		"iu": "iou", "iou": "iou",
		"ian": "iɛn", "in": "in", "iang": "iaŋ", "ing": "iŋ", "iong": "iuŋ",
		"ua": "ua", "uo": "uo", "uai": "uaɪ",
		"ui": "ueɪ", "uei": "ueɪ",
		"uan": "uan", "un": "uən", "uen": "uən",
		"uang": "uaŋ", "ueng": "uəŋ",
		"üe": "yɛ", "ve": "yɛ",
		"üan": "yɛn", "van": "yɛn",
		"ün": "yn", "vn": "yn",
		"-i_retroflex": "ɻ̩",
		"-i_alveolar":  "ɨ",
	}
	if len(zhFinalToIPA) != len(pythonFinals) {
		t.Errorf("zhFinalToIPA has %d entries, Python has %d",
			len(zhFinalToIPA), len(pythonFinals))
	}
	for final, wantIPA := range pythonFinals {
		gotIPA, ok := zhFinalToIPA[final]
		if !ok {
			t.Errorf("zhFinalToIPA missing key %q", final)
			continue
		}
		if gotIPA != wantIPA {
			t.Errorf("zhFinalToIPA[%q] = %q, want %q (Python ref)", final, gotIPA, wantIPA)
		}
	}
}

// ===========================================================================
// 10. Full pipeline: PhonemizeWithProsody basic tests
// ===========================================================================

func TestChinesePhonemizer_EmptyInput(t *testing.T) {
	p := NewChinesePhonemizer(nil, nil)
	result, err := p.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want %q", result.EOSToken, "$")
	}
	if len(result.Tokens) != 0 {
		t.Errorf("Tokens = %v, want empty", result.Tokens)
	}
}

func TestChinesePhonemizer_SingleChar(t *testing.T) {
	// 你 -> ni3: normalized = "ni", tone = 3
	// Expected IPA: n + i + tone3
	singleDict := map[rune]string{
		'你': "ni3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Reverse PUA mapping to get raw tokens
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "n") {
		t.Errorf("tokens %v should contain 'n'", rawTokens)
	}
	if !sliceContains(rawTokens, "i") {
		t.Errorf("tokens %v should contain 'i'", rawTokens)
	}
	if !sliceContains(rawTokens, "tone3") {
		t.Errorf("tokens %v should contain 'tone3'", rawTokens)
	}
}

func TestChinesePhonemizer_TwoCharToneSandhi(t *testing.T) {
	// 你好 ni3hao3 -> tone sandhi: ni2 + hao3
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rawTokens := unmapPUA(result.Tokens)

	// After tone sandhi, 你 should have tone2 (not tone3)
	if !sliceContains(rawTokens, "tone2") {
		t.Errorf("tokens %v should contain 'tone2' after T3+T3 sandhi", rawTokens)
	}
	// 好 should still have tone3
	if !sliceContains(rawTokens, "tone3") {
		t.Errorf("tokens %v should contain 'tone3' for 好", rawTokens)
	}
}

func TestChinesePhonemizer_PunctuationEOS(t *testing.T) {
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)

	// Test question mark EOS
	result, err := p.PhonemizeWithProsody("你好？")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "?" {
		t.Errorf("EOSToken = %q, want %q for ？", result.EOSToken, "?")
	}

	// Test exclamation mark EOS
	result, err = p.PhonemizeWithProsody("你好！")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "!" {
		t.Errorf("EOSToken = %q, want %q for ！", result.EOSToken, "!")
	}

	// Test period -> default EOS
	result, err = p.PhonemizeWithProsody("你好。")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want %q for 。", result.EOSToken, "$")
	}
}

func TestChinesePhonemizer_MixedPunctuation(t *testing.T) {
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你好，你好。")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rawTokens := unmapPUA(result.Tokens)
	// The Chinese comma 、 should be mapped to ","
	if !sliceContains(rawTokens, ",") {
		t.Errorf("tokens %v should contain ',' for ，", rawTokens)
	}
	if !sliceContains(rawTokens, ".") {
		t.Errorf("tokens %v should contain '.' for 。", rawTokens)
	}
}

// ===========================================================================
// 11. Erhua (儿化音) handling
// ===========================================================================

func TestChinesePhonemizer_Erhua(t *testing.T) {
	// 花儿 -> hua1r: the character 花 with erhua suffix
	// The erhua 'r' is on the last character in actual usage
	singleDict := map[rune]string{
		'花': "hua1",
		'儿': "er2",
	}
	p := NewChinesePhonemizer(singleDict, nil)

	// Test standalone "er" -> should produce ɚ
	result, err := p.PhonemizeWithProsody("儿")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "ɚ") {
		t.Errorf("standalone 儿 tokens %v should contain 'ɚ'", rawTokens)
	}
}

func TestZhPinyinToIPA_ErFinal(t *testing.T) {
	// Direct test: "er" -> ɚ (the er final, not erhua)
	tokens := zhPinyinToIPA("er", 2)
	want := []string{"ɚ", "tone2"}
	if !sliceEqual(tokens, want) {
		t.Errorf("zhPinyinToIPA(\"er\", 2) = %v, want %v", tokens, want)
	}
}

// ===========================================================================
// 12. Yi/Bu tone sandhi integration
// ===========================================================================

func TestChinesePhonemizer_YiToneSandhi(t *testing.T) {
	// 一定 yi1 ding4 -> yi2 ding4 (T1 before T4 -> T2)
	singleDict := map[rune]string{
		'一': "yi1",
		'定': "ding4",
		'般': "ban1",
	}
	p := NewChinesePhonemizer(singleDict, nil)

	result, err := p.PhonemizeWithProsody("一定")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	// After yi sandhi, 一 should have tone2
	if !sliceContains(rawTokens, "tone2") {
		t.Errorf("一定: tokens %v should contain 'tone2' for 一 before T4", rawTokens)
	}

	// 一般 yi1 ban1 -> yi4 ban1 (T1 before T1 -> T4)
	result, err = p.PhonemizeWithProsody("一般")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens = unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "tone4") {
		t.Errorf("一般: tokens %v should contain 'tone4' for 一 before T1", rawTokens)
	}
}

func TestChinesePhonemizer_BuToneSandhi(t *testing.T) {
	// 不对 bu4 dui4 -> bu2 dui4 (T4 before T4 -> T2)
	singleDict := map[rune]string{
		'不': "bu4",
		'对': "dui4",
		'行': "xing2",
	}
	p := NewChinesePhonemizer(singleDict, nil)

	result, err := p.PhonemizeWithProsody("不对")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "tone2") {
		t.Errorf("不对: tokens %v should contain 'tone2' for 不 before T4", rawTokens)
	}

	// 不行 bu4 xing2 -> no sandhi, bu stays T4
	result, err = p.PhonemizeWithProsody("不行")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens = unmapPUA(result.Tokens)
	// First tone should be tone4, second should be tone2
	toneIdx := 0
	for _, tok := range rawTokens {
		if strings.HasPrefix(tok, "tone") {
			if toneIdx == 0 && tok != "tone4" {
				t.Errorf("不行: first tone should be tone4, got %q", tok)
			}
			if toneIdx == 1 && tok != "tone2" {
				t.Errorf("不行: second tone should be tone2, got %q", tok)
			}
			toneIdx++
		}
	}
}

// ===========================================================================
// 13. Word boundary / prosody
// ===========================================================================

func TestZhBuildWordInfo(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  map[int]wordPos
	}{
		{
			"two-char word",
			"你好",
			map[int]wordPos{0: {1, 2}, 1: {2, 2}},
		},
		{
			"three-char word",
			"中国人",
			map[int]wordPos{0: {1, 3}, 1: {2, 3}, 2: {3, 3}},
		},
		{
			"two words separated by punct",
			"你好，世界",
			map[int]wordPos{0: {1, 2}, 1: {2, 2}, 3: {1, 2}, 4: {2, 2}},
		},
		{
			"single char",
			"好",
			map[int]wordPos{0: {1, 1}},
		},
		{
			"no CJK",
			"hello",
			map[int]wordPos{},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := zhBuildWordInfo([]rune(tc.input))
			if len(got) != len(tc.want) {
				t.Fatalf("zhBuildWordInfo(%q): got %d entries, want %d. got=%v",
					tc.input, len(got), len(tc.want), got)
			}
			for idx, wantWP := range tc.want {
				gotWP, ok := got[idx]
				if !ok {
					t.Errorf("missing entry for index %d", idx)
					continue
				}
				if gotWP != wantWP {
					t.Errorf("index %d: got %+v, want %+v", idx, gotWP, wantWP)
				}
			}
		})
	}
}

func TestChinesePhonemizer_Prosody(t *testing.T) {
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Check prosody is present for Chinese phoneme tokens
	foundProsody := false
	for _, pros := range result.Prosody {
		if pros != nil && pros.A3 > 0 {
			foundProsody = true
			break
		}
	}
	if !foundProsody {
		t.Error("expected non-nil prosody with A3 > 0 for Chinese characters")
	}
}

// ===========================================================================
// 14. Phrase matching
// ===========================================================================

func TestZhPhraseMatch(t *testing.T) {
	phrases := map[string]string{
		"你好":   "ni3 hao3",
		"中华人民": "zhong1 hua2 ren2 min2",
	}
	runes := []rune("你好世界")

	// Should match 你好 at position 0
	matchLen, py, ok := zhPhraseMatch(runes, 0, phrases)
	if !ok {
		t.Fatal("expected phrase match for 你好")
	}
	if matchLen != 2 {
		t.Errorf("matchLen = %d, want 2", matchLen)
	}
	if py != "ni3 hao3" {
		t.Errorf("pinyin = %q, want %q", py, "ni3 hao3")
	}

	// No match at position 2 (世界 not in dict)
	_, _, ok = zhPhraseMatch(runes, 2, phrases)
	if ok {
		t.Error("expected no match for 世界")
	}
}

func TestZhPhraseMatch_LongestFirst(t *testing.T) {
	// Longest prefix match: 中华人民 (4) should match before 中华 (2)
	phrases := map[string]string{
		"中华":   "zhong1 hua2",
		"中华人民": "zhong1 hua2 ren2 min2",
	}
	runes := []rune("中华人民共和国")

	matchLen, _, ok := zhPhraseMatch(runes, 0, phrases)
	if !ok {
		t.Fatal("expected phrase match")
	}
	if matchLen != 4 {
		t.Errorf("matchLen = %d, want 4 (longest match)", matchLen)
	}
}

// ===========================================================================
// 15. Digits and alphabetic pass-through
// ===========================================================================

func TestChinesePhonemizer_Digits(t *testing.T) {
	p := NewChinesePhonemizer(nil, nil)
	result, err := p.PhonemizeWithProsody("123")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	expected := []string{"1", "2", "3"}
	if !sliceEqual(rawTokens, expected) {
		t.Errorf("digits: got %v, want %v", rawTokens, expected)
	}
}

func TestChinesePhonemizer_LatinPassthrough(t *testing.T) {
	p := NewChinesePhonemizer(nil, nil)
	result, err := p.PhonemizeWithProsody("ABC")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	expected := []string{"A", "B", "C"}
	if !sliceEqual(rawTokens, expected) {
		t.Errorf("latin: got %v, want %v", rawTokens, expected)
	}
}

func TestChinesePhonemizer_Whitespace(t *testing.T) {
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你 好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, " ") {
		t.Errorf("whitespace: tokens %v should contain space", rawTokens)
	}
}

// ===========================================================================
// 16. Unknown CJK character handling
// ===========================================================================

func TestChinesePhonemizer_UnknownChar(t *testing.T) {
	// CJK character not in dictionary should be treated as non-Chinese
	singleDict := map[rune]string{
		'你': "ni3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你龘")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Should not panic; the unknown char should be skipped
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "n") {
		t.Errorf("tokens %v should contain 'n' from 你", rawTokens)
	}
}

// ===========================================================================
// 17. Multi-reading characters (comma-separated pinyin in dict)
// ===========================================================================

func TestChinesePhonemizer_MultiReading(t *testing.T) {
	// 行 has readings "xing2,hang2" -> should use first (xing2)
	singleDict := map[rune]string{
		'行': "xing2,hang2",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("行")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	// xing2: x->ɕ, ing->iŋ, tone2
	if !sliceContains(rawTokens, "ɕ") {
		t.Errorf("行 tokens %v should contain 'ɕ' (initial x)", rawTokens)
	}
	if !sliceContains(rawTokens, "iŋ") {
		t.Errorf("行 tokens %v should contain 'iŋ' (final ing)", rawTokens)
	}
}

// ===========================================================================
// 18. LanguageCode
// ===========================================================================

func TestChinesePhonemizer_LanguageCode(t *testing.T) {
	p := NewChinesePhonemizer(nil, nil)
	if got := p.LanguageCode(); got != "zh" {
		t.Errorf("LanguageCode() = %q, want %q", got, "zh")
	}
}

// ===========================================================================
// 19. PUA mapping for Chinese-specific tokens
// ===========================================================================

func TestZhTokensPUAMapping(t *testing.T) {
	// Verify that all Chinese IPA tokens in the PUA map can be round-tripped
	zhTokens := []struct {
		token string
		pua   rune
	}{
		{"pʰ", 0xE020},
		{"tʰ", 0xE021},
		{"kʰ", 0xE022},
		{"tɕ", 0xE023},
		{"tɕʰ", 0xE024},
		{"tʂ", 0xE025},
		{"tʂʰ", 0xE026},
		{"tsʰ", 0xE027},
		{"aɪ", 0xE028},
		{"eɪ", 0xE029},
		{"aʊ", 0xE02A},
		{"oʊ", 0xE02B},
		{"an", 0xE02C},
		{"ən", 0xE02D},
		{"aŋ", 0xE02E},
		{"əŋ", 0xE02F},
		{"uŋ", 0xE030},
		{"ia", 0xE031},
		{"iɛ", 0xE032},
		{"iou", 0xE033},
		{"iaʊ", 0xE034},
		{"iɛn", 0xE035},
		{"in", 0xE036},
		{"iaŋ", 0xE037},
		{"iŋ", 0xE038},
		{"iuŋ", 0xE039},
		{"ua", 0xE03A},
		{"uo", 0xE03B},
		{"uaɪ", 0xE03C},
		{"ueɪ", 0xE03D},
		{"uan", 0xE03E},
		{"uən", 0xE03F},
		{"uaŋ", 0xE040},
		{"uəŋ", 0xE041},
		{"yɛ", 0xE042},
		{"yɛn", 0xE043},
		{"yn", 0xE044},
		{"ɻ̩", 0xE045},
		{"tone1", 0xE046},
		{"tone2", 0xE047},
		{"tone3", 0xE048},
		{"tone4", 0xE049},
		{"tone5", 0xE04A},
		{"y_vowel", 0xE01E},
	}
	for _, tc := range zhTokens {
		// Forward: token -> PUA
		mapped := RegisterToken(tc.token)
		if mapped != string(tc.pua) {
			t.Errorf("RegisterToken(%q) = U+%04X, want U+%04X",
				tc.token, []rune(mapped)[0], tc.pua)
		}
		// Reverse: PUA -> token
		got, ok := PUAToToken(tc.pua)
		if !ok {
			t.Errorf("PUAToToken(U+%04X) returned ok=false, want %q", tc.pua, tc.token)
			continue
		}
		if got != tc.token {
			t.Errorf("PUAToToken(U+%04X) = %q, want %q", tc.pua, got, tc.token)
		}
	}
}

// ===========================================================================
// 20. Full pipeline end-to-end with realistic input
// ===========================================================================

func TestChinesePhonemizer_EndToEnd(t *testing.T) {
	singleDict := map[rune]string{
		'中': "zhong1",
		'国': "guo2",
		'人': "ren2",
		'民': "min2",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("中国人民")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	rawTokens := unmapPUA(result.Tokens)

	// Expected token sequence (4 characters):
	// zhong1: tʂ + uŋ + tone1
	// guo2: k + uo + tone2
	// ren2: ɻ + ən + tone2
	// min2: m + in + tone2
	expectedSubseqs := [][]string{
		{"tʂ", "uŋ", "tone1"},
		{"k", "uo", "tone2"},
		{"ɻ", "ən", "tone2"},
		{"m", "in", "tone2"},
	}
	tokenStr := strings.Join(rawTokens, "|")
	for _, subseq := range expectedSubseqs {
		subStr := strings.Join(subseq, "|")
		if !strings.Contains(tokenStr, subStr) {
			t.Errorf("tokens %v missing subsequence %v", rawTokens, subseq)
		}
	}
}

func TestChinesePhonemizer_RetroflexInitials(t *testing.T) {
	singleDict := map[rune]string{
		'知': "zhi1",
		'吃': "chi1",
		'是': "shi4",
		'日': "ri4",
		'字': "zi4",
		'次': "ci4",
		'思': "si1",
	}
	p := NewChinesePhonemizer(singleDict, nil)

	tests := []struct {
		char        string
		wantInitial string
		wantFinal   string
	}{
		{"知", "tʂ", "ɻ̩"},
		{"吃", "tʂʰ", "ɻ̩"},
		{"是", "ʂ", "ɻ̩"},
		{"日", "ɻ", "ɻ̩"},
		{"字", "ts", "ɨ"},
		{"次", "tsʰ", "ɨ"},
		{"思", "s", "ɨ"},
	}
	for _, tc := range tests {
		result, err := p.PhonemizeWithProsody(tc.char)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.char, err)
		}
		rawTokens := unmapPUA(result.Tokens)
		if !sliceContains(rawTokens, tc.wantInitial) {
			t.Errorf("%s: tokens %v should contain initial %q", tc.char, rawTokens, tc.wantInitial)
		}
		if !sliceContains(rawTokens, tc.wantFinal) {
			t.Errorf("%s: tokens %v should contain final %q", tc.char, rawTokens, tc.wantFinal)
		}
	}
}

// ===========================================================================
// 21. Tone sandhi applied to characters (consecutive group tracking)
// ===========================================================================

func TestZhApplyToneSandhiToChars(t *testing.T) {
	// Simulate: 你好 (two consecutive Chinese chars, both tone 3)
	chars := []charPinyin{
		{isChinese: true, normalized: "ni", tone: 3},
		{isChinese: true, normalized: "hao", tone: 3},
	}
	zhApplyToneSandhiToChars(chars)
	if chars[0].tone != 2 {
		t.Errorf("chars[0].tone = %d, want 2 after T3+T3 sandhi", chars[0].tone)
	}
	if chars[1].tone != 3 {
		t.Errorf("chars[1].tone = %d, want 3 (unchanged)", chars[1].tone)
	}
}

func TestZhApplyToneSandhiToChars_SplitByNonChinese(t *testing.T) {
	// Two Chinese groups split by a non-Chinese character
	// Group 1: T3 + T3 -> sandhi
	// Group 2: single T3 -> no sandhi
	chars := []charPinyin{
		{isChinese: true, normalized: "ni", tone: 3},
		{isChinese: true, normalized: "hao", tone: 3},
		{isChinese: false}, // punctuation/space separator
		{isChinese: true, normalized: "hao", tone: 3},
	}
	zhApplyToneSandhiToChars(chars)
	if chars[0].tone != 2 {
		t.Errorf("group1[0].tone = %d, want 2", chars[0].tone)
	}
	if chars[1].tone != 3 {
		t.Errorf("group1[1].tone = %d, want 3", chars[1].tone)
	}
	// Group 2 is a single char, no sandhi
	if chars[3].tone != 3 {
		t.Errorf("group2[0].tone = %d, want 3 (no sandhi for single char)", chars[3].tone)
	}
}

// ===========================================================================
// 22. Edge cases: special characters, combining marks, empty slices
// ===========================================================================

func TestChinesePhonemizer_SpecialChars(t *testing.T) {
	p := NewChinesePhonemizer(nil, nil)

	// Various special characters that should not crash
	inputs := []string{
		"",
		" ",
		"  \t\n  ",
		"...",
		"！？，。",
		"@#$%^&*()",
		"\u200b", // zero-width space
	}
	for _, input := range inputs {
		_, err := p.PhonemizeWithProsody(input)
		if err != nil {
			t.Errorf("PhonemizeWithProsody(%q) unexpected error: %v", input, err)
		}
	}
}

func TestZhApplyToneSandhi_Empty(t *testing.T) {
	// Should not panic on empty slice
	var empty []syllableTone
	zhApplyToneSandhi(empty)
}

func TestZhApplyToneSandhi_Single(t *testing.T) {
	// Single element: no sandhi possible
	st := []syllableTone{{"ma", 3}}
	zhApplyToneSandhi(st)
	if st[0].tone != 3 {
		t.Errorf("single element tone = %d, want 3 (unchanged)", st[0].tone)
	}
}

// ===========================================================================
// 23. All 21 initials produce correct IPA
// ===========================================================================

func TestAllInitials_ProduceIPA(t *testing.T) {
	// Each initial + "a" should produce (initial_ipa, "a", tone marker)
	for _, init := range zhInitialsOrder {
		syllable := init + "a"
		tokens := zhPinyinToIPA(syllable, 1)
		if len(tokens) < 2 {
			t.Errorf("zhPinyinToIPA(%q, 1) = %v, expected at least 2 tokens", syllable, tokens)
			continue
		}
		expectedInitIPA := zhInitialToIPA[init]
		if tokens[0] != expectedInitIPA {
			t.Errorf("zhPinyinToIPA(%q, 1)[0] = %q, want %q",
				syllable, tokens[0], expectedInitIPA)
		}
	}
}

// ===========================================================================
// 24. Comprehensive normalization + split + IPA pipeline
//     (simulating Python's phonemize_from_pinyin_syllables path)
// ===========================================================================

func TestFullPinyinPipeline(t *testing.T) {
	// Simulate the full pipeline: raw pinyin -> normalize -> split -> IPA
	tests := []struct {
		name       string
		rawPinyin  string // with tone digit
		wantTokens []string
	}{
		{"ma1", "ma1", []string{"m", "a", "tone1"}},
		{"wo3", "wo3", []string{"uo", "tone3"}},         // w normalization
		{"yi1", "yi1", []string{"i", "tone1"}},          // y normalization
		{"wu3", "wu3", []string{"u", "tone3"}},          // w normalization
		{"yu4", "yu4", []string{"y_vowel", "tone4"}},    // y normalization -> ü
		{"zhi1", "zhi1", []string{"tʂ", "ɻ̩", "tone1"}}, // retroflex syllabic
		{"ci2", "ci2", []string{"tsʰ", "ɨ", "tone2"}},   // alveolar syllabic
		{"er2", "er2", []string{"ɚ", "tone2"}},          // standalone er
		{"yue4", "yue4", []string{"yɛ", "tone4"}},       // yu -> ü, üe -> yɛ
		{"yuan2", "yuan2", []string{"yɛn", "tone2"}},    // yuan -> üan -> yɛn
		{"yun2", "yun2", []string{"yn", "tone2"}},       // yun -> ün -> yn
		{"jun1", "jun1", []string{"tɕ", "yn", "tone1"}}, // j + un -> j + ün -> tɕ + yn
		{"gui4", "gui4", []string{"k", "ueɪ", "tone4"}}, // g + ui -> k + ueɪ
		{"dui4", "dui4", []string{"t", "ueɪ", "tone4"}}, // d + ui -> t + ueɪ
		{"liang2", "liang2", []string{"l", "iaŋ", "tone2"}},
		{"xiong2", "xiong2", []string{"ɕ", "iuŋ", "tone2"}},
		{"guang1", "guang1", []string{"k", "uaŋ", "tone1"}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			base, tone := zhExtractTone(tc.rawPinyin)
			normalized := zhNormalizePinyin(base)
			tokens := zhPinyinToIPA(normalized, tone)
			if !sliceEqual(tokens, tc.wantTokens) {
				t.Errorf("pipeline(%q): got %v, want %v",
					tc.rawPinyin, tokens, tc.wantTokens)
			}
		})
	}
}

// ===========================================================================
// 25. Nil dictionary handling
// ===========================================================================

func TestChinesePhonemizer_NilDictionaries_NoPanic(t *testing.T) {
	// NewChinesePhonemizer(nil, nil) must not panic.
	p := NewChinesePhonemizer(nil, nil)
	if p == nil {
		t.Fatal("NewChinesePhonemizer(nil, nil) returned nil")
	}

	// PhonemizeWithProsody with CJK input must not panic either.
	result, err := p.PhonemizeWithProsody("你好世界")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result == nil {
		t.Fatal("result is nil")
	}
}

func TestChinesePhonemizer_NilDictionaries_CJKSkipped(t *testing.T) {
	// With nil dictionaries, CJK characters are not phonemized to IPA.
	// They pass through as raw characters (via unicode.IsLetter fallback).
	p := NewChinesePhonemizer(nil, nil)
	result, err := p.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// No IPA/tone tokens should be produced for CJK characters without a dictionary.
	rawTokens := unmapPUA(result.Tokens)
	for _, tok := range rawTokens {
		if strings.HasPrefix(tok, "tone") {
			t.Errorf("nil-dict phonemizer produced tone token %q for CJK input", tok)
		}
	}
	// CJK characters pass through as raw letters (not phonemized).
	expected := []string{"你", "好"}
	if !sliceEqual(rawTokens, expected) {
		t.Errorf("nil-dict phonemizer: got %v, want %v (raw pass-through)", rawTokens, expected)
	}
}

func TestChinesePhonemizer_SingleCharDictOnly(t *testing.T) {
	// Only singleChar dict provided; phrases is nil.
	singleDict := map[rune]string{
		'你': "ni3",
		'好': "hao3",
	}
	p := NewChinesePhonemizer(singleDict, nil)
	result, err := p.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	if !sliceContains(rawTokens, "n") {
		t.Errorf("singleChar-only: tokens %v should contain 'n' from 你", rawTokens)
	}
	if !sliceContains(rawTokens, "tone3") {
		t.Errorf("singleChar-only: tokens %v should contain 'tone3' from 好", rawTokens)
	}
}

func TestChinesePhonemizer_PhrasesDictOnly(t *testing.T) {
	// Only phrases dict provided; singleChar is nil.
	phrases := map[string]string{
		"你好": "ni3 hao3",
	}
	p := NewChinesePhonemizer(nil, phrases)
	result, err := p.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens := unmapPUA(result.Tokens)
	// Phrase match should produce IPA tokens.
	if !sliceContains(rawTokens, "n") {
		t.Errorf("phrases-only: tokens %v should contain 'n' from 你好 phrase", rawTokens)
	}

	// A character not covered by any phrase or single-char dict passes through as raw.
	result2, err := p.PhonemizeWithProsody("世")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	rawTokens2 := unmapPUA(result2.Tokens)
	expected := []string{"世"}
	if !sliceEqual(rawTokens2, expected) {
		t.Errorf("phrases-only: single unknown char got %v, want %v (raw pass-through)", rawTokens2, expected)
	}
}

// ===========================================================================
// Helper functions (shared with other *_test.go in same package)
// ===========================================================================

func sliceEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func sliceContains(s []string, target string) bool {
	for _, v := range s {
		if v == target {
			return true
		}
	}
	return false
}

// unmapPUA reverses PUA mapping to get human-readable tokens.
func unmapPUA(tokens []string) []string {
	result := make([]string, len(tokens))
	for i, tok := range tokens {
		runes := []rune(tok)
		if len(runes) == 1 {
			if original, ok := PUAToToken(runes[0]); ok {
				result[i] = original
				continue
			}
		}
		result[i] = tok
	}
	return result
}
