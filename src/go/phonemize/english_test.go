package phonemize

import (
	"strings"
	"testing"
)

// ===========================================================================
// Helper: build a mock CMU dict for testing
// ===========================================================================

// testCMUDict returns a small CMU dictionary sufficient for testing.
// Entries match g2p-en output for the same words.
func testCMUDict() map[string][]string {
	return map[string][]string{
		// Basic words
		"hello":       {"HH", "AH0", "L", "OW1"},
		"world":       {"W", "ER1", "L", "D"},
		"cat":         {"K", "AE1", "T"},
		"dog":         {"D", "AO1", "G"},
		"the":         {"DH", "AH0"},
		"a":           {"AH0"},
		"go":          {"G", "OW1"},
		"car":         {"K", "AA1", "R"},
		"bird":        {"B", "ER1", "D"},
		"today":       {"T", "AH0", "D", "EY1"},
		"are":         {"AA1", "R"},
		"you":         {"Y", "UW1"},
		"how":         {"HH", "AW1"},
		"information": {"IH2", "N", "F", "ER0", "M", "EY1", "SH", "AH0", "N"},
		"letter":      {"L", "EH1", "T", "ER0"},
		"but":         {"B", "AH1", "T"},
		"and":         {"AH0", "N", "D"},
		"not":         {"N", "AA1", "T"},
		"is":          {"IH1", "Z"},
		"with":        {"W", "IH1", "DH"},
		"about":       {"AH0", "B", "AW1", "T"},
		"she":         {"SH", "IY1"},
		"he":          {"HH", "IY1"},
		"we":          {"W", "IY1"},
		"they":        {"DH", "EY1"},
		"don't":       {"D", "OW1", "N", "T"},
		"i'm":         {"AY1", "M"},
		"can't":       {"K", "AE1", "N", "T"},
		"it's":        {"IH1", "T", "S"},
		"i":           {"AY1"},
		"computer":    {"K", "AH0", "M", "P", "Y", "UW1", "T", "ER0"},
		"test":        {"T", "EH1", "S", "T"},
		"beautiful":   {"B", "Y", "UW1", "T", "AH0", "F", "AH0", "L"},
		"music":       {"M", "Y", "UW1", "Z", "IH0", "K"},
		"thing":       {"TH", "IH1", "NG"},
		"measure":     {"M", "EH1", "ZH", "ER0"},
		"judge":       {"JH", "AH1", "JH"},
		"church":      {"CH", "ER1", "CH"},
		"father":      {"F", "AA1", "DH", "ER0"},
		"vision":      {"V", "IH1", "ZH", "AH0", "N"},
		"boy":         {"B", "OY1"},
		"book":        {"B", "UH1", "K"},
	}
}

// ===========================================================================
// 1. ARPAbet -> IPA conversion table (must match Python ARPABET_TO_IPA)
// ===========================================================================

func TestArpabetToIPA_AllEntries(t *testing.T) {
	// Every ARPAbet consonant/vowel base symbol must map to the correct IPA.
	// This table is taken directly from the Python reference implementation.
	expected := map[string]string{
		"AA": "ɑ",
		"AE": "æ",
		"AH": "ʌ",
		"AO": "ɔː",
		"AW": "aʊ",
		"AY": "aɪ",
		"B":  "b",
		"CH": "tʃ",
		"D":  "d",
		"DH": "ð",
		"EH": "ɛ",
		"ER": "ɚ",
		"EY": "eɪ",
		"F":  "f",
		"G":  "ɡ", // U+0261, not ASCII g
		"HH": "h",
		"IH": "ɪ",
		"IY": "iː",
		"JH": "dʒ",
		"K":  "k",
		"L":  "l",
		"M":  "m",
		"N":  "n",
		"NG": "ŋ",
		"OW": "oʊ",
		"OY": "ɔɪ",
		"P":  "p",
		"R":  "ɹ",
		"S":  "s",
		"SH": "ʃ",
		"T":  "t",
		"TH": "θ",
		"UH": "ʊ",
		"UW": "uː",
		"V":  "v",
		"W":  "w",
		"Y":  "j",
		"Z":  "z",
		"ZH": "ʒ",
	}

	// Verify the Go map has all expected entries
	if len(arpabetToIPA) != len(expected) {
		t.Errorf("arpabetToIPA has %d entries, expected %d", len(arpabetToIPA), len(expected))
	}

	for arpa, wantIPA := range expected {
		gotIPA, ok := arpabetToIPA[arpa]
		if !ok {
			t.Errorf("arpabetToIPA missing entry for %q", arpa)
			continue
		}
		if gotIPA != wantIPA {
			t.Errorf("arpabetToIPA[%q] = %q (U+%04X...), want %q (U+%04X...)",
				arpa, gotIPA, []rune(gotIPA)[0], wantIPA, []rune(wantIPA)[0])
		}
	}

	// Also verify no extra entries exist in Go that are absent from Python
	for arpa := range arpabetToIPA {
		if _, ok := expected[arpa]; !ok {
			t.Errorf("arpabetToIPA has unexpected entry %q -> %q", arpa, arpabetToIPA[arpa])
		}
	}
}

