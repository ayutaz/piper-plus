package piperplus

import (
	"bytes"
	"encoding/binary"
	"io"
	"math"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// peakNormalize
// ---------------------------------------------------------------------------

func TestPeakNormalize_BasicScaling(t *testing.T) {
	in := []float32{0.5, -0.5, 0.25}
	out := peakNormalize(in)

	if len(out) != len(in) {
		t.Fatalf("expected %d samples, got %d", len(in), len(out))
	}

	// Peak is 0.5 → scale = 32767 / 0.5 = 65534.
	// 0.5  * 65534 = 32767
	// -0.5 * 65534 = -32767
	// 0.25 * 65534 = 16383 (truncated)
	wantApprox := []int16{32767, -32767, 16383}
	for i, want := range wantApprox {
		if diff := int(out[i]) - int(want); diff < -1 || diff > 1 {
			t.Errorf("sample[%d]: want ~%d, got %d", i, want, out[i])
		}
	}
}

func TestPeakNormalize_FullScale(t *testing.T) {
	in := []float32{1.0, -1.0}
	out := peakNormalize(in)

	if out[0] != 32767 {
		t.Errorf("expected 32767, got %d", out[0])
	}
	if out[1] != -32767 {
		t.Errorf("expected -32767, got %d", out[1])
	}
}

func TestPeakNormalize_Silence(t *testing.T) {
	in := []float32{0.0, 0.0, 0.0}
	out := peakNormalize(in)

	for i, s := range out {
		if s != 0 {
			t.Errorf("sample[%d]: expected 0, got %d", i, s)
		}
	}
}

func TestPeakNormalize_SmallValues(t *testing.T) {
	// Peak 0.001 < 0.01 → clamped to 0.01.
	// scale = 32767 / 0.01 = 3276700.
	// 0.001 * 3276700 ≈ 3276 (clamped within int16 range).
	in := []float32{0.001, -0.001}
	out := peakNormalize(in)

	if len(out) != 2 {
		t.Fatalf("expected 2 samples, got %d", len(out))
	}
	// Should not panic or produce extreme values.
	// Note: out is []int16, so values are inherently within [-32768, 32767].
	// Verify no clipping to extremes occurred.
	for i, s := range out {
		if int(s) < -32767 || int(s) > 32767 {
			t.Errorf("sample[%d] out of expected range: %d", i, s)
		}
	}
	// Verify nonzero output (scale was clamped, not zero-divided).
	if out[0] == 0 {
		t.Error("expected nonzero output for 0.001 input")
	}
}

func TestPeakNormalize_Empty(t *testing.T) {
	out := peakNormalize([]float32{})
	if len(out) != 0 {
		t.Fatalf("expected empty output, got %d samples", len(out))
	}
}

// ---------------------------------------------------------------------------
// writeWAVHeader
// ---------------------------------------------------------------------------

func TestWriteWAVHeader(t *testing.T) {
	var buf bytes.Buffer
	sampleRate := 22050
	numSamples := 100

	if err := writeWAVHeader(&buf, sampleRate, numSamples); err != nil {
		t.Fatalf("writeWAVHeader error: %v", err)
	}

	b := buf.Bytes()
	if len(b) != 44 {
		t.Fatalf("expected 44 header bytes, got %d", len(b))
	}

	// RIFF tag.
	if tag := string(b[0:4]); tag != "RIFF" {
		t.Errorf("bytes 0-3: expected RIFF, got %q", tag)
	}

	// WAVE tag.
	if tag := string(b[8:12]); tag != "WAVE" {
		t.Errorf("bytes 8-11: expected WAVE, got %q", tag)
	}

	// fmt  tag.
	if tag := string(b[12:16]); tag != "fmt " {
		t.Errorf("bytes 12-15: expected 'fmt ', got %q", tag)
	}

	// Audio format = 1 (PCM).
	if v := binary.LittleEndian.Uint16(b[20:22]); v != 1 {
		t.Errorf("audio format: expected 1, got %d", v)
	}

	// Channels = 1 (mono).
	if v := binary.LittleEndian.Uint16(b[22:24]); v != 1 {
		t.Errorf("channels: expected 1, got %d", v)
	}

	// Sample rate.
	if v := binary.LittleEndian.Uint32(b[24:28]); v != uint32(sampleRate) {
		t.Errorf("sample rate: expected %d, got %d", sampleRate, v)
	}

	// Bits per sample = 16.
	if v := binary.LittleEndian.Uint16(b[34:36]); v != 16 {
		t.Errorf("bits per sample: expected 16, got %d", v)
	}

	// data tag.
	if tag := string(b[36:40]); tag != "data" {
		t.Errorf("bytes 36-39: expected 'data', got %q", tag)
	}

	// data chunk size = numSamples * 2.
	if v := binary.LittleEndian.Uint32(b[40:44]); v != uint32(numSamples*2) {
		t.Errorf("data size: expected %d, got %d", numSamples*2, v)
	}
}

// ---------------------------------------------------------------------------
// pcmToBytes
// ---------------------------------------------------------------------------

func TestPcmToBytes(t *testing.T) {
	in := []int16{1, -1, 32767}
	out := pcmToBytes(in)

	if len(out) != 6 {
		t.Fatalf("expected 6 bytes, got %d", len(out))
	}

	// Verify little-endian encoding for each sample.
	for i, s := range in {
		got := binary.LittleEndian.Uint16(out[i*2 : i*2+2])
		if got != uint16(s) {
			t.Errorf("sample[%d]: expected %d, got %d", i, uint16(s), got)
		}
	}
}

// ---------------------------------------------------------------------------
// SynthesisResult.WriteTo
// ---------------------------------------------------------------------------

func TestSynthesisResult_WriteTo(t *testing.T) {
	audio := []int16{100, -200, 300}
	r := &SynthesisResult{
		Audio:      audio,
		SampleRate: 22050,
		Duration:   1 * time.Second,
		InferTime:  100 * time.Millisecond,
	}

	var buf bytes.Buffer
	n, err := r.WriteTo(&buf)
	if err != nil {
		t.Fatalf("WriteTo error: %v", err)
	}

	expectedSize := int64(44 + len(audio)*2)
	if n != expectedSize {
		t.Errorf("expected %d bytes written, got %d", expectedSize, n)
	}
	if int64(buf.Len()) != expectedSize {
		t.Errorf("buffer length: expected %d, got %d", expectedSize, buf.Len())
	}

	// Starts with RIFF.
	if tag := string(buf.Bytes()[0:4]); tag != "RIFF" {
		t.Errorf("expected RIFF header, got %q", tag)
	}

	// Verify io.WriterTo interface at compile time.
	var _ io.WriterTo = r
}

// ---------------------------------------------------------------------------
// SynthesisResult.RTF
// ---------------------------------------------------------------------------

func TestSynthesisResult_RTF(t *testing.T) {
	r := &SynthesisResult{
		Duration:  1 * time.Second,
		InferTime: 100 * time.Millisecond,
	}

	rtf := r.RTF()
	if math.Abs(rtf-0.1) > 1e-9 {
		t.Errorf("expected RTF ~0.1, got %f", rtf)
	}
}

func TestSynthesisResult_RTF_ZeroDuration(t *testing.T) {
	r := &SynthesisResult{
		Duration:  0,
		InferTime: 100 * time.Millisecond,
	}

	// Must not panic.
	rtf := r.RTF()
	if rtf != 0 {
		t.Errorf("expected RTF 0 for zero duration, got %f", rtf)
	}
}

// ---------------------------------------------------------------------------
// SynthesisResult.AudioFloat32
// ---------------------------------------------------------------------------

func TestSynthesisResult_AudioFloat32(t *testing.T) {
	r := &SynthesisResult{
		Audio: []int16{32767, -32767, 0},
	}

	out := r.AudioFloat32()
	if len(out) != 3 {
		t.Fatalf("expected 3 samples, got %d", len(out))
	}

	const tol = 1e-4
	want := []float32{1.0, -1.0, 0.0}
	for i, w := range want {
		if diff := math.Abs(float64(out[i]) - float64(w)); diff > tol {
			t.Errorf("sample[%d]: expected ~%f, got %f", i, w, out[i])
		}
	}
}

// ---------------------------------------------------------------------------
// SynthesisResult.RawPCMReader
// ---------------------------------------------------------------------------

func TestSynthesisResult_RawPCMReader(t *testing.T) {
	audio := []int16{100, -200, 300}
	r := &SynthesisResult{
		Audio:      audio,
		SampleRate: 22050,
	}

	reader := r.RawPCMReader()
	data, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("ReadAll error: %v", err)
	}

	// Should be raw PCM bytes, no WAV header.
	expectedLen := len(audio) * 2
	if len(data) != expectedLen {
		t.Fatalf("expected %d bytes, got %d", expectedLen, len(data))
	}

	// Must NOT start with "RIFF".
	if len(data) >= 4 && string(data[0:4]) == "RIFF" {
		t.Error("RawPCMReader output should not contain a WAV header")
	}

	// Verify sample values.
	for i, s := range audio {
		got := int16(binary.LittleEndian.Uint16(data[i*2 : i*2+2]))
		if got != s {
			t.Errorf("sample[%d]: expected %d, got %d", i, s, got)
		}
	}
}
