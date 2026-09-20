package piperplus

import (
	"encoding/json"
	"math"
	"strings"
	"testing"
)

func almostEqual(a, b, epsilon float64) bool {
	return math.Abs(a-b) < epsilon
}

func TestDurationsToTiming_Basic(t *testing.T) {
	durations := []float32{10.0, 20.0, 5.0}
	tokens := []string{"a", "b", "c"}
	sampleRate := 22050
	hopLength := 256

	result, err := DurationsToTiming(durations, tokens, sampleRate, hopLength)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	const eps = 0.1
	msPerFrame := float64(hopLength) / float64(sampleRate) * 1000.0

	if len(result.Phonemes) != 3 {
		t.Fatalf("expected 3 phonemes, got %d", len(result.Phonemes))
	}

	// Phoneme 0: start~0, duration~116.1, end~116.1
	p0 := result.Phonemes[0]
	if p0.Phoneme != "a" {
		t.Errorf("phoneme[0]: expected %q, got %q", "a", p0.Phoneme)
	}
	if !almostEqual(p0.StartMs, 0.0, eps) {
		t.Errorf("phoneme[0].StartMs: expected ~0.0, got %f", p0.StartMs)
	}
	expectedDur0 := 10.0 * msPerFrame
	if !almostEqual(p0.DurationMs, expectedDur0, eps) {
		t.Errorf("phoneme[0].DurationMs: expected ~%f, got %f", expectedDur0, p0.DurationMs)
	}
	if !almostEqual(p0.EndMs, expectedDur0, eps) {
		t.Errorf("phoneme[0].EndMs: expected ~%f, got %f", expectedDur0, p0.EndMs)
	}

	// Phoneme 1: start~116.1, duration~232.2, end~348.3
	p1 := result.Phonemes[1]
	if p1.Phoneme != "b" {
		t.Errorf("phoneme[1]: expected %q, got %q", "b", p1.Phoneme)
	}
	expectedStart1 := expectedDur0
	expectedDur1 := 20.0 * msPerFrame
	if !almostEqual(p1.StartMs, expectedStart1, eps) {
		t.Errorf("phoneme[1].StartMs: expected ~%f, got %f", expectedStart1, p1.StartMs)
	}
	if !almostEqual(p1.DurationMs, expectedDur1, eps) {
		t.Errorf("phoneme[1].DurationMs: expected ~%f, got %f", expectedDur1, p1.DurationMs)
	}
	if !almostEqual(p1.EndMs, expectedStart1+expectedDur1, eps) {
		t.Errorf("phoneme[1].EndMs: expected ~%f, got %f", expectedStart1+expectedDur1, p1.EndMs)
	}

	// Phoneme 2: start~348.3, duration~58.0, end~406.3
	p2 := result.Phonemes[2]
	if p2.Phoneme != "c" {
		t.Errorf("phoneme[2]: expected %q, got %q", "c", p2.Phoneme)
	}
	expectedStart2 := expectedStart1 + expectedDur1
	expectedDur2 := 5.0 * msPerFrame
	if !almostEqual(p2.StartMs, expectedStart2, eps) {
		t.Errorf("phoneme[2].StartMs: expected ~%f, got %f", expectedStart2, p2.StartMs)
	}
	if !almostEqual(p2.DurationMs, expectedDur2, eps) {
		t.Errorf("phoneme[2].DurationMs: expected ~%f, got %f", expectedDur2, p2.DurationMs)
	}
	if !almostEqual(p2.EndMs, expectedStart2+expectedDur2, eps) {
		t.Errorf("phoneme[2].EndMs: expected ~%f, got %f", expectedStart2+expectedDur2, p2.EndMs)
	}

	// TotalDuration ~406.3
	expectedTotal := expectedDur0 + expectedDur1 + expectedDur2
	if !almostEqual(result.TotalDurationMs, expectedTotal, eps) {
		t.Errorf("TotalDurationMs: expected ~%f, got %f", expectedTotal, result.TotalDurationMs)
	}

	if result.SampleRate != sampleRate {
		t.Errorf("SampleRate: expected %d, got %d", sampleRate, result.SampleRate)
	}
}

