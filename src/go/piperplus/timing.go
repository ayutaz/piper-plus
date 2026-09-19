package piperplus

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"math"
	"sort"
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
// BuildPhonemeIDReverseMap builds a phoneme ID -> display name map from the
// model config's phoneme_id_map, per docs/spec/phoneme-timing-contract.toml
// [reverse_map]:
//
//   - first-wins: when several phoneme strings share an ID, the first one seen
//     is kept.
//   - PUA fallback: a Private Use Area character (U+E000..U+F8FF) with no
//     explicit name renders as "U+XXXX" (uppercase, 4 hex digits).
//   - explicit mapping: puaToMultiChar takes precedence when it has the key.
//
// The canonical implementation is src/python_run/piper_plus/timing.py
// (build_phoneme_id_reverse_map); the JS mirror is
// src/wasm/openjtalk-web/src/timing.js (buildPhonemeIdToTokenMap).
//
// Iteration order: Python dicts and JS objects preserve insertion order, so
// "first" is well defined there. Go map iteration is randomised, so keys are
// SORTED before iterating to make the result deterministic. Order cannot affect
// the outcome for maps without ID collisions, which is every shipped model (the
// in-tree fixture has 173 keys and zero collisions); a colliding map may pick a
// different winner than the canonical implementation.
func BuildPhonemeIDReverseMap(
	phonemeIDMap map[string][]int64,
	puaToMultiChar map[string]string,
) map[int64]string {
	reverse := make(map[int64]string, len(phonemeIDMap))

	keys := make([]string, 0, len(phonemeIDMap))
	for k := range phonemeIDMap {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	for _, key := range keys {
		display := key
		if name, ok := puaToMultiChar[key]; ok {
			display = name
		} else {
			runes := []rune(key)
			if len(runes) == 1 && isPrivateUseArea(runes[0]) {
				display = fmt.Sprintf("U+%04X", runes[0])
			}
		}

		for _, id := range phonemeIDMap[key] {
			if _, exists := reverse[id]; !exists {
				reverse[id] = display
			}
		}
	}

	return reverse
}

// ResolveTimingTokens picks the display names for a timing result.
//
// It returns the reverse-mapped phoneme names when phonemeIDs lines up with
// durationCount, and positional placeholders ("ph_0", "ph_1", ...) otherwise.
// The
// fallback is deliberate: a confidently WRONG phoneme name is more misleading
// than an obviously meaningless placeholder, and the two cannot be told apart
// from the output alone. The bool reports which branch was taken so callers can
// log it.
//
// Extracted from the CLI so the decision is testable: the alignment condition
// and its fallback previously lived inline in cmd/piper-plus and no test or CI
// step executed either branch (issue #656).
func ResolveTimingTokens(
	phonemeIDs []int64,
	durationCount int,
	phonemeIDMap map[string][]int64,
	puaToMultiChar map[string]string,
) (tokens []string, resolved bool) {
	if len(phonemeIDs) == durationCount && durationCount > 0 {
		reverse := BuildPhonemeIDReverseMap(phonemeIDMap, puaToMultiChar)
		return PhonemeIDsToTokens(phonemeIDs, reverse), true
	}

	tokens = make([]string, durationCount)
	for i := range tokens {
		tokens[i] = fmt.Sprintf("ph_%d", i)
	}
	return tokens, false
}

// isPrivateUseArea reports whether r is in the Unicode PUA (U+E000..U+F8FF).
func isPrivateUseArea(r rune) bool {
	return r >= 0xE000 && r <= 0xF8FF
}

// PhonemeIDsToTokens maps phoneme IDs to display names. An ID missing from the
// reverse map is rendered as "<id>" rather than a positional placeholder, so
// the unknown ID stays identifiable.
func PhonemeIDsToTokens(phonemeIDs []int64, reverseMap map[int64]string) []string {
	tokens := make([]string, len(phonemeIDs))
	for i, id := range phonemeIDs {
		if name, ok := reverseMap[id]; ok {
			tokens[i] = name
		} else {
			tokens[i] = fmt.Sprintf("<%d>", id)
		}
	}
	return tokens
}

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
// (src/python_run/piper_plus/timing.py:174-204).
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
// to 0 to match the Rust/Python behavior.
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
