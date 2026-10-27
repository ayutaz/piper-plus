//go:build integration

package piperplus

// zs-v1 CAM++ embedding parity with the Python recipe, using the real model.
//
// kaldi_fbank_test.go checks the features; this checks what the runtime
// feeds the base model: SpeakerEncoder on the pinned campplus.onnx, against
// embeddings that test/generate_zs_campplus_golden.py computed with
// torchaudio + onnxruntime (the recipe in huggingface-space/zero_shot.py).
// The browser runs the same fixture in test-zs-campplus-parity.js.
//
// Needs the pinned model at PIPER_PLUS_CAMPPLUS_ONNX (CI sets it).

import (
	"crypto/sha256"
	"encoding/hex"
	"math"
	"os"
	"testing"
)

const campplusSHA256 = "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73"

// Same thresholds as the browser test: measured cosine >= 0.9999999 on these
// signals. Changing one detail lands below: preemphasis 0.97 -> 0.96 gives
// 0.99969, resampler rolloff 0.99 gives 0.981, a plain Hann window 0.987.
const (
	campplusMinCosine = 0.9999
	campplusMaxAbs    = 5e-4
)

type campplusGolden struct {
	CampplusSHA256 string         `json:"campplus_sha256"`
	SyllableHz     float64        `json:"syllable_hz"`
	Amplitude      float64        `json:"amplitude"`
	MaxHarmonics   int            `json:"max_harmonics"`
	NoisePartials  [][2]float64   `json:"noise_partials"`
	NoiseFloor     float64        `json:"noise_floor"`
	NoiseSeed      uint32         `json:"noise_seed"`
	DistinctPair   [2]string      `json:"distinct_pair"`
	Cases          []campplusCase `json:"cases"`
}

type campplusCase struct {
	Name           string    `json:"name"`
	SampleRate     int       `json:"sample_rate"`
	Seconds        float64   `json:"seconds"`
	F0             float64   `json:"f0"`
	VibratoHz      float64   `json:"vibrato_hz"`
	VibratoDepthHz float64   `json:"vibrato_depth_hz"`
	Embedding      []float32 `json:"embedding"`
}

// campplusModelPath returns PIPER_PLUS_CAMPPLUS_ONNX after checking the
// file is the pinned model, or skips when the variable is unset.
func campplusModelPath(t *testing.T) string {
	t.Helper()
	path := os.Getenv("PIPER_PLUS_CAMPPLUS_ONNX")
	if path == "" {
		t.Skip("PIPER_PLUS_CAMPPLUS_ONNX not set")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("PIPER_PLUS_CAMPPLUS_ONNX=%s: %v", path, err)
	}
	sum := sha256.Sum256(data)
	if got := hex.EncodeToString(sum[:]); got != campplusSHA256 {
		t.Fatalf("campplus.onnx hash %s, want %s", got, campplusSHA256)
	}
	return path
}

// whiteNoise is xorshift32 in [-0.5, 0.5), bit-identical to white_noise()
// in the generator.
func whiteNoise(n int, seed uint32) []float64 {
	out := make([]float64, n)
	x := seed
	for i := range out {
		x ^= x << 13
		x ^= x >> 17
		x ^= x << 5
		out[i] = float64(x)/4294967296.0 - 0.5
	}
	return out
}

// voicedSignal mirrors voiced_signal() in the generator: a harmonic tone
// with vibrato and a syllable-rate envelope, high partials in the gaps
// (they exercise the resampler cutoff) and a weak white floor, computed in
// float64 and stored as float32.
func voicedSignal(g *campplusGolden, c *campplusCase) []float32 {
	rate := float64(c.SampleRate)
	n := int(math.Round(rate * c.Seconds))
	floor := whiteNoise(n, g.NoiseSeed)
	out := make([]float32, n)
	for i := range out {
		t := float64(i) / rate
		phase := 2*math.Pi*c.F0*t - (c.VibratoDepthHz/c.VibratoHz)*math.Cos(2*math.Pi*c.VibratoHz*t)
		envelope := 0.5 * (1 - math.Cos(2*math.Pi*g.SyllableHz*t))
		x := 0.0
		for k := 1; float64(k)*(c.F0+c.VibratoDepthHz) < rate/2 && k <= g.MaxHarmonics; k++ {
			x += (g.Amplitude / float64(k)) * math.Sin(float64(k)*phase)
		}
		noise := 0.0
		for _, p := range g.NoisePartials {
			if p[1] < rate/2 {
				noise += p[0] * math.Sin(2*math.Pi*p[1]*t)
			}
		}
		out[i] = float32(envelope*x + (1-envelope)*noise + g.NoiseFloor*floor[i])
	}
	return out
}

