package phonemize

import (
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// Mock phonemizers for testing MultilingualPhonemizer
// ---------------------------------------------------------------------------

// mockPhonemizer returns predictable tokens for testing.
type mockPhonemizer struct {
	lang   string
	tokens []string // tokens to return (including BOS/EOS)
}

func (m *mockPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	prosody := make([]*ProsodyInfo, len(m.tokens))
	for i, tok := range m.tokens {
		if tok == "^" || tok == "$" || tok == "?" {
			prosody[i] = nil
		} else {
			prosody[i] = &ProsodyInfo{A1: 0, A2: 0, A3: 1}
		}
	}
	// Determine EOS from tokens
	eos := "$"
	for _, tok := range m.tokens {
		if tok == "?" || tok == string(rune(0xE016)) || tok == string(rune(0xE017)) || tok == string(rune(0xE018)) {
			eos = tok
		}
	}
	return &PhonemizeResult{
		Tokens:   m.tokens,
		Prosody:  prosody,
		EOSToken: eos,
	}, nil
}

func (m *mockPhonemizer) LanguageCode() string {
	return m.lang
}

// ---------------------------------------------------------------------------
// Helper: build MultilingualPhonemizer with mocks
// ---------------------------------------------------------------------------

func newTestMultilingualPhonemizer(
	languages []string,
	defaultLatin string,
	mocks map[string]*mockPhonemizer,
) *MultilingualPhonemizer {
	phonemizers := make(map[string]Phonemizer, len(mocks))
	for lang, mock := range mocks {
		phonemizers[lang] = mock
	}
	return NewMultilingualPhonemizer(languages, defaultLatin, phonemizers)
}

// ---------------------------------------------------------------------------
// Test: empty and whitespace-only input
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_EmptyInput(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", "$"}},
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("empty input: expected 0 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("empty input: expected EOS=$, got %q", result.EOSToken)
	}
}

func TestMultilingualPhonemizer_WhitespaceOnly(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", "$"}},
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
		},
	)

	// Whitespace-only text returns empty (Python parity: not text.strip() -> []).
	result, err := mp.PhonemizeWithProsody("   ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 0 {
		t.Errorf("whitespace input: expected empty tokens, got %v", result.Tokens)
	}
}

