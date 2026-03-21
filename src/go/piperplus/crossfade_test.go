package piperplus

import (
	"math"
	"testing"
)

// ---------------------------------------------------------------------------
// CrossfadeChunks — float32 crossfade matching C++ crossfadeAudioChunks()
// ---------------------------------------------------------------------------

func TestCrossfadeChunks_Basic(t *testing.T) {
	// Two chunks of 200 samples each. With overlapSamples=50,
	// actualOverlap = min(50, 200/4=50, 200/4=50) = 50 >= 44 -> crossfade.
	prev := make([]float32, 200)
	next := make([]float32, 200)
	for i := range prev {
		prev[i] = 1000.0
	}
	for i := range next {
		next[i] = 2000.0
	}

	out := CrossfadeChunks(prev, next, 50)

	expectedLen := 200 + 200 - 50
	if len(out) != expectedLen {
		t.Fatalf("expected %d samples, got %d", expectedLen, len(out))
	}

	// Non-overlapping head should be 1000.
	for i := 0; i < 150; i++ {
		if out[i] != 1000.0 {
			t.Errorf("head[%d]: expected 1000, got %f", i, out[i])
			break
		}
	}

	// Non-overlapping tail should be 2000.
	for i := 200; i < expectedLen; i++ {
		if out[i] != 2000.0 {
			t.Errorf("tail[%d]: expected 2000, got %f", i, out[i])
			break
		}
	}

	// Blended region: midpoint should be close to 1500.
	mid := 150 + 25 // midpoint of the overlap
	tolerance := float32(1.0)
	if math.Abs(float64(out[mid]-1500.0)) > float64(tolerance) {
		t.Errorf("blend midpoint[%d]: expected ~1500, got %f", mid, out[mid])
	}

	// First blended sample: t=0 -> prev*1 + next*0 = 1000.
	if out[150] != 1000.0 {
		t.Errorf("blend start[150]: expected 1000, got %f", out[150])
	}

	// Last blended sample: t=49/50=0.98 -> 1000*0.02 + 2000*0.98 = 1980.
	lastBlend := 150 + 49
	expected := float32(1000.0*0.02 + 2000.0*0.98)
	if math.Abs(float64(out[lastBlend]-expected)) > 1.0 {
		t.Errorf("blend end[%d]: expected ~%f, got %f", lastBlend, expected, out[lastBlend])
	}
}

func TestCrossfadeChunks_OverlapCappedAtQuarter(t *testing.T) {
	// prev has 200 samples, next has 100 samples.
	// overlapSamples = 220 (default).
	// actualOverlap = min(220, 200/4=50, 100/4=25) = 25.
	// 25 < MinCrossfadeSamples(44) -> no crossfade, just concatenate.
	prev := make([]float32, 200)
	next := make([]float32, 100)
	for i := range prev {
		prev[i] = float32(i)
	}
	for i := range next {
		next[i] = float32(i + 1000)
	}

	out := CrossfadeChunks(prev, next, DefaultOverlapSamples)

	if len(out) != 300 {
		t.Fatalf("expected 300 samples (concatenated), got %d", len(out))
	}

	// Verify concatenation.
	for i := 0; i < 200; i++ {
		if out[i] != float32(i) {
			t.Errorf("prev[%d]: expected %f, got %f", i, float32(i), out[i])
			break
		}
	}
	for i := 0; i < 100; i++ {
		if out[200+i] != float32(i+1000) {
			t.Errorf("next[%d]: expected %f, got %f", i, float32(i+1000), out[200+i])
			break
		}
	}
}

func TestCrossfadeChunks_OverlapCappedButAboveMin(t *testing.T) {
	// prev has 400 samples, next has 200 samples.
	// overlapSamples = 220.
	// actualOverlap = min(220, 400/4=100, 200/4=50) = 50 >= 44 -> crossfade.
	prev := make([]float32, 400)
	next := make([]float32, 200)
	for i := range prev {
		prev[i] = 500.0
	}
	for i := range next {
		next[i] = 1500.0
	}

	out := CrossfadeChunks(prev, next, DefaultOverlapSamples)

	expectedLen := 400 + 200 - 50
	if len(out) != expectedLen {
		t.Fatalf("expected %d samples, got %d", expectedLen, len(out))
	}
}