func cosine(a, b []float32) float64 {
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	return dot / math.Sqrt(na*nb)
}

func TestCampplusEmbeddingsMatchPythonRecipe(t *testing.T) {
	path := campplusModelPath(t)
	var g campplusGolden
	readRepoFixture(t, "zs_campplus_golden.json", &g)
	if g.CampplusSHA256 != campplusSHA256 {
		t.Fatalf("fixture was generated with another model: %s", g.CampplusSHA256)
	}

	// The default constructor must pick the zs-v1 front end for CAM++.
	enc, err := NewSpeakerEncoder(path)
	if err != nil {
		t.Fatal(err)
	}
	defer enc.Close()
	if enc.FrontEnd() != SpeakerFrontEndKaldiFbank {
		t.Fatalf("front end %v, want kaldi-fbank", enc.FrontEnd())
	}

	embeddings := map[string][]float32{}
	for i := range g.Cases {
		c := &g.Cases[i]
		emb, err := enc.Encode(voicedSignal(&g, c), c.SampleRate)
		if err != nil {
			t.Fatalf("%s: %v", c.Name, err)
		}
		if len(emb) != len(c.Embedding) {
			t.Fatalf("%s: %d values, want %d", c.Name, len(emb), len(c.Embedding))
		}
		maxAbs := 0.0
		for j := range emb {
			maxAbs = math.Max(maxAbs, math.Abs(float64(emb[j])-float64(c.Embedding[j])))
		}
		cos := cosine(emb, c.Embedding)
		t.Logf("%s: cosine %.7f, max abs %.2e", c.Name, cos, maxAbs)
		if cos < campplusMinCosine {
			t.Errorf("%s: cosine %g < %g", c.Name, cos, campplusMinCosine)
		}
		if maxAbs > campplusMaxAbs {
			t.Errorf("%s: max abs %g > %g", c.Name, maxAbs, campplusMaxAbs)
		}
		embeddings[c.Name] = emb
	}

	// Guards against a degenerate encoder that returns the same vector for
	// every voice.
	low, high := embeddings[g.DistinctPair[0]], embeddings[g.DistinctPair[1]]
	if low == nil || high == nil {
		t.Fatal("distinct_pair cases must have run")
	}
	if cos := cosine(low, high); cos >= 0.95 {
		t.Errorf("cosine %g between distinct voices", cos)
	}
}

func TestCampplusMelFrontEndDoesNotMatch(t *testing.T) {
	// The legacy front end on the same model drifts well away from the
	// Python embedding; this is what #915 fixed for CAM++.
	path := campplusModelPath(t)
	var g campplusGolden
	readRepoFixture(t, "zs_campplus_golden.json", &g)
	var c *campplusCase
	for i := range g.Cases {
		if g.Cases[i].SampleRate != 16000 {
			c = &g.Cases[i]
			break
		}
	}
	if c == nil {
		t.Fatal("no resampled case")
	}
	enc, err := NewSpeakerEncoderWithFrontEnd(path, SpeakerFrontEndMel)
	if err != nil {
		t.Fatal(err)
	}
	defer enc.Close()
	emb, err := enc.Encode(voicedSignal(&g, c), c.SampleRate)
	if err != nil {
		t.Fatal(err)
	}
	cos := cosine(emb, c.Embedding)
	t.Logf("%s with the legacy front end: cosine %.4f", c.Name, cos)
	if cos >= campplusMinCosine {
		t.Errorf("legacy front end unexpectedly matched: cosine %g", cos)
	}
}
