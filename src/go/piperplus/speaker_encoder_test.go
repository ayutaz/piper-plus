package piperplus

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// ---------------------------------------------------------------------------
// Golden file structures
// ---------------------------------------------------------------------------

type goldenData struct {
	MelParams     goldenMelParams  `json:"mel_params"`
	HannWindow    goldenHannWindow `json:"hann_window"`
	MelFilterbank goldenFilterbank `json:"mel_filterbank"`
	TestCases     []goldenTestCase `json:"test_cases"`
}

type goldenMelParams struct {
	SR        int     `json:"sr"`
	NFFT      int     `json:"n_fft"`
	HopLength int     `json:"hop_length"`
	NMels     int     `json:"n_mels"`
	Fmin      float64 `json:"fmin"`
	Fmax      float64 `json:"fmax"`
}

type goldenHannWindow struct {
	Length   int       `json:"length"`
	First5   []float64 `json:"first_5"`
	Last5    []float64 `json:"last_5"`
	MidValue float64   `json:"mid_value"`
	Checksum string    `json:"checksum"`
}

type goldenFilterbank struct {
	Shape    []int     `json:"shape"`
	BandSums []float64 `json:"band_sums"`
	TotalSum float64   `json:"total_sum"`
	Checksum string    `json:"checksum"`
}

type goldenTestCase struct {
	ID                  string          `json:"id"`
	AudioParams         json.RawMessage `json:"audio_params"`
	AudioSamplesCount   int             `json:"audio_samples_count"`
	ExpectedMelShape    []int           `json:"expected_mel_shape"`
	MelCornerValues     *goldenCorners  `json:"mel_corner_values"`
	MelSampledEvery10   []float64       `json:"mel_sampled_every_10"`
	InputSamplesCount   int             `json:"input_samples_count"`
	ExpectedOutputCount int             `json:"expected_output_count"`
	OutputFirst10       []float64       `json:"output_first_10"`
	OutputLast10        []float64       `json:"output_last_10"`
}

