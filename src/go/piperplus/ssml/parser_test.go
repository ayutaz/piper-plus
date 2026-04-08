package ssml

import (
	"strings"
	"testing"
)

// =====================================================================
// IsSSML
// =====================================================================

func TestIsSSML_SpeakTag(t *testing.T) {
	if !IsSSML("<speak>Hello</speak>") {
		t.Error("expected true for <speak> tag")
	}
}

func TestIsSSML_SpeakTagWithAttributes(t *testing.T) {
	if !IsSSML(`<speak version="1.0">Hi</speak>`) {
		t.Error("expected true for <speak> with attributes")
	}
}

func TestIsSSML_LeadingWhitespace(t *testing.T) {
	if !IsSSML("  \n<speak>Hello</speak>") {
		t.Error("expected true with leading whitespace")
	}
}

func TestIsSSML_PlainText(t *testing.T) {
	if IsSSML("Hello, world!") {
		t.Error("expected false for plain text")
	}
}

func TestIsSSML_OtherXML(t *testing.T) {
	if IsSSML("<html><body>Hi</body></html>") {
		t.Error("expected false for non-SSML XML")
	}
}

func TestIsSSML_EmptyString(t *testing.T) {
	if IsSSML("") {
		t.Error("expected false for empty string")
	}
}

func TestIsSSML_SpeakSubstring(t *testing.T) {
	if IsSSML("I want to speak clearly.") {
		t.Error("expected false for 'speak' in normal text")
	}
}

func TestIsSSML_SpeakInMiddle(t *testing.T) {
	if IsSSML("Hello <speak>world</speak>") {
		t.Error("expected false for <speak> not at start")
	}
}

// =====================================================================
// parseBreakTime (internal)
// =====================================================================

func TestParseBreakTime_Milliseconds(t *testing.T) {
	if got := parseBreakTime("500ms"); got != 500 {
		t.Errorf("expected 500, got %d", got)
	}
}

func TestParseBreakTime_Seconds(t *testing.T) {
	if got := parseBreakTime("1s"); got != 1000 {
		t.Errorf("expected 1000, got %d", got)
	}
}

func TestParseBreakTime_FractionalSeconds(t *testing.T) {
	if got := parseBreakTime("0.5s"); got != 500 {
		t.Errorf("expected 500, got %d", got)
	}
}

func TestParseBreakTime_FractionalMs(t *testing.T) {
	if got := parseBreakTime("250.5ms"); got != 250 {
		t.Errorf("expected 250, got %d", got)
	}
}

func TestParseBreakTime_ZeroMs(t *testing.T) {
	if got := parseBreakTime("0ms"); got != 0 {
		t.Errorf("expected 0, got %d", got)
	}
}

func TestParseBreakTime_ZeroS(t *testing.T) {
	if got := parseBreakTime("0s"); got != 0 {
		t.Errorf("expected 0, got %d", got)
	}
}

func TestParseBreakTime_Whitespace(t *testing.T) {
	if got := parseBreakTime("  500ms  "); got != 500 {
		t.Errorf("expected 500, got %d", got)
	}
}

func TestParseBreakTime_Invalid(t *testing.T) {
	if got := parseBreakTime("abc"); got != 0 {
		t.Errorf("expected 0, got %d", got)
	}
}

func TestParseBreakTime_BareNumber(t *testing.T) {
	if got := parseBreakTime("300"); got != 300 {
		t.Errorf("expected 300, got %d", got)
	}
}

// =====================================================================
// parseRate (internal)
// =====================================================================

func TestParseRate_NamedSlow(t *testing.T) {
	if got := parseRate("slow"); got != 1.25 {
		t.Errorf("expected 1.25, got %f", got)
	}
}

func TestParseRate_NamedFast(t *testing.T) {
	if got := parseRate("fast"); got != 0.8 {
		t.Errorf("expected 0.8, got %f", got)
	}
}

func TestParseRate_NamedMedium(t *testing.T) {
	if got := parseRate("medium"); got != 1.0 {
		t.Errorf("expected 1.0, got %f", got)
	}
}

func TestParseRate_NamedXSlow(t *testing.T) {
	if got := parseRate("x-slow"); got != 1.5 {
		t.Errorf("expected 1.5, got %f", got)
	}
}

func TestParseRate_NamedXFast(t *testing.T) {
	if got := parseRate("x-fast"); got != 0.6 {
		t.Errorf("expected 0.6, got %f", got)
	}
}

