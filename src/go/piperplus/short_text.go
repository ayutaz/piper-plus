package piperplus

import (
	"fmt"
	"math"
	"strings"
	"unicode"
)

// Short-text synthesis quality mitigation constants.
// Keep in sync with docs/spec/short-text-contract.toml.
const (
	// minPhonemeIDs is the minimum number of phoneme IDs required for stable
	// VITS inference. Shorter sequences are padded with silence (pause ID = 0).
	//
	// Issue #356: Was 40, but empirical measurements on the tsukuyomi 6lang
	// model show synthesis is stable down to ~8 IDs. 40 caused Strategy A to
	// fire on already-stable inputs and leak padding artifacts. 15 keeps
	// Strategy A active for genuinely tiny inputs only.
	minPhonemeIDs = 15

	// minBodyForStrategyA is the minimum body length (= phoneme IDs minus
	// BOS / EOS) for Strategy A to apply. Below this threshold, padding
	// would dominate over actual content; raw VITS output is preferable.
	minBodyForStrategyA = 3

	// shortTextChars is the character-count threshold (excluding whitespace)
	// below which Strategy C (silence break auto-injection) is applied.
	shortTextChars = 10

	// silencePadMs is the duration of silence (in milliseconds) prepended and
	// appended to short text by Strategy C.
	silencePadMs = 300

	// trimThresholdRMS is the RMS amplitude threshold used to detect silence
	// when trimming padded audio (Strategy A post-trim).
	trimThresholdRMS = 0.01

	// trimMinSamples is the minimum number of audio samples to preserve
	// after trimming (22050 Hz * 0.1s = 2205).
	trimMinSamples = 2205

	// trimWindowSize is the number of samples per RMS analysis window
	// used in silence trimming.
	trimWindowSize = 256

	// trimEosMaxFrames bounds how many EOS frames the durations-based trim
	// keeps after Strategy A padding. VITS predicts an inflated EOS under
	// the padded context that produces an audible artifact otherwise
	// (issue #356). Default 0 = drop the entire EOS region.
	trimEosMaxFrames = 0
)

// padPhonemeIDs inserts pause IDs (0) into phonemeIDs to reach minPhonemeIDs.
// Pause IDs are inserted evenly after BOS (index 0) and before EOS (last index).
// Returns the padded slice, true if padding was applied, and the front/back
// padding counts. Strategy A is skipped (returns the original slice and zero
// counts) when the body (= phoneme IDs minus BOS / EOS) is shorter than
// minBodyForStrategyA — see issue #356.
func padPhonemeIDs(ids []int64) ([]int64, bool, int, int) {
	bodyLen := len(ids) - 2 // exclude BOS / EOS
	if bodyLen < minBodyForStrategyA {
		return ids, false, 0, 0
	}
	if len(ids) >= minPhonemeIDs {
		return ids, false, 0, 0
	}

	needed := minPhonemeIDs - len(ids)
	// Split padding: half after BOS, half before EOS.
	frontPad := needed / 2
	backPad := needed - frontPad

	padded := make([]int64, 0, minPhonemeIDs)

	// BOS (first element).
	padded = append(padded, ids[0])

	// Front padding (pause ID = 0).
	for i := 0; i < frontPad; i++ {
		padded = append(padded, 0)
	}

	// Middle content (everything between BOS and EOS).
	if len(ids) > 2 {
		padded = append(padded, ids[1:len(ids)-1]...)
	}

	// Back padding (pause ID = 0).
	for i := 0; i < backPad; i++ {
		padded = append(padded, 0)
	}

	// EOS (last element).
	padded = append(padded, ids[len(ids)-1])

	return padded, true, frontPad, backPad
}

