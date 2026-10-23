package phonemize

// Golden parity with Python for the multilingual phonemizer.
//
// Compares MultilingualPhonemizer.PhonemizeWithLanguage with
// tests/fixtures/g2p/phoneme_test_cases_golden.json, which Python's
// MultilingualPhonemizer generates with the case language as the Latin
// default. piperplus phonemizes with the same call when a language is given
// (WithLanguage, CLI --language), so this is the output a Go caller gets.
//
// Cases known to differ are listed in tests/fixtures/g2p/known_divergences.json
// for the "go" runtime. A difference that is not listed fails, and so does a
// listed case that now matches, so the list shrinks as the linked issues are
// fixed. English words that must never phonemize to nothing are listed in
// tests/fixtures/g2p/english_no_drop_words.json and follow the same rule.
//
// One representation difference is not a divergence: multi-codepoint
// phonemes (rr, tʃ, tone3) are one PUA character here (pua.json) and spelled
// out in the golden. Only the golden side is mapped, so output that forgets
// the PUA encoding still fails.
//
// The dictionaries are the checked-in src/rust/piper-plus-g2p/data/ files, so
// nothing here is skipped when a dictionary is missing: a load failure fails
// the test. Japanese needs OpenJTalk and Korean is absent from the golden (and
// from the trained models), so both are left out of the comparison.

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

const goldenParityRuntime = "go"

// repoRoot is the repository root relative to src/go/phonemize.
const repoRoot = "../../.."

// goldenParityLanguages are the golden languages compared here.
var goldenParityLanguages = map[string]bool{
	"en": true, "es": true, "fr": true, "pt": true, "sv": true, "zh": true,
}

func readRepoJSON(t *testing.T, relative string, v any) {
	t.Helper()
	path := filepath.Join(repoRoot, filepath.FromSlash(relative))
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("cannot read %s: %v", path, err)
	}
	if err := json.Unmarshal(data, v); err != nil {
		t.Fatalf("cannot parse %s: %v", path, err)
	}
}

// goldenParityPhonemizer builds the phonemizer piperplus creates for a
// multilingual model, with the checked-in dictionaries.
func goldenParityPhonemizer(t *testing.T) *MultilingualPhonemizer {
	t.Helper()
	const data = "src/rust/piper-plus-g2p/data/"

	var cmuRaw map[string]string
	readRepoJSON(t, data+"cmudict_data.json", &cmuRaw)
	cmu := make(map[string][]string, len(cmuRaw))
	for word, arpabet := range cmuRaw {
		if tokens := strings.Fields(arpabet); len(tokens) > 0 {
			cmu[word] = tokens
		}
	}
	if len(cmu) == 0 {
		t.Fatal("cmudict_data.json has no entries")
	}

	var singleRaw map[string]string
	readRepoJSON(t, data+"pinyin_single.json", &singleRaw)
	single := make(map[rune]string, len(singleRaw))
	for key, pinyin := range singleRaw {
		cp, err := strconv.Atoi(key)
		if err != nil || cp < 0 || cp > 0x10FFFF {
			t.Fatalf("pinyin_single.json: bad codepoint key %q", key)
		}
		single[rune(cp)] = pinyin
	}

	var phraseRaw map[string][][]string
	readRepoJSON(t, data+"pinyin_phrases.json", &phraseRaw)
	phrases := make(map[string]string, len(phraseRaw))
	for phrase, syllables := range phraseRaw {
		parts := make([]string, 0, len(syllables))
		for _, s := range syllables {
			if len(s) > 0 {
				parts = append(parts, s[0])
			}
		}
		phrases[phrase] = strings.Join(parts, " ")
	}
	if len(single) == 0 || len(phrases) == 0 {
		t.Fatal("pinyin dictionaries have no entries")
	}

	phonemizers := map[string]Phonemizer{
		"en": NewEnglishPhonemizer(cmu),
		"es": NewSpanishPhonemizer(),
		"fr": NewFrenchPhonemizer(),
		"ko": NewKoreanPhonemizer(),
		"pt": NewPortuguesePhonemizer(),
		"sv": NewSwedishPhonemizer(),
		"zh": NewChinesePhonemizer(single, phrases),
	}
	// Sorted, as piperplus builds the list; the Latin default only matters
	// when no language is given.
	languages := []string{"en", "es", "fr", "ko", "pt", "sv", "zh"}
	return NewMultilingualPhonemizer(languages, DefaultLatinLanguage(languages), phonemizers)
}

// goldenPUATable maps the golden spelling of multi-codepoint phonemes to their
// PUA character.
func goldenPUATable(t *testing.T) map[string]string {
	t.Helper()
	var doc struct {
		Entries []struct {
			Token     string `json:"token"`
			Codepoint string `json:"codepoint"`
		} `json:"entries"`
	}
	readRepoJSON(t, "src/python/g2p/piper_plus_g2p/data/pua.json", &doc)
	if len(doc.Entries) == 0 {
		t.Fatal("pua.json has no entries")
	}
	table := make(map[string]string, len(doc.Entries))
	for _, e := range doc.Entries {
		cp, err := strconv.ParseUint(strings.TrimPrefix(e.Codepoint, "0x"), 16, 32)
		if err != nil {
			t.Fatalf("pua.json: bad codepoint %q for %q", e.Codepoint, e.Token)
		}
		table[e.Token] = string(rune(cp))
	}
	return table
}

