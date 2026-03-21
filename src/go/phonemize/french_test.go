package phonemize

import (
	"strings"
	"testing"
)

// ===========================================================================
// Helper: extract raw phonemes from frWord (before PUA mapping)
// ===========================================================================

func frWordPhonemes(word string) []string {
	return frWord(word)
}

// ===========================================================================
// 1. Nasal vowels — am/an, em/en, im/in, om/on, um/un, ym/yn
// ===========================================================================

func TestFrenchNasalVowels_AN_AM(t *testing.T) {
	// am/an -> ɑ̃ (both Go and Python agree)
	tests := []struct {
		word string
		want string // expected nasal vowel phoneme
	}{
		{"france", "\u0251\u0303"},  // an -> ɑ̃
		{"sang", "\u0251\u0303"},    // an word-final -> ɑ̃
		{"camp", "\u0251\u0303"},    // am -> ɑ̃
		{"lampe", "\u0251\u0303"},   // am before consonant -> ɑ̃
		{"chambre", "\u0251\u0303"}, //nolint:misspell // French word — am before b (consonant) -> ɑ̃
		{"champ", "\u0251\u0303"},   // am word-final -> ɑ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasalVowels_EN_EM(t *testing.T) {
	// en/em -> ɑ̃ (merged with an/am in standard French, matches Python reference)
	tests := []struct {
		word string
		want string
	}{
		{"temps", "\u0251\u0303"},    // em -> ɑ̃
		{"entrer", "\u0251\u0303"},   // en -> ɑ̃
		{"ensemble", "\u0251\u0303"}, // en -> ɑ̃
		{"novembre", "\u0251\u0303"}, // em -> ɑ̃
		{"enfant", "\u0251\u0303"},   // en -> ɑ̃
		{"comment", "\u0251\u0303"},  // en word-final -> ɑ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasalVowels_IN_IM(t *testing.T) {
	// in/im -> ɛ̃ (both Go and Python agree)
	tests := []struct {
		word string
		want string
	}{
		{"vin", "\u025b\u0303"},    // in -> ɛ̃
		{"simple", "\u025b\u0303"}, // im -> ɛ̃
		{"fin", "\u025b\u0303"},    // in -> ɛ̃
		{"jardin", "\u025b\u0303"}, // in -> ɛ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasalVowels_ON_OM(t *testing.T) {
	// on/om -> ɔ̃ (both Go and Python agree)
	tests := []struct {
		word string
		want string
	}{
		{"bon", "\u0254\u0303"},   // on -> ɔ̃
		{"nom", "\u0254\u0303"},   // om -> ɔ̃
		{"monde", "\u0254\u0303"}, // on before consonant -> ɔ̃
		{"ombre", "\u0254\u0303"}, // om before consonant -> ɔ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasalVowels_UN_UM(t *testing.T) {
	// un/um -> ɛ̃ (modern French merger; both Go and Python agree)
	tests := []struct {
		word string
		want string
	}{
		{"brun", "\u025b\u0303"},   // un -> ɛ̃
		{"lundi", "\u025b\u0303"},  // un -> ɛ̃
		{"humble", "\u025b\u0303"}, // um -> ɛ̃
		{"parfum", "\u025b\u0303"}, // um -> ɛ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasalVowels_YN_YM(t *testing.T) {
	// yn/ym -> ɛ̃ (both Go and Python agree)
	tests := []struct {
		word string
		want string
	}{
		{"syndicat", "\u025b\u0303"}, // yn -> ɛ̃
		{"symbole", "\u025b\u0303"},  // ym -> ɛ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain nasal %q", tc.word, ph, tc.want)
		}
	}
}

// Nasal vowel non-nasalization: doubled n/m and vowel-following should NOT nasalize.
func TestFrenchNasal_NonNasalCases(t *testing.T) {
	tests := []struct {
		word   string
		nasals []string // these should NOT appear in output
		desc   string
	}{
		// "anne" — doubled 'n' should NOT nasalize
		{"anne", []string{"\u0251\u0303", "\u025b\u0303"}, "doubled n blocks nasal"},
		// "animal" — 'n' followed by vowel 'i' should NOT nasalize
		{"animal", []string{"\u0251\u0303"}, "n before vowel blocks nasal for 'a'"},
		// "ami" — 'm' followed by vowel 'i' should NOT nasalize
		{"ami", []string{"\u0251\u0303", "\u025b\u0303"}, "m before vowel blocks nasal"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		for _, nasal := range tc.nasals {
			for _, p := range ph {
				if p == nasal {
					t.Errorf("frWord(%q) = %v, should NOT contain nasal %q (%s)", tc.word, ph, nasal, tc.desc)
					break
				}
			}
		}
	}

	// Separate test: "immobile" — doubled 'm' blocks nasal for initial 'i'.
	// First phoneme should be plain "i", not a nasal.
	ph := frWordPhonemes("immobile")
	if len(ph) > 0 && (ph[0] == "\u025b\u0303" || ph[0] == "\u0251\u0303") {
		t.Errorf("frWord(\"immobile\") first phoneme = %q, expected plain 'i' (doubled m blocks nasal)", ph[0])
	}
}

// ===========================================================================
// 2. Complex nasal patterns: ain, ein, oin, ien, tion
// ===========================================================================

func TestFrenchNasal_AIN_EIN(t *testing.T) {
	tests := []struct {
		word string
		want string
	}{
		{"pain", "\u025b\u0303"},  // ain -> ɛ̃
		{"main", "\u025b\u0303"},  // ain -> ɛ̃
		{"plein", "\u025b\u0303"}, // ein -> ɛ̃
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected nasal %q", tc.word, ph, tc.want)
		}
	}
}

func TestFrenchNasal_OIN(t *testing.T) {
	// oin -> w + ɛ̃
	ph := frWordPhonemes("loin")
	foundW := false
	foundNasal := false
	for _, p := range ph {
		if p == "w" {
			foundW = true
		}
		if p == "\u025b\u0303" {
			foundNasal = true
		}
	}
	if !foundW || !foundNasal {
		t.Errorf("frWord(\"loin\") = %v, expected 'w' and 'ɛ̃'", ph)
	}
}

func TestFrenchNasal_IEN(t *testing.T) {
	// ien -> j + ɛ̃
	ph := frWordPhonemes("bien")
	foundJ := false
	foundNasal := false
	for _, p := range ph {
		if p == "j" {
			foundJ = true
		}
		if p == "\u025b\u0303" {
			foundNasal = true
		}
	}
	if !foundJ || !foundNasal {
		t.Errorf("frWord(\"bien\") = %v, expected 'j' and 'ɛ̃'", ph)
	}
}

func TestFrenchNasal_TION(t *testing.T) {
	// tion -> s + j + ɔ̃ (without preceding 's')
	ph := frWordPhonemes("nation")
	foundS := false
	foundJ := false
	foundNasal := false
	for _, p := range ph {
		if p == "s" {
			foundS = true
		}
		if p == "j" {
			foundJ = true
		}
		if p == "\u0254\u0303" {
			foundNasal = true
		}
	}
	if !foundS || !foundJ || !foundNasal {
		t.Errorf("frWord(\"nation\") = %v, expected 's', 'j', and 'ɔ̃'", ph)
	}
}

func TestFrenchNasal_STION(t *testing.T) {
	// stion -> s + t + j + ɔ̃ (s already emitted, tion produces t+j+ɔ̃)
	ph := frWordPhonemes("question")
	foundT := false
	foundNasal := false
	for _, p := range ph {
		if p == "t" {
			foundT = true
		}
		if p == "\u0254\u0303" {
			foundNasal = true
		}
	}
	if !foundT || !foundNasal {
		t.Errorf("frWord(\"question\") = %v, expected 't' and 'ɔ̃'", ph)
	}
}

// ===========================================================================
// 3. Silent letters (lettres muettes)
// ===========================================================================

func TestFrenchSilentFinalConsonants(t *testing.T) {
	tests := []struct {
		word         string
		shouldNotEnd string // this phoneme should NOT be the last one
		desc         string
	}{
		// Final 't' is silent in "petit"
		{"petit", "t", "final t should be silent"},
		// Final 'd' is silent in "grand"
		{"grand", "d", "final d should be silent"},
		// Final 's' is silent in "gros"
		{"gros", "s", "final s should be silent"},
		// Final 'x' is silent in "voix"
		{"voix", "k", "final x should be silent"},
		// Final 'z' is silent in "chez"
		{"chez", "z", "final z should be silent"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		if len(ph) > 0 && ph[len(ph)-1] == tc.shouldNotEnd {
			t.Errorf("frWord(%q) = %v, last phoneme should not be %q (%s)", tc.word, ph, tc.shouldNotEnd, tc.desc)
		}
	}
}

func TestFrenchSilentE(t *testing.T) {
	// Word-final 'e' should be silent (not produce a phoneme)
	tests := []struct {
		word    string
		badLast string
	}{
		{"table", "\u0259"},  // final 'e' should not produce schwa
		{"grande", "\u0259"}, // final 'e' should not produce schwa
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		if len(ph) > 0 && ph[len(ph)-1] == tc.badLast {
			t.Errorf("frWord(%q) = %v, final 'e' should be silent (last phoneme should not be %q)", tc.word, ph, tc.badLast)
		}
	}
}

func TestFrenchSilentH(t *testing.T) {
	// 'h' is always silent — should not produce any phoneme
	tests := []struct {
		word string
	}{
		{"homme"},
		{"heure"},
		{"habiter"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		for _, p := range ph {
			if p == "h" {
				t.Errorf("frWord(%q) = %v, 'h' should be silent", tc.word, ph)
				break
			}
		}
	}
}

// ===========================================================================
// 4. Special characters: ç, œ, æ, accented vowels
// ===========================================================================

func TestFrenchCedilla(t *testing.T) {
	// ç -> s
	ph := frWordPhonemes("fran\u00e7ais")
	foundS := false
	for _, p := range ph {
		if p == "s" {
			foundS = true
			break
		}
	}
	if !foundS {
		t.Errorf("frWord(\"français\") = %v, expected 's' for ç", ph)
	}
}

func TestFrenchOE(t *testing.T) {
	// œ -> œ
	ph := frWordPhonemes("\u0153il")
	foundOE := false
	for _, p := range ph {
		if p == "\u0153" {
			foundOE = true
			break
		}
	}
	if !foundOE {
		t.Errorf("frWord(\"œil\") = %v, expected 'œ' phoneme", ph)
	}
}

func TestFrenchAE(t *testing.T) {
	// æ -> e
	ph := frWordPhonemes("\u00e6")
	if len(ph) != 1 || ph[0] != "e" {
		t.Errorf("frWord(\"æ\") = %v, expected [\"e\"]", ph)
	}
}

func TestFrenchAccentedVowels(t *testing.T) {
	tests := []struct {
		char rune
		want string
	}{
		{'\u00e9', "e"},       // é -> e
		{'\u00e8', "\u025b"},  // è -> ɛ
		{'\u00ea', "\u025b"},  // ê -> ɛ
		{'\u00eb', "\u025b"},  // ë -> ɛ
		{'\u00e0', "a"},       // à -> a
		{'\u00e2', "a"},       // â -> a
		{'\u00ee', "i"},       // î -> i
		{'\u00ef', "i"},       // ï -> i
		{'\u00f4', "o"},       // ô -> o
		{'\u00f9', "y_vowel"}, // ù -> y_vowel
		{'\u00fb', "y_vowel"}, // û -> y_vowel
		{'\u00fc', "y_vowel"}, // ü -> y_vowel
	}
	for _, tc := range tests {
		// Test as single-character word
		word := string(tc.char)
		ph := frWordPhonemes(word)
		if len(ph) == 0 {
			t.Errorf("frWord(%q) returned empty", word)
			continue
		}
		// The phoneme should be present somewhere in output
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected to contain %q", word, ph, tc.want)
		}
	}
}

// ===========================================================================
// 5. Vowel digraphs and trigraphs: eau, ou, au, oi, ai, ei, eu
// ===========================================================================

func TestFrenchVowelDigraphs(t *testing.T) {
	tests := []struct {
		word     string
		expected []string // expected phoneme sequence (subset)
		desc     string
	}{
		{"eau", []string{"o"}, "eau -> o"},
		{"beau", []string{"b", "o"}, "eau -> o in beau"},
		{"ou", []string{"u"}, "ou -> u"},
		{"nous", []string{"n", "u"}, "ou -> u in nous"},
		{"au", []string{"o"}, "au -> o"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		for _, exp := range tc.expected {
			found := false
			for _, p := range ph {
				if p == exp {
					found = true
					break
				}
			}
			if !found {
				t.Errorf("frWord(%q) = %v, expected %q (%s)", tc.word, ph, exp, tc.desc)
			}
		}
	}
}

func TestFrenchOI(t *testing.T) {
	// oi -> w + a
	ph := frWordPhonemes("moi")
	foundW := false
	foundA := false
	for _, p := range ph {
		if p == "w" {
			foundW = true
		}
		if p == "a" {
			foundA = true
		}
	}
	if !foundW || !foundA {
		t.Errorf("frWord(\"moi\") = %v, expected 'w' and 'a'", ph)
	}
}

func TestFrenchAI(t *testing.T) {
	// ai -> ɛ
	ph := frWordPhonemes("fait")
	found := false
	for _, p := range ph {
		if p == "\u025b" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"fait\") = %v, expected 'ɛ'", ph)
	}
}

func TestFrenchEI(t *testing.T) {
	// ei -> ɛ
	ph := frWordPhonemes("neige")
	found := false
	for _, p := range ph {
		if p == "\u025b" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"neige\") = %v, expected 'ɛ'", ph)
	}
}

func TestFrenchEU(t *testing.T) {
	// eu -> ø (closed) or œ (open before pronounced consonant)
	tests := []struct {
		word string
		want string
		desc string
	}{
		{"peu", "\u00f8", "eu closed -> ø"}, // peu: no following consonant
		{"jeu", "\u00f8", "eu closed -> ø"}, // jeu: no following consonant
		{"peur", "\u0153", "eu open -> œ"},  // peur: before pronounced 'r'
		{"fleur", "\u0153", "eu open -> œ"}, // fleur: before pronounced 'r'
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected %q (%s)", tc.word, ph, tc.want, tc.desc)
		}
	}
}

// ===========================================================================
// 6. Consonant digraphs: ch, ph, gn, th, qu, gu
// ===========================================================================

func TestFrenchConsonantDigraphs(t *testing.T) {
	tests := []struct {
		word string
		want string
		desc string
	}{
		{"chat", "\u0283", "ch -> ʃ"},
		{"photo", "f", "ph -> f"},
		{"montagne", "\u0272", "gn -> ɲ"},
		{"the", "t", "th -> t"},
		{"quatre", "k", "qu -> k"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected %q (%s)", tc.word, ph, tc.want, tc.desc)
		}
	}
}

func TestFrenchGU(t *testing.T) {
	// gu before e/i -> ɡ (u silent)
	ph := frWordPhonemes("guerre")
	found := false
	for _, p := range ph {
		if p == "\u0261" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"guerre\") = %v, expected 'ɡ' (U+0261) for 'gu' before 'e'", ph)
	}
}

// ===========================================================================
// 7. Soft c/g, intervocalic s, doubled consonants, r
// ===========================================================================

func TestFrenchSoftC(t *testing.T) {
	// c before e/i/y -> s
	tests := []struct {
		word string
	}{
		{"ceci"},
		{"ciel"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		foundS := false
		for _, p := range ph {
			if p == "s" {
				foundS = true
				break
			}
		}
		if !foundS {
			t.Errorf("frWord(%q) = %v, expected 's' for soft c", tc.word, ph)
		}
	}
}

func TestFrenchSoftG(t *testing.T) {
	// g before e/i -> ʒ
	ph := frWordPhonemes("geste")
	found := false
	for _, p := range ph {
		if p == "\u0292" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"geste\") = %v, expected 'ʒ' for soft g", ph)
	}
}

func TestFrenchIntervocalicS(t *testing.T) {
	// s between vowels -> z
	ph := frWordPhonemes("maison")
	found := false
	for _, p := range ph {
		if p == "z" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"maison\") = %v, expected 'z' for intervocalic s", ph)
	}
}

func TestFrenchDoubledConsonants(t *testing.T) {
	// Doubled consonants should produce only one phoneme
	ph := frWordPhonemes("belle")
	count := 0
	for _, p := range ph {
		if p == "l" {
			count++
		}
	}
	if count > 1 {
		t.Errorf("frWord(\"belle\") = %v, doubled 'l' should produce single phoneme", ph)
	}
}

func TestFrenchR(t *testing.T) {
	// r -> ʁ, doubled rr -> single ʁ
	tests := []struct {
		word  string
		count int
	}{
		{"rare", 2},  // two separate r's
		{"terre", 1}, // doubled rr -> single
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		count := 0
		for _, p := range ph {
			if p == "\u0281" {
				count++
			}
		}
		if count != tc.count {
			t.Errorf("frWord(%q) = %v, expected %d ʁ phonemes, got %d", tc.word, ph, tc.count, count)
		}
	}
}

// ===========================================================================
// 8. -er verb ending rules
// ===========================================================================

func TestFrenchER_VerbInfinitive(t *testing.T) {
	// Polysyllabic words ending in -er -> /e/ (verb infinitive)
	tests := []struct {
		word string
		want string
	}{
		{"parler", "e"},  // verb infinitive
		{"manger", "e"},  // verb infinitive
		{"chanter", "e"}, // verb infinitive
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		// Last non-empty phoneme should be 'e' (since final 'r' is absorbed)
		if len(ph) == 0 {
			t.Fatalf("frWord(%q) returned empty", tc.word)
		}
		last := ph[len(ph)-1]
		if last != tc.want {
			t.Errorf("frWord(%q) = %v, last phoneme = %q, expected %q", tc.word, ph, last, tc.want)
		}
	}
}

func TestFrenchER_Exceptions(t *testing.T) {
	// Words in erEH list should NOT produce /e/ but instead /ɛʁ/
	tests := []string{
		"hiver",
		"enfer",
		"amer",
		"cancer",
		"super",
		"fer",
	}
	for _, word := range tests {
		ph := frWordPhonemes(word)
		// Should contain ʁ (the 'r' is pronounced)
		foundR := false
		for _, p := range ph {
			if p == "\u0281" {
				foundR = true
				break
			}
		}
		if !foundR {
			t.Errorf("frWord(%q) = %v, expected 'ʁ' for exception -er word", word, ph)
		}
	}
}

// ===========================================================================
// 9. -ille patterns
// ===========================================================================

func TestFrenchILLE_Default(t *testing.T) {
	// Default: ille -> i + j
	ph := frWordPhonemes("fille")
	foundJ := false
	for _, p := range ph {
		if p == "j" {
			foundJ = true
			break
		}
	}
	if !foundJ {
		t.Errorf("frWord(\"fille\") = %v, expected 'j' for ille", ph)
	}
}

func TestFrenchILLE_Exceptions(t *testing.T) {
	// Exception words: ille -> i + l (not j)
	tests := []string{"ville", "mille", "tranquille"}
	for _, word := range tests {
		ph := frWordPhonemes(word)
		foundL := false
		foundJ := false
		for _, p := range ph {
			if p == "l" {
				foundL = true
			}
			if p == "j" {
				foundJ = true
			}
		}
		if !foundL {
			t.Errorf("frWord(%q) = %v, expected 'l' for ille exception", word, ph)
		}
		if foundJ {
			t.Errorf("frWord(%q) = %v, should NOT contain 'j' for ille exception", word, ph)
		}
	}
}

func TestFrenchAILLE(t *testing.T) {
	// aille -> a + j
	ph := frWordPhonemes("bataille")
	foundA := false
	foundJ := false
	for _, p := range ph {
		if p == "a" {
			foundA = true
		}
		if p == "j" {
			foundJ = true
		}
	}
	if !foundA || !foundJ {
		t.Errorf("frWord(\"bataille\") = %v, expected 'a' and 'j' for aille", ph)
	}
}

func TestFrenchOUILLE(t *testing.T) {
	// ouille -> u + j
	// "bouteille" actually has "eille" pattern, not "ouille"
	// Use "grenouille" for ouille test
	ph := frWordPhonemes("grenouille")
	foundU := false
	foundJ := false
	for _, p := range ph {
		if p == "u" {
			foundU = true
		}
		if p == "j" {
			foundJ = true
		}
	}
	if !foundU || !foundJ {
		t.Errorf("frWord(\"grenouille\") = %v, expected 'u' and 'j' for ouille", ph)
	}
}

func TestFrenchEILLE(t *testing.T) {
	// eille -> ɛ + j
	ph := frWordPhonemes("abeille")
	foundE := false
	foundJ := false
	for _, p := range ph {
		if p == "\u025b" {
			foundE = true
		}
		if p == "j" {
			foundJ = true
		}
	}
	if !foundE || !foundJ {
		t.Errorf("frWord(\"abeille\") = %v, expected 'ɛ' and 'j' for eille", ph)
	}
}

// ===========================================================================
// 10. Semi-vowels: ui -> ɥi, i before vowel -> j
// ===========================================================================

func TestFrenchSemiVowel_UI(t *testing.T) {
	// ui -> ɥ + i
	ph := frWordPhonemes("nuit")
	foundH := false
	for _, p := range ph {
		if p == "\u0265" {
			foundH = true
			break
		}
	}
	if !foundH {
		t.Errorf("frWord(\"nuit\") = %v, expected 'ɥ' (U+0265) for ui", ph)
	}
}

func TestFrenchSemiVowel_I_BeforeVowel(t *testing.T) {
	// i before vowel -> j (except before final silent 'e')
	ph := frWordPhonemes("lion")
	found := false
	for _, p := range ph {
		if p == "j" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"lion\") = %v, expected 'j' for i before vowel", ph)
	}
}

