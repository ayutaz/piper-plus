package phonemize

import (
	"testing"
)

func TestRegisterToken_FixedPUA(t *testing.T) {
	tests := []struct {
		token string
		want  rune
	}{
		{"a:", 0xE000},
		{"N_m", 0xE019},
		{"tone1", 0xE046},
		{"tʃ", 0xE054},
		{"ɛ̃", 0xE056},
	}
	for _, tc := range tests {
		got := RegisterToken(tc.token)
		expected := string(tc.want)
		if got != expected {
			t.Errorf("RegisterToken(%q) = %q, want %q (U+%04X)", tc.token, got, expected, tc.want)
		}
	}
}

func TestRegisterToken_SingleChar(t *testing.T) {
	tests := []struct {
		token string
		want  string
	}{
		{"a", "a"},
		{"k", "k"},
	}
	for _, tc := range tests {
		got := RegisterToken(tc.token)
		if got != tc.want {
			t.Errorf("RegisterToken(%q) = %q, want %q", tc.token, got, tc.want)
		}
	}
}

func TestPUAToToken_ReverseMapping(t *testing.T) {
	tests := []struct {
		r    rune
		want string
	}{
		{0xE000, "a:"},
		{0xE019, "N_m"},
		{0xE046, "tone1"},
		{0xE054, "tʃ"},
		{0xE056, "ɛ̃"},
	}
	for _, tc := range tests {
		got, ok := PUAToToken(tc.r)
		if !ok {
			t.Errorf("PUAToToken(U+%04X) returned ok=false, want token %q", tc.r, tc.want)
			continue
		}
		if got != tc.want {
			t.Errorf("PUAToToken(U+%04X) = %q, want %q", tc.r, got, tc.want)
		}
	}
}

func TestMapSequence(t *testing.T) {
	input := []string{"a:", "k", "o", "N_m"}
	got := MapSequence(input)
	expected := []string{"\uE000", "k", "o", "\uE019"}
	if len(got) != len(expected) {
		t.Fatalf("MapSequence length = %d, want %d", len(got), len(expected))
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("MapSequence[%d] = %q, want %q", i, got[i], expected[i])
		}
	}
}

func TestPostProcessIDs_BasicPadding(t *testing.T) {
	ids := []int64{10, 11, 12}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + 10 + pad(0) + 11 + pad(0) + 12 + pad(0) + EOS(2)
	expected := []int64{1, 0, 10, 0, 11, 0, 12, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

func TestPostProcessIDs_SkipDoublePad(t *testing.T) {
	// 0 is the pad token; padding should NOT be inserted after it.
	ids := []int64{10, 0, 11}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "$")
	// Expected: BOS(1) + pad(0) + 10 + pad(0) + 0 + 11 + pad(0) + EOS(2)
	// The existing 0 (pad) does NOT get an additional pad after it.
	expected := []int64{1, 0, 10, 0, 0, 11, 0, 2}
	if len(got) != len(expected) {
		t.Fatalf("PostProcessIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("PostProcessIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}

func TestPostProcessIDs_CustomEOS(t *testing.T) {
	ids := []int64{10, 11}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
		"?": {3},
	}
	got, _ := PostProcessIDs(ids, nil, idMap, "?")
	// Should end with EOS=3 instead of 2.
	lastID := got[len(got)-1]
	if lastID != 3 {
		t.Errorf("PostProcessIDs with custom EOS: last ID = %d, want 3; got %v", lastID, got)
	}
}

func TestTokensToIDs(t *testing.T) {
	idMap := map[string][]int64{
		"\uE000": {10},        // a: -> PUA
		"k":      {20},
		"o":      {30},
		"\uE019": {40},        // N_m -> PUA
	}
	tokens := []string{"a:", "k", "o", "N_m"}
	got := TokensToIDs(tokens, idMap)
	expected := []int64{10, 20, 30, 40}
	if len(got) != len(expected) {
		t.Fatalf("TokensToIDs length = %d, want %d; got %v", len(got), len(expected), got)
	}
	for i := range expected {
		if got[i] != expected[i] {
			t.Errorf("TokensToIDs[%d] = %d, want %d", i, got[i], expected[i])
		}
	}
}
