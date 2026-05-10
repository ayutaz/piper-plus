package piperplus

import (
	"bytes"
	"encoding/binary"
	"errors"
	"testing"
)

// ---------------------------------------------------------------------------
// WriterAudioSink.WriteAudio
// ---------------------------------------------------------------------------

func TestWriterAudioSink_WriteAudio(t *testing.T) {
	var buf bytes.Buffer
	sink := NewWriterAudioSink(&buf)

	samples := []int16{100, -200, 32767}
	if err := sink.WriteAudio(samples, 22050); err != nil {
		t.Fatalf("WriteAudio returned unexpected error: %v", err)
	}

	data := buf.Bytes()
	if len(data) != len(samples)*2 {
		t.Fatalf("expected %d bytes, got %d", len(samples)*2, len(data))
	}

	for i, s := range samples {
		got := int16(binary.LittleEndian.Uint16(data[i*2 : i*2+2]))
		if got != s {
			t.Errorf("sample[%d]: expected %d, got %d", i, s, got)
		}
	}

	// Close should be a no-op and return nil.
	if err := sink.Close(); err != nil {
		t.Errorf("Close returned unexpected error: %v", err)
	}
}

// errWriter is an io.Writer that always fails. Used to test the failing-Write
// branch in WriterAudioSink.WriteAudio.
type errWriter struct{}

var errWriterFailed = errors.New("write failed")

func (errWriter) Write(p []byte) (int, error) {
	return 0, errWriterFailed
}

// TestWriterAudioSink_WriteFailurePropagated verifies that a failing
// underlying writer's error is returned as-is by WriteAudio (not wrapped or
// silently swallowed). This pins the contract used by SynthesizeStream
// callers who classify sink failures.
func TestWriterAudioSink_WriteFailurePropagated(t *testing.T) {
	sink := NewWriterAudioSink(errWriter{})
	err := sink.WriteAudio([]int16{1, 2, 3}, 22050)
	if err == nil {
		t.Fatal("expected error from failing writer, got nil")
	}
	if !errors.Is(err, errWriterFailed) {
		t.Errorf("expected errors.Is(err, errWriterFailed), got %v", err)
	}
}

// TestWriterAudioSink_EmptySamples verifies WriteAudio handles a zero-length
// sample slice without erroring (no-op write).
func TestWriterAudioSink_EmptySamples(t *testing.T) {
	var buf bytes.Buffer
	sink := NewWriterAudioSink(&buf)
	if err := sink.WriteAudio(nil, 22050); err != nil {
		t.Errorf("WriteAudio with nil samples returned error: %v", err)
	}
	if err := sink.WriteAudio([]int16{}, 22050); err != nil {
		t.Errorf("WriteAudio with empty samples returned error: %v", err)
	}
	if buf.Len() != 0 {
		t.Errorf("expected 0 bytes written, got %d", buf.Len())
	}
}

// ---------------------------------------------------------------------------
// crossfade
// ---------------------------------------------------------------------------

func TestCrossfade_Basic(t *testing.T) {
	prev := []int16{100, 200, 300, 400}
	next := []int16{1000, 2000, 3000, 4000}
	overlap := 2

	out := crossfade(prev, next, overlap)

	// Expected length: 4 + 4 - 2 = 6.
	if len(out) != 6 {
		t.Fatalf("expected 6 samples, got %d", len(out))
	}

	// Non-overlapping head of prev: [100, 200].
	if out[0] != 100 || out[1] != 200 {
		t.Errorf("head: expected [100, 200], got [%d, %d]", out[0], out[1])
	}

	// Overlap region (indices 2-3):
	// i=0: ratio=0.0 -> prev[2]*1.0 + next[0]*0.0 = 300
	// i=1: ratio=0.5 -> prev[3]*0.5 + next[1]*0.5 = 200+1000 = 1200
	if out[2] != 300 {
		t.Errorf("overlap[0]: expected 300, got %d", out[2])
	}
	if out[3] != 1200 {
		t.Errorf("overlap[1]: expected 1200, got %d", out[3])
	}

	// Non-overlapping tail of next: [3000, 4000].
	if out[4] != 3000 || out[5] != 4000 {
		t.Errorf("tail: expected [3000, 4000], got [%d, %d]", out[4], out[5])
	}
}

