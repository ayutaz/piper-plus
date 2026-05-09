package piperplus

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// E2E cosine gate for the speaker encoder. Mirrors
// test/test_speaker_encoder_e2e.py and src/rust/piper-core/tests/test_speaker_encoder_e2e.rs.
// See docs/spec/speaker-encoder-contract.md.
//
// This test is opt-in: it skips by default unless both
//   1. The fixture has an "e2e_cosine_gate" block, AND
//   2. PIPER_SPEAKER_ENCODER_ONNX_PATH points at a local encoder ONNX.

type e2eEncoderRef struct {
	HFRepo     string `json:"hf_repo"`
	HFFilename string `json:"hf_filename"`
	HFRevision string `json:"hf_revision"`
	SHA256     string `json:"sha256"`
}

type e2eReferenceWav struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}

type e2eExpectedEmbedding struct {
	Dim      int       `json:"dim"`
	Values   []float32 `json:"values"`
	Checksum string    `json:"checksum"`
}

type e2eGate struct {
	Version           int                  `json:"version"`
	EncoderONNX       e2eEncoderRef        `json:"encoder_onnx"`
	ReferenceWav      e2eReferenceWav      `json:"reference_wav"`
	ExpectedEmbedding e2eExpectedEmbedding `json:"expected_embedding"`
	CosineThreshold  float32 `json:"cosine_threshold"`
}

type e2eFixture struct {
	E2ECosineGate *e2eGate `json:"e2e_cosine_gate"`
}

func e2eRepoRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve caller path")
	}
	// src/go/piperplus/speaker_encoder_e2e_test.go -> three levels up
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
}

func e2eLoadFixture(t *testing.T) e2eFixture {
	t.Helper()
	root := e2eRepoRoot(t)
	path := filepath.Join(root, "test", "fixtures", "speaker_encoder_golden.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Skipf("cannot read fixture %s: %v", path, err)
	}
	var fx e2eFixture
	if err := json.Unmarshal(raw, &fx); err != nil {
		t.Skipf("cannot parse fixture: %v", err)
	}
	return fx
}

func e2eSHA256File(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("cannot read %s: %v", path, err)
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func e2eCosine(a, b []float32) float32 {
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return float32(dot / (math.Sqrt(na) * math.Sqrt(nb)))
}

func TestSpeakerEncoderE2ECosineGate(t *testing.T) {
	fx := e2eLoadFixture(t)
	if fx.E2ECosineGate == nil {
		t.Skip("fixture has no e2e_cosine_gate block — generator was run without " +
			"--encoder-onnx; layer-1 mel parity tests still apply")
	}
	gate := fx.E2ECosineGate

	encoderPath := os.Getenv("PIPER_SPEAKER_ENCODER_ONNX_PATH")
	if encoderPath == "" {
		t.Skip("PIPER_SPEAKER_ENCODER_ONNX_PATH not set — opt-in test, " +
			"skipping by default")
	}
	if _, err := os.Stat(encoderPath); err != nil {
		t.Fatalf("PIPER_SPEAKER_ENCODER_ONNX_PATH=%s does not exist: %v",
			encoderPath, err)
	}

	if expected := gate.EncoderONNX.SHA256; expected != "" {
		actual := e2eSHA256File(t, encoderPath)
		if actual != expected {
			t.Fatalf("encoder ONNX sha256 mismatch (silent upstream replacement?):\n"+
				"  expected: %s\n  actual:   %s\n  path:     %s",
				expected, actual, encoderPath)
		}
	}

	wavPath := gate.ReferenceWav.Path
	if !filepath.IsAbs(wavPath) {
		wavPath = filepath.Join(e2eRepoRoot(t), wavPath)
	}
	if _, err := os.Stat(wavPath); err != nil {
		t.Skipf("reference WAV not found at %s: %v", wavPath, err)
	}

	enc, err := NewSpeakerEncoder(encoderPath)
	if err != nil {
		t.Fatalf("NewSpeakerEncoder: %v", err)
	}
	defer enc.Close()

	actual, err := enc.EncodeFile(wavPath)
	if err != nil {
		t.Fatalf("EncodeFile: %v", err)
	}

	if got, want := len(actual), len(gate.ExpectedEmbedding.Values); got != want {
		t.Fatalf("embedding dim drift: got=%d want=%d", got, want)
	}

	cos := e2eCosine(actual, gate.ExpectedEmbedding.Values)
	if cos < gate.CosineThreshold {
		t.Fatalf("cosine gate failed: cos=%.6f < threshold=%.6f\n"+
			"  encoder: %s\n  WAV:     %s",
			cos, gate.CosineThreshold, encoderPath, wavPath)
	}
}
