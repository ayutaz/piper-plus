package piperplus

import (
	"strings"
	"testing"
	"unicode/utf8"
)

// ---------------------------------------------------------------------------
// SplitSentences
// ---------------------------------------------------------------------------

func TestSplitSentences_English(t *testing.T) {
	got := SplitSentences("Hello world. How are you? I'm fine!")
	want := []string{"Hello world.", "How are you?", "I'm fine!"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_Japanese(t *testing.T) {
	got := SplitSentences("こんにちは。お元気ですか？元気です！")
	want := []string{"こんにちは。", "お元気ですか？", "元気です！"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_Mixed(t *testing.T) {
	got := SplitSentences("Hello. こんにちは。")
	want := []string{"Hello.", "こんにちは。"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_NoSplit(t *testing.T) {
	got := SplitSentences("Hello world")
	want := []string{"Hello world"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	if got[0] != want[0] {
		t.Errorf("expected %q, got %q", want[0], got[0])
	}
}

func TestSplitSentences_Empty(t *testing.T) {
	got := SplitSentences("")
	if got != nil {
		t.Errorf("expected nil, got %v", got)
	}
}

func TestSplitSentences_KeepPunctuation(t *testing.T) {
	got := SplitSentences("Hello.")
	want := []string{"Hello."}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	if got[0] != want[0] {
		t.Errorf("expected %q, got %q", want[0], got[0])
	}
}

func TestSplitSentences_QuotesNotSplit(t *testing.T) {
	// Periods inside quotes should not cause a split.
	got := SplitSentences(`He said "Hello. Goodbye." Then left.`)
	want := []string{`He said "Hello. Goodbye."`, "Then left."}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_ParensNotSplit(t *testing.T) {
	got := SplitSentences("Check (see fig. 1) for details. Done.")
	want := []string{"Check (see fig. 1) for details.", "Done."}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_JapaneseQuotes(t *testing.T) {
	got := SplitSentences("彼は「元気です。」と言った。終わり。")
	// The 。 inside 「」 should not split.
	want := []string{"彼は「元気です。」と言った。", "終わり。"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

func TestSplitSentences_WhitespaceOnly(t *testing.T) {
	got := SplitSentences("   ")
	if got != nil {
		t.Errorf("expected nil for whitespace-only input, got %v", got)
	}
}

func TestSplitSentences_Chinese(t *testing.T) {
	got := SplitSentences("你好。今天天气很好！你觉得呢？")
	want := []string{"你好。", "今天天气很好！", "你觉得呢？"}

	if len(got) != len(want) {
		t.Fatalf("expected %d sentences, got %d: %v", len(want), len(got), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("sentence[%d]: expected %q, got %q", i, want[i], got[i])
		}
	}
}

// ---------------------------------------------------------------------------
// SplitTextChunks
// ---------------------------------------------------------------------------

func TestSplitTextChunks_Basic(t *testing.T) {
	text := "Hello world. How are you? I'm fine! Thank you very much."
	chunks := SplitTextChunks(text, 50)

	for i, c := range chunks {
		n := utf8.RuneCountInString(c)
		if n > 50 {
			// Only allowed if it's a single sentence.
			sentences := SplitSentences(c)
			if len(sentences) > 1 {
				t.Errorf("chunk[%d] has %d runes (>50) and %d sentences: %q",
					i, n, len(sentences), c)
			}
		}
	}

	// All original text should be recoverable.
	joined := strings.Join(chunks, " ")
	for _, s := range SplitSentences(text) {
		if !strings.Contains(joined, s) {
			t.Errorf("missing sentence in chunks: %q", s)
		}
	}
}

func TestSplitTextChunks_SingleLongSentence(t *testing.T) {
	long := "This is a very long sentence that exceeds the maximum character limit by quite a lot and should not be broken."
	chunks := SplitTextChunks(long, 20)

	// A single sentence exceeding maxChars is kept as-is.
	if len(chunks) != 1 {
		t.Fatalf("expected 1 chunk for single long sentence, got %d: %v", len(chunks), chunks)
	}
	if chunks[0] != long {
		t.Errorf("expected chunk to equal original, got %q", chunks[0])
	}
}

func TestSplitTextChunks_Empty(t *testing.T) {
	chunks := SplitTextChunks("", 50)
	if chunks != nil {
		t.Errorf("expected nil for empty input, got %v", chunks)
	}
}

func TestSplitTextChunks_Japanese(t *testing.T) {
	text := "こんにちは。お元気ですか？元気です！ありがとう。"
	chunks := SplitTextChunks(text, 15)

	// Each chunk should be at most 15 runes (unless a single sentence is longer).
	for i, c := range chunks {
		n := utf8.RuneCountInString(c)
		if n > 15 {
			sentences := SplitSentences(c)
			if len(sentences) > 1 {
				t.Errorf("chunk[%d] has %d runes (>15) and multiple sentences: %q",
					i, n, c)
			}
		}
	}
}

func TestSplitTextChunks_AllFitInOne(t *testing.T) {
	text := "Hello. World."
	chunks := SplitTextChunks(text, 100)

	if len(chunks) != 1 {
		t.Fatalf("expected 1 chunk, got %d: %v", len(chunks), chunks)
	}
	if chunks[0] != "Hello. World." {
		t.Errorf("expected %q, got %q", "Hello. World.", chunks[0])
	}
}

// ---------------------------------------------------------------------------
// CalculateDynamicChunkSize
// ---------------------------------------------------------------------------

func TestCalculateDynamicChunkSize_Short(t *testing.T) {
	size := CalculateDynamicChunkSize("Hello.", 50)
	if size != 6 {
		t.Errorf("expected 6, got %d", size)
	}
}

func TestCalculateDynamicChunkSize_HighPunct(t *testing.T) {
	// Need >= 100 runes (baseChunkSize*2) with density > 0.05.
	// 34 repetitions of "Ab. " = 136 runes, 34 periods -> density ~0.25.
	text := strings.Repeat("Ab. ", 34)
	size := CalculateDynamicChunkSize(text, 50)
	if size != 50 {
		t.Errorf("expected 50, got %d", size)
	}
}

// ---------------------------------------------------------------------------
// SplitTextForStreaming
// ---------------------------------------------------------------------------

func TestSplitTextForStreaming_Empty(t *testing.T) {
	chunks := SplitTextForStreaming("", 50)
	if len(chunks) != 0 {
		t.Errorf("expected 0 chunks, got %d", len(chunks))
	}
}

func TestSplitTextForStreaming_Short(t *testing.T) {
	chunks := SplitTextForStreaming("Hello.", 50)
	if len(chunks) != 1 || chunks[0] != "Hello." {
		t.Errorf("unexpected: %v", chunks)
	}
}