func TestParseRate_Percentage100(t *testing.T) {
	got := parseRate("100%")
	if !approxEqual(got, 1.0) {
		t.Errorf("expected ~1.0, got %f", got)
	}
}

func TestParseRate_Percentage120(t *testing.T) {
	got := parseRate("120%")
	expected := float32(100.0 / 120.0)
	if !approxEqual(got, expected) {
		t.Errorf("expected ~%f, got %f", expected, got)
	}
}

func TestParseRate_Percentage50(t *testing.T) {
	got := parseRate("50%")
	if !approxEqual(got, 2.0) {
		t.Errorf("expected ~2.0, got %f", got)
	}
}

func TestParseRate_Percentage200(t *testing.T) {
	got := parseRate("200%")
	if !approxEqual(got, 0.5) {
		t.Errorf("expected ~0.5, got %f", got)
	}
}

func TestParseRate_ZeroPercentage(t *testing.T) {
	if got := parseRate("0%"); got != 1.0 {
		t.Errorf("expected 1.0, got %f", got)
	}
}

func TestParseRate_NegativePercentage(t *testing.T) {
	if got := parseRate("-50%"); got != 1.0 {
		t.Errorf("expected 1.0, got %f", got)
	}
}

func TestParseRate_Invalid(t *testing.T) {
	if got := parseRate("banana"); got != 1.0 {
		t.Errorf("expected 1.0, got %f", got)
	}
}

func TestParseRate_CaseInsensitive(t *testing.T) {
	if got := parseRate("SLOW"); got != 1.25 {
		t.Errorf("expected 1.25, got %f", got)
	}
	if got := parseRate("Fast"); got != 0.8 {
		t.Errorf("expected 0.8, got %f", got)
	}
}

// =====================================================================
// breakStrengthMs map
// =====================================================================

func TestBreakStrength_NoneIsZero(t *testing.T) {
	if breakStrengthMs["none"] != 0 {
		t.Errorf("expected 0, got %d", breakStrengthMs["none"])
	}
}

func TestBreakStrength_XStrongIs1000(t *testing.T) {
	if breakStrengthMs["x-strong"] != 1000 {
		t.Errorf("expected 1000, got %d", breakStrengthMs["x-strong"])
	}
}

func TestBreakStrength_AllPresent(t *testing.T) {
	expected := []string{"none", "x-weak", "weak", "medium", "strong", "x-strong"}
	for _, name := range expected {
		if _, ok := breakStrengthMs[name]; !ok {
			t.Errorf("missing break strength: %s", name)
		}
	}
}

// =====================================================================
// Parse — break tags
// =====================================================================

