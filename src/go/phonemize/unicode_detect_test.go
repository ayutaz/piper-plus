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

// ---------------------------------------------------------------------------
// Additional: CJK Extension A and Compatibility ranges
// ---------------------------------------------------------------------------

func TestDetectChar_CJKExtensionA(t *testing.T) {
	// CJK Unified Ideographs Extension A: U+3400-U+4DBF
	d := NewUnicodeLanguageDetector([]string{"ja", "zh", "en"}, "en")
	got := d.DetectChar('\u3400', false) // first char of Extension A
	if got != "zh" {
		t.Errorf("CJK Extension A (U+3400, no kana): expected zh, got %q", got)
	}
	got = d.DetectChar('\u4DBF', true) // last char of Extension A
	if got != "ja" {
		t.Errorf("CJK Extension A (U+4DBF, with kana): expected ja, got %q", got)
	}
}

func TestDetectChar_CJKCompatibility(t *testing.T) {
	// CJK Compatibility Ideographs: U+F900-U+FAFF
	d := NewUnicodeLanguageDetector([]string{"ja", "zh", "en"}, "en")
	got := d.DetectChar('\uF900', false)
	if got != "zh" {
		t.Errorf("CJK Compat (U+F900, no kana): expected zh, got %q", got)
	}
	got = d.DetectChar('\uFAFF', true)
	if got != "ja" {
		t.Errorf("CJK Compat (U+FAFF, with kana): expected ja, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Additional: CJK with neither JA nor ZH registered
// ---------------------------------------------------------------------------

func TestDetectChar_CJKNeitherJANorZH(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "ko"}, "en")
	got := d.DetectChar('漢', false)
	if got != "" {
		t.Errorf("CJK with neither JA nor ZH: expected empty, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Additional: Hangul boundary values
// ---------------------------------------------------------------------------

func TestDetectChar_HangulBoundaries(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ko", "en"}, "en")
	tests := []struct {
		ch   rune
		want string
		desc string
	}{
		{0xAC00, "ko", "Hangul Syllables start (가)"},
		{0xD7AF, "ko", "Hangul Syllables end"},
		{0x1100, "ko", "Hangul Jamo start (ᄀ)"},
		{0x11FF, "ko", "Hangul Jamo end"},
		{0x3130, "ko", "Hangul Compat Jamo start"},
		{0x318F, "ko", "Hangul Compat Jamo end"},
	}
	for _, tc := range tests {
		got := d.DetectChar(tc.ch, false)
		if got != tc.want {
			t.Errorf("DetectChar(U+%04X) = %q, want %q [%s]", tc.ch, got, tc.want, tc.desc)
		}
	}
}

// ---------------------------------------------------------------------------
// Additional: Hangul without KO registered
// ---------------------------------------------------------------------------

func TestDetectChar_HangulNoKO(t *testing.T) {
	// Python returns None when ko not in languages; Go should return ""
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	got := d.DetectChar('한', false)
	if got != "" {
		t.Errorf("Hangul without KO registered: expected empty, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Additional: Kana without JA registered
// ---------------------------------------------------------------------------

func TestDetectChar_KanaNoJA(t *testing.T) {
	// Python returns None when ja not in languages; Go should return ""
	d := NewUnicodeLanguageDetector([]string{"zh", "en"}, "en")
	got := d.DetectChar('あ', false)
	if got != "" {
		t.Errorf("Kana without JA registered: expected empty, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Additional: fullwidth punctuation boundary coverage
// ---------------------------------------------------------------------------

func TestDetectChar_FullwidthPunctBoundaries(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	tests := []struct {
		ch   rune
		want string
		desc string
	}{
		{0x3000, "ja", "ideographic space (CJK punct start)"},
		{0x303F, "ja", "CJK punct end"},
		{0xFF00, "ja", "fullwidth forms start (＀)"},
		{0xFF20, "ja", "fullwidth @ (＠)"},
		// 0xFF21 (Ａ) is fullwidth Latin -> en
		{0xFF21, "en", "fullwidth A -> Latin"},
		{0xFF3A, "en", "fullwidth Z -> Latin"},
		// 0xFF3B (［) back to JA punct
		{0xFF3B, "ja", "fullwidth [ -> JA punct"},
		{0xFF40, "ja", "fullwidth ` -> JA punct"},
		// 0xFF41 (ａ) is fullwidth Latin -> en
		{0xFF41, "en", "fullwidth a -> Latin"},
		{0xFF5A, "en", "fullwidth z -> Latin"},
		// 0xFF5B (｛) -> JA punct
		{0xFF5B, "ja", "fullwidth { -> JA punct"},
		{0xFFEF, "ja", "halfwidth/fullwidth forms end"},
	}
	for _, tc := range tests {
		got := d.DetectChar(tc.ch, false)
		if got != tc.want {
			t.Errorf("DetectChar(U+%04X) = %q, want %q [%s]", tc.ch, got, tc.want, tc.desc)
		}
	}
}

// ---------------------------------------------------------------------------
// Additional: Latin extended range boundary tests
// ---------------------------------------------------------------------------

func TestDetectChar_LatinBoundaries(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en"}, "en")
	tests := []struct {
		ch   rune
		want string
		desc string
	}{
		{0x00C0, "en", "Latin A-grave (start of extended range)"},
		{0x00D6, "en", "Latin O-diaeresis (end of first block)"},
		{0x00D7, "", "multiplication sign (excluded from Latin)"},
		{0x00D8, "en", "Latin O-stroke"},
		{0x00F6, "en", "Latin o-diaeresis"},
		{0x00F7, "", "division sign (excluded from Latin)"},
		{0x00F8, "en", "Latin o-stroke"},
		{0x00FF, "en", "Latin y-diaeresis (end of range)"},
	}
	for _, tc := range tests {
		got := d.DetectChar(tc.ch, false)
		if got != tc.want {
			t.Errorf("DetectChar(U+%04X) = %q, want %q [%s]", tc.ch, got, tc.want, tc.desc)
		}
	}
}

// ---------------------------------------------------------------------------
// Additional: multi-segment boundary with neutral chars between languages
// ---------------------------------------------------------------------------

func TestSegmentText_NeutralBetweenLanguages(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	// "hello 123 こんにちは" -> neutral "123" between en and ja.
	// "123" is after "hello " (en), so it's absorbed into en.
	segs := SegmentText("hello 123 こんにちは", d)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected en, got %q", segs[0].Language)
	}
	// "hello 123 " should all be in en segment
	if segs[0].Text != "hello 123 " {
		t.Errorf("segment 0: expected 'hello 123 ', got %q", segs[0].Text)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected ja, got %q", segs[1].Language)
	}
}

func TestSegmentText_MultipleLanguageSwitches(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	// "abc漢字def" -> no kana, CJK=zh: [en:"abc", zh:"漢字", en:"def"]
	segs := SegmentText("abc漢字def", d)
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" || segs[1].Language != "zh" || segs[2].Language != "en" {
		t.Errorf("expected [en, zh, en], got [%q, %q, %q]",
			segs[0].Language, segs[1].Language, segs[2].Language)
	}
}

// ---------------------------------------------------------------------------
// Additional: HasKana edge cases
// ---------------------------------------------------------------------------

func TestHasKana_KatakanaExtension(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	// U+31F0-U+31FF are Katakana Phonetic Extensions.
	// HasKana only checks U+3040-309F (hiragana) and U+30A0-30FF (katakana),
	// so katakana extension is NOT detected by HasKana.
	if d.HasKana(string(rune(0x31F0))) {
		t.Error("HasKana should return false for Katakana Phonetic Extension (only checks 3040-30FF)")
	}
}

func TestHasKana_MixedWithCJK(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	if !d.HasKana("漢字あ") {
		t.Error("HasKana should return true for CJK + hiragana")
	}
}

// ---------------------------------------------------------------------------
// CJK punctuation routing: JA not registered, ZH registered -> "zh"
// ---------------------------------------------------------------------------

func TestDetectChar_CJKPunctNoJAWithZH(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"zh", "en"}, "en")
	tests := []struct {
		ch   rune
		want string
		desc string
	}{
		{'。', "zh", "CJK period -> zh when JA absent, ZH present"},
		{'、', "zh", "CJK comma -> zh when JA absent, ZH present"},
		{'「', "zh", "CJK left bracket -> zh when JA absent, ZH present"},
		{0xFF01, "zh", "fullwidth ! -> zh when JA absent, ZH present"},
		{0xFF5B, "zh", "fullwidth { -> zh when JA absent, ZH present"},
	}
	for _, tc := range tests {
		got := d.DetectChar(tc.ch, false)
		if got != tc.want {
			t.Errorf("DetectChar(U+%04X) = %q, want %q [%s]", tc.ch, got, tc.want, tc.desc)
		}
	}
}

// ---------------------------------------------------------------------------
// CJK punctuation: neither JA nor ZH registered -> ""
// ---------------------------------------------------------------------------

func TestDetectChar_CJKPunctNeitherJANorZH(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "ko"}, "en")
	got := d.DetectChar('。', false)
	if got != "" {
		t.Errorf("CJK punct with neither JA nor ZH: expected empty, got %q", got)
	}
}

// ---------------------------------------------------------------------------
// Whitespace-only text -> empty slice (Python parity)
// ---------------------------------------------------------------------------

func TestSegmentText_WhitespaceOnly(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	tests := []string{
		" ",
		"   ",
		"\t",
		"\n",
		" \t\n ",
	}
	for _, text := range tests {
		segs := SegmentText(text, d)
		if len(segs) != 0 {
			t.Errorf("SegmentText(%q): expected 0 segments, got %d: %+v", text, len(segs), segs)
		}
	}
}

// ---------------------------------------------------------------------------
// Swedish (SV) language detection tests
// ---------------------------------------------------------------------------

// T1: ä/ö/å characters trigger SV detection.
func TestSegmentText_SwedishCharsDetected(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("Jag är glad", d)
	// "är" contains ä -> sv_score >= 1 -> segment is SV
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "sv" {
		t.Errorf("expected language sv, got %q", segs[0].Language)
	}
}

// T2: Function words alone trigger SV detection.
func TestSegmentText_SwedishFunctionWords(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("jag och hon", d)
	// "jag", "och", "hon" are all SV function words -> sv_score >= 1
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "sv" {
		t.Errorf("expected language sv, got %q", segs[0].Language)
	}
}

// T3: Latin text without SV indicators stays as default language (EN).
func TestSegmentText_NoSwedishIndicators(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("hello world", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected language en, got %q", segs[0].Language)
	}
}

// T4: SV not in language set -> no SV detection (post-processing disabled).
func TestSegmentText_NoSVInLanguages(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "fr"}, "en")
	segs := SegmentText("Jag är glad", d) // ä is Latin extended -> EN
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected language en, got %q", segs[0].Language)
	}
}

// T5: ja-sv with Latin text routed to SV (SV is defaultLatinLanguage).
func TestSegmentText_JaSvLatinGoesToSv(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "sv"}, "sv")
	segs := SegmentText("こんにちは hej", d)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("segment 0: expected ja, got %q", segs[0].Language)
	}
	if segs[1].Language != "sv" {
		t.Errorf("segment 1: expected sv, got %q", segs[1].Language)
	}
}

