package piperplus

import (
	"errors"
	"testing"
)

// TestValidate_SpeakerIDOnly_OK ensures a request with only SpeakerID set
// (and no SpeakerEmbedding) passes validation. This is the standard
// multi-speaker model path.
func TestValidate_SpeakerIDOnly_OK(t *testing.T) {
	req := &SynthesisRequest{
		PhonemeIDs: []int64{1, 2, 3},
		SpeakerID:  3,
	}
	if err := req.Validate(); err != nil {
		t.Fatalf("expected nil error for speaker_id-only request, got %v", err)
	}
}

// TestValidate_SpeakerEmbeddingOnly_OK ensures a request with only
// SpeakerEmbedding set (SpeakerID at zero default) passes validation. This
// is the voice-cloning path (single-speaker FT model + reference audio).
func TestValidate_SpeakerEmbeddingOnly_OK(t *testing.T) {
	req := &SynthesisRequest{
		PhonemeIDs:       []int64{1, 2, 3},
		SpeakerEmbedding: make([]float32, 256),
	}
	if err := req.Validate(); err != nil {
		t.Fatalf("expected nil error for embedding-only request, got %v", err)
	}
}

// TestValidate_BothSet_ReturnsError ensures specifying both a non-zero
// SpeakerID and a non-empty SpeakerEmbedding returns
// ErrSpeakerIDEmbeddingExclusive (matching Python/Rust behavior).
func TestValidate_BothSet_ReturnsError(t *testing.T) {
	req := &SynthesisRequest{
		PhonemeIDs:       []int64{1, 2, 3},
		SpeakerID:        3,
		SpeakerEmbedding: make([]float32, 256),
	}
	err := req.Validate()
	if err == nil {
		t.Fatal("expected error when both speaker_id and speaker_embedding are set, got nil")
	}
	if !errors.Is(err, ErrSpeakerIDEmbeddingExclusive) {
		t.Fatalf("expected ErrSpeakerIDEmbeddingExclusive, got %v", err)
	}
}

// TestValidate_NeitherSet_OK ensures the default zero-value request
// (SpeakerID == 0, SpeakerEmbedding == nil) passes validation. This is the
// single-speaker model path.
func TestValidate_NeitherSet_OK(t *testing.T) {
	req := &SynthesisRequest{
		PhonemeIDs: []int64{1, 2, 3},
	}
	if err := req.Validate(); err != nil {
		t.Fatalf("expected nil error for neither-set request, got %v", err)
	}
}

// TestValidate_NilRequest_OK ensures a nil receiver returns nil. Defensive:
// callers should never pass nil, but Validate should not panic.
func TestValidate_NilRequest_OK(t *testing.T) {
	var req *SynthesisRequest
	if err := req.Validate(); err != nil {
		t.Fatalf("expected nil error for nil request, got %v", err)
	}
}

// TestValidate_EmptyEmbeddingSlice_OK ensures a non-nil but empty
// SpeakerEmbedding slice (len == 0) is treated as "unset" and does not
// conflict with a non-zero SpeakerID. The mutual-exclusion check uses len()
// rather than nil-ness so callers can pre-allocate slices safely.
func TestValidate_EmptyEmbeddingSlice_OK(t *testing.T) {
	req := &SynthesisRequest{
		PhonemeIDs:       []int64{1, 2, 3},
		SpeakerID:        3,
		SpeakerEmbedding: []float32{},
	}
	if err := req.Validate(); err != nil {
		t.Fatalf("expected nil error for empty embedding slice with speaker_id, got %v", err)
	}
}

// TestValidateOptions_OK ensures SynthesisOptions.Validate is a stable
// no-op for callers that wish to call it uniformly. The speaker_id ×
// speaker_embedding check lives on SynthesisRequest because
// SynthesisOptions does not carry an embedding field.
func TestValidateOptions_OK(t *testing.T) {
	opts := &SynthesisOptions{SpeakerID: 5}
	if err := opts.Validate(); err != nil {
		t.Fatalf("expected nil error from SynthesisOptions.Validate, got %v", err)
	}
	var nilOpts *SynthesisOptions
	if err := nilOpts.Validate(); err != nil {
		t.Fatalf("expected nil error from nil SynthesisOptions.Validate, got %v", err)
	}
}