func TestParse_BreakTimeMs(t *testing.T) {
	ssml := `<speak>Hello<break time="500ms"/>world</speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	breaks := collectBreaks(segments)

	assertContainsStr(t, texts, "Hello")
	assertContainsStr(t, texts, "world")
	assertContainsInt(t, breaks, 500)
}

func TestParse_BreakTimeSeconds(t *testing.T) {
	ssml := `<speak>A<break time="2s"/>B</speak>`
	segments := Parse(ssml)

	breaks := collectBreaks(segments)
	assertContainsInt(t, breaks, 2000)
}

func TestParse_BreakStrength(t *testing.T) {
	ssml := `<speak>A<break strength="strong"/>B</speak>`
	segments := Parse(ssml)

	breaks := collectBreaks(segments)
	assertContainsInt(t, breaks, 700)
}

func TestParse_BreakNoAttributes(t *testing.T) {
	ssml := `<speak>A<break/>B</speak>`
	segments := Parse(ssml)

	breaks := collectBreaks(segments)
	assertContainsInt(t, breaks, 400) // medium default
}

func TestParse_StandaloneBreak(t *testing.T) {
	ssml := `<speak><break time="1s"/></speak>`
	segments := Parse(ssml)

	found := false
	for _, s := range segments {
		if s.BreakMs == 1000 {
			found = true
		}
	}
	if !found {
		t.Error("expected a segment with BreakMs=1000")
	}
}

// =====================================================================
// Parse — prosody rate
// =====================================================================

func TestParse_ProsodyRateSlow(t *testing.T) {
	ssml := `<speak><prosody rate="slow">Hello</prosody></speak>`
	segments := Parse(ssml)

	if len(segments) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(segments))
	}
	if segments[0].Text != "Hello" {
		t.Errorf("expected text 'Hello', got %q", segments[0].Text)
	}
	if segments[0].Rate != 1.25 {
		t.Errorf("expected rate 1.25, got %f", segments[0].Rate)
	}
}

func TestParse_ProsodyRateFast(t *testing.T) {
	ssml := `<speak><prosody rate="fast">Quick</prosody></speak>`
	segments := Parse(ssml)

	if segments[0].Rate != 0.8 {
		t.Errorf("expected rate 0.8, got %f", segments[0].Rate)
	}
}

func TestParse_ProsodyRatePercentage(t *testing.T) {
	ssml := `<speak><prosody rate="150%">Faster</prosody></speak>`
	segments := Parse(ssml)

	expected := float32(100.0 / 150.0)
	if !approxEqual(segments[0].Rate, expected) {
		t.Errorf("expected rate ~%f, got %f", expected, segments[0].Rate)
	}
}

func TestParse_DefaultRateWhenAbsent(t *testing.T) {
	ssml := `<speak>Normal text</speak>`
	segments := Parse(ssml)

	if segments[0].Rate != 1.0 {
		t.Errorf("expected rate 1.0, got %f", segments[0].Rate)
	}
}

func TestParse_ProsodyWithoutRateAttr(t *testing.T) {
	ssml := `<speak><prosody>Text</prosody></speak>`
	segments := Parse(ssml)

	if segments[0].Rate != 1.0 {
		t.Errorf("expected rate 1.0, got %f", segments[0].Rate)
	}
}

// =====================================================================
// Parse — nested tags
// =====================================================================

func TestParse_BreakInsideProsody(t *testing.T) {
	ssml := `<speak><prosody rate="slow">Before<break time="300ms"/>After</prosody></speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "Before")
	assertContainsStr(t, texts, "After")

	breakSegs := filterBreaks(segments)
	if len(breakSegs) != 1 {
		t.Fatalf("expected 1 break segment, got %d", len(breakSegs))
	}
	if breakSegs[0].BreakMs != 300 {
		t.Errorf("expected break 300ms, got %d", breakSegs[0].BreakMs)
	}
}

func TestParse_MultipleProsodySections(t *testing.T) {
	ssml := `<speak><prosody rate="slow">Slow</prosody><prosody rate="fast">Fast</prosody></speak>`
	segments := Parse(ssml)

	var slowSegs, fastSegs []Segment
	for _, s := range segments {
		if s.Rate == 1.25 {
			slowSegs = append(slowSegs, s)
		}
		if s.Rate == 0.8 {
			fastSegs = append(fastSegs, s)
		}
	}
	if len(slowSegs) == 0 {
		t.Error("expected at least one slow segment")
	}
	if len(fastSegs) == 0 {
		t.Error("expected at least one fast segment")
	}
	if slowSegs[0].Text != "Slow" {
		t.Errorf("expected slow text 'Slow', got %q", slowSegs[0].Text)
	}
	if fastSegs[0].Text != "Fast" {
		t.Errorf("expected fast text 'Fast', got %q", fastSegs[0].Text)
	}
}

// =====================================================================
// Parse — combined break + prosody
// =====================================================================

func TestParse_BreakBetweenProsody(t *testing.T) {
	ssml := `<speak><prosody rate="slow">Slow</prosody><break time="500ms"/><prosody rate="fast">Fast</prosody></speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "Slow")
	assertContainsStr(t, texts, "Fast")

	found := false
	for _, s := range segments {
		if s.BreakMs == 500 {
			found = true
		}
	}
	if !found {
		t.Error("expected a segment with BreakMs=500")
	}
}

func TestParse_ComplexMixed(t *testing.T) {
	ssml := `<speak>Hello <break time="200ms"/><prosody rate="fast">Quick part</prosody><break time="1s"/>End</speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "Hello")
	assertContainsStr(t, texts, "Quick part")
	assertContainsStr(t, texts, "End")
}

// =====================================================================
// Parse — XML error fallback
// =====================================================================

func TestParse_UnclosedTagFallback(t *testing.T) {
	ssml := "<speak>Hello <break"
	segments := Parse(ssml)

	if len(segments) == 0 {
		t.Fatal("expected at least one segment")
	}
	fullText := joinTexts(segments)
	if !containsStr(fullText, "Hello") {
		t.Errorf("expected 'Hello' in output, got %q", fullText)
	}
}