func TestDurationsToTiming_NegativeDuration(t *testing.T) {
	durations := []float32{-5.0, 10.0}
	tokens := []string{"x", "y"}

	result, err := DurationsToTiming(durations, tokens, 22050, 256)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Negative duration should be clamped to 0.
	if result.Phonemes[0].DurationMs != 0.0 {
		t.Errorf("expected negative duration clamped to 0, got %f", result.Phonemes[0].DurationMs)
	}
	if result.Phonemes[0].StartMs != 0.0 {
		t.Errorf("expected start 0, got %f", result.Phonemes[0].StartMs)
	}
	if result.Phonemes[0].EndMs != 0.0 {
		t.Errorf("expected end 0, got %f", result.Phonemes[0].EndMs)
	}

	// Second phoneme should start at 0 since first was clamped.
	if result.Phonemes[1].StartMs != 0.0 {
		t.Errorf("expected phoneme[1].StartMs = 0, got %f", result.Phonemes[1].StartMs)
	}
	if result.Phonemes[1].DurationMs <= 0 {
		t.Errorf("expected positive duration for phoneme[1], got %f", result.Phonemes[1].DurationMs)
	}
}

func TestDurationsToTiming_ZeroDurations(t *testing.T) {
	durations := []float32{0, 0, 0}
	tokens := []string{"a", "b", "c"}

	result, err := DurationsToTiming(durations, tokens, 22050, 256)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	for i, p := range result.Phonemes {
		if p.StartMs != 0 || p.EndMs != 0 || p.DurationMs != 0 {
			t.Errorf("phoneme[%d]: expected all zeros, got start=%f end=%f dur=%f",
				i, p.StartMs, p.EndMs, p.DurationMs)
		}
	}

	if result.TotalDurationMs != 0 {
		t.Errorf("expected total duration 0, got %f", result.TotalDurationMs)
	}
}

func TestDurationsToTiming_LengthMismatch(t *testing.T) {
	durations := []float32{1.0, 2.0, 3.0}
	tokens := []string{"a", "b"}

	_, err := DurationsToTiming(durations, tokens, 22050, 256)
	if err == nil {
		t.Fatal("expected error for length mismatch, got nil")
	}
	if !strings.Contains(err.Error(), "length mismatch") {
		t.Errorf("expected error to contain %q, got %q", "length mismatch", err.Error())
	}
}

func TestDurationsToTiming_InvalidSampleRate(t *testing.T) {
	durations := []float32{1.0}
	tokens := []string{"a"}

	_, err := DurationsToTiming(durations, tokens, 0, 256)
	if err == nil {
		t.Fatal("expected error for sampleRate=0, got nil")
	}
	if !strings.Contains(err.Error(), "sampleRate") {
		t.Errorf("expected error to mention sampleRate, got %q", err.Error())
	}
}

func TestDurationsToTiming_InvalidHopLength(t *testing.T) {
	durations := []float32{1.0}
	tokens := []string{"a"}

	_, err := DurationsToTiming(durations, tokens, 22050, 0)
	if err == nil {
		t.Fatal("expected error for hopLength=0, got nil")
	}
	if !strings.Contains(err.Error(), "hopLength") {
		t.Errorf("expected error to mention hopLength, got %q", err.Error())
	}
}

func TestTimingResult_ToTSV(t *testing.T) {
	result := &TimingResult{
		Phonemes: []PhonemeTimingInfo{
			{Phoneme: "a", StartMs: 0.0, EndMs: 100.0, DurationMs: 100.0},
			{Phoneme: "b", StartMs: 100.0, EndMs: 250.0, DurationMs: 150.0},
		},
		TotalDurationMs: 250.0,
		SampleRate:      22050,
	}

	tsv := result.ToTSV()
	lines := strings.Split(strings.TrimRight(tsv, "\n"), "\n")

	if len(lines) != 3 {
		t.Fatalf("expected 3 lines (header + 2 data), got %d", len(lines))
	}

	// Verify header.
	expectedHeader := "start_ms\tend_ms\tduration_ms\tphoneme"
	if lines[0] != expectedHeader {
		t.Errorf("header: expected %q, got %q", expectedHeader, lines[0])
	}

	// Verify data lines contain tab-separated fields.
	fields1 := strings.Split(lines[1], "\t")
	if len(fields1) != 4 {
		t.Errorf("expected 4 fields in data line, got %d", len(fields1))
	}
	if fields1[3] != "a" {
		t.Errorf("expected phoneme %q, got %q", "a", fields1[3])
	}

	fields2 := strings.Split(lines[2], "\t")
	if len(fields2) != 4 {
		t.Errorf("expected 4 fields in data line, got %d", len(fields2))
	}
	if fields2[3] != "b" {
		t.Errorf("expected phoneme %q, got %q", "b", fields2[3])
	}
}

