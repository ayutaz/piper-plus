package piperplus

import (
	"math"
	"testing"
)

// ---------------------------------------------------------------------------
// Strategy A: padPhonemeIDs
// ---------------------------------------------------------------------------

func TestPadPhonemeIDs_NoPaddingNeeded(t *testing.T) {
	ids := make([]int64, minPhonemeIDs)
	for i := range ids {
		ids[i] = int64(i)
	}

	padded, wasPadded := padPhonemeIDs(ids)
	if wasPadded {
		t.Error("expected wasPadded=false for len >= minPhonemeIDs")
	}
	if len(padded) != len(ids) {
		t.Errorf("expected length %d, got %d", len(ids), len(padded))
	}
}

func TestPadPhonemeIDs_ShortSequence(t *testing.T) {
	// BOS=1, some content, EOS=2
	ids := []int64{1, 10, 20, 30, 2}

	padded, wasPadded := padPhonemeIDs(ids)
	if !wasPadded {
		t.Error("expected wasPadded=true for short sequence")
	}
	if len(padded) != minPhonemeIDs {
		t.Errorf("expected padded length %d, got %d", minPhonemeIDs, len(padded))
	}

	// First element must be BOS.
	if padded[0] != 1 {
		t.Errorf("expected BOS=1 at index 0, got %d", padded[0])
	}

	// Last element must be EOS.
	if padded[len(padded)-1] != 2 {
		t.Errorf("expected EOS=2 at last index, got %d", padded[len(padded)-1])
	}

	// Content phonemes must be present.
	found := map[int64]bool{}
	for _, id := range padded {
		found[id] = true
	}
	for _, id := range []int64{10, 20, 30} {
		if !found[id] {
			t.Errorf("expected content phoneme %d to be present in padded output", id)
		}
	}

	// Padding should be pause ID (0).
	zeroCount := 0
	for _, id := range padded {
		if id == 0 {
			zeroCount++
		}
	}
	expectedZeros := minPhonemeIDs - len(ids)
	if zeroCount != expectedZeros {
		t.Errorf("expected %d pause IDs, got %d", expectedZeros, zeroCount)
	}
}

func TestPadPhonemeIDs_MinimalSequence(t *testing.T) {
	// Just BOS and EOS.
	ids := []int64{1, 2}

	padded, wasPadded := padPhonemeIDs(ids)
	if !wasPadded {
		t.Error("expected wasPadded=true")
	}
	if len(padded) != minPhonemeIDs {
		t.Errorf("expected length %d, got %d", minPhonemeIDs, len(padded))
	}
	if padded[0] != 1 {
		t.Errorf("expected BOS=1 at index 0, got %d", padded[0])
	}
	if padded[len(padded)-1] != 2 {
		t.Errorf("expected EOS=2 at last index, got %d", padded[len(padded)-1])
	}
}

func TestPadPhonemeIDs_ExactMinimum(t *testing.T) {
	ids := make([]int64, minPhonemeIDs)
	ids[0] = 1
	ids[len(ids)-1] = 2

	padded, wasPadded := padPhonemeIDs(ids)
	if wasPadded {
		t.Error("expected wasPadded=false when exactly at minimum")
	}
	if len(padded) != minPhonemeIDs {
		t.Errorf("expected length %d, got %d", minPhonemeIDs, len(padded))
	}
}

func TestPadPhonemeIDs_AboveMinimum(t *testing.T) {
	ids := make([]int64, minPhonemeIDs+10)
	ids[0] = 1
	ids[len(ids)-1] = 2

	padded, wasPadded := padPhonemeIDs(ids)
	if wasPadded {
		t.Error("expected wasPadded=false when above minimum")
	}
	if len(padded) != len(ids) {
		t.Errorf("expected length %d, got %d", len(ids), len(padded))
	}
}

// ---------------------------------------------------------------------------
// Strategy A: padProsodyFeatures
// ---------------------------------------------------------------------------

func TestPadProsodyFeatures_NilInput(t *testing.T) {
	result := padProsodyFeatures(nil, 5, minPhonemeIDs)
	if result != nil {
		t.Error("expected nil for nil input")
	}
}

