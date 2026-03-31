package piperplus

import (
	"bytes"
	"encoding/binary"
	"io"
	"math"
	"time"
)

// SynthesisResult holds the output of a TTS synthesis operation.
type SynthesisResult struct {
	Audio      []int16       // PCM samples (mono, 16-bit)
	SampleRate int           // e.g., 22050
	Duration   time.Duration // audio duration
	InferTime  time.Duration // wall-clock inference time
	Durations  []float32     // per-phoneme durations in frames (nil if not available)
}

// WriteTo writes the synthesis result as a WAV file to w.
// It implements [io.WriterTo].
func (r *SynthesisResult) WriteTo(w io.Writer) (int64, error) {
	var buf bytes.Buffer

	if err := writeWAVHeader(&buf, r.SampleRate, len(r.Audio)); err != nil {
		return 0, err
	}

	pcm := pcmToBytes(r.Audio)
	buf.Write(pcm)

	n, err := w.Write(buf.Bytes())
	if err == nil && n < buf.Len() {
		return int64(n), io.ErrShortWrite
	}
	return int64(n), err
}

// WriteWAV writes the synthesis result as a WAV file to w.
// It is a convenience wrapper around [SynthesisResult.WriteTo].
func (r *SynthesisResult) WriteWAV(w io.Writer) error {
	_, err := r.WriteTo(w)
	return err
}

// RawPCMReader returns an [io.Reader] over the raw PCM bytes (little-endian
// int16) without a WAV header.
func (r *SynthesisResult) RawPCMReader() io.Reader {
	return bytes.NewReader(pcmToBytes(r.Audio))
}

// RTF returns the Real-Time Factor (InferTime / Duration).
// A value less than 1.0 means faster than real-time.
// Returns 0 if Duration is zero.
func (r *SynthesisResult) RTF() float64 {
	if r.Duration == 0 {
		return 0
	}
	return float64(r.InferTime) / float64(r.Duration)
}

// AudioFloat32 converts the int16 PCM samples back to float32 values in the
// range [-1.0, 1.0].
func (r *SynthesisResult) AudioFloat32() []float32 {
	out := make([]float32, len(r.Audio))
	for i, s := range r.Audio {
		out[i] = float32(s) / math.MaxInt16
	}
	return out
}

// peakNormalize scales float32 audio samples to int16 range using peak
// normalization. The peak amplitude is mapped to 32767; samples are clamped
// to [-32767, 32767].
func peakNormalize(audioFloat []float32) []int16 {
	// Find peak amplitude, skipping NaN/Inf values.
	var peak float64
	for _, s := range audioFloat {
		v := float64(s)
		if math.IsNaN(v) || math.IsInf(v, 0) {
			continue
		}
		if a := math.Abs(v); a > peak {
			peak = a
		}
	}

	scale := float64(math.MaxInt16) / math.Max(0.01, peak)

	out := make([]int16, len(audioFloat))
	for i, s := range audioFloat {
		v := float64(s) * scale
		// Clamp to int16 range [MinInt16, MaxInt16].
		if v > math.MaxInt16 {
			v = math.MaxInt16
		} else if v < math.MinInt16 {
			v = math.MinInt16
		}
		out[i] = int16(v)
	}
	return out
}

// writeWAVHeader writes a 44-byte RIFF WAV header for PCM 16-bit mono audio.
func writeWAVHeader(w io.Writer, sampleRate, numSamples int) error {
	const (
		channels       = 1
		bytesPerSample = 2 // 16-bit
	)
	dataSize := uint32(numSamples * bytesPerSample)
	fileSize := uint32(36 + numSamples*bytesPerSample) // 36 = header size (44) minus RIFF chunk prefix (8)
	// byteRate = sampleRate * channels * bytesPerSample
	byteRate := uint32(sampleRate * channels * bytesPerSample)

	// RIFF chunk descriptor.
	if _, err := w.Write([]byte("RIFF")); err != nil {
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, fileSize); err != nil {
		return err
	}
	if _, err := w.Write([]byte("WAVE")); err != nil {
		return err
	}

	// fmt sub-chunk.
	if _, err := w.Write([]byte("fmt ")); err != nil {
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint32(16)); err != nil { // chunk size
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint16(1)); err != nil { // PCM format
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint16(channels)); err != nil { // mono
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint32(sampleRate)); err != nil {
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, byteRate); err != nil { // sampleRate * channels * bytesPerSample
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint16(channels*bytesPerSample)); err != nil { // block align = channels * bytesPerSample
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, uint16(bytesPerSample*8)); err != nil { // bits per sample = bytesPerSample * 8
		return err
	}

	// data sub-chunk.
	if _, err := w.Write([]byte("data")); err != nil {
		return err
	}
	if err := binary.Write(w, binary.LittleEndian, dataSize); err != nil {
		return err
	}

	return nil
}

// pcmToBytes converts a slice of int16 PCM samples to a little-endian byte
// slice.
func pcmToBytes(samples []int16) []byte {
	buf := make([]byte, len(samples)*2)
	for i, s := range samples {
		binary.LittleEndian.PutUint16(buf[i*2:], uint16(s))
	}
	return buf
}