func TestTimingResult_ToJSON(t *testing.T) {
	result := &TimingResult{
		Phonemes: []PhonemeTimingInfo{
			{Phoneme: "a", StartMs: 0.0, EndMs: 100.0, DurationMs: 100.0},
		},
		TotalDurationMs: 100.0,
		SampleRate:      22050,
	}

	data, err := result.ToJSON()
	if err != nil {
		t.Fatalf("ToJSON error: %v", err)
	}

	// Verify it is valid JSON.
	var parsed map[string]interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		t.Fatalf("ToJSON produced invalid JSON: %v", err)
	}

	// Verify expected top-level fields.
	if _, ok := parsed["phonemes"]; !ok {
		t.Error("JSON missing 'phonemes' field")
	}
	if _, ok := parsed["total_duration_ms"]; !ok {
		t.Error("JSON missing 'total_duration_ms' field")
	}
	if _, ok := parsed["sample_rate"]; !ok {
		t.Error("JSON missing 'sample_rate' field")
	}

	// Verify compact output is also valid.
	compact, err := result.ToJSONCompact()
	if err != nil {
		t.Fatalf("ToJSONCompact error: %v", err)
	}
	var parsedCompact map[string]interface{}
	if err := json.Unmarshal(compact, &parsedCompact); err != nil {
		t.Fatalf("ToJSONCompact produced invalid JSON: %v", err)
	}

	// Compact should not contain newlines.
	if strings.Contains(string(compact), "\n") {
		t.Error("compact JSON should not contain newlines")
	}
}

// ----------------------------------------------------------------------
// SRT format tests — spec [output_formats.srt]. Cross-runtime parity
// with Rust (test_srt_format / test_srt_large_timestamps in timing.rs)
// and Python (_format_srt_timestamp in timing.py).
// ----------------------------------------------------------------------

func TestFormatSRTTimestamp_ZeroIsAllZeros(t *testing.T) {
	got := formatSRTTimestamp(0)
	want := "00:00:00,000"
	if got != want {
		t.Errorf("formatSRTTimestamp(0) = %q; want %q", got, want)
	}
}

func TestFormatSRTTimestamp_VariousMagnitudes(t *testing.T) {
	cases := []struct {
		ms   float64
		want string
	}{
		{1.0, "00:00:00,001"},
		{999.0, "00:00:00,999"},
		{1000.0, "00:00:01,000"},
		{61_500.0, "00:01:01,500"},
		{3_600_000.0, "01:00:00,000"},
		{3_661_123.0, "01:01:01,123"},
	}
	for _, tc := range cases {
		if got := formatSRTTimestamp(tc.ms); got != tc.want {
			t.Errorf("formatSRTTimestamp(%v) = %q; want %q", tc.ms, got, tc.want)
		}
	}
}

// SRT millisecond rounding is half-away-from-zero per
// docs/spec/phoneme-timing-contract.toml [output_formats.srt].rounding. Every
// case has an EVEN integer part, which is exactly where half-to-even and
// half-away-from-zero disagree; a case such as 1.5 rounds to 2 under both and
// proves nothing. Python and C# used their language default (ToEven) and were
// 1 ms early on every such boundary (issue #681) -- this runtime is the
// reference the others cite, so these cases lock it in place.
func TestFormatSRTTimestamp_RoundsHalfAwayFromZero(t *testing.T) {
	cases := []struct {
		ms   float64
		want string
	}{
		{0.5, "00:00:00,001"},
		{1234.5, "00:00:01,235"},
		{2500.5, "00:00:02,501"},
		{0.0, "00:00:00,000"},
		// Largest double below 0.5: ms + 0.5 is exactly 1.0 in binary64, so the
		// floor(ms + 0.5) idiom yields 1 here while math.Round yields 0.
		{0.49999999999999994, "00:00:00,000"},
		{3661500.0, "01:01:01,500"},
	}
	for _, tc := range cases {
		if got := formatSRTTimestamp(tc.ms); got != tc.want {
			t.Errorf("formatSRTTimestamp(%v) = %q; want %q (must round half away from zero)", tc.ms, got, tc.want)
		}
	}
}