func TestFrenchSemiVowel_I_BeforeFinalE(t *testing.T) {
	// i before word-final 'e' should be 'i' (not 'j')
	// "vie" -> /vi/ not */vj/
	ph := frWordPhonemes("vie")
	foundI := false
	for _, p := range ph {
		if p == "i" {
			foundI = true
			break
		}
	}
	if !foundI {
		t.Errorf("frWord(\"vie\") = %v, expected 'i' (not 'j') before final silent 'e'", ph)
	}
}

// ===========================================================================
// 11. Context-dependent 'e' (schwa vs open ɛ)
// ===========================================================================

func TestFrenchE_Contexts(t *testing.T) {
	tests := []struct {
		word string
		want string
		desc string
	}{
		// 'e' before 2+ consonants -> ɛ (closed syllable)
		{"merci", "\u025b", "e before rci (2+ consonants) -> ɛ"},
		// 'e' before single non-silent consonant -> ɛ
		{"bel", "\u025b", "e before l (pronounced final) -> ɛ"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected %q (%s)", tc.word, ph, tc.want, tc.desc)
		}
	}
}

// ===========================================================================
// 12. Context-dependent 'x'
// ===========================================================================

func TestFrenchX(t *testing.T) {
	// Default x -> ks
	ph := frWordPhonemes("taxi")
	foundK := false
	foundS := false
	for _, p := range ph {
		if p == "k" {
			foundK = true
		}
		if p == "s" {
			foundS = true
		}
	}
	if !foundK || !foundS {
		t.Errorf("frWord(\"taxi\") = %v, expected 'k' and 's' for x", ph)
	}
}