// ===========================================================================
// 2. parseArpabet — stress digit extraction
// ===========================================================================

func TestParseArpabet(t *testing.T) {
	tests := []struct {
		token    string
		wantBase string
		wantStr  int
	}{
		{"AH0", "AH", 0},
		{"AH1", "AH", 1},
		{"AH2", "AH", 2},
		{"B", "B", -1},
		{"NG", "NG", -1},
		{"OW1", "OW", 1},
		{"IH0", "IH", 0},
		{"", "", -1},
		{"ER0", "ER", 0},
		{"ER1", "ER", 1},
		{"ER2", "ER", 2},
	}
	for _, tc := range tests {
		base, stress := parseArpabet(tc.token)
		if base != tc.wantBase || stress != tc.wantStr {
			t.Errorf("parseArpabet(%q) = (%q, %d), want (%q, %d)",
				tc.token, base, stress, tc.wantBase, tc.wantStr)
		}
	}
}

// ===========================================================================
// 3. arpabetTokenToIPA — single-token conversion with stress
// ===========================================================================

func TestArpabetTokenToIPA(t *testing.T) {
	tests := []struct {
		token      string
		wantIPA    string
		wantStress int
	}{
		// Consonant — no stress
		{"B", "b", -1},
		{"SH", "ʃ", -1},
		{"TH", "θ", -1},
		{"NG", "ŋ", -1},
		{"CH", "tʃ", -1},
		{"JH", "dʒ", -1},
		{"ZH", "ʒ", -1},
		{"HH", "h", -1},
		// Vowel with stress
		{"OW1", "oʊ", 1},
		{"AO2", "ɔː", 2},
		{"IH0", "ɪ", 0},
		{"EY1", "eɪ", 1},
		// AH special case: AH0 -> schwa
		{"AH0", "ə", 0},
		{"AH1", "ʌ", 1},
		{"AH2", "ʌ", 2},
		// ER (basic — context-dependent rules handled in convertWordToIPA)
		{"ER0", "ɚ", 0},
		// Unknown token — returned as-is
		{"XYZ", "XYZ", -1},
		// Punctuation pass-through
		{",", ",", -1},
	}
	for _, tc := range tests {
		ipa, stress := arpabetTokenToIPA(tc.token)
		if ipa != tc.wantIPA || stress != tc.wantStress {
			t.Errorf("arpabetTokenToIPA(%q) = (%q, %d), want (%q, %d)",
				tc.token, ipa, stress, tc.wantIPA, tc.wantStress)
		}
	}
}

// ===========================================================================
// 4. convertWordToIPA — context-dependent rules (AA+R, stressed ER)
// ===========================================================================

func TestConvertWordToIPA(t *testing.T) {
	t.Run("AA+R merge", func(t *testing.T) {
		// "car" -> K AA1 R -> should produce ɑːɹ merged token
		tokens := []string{"K", "AA1", "R"}
		result := convertWordToIPA(tokens)
		found := false
		for _, ph := range result {
			if ph.ipa == "ɑːɹ" {
				found = true
				if ph.stress != 1 {
					t.Errorf("AA+R merged token stress = %d, want 1", ph.stress)
				}
			}
		}
		if !found {
			t.Error("convertWordToIPA([K, AA1, R]) did not produce ɑːɹ")
		}
	})

	t.Run("stressed ER", func(t *testing.T) {
		// "bird" -> B ER1 D -> ER1 should become ɜː
		tokens := []string{"B", "ER1", "D"}
		result := convertWordToIPA(tokens)
		found := false
		for _, ph := range result {
			if ph.ipa == "ɜː" {
				found = true
				if ph.stress != 1 {
					t.Errorf("stressed ER token stress = %d, want 1", ph.stress)
				}
			}
		}
		if !found {
			t.Error("convertWordToIPA([B, ER1, D]) did not produce ɜː")
		}
	})

	t.Run("unstressed ER", func(t *testing.T) {
		// "letter" -> L EH1 T ER0 -> ER0 should become ɚ
		tokens := []string{"L", "EH1", "T", "ER0"}
		result := convertWordToIPA(tokens)
		found := false
		for _, ph := range result {
			if ph.ipa == "ɚ" {
				found = true
			}
		}
		if !found {
			t.Error("convertWordToIPA([L, EH1, T, ER0]) did not produce ɚ")
		}
	})

	t.Run("AA without following R", func(t *testing.T) {
		// AA1 not followed by R should stay as ɑ (not merge)
		tokens := []string{"AA1", "T"}
		result := convertWordToIPA(tokens)
		if len(result) != 2 {
			t.Fatalf("expected 2 phonemes, got %d", len(result))
		}
		if result[0].ipa != "ɑ" {
			t.Errorf("AA1 without R: ipa = %q, want ɑ", result[0].ipa)
		}
	})

	t.Run("ER2 secondary stress", func(t *testing.T) {
		// ER2 should NOT trigger the stressed ER rule (only ER1 does)
		tokens := []string{"ER2"}
		result := convertWordToIPA(tokens)
		if len(result) != 1 {
			t.Fatalf("expected 1 phoneme, got %d", len(result))
		}
		if result[0].ipa != "ɚ" {
			t.Errorf("ER2 ipa = %q, want ɚ", result[0].ipa)
		}
	})
}

