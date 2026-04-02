package phonemize

import (
	"encoding/json"
	"os"
	"testing"
)

// ===========================================================================
// Golden test: cross-platform G2P consistency
//
// Uses the shared fixture tests/fixtures/g2p/phoneme_test_cases.json
// to validate that Go phonemizers produce output consistent with
// Python, Rust, and JS runtimes.
//
// Japanese (ja) is skipped because it requires the openjtalk build tag.
// ===========================================================================

// fixtureFile is the relative path from src/go/phonemize/ to the shared fixture.
const fixtureFile = "../../../tests/fixtures/g2p/phoneme_test_cases.json"

// ---------------------------------------------------------------------------
// Fixture types
// ---------------------------------------------------------------------------

type goldenFixture struct {
	Version        int               `json:"version"`
	TestCases      []goldenTestCase  `json:"test_cases"`
	PUAMapCount    int               `json:"pua_map_count"`
	PUASpotChecks  []puaSpotCheck    `json:"pua_spot_checks"`
	DetectCases    []detectTestCase  `json:"detect_test_cases"`
}

type goldenTestCase struct {
	Language              string   `json:"language"`
	Input                 string   `json:"input"`
	Description           string   `json:"description"`
	ExpectedTokens        []string `json:"expected_tokens,omitempty"`
	ExpectedTokenCountMin int      `json:"expected_token_count_min,omitempty"`
	ExpectedContains      []string `json:"expected_contains,omitempty"`
	ExpectedNotContains   []string `json:"expected_not_contains,omitempty"`
	ExpectedHasQuestion   *bool    `json:"expected_has_question_marker,omitempty"`
	ExpectedContainsAnyTone *bool  `json:"expected_contains_any_tone,omitempty"`
}

type puaSpotCheck struct {
	Token       string `json:"token"`
	Codepoint   string `json:"codepoint"`
	Description string `json:"description"`
}

type detectTestCase struct {
	Input            string `json:"input"`
	ExpectedLanguage string `json:"expected_language"`
	Description      string `json:"description"`
}

// ---------------------------------------------------------------------------
// Fixture loader
// ---------------------------------------------------------------------------

func loadGoldenFixture(t *testing.T) *goldenFixture {
	t.Helper()

	data, err := os.ReadFile(fixtureFile)
	if err != nil {
		t.Skipf("fixture file not found (expected at %s): %v", fixtureFile, err)
	}

	var f goldenFixture
	if err := json.Unmarshal(data, &f); err != nil {
		t.Fatalf("failed to parse fixture: %v", err)
	}
	return &f
}

// casesForLang filters test_cases by language.
func casesForLang(cases []goldenTestCase, lang string) []goldenTestCase {
	var out []goldenTestCase
	for _, c := range cases {
		if c.Language == lang {
			out = append(out, c)
		}
	}
	return out
}

// tokensContain checks if a token is present in the slice.
func tokensContain(tokens []string, target string) bool {
	for _, t := range tokens {
		if t == target {
			return true
		}
	}
	return false
}

// ===========================================================================
// PUA mapping consistency
// ===========================================================================

func TestGolden_PUAMapCount(t *testing.T) {
	f := loadGoldenFixture(t)
	if len(fixedPUA) != f.PUAMapCount {
		t.Errorf("fixedPUA has %d entries, fixture expects %d", len(fixedPUA), f.PUAMapCount)
	}
}

func TestGolden_PUASpotChecks(t *testing.T) {
	f := loadGoldenFixture(t)
	for _, check := range f.PUASpotChecks {
		mapped := RegisterToken(check.Token)
		var cp int
		for _, r := range mapped {
			cp = int(r)
			break
		}
		var expectedCP int64
		// Parse hex codepoint like "0xE000"
		if _, err := parseHexCodepoint(check.Codepoint); err != nil {
			t.Errorf("bad codepoint in fixture for %q: %v", check.Token, err)
			continue
		}
		expectedCP, _ = parseHexCodepoint(check.Codepoint)
		if int64(cp) != expectedCP {
			t.Errorf("PUA mismatch for %q: got U+%04X, expected U+%04X (%s)",
				check.Token, cp, expectedCP, check.Description)
		}
	}
}