// T6: "Det är en bra dag" -> SV detected via ä character.
func TestSegmentText_SwedishRingA(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("Det \u00e4r en bra dag", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "sv" {
		t.Errorf("expected language sv, got %q", segs[0].Language)
	}
}

// T7: DefaultLatinLanguage with ja-sv returns SV.
func TestDefaultLatinLanguage_JaSv(t *testing.T) {
	got := DefaultLatinLanguage([]string{"ja", "sv"})
	if got != "sv" {
		t.Errorf("expected sv, got %q", got)
	}
}

// T8: DefaultLatinLanguage with en-sv returns EN (higher priority).
func TestDefaultLatinLanguage_EnSv(t *testing.T) {
	got := DefaultLatinLanguage([]string{"en", "sv"})
	if got != "en" {
		t.Errorf("expected en, got %q", got)
	}
}

// T9: SV single Latin language -> detectSwedish is false (no ambiguity).
func TestSegmentText_SvOnlyLatin_NoDetection(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"ja", "sv"}, "sv")
	// With only sv as Latin language, detectSwedish=false.
	// "hello" should be SV (the default Latin).
	segs := SegmentText("hello", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "sv" {
		t.Errorf("expected language sv, got %q", segs[0].Language)
	}
}

// T10: å character (U+00E5) triggers SV detection.
func TestSegmentText_SwedishAring(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("Vi g\u00e5r hem", d) // "går" contains å
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "sv" {
		t.Errorf("expected language sv, got %q", segs[0].Language)
	}
}