// trimPaddingByDurations performs the Strategy A precise post-trim using the
// model's duration output. Mirrors src/python_run/piper/voice.py
// _trim_padding_by_durations so all runtimes produce byte-equal output for
// the same inputs (issue #356, cross-runtime contract).
//
// The padded sequence layout is:
//
//	[BOS, pad×frontPad, ...body..., pad×backPad, EOS]
//
// durations[i] is the frame count VITS assigned to phoneme i. Multiplying the
// pad-token totals by hopSize gives the exact sample count to drop.
//
// Trimming policy:
//   - BOS + front padding: stripped completely
//   - Back padding: stripped completely
//   - EOS: keep only eosMaxFrames frames (default trimEosMaxFrames = 0)
//
// All frame→sample conversions use truncation (int) — required for
// byte-equality with the Python reference implementation.
//
// Returns audio unchanged when inputs are inconsistent (nil durations, zero
// hop, durations shorter than 1+frontPad+backPad+1, etc.).
func trimPaddingByDurations(audio []int16, durations []float32, frontPad, backPad, hopSize, eosMaxFrames int) []int16 {
	if frontPad <= 0 && backPad <= 0 {
		return audio
	}
	if durations == nil || hopSize <= 0 {
		return audio
	}
	expectedLen := 1 + frontPad + backPad + 1 // BOS + pads + EOS
	if len(durations) < expectedLen {
		return audio
	}

	// Front: BOS + front padding samples. Truncation matches int() in Python.
	var frontSum float32
	for i := 0; i < 1+frontPad; i++ {
		frontSum += durations[i]
	}
	frontSamples := int(frontSum * float32(hopSize))

	// Back: back padding samples + EOS excess (over eosMaxFrames).
	var backPadSum float32
	if backPad > 0 {
		// durations[-(1+backPad) : -1] in Python = durations[len-1-backPad : len-1]
		start := len(durations) - 1 - backPad
		for i := start; i < len(durations)-1; i++ {
			backPadSum += durations[i]
		}
	}
	backPadSamples := int(backPadSum * float32(hopSize))

	eosFrames := durations[len(durations)-1]
	eosExcess := eosFrames - float32(eosMaxFrames)
	if eosExcess < 0 {
		eosExcess = 0
	}
	backSamples := backPadSamples + int(eosExcess*float32(hopSize))

	if frontSamples < 0 {
		frontSamples = 0
	}
	end := len(audio) - backSamples
	if end < frontSamples {
		end = frontSamples
	}
	if frontSamples >= len(audio) || end <= 0 || frontSamples >= end {
		return audio
	}
	return audio[frontSamples:end]
}

// padProsodyFeatures extends prosody features to match the new padded phoneme
// length. Inserted positions are zero-filled.
func padProsodyFeatures(original [][3]int64, originalLen, paddedLen int) [][3]int64 {
	if len(original) == 0 {
		return nil
	}
	if paddedLen <= originalLen {
		return original
	}

	needed := paddedLen - originalLen
	frontPad := needed / 2
	backPad := needed - frontPad

	padded := make([][3]int64, 0, paddedLen)

	// BOS prosody.
	if len(original) > 0 {
		padded = append(padded, original[0])
	}

	// Front padding (zero prosody).
	for i := 0; i < frontPad; i++ {
		padded = append(padded, [3]int64{})
	}

	// Middle content prosody.
	if len(original) > 2 {
		end := len(original) - 1
		if end > originalLen-1 {
			end = originalLen - 1
		}
		padded = append(padded, original[1:end]...)
	}

	// Back padding (zero prosody).
	for i := 0; i < backPad; i++ {
		padded = append(padded, [3]int64{})
	}

	// EOS prosody. When len(original) == 1 the single element already served
	// as BOS, and the front+back padding fills the remaining paddedLen-1 slots,
	// so no extra EOS element is appended.
	if len(original) > 1 {
		padded = append(padded, original[len(original)-1])
	}

	return padded
}

// trimSilence removes leading and trailing silence from int16 audio samples
// using a sliding RMS window. At least trimMinSamples are always preserved.
func trimSilence(audio []int16) []int16 {
	if len(audio) <= trimMinSamples {
		return audio
	}

	// Find the first non-silent window from the front.
	start := 0
	for start+trimWindowSize <= len(audio) {
		if windowRMS(audio[start:start+trimWindowSize]) > trimThresholdRMS {
			break
		}
		start += trimWindowSize
	}

	// Find the last non-silent window from the end.
	end := len(audio)
	for end-trimWindowSize >= 0 {
		if windowRMS(audio[end-trimWindowSize:end]) > trimThresholdRMS {
			break
		}
		end -= trimWindowSize
	}

	// Ensure minimum sample count.
	if end <= start {
		// All silence -- return center portion.
		center := len(audio) / 2
		start = center - trimMinSamples/2
		end = center + trimMinSamples/2
		if start < 0 {
			start = 0
		}
		if end > len(audio) {
			end = len(audio)
		}
	}

	if end-start < trimMinSamples {
		// Expand around the detected region to meet minimum.
		deficit := trimMinSamples - (end - start)
		expandFront := deficit / 2
		expandBack := deficit - expandFront
		start -= expandFront
		end += expandBack
		if start < 0 {
			end -= start // shift end by the overshoot
			start = 0
		}
		if end > len(audio) {
			start -= end - len(audio) // shift start by the overshoot
			end = len(audio)
		}
		if start < 0 {
			start = 0
		}
	}

	return audio[start:end]
}