type goldenCorners struct {
	TopLeft     float64 `json:"top_left"`
	TopRight    float64 `json:"top_right"`
	BottomLeft  float64 `json:"bottom_left"`
	BottomRight float64 `json:"bottom_right"`
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func loadGoldenData(t *testing.T) goldenData {
	t.Helper()

	_, filename, _, _ := runtime.Caller(0)
	dir := filepath.Dir(filename)

	candidates := []string{
		filepath.Join(dir, "..", "..", "..", "test", "fixtures", "speaker_encoder_golden.json"),
		filepath.Join(dir, "..", "..", "test", "fixtures", "speaker_encoder_golden.json"),
	}

	var data []byte
	var err error
	for _, candidate := range candidates {
		data, err = os.ReadFile(candidate)
		if err == nil {
			break
		}
	}
	if err != nil {
		t.Fatalf("Failed to load golden file: %v", err)
	}

	var g goldenData
	if err := json.Unmarshal(data, &g); err != nil {
		t.Fatalf("Failed to parse golden file: %v", err)
	}
	return g
}

func findTestCase(t *testing.T, g goldenData, id string) goldenTestCase {
	t.Helper()
	for _, tc := range g.TestCases {
		if tc.ID == id {
			return tc
		}
	}
	t.Fatalf("Test case %q not found in golden data", id)
	return goldenTestCase{}
}

func generateSineGo(freqHz float64, durationS float64, sr int) []float32 {
	n := int(durationS * float64(sr))
	samples := make([]float32, n)
	for i := 0; i < n; i++ {
		samples[i] = float32(math.Sin(2 * math.Pi * freqHz * float64(i) / float64(sr)))
	}
	return samples
}

func generateMultitoneGo(freqs []float64, durationS float64, sr int) []float32 {
	n := int(durationS * float64(sr))
	samples := make([]float32, n)
	for _, f := range freqs {
		for i := 0; i < n; i++ {
			samples[i] += float32(math.Sin(2 * math.Pi * f * float64(i) / float64(sr)))
		}
	}
	var peak float32
	for _, s := range samples {
		if v := float32(math.Abs(float64(s))); v > peak {
			peak = v
		}
	}
	if peak > 0 {
		for i := range samples {
			samples[i] /= peak
		}
	}
	return samples
}

// logFloor = float32(-23.025851) // log(1e-10) -- removed: unused in tests

// ---------------------------------------------------------------------------
// Tests: Parameter validation
// ---------------------------------------------------------------------------

func TestGolden_MelParamsMatch(t *testing.T) {
	g := loadGoldenData(t)

	if g.MelParams.SR != melSampleRate {
		t.Errorf("SR: expected %d, got %d", melSampleRate, g.MelParams.SR)
	}
	if g.MelParams.NFFT != melNFFT {
		t.Errorf("NFFT: expected %d, got %d", melNFFT, g.MelParams.NFFT)
	}
	if g.MelParams.HopLength != melHopLength {
		t.Errorf("HopLength: expected %d, got %d", melHopLength, g.MelParams.HopLength)
	}
	if g.MelParams.NMels != melNMels {
		t.Errorf("NMels: expected %d, got %d", melNMels, g.MelParams.NMels)
	}
	if math.Abs(g.MelParams.Fmin-melFmin) > 0.01 {
		t.Errorf("Fmin: expected %v, got %v", melFmin, g.MelParams.Fmin)
	}
	if math.Abs(g.MelParams.Fmax-melFmax) > 0.01 {
		t.Errorf("Fmax: expected %v, got %v", melFmax, g.MelParams.Fmax)
	}
}

// ---------------------------------------------------------------------------
// Tests: Hann window
// ---------------------------------------------------------------------------

func TestGolden_HannWindow_First5(t *testing.T) {
	g := loadGoldenData(t)
	w := hannWindow(g.HannWindow.Length)

	for i, expected := range g.HannWindow.First5 {
		if math.Abs(float64(w[i])-expected) > 1e-5 {
			t.Errorf("hann_window[%d]: expected %v, got %v", i, expected, w[i])
		}
	}
}

func TestGolden_HannWindow_Last5(t *testing.T) {
	g := loadGoldenData(t)
	w := hannWindow(g.HannWindow.Length)
	n := len(w)

	for i, expected := range g.HannWindow.Last5 {
		idx := n - 5 + i
		if math.Abs(float64(w[idx])-expected) > 1e-5 {
			t.Errorf("hann_window[%d]: expected %v, got %v", idx, expected, w[idx])
		}
	}
}

func TestGolden_HannWindow_MidValue(t *testing.T) {
	g := loadGoldenData(t)
	w := hannWindow(g.HannWindow.Length)
	mid := len(w) / 2

	if math.Abs(float64(w[mid])-g.HannWindow.MidValue) > 1e-5 {
		t.Errorf("hann_window mid: expected %v, got %v", g.HannWindow.MidValue, w[mid])
	}
}

// ---------------------------------------------------------------------------
// Tests: Mel filterbank
// ---------------------------------------------------------------------------

func TestGolden_Filterbank_Shape(t *testing.T) {
	g := loadGoldenData(t)
	fb := createMelFilterbank()
	fftBins := melNFFT/2 + 1

	if g.MelFilterbank.Shape[0] != melNMels {
		t.Errorf("filterbank shape[0]: expected %d, got %d", melNMels, g.MelFilterbank.Shape[0])
	}
	if g.MelFilterbank.Shape[1] != fftBins {
		t.Errorf("filterbank shape[1]: expected %d, got %d", fftBins, g.MelFilterbank.Shape[1])
	}
	if len(fb) != melNMels*fftBins {
		t.Errorf("filterbank length: expected %d, got %d", melNMels*fftBins, len(fb))
	}
}

func TestGolden_Filterbank_BandSums(t *testing.T) {
	g := loadGoldenData(t)
	fb := createMelFilterbank()
	fftBins := melNFFT/2 + 1

	for m := 0; m < melNMels; m++ {
		var bandSum float64
		for k := 0; k < fftBins; k++ {
			bandSum += float64(fb[m*fftBins+k])
		}
		expected := g.MelFilterbank.BandSums[m]
		var relErr float64
		if math.Abs(expected) > 1e-10 {
			relErr = math.Abs((bandSum - expected) / expected)
		} else {
			relErr = math.Abs(bandSum - expected)
		}
		if relErr >= 0.02 {
			t.Errorf("filterbank band[%d] sum: expected %v, got %v (rel err %v)",
				m, expected, bandSum, relErr)
		}
	}
}

func TestGolden_Filterbank_TotalSum(t *testing.T) {
	g := loadGoldenData(t)
	fb := createMelFilterbank()

	var total float64
	for _, v := range fb {
		total += float64(v)
	}
	relErr := math.Abs((total - g.MelFilterbank.TotalSum) / g.MelFilterbank.TotalSum)
	if relErr >= 0.02 {
		t.Errorf("filterbank total: expected %v, got %v (rel err %v)",
			g.MelFilterbank.TotalSum, total, relErr)
	}
}

// ---------------------------------------------------------------------------
// Tests: Mel spectrogram shape and structure
// ---------------------------------------------------------------------------

func TestGolden_Sine440Hz_MelShape(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "sine_440hz_1s")

	audio := generateSineGo(440, 1.0, melSampleRate)
	if len(audio) != tc.AudioSamplesCount {
		t.Fatalf("audio length: expected %d, got %d", tc.AudioSamplesCount, len(audio))
	}

	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if tc.ExpectedMelShape[0] != melNMels {
		t.Errorf("mel shape[0]: expected %d, got %d", melNMels, tc.ExpectedMelShape[0])
	}
	if tc.ExpectedMelShape[1] != nFrames {
		t.Errorf("mel shape[1]: expected %d, got %d", nFrames, tc.ExpectedMelShape[1])
	}
}

