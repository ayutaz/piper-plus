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

func TestParseInlinePhonemes_ConsecutiveBlocks(t *testing.T) {
	segs := ParseInlinePhonemes("[[ a b ]][[ c d ]]")
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if !segs[0].IsPhoneme || segs[0].Phonemes != "a b" {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if !segs[1].IsPhoneme || segs[1].Phonemes != "c d" {
		t.Errorf("seg[1]: %+v", segs[1])
	}
}

func TestParseInlinePhonemes_ConsecutiveBlocksWithSpace(t *testing.T) {
	segs := ParseInlinePhonemes("[[ a ]] [[ b ]]")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if !segs[0].IsPhoneme || segs[0].Phonemes != "a" {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if segs[1].IsPhoneme || segs[1].Text != " " {
		t.Errorf("seg[1] should be plain space: %+v", segs[1])
	}
	if !segs[2].IsPhoneme || segs[2].Phonemes != "b" {
		t.Errorf("seg[2]: %+v", segs[2])
	}
}

func TestParseInlinePhonemes_TextAndPhonemesMixed(t *testing.T) {
	segs := ParseInlinePhonemes("Say [[ h ɛ l oʊ ]] and then [[ w ɜ l d ]]!")
	if len(segs) != 5 {
		t.Fatalf("expected 5 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Text != "Say " || segs[0].IsPhoneme {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if !segs[1].IsPhoneme || segs[1].Phonemes != "h ɛ l oʊ" {
		t.Errorf("seg[1]: %+v", segs[1])
	}
	if segs[2].Text != " and then " || segs[2].IsPhoneme {
		t.Errorf("seg[2]: %+v", segs[2])
	}
	if !segs[3].IsPhoneme || segs[3].Phonemes != "w ɜ l d" {
		t.Errorf("seg[3]: %+v", segs[3])
	}
	if segs[4].Text != "!" || segs[4].IsPhoneme {
		t.Errorf("seg[4]: %+v", segs[4])
	}
}

func TestParseInlinePhonemes_EmptyBlock(t *testing.T) {
	segs := ParseInlinePhonemes("before [[  ]] after")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Text != "before " {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	// Empty block: whitespace is trimmed by regex, so Phonemes should be ""
	if !segs[1].IsPhoneme || segs[1].Phonemes != "" {
		t.Errorf("seg[1] should be empty phoneme block: %+v", segs[1])
	}
	if segs[2].Text != " after" {
		t.Errorf("seg[2]: %+v", segs[2])
	}
}

func TestParseInlinePhonemes_UnclosedBracket(t *testing.T) {
	// Unclosed [[ should be treated as plain text
	segs := ParseInlinePhonemes("hello [[ unclosed")
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment for unclosed bracket, got %d: %+v", len(segs), segs)
	}
	if segs[0].IsPhoneme || segs[0].Text != "hello [[ unclosed" {
		t.Errorf("unclosed bracket should be plain text: %+v", segs[0])
	}
}

func TestParseInlinePhonemes_SingleBrackets(t *testing.T) {
	// Single brackets [ ] should not be parsed as phoneme blocks
	segs := ParseInlinePhonemes("test [ not phonemes ] here")
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment for single brackets, got %d: %+v", len(segs), segs)
	}
	if segs[0].IsPhoneme || segs[0].Text != "test [ not phonemes ] here" {
		t.Errorf("single brackets should be plain text: %+v", segs[0])
	}
}

func TestParseInlinePhonemes_NestedBrackets(t *testing.T) {
	// Nested [[ [[ ]] ]] — regex should match the innermost valid pair
	segs := ParseInlinePhonemes("[[ [[ nested ]] ]]")
	// The regex captures the first [[ ... ]] match
	if len(segs) == 0 {
		t.Fatal("expected at least 1 segment")
	}
	// Verify at least one phoneme segment was extracted
	hasPhoneme := false
	for _, seg := range segs {
		if seg.IsPhoneme {
			hasPhoneme = true
			break
		}
	}
	if !hasPhoneme {
		t.Errorf("expected at least one phoneme segment in nested case: %+v", segs)
	}
}

func TestParseInlinePhonemes_IPASymbols(t *testing.T) {
	segs := ParseInlinePhonemes("word [[ ʃ ʒ θ ð ŋ ]] end")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if !segs[1].IsPhoneme || segs[1].Phonemes != "ʃ ʒ θ ð ŋ" {
		t.Errorf("IPA symbols not preserved: %+v", segs[1])
	}
}

func TestParseInlinePhonemes_LeadingTrailingText(t *testing.T) {
	segs := ParseInlinePhonemes("prefix[[ ph ]]suffix")
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Text != "prefix" {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if !segs[1].IsPhoneme || segs[1].Phonemes != "ph" {
		t.Errorf("seg[1]: %+v", segs[1])
	}
	if segs[2].Text != "suffix" {
		t.Errorf("seg[2]: %+v", segs[2])
	}
}

func TestParseInlinePhonemes_OnlyWhitespace(t *testing.T) {
	segs := ParseInlinePhonemes("   ")
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].IsPhoneme || segs[0].Text != "   " {
		t.Errorf("whitespace should be plain text: %+v", segs[0])
	}
}

func TestParseInlinePhonemes_ManyBlocks(t *testing.T) {
	segs := ParseInlinePhonemes("[[ a ]] b [[ c ]] d [[ e ]]")
	if len(segs) != 5 {
		t.Fatalf("expected 5 segments, got %d: %+v", len(segs), segs)
	}
	if !segs[0].IsPhoneme || segs[0].Phonemes != "a" {
		t.Errorf("seg[0]: %+v", segs[0])
	}
	if segs[1].IsPhoneme || segs[1].Text != " b " {
		t.Errorf("seg[1]: %+v", segs[1])
	}
	if !segs[2].IsPhoneme || segs[2].Phonemes != "c" {
		t.Errorf("seg[2]: %+v", segs[2])
	}
	if segs[3].IsPhoneme || segs[3].Text != " d " {
		t.Errorf("seg[3]: %+v", segs[3])
	}
	if !segs[4].IsPhoneme || segs[4].Phonemes != "e" {
		t.Errorf("seg[4]: %+v", segs[4])
	}
}