func TestFrenchX_Examen(t *testing.T) {
	// ex + vowel -> ɡz
	ph := frWordPhonemes("examen")
	foundG := false
	foundZ := false
	for _, p := range ph {
		if p == "\u0261" {
			foundG = true
		}
		if p == "z" {
			foundZ = true
		}
	}
	if !foundG || !foundZ {
		t.Errorf("frWord(\"examen\") = %v, expected 'ɡ' and 'z' for ex+vowel", ph)
	}
}

// ===========================================================================
// 13. Open/closed 'o'
// ===========================================================================

func TestFrenchO_OpenClosed(t *testing.T) {
	tests := []struct {
		word string
		want string
		desc string
	}{
		{"mot", "o", "o before silent final t -> closed o"},
		{"porte", "\u0254", "o before rt (pronounced) -> open ɔ"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected %q (%s)", tc.word, ph, tc.want, tc.desc)
		}
	}
}

// ===========================================================================
// 14. Edge cases: empty input, single chars, punctuation
// ===========================================================================

func TestFrenchWord_Empty(t *testing.T) {
	ph := frWordPhonemes("")
	if len(ph) != 0 {
		t.Errorf("frWord(\"\") = %v, expected empty", ph)
	}
}

func TestFrenchWord_SingleVowel(t *testing.T) {
	tests := []struct {
		word string
		want string
	}{
		{"a", "a"},
		{"o", "o"},
		{"i", "i"},
		{"u", "y_vowel"},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		if len(ph) != 1 || ph[0] != tc.want {
			t.Errorf("frWord(%q) = %v, expected [%q]", tc.word, ph, tc.want)
		}
	}
}