func TestParse_InvalidXMLReturnsStripped(t *testing.T) {
	ssml := "<speak>Some text <invalid></speak>"
	segments := Parse(ssml)

	if len(segments) == 0 {
		t.Fatal("expected at least one segment")
	}
	fullText := joinTexts(segments)
	if !containsStr(fullText, "text") {
		t.Errorf("expected 'text' in output, got %q", fullText)
	}
}

// =====================================================================
// Parse — plain text (non-SSML)
// =====================================================================

func TestParse_PlainTextPassthrough(t *testing.T) {
	text := "Hello, world!"
	segments := Parse(text)

	if len(segments) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(segments))
	}
	if segments[0].Text != text {
		t.Errorf("expected text %q, got %q", text, segments[0].Text)
	}
	if segments[0].BreakMs != 0 {
		t.Errorf("expected BreakMs 0, got %d", segments[0].BreakMs)
	}
	if segments[0].Rate != 1.0 {
		t.Errorf("expected Rate 1.0, got %f", segments[0].Rate)
	}
}

func TestParse_EmptyString(t *testing.T) {
	segments := Parse("")
	if len(segments) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(segments))
	}
	if segments[0].Text != "" {
		t.Errorf("expected empty text, got %q", segments[0].Text)
	}
}

// =====================================================================
// Parse — Japanese text
// =====================================================================

func TestParse_JapaneseInSpeak(t *testing.T) {
	ssml := "<speak>\u3053\u3093\u306b\u3061\u306f\u3001\u4e16\u754c\u3002</speak>"
	segments := Parse(ssml)

	if len(segments) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(segments))
	}
	if !containsStr(segments[0].Text, "\u3053\u3093\u306b\u3061\u306f") {
		t.Errorf("expected Japanese text, got %q", segments[0].Text)
	}
}

func TestParse_JapaneseWithBreak(t *testing.T) {
	ssml := "<speak>\u304a\u306f\u3088\u3046<break time=\"500ms\"/>\u3054\u3056\u3044\u307e\u3059</speak>"
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "\u304a\u306f\u3088\u3046")
	assertContainsStr(t, texts, "\u3054\u3056\u3044\u307e\u3059")
}

func TestParse_JapaneseWithProsody(t *testing.T) {
	ssml := "<speak><prosody rate=\"slow\">\u3086\u3063\u304f\u308a\u8a71\u3057\u307e\u3059</prosody></speak>"
	segments := Parse(ssml)

	if segments[0].Text != "\u3086\u3063\u304f\u308a\u8a71\u3057\u307e\u3059" {
		t.Errorf("unexpected text: %q", segments[0].Text)
	}
	if segments[0].Rate != 1.25 {
		t.Errorf("expected rate 1.25, got %f", segments[0].Rate)
	}
}

func TestParse_MixedJapaneseEnglish(t *testing.T) {
	ssml := "<speak>\u3053\u3093\u306b\u3061\u306f<break time=\"300ms\"/><prosody rate=\"fast\">Hello world</prosody></speak>"
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "\u3053\u3093\u306b\u3061\u306f")
	assertContainsStr(t, texts, "Hello world")
}

// =====================================================================
// Parse — unknown tags (graceful degradation)
// =====================================================================

func TestParse_UnknownTagTextExtracted(t *testing.T) {
	ssml := "<speak><emphasis>Important</emphasis></speak>"
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "Important")
}