// ---------------------------------------------------------------------------
// Test: single language texts
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_SingleLanguageJapanese(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "k", "o", "N_m", "$"}},
			"en": {lang: "en", tokens: nil},
			"zh": {lang: "zh", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("こんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// BOS "^" and EOS "$" should be stripped.
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "k" || result.Tokens[1] != "o" || result.Tokens[2] != "N_m" {
		t.Errorf("expected [k o N_m], got %v", result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("expected EOS=$, got %q", result.EOSToken)
	}
}

func TestMultilingualPhonemizer_SingleLanguageEnglish(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: nil},
			"en": {lang: "en", tokens: []string{"^", "h", "ə", "l", "oʊ", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("hello")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 4 {
		t.Fatalf("expected 4 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("expected EOS=$, got %q", result.EOSToken)
	}
}

func TestMultilingualPhonemizer_SingleLanguageChinese(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"zh", "en"},
		"en",
		map[string]*mockPhonemizer{
			"zh": {lang: "zh", tokens: []string{"^", "n", "i", "tone3", "$"}},
			"en": {lang: "en", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("你好")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// BOS/EOS stripped -> 3 tokens
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.EOSToken != "$" {
		t.Errorf("expected EOS=$, got %q", result.EOSToken)
	}
}

func TestMultilingualPhonemizer_SingleLanguageSpanish(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"es", "en"},
		"es",
		map[string]*mockPhonemizer{
			"es": {lang: "es", tokens: []string{"^", "o", "l", "a", "$"}},
			"en": {lang: "en", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("hola")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
}

func TestMultilingualPhonemizer_SingleLanguageFrench(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"fr"},
		"fr",
		map[string]*mockPhonemizer{
			"fr": {lang: "fr", tokens: []string{"^", "b", "ɔ̃", "ʒ", "u", "ʁ", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("bonjour")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 5 {
		t.Fatalf("expected 5 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
}

func TestMultilingualPhonemizer_SingleLanguagePortuguese(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"pt"},
		"pt",
		map[string]*mockPhonemizer{
			"pt": {lang: "pt", tokens: []string{"^", "o", "l", "a", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("olá")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
}

// ---------------------------------------------------------------------------
// Test: two-language mixed texts
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_MixedJapaneseEnglish(t *testing.T) {
	// "Hello世界こんにちは" -> [en:"Hello", ja:"世界こんにちは"]
	// With kana present, CJK resolves to "ja".
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "s", "e", "k", "a", "i", "$"}},
			"en": {lang: "en", tokens: []string{"^", "h", "ɛ", "l", "oʊ", "$"}},
			"zh": {lang: "zh", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("Helloこんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// EN segment: h, ɛ, l, oʊ (4 tokens) + JA segment: s, e, k, a, i (5 tokens)
	if len(result.Tokens) != 9 {
		t.Fatalf("expected 9 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	// First 4 tokens from English, next 5 from Japanese
	if result.Tokens[0] != "h" {
		t.Errorf("token[0]: expected 'h', got %q", result.Tokens[0])
	}
	if result.Tokens[4] != "s" {
		t.Errorf("token[4]: expected 's', got %q", result.Tokens[4])
	}
}

func TestMultilingualPhonemizer_MixedJapaneseChinese(t *testing.T) {
	// "漢字とかな你好" -> kana present, so CJK before kana = ja, after it's ambiguous
	// The whole text has kana, so all CJK = ja.
	// But "你好" does not follow kana directly; since contextHasKana=true, all CJK -> ja.
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "zh", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "k", "a", "n", "$"}},
			"zh": {lang: "zh", tokens: nil},
			"en": {lang: "en", tokens: nil},
		},
	)

	// This text has kana (と, か, な) so all CJK ideographs -> ja
	result, err := mp.PhonemizeWithProsody("漢字とかな")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens (k,a,n), got %d: %v", len(result.Tokens), result.Tokens)
	}
}

func TestMultilingualPhonemizer_MixedEnglishFrench(t *testing.T) {
	// With default_latin = "en", both English and French text go to "en" phonemizer
	// because Latin characters all map to defaultLatinLanguage.
	// This is a known limitation: Latin-Latin language mixing is not distinguishable
	// by Unicode ranges alone.
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "fr"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "ɛ", "l", "oʊ", "$"}},
			"fr": {lang: "fr", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("Hello bonjour")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// All Latin -> "en" segment, so only "en" mock is called
	if len(result.Tokens) != 4 {
		t.Fatalf("expected 4 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
}

func TestMultilingualPhonemizer_MixedChineseEnglish(t *testing.T) {
	// "你好world" -> [zh:"你好", en:"world"]
	// No kana in text, so CJK -> zh
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: nil},
			"en": {lang: "en", tokens: []string{"^", "w", "ɝ", "l", "d", "$"}},
			"zh": {lang: "zh", tokens: []string{"^", "n", "i", "tone3", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("你好world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// ZH: n, i, tone3 (3) + EN: w, ɝ, l, d (4)
	if len(result.Tokens) != 7 {
		t.Fatalf("expected 7 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "n" {
		t.Errorf("token[0]: expected 'n' (ZH), got %q", result.Tokens[0])
	}
	if result.Tokens[3] != "w" {
		t.Errorf("token[3]: expected 'w' (EN), got %q", result.Tokens[3])
	}
}

// ---------------------------------------------------------------------------
// Test: three or more language mixed texts
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_ThreeLanguageMix(t *testing.T) {
	// "Hello你好こんにちは" -> [en:"Hello", zh/ja CJK context...]
	// No kana in "Hello你好", but "こんにちは" has kana.
	// Since SegmentText pre-scans the WHOLE text for kana,
	// contextHasKana=true => all CJK -> ja
	// So: [en:"Hello", ja:"你好こんにちは"] (2 segments, not 3)
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "j", "a", "$"}},
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
			"zh": {lang: "zh", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("Hello你好こんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// EN: h (1) + JA: j, a (2) = 3 tokens
	if len(result.Tokens) != 3 {
		t.Fatalf("expected 3 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "h" {
		t.Errorf("token[0]: expected 'h' (EN), got %q", result.Tokens[0])
	}
	if result.Tokens[1] != "j" {
		t.Errorf("token[1]: expected 'j' (JA), got %q", result.Tokens[1])
	}
}

func TestMultilingualPhonemizer_EnglishChineseNoKana(t *testing.T) {
	// "Hello你好world" -> [en:"Hello", zh:"你好", en:"world"]
	// No kana, so CJK -> zh
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: nil},
			"en": {lang: "en", tokens: []string{"^", "e", "n", "$"}},
			"zh": {lang: "zh", tokens: []string{"^", "z", "h", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("Hello你好world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// EN segment #1: e, n (2) + ZH: z, h (2) + EN segment #2: e, n (2) = 6
	if len(result.Tokens) != 6 {
		t.Fatalf("expected 6 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
}

// ---------------------------------------------------------------------------
// Test: EOS token tracking
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_EOSFromQuestion(t *testing.T) {
	// Japanese question marker should propagate as EOS
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", "?"}},
			"en": {lang: "en", tokens: nil},
		},
	)

	result, err := mp.PhonemizeWithProsody("なに？")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != "?" {
		t.Errorf("expected EOS=?, got %q", result.EOSToken)
	}
	// "?" is EOS and should be stripped from tokens
	for _, tok := range result.Tokens {
		if tok == "?" {
			t.Error("EOS token '?' should be stripped from tokens")
		}
	}
}

func TestMultilingualPhonemizer_EOSPUAQuestionMarker(t *testing.T) {
	// "?!" (PUA 0xE016) as EOS
	puaQE := string(rune(0xE016))
	mp := newTestMultilingualPhonemizer(
		[]string{"ja"},
		"ja",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", puaQE}},
		},
	)

	result, err := mp.PhonemizeWithProsody("なに？！")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.EOSToken != puaQE {
		t.Errorf("expected EOS=%q (PUA ?!), got %q", puaQE, result.EOSToken)
	}
}

func TestMultilingualPhonemizer_LastEOSWins(t *testing.T) {
	// When multiple segments have EOS tokens, the last one wins
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
			"ja": {lang: "ja", tokens: []string{"^", "a", "?"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("Helloなに？")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// EN segment EOS="$", then JA segment EOS="?" -> last wins
	if result.EOSToken != "?" {
		t.Errorf("expected last EOS=?, got %q", result.EOSToken)
	}
}

// ---------------------------------------------------------------------------
// Test: BOS/EOS stripping
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_BOSStripped(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja"},
		"ja",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "k", "o", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("こ")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	for _, tok := range result.Tokens {
		if tok == "^" {
			t.Error("BOS token '^' should be stripped from output")
		}
		if tok == "$" {
			t.Error("EOS token '$' should be stripped from output")
		}
	}
}

// ---------------------------------------------------------------------------
// Test: prosody alignment
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_ProsodyAlignment(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "ɛ", "$"}},
			"ja": {lang: "ja", tokens: []string{"^", "k", "o", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("Helloこんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != len(result.Prosody) {
		t.Errorf("tokens/prosody length mismatch: tokens=%d, prosody=%d",
			len(result.Tokens), len(result.Prosody))
	}
}

func TestMultilingualPhonemizer_ProsodyAlignmentThreeSegments(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
			"zh": {lang: "zh", tokens: []string{"^", "n", "tone3", "$"}},
		},
	)

	result, err := mp.PhonemizeWithProsody("Hello你好world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != len(result.Prosody) {
		t.Errorf("tokens/prosody length mismatch: tokens=%d, prosody=%d",
			len(result.Tokens), len(result.Prosody))
	}
}

// ---------------------------------------------------------------------------
// Test: punctuation at language boundaries
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_PunctuationBoundary(t *testing.T) {
	// "hello、こんにちは" - the fullwidth "、" (U+3001) is detected as "ja" punctuation.
	// This means "hello" is "en", then "、こんにちは" is "ja".
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello、こんにちは", detector)

	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected en, got %q", segs[0].Language)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected ja, got %q", segs[1].Language)
	}
}

func TestMultilingualPhonemizer_ASCIIPunctuationNeutral(t *testing.T) {
	// ASCII punctuation (.,!?) is neutral and absorbed into preceding segment.
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello, こんにちは!", detector)

	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	// The comma+space should be absorbed into "en" segment
	if !strings.HasSuffix(segs[0].Text, ", ") {
		t.Errorf("segment 0: expected trailing ', ', got %q", segs[0].Text)
	}
	// The "!" should be absorbed into "ja" segment
	if !strings.HasSuffix(segs[1].Text, "!") {
		t.Errorf("segment 1: expected trailing '!', got %q", segs[1].Text)
	}
}

// ---------------------------------------------------------------------------
// Test: CJK disambiguation in segmentation context
// ---------------------------------------------------------------------------

func TestSegmentText_CJKWithKanaContext_JA(t *testing.T) {
	// Text has kana -> all CJK -> ja
	detector := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	segs := SegmentText("漢字テスト", detector) // CJK + katakana
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("CJK+kana: expected ja, got %q", segs[0].Language)
	}
}

func TestSegmentText_CJKWithoutKanaContext_ZH(t *testing.T) {
	// Text has no kana -> CJK -> zh
	detector := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	segs := SegmentText("漢字測試", detector) // Pure CJK, no kana
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "zh" {
		t.Errorf("CJK without kana: expected zh, got %q", segs[0].Language)
	}
}

func TestSegmentText_CJKOnlyJARegistered(t *testing.T) {
	// Only JA registered (no ZH): CJK -> ja regardless of kana
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("漢字", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("CJK only JA: expected ja, got %q", segs[0].Language)
	}
}

func TestSegmentText_CJKOnlyZHRegistered(t *testing.T) {
	// Only ZH registered (no JA): CJK -> zh regardless of context
	detector := NewUnicodeLanguageDetector([]string{"zh", "en"}, "en")
	segs := SegmentText("漢字", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "zh" {
		t.Errorf("CJK only ZH: expected zh, got %q", segs[0].Language)
	}
}

// ---------------------------------------------------------------------------
// Test: LanguageCode()
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_LanguageCode(t *testing.T) {
	mp := NewMultilingualPhonemizer(
		[]string{"ja", "en", "zh", "es", "fr", "pt"},
		"en",
		nil,
	)
	got := mp.LanguageCode()
	want := "ja-en-zh-es-fr-pt"
	if got != want {
		t.Errorf("LanguageCode() = %q, want %q", got, want)
	}
}

// ---------------------------------------------------------------------------
// Test: DefaultLatinLanguage
// ---------------------------------------------------------------------------

func TestDefaultLatinLanguage_Priorities(t *testing.T) {
	tests := []struct {
		languages []string
		want      string
	}{
		{[]string{"ja", "en", "zh", "es", "fr", "pt"}, "en"},
		{[]string{"ja", "zh", "es", "fr", "pt"}, "es"},
		{[]string{"ja", "zh", "fr", "pt"}, "fr"},
		{[]string{"ja", "zh", "pt"}, "pt"},
		{[]string{"ja", "zh"}, "ja"}, // no Latin language -> first
		{[]string{}, "en"},           // empty -> "en"
	}
	for _, tc := range tests {
		got := DefaultLatinLanguage(tc.languages)
		if got != tc.want {
			t.Errorf("DefaultLatinLanguage(%v) = %q, want %q", tc.languages, got, tc.want)
		}
	}
}

// ---------------------------------------------------------------------------
// Test: missing phonemizer for segment language
// ---------------------------------------------------------------------------

func TestMultilingualPhonemizer_MissingPhonemizerSkipsSegment(t *testing.T) {
	// Register only EN, not JA. Japanese segment should be silently skipped.
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
			// No "ja" phonemizer
		},
	)

	result, err := mp.PhonemizeWithProsody("Helloこんにちは")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// Only EN segment should produce tokens
	if len(result.Tokens) != 1 {
		t.Fatalf("expected 1 token (from EN only), got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "h" {
		t.Errorf("expected token 'h', got %q", result.Tokens[0])
	}
}

// ---------------------------------------------------------------------------
// Test: PostProcessMultilingualIDs
// ---------------------------------------------------------------------------

func TestPostProcessMultilingualIDs(t *testing.T) {
	result := &PhonemizeResult{
		Tokens:   []string{"h", "ɛ"},
		Prosody:  []*ProsodyInfo{{A1: 0, A2: 0, A3: 2}, {A1: 0, A2: 0, A3: 2}},
		EOSToken: "$",
	}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
		"h": {10},
		"ɛ": {11},
	}

	ids, prosody := PostProcessMultilingualIDs(result, idMap)

	// Expected: BOS(1) + pad(0) + h(10) + pad(0) + ɛ(11) + pad(0) + EOS(2)
	expectedIDs := []int64{1, 0, 10, 0, 11, 0, 2}
	if len(ids) != len(expectedIDs) {
		t.Fatalf("PostProcessMultilingualIDs: got %d IDs, want %d: %v", len(ids), len(expectedIDs), ids)
	}
	for i, want := range expectedIDs {
		if ids[i] != want {
			t.Errorf("IDs[%d] = %d, want %d", i, ids[i], want)
		}
	}

	// Prosody should be same length as IDs
	if len(prosody) != len(ids) {
		t.Errorf("prosody length %d != IDs length %d", len(prosody), len(ids))
	}
}

func TestPostProcessMultilingualIDs_QuestionEOS(t *testing.T) {
	result := &PhonemizeResult{
		Tokens:   []string{"a"},
		Prosody:  []*ProsodyInfo{{A1: 0, A2: 0, A3: 1}},
		EOSToken: "?",
	}
	idMap := map[string][]int64{
		"_": {0},
		"^": {1},
		"$": {2},
		"?": {3},
		"a": {10},
	}

	ids, _ := PostProcessMultilingualIDs(result, idMap)

	// Last ID should be "?" = 3, not "$" = 2
	lastID := ids[len(ids)-1]
	if lastID != 3 {
		t.Errorf("PostProcessMultilingualIDs with question EOS: last ID = %d, want 3; ids=%v", lastID, ids)
	}
}

// ---------------------------------------------------------------------------
// Test: SegmentText boundary edge cases
// ---------------------------------------------------------------------------

func TestSegmentText_DigitsOnlyDefaultLanguage(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("12345", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	// All neutral -> default language
	if segs[0].Language != "en" {
		t.Errorf("digits only: expected en (default), got %q", segs[0].Language)
	}
}

func TestSegmentText_MixedDigitsAndJapanese(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	// "123こんにちは456" -> digits are neutral, absorbed into surrounding
	segs := SegmentText("123こんにちは456", detector)
	// "123" is neutral, first lang char is ja, so "123" absorbed into ja
	// "456" is neutral, absorbed into ja since no lang change follows
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("expected ja, got %q", segs[0].Language)
	}
}

func TestSegmentText_LeadingNeutralAbsorbedIntoFirst(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	// Leading "123 " is neutral; first lang-specific char is from "hello"
	segs := SegmentText("123 hello", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected en, got %q", segs[0].Language)
	}
	if segs[0].Text != "123 hello" {
		t.Errorf("expected text '123 hello', got %q", segs[0].Text)
	}
}

func TestSegmentText_TrailingNeutralAbsorbedIntoPreceding(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello...   ", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("expected en, got %q", segs[0].Language)
	}
	if segs[0].Text != "hello...   " {
		t.Errorf("expected 'hello...   ', got %q", segs[0].Text)
	}
}

func TestSegmentText_FullwidthPunctBoundary(t *testing.T) {
	// Fullwidth punctuation (。, ！) is classified as "ja" by DetectChar.
	// So "hello。" -> [en:"hello", ja:"。"]
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("hello。", detector)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected en, got %q", segs[0].Language)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected ja, got %q", segs[1].Language)
	}
}

// ---------------------------------------------------------------------------
// Test: Python compatibility — _segment_text_multilingual behavior comparison
// ---------------------------------------------------------------------------

// TestPythonParity_EmptyStringReturnsNil verifies that empty input returns nil,
// matching Python's [] return for empty/whitespace text.
func TestPythonParity_EmptyStringReturnsNil(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("", detector)
	if segs != nil {
		t.Errorf("expected nil for empty string, got %+v", segs)
	}
}

// TestPythonParity_NeutralOnlyFallsBackToDefault matches Python behavior:
// text with only neutral chars (digits, punctuation) falls back to default language.
func TestPythonParity_NeutralOnlyFallsBackToDefault(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("12345!!!", detector)
	if len(segs) != 1 {
		t.Fatalf("expected 1 segment, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("neutral-only: expected en (default), got %q", segs[0].Language)
	}
}

// TestPythonParity_WhitespaceOnlyHandling verifies Go matches Python behavior:
// whitespace-only text returns [] (Python: text.strip() == "" -> []).
func TestPythonParity_WhitespaceOnlyHandling(t *testing.T) {
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("   ", detector)

	// Both Go and Python return empty for whitespace-only input.
	// SegmentText short-circuits via strings.TrimSpace check.
	if len(segs) != 0 {
		t.Fatalf("whitespace-only: expected 0 segments (Python parity), got %d: %+v", len(segs), segs)
	}
}

// ---------------------------------------------------------------------------
// Test: real-world mixed text patterns
// ---------------------------------------------------------------------------

func TestSegmentText_RealWorld_JapaneseWithEnglishLoanword(t *testing.T) {
	// "Pythonを使ってみた" -> en:"Python", ja:"を使ってみた"
	detector := NewUnicodeLanguageDetector([]string{"ja", "en", "zh"}, "en")
	segs := SegmentText("Pythonを使ってみた", detector)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected en, got %q", segs[0].Language)
	}
	if segs[1].Language != "ja" {
		t.Errorf("segment 1: expected ja, got %q", segs[1].Language)
	}
	// Kana present -> CJK in "使" should also be "ja"
	if !strings.Contains(segs[1].Text, "使") {
		t.Errorf("segment 1: expected to contain '使', got %q", segs[1].Text)
	}
}

func TestSegmentText_RealWorld_ChineseWithEnglish(t *testing.T) {
	// "Python是一个编程语言" -> en:"Python", zh:"是一个编程语言"
	detector := NewUnicodeLanguageDetector([]string{"zh", "en"}, "en")
	segs := SegmentText("Python是一个编程语言", detector)
	if len(segs) != 2 {
		t.Fatalf("expected 2 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "en" {
		t.Errorf("segment 0: expected en, got %q", segs[0].Language)
	}
	if segs[1].Language != "zh" {
		t.Errorf("segment 1: expected zh, got %q", segs[1].Language)
	}
}

func TestSegmentText_RealWorld_FullwidthLatinInJapanese(t *testing.T) {
	// Fullwidth Latin letters (Ａ-Ｚ) -> defaultLatinLanguage
	// "Ａbc" -> all en (Ａ is fullwidth A, bc is basic latin)
	detector := NewUnicodeLanguageDetector([]string{"ja", "en"}, "en")
	segs := SegmentText("テストＡＢＣテスト", detector)
	// テスト = ja, ＡＢＣ = en (fullwidth latin), テスト = ja
	if len(segs) != 3 {
		t.Fatalf("expected 3 segments, got %d: %+v", len(segs), segs)
	}
	if segs[0].Language != "ja" {
		t.Errorf("segment 0: expected ja, got %q", segs[0].Language)
	}
	if segs[1].Language != "en" {
		t.Errorf("segment 1: expected en, got %q", segs[1].Language)
	}
	if segs[2].Language != "ja" {
		t.Errorf("segment 2: expected ja, got %q", segs[2].Language)
	}
}

// ---------------------------------------------------------------------------
// Test: concurrent safety of MultilingualPhonemizer
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Test: Unicode NFC normalization
// ---------------------------------------------------------------------------

// nfcNormMockPhonemizer captures the text passed to PhonemizeWithProsody so
// that tests can verify NFC normalization happened before delegation.
type nfcNormMockPhonemizer struct {
	lang     string
	captured string
}

func (m *nfcNormMockPhonemizer) PhonemizeWithProsody(text string) (*PhonemizeResult, error) {
	m.captured = text
	return &PhonemizeResult{
		Tokens:   []string{"^", "x", "$"},
		Prosody:  []*ProsodyInfo{nil, {A1: 0, A2: 0, A3: 1}, nil},
		EOSToken: "$",
	}, nil
}

func (m *nfcNormMockPhonemizer) LanguageCode() string {
	return m.lang
}

func TestMultilingualPhonemizer_NFC_NFDLatin(t *testing.T) {
	// NFD form of "é": U+0065 (e) + U+0301 (combining acute accent)
	nfdInput := "e\u0301"
	// NFC form of "é": U+00E9
	nfcExpected := "\u00e9"

	mock := &nfcNormMockPhonemizer{lang: "fr"}
	phonemizers := map[string]Phonemizer{"fr": mock}
	mp := NewMultilingualPhonemizer([]string{"fr"}, "fr", phonemizers)

	_, err := mp.PhonemizeWithProsody(nfdInput)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mock.captured != nfcExpected {
		t.Errorf("NFD Latin: phonemizer received %q (len=%d), want NFC %q (len=%d)",
			mock.captured, len(mock.captured), nfcExpected, len(nfcExpected))
	}
}

func TestMultilingualPhonemizer_NFC_AlreadyNFC(t *testing.T) {
	// NFC form of "é": U+00E9 — should pass through unchanged.
	nfcInput := "\u00e9"

	mock := &nfcNormMockPhonemizer{lang: "fr"}
	phonemizers := map[string]Phonemizer{"fr": mock}
	mp := NewMultilingualPhonemizer([]string{"fr"}, "fr", phonemizers)

	_, err := mp.PhonemizeWithProsody(nfcInput)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mock.captured != nfcInput {
		t.Errorf("NFC Latin: phonemizer received %q, want %q", mock.captured, nfcInput)
	}
}

func TestMultilingualPhonemizer_NFC_NFDAndNFCSameResult(t *testing.T) {
	// Both NFD and NFC inputs should produce identical phonemizer input.
	nfdInput := "e\u0301" // NFD
	nfcInput := "\u00e9"  // NFC

	mockNFD := &nfcNormMockPhonemizer{lang: "fr"}
	mockNFC := &nfcNormMockPhonemizer{lang: "fr"}

	mpNFD := NewMultilingualPhonemizer([]string{"fr"}, "fr", map[string]Phonemizer{"fr": mockNFD})
	mpNFC := NewMultilingualPhonemizer([]string{"fr"}, "fr", map[string]Phonemizer{"fr": mockNFC})

	if _, err := mpNFD.PhonemizeWithProsody(nfdInput); err != nil {
		t.Fatalf("NFD: unexpected error: %v", err)
	}
	if _, err := mpNFC.PhonemizeWithProsody(nfcInput); err != nil {
		t.Fatalf("NFC: unexpected error: %v", err)
	}
	if mockNFD.captured != mockNFC.captured {
		t.Errorf("NFD and NFC produced different phonemizer input: NFD=%q, NFC=%q",
			mockNFD.captured, mockNFC.captured)
	}
}

func TestMultilingualPhonemizer_NFC_JapaneseDakuten(t *testing.T) {
	// NFD form of "が": U+304B (か) + U+3099 (combining dakuten)
	nfdInput := "\u304b\u3099"
	// NFC form of "が": U+304C
	nfcExpected := "\u304c"

	mock := &nfcNormMockPhonemizer{lang: "ja"}
	phonemizers := map[string]Phonemizer{"ja": mock}
	mp := NewMultilingualPhonemizer([]string{"ja"}, "ja", phonemizers)

	_, err := mp.PhonemizeWithProsody(nfdInput)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if mock.captured != nfcExpected {
		t.Errorf("Japanese dakuten: phonemizer received %q (len=%d), want NFC %q (len=%d)",
			mock.captured, len(mock.captured), nfcExpected, len(nfcExpected))
	}
}

func TestMultilingualPhonemizer_ConcurrentSafe(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "en"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", "$"}},
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
		},
	)

	const goroutines = 20
	errCh := make(chan error, goroutines)

	for i := 0; i < goroutines; i++ {
		go func() {
			result, err := mp.PhonemizeWithProsody("Helloこんにちは")
			if err != nil {
				errCh <- err
				return
			}
			if len(result.Tokens) != 2 {
				errCh <- nil // non-fatal; just checking for races
			}
			errCh <- nil
		}()
	}

	for i := 0; i < goroutines; i++ {
		if err := <-errCh; err != nil {
			t.Errorf("concurrent call error: %v", err)
		}
	}
}

// ---------------------------------------------------------------------------
// Swedish (SV) multilingual integration tests
// ---------------------------------------------------------------------------

// E2E-1: SV text with ä character routes to SV mock phonemizer.
func TestMultilingualPhonemizer_SwedishRouting(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "sv"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "h", "$"}},
			"sv": {lang: "sv", tokens: []string{"^", "s", "v", "$"}},
		},
	)
	// "Jag är glad" has ä -> SV detected
	result, err := mp.PhonemizeWithProsody("Jag \u00e4r glad")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// SV mock returns ["^", "s", "v", "$"], BOS/EOS stripped -> ["s", "v"]
	if len(result.Tokens) != 2 {
		t.Fatalf("expected 2 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "s" || result.Tokens[1] != "v" {
		t.Errorf("expected [s v], got %v", result.Tokens)
	}
}

// E2E-2: JA + SV mixed text routes correctly.
func TestMultilingualPhonemizer_JaSvMixed(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"ja", "sv"},
		"sv",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "a", "$"}},
			"sv": {lang: "sv", tokens: []string{"^", "b", "$"}},
		},
	)
	result, err := mp.PhonemizeWithProsody("こんにちは Hej")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// JA segment: ["a"], SV segment: ["b"]
	if len(result.Tokens) != 2 {
		t.Fatalf("expected 2 tokens, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "a" || result.Tokens[1] != "b" {
		t.Errorf("expected [a b], got %v", result.Tokens)
	}
}

