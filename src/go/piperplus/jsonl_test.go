package piperplus

import (
	"context"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// ParseJSONLLine
// ---------------------------------------------------------------------------

func TestParseJSONLLine_PhonemeIDs(t *testing.T) {
	line := []byte(`{"phoneme_ids": [1, 10, 57, 14, 2], "speaker_id": 0}`)
	input, err := ParseJSONLLine(line)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	wantIDs := []int64{1, 10, 57, 14, 2}
	if len(input.PhonemeIDs) != len(wantIDs) {
		t.Fatalf("phoneme_ids length: expected %d, got %d", len(wantIDs), len(input.PhonemeIDs))
	}
	for i, id := range wantIDs {
		if input.PhonemeIDs[i] != id {
			t.Errorf("phoneme_ids[%d]: expected %d, got %d", i, id, input.PhonemeIDs[i])
		}
	}

	if input.SpeakerID == nil {
		t.Fatal("speaker_id should not be nil")
	}
	if *input.SpeakerID != 0 {
		t.Errorf("speaker_id: expected 0, got %d", *input.SpeakerID)
	}

	if input.Text != "" {
		t.Errorf("text: expected empty, got %q", input.Text)
	}
}

func TestParseJSONLLine_Text(t *testing.T) {
	line := []byte(`{"text": "hello", "language": "en"}`)
	input, err := ParseJSONLLine(line)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if input.Text != "hello" {
		t.Errorf("text: expected %q, got %q", "hello", input.Text)
	}
	if input.Language != "en" {
		t.Errorf("language: expected %q, got %q", "en", input.Language)
	}
	if len(input.PhonemeIDs) != 0 {
		t.Errorf("phoneme_ids: expected empty, got %v", input.PhonemeIDs)
	}
}

func TestParseJSONLLine_InvalidJSON(t *testing.T) {
	line := []byte(`{bad json`)
	_, err := ParseJSONLLine(line)
	if err == nil {
		t.Fatal("expected error for invalid JSON")
	}
}

func TestParseJSONLLine_EmptyInput(t *testing.T) {
	line := []byte(`{"speaker_id": 1}`)
	_, err := ParseJSONLLine(line)
	if err == nil {
		t.Fatal("expected error when neither phoneme_ids nor text is set")
	}
}

func TestParseJSONLLine_WithProsody(t *testing.T) {
	line := []byte(`{"phoneme_ids": [1, 2, 3], "prosody_features": [[-2, 1, 5], [0, 0, 3], [1, 2, 4]]}`)
	input, err := ParseJSONLLine(line)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(input.ProsodyFeatures) != 3 {
		t.Fatalf("prosody_features length: expected 3, got %d", len(input.ProsodyFeatures))
	}

	want := [3]int64{-2, 1, 5}
	if input.ProsodyFeatures[0] != want {
		t.Errorf("prosody_features[0]: expected %v, got %v", want, input.ProsodyFeatures[0])
	}
}

// ---------------------------------------------------------------------------
// ReadJSONL
// ---------------------------------------------------------------------------

func TestReadJSONL(t *testing.T) {
	data := strings.Join([]string{
		`{"phoneme_ids": [1, 2, 3]}`,
		``,
		`// this is a comment`,
		`{"text": "hello", "language": "en"}`,
		`{"phoneme_ids": [4, 5], "speaker_id": 2}`,
	}, "\n")

	ctx := context.Background()
	inputCh, errCh := ReadJSONL(ctx, strings.NewReader(data))

	var inputs []*JSONLInput
	for inp := range inputCh {
		inputs = append(inputs, inp)
	}

	// Drain error channel.
	for err := range errCh {
		t.Fatalf("unexpected error: %v", err)
	}

	if len(inputs) != 3 {
		t.Fatalf("expected 3 inputs, got %d", len(inputs))
	}

	// First: phoneme_ids [1, 2, 3].
	if len(inputs[0].PhonemeIDs) != 3 || inputs[0].PhonemeIDs[0] != 1 {
		t.Errorf("input[0]: unexpected phoneme_ids %v", inputs[0].PhonemeIDs)
	}

	// Second: text "hello".
	if inputs[1].Text != "hello" {
		t.Errorf("input[1]: expected text %q, got %q", "hello", inputs[1].Text)
	}

	// Third: phoneme_ids [4, 5] with speaker_id 2.
	if len(inputs[2].PhonemeIDs) != 2 || inputs[2].PhonemeIDs[0] != 4 {
		t.Errorf("input[2]: unexpected phoneme_ids %v", inputs[2].PhonemeIDs)
	}
	if inputs[2].SpeakerID == nil || *inputs[2].SpeakerID != 2 {
		t.Errorf("input[2]: expected speaker_id 2, got %v", inputs[2].SpeakerID)
	}
}

// ---------------------------------------------------------------------------
// ToSynthesisRequest
// ---------------------------------------------------------------------------

func TestJSONLInput_ToSynthesisRequest(t *testing.T) {
	defaults := SynthesisOptions{
		SpeakerID:   5,
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}

	t.Run("phoneme_ids with overrides", func(t *testing.T) {
		sid := int64(3)
		lid := int64(1)
		input := &JSONLInput{
			PhonemeIDs: []int64{1, 2, 3},
			SpeakerID:  &sid,
			LanguageID: &lid,
		}

		req := input.ToSynthesisRequest(defaults)
		if req == nil {
			t.Fatal("expected non-nil request")
		}
		if req.SpeakerID != 3 {
			t.Errorf("SpeakerID: expected 3, got %d", req.SpeakerID)
		}
		if req.LanguageID != 1 {
			t.Errorf("LanguageID: expected 1, got %d", req.LanguageID)
		}
		if req.NoiseScale != 0.667 {
			t.Errorf("NoiseScale: expected 0.667, got %f", req.NoiseScale)
		}
	})

	t.Run("phoneme_ids with defaults", func(t *testing.T) {
		input := &JSONLInput{
			PhonemeIDs: []int64{10, 20},
		}

		req := input.ToSynthesisRequest(defaults)
		if req == nil {
			t.Fatal("expected non-nil request")
		}
		if req.SpeakerID != 5 {
			t.Errorf("SpeakerID: expected default 5, got %d", req.SpeakerID)
		}
		if req.LanguageID != 0 {
			t.Errorf("LanguageID: expected default 0, got %d", req.LanguageID)
		}
	})

	t.Run("text mode returns nil", func(t *testing.T) {
		input := &JSONLInput{
			Text:     "hello",
			Language: "en",
		}

		req := input.ToSynthesisRequest(defaults)
		if req != nil {
			t.Error("expected nil for text-mode input")
		}
	})
}
