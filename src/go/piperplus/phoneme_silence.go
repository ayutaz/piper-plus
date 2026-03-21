package piperplus

// ApplyPhonemeSilence inserts silence samples after specified phonemes.
//
// For each phoneme in phonemeIDs, the function uses idToPhoneme to look up the
// phoneme string. If that string appears in silenceMap, the corresponding
// number of seconds of silence (zero-valued float32 samples) is appended after
// that phoneme's audio segment.
//
// The audio is segmented using durations (per-phoneme frame counts from the
// ONNX model) and hopSize (STFT hop length in samples). Each phoneme occupies
// int(durations[i]) * hopSize samples in audio.
//
// Parameters:
//   - audio: float32 PCM samples from ONNX inference (before peak normalization).
//   - durations: per-phoneme duration in frames (from model output).
//   - phonemeIDs: the phoneme ID sequence used for inference.
//   - silenceMap: phoneme string -> seconds of silence to insert after it.
//   - sampleRate: audio sample rate (e.g., 22050).
//   - hopSize: STFT hop length in samples (e.g., 256).
//   - idToPhoneme: mapping from phoneme ID to phoneme string.
//
// Returns a new audio slice with silence inserted. If silenceMap is nil/empty,
// durations is nil, or lengths do not match, the original audio is returned
// unchanged.
func ApplyPhonemeSilence(
	audio []float32,
	durations []float32,
	phonemeIDs []int64,
	silenceMap map[string]float64,
	sampleRate int,
	hopSize int,
	idToPhoneme map[int64]string,
) []float32 {
	// Fast path: nothing to do.
	if len(silenceMap) == 0 || len(durations) == 0 || len(phonemeIDs) == 0 {
		return audio
	}
	if len(durations) != len(phonemeIDs) {
		return audio
	}
	if sampleRate <= 0 || hopSize <= 0 {
		return audio
	}

	// Calculate total extra silence samples needed so we can pre-allocate.
	totalExtra := 0
	for i, pid := range phonemeIDs {
		phoneme, ok := idToPhoneme[pid]
		if !ok {
			continue
		}
		seconds, ok := silenceMap[phoneme]
		if !ok || seconds <= 0 {
			continue
		}
		_ = durations[i] // bounds check
		silenceSamples := int(seconds * float64(sampleRate))
		if silenceSamples > 0 {
			totalExtra += silenceSamples
		}
	}

	if totalExtra == 0 {
		return audio
	}

	// Build new audio with silence inserted.
	result := make([]float32, 0, len(audio)+totalExtra)
	audioPos := 0

	for i, pid := range phonemeIDs {
		// Number of audio samples this phoneme occupies.
		frameDur := int(durations[i])
		if frameDur < 0 {
			frameDur = 0
		}
		segmentSamples := frameDur * hopSize

		// Copy this phoneme's audio segment.
		end := audioPos + segmentSamples
		if end > len(audio) {
			end = len(audio)
		}
		if audioPos < len(audio) {
			result = append(result, audio[audioPos:end]...)
		}
		audioPos = end

		// Insert silence after this phoneme if configured.
		phoneme, ok := idToPhoneme[pid]
		if !ok {
			continue
		}
		seconds, ok := silenceMap[phoneme]
		if !ok || seconds <= 0 {
			continue
		}
		silenceSamples := int(seconds * float64(sampleRate))
		if silenceSamples > 0 {
			result = append(result, make([]float32, silenceSamples)...)
		}
	}

	// Append any remaining audio beyond the last phoneme's segment.
	if audioPos < len(audio) {
		result = append(result, audio[audioPos:]...)
	}

	return result
}

// BuildIDToPhonemeMap inverts a PhonemeIDMap (phoneme_string -> []int64) to
// produce a map from each phoneme ID back to its phoneme string. When multiple
// IDs map to the same phoneme, all are included. This is used by
// ApplyPhonemeSilence to resolve phoneme IDs back to strings.
func BuildIDToPhonemeMap(phonemeIDMap map[string][]int64) map[int64]string {
	m := make(map[int64]string, len(phonemeIDMap)*2)
	for phoneme, ids := range phonemeIDMap {
		for _, id := range ids {
			m[id] = phoneme
		}
	}
	return m
}