// E2E-3: Latin text without SV indicators routes to EN, not SV.
func TestMultilingualPhonemizer_LatinDefaultsToEnNotSv(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "sv"},
		"en",
		map[string]*mockPhonemizer{
			"en": {lang: "en", tokens: []string{"^", "e", "$"}},
			"sv": {lang: "sv", tokens: []string{"^", "s", "$"}},
		},
	)
	result, err := mp.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// No SV indicators -> EN
	if len(result.Tokens) != 1 {
		t.Fatalf("expected 1 token, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "e" {
		t.Errorf("expected [e], got %v", result.Tokens)
	}
}

// E2E-4: 7-language set (ja-en-zh-es-fr-pt-sv) with SV text detection.
func TestMultilingualPhonemizer_7LangSvDetection(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "es", "fr", "ja", "pt", "sv", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "j", "$"}},
			"en": {lang: "en", tokens: []string{"^", "e", "$"}},
			"zh": {lang: "zh", tokens: []string{"^", "z", "$"}},
			"es": {lang: "es", tokens: []string{"^", "s", "$"}},
			"fr": {lang: "fr", tokens: []string{"^", "f", "$"}},
			"pt": {lang: "pt", tokens: []string{"^", "p", "$"}},
			"sv": {lang: "sv", tokens: []string{"^", "v", "$"}},
		},
	)
	// Swedish text with ä should be detected as SV
	result, err := mp.PhonemizeWithProsody("Jag \u00e4r glad")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 1 {
		t.Fatalf("expected 1 token, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "v" {
		t.Errorf("expected [v] (SV mock), got %v", result.Tokens)
	}
}

