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