// ===========================================================================
// 5. tokenizeText — text splitting into words and punctuation
// ===========================================================================

func TestTokenizeText(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  []textToken
	}{
		{
			name:  "simple words",
			input: "hello world",
			want: []textToken{
				{text: "hello", kind: tokenWord},
				{text: "world", kind: tokenWord},
			},
		},
		{
			name:  "words with punctuation",
			input: "Hello, world!",
			want: []textToken{
				{text: "Hello", kind: tokenWord},
				{text: ",", kind: tokenPunct},
				{text: "world", kind: tokenWord},
				{text: "!", kind: tokenPunct},
			},
		},
		{
			name:  "apostrophe in word",
			input: "don't",
			want: []textToken{
				{text: "don't", kind: tokenWord},
			},
		},
		{
			name:  "multiple apostrophes",
			input: "I'm don't can't",
			want: []textToken{
				{text: "I'm", kind: tokenWord},
				{text: "don't", kind: tokenWord},
				{text: "can't", kind: tokenWord},
			},
		},
		{
			name:  "empty string",
			input: "",
			want:  nil,
		},
		{
			name:  "only whitespace",
			input: "   \t\n  ",
			want:  nil,
		},
		{
			name:  "only punctuation",
			input: "...!?",
			want: []textToken{
				{text: ".", kind: tokenPunct},
				{text: ".", kind: tokenPunct},
				{text: ".", kind: tokenPunct},
				{text: "!", kind: tokenPunct},
				{text: "?", kind: tokenPunct},
			},
		},
		{
			name:  "numbers are skipped",
			input: "hello 123 world",
			want: []textToken{
				{text: "hello", kind: tokenWord},
				{text: "world", kind: tokenWord},
			},
		},
		{
			name:  "hyphens are skipped (split words)",
			input: "self-driving",
			want: []textToken{
				{text: "self", kind: tokenWord},
				{text: "driving", kind: tokenWord},
			},
		},
		{
			name:  "mixed case",
			input: "Hello WORLD test",
			want: []textToken{
				{text: "Hello", kind: tokenWord},
				{text: "WORLD", kind: tokenWord},
				{text: "test", kind: tokenWord},
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := tokenizeText(tc.input)
			if len(got) != len(tc.want) {
				t.Fatalf("tokenizeText(%q): got %d tokens, want %d\n  got:  %+v\n  want: %+v",
					tc.input, len(got), len(tc.want), got, tc.want)
			}
			for i := range tc.want {
				if got[i].text != tc.want[i].text || got[i].kind != tc.want[i].kind {
					t.Errorf("tokenizeText(%q)[%d] = {%q, %d}, want {%q, %d}",
						tc.input, i, got[i].text, got[i].kind,
						tc.want[i].text, tc.want[i].kind)
				}
			}
		})
	}
}

// ===========================================================================
// 6. Function words set — must match Python _FUNCTION_WORDS exactly
// ===========================================================================