// ===========================================================================
// 15. Full sentence: PhonemizeWithProsody integration
// ===========================================================================

func TestFrenchPhonemizer_PhonemizeWithProsody(t *testing.T) {
	p := NewFrenchPhonemizer()
	result, err := p.PhonemizeWithProsody("Bonjour le monde!")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	if len(result.Tokens) == 0 {
		t.Fatal("PhonemizeWithProsody returned empty tokens")
	}
	if result.EOSToken != "!" {
		t.Errorf("EOSToken = %q, want \"!\"", result.EOSToken)
	}
	// Should have prosody info for each token
	if len(result.Prosody) != len(result.Tokens) {
		t.Errorf("prosody count %d != token count %d", len(result.Prosody), len(result.Tokens))
	}
	// Should contain a space separator between words
	joined := strings.Join(result.Tokens, "|")
	if !strings.Contains(joined, " ") {
		t.Errorf("expected space between words in tokens: %v", result.Tokens)
	}
}

func TestFrenchPhonemizer_Punctuation(t *testing.T) {
	p := NewFrenchPhonemizer()
	result, err := p.PhonemizeWithProsody("oui, non!")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	// Should contain punctuation tokens
	hasPunct := false
	for _, tok := range result.Tokens {
		if tok == "," || tok == "!" {
			hasPunct = true
			break
		}
	}
	if !hasPunct {
		t.Errorf("expected punctuation in tokens: %v", result.Tokens)
	}
}