func TestPadProsodyFeatures_NoPaddingNeeded(t *testing.T) {
	original := make([][3]int64, minPhonemeIDs)
	result := padProsodyFeatures(original, minPhonemeIDs, minPhonemeIDs)
	if len(result) != minPhonemeIDs {
		t.Errorf("expected length %d, got %d", minPhonemeIDs, len(result))
	}
}

func TestPadProsodyFeatures_PaddingApplied(t *testing.T) {
	originalLen := 5
	paddedLen := minPhonemeIDs
	original := make([][3]int64, originalLen)
	for i := range original {
		original[i] = [3]int64{int64(i + 1), int64(i + 2), int64(i + 3)}
	}

	result := padProsodyFeatures(original, originalLen, paddedLen)
	if len(result) != paddedLen {
		t.Errorf("expected length %d, got %d", paddedLen, len(result))
	}

	// First element should match original BOS prosody.
	if result[0] != original[0] {
		t.Errorf("expected first element %v, got %v", original[0], result[0])
	}

	// Last element should match original EOS prosody.
	if result[len(result)-1] != original[len(original)-1] {
		t.Errorf("expected last element %v, got %v", original[len(original)-1], result[len(result)-1])
	}
}

// ---------------------------------------------------------------------------
// Strategy A: trimSilence
// ---------------------------------------------------------------------------

func TestTrimSilence_AllSilence(t *testing.T) {
	audio := make([]int16, 10000)
	trimmed := trimSilence(audio)
	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
}

func TestTrimSilence_ShortAudio(t *testing.T) {
	audio := make([]int16, trimMinSamples-100)
	for i := range audio {
		audio[i] = 1000
	}
	trimmed := trimSilence(audio)
	if len(trimmed) != len(audio) {
		t.Errorf("expected untouched audio of length %d, got %d", len(audio), len(trimmed))
	}
}

func TestTrimSilence_SilenceAroundContent(t *testing.T) {
	// 2000 silence + 5000 content + 2000 silence
	audio := make([]int16, 9000)
	for i := 2000; i < 7000; i++ {
		audio[i] = 10000
	}

	trimmed := trimSilence(audio)

	// The trimmed audio should be shorter.
	if len(trimmed) >= len(audio) {
		t.Errorf("expected trimmed audio to be shorter than %d, got %d", len(audio), len(trimmed))
	}
	// Should still contain the content.
	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
}

func TestTrimSilence_NoSilence(t *testing.T) {
	audio := make([]int16, 5000)
	for i := range audio {
		audio[i] = 5000
	}

	trimmed := trimSilence(audio)
	// Should be approximately the same length (no trimming needed).
	if len(trimmed) != len(audio) {
		t.Errorf("expected length %d, got %d", len(audio), len(trimmed))
	}
}

// ---------------------------------------------------------------------------
// Strategy A: windowRMS
// ---------------------------------------------------------------------------

func TestWindowRMS_Silence(t *testing.T) {
	samples := make([]int16, trimWindowSize)
	rms := windowRMS(samples)
	if rms != 0 {
		t.Errorf("expected RMS=0 for silence, got %f", rms)
	}
}

func TestWindowRMS_LoudSignal(t *testing.T) {
	samples := make([]int16, trimWindowSize)
	for i := range samples {
		samples[i] = math.MaxInt16
	}
	rms := windowRMS(samples)
	if rms < 0.99 {
		t.Errorf("expected RMS close to 1.0, got %f", rms)
	}
}

func TestWindowRMS_EmptySlice(t *testing.T) {
	rms := windowRMS(nil)
	if rms != 0 {
		t.Errorf("expected RMS=0 for empty slice, got %f", rms)
	}
}

// ---------------------------------------------------------------------------
// Strategy B: adjustScalesForShortText
// ---------------------------------------------------------------------------

func TestAdjustScales_NoAdjustment(t *testing.T) {
	ns, nw := adjustScalesForShortText(minPhonemeIDs, 0.667, 0.8)
	if ns != 0.667 {
		t.Errorf("expected noiseScale=0.667, got %f", ns)
	}
	if nw != 0.8 {
		t.Errorf("expected noiseW=0.8, got %f", nw)
	}
}

func TestAdjustScales_AboveMinimum(t *testing.T) {
	ns, nw := adjustScalesForShortText(minPhonemeIDs+10, 0.667, 0.8)
	if ns != 0.667 {
		t.Errorf("expected noiseScale=0.667, got %f", ns)
	}
	if nw != 0.8 {
		t.Errorf("expected noiseW=0.8, got %f", nw)
	}
}

