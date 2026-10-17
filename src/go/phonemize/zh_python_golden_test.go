package phonemize

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

// The shipped pinyin dictionaries (installed from the Rust crate's copy) and
// the Python golden output for the shared G2P fixture.
const (
	zhGoldenSinglePath  = "../../rust/piper-plus-g2p/data/pinyin_single.json"
	zhGoldenPhrasesPath = "../../rust/piper-plus-g2p/data/pinyin_phrases.json"
	zhGoldenFixturePath = "../../../tests/fixtures/g2p/phoneme_test_cases_golden.json"
)

// zhGoldenPunctuation is what Python's MultilingualPhonemizer drops and the
// Go ChinesePhonemizer keeps; only spoken tokens are compared.
var zhGoldenPunctuation = map[string]bool{
	" ": true, ".": true, ",": true, "!": true, "?": true, ";": true, ":": true,
}

// TestChinese_MatchesPythonGolden compares Go's Chinese output exactly with
// pypinyin's, through the real dictionary loader and the shipped files. The
// structural golden test (tone marker present, minimum token count) passed
// while every syllable came out as tone 5 with its final dropped.
func TestChinese_MatchesPythonGolden(t *testing.T) {
	single, phrases, err := LoadPinyinDicts(zhGoldenSinglePath, zhGoldenPhrasesPath)
	if err != nil {
		t.Fatalf("shipped pinyin dictionaries must load: %v", err)
	}
	data, err := os.ReadFile(zhGoldenFixturePath)
	if err != nil {
		t.Fatalf("read golden fixture: %v", err)
	}
	var golden struct {
		TestCases []struct {
			Language         string `json:"language"`
			Input            string `json:"input"`
			ExpectedPhonemes string `json:"expected_phonemes"`
		} `json:"test_cases"`
	}
	if err := json.Unmarshal(data, &golden); err != nil {
		t.Fatalf("parse golden fixture: %v", err)
	}

	p := NewChinesePhonemizer(single, phrases)
	checked := 0
	for _, tc := range golden.TestCases {
		// Latin letters and digits go through the multilingual ZH-EN and
		// number handling, not ChinesePhonemizer alone.
		if tc.Language != "zh" || strings.ContainsAny(strings.ToLower(tc.Input), "abcdefghijklmnopqrstuvwxyz0123456789") {
			continue
		}
		checked++
		result, err := p.PhonemizeWithProsody(tc.Input)
		if err != nil {
			t.Errorf("PhonemizeWithProsody(%q): %v", tc.Input, err)
			continue
		}
		var got []string
		for _, tok := range result.Tokens {
			if r := []rune(tok); len(r) == 1 {
				if raw, ok := PUAToToken(r[0]); ok {
					tok = raw
				}
			}
			if !zhGoldenPunctuation[tok] {
				got = append(got, tok)
			}
		}
		want := strings.Fields(tc.ExpectedPhonemes)
		if strings.Join(got, " ") != strings.Join(want, " ") {
			t.Errorf("zh mismatch for %q:\n got: %v\nwant: %v", tc.Input, got, want)
		}
	}
	if checked == 0 {
		t.Fatal("no zh cases in the golden fixture")
	}
}