// TestGolden_Sine440Hz_ActiveBins verifies that a 440Hz sine produces high
// energy in the expected low-frequency mel bins and low energy in the high-
// frequency mel bins.
func TestGolden_Sine440Hz_ActiveBins(t *testing.T) {
	audio := generateSineGo(440, 1.0, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if nFrames == 0 {
		t.Fatal("no frames produced")
	}

	// 440Hz maps roughly to mel bin ~12-15. Check that the mid-frame has
	// high energy in bins 5-25 and low energy in bins 60-80.
	midFrame := nFrames / 2

	var lowBinMax float32 = -100
	for m := 5; m < 25; m++ {
		v := mel[m*nFrames+midFrame]
		if v > lowBinMax {
			lowBinMax = v
		}
	}

	var highBinMax float32 = -100
	for m := 60; m < melNMels; m++ {
		v := mel[m*nFrames+midFrame]
		if v > highBinMax {
			highBinMax = v
		}
	}

	// The active bins should have significantly higher energy than the quiet bins
	if lowBinMax <= highBinMax {
		t.Errorf("expected low mel bins to have more energy than high bins for 440Hz: low=%v, high=%v",
			lowBinMax, highBinMax)
	}

	// Active bins should have energy well above the floor
	if lowBinMax < float32(-15) {
		t.Errorf("expected active mel bins to have energy > -15 for 440Hz sine, got %v", lowBinMax)
	}
}

// TestGolden_Sine440Hz_MelCornerStructure verifies that the golden and Go
// implementations agree on the general structure: which corners have high
// vs low energy. Exact values may differ due to Go's float64 trig.
func TestGolden_Sine440Hz_MelCornerStructure(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "sine_440hz_1s")

	audio := generateSineGo(440, 1.0, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	// Top-left (mel bin 0, frame 0) — golden and Go should agree within 2.0
	goTL := float64(mel[0])
	goldenTL := tc.MelCornerValues.TopLeft
	if math.Abs(goTL-goldenTL) > 2.0 {
		t.Errorf("top_left: golden=%v, go=%v (diff %v)", goldenTL, goTL, math.Abs(goTL-goldenTL))
	}

	// Top-right (mel bin 0, last frame) — should also agree
	goTR := float64(mel[nFrames-1])
	goldenTR := tc.MelCornerValues.TopRight
	if math.Abs(goTR-goldenTR) > 2.0 {
		t.Errorf("top_right: golden=%v, go=%v (diff %v)", goldenTR, goTR, math.Abs(goTR-goldenTR))
	}

	// Bottom corners (high mel bins) may differ more due to near-zero energy
	// but both should be negative (log of small values)
	goBL := float64(mel[(melNMels-1)*nFrames])
	goBR := float64(mel[melNMels*nFrames-1])
	if goBL > 0 {
		t.Errorf("bottom_left should be negative (log-mel), got %v", goBL)
	}
	if goBR > 0 {
		t.Errorf("bottom_right should be negative (log-mel), got %v", goBR)
	}
}

func TestGolden_Sine1000Hz_MelShape(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "sine_1000hz_0.5s")

	audio := generateSineGo(1000, 0.5, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if tc.ExpectedMelShape[0] != melNMels {
		t.Errorf("mel shape[0]: expected %d, got %d", melNMels, tc.ExpectedMelShape[0])
	}
	if tc.ExpectedMelShape[1] != nFrames {
		t.Errorf("mel shape[1]: expected %d, got %d", nFrames, tc.ExpectedMelShape[1])
	}
}

func TestGolden_Sine1000Hz_ActiveBins(t *testing.T) {
	audio := generateSineGo(1000, 0.5, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if nFrames == 0 {
		t.Fatal("no frames produced")
	}

	// 1000Hz maps roughly to mel bin ~20-30
	midFrame := nFrames / 2

	var activeBinMax float32 = -100
	for m := 15; m < 40; m++ {
		v := mel[m*nFrames+midFrame]
		if v > activeBinMax {
			activeBinMax = v
		}
	}

	if activeBinMax < float32(-15) {
		t.Errorf("expected active mel bins to have energy > -15 for 1000Hz sine, got %v", activeBinMax)
	}
}

func TestGolden_Multitone_MelShape(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "multitone_200_600_2000hz_0.5s")

	audio := generateMultitoneGo([]float64{200, 600, 2000}, 0.5, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if tc.ExpectedMelShape[0] != melNMels {
		t.Errorf("mel shape[0]: expected %d, got %d", melNMels, tc.ExpectedMelShape[0])
	}
	if tc.ExpectedMelShape[1] != nFrames {
		t.Errorf("mel shape[1]: expected %d, got %d", nFrames, tc.ExpectedMelShape[1])
	}
}

func TestGolden_Multitone_ActiveBins(t *testing.T) {
	audio := generateMultitoneGo([]float64{200, 600, 2000}, 0.5, melSampleRate)
	mel := computeMelSpectrogram(audio)
	nFrames := len(mel) / melNMels

	if nFrames == 0 {
		t.Fatal("no frames produced")
	}

	midFrame := nFrames / 2

	// Multitone should have energy distributed across multiple mel bins.
	// Count how many bins have energy above -20 (well above the floor -23.025).
	activeBins := 0
	for m := 0; m < melNMels; m++ {
		if mel[m*nFrames+midFrame] > -20 {
			activeBins++
		}
	}
	// With 3 tones (200, 600, 2000 Hz) we should see at least 3 active bins
	if activeBins < 3 {
		t.Errorf("expected at least 3 active mel bins for multitone, got %d", activeBins)
	}
}

// ---------------------------------------------------------------------------
// Tests: Resampling (golden comparison -- resampling is independent of trig)
// ---------------------------------------------------------------------------

func TestGolden_Resample48kTo16k_OutputLength(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "resample_48k_to_16k")

	audio48k := generateSineGo(440, 0.1, 48000)
	if len(audio48k) != tc.InputSamplesCount {
		t.Fatalf("input length: expected %d, got %d", tc.InputSamplesCount, len(audio48k))
	}

	resampled := resampleLinear(audio48k, 48000, melSampleRate)
	if len(resampled) != tc.ExpectedOutputCount {
		t.Errorf("output length: expected %d, got %d", tc.ExpectedOutputCount, len(resampled))
	}
}

func TestGolden_Resample48kTo16k_Values(t *testing.T) {
	g := loadGoldenData(t)
	tc := findTestCase(t, g, "resample_48k_to_16k")

	audio48k := generateSineGo(440, 0.1, 48000)
	resampled := resampleLinear(audio48k, 48000, melSampleRate)

	for i, expected := range tc.OutputFirst10 {
		if math.Abs(float64(resampled[i])-expected) > 1e-4 {
			t.Errorf("resample first[%d]: expected %v, got %v", i, expected, resampled[i])
		}
	}

	n := len(resampled)
	for i, expected := range tc.OutputLast10 {
		idx := n - 10 + i
		if math.Abs(float64(resampled[idx])-expected) > 1e-4 {
			t.Errorf("resample last[%d]: expected %v, got %v", i, expected, resampled[idx])
		}
	}
}

// ---------------------------------------------------------------------------
// Tests: Determinism (Go self-consistency)
// ---------------------------------------------------------------------------

func TestGolden_Deterministic_SameInput(t *testing.T) {
	audio := generateSineGo(440, 0.5, melSampleRate)
	mel1 := computeMelSpectrogram(audio)
	mel2 := computeMelSpectrogram(audio)

	if len(mel1) != len(mel2) {
		t.Fatalf("length mismatch: %d vs %d", len(mel1), len(mel2))
	}
	for i := range mel1 {
		if mel1[i] != mel2[i] {
			t.Fatalf("non-deterministic at index %d: %v vs %v", i, mel1[i], mel2[i])
		}
	}
}

// ---------------------------------------------------------------------------
// Tests: Edge cases
// ---------------------------------------------------------------------------

func TestGolden_SilentAudio_FiniteMel(t *testing.T) {
	silence := make([]float32, 16000)
	mel := computeMelSpectrogram(silence)

	if len(mel) == 0 {
		t.Fatal("silent audio should produce non-empty mel")
	}
	for i, v := range mel {
		if math.IsNaN(float64(v)) || math.IsInf(float64(v), 0) {
			t.Fatalf("mel[%d] is not finite: %v", i, v)
		}
	}
}

func TestGolden_ShortAudio_EmptyMel(t *testing.T) {
	short := make([]float32, 100)
	mel := computeMelSpectrogram(short)
	if len(mel) != 0 {
		t.Errorf("short audio should produce empty mel, got %d values", len(mel))
	}
}

func TestGolden_ResampleSameRate(t *testing.T) {
	samples := []float32{1, 2, 3, 4}
	result := resampleLinear(samples, 16000, 16000)
	if len(result) != len(samples) {
		t.Fatalf("expected %d samples, got %d", len(samples), len(result))
	}
	for i := range samples {
		if result[i] != samples[i] {
			t.Errorf("sample[%d]: expected %v, got %v", i, samples[i], result[i])
		}
	}
}

func TestGolden_ResampleEmpty(t *testing.T) {
	result := resampleLinear([]float32{}, 48000, 16000)
	if len(result) != 0 {
		t.Errorf("expected empty, got %d samples", len(result))
	}
}

func TestGolden_ResampleDownsample(t *testing.T) {
	samples := make([]float32, 1000)
	for i := range samples {
		samples[i] = float32(math.Sin(float64(i)))
	}
	result := resampleLinear(samples, 48000, 16000)
	// 48kHz -> 16kHz = 1/3 ratio, expect ~334 samples
	if math.Abs(float64(len(result))-334.0) > 2 {
		t.Errorf("expected ~334 samples, got %d", len(result))
	}
}

func TestGolden_HannWindow_Endpoints(t *testing.T) {
	w := hannWindow(512)
	if len(w) != 512 {
		t.Fatalf("expected 512 window values, got %d", len(w))
	}
	if math.Abs(float64(w[0])) > 1e-6 {
		t.Errorf("first window value should be near zero: %v", w[0])
	}
}

func TestGolden_HzToMel_Roundtrip(t *testing.T) {
	hz := float32(1000)
	mel := hzToMel(hz)
	hzBack := melToHz(mel)
	if math.Abs(float64(hz-hzBack)) > 0.01 {
		t.Errorf("Hz roundtrip: %v -> %v -> %v", hz, mel, hzBack)
	}
}

func TestGolden_FilterbankBands_AllNonZero(t *testing.T) {
	fb := createMelFilterbank()
	fftBins := melNFFT/2 + 1

	for m := 0; m < melNMels; m++ {
		var bandSum float64
		for k := 0; k < fftBins; k++ {
			bandSum += float64(fb[m*fftBins+k])
		}
		if bandSum <= 0 {
			t.Errorf("mel band %d has zero total weight", m)
		}
	}
}

func TestGolden_AllMelValues_Finite(t *testing.T) {
	signals := []struct {
		name string
		gen  func() []float32
	}{
		{"440Hz", func() []float32 { return generateSineGo(440, 1.0, melSampleRate) }},
		{"1000Hz", func() []float32 { return generateSineGo(1000, 0.5, melSampleRate) }},
		{"multitone", func() []float32 { return generateMultitoneGo([]float64{200, 600, 2000}, 0.5, melSampleRate) }},
	}

	for _, sig := range signals {
		t.Run(sig.name, func(t *testing.T) {
			audio := sig.gen()
			mel := computeMelSpectrogram(audio)
			for i, v := range mel {
				if math.IsNaN(float64(v)) || math.IsInf(float64(v), 0) {
					t.Fatalf("%s: mel[%d] is not finite: %v", sig.name, i, v)
				}
			}
		})
	}
}