// windowRMS computes the root-mean-square of a window of int16 samples,
// normalized to [0, 1] range.
func windowRMS(samples []int16) float64 {
	if len(samples) == 0 {
		return 0
	}
	var sum float64
	for _, s := range samples {
		v := float64(s) / math.MaxInt16
		sum += v * v
	}
	return math.Sqrt(sum / float64(len(samples)))
}

// adjustScalesForShortText applies Strategy B: dynamic noise/noiseW reduction
// for short phoneme sequences. Returns possibly modified noiseScale and noiseW.
func adjustScalesForShortText(phonemeLen int, noiseScale, noiseW float32) (float32, float32) {
	if phonemeLen >= minPhonemeIDs {
		return noiseScale, noiseW
	}

	ratio := float64(phonemeLen) / float64(minPhonemeIDs)
	if ratio < 0 {
		ratio = 0
	}
	if ratio > 1 {
		ratio = 1
	}

	// noiseScale *= max(0.5, ratio)
	nsFactor := math.Max(0.5, ratio)
	noiseScale *= float32(nsFactor)

	// noiseW *= max(0.4, ratio)
	nwFactor := math.Max(0.4, ratio)
	noiseW *= float32(nwFactor)

	return noiseScale, noiseW
}

// countNonSpaceChars counts characters in text excluding whitespace.
func countNonSpaceChars(text string) int {
	count := 0
	for _, r := range text {
		if !unicode.IsSpace(r) {
			count++
		}
	}
	return count
}

// wrapShortTextWithBreaks applies Strategy C: if the text is not already SSML
// (does not start with "<speak>") and has shortTextChars or fewer non-space
// characters, wraps it with <break> silence padding for SSML processing.
// Since the Go runtime does not have an SSML parser, this function instead
// returns the original text and a flag indicating that silence padding should
// be applied at the audio level.
func wrapShortTextWithBreaks(text string) (string, bool) {
	trimmed := strings.TrimSpace(text)
	if trimmed == "" {
		return text, false
	}

	// If already SSML, do not wrap.
	if strings.HasPrefix(trimmed, "<speak>") || strings.HasPrefix(trimmed, "<speak ") {
		return text, false
	}

	// Check non-space character count.
	if countNonSpaceChars(trimmed) > shortTextChars {
		return text, false
	}

	return text, true
}

// prependSilence adds silence samples at the beginning of audio.
func prependSilence(audio []int16, sampleRate int, durationMs int) []int16 {
	silenceSamples := sampleRate * durationMs / 1000
	result := make([]int16, silenceSamples+len(audio))
	copy(result[silenceSamples:], audio)
	return result
}

// appendSilence adds silence samples at the end of audio.
func appendSilence(audio []int16, sampleRate int, durationMs int) []int16 {
	silenceSamples := sampleRate * durationMs / 1000
	result := make([]int16, len(audio)+silenceSamples)
	copy(result, audio)
	return result
}

// applyShortTextMitigation is a convenience function that logs the mitigation
// details. It is called from engine.Synthesize when short-text strategies are
// active.
func shortTextMitigationSummary(originalLen, paddedLen int, wasPadded bool, scalesAdjusted bool) string {
	parts := make([]string, 0, 3)
	if wasPadded {
		parts = append(parts, fmt.Sprintf("padded %d->%d phonemes", originalLen, paddedLen))
	}
	if scalesAdjusted {
		parts = append(parts, "scales adjusted")
	}
	if len(parts) == 0 {
		return ""
	}
	return "short-text mitigation: " + strings.Join(parts, ", ")
}