func TestFrenchPhonemizer_EmptyInput(t *testing.T) {
	p := NewFrenchPhonemizer()
	result, err := p.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("expected empty tokens for empty input, got %v", result.Tokens)
	}
}

func TestFrenchPhonemizer_CaseFolding(t *testing.T) {
	p := NewFrenchPhonemizer()
	r1, _ := p.PhonemizeWithProsody("Bonjour")
	r2, _ := p.PhonemizeWithProsody("bonjour")
	if strings.Join(r1.Tokens, "") != strings.Join(r2.Tokens, "") {
		t.Errorf("case folding: %v != %v", r1.Tokens, r2.Tokens)
	}
}

func TestFrenchPhonemizer_Apostrophe(t *testing.T) {
	// Elision: l'ami should split into "l" and "ami"
	p := NewFrenchPhonemizer()
	r1, _ := p.PhonemizeWithProsody("l'ami")
	r2, _ := p.PhonemizeWithProsody("l\u2019ami") // curly apostrophe
	j1 := strings.Join(r1.Tokens, "")
	j2 := strings.Join(r2.Tokens, "")
	if j1 != j2 {
		t.Errorf("apostrophe normalization: %q != %q", j1, j2)
	}
}

// ===========================================================================
// 15b. EOS token tracking
// ===========================================================================

