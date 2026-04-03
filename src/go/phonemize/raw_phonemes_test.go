package phonemize

import (
	"errors"
	"testing"
)

func TestParseRawPhonemes_Basic(t *testing.T) {
	tokens, err := ParseRawPhonemes("h ə l oʊ")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 4 {
		t.Fatalf("expected 4 tokens, got %d", len(tokens))
	}
	if tokens[0] != "h" || tokens[3] != "oʊ" {
		t.Errorf("unexpected tokens: %v", tokens)
	}
}

func TestParseRawPhonemes_Empty(t *testing.T) {
	_, err := ParseRawPhonemes("")
	if !errors.Is(err, ErrEmptyInput) {
		t.Errorf("expected ErrEmptyInput, got %v", err)
	}
}

func TestParseRawPhonemes_WhitespaceOnly(t *testing.T) {
	_, err := ParseRawPhonemes("   \t  ")
	if !errors.Is(err, ErrEmptyInput) {
		t.Errorf("expected ErrEmptyInput, got %v", err)
	}
}

func TestParseRawPhonemes_SingleToken(t *testing.T) {
	tokens, err := ParseRawPhonemes("a")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 1 || tokens[0] != "a" {
		t.Errorf("unexpected: %v", tokens)
	}
}

func TestParseRawPhonemes_MultipleConsecutive(t *testing.T) {
	tokens, err := ParseRawPhonemes("k o N_n n i ch i h a")
	if err != nil {
		t.Fatal(err)
	}
	expected := []string{"k", "o", "N_n", "n", "i", "ch", "i", "h", "a"}
	if len(tokens) != len(expected) {
		t.Fatalf("expected %d tokens, got %d: %v", len(expected), len(tokens), tokens)
	}
	for i, tok := range tokens {
		if tok != expected[i] {
			t.Errorf("token[%d] = %q, want %q", i, tok, expected[i])
		}
	}
}

func TestParseRawPhonemes_TabSeparated(t *testing.T) {
	tokens, err := ParseRawPhonemes("a\tb\tc")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(tokens), tokens)
	}
}

func TestParseRawPhonemes_MixedWhitespace(t *testing.T) {
	tokens, err := ParseRawPhonemes("  a   b  \t c  ")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(tokens), tokens)
	}
	if tokens[0] != "a" || tokens[1] != "b" || tokens[2] != "c" {
		t.Errorf("unexpected tokens: %v", tokens)
	}
}

func TestParseRawPhonemes_SpecialCharacters(t *testing.T) {
	// IPA symbols and multi-byte characters should be preserved as-is
	tokens, err := ParseRawPhonemes("ʃ ʒ θ ð ŋ ɹ ɑ̃")
	if err != nil {
		t.Fatal(err)
	}
	expected := []string{"ʃ", "ʒ", "θ", "ð", "ŋ", "ɹ", "ɑ̃"}
	if len(tokens) != len(expected) {
		t.Fatalf("expected %d tokens, got %d: %v", len(expected), len(tokens), tokens)
	}
	for i, tok := range tokens {
		if tok != expected[i] {
			t.Errorf("token[%d] = %q, want %q", i, tok, expected[i])
		}
	}
}

func TestParseRawPhonemes_PUATokens(t *testing.T) {
	// Multi-char PUA tokens like N_m, N_uvular should remain as single tokens
	tokens, err := ParseRawPhonemes("sh i N_m b u N_uvular")
	if err != nil {
		t.Fatal(err)
	}
	expected := []string{"sh", "i", "N_m", "b", "u", "N_uvular"}
	if len(tokens) != len(expected) {
		t.Fatalf("expected %d tokens, got %d: %v", len(expected), len(tokens), tokens)
	}
	for i, tok := range tokens {
		if tok != expected[i] {
			t.Errorf("token[%d] = %q, want %q", i, tok, expected[i])
		}
	}
}

func TestParseRawPhonemes_NewlineOnly(t *testing.T) {
	_, err := ParseRawPhonemes("\n\n")
	if !errors.Is(err, ErrEmptyInput) {
		t.Errorf("expected ErrEmptyInput for newline-only input, got %v", err)
	}
}

func TestParseRawPhonemes_ToneTokens(t *testing.T) {
	// Chinese tone tokens
	tokens, err := ParseRawPhonemes("n i tone3 h aʊ tone3")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 6 {
		t.Fatalf("expected 6 tokens, got %d: %v", len(tokens), tokens)
	}
	if tokens[2] != "tone3" || tokens[5] != "tone3" {
		t.Errorf("tone tokens not preserved: %v", tokens)
	}
}

func TestParseRawPhonemes_LongSequence(t *testing.T) {
	// Simulate a long utterance with many phonemes
	// k o N_n n i ch i w a t o u ky o u e y o u k o s o = 23 tokens
	tokens, err := ParseRawPhonemes("k o N_n n i ch i w a t o u ky o u e y o u k o s o")
	if err != nil {
		t.Fatal(err)
	}
	if len(tokens) != 23 {
		t.Fatalf("expected 23 tokens, got %d: %v", len(tokens), tokens)
	}
}
