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

// ToSRT returns the timing result as SRT-style subtitle blocks.
//
// spec [output_formats.srt] (docs/spec/phoneme-timing-contract.toml). Each
// phoneme is emitted as one cue with a 1-based index, start --> end
// timestamps in HH:MM:SS,mmm form, and the phoneme as the cue text. Cues
// are separated by a blank line ("\n\n"). Cross-runtime parity with
// Rust (src/rust/piper-core/src/timing.rs:55-77) and Python
// (src/python_run/piper/timing.py:174-204).
func (r *TimingResult) ToSRT() string {
	var b strings.Builder
	for i, p := range r.Phonemes {
		idx := i + 1
		start := formatSRTTimestamp(p.StartMs)
		end := formatSRTTimestamp(p.EndMs)
		fmt.Fprintf(&b, "%d\n%s --> %s\n%s\n\n", idx, start, end, p.Phoneme)
	}
	return b.String()
}

// formatSRTTimestamp formats milliseconds as the SRT timestamp HH:MM:SS,mmm.
// The comma (,) before milliseconds is mandated by the SRT format spec
// (distinct from WebVTT which uses a period). Negative inputs are clamped
// to 0 to match the Rust/Python behaviour.
func formatSRTTimestamp(ms float64) string {
	if ms < 0 {
		ms = 0
	}
	totalMs := uint64(math.Round(ms))
	millis := totalMs % 1000
	totalSecs := totalMs / 1000
	secs := totalSecs % 60
	totalMins := totalSecs / 60
	mins := totalMins % 60
	hours := totalMins / 60
	return fmt.Sprintf("%02d:%02d:%02d,%03d", hours, mins, secs, millis)
}