func TestFormatSRTTimestamp_NegativeClampsToZero(t *testing.T) {
	got := formatSRTTimestamp(-100)
	want := "00:00:00,000"
	if got != want {
		t.Errorf("formatSRTTimestamp(-100) = %q; want %q (negative must clamp)", got, want)
	}
}

func TestToSRT_SingleCueShape(t *testing.T) {
	// hop=1 / sample_rate=1000 → 1 frame == 1 ms (Rust fixture style).
	durations := []float32{500}
	tokens := []string{"a"}
	result, err := DurationsToTiming(durations, tokens, 1000, 1)
	if err != nil {
		t.Fatalf("DurationsToTiming error: %v", err)
	}

	got := result.ToSRT()
	want := "1\n00:00:00,000 --> 00:00:00,500\na\n\n"
	if got != want {
		t.Errorf("ToSRT mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestToSRT_ThreePhonemesUseSequentialOneBasedIndex(t *testing.T) {
	durations := []float32{100, 200, 50}
	tokens := []string{"a", "b", "c"}
	result, err := DurationsToTiming(durations, tokens, 1000, 1)
	if err != nil {
		t.Fatalf("DurationsToTiming error: %v", err)
	}

	got := result.ToSRT()
	expected := "" +
		"1\n00:00:00,000 --> 00:00:00,100\na\n\n" +
		"2\n00:00:00,100 --> 00:00:00,300\nb\n\n" +
		"3\n00:00:00,300 --> 00:00:00,350\nc\n\n"
	if got != expected {
		t.Errorf("ToSRT mismatch\n got: %q\nwant: %q", got, expected)
	}
}

func TestToSRT_EmptyTimingProducesEmptyString(t *testing.T) {
	result, err := DurationsToTiming([]float32{}, []string{}, 22050, 256)
	if err != nil {
		t.Fatalf("DurationsToTiming error: %v", err)
	}
	if got := result.ToSRT(); got != "" {
		t.Errorf("ToSRT() on empty timing = %q; want empty string", got)
	}
}

// ---- reverse map (issue #656) ----
//
// Pins the three rules of spec [reverse_map] (first-wins / PUA fallback /
// explicit mapping) and agreement with the canonical Python and JS mirrors.
// Before the fix the Go CLI emitted `p0`, `p1`, ... positional placeholders, so
// the timing output could not identify phonemes at all.

func sampleIDMap() map[string][]int64 {
	return map[string][]int64{
		"a":  {5},
		"b":  {6, 7},
		"":  {42},
		"ch": {50},
	}
}

func TestBuildPhonemeIDReverseMap_MapsEveryIDOfAKey(t *testing.T) {
	reverse := BuildPhonemeIDReverseMap(sampleIDMap(), nil)
	if got := reverse[5]; got != "a" {
		t.Errorf("id 5 = %q; want %q", got, "a")
	}
	// Both ids of "b" must resolve; the canonical doctest pins {6: 'b', 7: 'b'}.
	if got := reverse[6]; got != "b" {
		t.Errorf("id 6 = %q; want %q", got, "b")
	}
	if got := reverse[7]; got != "b" {
		t.Errorf("id 7 = %q; want %q", got, "b")
	}
}

func TestBuildPhonemeIDReverseMap_RendersUnmappedPUAAsCodepoint(t *testing.T) {
	reverse := BuildPhonemeIDReverseMap(sampleIDMap(), nil)
	// [reverse_map.pua_handling]: uppercase, 4 hex digits.
	if got := reverse[42]; got != "U+E019" {
		t.Errorf("id 42 = %q; want %q", got, "U+E019")
	}
}

func TestBuildPhonemeIDReverseMap_PrefersExplicitPUAName(t *testing.T) {
	reverse := BuildPhonemeIDReverseMap(sampleIDMap(), map[string]string{"": "N_m"})
	if got := reverse[42]; got != "N_m" {
		t.Errorf("id 42 = %q; want %q", got, "N_m")
	}
}

func TestBuildPhonemeIDReverseMap_PassesMultiCharKeysThrough(t *testing.T) {
	reverse := BuildPhonemeIDReverseMap(sampleIDMap(), nil)
	// "ch" is two runes, so the PUA branch must not fire.
	if got := reverse[50]; got != "ch" {
		t.Errorf("id 50 = %q; want %q", got, "ch")
	}
}

// NOTE: this pins DETERMINISM, not cross-runtime parity. Python and JS resolve
// first-wins in insertion order and would pick "zz" here. The contract records
// the divergence under [reverse_map.collision_resolution] key_order; it is
// unreachable for every shipped model because none has a collision (in-tree
// fixture: 173 keys, 0).
func TestBuildPhonemeIDReverseMap_DeterministicOnCollision(t *testing.T) {
	// Two keys claim id 9. Go map iteration is randomized, so the
	// implementation sorts keys: "aa" must win on every run.
	m := map[string][]int64{"zz": {9}, "aa": {9}}
	for i := 0; i < 16; i++ {
		if got := BuildPhonemeIDReverseMap(m, nil)[9]; got != "aa" {
			t.Fatalf("run %d: id 9 = %q; want %q (collision winner must be stable)", i, got, "aa")
		}
	}
}

func TestBuildPhonemeIDReverseMap_PUABoundaries(t *testing.T) {
	m := map[string][]int64{
		"퟿": {1}, // below the surrogate block
		"": {2}, // first PUA
		"": {3}, // last PUA
		"豈": {4}, // just above
	}
	reverse := BuildPhonemeIDReverseMap(m, nil)

	if got := reverse[2]; got != "U+E000" {
		t.Errorf("id 2 = %q; want %q", got, "U+E000")
	}
	if got := reverse[3]; got != "U+F8FF" {
		t.Errorf("id 3 = %q; want %q", got, "U+F8FF")
	}
	// Outside the range the character passes through unchanged.
	if got := reverse[4]; got == "U+F900" {
		t.Errorf("id 4 = %q; U+F900 is outside the PUA and must pass through", got)
	}
	if got := reverse[1]; got == "U+D7FF" {
		t.Errorf("id 1 = %q; U+D7FF is outside the PUA and must pass through", got)
	}
}

func TestPhonemeIDsToTokens_MarksUnknownIDsDistinguishably(t *testing.T) {
	reverse := BuildPhonemeIDReverseMap(sampleIDMap(), nil)
	tokens := PhonemeIDsToTokens([]int64{5, 999, 42}, reverse)
	want := []string{"a", "<999>", "U+E019"}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("token %d = %q; want %q", i, tokens[i], want[i])
		}
	}
}