func TestCrossfade_ZeroOverlap(t *testing.T) {
	prev := []int16{10, 20}
	next := []int16{30, 40}

	out := crossfade(prev, next, 0)

	if len(out) != 4 {
		t.Fatalf("expected 4 samples, got %d", len(out))
	}

	want := []int16{10, 20, 30, 40}
	for i, w := range want {
		if out[i] != w {
			t.Errorf("sample[%d]: expected %d, got %d", i, w, out[i])
		}
	}
}

func TestCrossfade_Empty(t *testing.T) {
	// Both empty: should not panic.
	out := crossfade(nil, nil, 0)
	if len(out) != 0 {
		t.Errorf("expected 0 samples, got %d", len(out))
	}

	// One empty, one non-empty.
	out = crossfade([]int16{1, 2}, nil, 0)
	if len(out) != 2 {
		t.Errorf("expected 2 samples, got %d", len(out))
	}

	out = crossfade(nil, []int16{3, 4}, 0)
	if len(out) != 2 {
		t.Errorf("expected 2 samples, got %d", len(out))
	}
}

// TestCrossfade_OverlapExceedsChunkSize pins the safety check at
// streaming.go:165 — when overlapSamples > len(prev) or > len(next), the
// function falls back to direct concatenation instead of slicing past array
// bounds. Without this guard a malformed call would panic with "slice bounds
// out of range".
func TestCrossfade_OverlapExceedsChunkSize(t *testing.T) {
	prev := []int16{10, 20}
	next := []int16{30, 40, 50}

	// overlap=5 > len(prev)=2 → direct concatenation.
	out := crossfade(prev, next, 5)
	want := []int16{10, 20, 30, 40, 50}
	if len(out) != len(want) {
		t.Fatalf("expected %d samples, got %d", len(want), len(out))
	}
	for i, w := range want {
		if out[i] != w {
			t.Errorf("sample[%d]: expected %d, got %d", i, w, out[i])
		}
	}
}

// TestCrossfade_OverlapEqualToShorterChunk exercises the boundary
// overlap == len(prev). This is the largest valid overlap for prev — the
// crossfade should consume the entire prev buffer in the blend.
func TestCrossfade_OverlapEqualToShorterChunk(t *testing.T) {
	prev := []int16{100, 200}
	next := []int16{1000, 2000, 3000, 4000}
	// overlap == len(prev) == 2 → valid path.
	out := crossfade(prev, next, 2)

	// Expected length: 2 + 4 - 2 = 4.
	if len(out) != 4 {
		t.Fatalf("expected 4 samples, got %d", len(out))
	}
	// At i=0: ratio=0.0 → 100*1.0 + 1000*0.0 = 100
	// At i=1: ratio=0.5 → 200*0.5 + 2000*0.5 = 1100
	if out[0] != 100 {
		t.Errorf("blend[0]: expected 100, got %d", out[0])
	}
	if out[1] != 1100 {
		t.Errorf("blend[1]: expected 1100, got %d", out[1])
	}
	// Tail of next: [3000, 4000].
	if out[2] != 3000 || out[3] != 4000 {
		t.Errorf("tail: expected [3000, 4000], got [%d, %d]", out[2], out[3])
	}
}

// TestCrossfade_ExtremeValuesClamped verifies the overflow guard at
// streaming.go:187-191. Without clamping, sum of two MaxInt16-magnitude
// values would overflow when cast to int16, producing wraparound noise.
func TestCrossfade_ExtremeValuesClamped(t *testing.T) {
	// Use 4 samples on each side with overlap=2. Both buffers contain MaxInt16
	// throughout — when ratio=0.5 the blend is 32767 → clamps to MaxInt16.
	maxv := int16(32767)
	prev := []int16{maxv, maxv, maxv, maxv}
	next := []int16{maxv, maxv, maxv, maxv}
	out := crossfade(prev, next, 2)

	// Blended region should still be at MaxInt16 (no overflow wraparound).
	for i, v := range out {
		if v != maxv {
			t.Errorf("sample[%d]: expected MaxInt16=%d, got %d", i, maxv, v)
		}
	}
}
