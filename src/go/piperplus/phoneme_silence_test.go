package piperplus

import (
	"testing"
)

// ---------------------------------------------------------------------------
// ApplyPhonemeSilence
// ---------------------------------------------------------------------------

func TestApplyPhonemeSilence_Basic(t *testing.T) {
	// 3 phonemes: "a" (dur=2 frames), "b" (dur=3 frames), "c" (dur=2 frames).
	// hopSize=4, so segments are 8, 12, 8 samples = 28 total.
	// Insert 0.5s silence after "b" at sampleRate=10 -> 5 extra samples.
	audio := make([]float32, 28)
	for i := range audio {
		audio[i] = float32(i + 1) // 1..28
	}

	durations := []float32{2, 3, 2}
	phonemeIDs := []int64{10, 20, 30}
	silenceMap := map[string]float64{"b": 0.5}
	idToPhoneme := map[int64]string{10: "a", 20: "b", 30: "c"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// Expected: 28 original + 5 silence = 33 samples.
	if len(result) != 33 {
		t.Fatalf("expected 33 samples, got %d", len(result))
	}

	// First 8 samples (phoneme "a"): 1..8.
	for i := 0; i < 8; i++ {
		if result[i] != float32(i+1) {
			t.Errorf("result[%d]: expected %f, got %f", i, float32(i+1), result[i])
		}
	}

	// Next 12 samples (phoneme "b"): 9..20.
	for i := 8; i < 20; i++ {
		if result[i] != float32(i+1) {
			t.Errorf("result[%d]: expected %f, got %f", i, float32(i+1), result[i])
		}
	}

	// 5 silence samples after "b": all zeros.
	for i := 20; i < 25; i++ {
		if result[i] != 0 {
			t.Errorf("result[%d]: expected 0 (silence), got %f", i, result[i])
		}
	}

	// Last 8 samples (phoneme "c"): 21..28.
	for i := 25; i < 33; i++ {
		expected := float32(i - 25 + 21)
		if result[i] != expected {
			t.Errorf("result[%d]: expected %f, got %f", i, expected, result[i])
		}
	}
}

func TestApplyPhonemeSilence_MultiplePhonemes(t *testing.T) {
	// Insert silence after two different phonemes.
	audio := make([]float32, 12) // 3 phonemes, dur=1 frame each, hopSize=4
	for i := range audio {
		audio[i] = float32(i + 1)
	}

	durations := []float32{1, 1, 1}
	phonemeIDs := []int64{10, 20, 30}
	silenceMap := map[string]float64{"a": 0.2, "c": 0.3} // 2 + 3 = 5 extra
	idToPhoneme := map[int64]string{10: "a", 20: "b", 30: "c"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// Expected: 12 + 2 (after "a") + 3 (after "c") = 17.
	if len(result) != 17 {
		t.Fatalf("expected 17 samples, got %d", len(result))
	}

	// Phoneme "a": samples 1..4.
	for i := 0; i < 4; i++ {
		if result[i] != float32(i+1) {
			t.Errorf("result[%d]: expected %f, got %f", i, float32(i+1), result[i])
		}
	}

	// 2 silence samples after "a".
	for i := 4; i < 6; i++ {
		if result[i] != 0 {
			t.Errorf("result[%d]: expected 0 (silence after a), got %f", i, result[i])
		}
	}

	// Phoneme "b": samples 5..8.
	for i := 6; i < 10; i++ {
		expected := float32(i - 6 + 5)
		if result[i] != expected {
			t.Errorf("result[%d]: expected %f, got %f", i, expected, result[i])
		}
	}

	// Phoneme "c": samples 9..12.
	for i := 10; i < 14; i++ {
		expected := float32(i - 10 + 9)
		if result[i] != expected {
			t.Errorf("result[%d]: expected %f, got %f", i, expected, result[i])
		}
	}

	// 3 silence samples after "c".
	for i := 14; i < 17; i++ {
		if result[i] != 0 {
			t.Errorf("result[%d]: expected 0 (silence after c), got %f", i, result[i])
		}
	}
}

func TestApplyPhonemeSilence_NilSilenceMap(t *testing.T) {
	audio := []float32{1, 2, 3}
	durations := []float32{1}
	phonemeIDs := []int64{10}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, nil, 22050, 256, nil)

	if len(result) != len(audio) {
		t.Fatalf("expected %d samples, got %d", len(audio), len(result))
	}
	// Should return the exact same slice.
	if &result[0] != &audio[0] {
		t.Error("expected same slice returned when silenceMap is nil")
	}
}

func TestApplyPhonemeSilence_EmptySilenceMap(t *testing.T) {
	audio := []float32{1, 2, 3}
	durations := []float32{1}
	phonemeIDs := []int64{10}
	idToPhoneme := map[int64]string{10: "a"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, map[string]float64{}, 22050, 256, idToPhoneme)

	if len(result) != len(audio) {
		t.Fatalf("expected %d samples, got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_NilDurations(t *testing.T) {
	audio := []float32{1, 2, 3}
	silenceMap := map[string]float64{"a": 0.1}

	result := ApplyPhonemeSilence(audio, nil, []int64{10}, silenceMap, 22050, 256, nil)

	if len(result) != len(audio) {
		t.Fatalf("expected %d samples, got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_LengthMismatch(t *testing.T) {
	audio := []float32{1, 2, 3}
	durations := []float32{1, 2}      // 2 elements
	phonemeIDs := []int64{10, 20, 30} // 3 elements
	silenceMap := map[string]float64{"a": 0.1}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 22050, 256, nil)

	// Should return original when lengths mismatch.
	if len(result) != len(audio) {
		t.Fatalf("expected %d samples, got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_ZeroSampleRate(t *testing.T) {
	audio := []float32{1, 2, 3}
	durations := []float32{1}
	phonemeIDs := []int64{10}
	silenceMap := map[string]float64{"a": 0.1}
	idToPhoneme := map[int64]string{10: "a"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 0, 256, idToPhoneme)

	if len(result) != len(audio) {
		t.Fatalf("expected %d samples (invalid sampleRate), got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_ZeroHopSize(t *testing.T) {
	audio := []float32{1, 2, 3}
	durations := []float32{1}
	phonemeIDs := []int64{10}
	silenceMap := map[string]float64{"a": 0.1}
	idToPhoneme := map[int64]string{10: "a"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 22050, 0, idToPhoneme)

	if len(result) != len(audio) {
		t.Fatalf("expected %d samples (invalid hopSize), got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_NegativeSilenceDuration(t *testing.T) {
	// Negative silence values should be ignored.
	audio := make([]float32, 8) // 2 phonemes, dur=1 each, hopSize=4
	for i := range audio {
		audio[i] = float32(i + 1)
	}

	durations := []float32{1, 1}
	phonemeIDs := []int64{10, 20}
	silenceMap := map[string]float64{"a": -0.5, "b": 0.0}
	idToPhoneme := map[int64]string{10: "a", 20: "b"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// No silence should be inserted for negative or zero values.
	if len(result) != len(audio) {
		t.Fatalf("expected %d samples (negative/zero silence ignored), got %d", len(audio), len(result))
	}
}

func TestApplyPhonemeSilence_UnknownPhonemeID(t *testing.T) {
	// Phoneme ID not in idToPhoneme map should be silently skipped.
	audio := make([]float32, 8) // 2 phonemes, dur=1 each, hopSize=4
	for i := range audio {
		audio[i] = float32(i + 1)
	}

	durations := []float32{1, 1}
	phonemeIDs := []int64{10, 99} // 99 not in map
	silenceMap := map[string]float64{"a": 0.5}
	idToPhoneme := map[int64]string{10: "a"} // no entry for 99

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// 8 original + 5 (after "a") = 13.
	if len(result) != 13 {
		t.Fatalf("expected 13 samples, got %d", len(result))
	}
}

func TestApplyPhonemeSilence_EmptyAudio(t *testing.T) {
	durations := []float32{0, 0}
	phonemeIDs := []int64{10, 20}
	silenceMap := map[string]float64{"a": 0.5}
	idToPhoneme := map[int64]string{10: "a", 20: "b"}

	result := ApplyPhonemeSilence([]float32{}, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// Even with empty audio, silence should be inserted after "a".
	// dur=0 for both, so no original audio copied, but 5 silence samples after "a".
	if len(result) != 5 {
		t.Fatalf("expected 5 samples (silence only), got %d", len(result))
	}
	for i := 0; i < 5; i++ {
		if result[i] != 0 {
			t.Errorf("result[%d]: expected 0 (silence), got %f", i, result[i])
		}
	}
}

func TestApplyPhonemeSilence_AudioShorterThanDurations(t *testing.T) {
	// Audio is shorter than what durations imply (edge case).
	audio := []float32{1, 2, 3}  // only 3 samples
	durations := []float32{2, 2} // implies 2*4 + 2*4 = 16 samples
	phonemeIDs := []int64{10, 20}
	silenceMap := map[string]float64{"b": 0.2} // 2 silence samples at sr=10
	idToPhoneme := map[int64]string{10: "a", 20: "b"}

	result := ApplyPhonemeSilence(audio, durations, phonemeIDs, silenceMap, 10, 4, idToPhoneme)

	// Should handle gracefully: copy what audio exists + silence.
	// Phoneme "a" segment: min(8, 3) = 3 samples [1,2,3].
	// Phoneme "b" segment: audioPos=8 > len(audio)=3, so nothing copied.
	// Silence after "b": 2 samples.
	if len(result) != 5 {
		t.Fatalf("expected 5 samples, got %d", len(result))
	}
	if result[0] != 1 || result[1] != 2 || result[2] != 3 {
		t.Errorf("first 3 samples: expected [1,2,3], got [%f,%f,%f]", result[0], result[1], result[2])
	}
	if result[3] != 0 || result[4] != 0 {
		t.Errorf("silence: expected [0,0], got [%f,%f]", result[3], result[4])
	}
}

// ---------------------------------------------------------------------------
// BuildIDToPhonemeMap
// ---------------------------------------------------------------------------

func TestBuildIDToPhonemeMap_Basic(t *testing.T) {
	phonemeIDMap := map[string][]int64{
		"a": {10, 11},
		"b": {20},
		"c": {30},
	}

	m := BuildIDToPhonemeMap(phonemeIDMap)

	if len(m) != 4 {
		t.Fatalf("expected 4 entries, got %d", len(m))
	}

	tests := map[int64]string{
		10: "a",
		11: "a",
		20: "b",
		30: "c",
	}
	for id, want := range tests {
		got, ok := m[id]
		if !ok {
			t.Errorf("ID %d not found in map", id)
			continue
		}
		if got != want {
			t.Errorf("ID %d: expected %q, got %q", id, want, got)
		}
	}
}

func TestBuildIDToPhonemeMap_Empty(t *testing.T) {
	m := BuildIDToPhonemeMap(map[string][]int64{})
	if len(m) != 0 {
		t.Errorf("expected empty map, got %d entries", len(m))
	}
}

func TestBuildIDToPhonemeMap_Nil(t *testing.T) {
	m := BuildIDToPhonemeMap(nil)
	if len(m) != 0 {
		t.Errorf("expected empty map, got %d entries", len(m))
	}
}

// ---------------------------------------------------------------------------
// WithPhonemeSilence option
// ---------------------------------------------------------------------------

func TestWithPhonemeSilence_Option(t *testing.T) {
	m := map[string]float64{"_": 0.1, ".": 0.3}
	opts := applySynthesisOptions([]SynthesisOption{WithPhonemeSilence(m)})

	if opts.PhonemeSilence == nil {
		t.Fatal("expected non-nil PhonemeSilence")
	}
	if len(opts.PhonemeSilence) != 2 {
		t.Fatalf("expected 2 entries, got %d", len(opts.PhonemeSilence))
	}
	if opts.PhonemeSilence["_"] != 0.1 {
		t.Errorf("expected _=0.1, got %f", opts.PhonemeSilence["_"])
	}
	if opts.PhonemeSilence["."] != 0.3 {
		t.Errorf("expected .=0.3, got %f", opts.PhonemeSilence["."])
	}
}

func TestWithPhonemeSilenceLoad_Option(t *testing.T) {
	m := map[string]float64{"_": 0.2}
	lo := &LoadOptions{}
	WithPhonemeSilenceLoad(m)(lo)

	if lo.PhonemeSilence == nil {
		t.Fatal("expected non-nil PhonemeSilence in LoadOptions")
	}
	if lo.PhonemeSilence["_"] != 0.2 {
		t.Errorf("expected _=0.2, got %f", lo.PhonemeSilence["_"])
	}
}

func TestNewSynthesisRequest_PhonemeSilence(t *testing.T) {
	m := map[string]float64{"_": 0.15}
	req := NewSynthesisRequest([]int64{1, 2, 3}, WithPhonemeSilence(m))

	if req.PhonemeSilence == nil {
		t.Fatal("expected non-nil PhonemeSilence in SynthesisRequest")
	}
	if req.PhonemeSilence["_"] != 0.15 {
		t.Errorf("expected _=0.15, got %f", req.PhonemeSilence["_"])
	}
}