// ResolveTimingTokens tests. The alignment decision and its fallback used to
// live inline in cmd/piper-plus, where no test or CI step executed either
// branch (issue #656 review finding).

func TestResolveTimingTokens_UsesRealPhonemesWhenAligned(t *testing.T) {
	ids := []int64{5, 6, 50}
	tokens, resolved := ResolveTimingTokens(ids, len(ids), sampleIDMap(), nil)
	if !resolved {
		t.Error("aligned ids must take the reverse-map branch")
	}
	want := []string{"a", "b", "ch"}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("token %d = %q; want %q", i, tokens[i], want[i])
		}
	}
}

func TestResolveTimingTokens_AppliesPUANamesWhenAligned(t *testing.T) {
	pua := map[string]string{"": "N_m"}
	ids := []int64{42, 5}
	tokens, resolved := ResolveTimingTokens(ids, len(ids), sampleIDMap(), pua)
	if !resolved {
		t.Fatal("aligned ids must resolve")
	}
	if tokens[0] != "N_m" || tokens[1] != "a" {
		t.Errorf("tokens = %v; want [N_m a]", tokens)
	}
}

func TestResolveTimingTokens_FallsBackWhenCountsDiffer(t *testing.T) {
	// The pre-#656 bug shape: text-derived ids (5) against decoder durations
	// (15, after Strategy A padding). Emitting the 5 names across 15 slots
	// would silently mislabel every entry.
	ids := []int64{5, 6, 7, 50, 42}
	tokens, resolved := ResolveTimingTokens(ids, 15, sampleIDMap(), nil)
	if resolved {
		t.Error("mismatched counts must NOT claim resolution")
	}
	if len(tokens) != 15 {
		t.Fatalf("len(tokens) = %d; want 15 (one per duration)", len(tokens))
	}
	if tokens[0] != "ph_0" || tokens[14] != "ph_14" {
		t.Errorf("tokens[0]=%q tokens[14]=%q; want ph_0 / ph_14", tokens[0], tokens[14])
	}
	for i, tok := range tokens {
		if !strings.HasPrefix(tok, "ph_") {
			t.Errorf("token %d = %q; fallback leaked a reverse-mapped name", i, tok)
		}
	}
}

