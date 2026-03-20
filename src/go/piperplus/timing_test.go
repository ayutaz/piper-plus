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