func TestFrenchPhonemizer_EOSToken(t *testing.T) {
	p := NewFrenchPhonemizer()
	tests := []struct {
		text string
		want string
	}{
		{"Bonjour.", "$"},            // period -> default $
		{"Comment allez-vous?", "?"}, // question mark -> ?
		{"Très bien!", "!"},          // exclamation -> !
		{"Bonjour le monde", "$"},    // no punctuation -> default $
		{"Vraiment?!", "!"},          // last punctuation wins
	}
	for _, tc := range tests {
		result, err := p.PhonemizeWithProsody(tc.text)
		if err != nil {
			t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.text, err)
		}
		if result.EOSToken != tc.want {
			t.Errorf("PhonemizeWithProsody(%q).EOSToken = %q, want %q", tc.text, result.EOSToken, tc.want)
		}
	}
}

// ===========================================================================
// 16. Python reference conformance: specific word-level comparisons
// ===========================================================================

// TestFrenchPythonConformance_EN_EM verifies that Go now matches Python for
// en/em nasal vowels. Both produce ɑ̃ (standard French merger of an/am/en/em).
func TestFrenchPythonConformance_EN_EM(t *testing.T) {
	cases := []struct {
		word string
		want string // ɑ̃ — same as Python reference
	}{
		{"temps", "\u0251\u0303"},
		{"entrer", "\u0251\u0303"},
		{"ensemble", "\u0251\u0303"},
		{"enfant", "\u0251\u0303"},
		{"comment", "\u0251\u0303"},
	}
	for _, tc := range cases {
		ph := frWordPhonemes(tc.word)
		found := false
		for _, p := range ph {
			if p == tc.want {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("frWord(%q) = %v, expected nasal %q (Python conformance)", tc.word, ph, tc.want)
		}
	}
}

// TestFrenchPythonConformance_BasicWords checks that basic French words produce
// the same phoneme sequences in Go as in the Python reference.
func TestFrenchPythonConformance_BasicWords(t *testing.T) {
	tests := []struct {
		word string
		want []string // exact phoneme sequence from Python _convert_word
	}{
		// "bonjour": b + ɔ̃ + ʒ + u + ʁ
		// Note: Python produces ɑ̃ for "on" -> no, "on" -> ɔ̃ in both
		{"bonjour", []string{"b", "\u0254\u0303", "\u0292", "u", "\u0281"}},
		// "merci": m + ɛ + ʁ + s + i
		{"merci", []string{"m", "\u025b", "\u0281", "s", "i"}},
		// "chat": ʃ + a
		{"chat", []string{"\u0283", "a"}},
		// "eau": o
		{"eau", []string{"o"}},
		// "oui": w + i (ou -> u, then i)
		// Actually: "oui" — ou -> u, i at end -> "i"
		{"oui", []string{"u", "i"}},
	}
	for _, tc := range tests {
		ph := frWordPhonemes(tc.word)
		if len(ph) != len(tc.want) {
			t.Errorf("frWord(%q) = %v (len %d), want %v (len %d)",
				tc.word, ph, len(ph), tc.want, len(tc.want))
			continue
		}
		for j := range ph {
			if ph[j] != tc.want[j] {
				t.Errorf("frWord(%q)[%d] = %q, want %q (full: %v vs %v)",
					tc.word, j, ph[j], tc.want[j], ph, tc.want)
			}
		}
	}
}

// ===========================================================================
// 17. J phoneme (j -> ʒ)
// ===========================================================================

func TestFrenchJ(t *testing.T) {
	ph := frWordPhonemes("jour")
	found := false
	for _, p := range ph {
		if p == "\u0292" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("frWord(\"jour\") = %v, expected 'ʒ' for j", ph)
	}
}

// ===========================================================================
// 18. Word splitting (frSplit)
// ===========================================================================

func TestFrSplit(t *testing.T) {
	tests := []struct {
		input string
		want  []string
	}{
		{"bonjour le monde", []string{"bonjour", "le", "monde"}},
		{"oui, non!", []string{"oui", ",", "non", "!"}},
		{"l'ami", []string{"l", "ami"}},
		{"l\u2019ami", []string{"l", "ami"}}, // curly apostrophe
		{"", nil},
		{"  spaces  ", []string{"spaces"}},
	}
	for _, tc := range tests {
		got := frSplit(tc.input)
		if len(got) != len(tc.want) {
			t.Errorf("frSplit(%q) = %v (len %d), want %v (len %d)",
				tc.input, got, len(got), tc.want, len(tc.want))
			continue
		}
		for j := range got {
			if got[j] != tc.want[j] {
				t.Errorf("frSplit(%q)[%d] = %q, want %q", tc.input, j, got[j], tc.want[j])
			}
		}
	}
}