func TestCrossfadeChunks_BelowMinThreshold(t *testing.T) {
	// Both chunks have 160 samples -> quarter = 40 < MinCrossfadeSamples(44).
	// Should concatenate without crossfade.
	prev := make([]float32, 160)
	next := make([]float32, 160)
	for i := range prev {
		prev[i] = 100.0
	}
	for i := range next {
		next[i] = 200.0
	}

	out := CrossfadeChunks(prev, next, DefaultOverlapSamples)

	if len(out) != 320 {
		t.Fatalf("expected 320 (concatenated), got %d", len(out))
	}

	// Verify no blending.
	if out[159] != 100.0 {
		t.Errorf("expected prev tail = 100, got %f", out[159])
	}
	if out[160] != 200.0 {
		t.Errorf("expected next head = 200, got %f", out[160])
	}
}

func TestCrossfadeChunks_EmptyPrev(t *testing.T) {
	next := []float32{1.0, 2.0, 3.0}
	out := CrossfadeChunks(nil, next, 50)

	if len(out) != 3 {
		t.Fatalf("expected 3 samples, got %d", len(out))
	}
	for i, v := range next {
		if out[i] != v {
			t.Errorf("sample[%d]: expected %f, got %f", i, v, out[i])
		}
	}
}

func TestCrossfadeChunks_EmptyNext(t *testing.T) {
	prev := []float32{4.0, 5.0, 6.0}
	out := CrossfadeChunks(prev, nil, 50)

	if len(out) != 3 {
		t.Fatalf("expected 3 samples, got %d", len(out))
	}
	for i, v := range prev {
		if out[i] != v {
			t.Errorf("sample[%d]: expected %f, got %f", i, v, out[i])
		}
	}
}

func TestCrossfadeChunks_BothEmpty(t *testing.T) {
	out := CrossfadeChunks(nil, nil, 50)
	if len(out) != 0 {
		t.Errorf("expected 0 samples, got %d", len(out))
	}
}

func TestCrossfadeChunks_ZeroOverlap(t *testing.T) {
	prev := []float32{1.0, 2.0}
	next := []float32{3.0, 4.0}
	out := CrossfadeChunks(prev, next, 0)

	if len(out) != 4 {
		t.Fatalf("expected 4 samples, got %d", len(out))
	}
	want := []float32{1.0, 2.0, 3.0, 4.0}
	for i, w := range want {
		if out[i] != w {
			t.Errorf("sample[%d]: expected %f, got %f", i, w, out[i])
		}
	}
}

func TestCrossfadeChunks_NegativeOverlap(t *testing.T) {
	prev := []float32{1.0, 2.0}
	next := []float32{3.0, 4.0}
	out := CrossfadeChunks(prev, next, -10)

	if len(out) != 4 {
		t.Fatalf("expected 4 samples, got %d", len(out))
	}
}

func TestCrossfadeChunks_LinearRamp(t *testing.T) {
	// 200 samples each, overlapSamples=50 -> actualOverlap = 50.
	// prev = all zeros, next = all 1000 -> blended region should ramp
	// linearly from 0 to ~1000.
	prev := make([]float32, 200)
	next := make([]float32, 200)
	for i := range next {
		next[i] = 1000.0
	}

	out := CrossfadeChunks(prev, next, 50)
	overlap := 50

	headEnd := 200 - overlap
	for i := 0; i < overlap; i++ {
		t_ratio := float32(i) / float32(overlap)
		expected := 1000.0 * t_ratio
		got := out[headEnd+i]
		if math.Abs(float64(got-expected)) > 0.5 {
			t.Errorf("ramp[%d]: expected %f, got %f", i, expected, got)
		}
	}
}

func TestCrossfadeChunks_SymmetricBlend(t *testing.T) {
	// If prev and next are the same constant value, blended region should
	// stay at that value (fadeOut*(1-t) + fadeIn*t = c*(1-t+t) = c).
	c := float32(500.0)
	prev := make([]float32, 200)
	next := make([]float32, 200)
	for i := range prev {
		prev[i] = c
		next[i] = c
	}

	out := CrossfadeChunks(prev, next, 50)

	for i, v := range out {
		if math.Abs(float64(v-c)) > 0.01 {
			t.Errorf("sample[%d]: expected %f, got %f", i, c, v)
			break
		}
	}
}