func parseHexCodepoint(s string) (int64, error) {
	// Strip "0x" or "0X" prefix
	if len(s) > 2 && (s[:2] == "0x" || s[:2] == "0X") {
		s = s[2:]
	}
	var val int64
	for _, ch := range s {
		val <<= 4
		switch {
		case ch >= '0' && ch <= '9':
			val += int64(ch - '0')
		case ch >= 'a' && ch <= 'f':
			val += int64(ch-'a') + 10
		case ch >= 'A' && ch <= 'F':
			val += int64(ch-'A') + 10
		default:
			return 0, os.ErrInvalid
		}
	}
	return val, nil
}

// ===========================================================================
// Per-language phonemize consistency
// ===========================================================================

// zhGoldenDict builds a minimal single-char pinyin dictionary covering
// all characters used in the ZH fixture test cases.
func zhGoldenDict() map[rune]string {
	return map[rune]string{
		'你': "ni3",
		'好': "hao3",
		'北': "bei3",
		'京': "jing1",
		'欢': "huan1",
		'迎': "ying2",
		'我': "wo3",
		'是': "shi4",
		'学': "xue2",
		'生': "sheng1",
	}
}

// enGoldenDict builds a minimal CMU dictionary covering
// all words used in the EN fixture test cases.
func enGoldenDict() map[string][]string {
	return map[string][]string{
		"hello":   {"HH", "AH0", "L", "OW1"},
		"the":     {"DH", "AH0"},
		"quick":   {"K", "W", "IH1", "K"},
		"brown":   {"B", "R", "AW1", "N"},
		"fox":     {"F", "AA1", "K", "S"},
		"jumps":   {"JH", "AH1", "M", "P", "S"},
		"she's":   {"SH", "IY1", "Z"},
		"she":     {"SH", "IY1"},
		"reading": {"R", "IY1", "D", "IH0", "NG"},
		"a":       {"AH0"},
		"book":    {"B", "UH1", "K"},
	}
}

// Question-type EOS markers emitted by the Japanese phonemizer
var goldenJAQuestionMarkers = map[string]bool{
	"?": true, "?!": true, "?.": true, "?~": true,
}

// Tone tokens emitted by the Chinese phonemizer
var goldenZHToneTokens = map[string]bool{
	"tone1": true, "tone2": true, "tone3": true, "tone4": true, "tone5": true,
}

// ---------------------------------------------------------------------------
// English
// ---------------------------------------------------------------------------

func TestGolden_EN(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewEnglishPhonemizer(enGoldenDict())

	for _, tc := range casesForLang(f.TestCases, "en") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				if !tokensContain(tokens, expected) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Chinese
// ---------------------------------------------------------------------------

func TestGolden_ZH(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewChinesePhonemizer(zhGoldenDict(), nil)

	for _, tc := range casesForLang(f.TestCases, "zh") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			if tc.ExpectedContainsAnyTone != nil && *tc.ExpectedContainsAnyTone {
				// PUA-mapped tone tokens: check raw form
				hasTone := false
				for _, tok := range tokens {
					raw := reverseRegisterToken(tok)
					if goldenZHToneTokens[raw] {
						hasTone = true
						break
					}
				}
				if !hasTone {
					t.Errorf("output missing tone marker for %q: %v", tc.Input, tokens)
				}
			}
		})
	}
}

// reverseRegisterToken converts a PUA-mapped token back to its multi-char form.
func reverseRegisterToken(tok string) string {
	for multi, pua := range fixedPUA {
		if tok == string(pua) {
			return multi
		}
	}
	return tok
}

// ---------------------------------------------------------------------------
// Spanish
// ---------------------------------------------------------------------------