func TestFunctionWords_MatchesPython(t *testing.T) {
	// Complete function word set from Python reference implementation.
	pythonFunctionWords := map[string]bool{
		// articles / determiners
		"a": true, "an": true, "the": true,
		// pronouns
		"i": true, "me": true, "my": true, "mine": true, "myself": true,
		"you": true, "your": true, "yours": true, "yourself": true,
		"he": true, "him": true, "his": true, "himself": true,
		"she": true, "her": true, "hers": true, "herself": true,
		"it": true, "its": true, "itself": true,
		"we": true, "us": true, "our": true, "ours": true, "ourselves": true,
		"they": true, "them": true, "their": true, "theirs": true, "themselves": true,
		// be-verbs
		"am": true, "is": true, "are": true, "was": true, "were": true,
		"be": true, "been": true, "being": true,
		// auxiliaries
		"have": true, "has": true, "had": true, "having": true,
		"do": true, "does": true, "did": true,
		"will": true, "would": true, "can": true, "could": true,
		"shall": true, "should": true, "may": true, "might": true, "must": true,
		// prepositions
		"at": true, "by": true, "for": true, "from": true, "in": true,
		"of": true, "on": true, "to": true, "with": true,
		"about": true, "after": true, "before": true, "between": true,
		"into": true, "through": true, "under": true,
		// conjunctions
		"and": true, "but": true, "or": true, "nor": true,
		"so": true, "yet": true,
		"if": true, "that": true, "than": true,
		"when": true, "while": true, "as": true,
		"because": true, "since": true,
		// others
		"not": true, "no": true,
	}

	// Check Go has all Python entries
	for word := range pythonFunctionWords {
		if !functionWords[word] {
			t.Errorf("Go functionWords missing Python entry: %q", word)
		}
	}

	// Check Python has all Go entries (no extras in Go)
	for word := range functionWords {
		if !pythonFunctionWords[word] {
			t.Errorf("Go functionWords has extra entry not in Python: %q", word)
		}
	}

	// Count match
	if len(functionWords) != len(pythonFunctionWords) {
		t.Errorf("functionWords count: Go=%d, Python=%d", len(functionWords), len(pythonFunctionWords))
	}
}

// ===========================================================================
// 7. Function word destressing
// ===========================================================================

func TestFunctionWordDestressing(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "the" is a function word — stress should be removed
	result, err := p.PhonemizeWithProsody("the cat")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// Find the position of "the" tokens (before the space)
	spaceIdx := -1
	for i, tok := range result.Tokens {
		if tok == " " {
			spaceIdx = i
			break
		}
	}
	if spaceIdx < 0 {
		t.Fatal("expected space between words in 'the cat'")
	}

	// "the" phonemes are before the space — none should have stress marker
	for i := 0; i < spaceIdx; i++ {
		if result.Tokens[i] == "ˈ" || result.Tokens[i] == "ˌ" {
			t.Errorf("function word 'the' has stress marker at position %d", i)
		}
	}

	// "cat" should have stress marker ˈ
	foundCatStress := false
	for i := spaceIdx + 1; i < len(result.Tokens); i++ {
		if result.Tokens[i] == "ˈ" {
			foundCatStress = true
			break
		}
	}
	if !foundCatStress {
		t.Error("content word 'cat' should have primary stress marker ˈ")
	}
}

func TestFunctionWordDestressing_AllAuxiliaries(t *testing.T) {
	// Test that common function words are destressed
	funcWordCMU := map[string][]string{
		"is":   {"IH1", "Z"},
		"are":  {"AA1", "R"},
		"but":  {"B", "AH1", "T"},
		"and":  {"AH0", "N", "D"},
		"not":  {"N", "AA1", "T"},
		"with": {"W", "IH1", "DH"},
		"you":  {"Y", "UW1"},
		"he":   {"HH", "IY1"},
		"she":  {"SH", "IY1"},
		"we":   {"W", "IY1"},
		"they": {"DH", "EY1"},
	}
	for word, arpabet := range funcWordCMU {
		dict := map[string][]string{word: arpabet}
		p := NewEnglishPhonemizer(dict)
		result, err := p.PhonemizeWithProsody(word)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", word, err)
		}
		for _, tok := range result.Tokens {
			if tok == "ˈ" || tok == "ˌ" {
				t.Errorf("function word %q should not have stress marker, found in tokens %v",
					word, result.Tokens)
				break
			}
		}
	}
}

// ===========================================================================
// 8. Stress markers — primary and secondary
// ===========================================================================

func TestStressMarkers_Primary(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "hello" -> HH AH0 L OW1 -> h ə l ˈ o ʊ
	result, err := p.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	foundPrimary := false
	for i, tok := range result.Tokens {
		if tok == "ˈ" {
			foundPrimary = true
			// Next token should be the stressed vowel "o"
			if i+1 < len(result.Tokens) && result.Tokens[i+1] != "o" {
				t.Errorf("primary stress marker should precede 'o', got %q", result.Tokens[i+1])
			}
		}
	}
	if !foundPrimary {
		t.Error("'hello' should have primary stress marker ˈ")
	}
}

func TestStressMarkers_Secondary(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "information" -> IH2 N F ER0 M EY1 SH AH0 N
	// IH2 has secondary stress -> should produce ˌ
	result, err := p.PhonemizeWithProsody("information")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	foundSecondary := false
	for _, tok := range result.Tokens {
		if tok == "ˌ" {
			foundSecondary = true
			break
		}
	}
	if !foundSecondary {
		t.Error("'information' should have secondary stress marker ˌ")
	}
}

