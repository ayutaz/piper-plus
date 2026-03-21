package phonemize

import "testing"

func TestParseInlinePhonemes_PlainText(t *testing.T) {
	segs := ParseInlinePhonemes("Hello world")
	if len(segs) != 1 || segs[0].IsPhoneme || segs[0].Text != "Hello world" {
		t.Errorf("unexpected: %+v", segs)
	}
}

func TestParseInlinePhonemes_OnlyPhonemes(t *testing.T) {
	segs := ParseInlinePhonemes("[[ a b c ]]")
	if len(segs) != 1 || !segs[0].IsPhoneme || segs[0].Phonemes != "a b c" {
		t.Errorf("unexpected: %+v", segs)
	}
}

func TestParseInlinePhonemes_Mixed(t *testing.T) {
	segs := ParseInlinePhonemes("Hello [[ h ə l oʊ ]] world")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Text != "Hello " || segs[0].IsPhoneme {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if segs[1].Phonemes != "h ə l oʊ" || !segs[1].IsPhoneme {
		t.Errorf("seg[1]: %+v", segs[1])
	}
	if segs[2].Text != " world" || segs[2].IsPhoneme {
		t.Errorf("seg[2]: %+v", segs[2])
	}
}

func TestParseInlinePhonemes_Empty(t *testing.T) {
	segs := ParseInlinePhonemes("")
	if len(segs) != 0 {
		t.Errorf("expected nil, got %+v", segs)
	}
}

func TestParseInlinePhonemes_Multiple(t *testing.T) {
	segs := ParseInlinePhonemes("[[ a ]] text [[ b ]]")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d", len(segs))
	}
}
