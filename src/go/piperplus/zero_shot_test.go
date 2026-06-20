//go:build integration

package piperplus

import (
	"bytes"
	"context"
	"log/slog"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// zeroShotModelPath returns the model path for zero-shot integration tests.
// It prefers the PIPER_ZERO_SHOT_MODEL env var; otherwise it resolves the
// bundled test model relative to this source file.
func zeroShotModelPath(t *testing.T) string {
	t.Helper()
	if path := os.Getenv("PIPER_ZERO_SHOT_MODEL"); path != "" {
		return path
	}
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(filename), "..", "..", "..", "test", "models", "zero-shot-test.onnx")
}

// zeroShotSpeakerEmbeddingPath returns the test speaker embedding path.
func zeroShotSpeakerEmbeddingPath(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	return filepath.Join(filepath.Dir(filename), "..", "..", "..", "test", "models", "test_speaker.npy")
}

// TestZeroShotInference verifies end-to-end zero-shot synthesis:
// load model, load speaker embedding, synthesize, check non-empty audio.
func TestZeroShotInference(t *testing.T) {
	modelPath := zeroShotModelPath(t)
	embPath := zeroShotSpeakerEmbeddingPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	if !engine.Capabilities().HasSpeakerEmbedding {
		t.Skip("model does not have speaker_embedding input; skipping zero-shot test")
	}

	emb, err := LoadSpeakerEmbeddingFile(embPath)
	if err != nil {
		t.Fatalf("LoadSpeakerEmbeddingFile failed: %v", err)
	}
	if len(emb) == 0 {
		t.Fatal("loaded speaker embedding is empty")
	}

	req := &SynthesisRequest{
		PhonemeIDs:       []int64{1, 10, 57, 14, 2}, // ^, a, n, o, $
		SpeakerEmbedding: emb,
		NoiseScale:       0.4,
		LengthScale:      1.0,
		NoiseW:           0.5,
	}

	result, err := engine.Synthesize(context.Background(), req)
	if err != nil {
		t.Fatalf("Synthesize failed: %v", err)
	}
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if len(result.Audio) == 0 {
		t.Error("expected non-empty audio output")
	}
	if result.SampleRate != config.Audio.SampleRate {
		t.Errorf("expected SampleRate %d, got %d", config.Audio.SampleRate, result.SampleRate)
	}
	if result.InferTime <= 0 {
		t.Error("expected InferTime > 0")
	}

	// Verify the audio is writable as WAV.
	var buf bytes.Buffer
	if err := result.WriteWAV(&buf); err != nil {
		t.Fatalf("WriteWAV failed: %v", err)
	}
	if buf.Len() <= 44 {
		t.Errorf("expected WAV size > 44 bytes, got %d", buf.Len())
	}
}

// TestZeroShotDifferentEmbeddings verifies that two different speaker
// embeddings produce different audio outputs.
func TestZeroShotDifferentEmbeddings(t *testing.T) {
	modelPath := zeroShotModelPath(t)
	embPath := zeroShotSpeakerEmbeddingPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	if !engine.Capabilities().HasSpeakerEmbedding {
		t.Skip("model does not have speaker_embedding input; skipping zero-shot test")
	}

	emb1, err := LoadSpeakerEmbeddingFile(embPath)
	if err != nil {
		t.Fatalf("LoadSpeakerEmbeddingFile failed: %v", err)
	}

	// Create a second embedding by inverting the first.
	emb2 := make([]float32, len(emb1))
	for i, v := range emb1 {
		emb2[i] = -v
	}

	phonemeIDs := []int64{1, 10, 57, 14, 2}

	result1, err := engine.Synthesize(context.Background(), &SynthesisRequest{
		PhonemeIDs:       phonemeIDs,
		SpeakerEmbedding: emb1,
		NoiseScale:       0.0, // deterministic
		LengthScale:      1.0,
		NoiseW:           0.0,
	})
	if err != nil {
		t.Fatalf("Synthesize (emb1) failed: %v", err)
	}

	result2, err := engine.Synthesize(context.Background(), &SynthesisRequest{
		PhonemeIDs:       phonemeIDs,
		SpeakerEmbedding: emb2,
		NoiseScale:       0.0,
		LengthScale:      1.0,
		NoiseW:           0.0,
	})
	if err != nil {
		t.Fatalf("Synthesize (emb2) failed: %v", err)
	}

	if len(result1.Audio) == 0 || len(result2.Audio) == 0 {
		t.Fatal("expected non-empty audio for both embeddings")
	}

	// The two outputs must differ somewhere.
	same := len(result1.Audio) == len(result2.Audio)
	if same {
		for i := range result1.Audio {
			if result1.Audio[i] != result2.Audio[i] {
				same = false
				break
			}
		}
	}
	if same {
		t.Error("expected different audio for different speaker embeddings, but outputs are identical")
	}
}

// TestZeroShotZeroEmbedding verifies that an all-zeros speaker embedding does
// not cause a panic or error — the model may produce silent/degraded audio, but
// must not crash.
func TestZeroShotZeroEmbedding(t *testing.T) {
	modelPath := zeroShotModelPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	if !engine.Capabilities().HasSpeakerEmbedding {
		t.Skip("model does not have speaker_embedding input; skipping zero-shot test")
	}

	// 192-dimensional zero vector (matching CAM++ embedding size).
	zeroEmb := make([]float32, 192)

	req := &SynthesisRequest{
		PhonemeIDs:       []int64{1, 10, 57, 14, 2},
		SpeakerEmbedding: zeroEmb,
		NoiseScale:       0.4,
		LengthScale:      1.0,
		NoiseW:           0.5,
	}

	// Must not panic. An error is acceptable (e.g. NaN/Inf in output).
	result, err := engine.Synthesize(context.Background(), req)
	if err != nil {
		t.Logf("Synthesize with zero embedding returned error (acceptable): %v", err)
		return
	}
	if result == nil {
		t.Fatal("expected non-nil result")
	}
	// If synthesis succeeded, audio slice must be present (may be silent).
	// We do not assert non-empty here because a zero embedding may produce silence.
	t.Logf("zero embedding synthesis produced %d audio samples", len(result.Audio))
}