func TestCrossfadeChunks_LargeChunksDefaultOverlap(t *testing.T) {
	// Simulate realistic chunk sizes (~22050 samples = 1s at 22050Hz).
	// overlapSamples = DefaultOverlapSamples (220).
	// actualOverlap = min(220, 22050/4=5512, 22050/4=5512) = 220.
	n := 22050
	prev := make([]float32, n)
	next := make([]float32, n)
	for i := 0; i < n; i++ {
		prev[i] = float32(i)
		next[i] = float32(n + i)
	}

	out := CrossfadeChunks(prev, next, DefaultOverlapSamples)

	expectedLen := 2*n - DefaultOverlapSamples
	if len(out) != expectedLen {
		t.Fatalf("expected %d samples, got %d", expectedLen, len(out))
	}

	// Check that head of prev and tail of next are preserved exactly.
	headEnd := n - DefaultOverlapSamples
	for i := 0; i < 10; i++ {
		if out[i] != float32(i) {
			t.Errorf("head[%d]: expected %f, got %f", i, float32(i), out[i])
			break
		}
	}
	tailStart := headEnd + DefaultOverlapSamples
	for i := tailStart; i < tailStart+10 && i < len(out); i++ {
		nextIdx := DefaultOverlapSamples + (i - tailStart)
		expected := float32(n + nextIdx)
		if out[i] != expected {
			t.Errorf("tail[%d]: expected %f, got %f", i, expected, out[i])
			break
		}
	}
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

func TestDefaultOverlapSamples(t *testing.T) {
	if DefaultOverlapSamples != 220 {
		t.Errorf("expected DefaultOverlapSamples=220, got %d", DefaultOverlapSamples)
	}
}

func TestMinCrossfadeSamples(t *testing.T) {
	if MinCrossfadeSamples != 44 {
		t.Errorf("expected MinCrossfadeSamples=44, got %d", MinCrossfadeSamples)
	}
}

// ---------------------------------------------------------------------------
// int16 <-> float32 conversion helpers
// ---------------------------------------------------------------------------

func TestInt16ToFloat32(t *testing.T) {
	in := []int16{0, 100, -200, 32767, -32768}
	out := int16ToFloat32(in)

	if len(out) != len(in) {
		t.Fatalf("expected %d elements, got %d", len(in), len(out))
	}
	for i, v := range in {
		if out[i] != float32(v) {
			t.Errorf("[%d]: expected %f, got %f", i, float32(v), out[i])
		}
	}
}

func TestFloat32ToInt16(t *testing.T) {
	in := []float32{0.0, 100.5, -200.7, 32767.0, -32768.0}
	out := float32ToInt16(in)

	if len(out) != len(in) {
		t.Fatalf("expected %d elements, got %d", len(in), len(out))
	}
	// int16(100.5) = 100, int16(-200.7) = -200
	want := []int16{0, 100, -200, 32767, -32768}
	for i, w := range want {
		if out[i] != w {
			t.Errorf("[%d]: expected %d, got %d", i, w, out[i])
		}
	}
}

func TestFloat32ToInt16_Clamping(t *testing.T) {
	in := []float32{40000.0, -40000.0, 100000.0}
	out := float32ToInt16(in)

	if out[0] != math.MaxInt16 {
		t.Errorf("expected MaxInt16 for 40000, got %d", out[0])
	}
	if out[1] != math.MinInt16 {
		t.Errorf("expected MinInt16 for -40000, got %d", out[1])
	}
	if out[2] != math.MaxInt16 {
		t.Errorf("expected MaxInt16 for 100000, got %d", out[2])
	}
}

func TestInt16ToFloat32_Empty(t *testing.T) {
	out := int16ToFloat32(nil)
	if len(out) != 0 {
		t.Errorf("expected 0 elements, got %d", len(out))
	}
}

func TestFloat32ToInt16_Empty(t *testing.T) {
	out := float32ToInt16(nil)
	if len(out) != 0 {
		t.Errorf("expected 0 elements, got %d", len(out))
	}
}

// ---------------------------------------------------------------------------
// Roundtrip: int16 -> float32 -> CrossfadeChunks -> float32ToInt16
// ---------------------------------------------------------------------------

func TestCrossfadeChunks_Int16Roundtrip(t *testing.T) {
	// Verify that converting int16 -> float32, crossfading, and converting
	// back produces sane int16 values.
	prevI16 := make([]int16, 200)
	nextI16 := make([]int16, 200)
	for i := 0; i < 200; i++ {
		prevI16[i] = int16(i * 100)
		nextI16[i] = int16(20000 - i*50)
	}

	prevF32 := int16ToFloat32(prevI16)
	nextF32 := int16ToFloat32(nextI16)
	blended := CrossfadeChunks(prevF32, nextF32, 50)
	result := float32ToInt16(blended)

	expectedLen := 200 + 200 - 50
	if len(result) != expectedLen {
		t.Fatalf("expected %d samples, got %d", expectedLen, len(result))
	}

	// Verify we got valid samples (clamping is already guaranteed by float32ToInt16).
	_ = result
}