func TestParse_NestedUnknownTags(t *testing.T) {
	ssml := `<speak><say-as interpret-as="date">2026-04-08</say-as></speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "2026-04-08")
}

// =====================================================================
// Segment defaults
// =====================================================================

func TestSegment_Defaults(t *testing.T) {
	seg := Segment{Text: "hello", Rate: 1.0}
	if seg.Text != "hello" {
		t.Errorf("unexpected text: %q", seg.Text)
	}
	if seg.BreakMs != 0 {
		t.Errorf("expected BreakMs 0, got %d", seg.BreakMs)
	}
	if seg.Rate != 1.0 {
		t.Errorf("expected Rate 1.0, got %f", seg.Rate)
	}
}

func TestSegment_CustomValues(t *testing.T) {
	seg := Segment{Text: "test", BreakMs: 500, Rate: 0.8}
	if seg.BreakMs != 500 {
		t.Errorf("expected 500, got %d", seg.BreakMs)
	}
	if seg.Rate != 0.8 {
		t.Errorf("expected 0.8, got %f", seg.Rate)
	}
}

func TestSegment_SilenceOnly(t *testing.T) {
	seg := Segment{Text: "", BreakMs: 1000, Rate: 1.0}
	if seg.Text != "" {
		t.Errorf("expected empty text, got %q", seg.Text)
	}
	if seg.BreakMs != 1000 {
		t.Errorf("expected 1000, got %d", seg.BreakMs)
	}
}

// =====================================================================
// Parse — edge cases
// =====================================================================

func TestParse_MultipleBreaksInSequence(t *testing.T) {
	ssml := `<speak>A<break time="100ms"/><break time="200ms"/>B</speak>`
	segments := Parse(ssml)

	breaks := collectBreaks(segments)
	assertContainsInt(t, breaks, 100)
	assertContainsInt(t, breaks, 200)
}

func TestParse_BreakStrengthXWeak(t *testing.T) {
	ssml := `<speak>A<break strength="x-weak"/>B</speak>`
	segments := Parse(ssml)

	breaks := collectBreaks(segments)
	assertContainsInt(t, breaks, 100)
}

func TestParse_BreakStrengthNone(t *testing.T) {
	ssml := `<speak>A<break strength="none"/>B</speak>`
	segments := Parse(ssml)

	// strength=none produces 0ms, so the break segment is merged away
	// (empty text + 0 break = no-op). Only text segments should remain.
	texts := collectTexts(segments)
	assertContainsStr(t, texts, "A")
	assertContainsStr(t, texts, "B")
}

func TestParse_NestedProsody(t *testing.T) {
	ssml := `<speak><prosody rate="slow"><prosody rate="fast">Inner</prosody></prosody></speak>`
	segments := Parse(ssml)

	if len(segments) == 0 {
		t.Fatal("expected at least one segment")
	}
	// Inner prosody should override outer
	if segments[0].Rate != 0.8 {
		t.Errorf("expected rate 0.8, got %f", segments[0].Rate)
	}
}

func TestParse_TextBeforeAndAfterChild(t *testing.T) {
	ssml := `<speak>Before <emphasis>middle</emphasis> after</speak>`
	segments := Parse(ssml)

	texts := collectTexts(segments)
	assertContainsStr(t, texts, "Before")
	assertContainsStr(t, texts, "middle")
	assertContainsStr(t, texts, "after")
}

func TestParse_WhitespaceOnlyText(t *testing.T) {
	ssml := `<speak>   </speak>`
	segments := Parse(ssml)

	// Whitespace-only text is trimmed and merged away, producing empty result
	if len(segments) != 1 {
		t.Fatalf("expected 1 segment, got %d", len(segments))
	}
	if segments[0].Text != "" {
		t.Errorf("expected empty text, got %q", segments[0].Text)
	}
}

func TestParse_ProsodyRateBareFloat(t *testing.T) {
	ssml := `<speak><prosody rate="1.5">Slow</prosody></speak>`
	segments := Parse(ssml)

	if !approxEqual(segments[0].Rate, 1.5) {
		t.Errorf("expected rate 1.5, got %f", segments[0].Rate)
	}
}

// =====================================================================
// Test helpers
// =====================================================================

func collectTexts(segs []Segment) []string {
	var texts []string
	for _, s := range segs {
		if s.Text != "" {
			texts = append(texts, s.Text)
		}
	}
	return texts
}

func collectBreaks(segs []Segment) []int {
	var breaks []int
	for _, s := range segs {
		if s.BreakMs > 0 {
			breaks = append(breaks, s.BreakMs)
		}
	}
	return breaks
}

func filterBreaks(segs []Segment) []Segment {
	var result []Segment
	for _, s := range segs {
		if s.BreakMs > 0 {
			result = append(result, s)
		}
	}
	return result
}

func joinTexts(segs []Segment) string {
	var parts []string
	for _, s := range segs {
		parts = append(parts, s.Text)
	}
	return strings.Join(parts, " ")
}

func containsStr(haystack, needle string) bool {
	return strings.Contains(haystack, needle)
}

func assertContainsStr(t *testing.T, slice []string, want string) {
	t.Helper()
	for _, s := range slice {
		if s == want {
			return
		}
	}
	t.Errorf("expected %q in %v", want, slice)
}

func assertContainsInt(t *testing.T, slice []int, want int) {
	t.Helper()
	for _, v := range slice {
		if v == want {
			return
		}
	}
	t.Errorf("expected %d in %v", want, slice)
}
