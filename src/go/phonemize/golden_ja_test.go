//go:build openjtalk

package phonemize

import (
	"os"
	"testing"
)

// ---------------------------------------------------------------------------
// Japanese — runs only with the openjtalk build tag (CGo + libopenjtalk)
// ---------------------------------------------------------------------------
//
// Same checks as the Rust golden test (src/rust/piper-core/tests/test_g2p_golden.rs)
// for the "ja" cases of tests/fixtures/g2p/phoneme_test_cases.json. The
// `openjtalk` job of .github/workflows/go-ci.yml builds libopenjtalk and runs
// this; before it existed, the default build only had an empty placeholder
// test that always skipped, so the CGo engine was never tested in CI.
//
// The phonemizer returns multi-character tokens as their PUA codepoints
// ("cl" -> U+E005, "?!" -> U+E016), so expected tokens are converted the same
// way before comparing, as the Rust golden test does with token_to_pua.

func TestGolden_JA(t *testing.T) {
	dictPath := os.Getenv("OPENJTALK_DICTIONARY_PATH")
	if dictPath == "" {
		// GitHub Actions sets CI=true; there the dictionary must be provided.
		if os.Getenv("CI") != "" {
			t.Fatal("OPENJTALK_DICTIONARY_PATH is not set")
		}
		t.Skip("OPENJTALK_DICTIONARY_PATH is not set")
	}
	engine, err := NewOpenJTalkEngine(dictPath)
	if err != nil {
		t.Fatalf("NewOpenJTalkEngine(%q): %v", dictPath, err)
	}
	p := NewJapanesePhonemizer(engine)

	questionMarkers := map[string]bool{}
	for _, m := range []string{"?", "?!", "?.", "?~"} {
		questionMarkers[puaForm(m)] = true
	}

	f := loadGoldenFixture(t)
	cases := casesForLang(f.TestCases, "ja")
	if len(cases) == 0 {
		t.Fatal("fixture has no ja cases")
	}
	for _, tc := range cases {
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
				if !tokensContain(tokens, puaForm(expected)) {
					t.Errorf("output missing %q for %q: %v", expected, tc.Input, tokens)
				}
			}
			for _, unexpected := range tc.ExpectedNotContains {
				if tokensContain(tokens, puaForm(unexpected)) {
					t.Errorf("output contains %q for %q: %v", unexpected, tc.Input, tokens)
				}
			}
			if tc.ExpectedHasQuestion != nil {
				hasMarker := false
				for _, tok := range tokens {
					if questionMarkers[tok] {
						hasMarker = true
						break
					}
				}
				if hasMarker != *tc.ExpectedHasQuestion {
					t.Errorf("question marker = %v, want %v for %q: %v",
						hasMarker, *tc.ExpectedHasQuestion, tc.Input, tokens)
				}
			}
		})
	}
}

// puaForm returns the PUA codepoint of a multi-character token in the fixed
// PUA table, or the token itself.
func puaForm(token string) string {
	if r, ok := fixedPUA[token]; ok {
		return string(r)
	}
	return token
}