// ---------------------------------------------------------------------------
// German false-positive prevention tests
// ---------------------------------------------------------------------------
// ä/ö are shared between Swedish and German. When SV is in the language set,
// text containing only ä/ö (without å or Swedish function words) should NOT
// be misclassified as Swedish.

// T11: "Äpfel und Größe" — ä/ö present but no Swedish-unique indicators.
func TestSegmentText_GermanNotMisdetectedAsSV_Apfel(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("\u00c4pfel und Gr\u00f6\u00dfe", d) // Äpfel und Größe
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language == "sv" {
		t.Errorf("German text %q should NOT be detected as sv, got %q",
			segs[0].Text, segs[0].Language)
	}
}

// T12: "schöne Blumen" — ö present but German text.
func TestSegmentText_GermanNotMisdetectedAsSV_Schone(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("sch\u00f6ne Blumen", d) // schöne Blumen
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language == "sv" {
		t.Errorf("German text %q should NOT be detected as sv, got %q",
			segs[0].Text, segs[0].Language)
	}
}

// T13: "Das ist gut" — no SV indicators at all.
func TestSegmentText_GermanNotMisdetectedAsSV_DasIstGut(t *testing.T) {
	d := NewUnicodeLanguageDetector([]string{"en", "sv"}, "en")
	segs := SegmentText("Das ist gut", d)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language == "sv" {
		t.Errorf("German text %q should NOT be detected as sv, got %q",
			segs[0].Text, segs[0].Language)
	}
}