func TestResolveTimingTokens_FallsBackWhenIDsAbsent(t *testing.T) {
	tokens, resolved := ResolveTimingTokens(nil, 3, sampleIDMap(), nil)
	if resolved {
		t.Error("nil ids must not claim resolution")
	}
	want := []string{"ph_0", "ph_1", "ph_2"}
	for i := range want {
		if tokens[i] != want[i] {
			t.Errorf("token %d = %q; want %q", i, tokens[i], want[i])
		}
	}
}

func TestResolveTimingTokens_TreatsZeroDurationsAsUnresolved(t *testing.T) {
	// Empty ids trivially "match" a length of 0, so the guard must be
	// explicit: otherwise an empty-and-broken result would suppress the
	// caller's warning.
	tokens, resolved := ResolveTimingTokens([]int64{}, 0, sampleIDMap(), nil)
	if resolved {
		t.Error("zero durations must not claim resolution")
	}
	if len(tokens) != 0 {
		t.Errorf("len(tokens) = %d; want 0", len(tokens))
	}
}

func TestResolveTimingTokens_KeepsPaddedAlignment(t *testing.T) {
	// Strategy A pads the id list; engine.go now returns the PADDED ids so
	// they line up with the padded durations.
	ids := make([]int64, 15)
	for i := range ids {
		if i%2 == 0 {
			ids[i] = 5
		} else {
			ids[i] = 6
		}
	}
	tokens, resolved := ResolveTimingTokens(ids, len(ids), sampleIDMap(), nil)
	if !resolved {
		t.Fatal("padded ids matching padded durations must resolve")
	}
	if tokens[0] != "a" || tokens[1] != "b" {
		t.Errorf("tokens[:2] = %v; want [a b]", tokens[:2])
	}
}

func TestResolveTimingTokens_MarksUnknownIDsDistinctly(t *testing.T) {
	// An unknown id is a different failure from a count mismatch: alignment
	// holds, so only that slot is unknown. It must be "<id>", never "ph_N".
	ids := []int64{5, 9999}
	tokens, resolved := ResolveTimingTokens(ids, len(ids), sampleIDMap(), nil)
	if !resolved {
		t.Fatal("an unknown id does not break alignment")
	}
	if tokens[0] != "a" || tokens[1] != "<9999>" {
		t.Errorf("tokens = %v; want [a <9999>]", tokens)
	}
}

func TestBuiltinPUANames_CoversTheFixedTable(t *testing.T) {
	names := BuiltinPUANames()
	// Anti-vacuity: an empty or truncated table would silently reproduce the
	// "U+E0xx" output this function exists to prevent.
	if len(names) < 50 {
		t.Fatalf("builtin PUA table looks truncated: %d entries", len(names))
	}
	// Spot-check the families that regressed: N variant, long vowel,
	// geminate, palatalised consonant, question marker.
	for pua, want := range map[string]string{
		"": "N_m",
		"": "a:",
		"": "cl",
		"": "ky",
		"": "?!",
	} {
		if got := names[pua]; got != want {
			t.Errorf("names[%q] = %q; want %q", pua, got, want)
		}
	}
	if _, ok := names[""]; ok {
		t.Error("U+F8FF is not in the fixed table and must be absent")
	}
}

func TestResolveTimingTokens_UsesBuiltinPUANamesByDefault(t *testing.T) {
	// nil must NOT degrade to the "U+XXXX" fallback: that is the exact shape
	// of the cross-runtime divergence (79 of 173 ids on the in-tree model)
	// this default exists to prevent.
	m := map[string][]int64{"": {26}, "a": {5}}
	ids := []int64{26, 5}
	tokens, resolved := ResolveTimingTokens(ids, len(ids), m, nil)
	if !resolved {
		t.Fatal("aligned ids must resolve")
	}
	if tokens[0] != "N_m" || tokens[1] != "a" {
		t.Errorf("tokens = %v; want [N_m a]", tokens)
	}
}

func TestResolveTimingTokens_ExplicitEmptyMapKeepsCodepointFallback(t *testing.T) {
	// An explicitly empty map is how a caller opts OUT of the builtin names;
	// it must not be confused with nil.
	m := map[string][]int64{"": {26}}
	tokens, resolved := ResolveTimingTokens([]int64{26}, 1, m, map[string]string{})
	if !resolved {
		t.Fatal("aligned ids must resolve")
	}
	if tokens[0] != "U+E019" {
		t.Errorf("tokens[0] = %q; want U+E019", tokens[0])
	}
}
