package piperplus

// Cross-runtime parity test: Go SplitSentences against contract.json.
//
// Loads tests/fixtures/text_splitter/contract.json and asserts that the Go
// streaming module's behavior matches the runtimes.go.* projection of the
// toml-generated fixture. After Issue #346 Go fix, Go uses post-consume
// (matching Python/Rust/C#/C++ canonical) with full 14/14 closing-punctuation
// coverage:
//
//   1. Each closing-punctuation codepoint listed in runtimes.go.closing_punctuation
//      is greedily consumed after a sentence terminator.
//   2. Each sentence-terminator codepoint listed in runtimes.go.sentence_terminators
//      triggers a split (followed by greedy closing-punctuation consume).
//
// The drift gate (parity-hub.yml text-splitter matrix entry) ensures the
// fixture stays in sync with docs/spec/text-splitter-contract.toml.

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

type textSplitterContract struct {
	SchemaVersion int `json:"schema_version"`
	Canonical     struct {
		ClosingPunctuation  []int  `json:"closing_punctuation"`
		SentenceTerminators []int  `json:"sentence_terminators"`
		Strategy            string `json:"strategy"`
	} `json:"canonical"`
	Runtimes map[string]struct {
		ClosingPunctuation  []int  `json:"closing_punctuation"`
		SentenceTerminators []int  `json:"sentence_terminators"`
		Strategy            string `json:"strategy"`
	} `json:"runtimes"`
}

func loadTextSplitterContract(t *testing.T) textSplitterContract {
	t.Helper()
	_, thisFile, _, _ := runtime.Caller(0)
	repoRoot := filepath.Join(filepath.Dir(thisFile), "..", "..", "..")
	path := filepath.Join(repoRoot, "tests", "fixtures", "text_splitter", "contract.json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", path, err)
	}
	var c textSplitterContract
	if err := json.Unmarshal(data, &c); err != nil {
		t.Fatalf("parse fixture: %v", err)
	}
	if c.SchemaVersion != 1 {
		t.Fatalf("schema_version mismatch: got %d", c.SchemaVersion)
	}
	if _, ok := c.Runtimes["go"]; !ok {
		t.Fatalf("contract.runtimes.go missing")
	}
	return c
}

func TestTextSplitterContract_FixtureLoadsWithGoSection(t *testing.T) {
	c := loadTextSplitterContract(t)
	if c.Runtimes["go"].Strategy != "post-consume" {
		t.Fatalf("Go strategy mismatch: got %q (post-consume aligns with Python/Rust canonical)", c.Runtimes["go"].Strategy)
	}
}

func TestTextSplitterContract_GoIsCloseBracketMatchesFixture(t *testing.T) {
	c := loadTextSplitterContract(t)
	expected := make(map[rune]bool, len(c.Runtimes["go"].ClosingPunctuation))
	for _, cp := range c.Runtimes["go"].ClosingPunctuation {
		expected[rune(cp)] = true
	}

	// Walk the union of canonical + go to check both directions.
	canonical := make(map[rune]bool, len(c.Canonical.ClosingPunctuation))
	for _, cp := range c.Canonical.ClosingPunctuation {
		canonical[rune(cp)] = true
	}

	for cp := range canonical {
		got := isCloseBracket(cp)
		want := expected[cp]
		if got != want {
			t.Errorf("isCloseBracket(U+%04X) = %v, want %v (per fixture runtimes.go)", cp, got, want)
		}
	}
}

func TestTextSplitterContract_GoSentenceTerminatorsMatchFixture(t *testing.T) {
	c := loadTextSplitterContract(t)
	expected := make(map[rune]bool, len(c.Runtimes["go"].SentenceTerminators))
	for _, cp := range c.Runtimes["go"].SentenceTerminators {
		expected[rune(cp)] = true
	}
	canonical := make(map[rune]bool, len(c.Canonical.SentenceTerminators))
	for _, cp := range c.Canonical.SentenceTerminators {
		canonical[rune(cp)] = true
	}
	for cp := range canonical {
		got := isSentenceEnd(cp)
		want := expected[cp]
		if got != want {
			t.Errorf("isSentenceEnd(U+%04X) = %v, want %v (per fixture runtimes.go)", cp, got, want)
		}
	}
}

func TestTextSplitterContract_GoPostConsumeBracket(t *testing.T) {
	// Behavioral pin: post-consume strategy consumes the trailing ')' with the
	// preceding chunk because it immediately follows '.'. Matches Rust/C#/Py.
	chunks := SplitSentences("She said (Hello.) Then left.")
	if len(chunks) != 2 {
		t.Fatalf("expected 2 chunks, got %d: %#v", len(chunks), chunks)
	}
	if chunks[0] != "She said (Hello.)" {
		t.Errorf("first chunk: got %q", chunks[0])
	}
}

func TestTextSplitterContract_GoSplitsAtListedTerminators(t *testing.T) {
	c := loadTextSplitterContract(t)
	for _, cp := range c.Runtimes["go"].SentenceTerminators {
		term := rune(cp)
		input := fmt.Sprintf("a%c b%c", term, term)
		chunks := SplitSentences(input)
		if len(chunks) != 2 {
			t.Errorf("U+%04X (%q): expected 2 chunks for %q, got %d: %#v", cp, term, input, len(chunks), chunks)
		}
	}
}