// ===========================================================================
// 9. Prosody A2 values — stress level mapping
// ===========================================================================

func TestProsody_A2_StressMapping(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "go" -> G OW1 -> primary stress -> A2 should be 2
	result, err := p.PhonemizeWithProsody("go")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	foundA2_2 := false
	for _, pr := range result.Prosody {
		if pr != nil && pr.A2 == 2 {
			foundA2_2 = true
			break
		}
	}
	if !foundA2_2 {
		t.Error("'go' with primary stress should have A2=2")
	}
}

func TestProsody_A2_Secondary(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "information" has IH2 -> secondary stress -> A2 should be 1
	result, err := p.PhonemizeWithProsody("information")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	foundA2_1 := false
	for _, pr := range result.Prosody {
		if pr != nil && pr.A2 == 1 {
			foundA2_1 = true
			break
		}
	}
	if !foundA2_1 {
		t.Error("'information' should have A2=1 for secondary stress")
	}
}

func TestProsody_A1_AlwaysZero(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("Hello world")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	for i, pr := range result.Prosody {
		if pr != nil && pr.A1 != 0 {
			t.Errorf("Prosody[%d].A1 = %d, want 0 (English A1 should always be 0)", i, pr.A1)
		}
	}
}

func TestProsody_A3_WordPhonemeCount(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "cat" -> K AE1 T -> k æ t -> 3 IPA chars
	result, err := p.PhonemizeWithProsody("cat")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// All non-nil prosody entries should have the same A3
	a3Set := make(map[int]bool)
	for _, pr := range result.Prosody {
		if pr != nil {
			a3Set[pr.A3] = true
		}
	}
	// Single word -> single A3 value (excluding stress marker prosody which
	// also has the same A3)
	if len(a3Set) != 1 {
		t.Errorf("'cat' prosody has multiple A3 values: %v, expected single value", a3Set)
	}
}

// ===========================================================================
// 10. Exact phoneme output for known words
// ===========================================================================

