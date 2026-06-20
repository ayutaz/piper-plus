package piperplus

import (
	"testing"
)

// ---------------------------------------------------------------------------
// SynthesisRequest SpeakerEmbedding propagation
// ---------------------------------------------------------------------------

// TestSynthesisRequestIncludesSpeakerEmbedding verifies that when
// SynthesisOptions.SpeakerEmbedding is set via WithSpeakerEmbedding, it is
// present on the SynthesisRequest built by NewSynthesisRequest.
func TestSynthesisRequestIncludesSpeakerEmbedding(t *testing.T) {
	emb := []float32{0.1, 0.2, 0.3}
	ids := []int64{1, 10, 57, 14, 2}

	req := NewSynthesisRequest(ids, WithSpeakerEmbedding(emb))

	if req == nil {
		t.Fatal("expected non-nil SynthesisRequest")
	}
	if len(req.SpeakerEmbedding) != len(emb) {
		t.Fatalf("SpeakerEmbedding length: expected %d, got %d", len(emb), len(req.SpeakerEmbedding))
	}
	for i, v := range emb {
		if req.SpeakerEmbedding[i] != v {
			t.Errorf("SpeakerEmbedding[%d]: expected %v, got %v", i, v, req.SpeakerEmbedding[i])
		}
	}
}

// TestSynthesisRequestNoSpeakerEmbedding verifies that NewSynthesisRequest
// leaves SpeakerEmbedding nil when WithSpeakerEmbedding is not used.
func TestSynthesisRequestNoSpeakerEmbedding(t *testing.T) {
	ids := []int64{1, 10, 57, 14, 2}
	req := NewSynthesisRequest(ids)

	if req == nil {
		t.Fatal("expected non-nil SynthesisRequest")
	}
	if len(req.SpeakerEmbedding) != 0 {
		t.Errorf("SpeakerEmbedding: expected nil/empty, got %v", req.SpeakerEmbedding)
	}
}
