package piperplus

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"strings"
)

// DefaultHopLength is the STFT hop length in samples.
const DefaultHopLength = 256

// PhonemeTimingInfo holds timing for a single phoneme.
type PhonemeTimingInfo struct {
	Phoneme    string  `json:"phoneme"`
	StartMs    float64 `json:"start_ms"`
	EndMs      float64 `json:"end_ms"`
	DurationMs float64 `json:"duration_ms"`
}

// TimingResult holds timing information for an entire utterance.
type TimingResult struct {
	Phonemes        []PhonemeTimingInfo `json:"phonemes"`
	TotalDurationMs float64             `json:"total_duration_ms"`
	SampleRate      int                 `json:"sample_rate"`
}

// DurationsToTiming converts per-phoneme duration frames from the ONNX model's
// duration output to timestamps. durations and phonemeTokens must have the same
// length. sampleRate and hopLength must both be positive.
func DurationsToTiming(durations []float32, phonemeTokens []string, sampleRate, hopLength int) (*TimingResult, error) {
	if len(durations) != len(phonemeTokens) {
		return nil, fmt.Errorf("length mismatch: durations has %d elements but phonemeTokens has %d", len(durations), len(phonemeTokens))
	}
	if sampleRate <= 0 {
		return nil, fmt.Errorf("sampleRate must be positive, got %d", sampleRate)
	}
	if hopLength <= 0 {
		return nil, fmt.Errorf("hopLength must be positive, got %d", hopLength)
	}

	msPerFrame := float64(hopLength) / float64(sampleRate) * 1000.0

	phonemes := make([]PhonemeTimingInfo, len(durations))
	var cumMs float64
	var totalDurationMs float64

	for i := range durations {
		if durations[i] < 0 {
			slog.Warn("negative phoneme duration clamped to 0",
				"index", i,
				"phoneme", phonemeTokens[i],
				"value", durations[i])
		}
		durationMs := math.Max(0, float64(durations[i])) * msPerFrame
		startMs := cumMs
		endMs := startMs + durationMs

		phonemes[i] = PhonemeTimingInfo{
			Phoneme:    phonemeTokens[i],
			StartMs:    startMs,
			EndMs:      endMs,
			DurationMs: durationMs,
		}

		cumMs = endMs
		totalDurationMs += durationMs
	}

	return &TimingResult{
		Phonemes:        phonemes,
		TotalDurationMs: totalDurationMs,
		SampleRate:      sampleRate,
	}, nil
}

// ToJSON returns the timing result as pretty-printed JSON.
func (r *TimingResult) ToJSON() ([]byte, error) {
	return json.MarshalIndent(r, "", "  ")
}

// ToJSONCompact returns the timing result as compact JSON.
func (r *TimingResult) ToJSONCompact() ([]byte, error) {
	return json.Marshal(r)
}

// ToTSV returns the timing result as tab-separated values with a header line.
func (r *TimingResult) ToTSV() string {
	var b strings.Builder
	b.WriteString("start_ms\tend_ms\tduration_ms\tphoneme\n")
	for _, p := range r.Phonemes {
		// Escape tab and newline characters in phoneme strings to preserve TSV format.
		escaped := strings.NewReplacer("\t", `\t`, "\n", `\n`).Replace(p.Phoneme)
		fmt.Fprintf(&b, "%.3f\t%.3f\t%.3f\t%s\n", p.StartMs, p.EndMs, p.DurationMs, escaped)
	}
	return b.String()
}
