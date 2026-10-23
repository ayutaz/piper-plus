package phonemize

// English text normalization parity with Python's g2p_en.
//
// Reads tests/fixtures/g2p/english_normalize_cases.json, which
// scripts/build_english_normalize_fixture.py generates from the vendored
// Python code (the Rust and C++ ports read it too):
//
//   - numbers: g2p_en's normalize_numbers(input) (inflect spelling);
//   - tokens: the lowercased words after number expansion, accent stripping,
//     the character filter, the i.e./e.g. replacement and nltk's
//     TweetTokenizer.
//
// Every case must match. All mismatches are reported at once, and a fixture
// with no case fails rather than passing vacuously.

import (
	"fmt"
	"slices"
	"strings"
	"testing"
)

const englishNormalizeFixture = "tests/fixtures/g2p/english_normalize_cases.json"

type englishNormalizeCases struct {
	Numbers []struct {
		Input  string `json:"input"`
		Output string `json:"output"`
	} `json:"numbers"`
	Tokens []struct {
		Input  string   `json:"input"`
		Tokens []string `json:"tokens"`
	} `json:"tokens"`
}

func TestEnglishNormalize_NumbersMatchPython(t *testing.T) {
	var fixture englishNormalizeCases
	readRepoJSON(t, englishNormalizeFixture, &fixture)

	var failures []string
	for _, c := range fixture.Numbers {
		if actual := normalizeNumbers(c.Input); actual != c.Output {
			failures = append(failures, fmt.Sprintf("%q\n  expected: %q\n  actual:   %q",
				c.Input, c.Output, actual))
		}
	}

	if len(fixture.Numbers) == 0 {
		t.Fatal("no 'numbers' case compared")
	}
	if len(failures) > 0 {
		t.Fatalf("%d of %d 'numbers' case(s) differ:\n%s",
			len(failures), len(fixture.Numbers), strings.Join(failures, "\n"))
	}
}

func TestEnglishNormalize_TokensMatchPython(t *testing.T) {
	var fixture englishNormalizeCases
	readRepoJSON(t, englishNormalizeFixture, &fixture)

	var failures []string
	for _, c := range fixture.Tokens {
		words := normalizeAndTokenize(c.Input)
		actual := make([]string, len(words))
		for i, w := range words {
			actual[i] = strings.ToLower(w)
		}
		expected := c.Tokens
		if expected == nil {
			expected = []string{}
		}
		if !slices.Equal(actual, expected) {
			failures = append(failures, fmt.Sprintf("%q\n  expected: %q\n  actual:   %q",
				c.Input, expected, actual))
		}
	}

	if len(fixture.Tokens) == 0 {
		t.Fatal("no 'tokens' case compared")
	}
	if len(failures) > 0 {
		t.Fatalf("%d of %d 'tokens' case(s) differ:\n%s",
			len(failures), len(fixture.Tokens), strings.Join(failures, "\n"))
	}
}

func TestEnglishNormalize_NumberBeyondQuintillionReadDigitByDigit(t *testing.T) {
	got := normalizeNumbers("1234567890123456789012")
	want := "one two three four five six seven eight nine zero one two three four five six " +
		"seven eight nine zero one two"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
	got = normalizeNumbers("999999999999999999999")
	want = "nine hundred ninety-nine quintillion, nine hundred ninety-nine quadrillion, " +
		"nine hundred ninety-nine trillion, nine hundred ninety-nine billion, " +
		"nine hundred ninety-nine million, nine hundred ninety-nine thousand, " +
		"nine hundred ninety-nine"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestEnglishNormalize_AccentsStrippedAndOtherCharactersRemoved(t *testing.T) {
	tests := []struct{ input, want string }{
		{"Crème Brûlée", "Creme Brulee"},
		{"Kelvin", "Kelvin"},
		{"a\tb\nc;d:e\"f", "a b cdef"},
		{"a b　c\u0085d", "a b c d"},
		{"日本 ß æ", "  "},
	}
	for _, tc := range tests {
		if got := stripAccentsAndFilter(tc.input); got != tc.want {
			t.Errorf("stripAccentsAndFilter(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

func TestEnglishNormalize_IeEgReplacedIgnoringCase(t *testing.T) {
	got := replaceIgnoreASCIICase("I.e. x i.E.", "i.e.", "that is")
	if want := "that is x that is"; got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestEnglishNormalize_ShortenHang(t *testing.T) {
	tests := []struct{ input, want string }{
		{"!!!!", "!!!"},
		{"a----b", "a---b"},
		{"aaaa...", "aaaa..."},
	}
	for _, tc := range tests {
		if got := shortenHang(tc.input); got != tc.want {
			t.Errorf("shortenHang(%q) = %q, want %q", tc.input, got, tc.want)
		}
	}
}

func TestEnglishNormalize_TokenizeKeepsCase(t *testing.T) {
	got := normalizeAndTokenize("ChatGPT, e.g. Mr. Smith")
	want := []string{"ChatGPT", ",", "for", "example", "Mr", ".", "Smith"}
	if !slices.Equal(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestEnglishNormalize_DomainWithHyphenAfterTLD(t *testing.T) {
	got := tweetTokenize("foo.bar-baz")
	want := []string{"foo.bar", "-", "baz"}
	if !slices.Equal(got, want) {
		t.Errorf("got %q, want %q", got, want)
	}
}