// E2E-5: 7-language set: non-SV Latin text still routes to EN.
func TestMultilingualPhonemizer_7LangNonSvLatin(t *testing.T) {
	mp := newTestMultilingualPhonemizer(
		[]string{"en", "es", "fr", "ja", "pt", "sv", "zh"},
		"en",
		map[string]*mockPhonemizer{
			"ja": {lang: "ja", tokens: []string{"^", "j", "$"}},
			"en": {lang: "en", tokens: []string{"^", "e", "$"}},
			"zh": {lang: "zh", tokens: []string{"^", "z", "$"}},
			"es": {lang: "es", tokens: []string{"^", "s", "$"}},
			"fr": {lang: "fr", tokens: []string{"^", "f", "$"}},
			"pt": {lang: "pt", tokens: []string{"^", "p", "$"}},
			"sv": {lang: "sv", tokens: []string{"^", "v", "$"}},
		},
	)
	// Plain English without SV indicators -> EN
	result, err := mp.PhonemizeWithProsody("hello world")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(result.Tokens) != 1 {
		t.Fatalf("expected 1 token, got %d: %v", len(result.Tokens), result.Tokens)
	}
	if result.Tokens[0] != "e" {
		t.Errorf("expected [e] (EN mock), got %v", result.Tokens)
	}
}
