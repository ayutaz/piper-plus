package phonemize

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// CustomDictionary: Add and Lookup
// ---------------------------------------------------------------------------

func TestCustomDictionary_AddAndLookup(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil, want phonemes")
	}
	want := []string{"h", "ə", "l", "oʊ"}
	if len(got) != len(want) {
		t.Fatalf("Lookup(\"hello\") = %v, want %v", got, want)
	}
	for i, w := range want {
		if got[i] != w {
			t.Errorf("Lookup(\"hello\")[%d] = %q, want %q", i, got[i], w)
		}
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: case-insensitive lookup
// ---------------------------------------------------------------------------

func TestCustomDictionary_CaseInsensitive(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("Hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil after Add(\"Hello\")")
	}

	got2 := d.Lookup("HELLO")
	if got2 == nil {
		t.Fatal("Lookup(\"HELLO\") returned nil after Add(\"Hello\")")
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: not found returns nil
// ---------------------------------------------------------------------------

func TestCustomDictionary_NotFound(t *testing.T) {
	d := NewCustomDictionary()
	d.Add("hello", []string{"h", "ə", "l", "oʊ"})

	got := d.Lookup("world")
	if got != nil {
		t.Errorf("Lookup(\"world\") = %v, want nil", got)
	}
}

// ---------------------------------------------------------------------------
// LoadDictFile: load from temp file
// ---------------------------------------------------------------------------

func TestLoadDictFile(t *testing.T) {
	content := "hello h ə l oʊ\nworld w ɜː l d\n"
	path := writeTempDict(t, content)

	d, err := LoadDictFile(path)
	if err != nil {
		t.Fatalf("LoadDictFile error: %v", err)
	}

	if d.Len() != 2 {
		t.Fatalf("Len() = %d, want 2", d.Len())
	}

	got := d.Lookup("hello")
	if got == nil {
		t.Fatal("Lookup(\"hello\") returned nil")
	}
	wantHello := []string{"h", "ə", "l", "oʊ"}
	if len(got) != len(wantHello) {
		t.Fatalf("Lookup(\"hello\") = %v, want %v", got, wantHello)
	}
	for i, w := range wantHello {
		if got[i] != w {
			t.Errorf("hello[%d] = %q, want %q", i, got[i], w)
		}
	}

	gotW := d.Lookup("world")
	if gotW == nil {
		t.Fatal("Lookup(\"world\") returned nil")
	}
	wantWorld := []string{"w", "ɜː", "l", "d"}
	if len(gotW) != len(wantWorld) {
		t.Fatalf("Lookup(\"world\") = %v, want %v", gotW, wantWorld)
	}
	for i, w := range wantWorld {
		if gotW[i] != w {
			t.Errorf("world[%d] = %q, want %q", i, gotW[i], w)
		}
	}
}

// ---------------------------------------------------------------------------
// LoadDictFile: comments and blank lines are skipped
// ---------------------------------------------------------------------------

func TestLoadDictFile_Comments(t *testing.T) {
	content := "# This is a comment\n\nhello h ə l oʊ\n# Another comment\nworld w ɜː l d\n\n"
	path := writeTempDict(t, content)

	d, err := LoadDictFile(path)
	if err != nil {
		t.Fatalf("LoadDictFile error: %v", err)
	}

	if d.Len() != 2 {
		t.Errorf("Len() = %d, want 2 (comments and blanks should be skipped)", d.Len())
	}

	if d.Lookup("hello") == nil {
		t.Error("Lookup(\"hello\") returned nil")
	}
	if d.Lookup("world") == nil {
		t.Error("Lookup(\"world\") returned nil")
	}
}

// ---------------------------------------------------------------------------
// CustomDictionary: Len
// ---------------------------------------------------------------------------

func TestCustomDictionary_Len(t *testing.T) {
	d := NewCustomDictionary()
	if d.Len() != 0 {
		t.Errorf("empty dict Len() = %d, want 0", d.Len())
	}

	d.Add("hello", []string{"h", "ə", "l", "oʊ"})
	if d.Len() != 1 {
		t.Errorf("after 1 Add, Len() = %d, want 1", d.Len())
	}

	d.Add("world", []string{"w", "ɜː", "l", "d"})
	if d.Len() != 2 {
		t.Errorf("after 2 Add, Len() = %d, want 2", d.Len())
	}

	// Overwriting an existing entry should not increase count.
	d.Add("hello", []string{"h", "ɛ", "l", "oʊ"})
	if d.Len() != 2 {
		t.Errorf("after overwrite, Len() = %d, want 2", d.Len())
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: BOS/EOS stripping — mock that always returns BOS/EOS
// ---------------------------------------------------------------------------

// dictMockPhonemizer returns predictable tokens with BOS/EOS for testing.
type dictMockPhonemizer struct {
	lang string
	// phonemes maps a lowercased word to its phoneme tokens (without BOS/EOS).
	phonemes map[string][]string
	eosToken string // EOS token this mock produces (default "$")
}

func (m *dictMockPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	word := strings.ToLower(strings.TrimSpace(text))
	ph, ok := m.phonemes[word]
	if !ok {
		return nil, fmt.Errorf("dictMockPhonemizer: unknown word %q", word)
	}
	eos := m.eosToken
	if eos == "" {
		eos = "$"
	}
	// Build tokens: ^ + phonemes + eos
	tokens := make([]string, 0, len(ph)+2)
	tokens = append(tokens, "^")
	tokens = append(tokens, ph...)
	tokens = append(tokens, eos)

	prosody := make([]*ProsodyInfo, len(tokens))
	for i, tok := range tokens {
		if tok == "^" || bosEosTokens[tok] {
			prosody[i] = nil
		} else {
			prosody[i] = &ProsodyInfo{A1: 0, A2: 0, A3: 1}
		}
	}

	return &PhonemizeResult{
		Tokens:   tokens,
		Prosody:  prosody,
		EOSToken: eos,
	}, nil
}

func (m *dictMockPhonemizer) LanguageCode() string {
	return m.lang
}

// assertTokensEqual is a test helper that compares token slices.
func assertTokensEqual(t *testing.T, label string, got, want []string) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("%s: len = %d, want %d\n  got:  %v\n  want: %v", label, len(got), len(want), got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("%s[%d] = %q, want %q", label, i, got[i], want[i])
		}
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: mixed dict + non-dict words — BOS/EOS once only
// ---------------------------------------------------------------------------

func TestDictPhonemizer_MixedWords_BosEosOnce(t *testing.T) {
	// "hello" is in the dictionary; "world" falls through to the mock.
	dict := NewCustomDictionary()
	dict.Add("hello", []string{"h", "ɛ", "l", "oʊ"})

	mock := &dictMockPhonemizer{
		lang:     "en",
		phonemes: map[string][]string{"world": {"w", "ɜː", "l", "d"}},
		eosToken: "$",
	}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// Expect dict phonemes + space + wrapped phonemes, no BOS/EOS in the middle.
	wantTokens := []string{"h", "ɛ", "l", "oʊ", " ", "w", "ɜː", "l", "d"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)

	// No BOS or EOS should appear anywhere in the token list.
	for i, tok := range res.Tokens {
		if bosEosTokens[tok] {
			t.Errorf("unexpected BOS/EOS token at index %d: %q", i, tok)
		}
	}

	if res.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want \"$\"", res.EOSToken)
	}

	// Prosody length must match tokens length.
	if len(res.Prosody) != len(res.Tokens) {
		t.Errorf("prosody len = %d, want %d", len(res.Prosody), len(res.Tokens))
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: all dict words — no wrapped phonemizer called
// ---------------------------------------------------------------------------

func TestDictPhonemizer_AllDictWords(t *testing.T) {
	dict := NewCustomDictionary()
	dict.Add("hello", []string{"h", "ɛ", "l", "oʊ"})
	dict.Add("world", []string{"w", "ɜː", "l", "d"})

	mock := &dictMockPhonemizer{
		lang:     "en",
		phonemes: map[string][]string{},
	}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	wantTokens := []string{"h", "ɛ", "l", "oʊ", " ", "w", "ɜː", "l", "d"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)

	for i, tok := range res.Tokens {
		if bosEosTokens[tok] {
			t.Errorf("unexpected BOS/EOS token at index %d: %q", i, tok)
		}
	}

	// Default EOS when no wrapped phonemizer was called.
	if res.EOSToken != "$" {
		t.Errorf("EOSToken = %q, want \"$\"", res.EOSToken)
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: all non-dict words — fully delegated
// ---------------------------------------------------------------------------

func TestDictPhonemizer_AllNonDictWords(t *testing.T) {
	dict := NewCustomDictionary() // empty dictionary

	mock := &dictMockPhonemizer{
		lang: "en",
		phonemes: map[string][]string{
			"good":    {"ɡ", "ʊ", "d"},
			"morning": {"m", "ɔː", "n", "ɪ", "ŋ"},
		},
		eosToken: "$",
	}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("good morning")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// Both words delegated; BOS/EOS stripped from each; space inserted between.
	wantTokens := []string{"ɡ", "ʊ", "d", " ", "m", "ɔː", "n", "ɪ", "ŋ"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)

	for i, tok := range res.Tokens {
		if bosEosTokens[tok] {
			t.Errorf("unexpected BOS/EOS token at index %d: %q", i, tok)
		}
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: single word (dict hit)
// ---------------------------------------------------------------------------

func TestDictPhonemizer_SingleDictWord(t *testing.T) {
	dict := NewCustomDictionary()
	dict.Add("hello", []string{"h", "ɛ", "l", "oʊ"})

	mock := &dictMockPhonemizer{lang: "en", phonemes: map[string][]string{}}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	wantTokens := []string{"h", "ɛ", "l", "oʊ"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)
}

// ---------------------------------------------------------------------------
// dictPhonemizer: single word (non-dict, delegated)
// ---------------------------------------------------------------------------

func TestDictPhonemizer_SingleNonDictWord(t *testing.T) {
	dict := NewCustomDictionary()

	mock := &dictMockPhonemizer{
		lang:     "en",
		phonemes: map[string][]string{"world": {"w", "ɜː", "l", "d"}},
		eosToken: "$",
	}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("world")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// BOS/EOS stripped even for a single delegated word.
	wantTokens := []string{"w", "ɜː", "l", "d"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)

	for i, tok := range res.Tokens {
		if bosEosTokens[tok] {
			t.Errorf("unexpected BOS/EOS token at index %d: %q", i, tok)
		}
	}
}

// ---------------------------------------------------------------------------
// dictPhonemizer: question EOS token propagated from wrapped phonemizer
// ---------------------------------------------------------------------------

func TestDictPhonemizer_QuestionEOSToken(t *testing.T) {
	dict := NewCustomDictionary()
	dict.Add("are", []string{"ɑː"})

	mock := &dictMockPhonemizer{
		lang:     "en",
		phonemes: map[string][]string{"you": {"j", "uː"}},
		eosToken: "?",
	}
	dp := dict.WrapPhonemizer(mock)

	res, err := dp.PhonemizeWithProsody("are you")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}

	// "?" should be propagated as EOSToken, not "$".
	if res.EOSToken != "?" {
		t.Errorf("EOSToken = %q, want \"?\"", res.EOSToken)
	}

	wantTokens := []string{"ɑː", " ", "j", "uː"}
	assertTokensEqual(t, "tokens", res.Tokens, wantTokens)
}

// ---------------------------------------------------------------------------
// Helper: write a temporary dictionary file
// ---------------------------------------------------------------------------

func writeTempDict(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "dict.txt")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("write temp dict: %v", err)
	}
	return path
}