func TestGolden_ES(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewSpanishPhonemizer()

	for _, tc := range casesForLang(f.TestCases, "es") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			// Exact token match
			if len(tc.ExpectedTokens) > 0 {
				if !tokenSliceEqual(tokens, tc.ExpectedTokens) {
					t.Errorf("exact mismatch for %q:\n  got:  %v\n  want: %v",
						tc.Input, tokens, tc.ExpectedTokens)
				}
			}

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				// For PUA tokens like "rr", check both raw and mapped form
				if !tokensContain(tokens, expected) && !tokensContain(tokens, RegisterToken(expected)) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// French
// ---------------------------------------------------------------------------

func TestGolden_FR(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewFrenchPhonemizer()

	for _, tc := range casesForLang(f.TestCases, "fr") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				if !tokensContain(tokens, expected) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Portuguese
// ---------------------------------------------------------------------------

func TestGolden_PT(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewPortuguesePhonemizer()

	for _, tc := range casesForLang(f.TestCases, "pt") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				if !tokensContain(tokens, expected) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Korean
// ---------------------------------------------------------------------------

func TestGolden_KO(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewKoreanPhonemizer()

	for _, tc := range casesForLang(f.TestCases, "ko") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				if !tokensContain(tokens, expected) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Swedish
// ---------------------------------------------------------------------------

func TestGolden_SV(t *testing.T) {
	f := loadGoldenFixture(t)
	p := NewSwedishPhonemizer()

	for _, tc := range casesForLang(f.TestCases, "sv") {
		t.Run(tc.Description, func(t *testing.T) {
			result, err := p.PhonemizeWithProsody(tc.Input)
			if err != nil {
				t.Fatalf("PhonemizeWithProsody(%q) error: %v", tc.Input, err)
			}
			tokens := result.Tokens

			if tc.ExpectedTokenCountMin > 0 && len(tokens) < tc.ExpectedTokenCountMin {
				t.Errorf("token count %d < expected min %d for %q: %v",
					len(tokens), tc.ExpectedTokenCountMin, tc.Input, tokens)
			}

			for _, expected := range tc.ExpectedContains {
				if !tokensContain(tokens, expected) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
		})
	}
}

// ---------------------------------------------------------------------------
// Japanese — skipped (requires openjtalk build tag)
// ---------------------------------------------------------------------------

func TestGolden_JA_Skipped(t *testing.T) {
	t.Skip("Japanese golden tests require the openjtalk build tag; skipping in default build")
}

// ===========================================================================
// Language detection consistency
// ===========================================================================

func TestGolden_DetectLanguage(t *testing.T) {
	f := loadGoldenFixture(t)

	// Collect all expected languages from the fixture
	langSet := make(map[string]bool)
	for _, dc := range f.DetectCases {
		langSet[dc.ExpectedLanguage] = true
	}
	languages := make([]string, 0, len(langSet))
	for lang := range langSet {
		languages = append(languages, lang)
	}

	det := NewUnicodeLanguageDetector(languages, "en")

	for _, dc := range f.DetectCases {
		t.Run(dc.Description, func(t *testing.T) {
			hasKana := det.HasKana(dc.Input)

			votes := make(map[string]int)
			for _, ch := range dc.Input {
				lang := det.DetectChar(ch, hasKana)
				if lang != "" {
					votes[lang]++
				}
			}

			detected := ""
			maxVotes := 0
			for lang, count := range votes {
				if count > maxVotes {
					maxVotes = count
					detected = lang
				}
			}

			if detected != dc.ExpectedLanguage {
				t.Errorf("detection mismatch: got %q, expected %q (votes: %v)",
					detected, dc.ExpectedLanguage, votes)
			}
		})
	}
}

// ===========================================================================
// Fixture schema sanity
// ===========================================================================

func TestGolden_FixtureVersion(t *testing.T) {
	f := loadGoldenFixture(t)
	if f.Version != 1 {
		t.Errorf("fixture version = %d, want 1", f.Version)
	}
}

func TestGolden_AllLanguagesCovered(t *testing.T) {
	f := loadGoldenFixture(t)

	testLangs := make(map[string]bool)
	for _, tc := range f.TestCases {
		testLangs[tc.Language] = true
	}

	expected := []string{"ja", "en", "zh", "ko", "es", "fr", "pt", "sv"}
	for _, lang := range expected {
		if !testLangs[lang] {
			t.Errorf("fixture missing test cases for language %q", lang)
		}
	}
}

// ===========================================================================
// Helpers
// ===========================================================================

func tokenSliceEqual(a, b []string) bool {
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
