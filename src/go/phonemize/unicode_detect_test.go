package phonemize

import (
	"testing"
)

func TestJapaneseTextSingleSegment(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	segs := SegmentText("こんにちは世界", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("expected language ja, got %q", segs[0].Language)
	}
	if segs[0].Text != "こんにちは世界" {
		t.Errorf("expected text %q, got %q", "こんにちは世界", segs[0].Text)
	}
}

func TestEnglishTextSingleSegment(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello world", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected language en, got %q", segs[0].Language)
	}
	if segs[0].Text != "hello world" {
		t.Errorf("expected text %q, got %q", "hello world", segs[0].Text)
	}
}

func TestMixedEnglishJapanese(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	// The comma is a neutral ASCII char absorbed into preceding "en" segment.
	// Then Japanese text starts a new segment.
	segs := SegmentText("hello、こんにちは", d)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected language en, got %q", segs[0].Language)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected language ja, got %q", segs[1].Language)
	}
}

func TestChineseNoKanaContext(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	segs := SegmentText("你好世界", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "zh" {
		t.Errorf("expected language zh, got %q", segs[0].Language)
	}
	if segs[0].Text != "你好世界" {
		t.Errorf("expected text %q, got %q", "你好世界", segs[0].Text)
	}
}

func TestCJKWithKanaContext(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	// "漢字とかな" contains kana, so CJK ideographs should resolve to "ja".
	segs := SegmentText("漢字とかな", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("expected language ja, got %q", segs[0].Language)
	}
}

func TestNeutralCharsAbsorbed(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en"}, "en")
	segs := SegmentText("hello 123 world", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected language en, got %q", segs[0].Language)
	}
	if segs[0].Text != "hello 123 world" {
		t.Errorf("expected text %q, got %q", "hello 123 world", segs[0].Text)
	}
}

func TestEmptyText(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("", d)
	if len(segs) != 0 {
		t.Fatalf("expected 0 segments, got %d: %+v", len(segs), segs)
	}
}

func TestHasKana(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")

	if !d.HasKana("あ") {
		t.Error("HasKana should return true for hiragana")
	}
	if !d.HasKana("アイウ") {
		t.Error("HasKana should return true for katakana")
	}
	if d.HasKana("abc") {
		t.Error("HasKana should return false for pure latin")
	}
	if d.HasKana("") {
		t.Error("HasKana should return false for empty string")
	}
	if d.HasKana("你好") {
		t.Error("HasKana should return false for CJK without kana")
	}
}

func TestDetectCharPriority(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh", "ko"}, "en")

	tests := []struct {
		ch             rune
		contextHasKana bool
		want           string
		desc           string
	}{
		{'あ', false, "ja", "hiragana"},
		{'カ', false, "ja", "katakana"},
		{'ㇰ', false, "ja", "katakana extension U+31F0"},
		{'한', false, "ko", "hangul syllable"},
		{'ᄀ', false, "ko", "hangul jamo U+1100"},
		{'ㅎ', false, "ko", "hangul compat jamo"},
		{'漢', false, "zh", "CJK no kana context -> zh"},
		{'漢', true, "ja", "CJK with kana context -> ja"},
		{'Ａ', false, "en", "fullwidth latin A"},
		{'ｚ', false, "en", "fullwidth latin z"},
		{'。', false, "ja", "CJK punctuation"},
		{'！', false, "ja", "fullwidth exclamation"},
		{'A', false, "en", "basic latin uppercase"},
		{'z', false, "en", "basic latin lowercase"},
		{'\u00C0', false, "en", "latin A-grave"},
		{'\u00FF', false, "en", "latin y-diaeresis"},
		{' ', false, "", "space is neutral"},
		{'5', false, "", "digit is neutral"},
		{'.', false, "", "ASCII period is neutral"},
	}

	for _, tc := range tests {
		got := d.DetectChar(tc.ch, tc.contextHasKana)
		if got != tc.want {
			t.Errorf("DetectChar(%q / U+%04X, contextHasKana=%v) = %q, want %q [%s]",
				tc.ch, tc.ch, tc.contextHasKana, got, tc.want, tc.desc)
		}
	}
}

func TestCJKOnlyJA(t *testing.T) {
	// Only JA registered, no ZH: CJK ideographs should resolve to "ja".
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	got := d.DetectChar('漢', false)
	if got != "ja" {
		t.Errorf("CJK with only JA: expected ja, got %q", got)
	}
}

func TestCJKOnlyZH(t *testing.T) {
	// Only ZH registered, no JA: CJK ideographs should resolve to "zh".
	d := NewUnicodeLanguageDetector([]string{"zh", "en"}, "en")
	got := d.DetectChar('漢', true)
	if got != "zh" {
		t.Errorf("CJK with only ZH: expected zh, got %q", got)
	}
}

func TestAllNeutralUsesDefault(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "ja"}, "en")
	segs := SegmentText("123 !!!", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected default language en, got %q", segs[0].Language)
	}
}

func TestDefaultLatinLanguageSpanish(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"es", "ja"}, "es")
	segs := SegmentText("hola mundo", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "es" {
		t.Errorf("expected language es, got %q", segs[0].Language)
	}
}

func TestLatinExtendedChars(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"fr", "ja"}, "fr")
	// French text with accented characters.
	segs := SegmentText("caf\u00e9", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "fr" {
		t.Errorf("expected language fr, got %q", segs[0].Language)
	}
}