func TestAdjustScales_VeryShort(t *testing.T) {
	// 5 phonemes -> ratio = 5/40 = 0.125
	// noiseScale *= max(0.5, 0.125) = 0.5
	// noiseW *= max(0.4, 0.125) = 0.4
	ns, nw := adjustScalesForShortText(5, 0.667, 0.8)

	expectedNS := float32(0.667 * 0.5)
	expectedNW := float32(0.8 * 0.4)

	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

func TestAdjustScales_HalfMinimum(t *testing.T) {
	// 20 phonemes -> ratio = 20/40 = 0.5
	// noiseScale *= max(0.5, 0.5) = 0.5
	// noiseW *= max(0.4, 0.5) = 0.5
	ns, nw := adjustScalesForShortText(20, 0.667, 0.8)

	expectedNS := float32(0.667 * 0.5)
	expectedNW := float32(0.8 * 0.5)

	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

func TestAdjustScales_MostlyFull(t *testing.T) {
	// 35 phonemes -> ratio = 35/40 = 0.875
	// noiseScale *= max(0.5, 0.875) = 0.875
	// noiseW *= max(0.4, 0.875) = 0.875
	ns, nw := adjustScalesForShortText(35, 0.667, 0.8)

	expectedNS := float32(0.667 * 0.875)
	expectedNW := float32(0.8 * 0.875)

	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

// ---------------------------------------------------------------------------
// Strategy C: wrapShortTextWithBreaks
// ---------------------------------------------------------------------------

func TestWrapShortText_EmptyString(t *testing.T) {
	text, needsPad := wrapShortTextWithBreaks("")
	if needsPad {
		t.Error("expected needsPad=false for empty string")
	}
	if text != "" {
		t.Errorf("expected empty string, got %q", text)
	}
}

func TestWrapShortText_WhitespaceOnly(t *testing.T) {
	text, needsPad := wrapShortTextWithBreaks("   ")
	if needsPad {
		t.Error("expected needsPad=false for whitespace-only")
	}
	if text != "   " {
		t.Errorf("expected whitespace string, got %q", text)
	}
}

func TestWrapShortText_ShortText(t *testing.T) {
	text, needsPad := wrapShortTextWithBreaks("Hello")
	if !needsPad {
		t.Error("expected needsPad=true for short text")
	}
	if text != "Hello" {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_ExactThreshold(t *testing.T) {
	// Exactly shortTextChars non-space characters.
	text, needsPad := wrapShortTextWithBreaks("1234567890")
	if !needsPad {
		t.Error("expected needsPad=true for text at exact threshold")
	}
	if text != "1234567890" {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_AboveThreshold(t *testing.T) {
	text, needsPad := wrapShortTextWithBreaks("12345678901")
	if needsPad {
		t.Error("expected needsPad=false for text above threshold")
	}
	if text != "12345678901" {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_ShortWithSpaces(t *testing.T) {
	// "ab cd" has 4 non-space chars.
	text, needsPad := wrapShortTextWithBreaks("ab cd")
	if !needsPad {
		t.Error("expected needsPad=true for short text with spaces")
	}
	if text != "ab cd" {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_SSMLInput(t *testing.T) {
	ssml := "<speak>Hello</speak>"
	text, needsPad := wrapShortTextWithBreaks(ssml)
	if needsPad {
		t.Error("expected needsPad=false for SSML input")
	}
	if text != ssml {
		t.Errorf("expected original SSML, got %q", text)
	}
}

func TestWrapShortText_LongText(t *testing.T) {
	long := "This is a much longer sentence that exceeds the threshold."
	text, needsPad := wrapShortTextWithBreaks(long)
	if needsPad {
		t.Error("expected needsPad=false for long text")
	}
	if text != long {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_Japanese(t *testing.T) {
	// "abc" = 3 non-space chars.
	text, needsPad := wrapShortTextWithBreaks("abc")
	if !needsPad {
		t.Error("expected needsPad=true for short Japanese-length text")
	}
	if text != "abc" {
		t.Errorf("expected original text, got %q", text)
	}
}

func TestWrapShortText_CJKShort(t *testing.T) {
	// 5 CJK characters.
	cjk := "\u3053\u3093\u306b\u3061\u306f"
	text, needsPad := wrapShortTextWithBreaks(cjk)
	if !needsPad {
		t.Error("expected needsPad=true for short CJK text")
	}
	if text != cjk {
		t.Errorf("expected original CJK text, got %q", text)
	}
}

// ---------------------------------------------------------------------------
// Strategy C: countNonSpaceChars
// ---------------------------------------------------------------------------

func TestCountNonSpaceChars(t *testing.T) {
	tests := []struct {
		input string
		want  int
	}{
		{"", 0},
		{"   ", 0},
		{"abc", 3},
		{"a b c", 3},
		{" a b c ", 3},
		{"\t\n", 0},
		{"\u3053\u3093\u306b\u3061\u306f", 5},
	}

	for _, tt := range tests {
		got := countNonSpaceChars(tt.input)
		if got != tt.want {
			t.Errorf("countNonSpaceChars(%q) = %d, want %d", tt.input, got, tt.want)
		}
	}
}

// ---------------------------------------------------------------------------
// Strategy C: prependSilence / appendSilence
// ---------------------------------------------------------------------------

func TestPrependSilence(t *testing.T) {
	audio := []int16{100, 200, 300}
	result := prependSilence(audio, 22050, 300)

	expectedSilenceSamples := 22050 * 300 / 1000 // 6615
	expectedLen := expectedSilenceSamples + len(audio)

	if len(result) != expectedLen {
		t.Errorf("expected length %d, got %d", expectedLen, len(result))
	}

	// Silence region should be zero.
	for i := 0; i < expectedSilenceSamples; i++ {
		if result[i] != 0 {
			t.Errorf("expected silence at index %d, got %d", i, result[i])
			break
		}
	}

	// Original audio should follow.
	for i, v := range audio {
		if result[expectedSilenceSamples+i] != v {
			t.Errorf("expected audio[%d]=%d at index %d, got %d", i, v, expectedSilenceSamples+i, result[expectedSilenceSamples+i])
		}
	}
}

func TestAppendSilence(t *testing.T) {
	audio := []int16{100, 200, 300}
	result := appendSilence(audio, 22050, 300)

	expectedSilenceSamples := 22050 * 300 / 1000 // 6615
	expectedLen := len(audio) + expectedSilenceSamples

	if len(result) != expectedLen {
		t.Errorf("expected length %d, got %d", expectedLen, len(result))
	}

	// Original audio should be at the front.
	for i, v := range audio {
		if result[i] != v {
			t.Errorf("expected audio[%d]=%d, got %d", i, v, result[i])
		}
	}

	// Trailing silence should be zero.
	for i := len(audio); i < len(result); i++ {
		if result[i] != 0 {
			t.Errorf("expected silence at index %d, got %d", i, result[i])
			break
		}
	}
}

// ---------------------------------------------------------------------------
// shortTextMitigationSummary
// ---------------------------------------------------------------------------

func TestShortTextMitigationSummary(t *testing.T) {
	tests := []struct {
		name           string
		origLen        int
		paddedLen      int
		wasPadded      bool
		scalesAdjusted bool
		wantEmpty      bool
	}{
		{"no mitigation", 50, 50, false, false, true},
		{"padded only", 5, 40, true, false, false},
		{"scales only", 5, 5, false, true, false},
		{"both", 5, 40, true, true, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := shortTextMitigationSummary(tt.origLen, tt.paddedLen, tt.wasPadded, tt.scalesAdjusted)
			if tt.wantEmpty && result != "" {
				t.Errorf("expected empty summary, got %q", result)
			}
			if !tt.wantEmpty && result == "" {
				t.Error("expected non-empty summary")
			}
		})
	}
}

// ---------------------------------------------------------------------------
// trimSilence boundary conditions
// ---------------------------------------------------------------------------

func TestTrimSilence_ExactMinSamples(t *testing.T) {
	// len(audio) == trimMinSamples: should be returned as-is (early return).
	audio := make([]int16, trimMinSamples)
	for i := range audio {
		audio[i] = 5000
	}
	trimmed := trimSilence(audio)
	if len(trimmed) != trimMinSamples {
		t.Errorf("expected length %d, got %d", trimMinSamples, len(trimmed))
	}
}

func TestTrimSilence_OneAboveMinSamples(t *testing.T) {
	// len(audio) == trimMinSamples+1: just above the early-return threshold.
	// All loud content, so nothing to trim.
	audio := make([]int16, trimMinSamples+1)
	for i := range audio {
		audio[i] = 5000
	}
	trimmed := trimSilence(audio)
	if len(trimmed) != len(audio) {
		t.Errorf("expected length %d, got %d", len(audio), len(trimmed))
	}
}

func TestTrimSilence_RMSExactlyAtThreshold(t *testing.T) {
	// Build a window whose RMS is exactly trimThresholdRMS (0.01).
	// RMS = sqrt(sum(v^2)/n), normalized by MaxInt16.
	// For uniform value v: RMS = |v|/MaxInt16.
	// v = trimThresholdRMS * MaxInt16 = 0.01 * 32767 ~ 327.67 -> 327
	//
	// With v=327: RMS = 327/32767 ~ 0.00998 < 0.01 (treated as silence).
	// With v=328: RMS = 328/32767 ~ 0.01003 > 0.01 (not silence).
	//
	// Construct: silence + borderline window + silence.
	totalLen := trimMinSamples + 1000
	audio := make([]int16, totalLen)

	// Place a window of value 327 (just below threshold) in the middle.
	// This should be treated as silence; entire audio is "silent".
	midStart := totalLen/2 - trimWindowSize/2
	for i := midStart; i < midStart+trimWindowSize; i++ {
		audio[i] = 327
	}

	trimmed := trimSilence(audio)
	// All silence path: should return at least trimMinSamples.
	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}

	// Now test with value 328 (just above threshold) -- should detect as content.
	audio2 := make([]int16, totalLen)
	midStart2 := totalLen/2 - trimWindowSize/2
	for i := midStart2; i < midStart2+trimWindowSize; i++ {
		audio2[i] = 328
	}

	trimmed2 := trimSilence(audio2)
	// Should detect the content and trim surrounding silence.
	if len(trimmed2) >= len(audio2) {
		t.Errorf("expected trimmed audio shorter than %d, got %d", len(audio2), len(trimmed2))
	}
	if len(trimmed2) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed2))
	}
}

func TestTrimSilence_MultiStageAdjustment_StartNegative(t *testing.T) {
	// Force the scenario where the detected content region is near the
	// beginning of the audio, so expanding symmetrically would push start < 0.
	// Layout: tiny non-silent window at the very start, then all silence.
	audioLen := trimMinSamples * 2
	audio := make([]int16, audioLen)
	// Place loud content only in the first window.
	for i := 0; i < trimWindowSize; i++ {
		audio[i] = 10000
	}

	trimmed := trimSilence(audio)

	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
	// start must not be negative (would panic on slice).
	// The test passing without panic verifies the start < 0 guard works.
}

func TestTrimSilence_MultiStageAdjustment_EndOverflow(t *testing.T) {
	// Force the scenario where the detected content region is near the
	// end of the audio, so expanding would push end > len(audio).
	audioLen := trimMinSamples * 2
	audio := make([]int16, audioLen)
	// Place loud content only in the last window.
	for i := audioLen - trimWindowSize; i < audioLen; i++ {
		audio[i] = 10000
	}

	trimmed := trimSilence(audio)

	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
	if len(trimmed) > len(audio) {
		t.Errorf("trimmed length %d exceeds original %d", len(trimmed), len(audio))
	}
}

func TestTrimSilence_MultiStageAdjustment_BothOverflow(t *testing.T) {
	// Audio slightly larger than trimMinSamples with a tiny content
	// region in the center, so expansion hits both boundaries.
	audioLen := trimMinSamples + trimWindowSize
	audio := make([]int16, audioLen)
	center := audioLen / 2
	for i := center; i < center+trimWindowSize && i < audioLen; i++ {
		audio[i] = 10000
	}

	trimmed := trimSilence(audio)

	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
	if len(trimmed) > len(audio) {
		t.Errorf("trimmed length %d exceeds original %d", len(trimmed), len(audio))
	}
}

func TestTrimSilence_AllSilenceSlightlyAboveMin(t *testing.T) {
	// All-silence audio that is only slightly above trimMinSamples.
	// Tests the center-portion fallback + minimum guarantee together.
	audio := make([]int16, trimMinSamples+1)
	trimmed := trimSilence(audio)
	if len(trimmed) < trimMinSamples {
		t.Errorf("expected at least %d samples, got %d", trimMinSamples, len(trimmed))
	}
	if len(trimmed) > len(audio) {
		t.Errorf("trimmed length %d exceeds original %d", len(trimmed), len(audio))
	}
}

// ---------------------------------------------------------------------------
// padProsodyFeatures edge cases
// ---------------------------------------------------------------------------

func TestPadProsodyFeatures_BOSEOSOnly(t *testing.T) {
	// Minimal prosody: just BOS and EOS (2 elements), matching phoneme [BOS, EOS].
	original := [][3]int64{{1, 2, 3}, {4, 5, 6}}
	originalLen := 2
	paddedLen := minPhonemeIDs

	result := padProsodyFeatures(original, originalLen, paddedLen)

	if len(result) != paddedLen {
		t.Errorf("expected length %d, got %d", paddedLen, len(result))
	}

	// First element must be BOS prosody.
	if result[0] != original[0] {
		t.Errorf("expected BOS prosody %v, got %v", original[0], result[0])
	}

	// Last element must be EOS prosody.
	if result[len(result)-1] != original[1] {
		t.Errorf("expected EOS prosody %v, got %v", original[1], result[len(result)-1])
	}
}

func TestPadProsodyFeatures_SingleElement(t *testing.T) {
	// Edge case: only 1 prosody element (just BOS, no EOS in original).
	original := [][3]int64{{7, 8, 9}}
	originalLen := 1
	paddedLen := minPhonemeIDs

	result := padProsodyFeatures(original, originalLen, paddedLen)

	if len(result) != paddedLen {
		t.Errorf("expected length %d, got %d", paddedLen, len(result))
	}

	// First element must be the single original prosody.
	if result[0] != original[0] {
		t.Errorf("expected first element %v, got %v", original[0], result[0])
	}

	// Last element should be zero (from back padding; no separate EOS for single-element input).
	zero := [3]int64{}
	if result[len(result)-1] != zero {
		t.Errorf("expected zero prosody at last position, got %v", result[len(result)-1])
	}
}

func TestPadProsodyFeatures_OriginalLenMismatch(t *testing.T) {
	// Case where len(original) > originalLen. The function should use originalLen
	// for indexing calculations but len(original) for actual data access.
	// original has 5 elements but originalLen says 3.
	original := [][3]int64{
		{1, 1, 1}, {2, 2, 2}, {3, 3, 3}, {4, 4, 4}, {5, 5, 5},
	}
	originalLen := 3
	paddedLen := minPhonemeIDs

	result := padProsodyFeatures(original, originalLen, paddedLen)

	if len(result) != paddedLen {
		t.Errorf("expected length %d, got %d", paddedLen, len(result))
	}

	// First element should be original[0].
	if result[0] != original[0] {
		t.Errorf("expected first element %v, got %v", original[0], result[0])
	}
}

func TestPadProsodyFeatures_PaddedLenSmallerThanOriginal(t *testing.T) {
	// If paddedLen <= originalLen, no padding should occur.
	original := [][3]int64{
		{1, 1, 1}, {2, 2, 2}, {3, 3, 3}, {4, 4, 4}, {5, 5, 5},
	}
	result := padProsodyFeatures(original, 5, 3)

	// Should return original unchanged.
	if len(result) != len(original) {
		t.Errorf("expected length %d, got %d", len(original), len(result))
	}
}

func TestPadProsodyFeatures_EmptySlice(t *testing.T) {
	// Empty (but non-nil) slice should return nil.
	result := padProsodyFeatures([][3]int64{}, 0, minPhonemeIDs)
	if result != nil {
		t.Errorf("expected nil for empty input, got length %d", len(result))
	}
}

// ---------------------------------------------------------------------------
// Strategy C logging: shortTextMitigationSummary additional cases
// ---------------------------------------------------------------------------

func TestShortTextMitigationSummary_ContainsPaddedInfo(t *testing.T) {
	result := shortTextMitigationSummary(5, 40, true, false)
	if result == "" {
		t.Fatal("expected non-empty summary")
	}
	// Should mention the original and padded lengths.
	if !containsSubstring(result, "5") || !containsSubstring(result, "40") {
		t.Errorf("expected summary to contain phoneme counts, got %q", result)
	}
}

func TestShortTextMitigationSummary_ContainsScalesInfo(t *testing.T) {
	result := shortTextMitigationSummary(5, 5, false, true)
	if result == "" {
		t.Fatal("expected non-empty summary")
	}
	if !containsSubstring(result, "scales") {
		t.Errorf("expected summary to mention scales, got %q", result)
	}
}

func TestShortTextMitigationSummary_BothStrategies(t *testing.T) {
	result := shortTextMitigationSummary(5, 40, true, true)
	if result == "" {
		t.Fatal("expected non-empty summary")
	}
	// Should contain both pieces of information.
	if !containsSubstring(result, "padded") || !containsSubstring(result, "scales") {
		t.Errorf("expected summary with both padded and scales info, got %q", result)
	}
}

// containsSubstring is a test helper that checks if s contains substr.
func containsSubstring(s, substr string) bool {
	return len(s) >= len(substr) && searchSubstring(s, substr)
}

func searchSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// windowRMS additional boundary tests
// ---------------------------------------------------------------------------

func TestWindowRMS_SingleSample(t *testing.T) {
	samples := []int16{math.MaxInt16}
	rms := windowRMS(samples)
	if rms < 0.99 {
		t.Errorf("expected RMS close to 1.0 for single max sample, got %f", rms)
	}
}

func TestWindowRMS_MixedSignal(t *testing.T) {
	// Half max positive, half max negative -- RMS should still be ~1.0.
	samples := make([]int16, trimWindowSize)
	for i := range samples {
		if i%2 == 0 {
			samples[i] = math.MaxInt16
		} else {
			samples[i] = math.MinInt16 + 1 // avoid overflow: MinInt16 = -32768
		}
	}
	rms := windowRMS(samples)
	if rms < 0.99 {
		t.Errorf("expected RMS close to 1.0 for alternating max signal, got %f", rms)
	}
}

// ---------------------------------------------------------------------------
// adjustScalesForShortText additional edge cases
// ---------------------------------------------------------------------------

func TestAdjustScales_ZeroPhonemes(t *testing.T) {
	// Edge case: 0 phonemes.
	ns, nw := adjustScalesForShortText(0, 0.667, 0.8)
	// ratio = 0/40 = 0, clamped floors: noiseScale *= 0.5, noiseW *= 0.4
	expectedNS := float32(0.667 * 0.5)
	expectedNW := float32(0.8 * 0.4)
	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

func TestAdjustScales_OnePhoneme(t *testing.T) {
	// ratio = 1/40 = 0.025, clamped: noiseScale *= 0.5, noiseW *= 0.4
	ns, nw := adjustScalesForShortText(1, 1.0, 1.0)
	expectedNS := float32(0.5)
	expectedNW := float32(0.4)
	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

func TestAdjustScales_JustBelowMinimum(t *testing.T) {
	// 39 phonemes -> ratio = 39/40 = 0.975
	ns, nw := adjustScalesForShortText(39, 0.667, 0.8)
	expectedNS := float32(0.667 * 0.975)
	expectedNW := float32(0.8 * 0.975)
	if math.Abs(float64(ns-expectedNS)) > 0.001 {
		t.Errorf("expected noiseScale~%f, got %f", expectedNS, ns)
	}
	if math.Abs(float64(nw-expectedNW)) > 0.001 {
		t.Errorf("expected noiseW~%f, got %f", expectedNW, nw)
	}
}

// ---------------------------------------------------------------------------
// Constants validation
// ---------------------------------------------------------------------------

func TestConstants(t *testing.T) {
	if minPhonemeIDs != 40 {
		t.Errorf("expected minPhonemeIDs=40, got %d", minPhonemeIDs)
	}
	if shortTextChars != 10 {
		t.Errorf("expected shortTextChars=10, got %d", shortTextChars)
	}
	if silencePadMs != 300 {
		t.Errorf("expected silencePadMs=300, got %d", silencePadMs)
	}
	if trimMinSamples != 2205 {
		t.Errorf("expected trimMinSamples=2205, got %d", trimMinSamples)
	}
	if trimWindowSize != 256 {
		t.Errorf("expected trimWindowSize=256, got %d", trimWindowSize)
	}
}
