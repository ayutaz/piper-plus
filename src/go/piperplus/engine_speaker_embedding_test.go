// Tests for the Issue #426 / PR #320 input-feed contract.
//
// MB-iSTFT-VITS2 + Voice Cloning exports declare speaker_embedding /
// speaker_embedding_mask unconditionally; mainline runtimes must feed
// zero embedding + mask=0 so the model falls back to emb_g(sid).
// These tests pin the contract in the Go runtime so the regression
// reported against docker/python-inference cannot re-emerge here.

package piperplus

import (
	"testing"
)

// buildInputNamesForTest mirrors the input-name construction inside
// newOnnxEngine (engine.go:74-88) so the contract can be unit-tested
// without spinning up a real ONNX session.
func buildInputNamesForTest(caps *ModelCapabilities) []string {
	inputNames := []string{"input", "input_lengths", "scales"}
	if caps.HasSpeakerID {
		inputNames = append(inputNames, "sid")
	}
	if caps.HasLanguageID {
		inputNames = append(inputNames, "lid")
	}
	if caps.HasProsody {
		inputNames = append(inputNames, "prosody_features")
	}
	if caps.HasSpeakerEmbedding {
		inputNames = append(inputNames, "speaker_embedding")
		inputNames = append(inputNames, "speaker_embedding_mask")
	}
	return inputNames
}

func contains(slice []string, value string) bool {
	for _, s := range slice {
		if s == value {
			return true
		}
	}
	return false
}

func TestBuildInputNames_BaseOnly(t *testing.T) {
	caps := &ModelCapabilities{}
	names := buildInputNamesForTest(caps)
	if len(names) != 3 {
		t.Errorf("expected 3 base inputs, got %d: %v", len(names), names)
	}
	for _, want := range []string{"input", "input_lengths", "scales"} {
		if !contains(names, want) {
			t.Errorf("base input %q missing: %v", want, names)
		}
	}
}

func TestBuildInputNames_SpeakerEmbeddingAddedWhenDeclared(t *testing.T) {
	// Issue #426: speaker_embedding declared in the ONNX graph must be
	// listed as a session input even if the request itself omits the
	// embedding — the engine fills in zero+mask=0 (engine.go:274-289).
	caps := &ModelCapabilities{
		HasSpeakerID:        true,
		HasSpeakerEmbedding: true,
	}
	names := buildInputNamesForTest(caps)
	if !contains(names, "speaker_embedding") {
		t.Errorf("speaker_embedding missing: %v", names)
	}
	if !contains(names, "speaker_embedding_mask") {
		t.Errorf("speaker_embedding_mask missing: %v", names)
	}
}

func TestBuildInputNames_SpeakerEmbeddingAbsentByDefault(t *testing.T) {
	// Legacy non-MB-iSTFT exports must NOT receive these inputs (ORT
	// would reject them).
	caps := &ModelCapabilities{
		HasSpeakerID: true,
		HasProsody:   true,
	}
	names := buildInputNamesForTest(caps)
	if contains(names, "speaker_embedding") {
		t.Errorf("speaker_embedding leaked into legacy export: %v", names)
	}
	if contains(names, "speaker_embedding_mask") {
		t.Errorf("speaker_embedding_mask leaked into legacy export: %v", names)
	}
}

func TestBuildInputNames_OrderingProsodyBeforeEmbedding(t *testing.T) {
	// ONNX feed order: ..., prosody_features, speaker_embedding,
	// speaker_embedding_mask (matches export_onnx.py:505-515 and the
	// other runtime implementations — Python, Rust, C++).
	caps := &ModelCapabilities{
		HasSpeakerID:        true,
		HasLanguageID:       true,
		HasProsody:          true,
		HasSpeakerEmbedding: true,
	}
	names := buildInputNamesForTest(caps)

	idx := func(target string) int {
		for i, n := range names {
			if n == target {
				return i
			}
		}
		return -1
	}

	prosody := idx("prosody_features")
	emb := idx("speaker_embedding")
	mask := idx("speaker_embedding_mask")

	if prosody == -1 || emb == -1 || mask == -1 {
		t.Fatalf("expected all of prosody_features/speaker_embedding/mask present, got %v", names)
	}
	if prosody >= emb {
		t.Errorf("prosody_features must come before speaker_embedding: got %v", names)
	}
	if emb >= mask {
		t.Errorf("speaker_embedding must come before speaker_embedding_mask: got %v", names)
	}
}

func TestModelCapabilities_HasSpeakerEmbeddingField(t *testing.T) {
	// Field-existence regression guard: if HasSpeakerEmbedding is
	// accidentally renamed/removed, this compile-time reference catches it.
	caps := ModelCapabilities{HasSpeakerEmbedding: true}
	if !caps.HasSpeakerEmbedding {
		t.Error("HasSpeakerEmbedding field must be settable and readable")
	}
}