func TestExactOutput_Hello(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// "hello" -> HH AH0 L OW1 -> h ə l ˈ o ʊ
	// After PUA mapping, each token should be a single codepoint.
	got := joinTokens(result.Tokens)
	want := "həlˈoʊ"
	if got != want {
		t.Errorf("phonemize(\"hello\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

func TestExactOutput_Cat(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("cat")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "kˈæt"
	if got != want {
		t.Errorf("phonemize(\"cat\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

func TestExactOutput_Car(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "car" -> K AA1 R -> AA+R merge -> k ˈ ɑ ː ɹ
	result, err := p.PhonemizeWithProsody("car")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "kˈɑːɹ"
	if got != want {
		t.Errorf("phonemize(\"car\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

func TestExactOutput_Bird(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "bird" -> B ER1 D -> ER1 -> ɜː -> b ˈ ɜ ː d
	result, err := p.PhonemizeWithProsody("bird")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "bˈɜːd"
	if got != want {
		t.Errorf("phonemize(\"bird\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

func TestExactOutput_TheCat(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "the cat" -> ð ə   k ˈ æ t  (function word "the" destressed)
	result, err := p.PhonemizeWithProsody("the cat")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "ðə kˈæt"
	if got != want {
		t.Errorf("phonemize(\"the cat\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

func TestExactOutput_Information(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "information" -> IH2 N F ER0 M EY1 SH AH0 N
	// -> ˌ ɪ n f ɚ m ˈ e ɪ ʃ ə n
	result, err := p.PhonemizeWithProsody("information")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "ˌɪnfɚmˈeɪʃən"
	if got != want {
		t.Errorf("phonemize(\"information\") = %q, want %q\n  tokens: %v", got, want, result.Tokens)
	}
}

// ===========================================================================
// 11. Apostrophe-containing words
// ===========================================================================

func TestApostropheWords(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	tests := []struct {
		input     string
		expectIPA bool // expect IPA output (not letter fallback)
	}{
		{"don't", true},
		{"can't", true},
		{"it's", true},
		{"i'm", true},
	}

	for _, tc := range tests {
		result, err := p.PhonemizeWithProsody(tc.input)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.input, err)
		}
		if len(result.Tokens) == 0 {
			t.Errorf("PhonemizeWithProsody(%q) returned empty tokens", tc.input)
			continue
		}

		if tc.expectIPA {
			// Should have been found in dict, not letter-by-letter fallback
			joined := joinTokens(result.Tokens)
			// Letter fallback would contain ASCII letters; IPA output shouldn't
			// contain pure ASCII lowercase except for common IPA (b, d, f, etc.)
			if strings.Contains(joined, "'") {
				t.Errorf("PhonemizeWithProsody(%q) output %q contains apostrophe (fallback?)",
					tc.input, joined)
			}
		}
	}
}

// ===========================================================================
// 12. Case normalization
// ===========================================================================

func TestCaseNormalization(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "HELLO", "Hello", "hello" should all produce the same output
	variants := []string{"hello", "Hello", "HELLO", "hElLo"}
	var results []string

	for _, v := range variants {
		result, err := p.PhonemizeWithProsody(v)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", v, err)
		}
		results = append(results, joinTokens(result.Tokens))
	}

	for i := 1; i < len(results); i++ {
		if results[i] != results[0] {
			t.Errorf("Case normalization: %q -> %q, but %q -> %q",
				variants[0], results[0], variants[i], results[i])
		}
	}
}

// ===========================================================================
// 13. Empty/whitespace input
// ===========================================================================

func TestEmptyInput(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("empty input should produce 0 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("EOS token = %q, want '$'", result.EOSToken)
	}
}

func TestWhitespaceOnlyInput(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	for _, input := range []string{" ", "  ", "\t", "\n", " \t\n "} {
		result, err := p.PhonemizeWithProsody(input)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", input, err)
		}
		if len(result.Tokens) != 0 {
			t.Errorf("whitespace input %q should produce 0 tokens, got %d: %v",
				input, len(result.Tokens), result.Tokens)
		}
	}
}

// ===========================================================================
// 14. Word boundary spaces
// ===========================================================================

func TestWordBoundarySpaces(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Should contain a space token between words
	foundSpace := false
	for _, tok := range result.Tokens {
		if tok == " " {
			foundSpace = true
			break
		}
	}
	if !foundSpace {
		t.Error("'hello world' should have space token between words")
	}

	// No leading space
	if result.Tokens[0] == " " {
		t.Error("should not have leading space token")
	}

	// No trailing space
	if result.Tokens[len(result.Tokens)-1] == " " {
		t.Error("should not have trailing space token")
	}
}

func TestSingleWordNoSpace(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	for _, tok := range result.Tokens {
		if tok == " " {
			t.Error("single word 'hello' should not contain space token")
		}
	}
}

// ===========================================================================
// 15. Punctuation handling
// ===========================================================================

func TestPunctuation_AttachesToPreviousWord(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("Hello, world")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Find comma position
	commaIdx := -1
	for i, tok := range result.Tokens {
		if tok == "," {
			commaIdx = i
			break
		}
	}
	if commaIdx < 0 {
		t.Fatal("expected comma token in 'Hello, world'")
	}

	// No space before comma
	if commaIdx > 0 && result.Tokens[commaIdx-1] == " " {
		t.Error("comma should attach to previous word (no space before)")
	}

	// Space after comma (before next word)
	if commaIdx+1 < len(result.Tokens) && result.Tokens[commaIdx+1] != " " {
		t.Error("expected space after comma before next word")
	}
}

func TestPunctuation_QuestionMark(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("Hello?")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Last token should be "?"
	last := result.Tokens[len(result.Tokens)-1]
	if last != "?" {
		t.Errorf("last token should be '?', got %q", last)
	}

	// No space before question mark
	if len(result.Tokens) >= 2 && result.Tokens[len(result.Tokens)-2] == " " {
		t.Error("question mark should attach to previous word (no space before)")
	}
}

func TestPunctuation_MultiplePunctuations(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("Hello! World.")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	tokens := result.Tokens
	foundExcl := false
	foundDot := false
	for _, tok := range tokens {
		if tok == "!" {
			foundExcl = true
		}
		if tok == "." {
			foundDot = true
		}
	}
	if !foundExcl {
		t.Error("expected '!' token")
	}
	if !foundDot {
		t.Error("expected '.' token")
	}
}

// ===========================================================================
// 16. Phoneme/prosody length alignment
// ===========================================================================

func TestTokenProsodyLengthMatch(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	texts := []string{
		"hello",
		"hello world",
		"Hello, how are you today?",
		"the cat",
		"information",
		"don't",
	}

	for _, text := range texts {
		result, err := p.PhonemizeWithProsody(text)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", text, err)
		}
		if len(result.Tokens) != len(result.Prosody) {
			t.Errorf("PhonemizeWithProsody(%q): token count %d != prosody count %d",
				text, len(result.Tokens), len(result.Prosody))
		}
	}
}

// ===========================================================================
// 17. OOV (out-of-vocabulary) fallback — letter-by-letter
// ===========================================================================

func TestOOVFallback(t *testing.T) {
	// Empty dictionary — everything is OOV
	dict := map[string][]string{}
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("xyz")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// OOV fallback: each letter becomes a token
	got := joinTokens(result.Tokens)
	if got != "xyz" {
		t.Errorf("OOV fallback for 'xyz' = %q, want 'xyz'", got)
	}

	// A3 should be the letter count of the word
	for _, pr := range result.Prosody {
		if pr != nil && pr.A3 != 3 {
			t.Errorf("OOV word A3 = %d, want 3 (letter count of 'xyz')", pr.A3)
		}
	}
}

// ===========================================================================
// 18. LanguageCode
// ===========================================================================

func TestLanguageCode(t *testing.T) {
	p := NewEnglishPhonemizer(nil)
	if got := p.LanguageCode(); got != "en" {
		t.Errorf("LanguageCode() = %q, want 'en'", got)
	}
}

// ===========================================================================
// 19. EOS token
// ===========================================================================

func TestEOSToken(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	tests := []struct {
		input   string
		wantEOS string
	}{
		{"hello", "$"},
		{"hello world", "$"},
		{"", "$"},
		{"  ", "$"},
		// Sentence-final punctuation determines EOS token
		{"hello?", "?"},
		{"how are you?", "?"},
		{"hello!", "!"},
		{"go!", "!"},
		// Period maps to default "$"
		{"hello.", "$"},
		{"hello world.", "$"},
		// Last punctuation wins
		{"hello! world?", "?"},
		{"hello? world!", "!"},
		// Only punctuation
		{"?", "?"},
		{"!", "!"},
		{".", "$"},
	}

	for _, tc := range tests {
		result, err := p.PhonemizeWithProsody(tc.input)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.input, err)
		}
		if result.EOSToken != tc.wantEOS {
			t.Errorf("PhonemizeWithProsody(%q).EOSToken = %q, want %q",
				tc.input, result.EOSToken, tc.wantEOS)
		}
	}
}

// ===========================================================================
// 20. PUA mapping pass-through for English (all tokens should be single rune)
// ===========================================================================

func TestPUAMapping_EnglishTokensAreSingleRune(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	texts := []string{
		"hello",
		"world",
		"information",
		"car",
		"bird",
		"the cat",
		"Hello, world!",
		"church",
		"judge",
		"measure",
		"thing",
		"vision",
	}

	for _, text := range texts {
		result, err := p.PhonemizeWithProsody(text)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", text, err)
		}
		for i, tok := range result.Tokens {
			if runeCount(tok) != 1 {
				t.Errorf("PhonemizeWithProsody(%q) token[%d] = %q (%d runes), want single rune",
					text, i, tok, runeCount(tok))
			}
		}
	}
}

// ===========================================================================
// 21. Multi-character IPA split verification
// ===========================================================================

func TestMultiCharIPA_SplitIntoSingleRunes(t *testing.T) {
	// Verify that multi-character IPA strings from arpabetToIPA are properly
	// split into individual rune tokens by the phonemizer.
	// E.g., "oʊ" (OW) should become two tokens: "o" and "ʊ"
	dict := map[string][]string{
		"go": {"G", "OW1"},
	}
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("go")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Expected: ˈ ɡ o ʊ  (stress marker before the stressed vowel, then
	// 'ɡ' might be before or after depending on whether G gets stress)
	// Actually: G -> ɡ (no stress, consonant), OW1 -> oʊ (stress=1)
	// So: ɡ ˈ o ʊ
	tokens := result.Tokens
	foundO := false
	foundU := false
	for _, tok := range tokens {
		if tok == "o" {
			foundO = true
		}
		if tok == "ʊ" {
			foundU = true
		}
	}
	if !foundO || !foundU {
		t.Errorf("'go' should split OW -> 'o' + 'ʊ', got tokens: %v", tokens)
	}
}

// ===========================================================================
// 22. Punctuation set completeness
// ===========================================================================

func TestPunctuationSet(t *testing.T) {
	// Python _PUNCTUATION = set(",.;:!?")
	expectedPunct := map[rune]bool{
		'.': true, ',': true, '!': true, '?': true, ';': true, ':': true,
	}

	if len(punctuationSet) != len(expectedPunct) {
		t.Errorf("punctuationSet has %d entries, expected %d", len(punctuationSet), len(expectedPunct))
	}

	for ch := range expectedPunct {
		if !punctuationSet[ch] {
			t.Errorf("punctuationSet missing %q", string(ch))
		}
	}

	for ch := range punctuationSet {
		if !expectedPunct[ch] {
			t.Errorf("punctuationSet has extra %q", string(ch))
		}
	}
}

// ===========================================================================
// 23. Edge cases
// ===========================================================================

func TestEdgeCase_OnlyPunctuation(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("...")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Should have 3 period tokens
	dotCount := 0
	for _, tok := range result.Tokens {
		if tok == "." {
			dotCount++
		}
	}
	if dotCount != 3 {
		t.Errorf("'...' should produce 3 dot tokens, got %d", dotCount)
	}
}

func TestEdgeCase_PunctuationOnly_NoSpace(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	result, err := p.PhonemizeWithProsody("!?")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	for _, tok := range result.Tokens {
		if tok == " " {
			t.Error("punctuation-only input should not produce space tokens")
		}
	}
}

func TestEdgeCase_WordAfterPunctuation(t *testing.T) {
	dict := testCMUDict()
	p := NewEnglishPhonemizer(dict)

	// "Hello. World" -> "." attaches to "Hello", space before "World"
	result, err := p.PhonemizeWithProsody("Hello. World")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	// Find the period
	dotIdx := -1
	for i, tok := range result.Tokens {
		if tok == "." {
			dotIdx = i
			break
		}
	}
	if dotIdx < 0 {
		t.Fatal("expected '.' token")
	}

	// Space should appear after period (before "World")
	if dotIdx+1 < len(result.Tokens) && result.Tokens[dotIdx+1] != " " {
		t.Errorf("expected space after period, got %q", result.Tokens[dotIdx+1])
	}
}

func TestEdgeCase_SingleCharWord(t *testing.T) {
	dict := map[string][]string{
		"a": {"AH0"},
		"i": {"AY1"},
	}
	p := NewEnglishPhonemizer(dict)

	// "a" is a function word -> destressed
	result, err := p.PhonemizeWithProsody("a")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if len(result.Tokens) == 0 {
		t.Error("'a' should produce at least one token")
	}
	for _, tok := range result.Tokens {
		if tok == "ˈ" || tok == "ˌ" {
			t.Error("function word 'a' should not have stress marker")
		}
	}

	// "i" is also a function word
	result, err = p.PhonemizeWithProsody("I")
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	for _, tok := range result.Tokens {
		if tok == "ˈ" || tok == "ˌ" {
			t.Error("function word 'I' should not have stress marker")
		}
	}
}

// ===========================================================================
// 24. Nil / empty dictionary handling
// ===========================================================================

func TestNilDict_NoPanic(t *testing.T) {
	// NewEnglishPhonemizer(nil) must not panic, and PhonemizeWithProsody
	// must also work without panicking.
	p := NewEnglishPhonemizer(nil)
	if p == nil {
		t.Fatal("NewEnglishPhonemizer(nil) returned nil")
	}

	result, err := p.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody with nil dict error: %v", err)
	}
	if len(result.Tokens) == 0 {
		t.Error("expected non-empty tokens from nil-dict phonemizer")
	}
	if result.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want '$'", result.EOSToken)
	}
}

func TestNilDict_LetterByLetterOutput(t *testing.T) {
	// With a nil dictionary every word should use letter-by-letter fallback.
	p := NewEnglishPhonemizer(nil)

	result, err := p.PhonemizeWithProsody("cat")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "cat"
	if got != want {
		t.Errorf("nil dict phonemize(\"cat\") = %q, want %q (letter-by-letter)", got, want)
	}

	// A3 should equal the letter count of the word (3 for "cat")
	for i, pr := range result.Prosody {
		if pr != nil && pr.A3 != 3 {
			t.Errorf("nil dict Prosody[%d].A3 = %d, want 3", i, pr.A3)
		}
	}
}

func TestEmptyDict_LetterByLetterOutput(t *testing.T) {
	// An empty (non-nil) map should behave the same as nil: all words are OOV.
	p := NewEnglishPhonemizer(map[string][]string{})

	result, err := p.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("error: %v", err)
	}

	got := joinTokens(result.Tokens)
	want := "hello"
	if got != want {
		t.Errorf("empty dict phonemize(\"hello\") = %q, want %q (letter-by-letter)", got, want)
	}

	// Token and prosody lengths must still match
	if len(result.Tokens) != len(result.Prosody) {
		t.Errorf("token count %d != prosody count %d", len(result.Tokens), len(result.Prosody))
	}

	// A3 should equal the letter count (5 for "hello")
	for i, pr := range result.Prosody {
		if pr != nil && pr.A3 != 5 {
			t.Errorf("empty dict Prosody[%d].A3 = %d, want 5", i, pr.A3)
		}
	}
}

// ===========================================================================
// Helpers
// ===========================================================================

// joinTokens concatenates tokens into a single string for easy comparison.
func joinTokens(tokens []string) string {
	return strings.Join(tokens, "")
}
