package piperplus

import (
	"bytes"
	"encoding/binary"
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