type runtimeListed struct {
	Runtimes []string `json:"runtimes"`
}

func (r runtimeListed) listsGo() bool {
	for _, rt := range r.Runtimes {
		if rt == goldenParityRuntime {
			return true
		}
	}
	return false
}

// spellPUA joins tokens for a failure message, spelling PUA characters the
// way the golden does so that they are readable.
func spellPUA(pua map[string]string, tokens []string) string {
	spelling := make(map[string]string, len(pua))
	for token, char := range pua {
		spelling[char] = token
	}
	out := make([]string, len(tokens))
	for i, tok := range tokens {
		if s, ok := spelling[tok]; ok {
			tok = s
		}
		out[i] = tok
	}
	return strings.Join(out, " ")
}

// splitGoldenPhonemes splits a golden string. Tokens are joined with one
// space; a word boundary token " " therefore appears as three spaces (two
// empty parts when split).
func splitGoldenPhonemes(s string) []string {
	var tokens []string
	if s == "" {
		return tokens
	}
	emptyParts := 0
	for _, part := range strings.Split(s, " ") {
		if part != "" {
			emptyParts = 0
			tokens = append(tokens, part)
			continue
		}
		emptyParts++
		if emptyParts == 2 {
			emptyParts = 0
			tokens = append(tokens, " ")
		}
	}
	return tokens
}

func TestGoldenParity_MatchesPythonExceptListedDivergences(t *testing.T) {
	pua := goldenPUATable(t)

	var registry struct {
		Divergences []struct {
			runtimeListed
			Language string `json:"language"`
			Input    string `json:"input"`
		} `json:"divergences"`
	}
	readRepoJSON(t, "tests/fixtures/g2p/known_divergences.json", &registry)
	known := make(map[[2]string]bool)
	for _, e := range registry.Divergences {
		if e.listsGo() {
			known[[2]string{e.Language, e.Input}] = true
		}
	}

	var golden struct {
		TestCases []struct {
			Language         string `json:"language"`
			Input            string `json:"input"`
			ExpectedPhonemes string `json:"expected_phonemes"`
		} `json:"test_cases"`
	}
	readRepoJSON(t, "tests/fixtures/g2p/phoneme_test_cases_golden.json", &golden)

	p := goldenParityPhonemizer(t)

	verified, knownCount := 0, 0
	var failures []string
	for _, c := range golden.TestCases {
		if !goldenParityLanguages[c.Language] {
			continue
		}
		expected := splitGoldenPhonemes(c.ExpectedPhonemes)
		for i, tok := range expected {
			if mapped, ok := pua[tok]; ok {
				expected[i] = mapped
			}
		}
		result, err := p.PhonemizeWithLanguage(c.Input, c.Language)
		var actual []string
		if err == nil {
			actual = result.Tokens
		}
		matches := err == nil && tokenSliceEqual(expected, actual)
		verified++

		label := fmt.Sprintf("[%s] %q", c.Language, c.Input)
		listed := known[[2]string{c.Language, c.Input}]
		switch {
		case matches && listed:
			failures = append(failures, label+" now matches; remove it from known_divergences.json")
		case !matches && listed:
			knownCount++
		case !matches:
			got := spellPUA(pua, actual)
			if err != nil {
				got = fmt.Sprintf("(phonemize failed: %v)", err)
			}
			failures = append(failures, fmt.Sprintf("%s\n  expected: %s\n  actual:   %s",
				label, c.ExpectedPhonemes, got))
		}
	}

	if verified == 0 {
		t.Fatal("no golden case compared")
	}
	if len(failures) > 0 {
		t.Fatalf("%d failure(s), %d known, %d cases:\n%s",
			len(failures), knownCount, verified, strings.Join(failures, "\n"))
	}
}

// spokenIgnoredTokens are not phonemes for the no-drop check.
var spokenIgnoredTokens = map[string]bool{
	" ": true, ".": true, ",": true, "!": true, "?": true, ";": true, ":": true,
	"'": true, "\"": true, "-": true,
}

func TestGoldenParity_EnglishWordsAreNotDropped(t *testing.T) {
	var list struct {
		Words      []string `json:"words"`
		KnownDrops []struct {
			runtimeListed
			Word string `json:"word"`
		} `json:"known_drops"`
	}
	readRepoJSON(t, "tests/fixtures/g2p/english_no_drop_words.json", &list)
	knownDrops := make(map[string]bool)
	for _, e := range list.KnownDrops {
		if e.listsGo() {
			knownDrops[e.Word] = true
		}
	}
	p := goldenParityPhonemizer(t)

	checked := 0
	var failures []string
	for _, word := range list.Words {
		var tokens []string
		if result, err := p.PhonemizeWithLanguage(word, "en"); err == nil {
			tokens = result.Tokens
		}
		spoken := false
		for _, tok := range tokens {
			if !spokenIgnoredTokens[tok] {
				spoken = true
				break
			}
		}
		checked++
		listed := knownDrops[word]
		switch {
		case spoken && listed:
			failures = append(failures, fmt.Sprintf("%q is now spoken; remove it from known_drops", word))
		case !spoken && !listed:
			failures = append(failures, fmt.Sprintf("%q produced no phoneme: %q", word, strings.Join(tokens, " ")))
		}
	}

	if checked == 0 {
		t.Fatal("english_no_drop_words.json has no words")
	}
	if len(failures) > 0 {
		t.Fatalf("%s", strings.Join(failures, "\n"))
	}
}
