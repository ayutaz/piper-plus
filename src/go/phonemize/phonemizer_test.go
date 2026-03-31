package phonemize

import (
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Japanese: question type detection
// ---------------------------------------------------------------------------

func TestJapanesePhonemizer_QuestionType(t *testing.T) {
	tests := []struct {
		text string
		want string
	}{
		{"こんにちは？", "?"},
		{"本当？！", "?!"},
		{"いいね？。", "?."},
		{"そうだね？～", "?~"},
		{"こんにちは", "$"},
	}
	for _, tc := range tests {
		got := getQuestionType(tc.text)
		if got != tc.want {
			t.Errorf("getQuestionType(%q) = %q, want %q", tc.text, got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// Japanese: context-dependent N phoneme rules
// ---------------------------------------------------------------------------

func TestApplyNPhonemeRules(t *testing.T) {
	tests := []struct {
		name  string
		input []string
		wantN string // expected replacement for the N token
	}{
		{
			name:  "bilabial b ahead (skip #)",
			input: []string{"k", "o", "N", "#", "b", "a"},
			wantN: "N_m",
		},
		{
			name:  "velar k ahead (skip #)",
			input: []string{"k", "o", "N", "#", "k", "a"},
			wantN: "N_ng",
		},
		{
			name:  "end of phrase",
			input: []string{"k", "o", "N", "$"},
			wantN: "N_uvular",
		},
		{
			name:  "vowel ahead",
			input: []string{"k", "o", "N", "#", "a"},
			wantN: "N_uvular",
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := applyNPhonemeRules(tc.input)
			// Find the token that replaced "N".
			found := false
			for _, tok := range got {
				if strings.HasPrefix(tok, "N_") {
					found = true
					if tok != tc.wantN {
						t.Errorf("applyNPhonemeRules(%v): N replaced with %q, want %q", tc.input, tok, tc.wantN)
					}
					break
				}
			}
			if !found {
				t.Errorf("applyNPhonemeRules(%v): no N_ variant found in result %v", tc.input, got)
			}
		})
	}
}

// ---------------------------------------------------------------------------
// English: basic word phonemization with mock CMU dict
// ---------------------------------------------------------------------------

func TestEnglishPhonemizer_BasicWord(t *testing.T) {
	cmuDict := map[string][]string{
		"hello": {"HH", "AH0", "L", "OW1"},
	}
	p := NewEnglishPhonemizer(cmuDict)
	result, err := p.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	joined := strings.Join(result.Tokens, "")
	// HH->h, AH0->ə, L->l, OW1->oʊ (with stress marker ˈ before stressed vowel)
	// Expect the output to contain "h", "ə", "l" at minimum.
	for _, expected := range []string{"h", "ə", "l"} {
		if !strings.Contains(joined, expected) {
			t.Errorf("PhonemizeWithProsody(\"hello\") tokens %q missing expected phoneme %q", joined, expected)
		}
	}
}

// ---------------------------------------------------------------------------
// Spanish: basic word phonemization
// ---------------------------------------------------------------------------

func TestSpanishPhonemizer_BasicWord(t *testing.T) {
	p := NewSpanishPhonemizer()
	result, err := p.PhonemizeWithProsody("hola")
	if err != nil {
		t.Fatalf("PhonemizeWithProsody error: %v", err)
	}
	// "hola": h is silent, o-l-a remain. Expect tokens to contain "o", "l", "a".
	var phonemes []string
	for _, tok := range result.Tokens {
		// Skip stress markers and PUA-mapped tokens.
		if tok == "ˈ" || tok == " " {
			continue
		}
		phonemes = append(phonemes, tok)
	}
	expected := []string{"o", "l", "a"}
	if len(phonemes) != len(expected) {
		t.Fatalf("SpanishPhonemizer(\"hola\"): got phonemes %v, want %v", phonemes, expected)
	}
	for i, want := range expected {
		if phonemes[i] != want {
			t.Errorf("SpanishPhonemizer(\"hola\")[%d] = %q, want %q", i, phonemes[i], want)
		}
	}
}

// ---------------------------------------------------------------------------
// Multilingual: DefaultLatinLanguage selection
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_DefaultLatinLanguage(t *testing.T) {
	tests := []struct {
		languages []string
		want      string
	}{
		{[]string{"ja", "en", "zh"}, "en"},
		{[]string{"ja", "zh", "es"}, "es"},
		{[]string{"ja", "zh"}, "ja"}, // no latin language -> first
	}
	for _, tc := range tests {
		got := DefaultLatinLanguage(tc.languages)
		if got != tc.want {
			t.Errorf("DefaultLatinLanguage(%v) = %q, want %q", tc.languages, got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// SegmentText: mixed language segmentation
// ---------------------------------------------------------------------------

func TestSegmentText_MixedLanguage(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello こんにちは", detector)
	if len(segs) != 2 {
		t.Fatalf("SegmentText: expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected language en, got %q", segs[0].Language)
	}
	if !strings.Contains(segs[0].Text, "hello") {
		t.Errorf("segment 0: expected text containing \"hello\", got %q", segs[0].Text)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected language ja, got %q", segs[1].Language)
	}
	if !strings.Contains(segs[1].Text, "こんにちは") {
		t.Errorf("segment 1: expected text containing \"こんにちは\", got %q", segs[1].Text)
	}
}
