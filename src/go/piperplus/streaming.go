package piperplus

import (
	"context"
	"fmt"
	"io"
	"math"
)

// AudioSink receives audio chunks during streaming synthesis.
type AudioSink interface {
	// WriteAudio receives a chunk of PCM int16 audio samples.
	WriteAudio(samples []int16, sampleRate int) error
	// Close signals no more audio will be written.
	Close() error
}

// WriterAudioSink wraps an io.Writer to implement AudioSink.
// Writes raw PCM int16 little-endian bytes.
type WriterAudioSink struct {
	w io.Writer
}

// NewWriterAudioSink creates a WriterAudioSink that writes raw PCM int16
// little-endian bytes to w.
func NewWriterAudioSink(w io.Writer) *WriterAudioSink {
	return &WriterAudioSink{w: w}
}

// WriteAudio writes PCM int16 samples as little-endian bytes to the underlying
// writer.
func (s *WriterAudioSink) WriteAudio(samples []int16, sampleRate int) error {
	buf := pcmToBytes(samples)
	_, err := s.w.Write(buf)
	return err
}

// Close is a no-op for WriterAudioSink.
func (s *WriterAudioSink) Close() error {
	return nil
}

// SynthesizeStream synthesizes long text by splitting into sentences,
// synthesizing each, and writing audio chunks to the sink. Silence of
// SentenceSilence seconds (default 0.2) is inserted between sentences.
// Adjacent sentence chunks are crossfaded using CrossfadeChunks to reduce
// click/pop artifacts at boundaries.
func (v *Voice) SynthesizeStream(
	ctx context.Context,
	text string,
	sink AudioSink,
	opts ...SynthesisOption,
) error {
	if v.phonemizer == nil {
		return fmt.Errorf("piperplus: phonemizer not configured; use SynthesizeFromIDs for direct phoneme input")
	}

	sentences := SplitSentences(text)
	if len(sentences) == 0 {
		return sink.Close()
	}

	// Ensure sink is always closed, even on error paths.
	var synthErr error
	defer func() {
		closeErr := sink.Close()
		if synthErr == nil {
			synthErr = closeErr
		}
	}()

	so := applySynthesisOptions(opts)
	sentenceSilence := so.SentenceSilence

	var prevChunkF32 []float32

	for i, sentence := range sentences {
		if err := ctx.Err(); err != nil {
			synthErr = err
			return synthErr
		}

		result, err := v.Synthesize(ctx, sentence, opts...)
		if err != nil {
			synthErr = fmt.Errorf("piperplus: streaming synthesis failed on sentence %d: %w", i, err)
			return synthErr
		}

		curChunkF32 := int16ToFloat32(result.Audio)

		if len(prevChunkF32) > 0 && len(curChunkF32) > 0 {
			// Crossfade with previous chunk to reduce boundary artifacts.
			blended := CrossfadeChunks(prevChunkF32, curChunkF32, DefaultOverlapSamples)
			if err := sink.WriteAudio(float32ToInt16(blended), result.SampleRate); err != nil {
				synthErr = fmt.Errorf("piperplus: sink write failed: %w", err)
				return synthErr
			}
			// After writing the blended result, there is no separate
			// "previous chunk" to carry forward (the blend already consumed
			// both). Reset so the next iteration starts fresh.
			prevChunkF32 = nil
		} else {
			// First chunk or empty current chunk -- write prev if pending,
			// then hold current for next iteration's crossfade.
			if len(prevChunkF32) > 0 {
				if err := sink.WriteAudio(float32ToInt16(prevChunkF32), result.SampleRate); err != nil {
					synthErr = fmt.Errorf("piperplus: sink write failed: %w", err)
					return synthErr
				}
			}
			prevChunkF32 = curChunkF32
		}

		// Insert silence between sentences (not after the last one).
		if i < len(sentences)-1 && sentenceSilence > 0 && result.SampleRate > 0 {
			silenceSamples := int(sentenceSilence * float64(result.SampleRate))
			if err := sink.WriteAudio(make([]int16, silenceSamples), result.SampleRate); err != nil {
				synthErr = fmt.Errorf("piperplus: sink write failed: %w", err)
				return synthErr
			}
		}
	}

	// Flush any remaining buffered chunk.
	if len(prevChunkF32) > 0 {
		if err := sink.WriteAudio(float32ToInt16(prevChunkF32), 22050); err != nil {
			synthErr = fmt.Errorf("piperplus: sink write failed: %w", err)
			return synthErr
		}
	}

	return synthErr
}

// int16ToFloat32 converts PCM int16 samples to float32.
func int16ToFloat32(s []int16) []float32 {
	out := make([]float32, len(s))
	for i, v := range s {
		out[i] = float32(v)
	}
	return out
}

// float32ToInt16 converts float32 samples back to PCM int16, clamping values
// that exceed the int16 range.
func float32ToInt16(s []float32) []int16 {
	out := make([]int16, len(s))
	for i, v := range s {
		switch {
		case v > math.MaxInt16:
			out[i] = math.MaxInt16
		case v < math.MinInt16:
			out[i] = math.MinInt16
		default:
			out[i] = int16(v)
		}
	}
	return out
}

// crossfade blends the end of prev with the start of next over overlapSamples
// using a linear crossfade. The returned slice has length
// len(prev) + len(next) - overlapSamples.
func crossfade(prev, next []int16, overlapSamples int) []int16 {
	if overlapSamples <= 0 || overlapSamples > len(prev) || overlapSamples > len(next) {
		// No valid overlap; concatenate directly.
		out := make([]int16, len(prev)+len(next))
		copy(out, prev)
		copy(out[len(prev):], next)
		return out
	}

	outLen := len(prev) + len(next) - overlapSamples
	out := make([]int16, outLen)

	// Copy the non-overlapping head of prev.
	copy(out, prev[:len(prev)-overlapSamples])

	// Blend the overlapping region.
	offset := len(prev) - overlapSamples
	for i := 0; i < overlapSamples; i++ {
		ratio := float64(i) / float64(overlapSamples)
		p := float64(prev[len(prev)-overlapSamples+i]) * (1 - ratio)
		n := float64(next[i]) * ratio
		// Clamp to [MinInt16, MaxInt16] to prevent integer overflow.
		sum := p + n
		if sum > math.MaxInt16 {
			sum = math.MaxInt16
		} else if sum < math.MinInt16 {
			sum = math.MinInt16
		}
		out[offset+i] = int16(sum)
	}

	// Copy the non-overlapping tail of next.
	copy(out[offset+overlapSamples:], next[overlapSamples:])

	return out
}

// DefaultOverlapSamples is the default number of samples used for crossfade
// between audio chunks (10 ms at 22050 Hz).
const DefaultOverlapSamples = 220

// MinCrossfadeSamples is the minimum overlap required to apply crossfade.
// Below this threshold (~2 ms at 22050 Hz) crossfade is skipped and chunks
// are simply concatenated.
const MinCrossfadeSamples = 44

// CrossfadeChunks blends the end of prev with the start of next using a
// linear crossfade over overlapSamples. The algorithm matches the C++
// crossfadeAudioChunks() in piper.cpp:
//
//  1. actualOverlap = min(overlapSamples, len(prev)/4, len(next)/4)
//  2. If actualOverlap < 44 (< ~2 ms): skip crossfade, concatenate.
//  3. Fade-out prev tail by (1 - t), fade-in next head by t, blend.
//  4. Return prev[:end-overlap] ++ blended ++ next[overlap:].
//
// The returned slice has length len(prev) + len(next) - actualOverlap when
// crossfade is applied, or len(prev) + len(next) when skipped.
func CrossfadeChunks(prev, next []float32, overlapSamples int) []float32 {
	if len(prev) == 0 || len(next) == 0 || overlapSamples <= 0 {
		out := make([]float32, len(prev)+len(next))
		copy(out, prev)
		copy(out[len(prev):], next)
		return out
	}

	// Cap overlap to at most 1/4 of each chunk.
	actualOverlap := overlapSamples
	if q := len(prev) / 4; q < actualOverlap {
		actualOverlap = q
	}
	if q := len(next) / 4; q < actualOverlap {
		actualOverlap = q
	}

	// If the overlap is too small to be audible, just concatenate.
	if actualOverlap < MinCrossfadeSamples {
		out := make([]float32, len(prev)+len(next))
		copy(out, prev)
		copy(out[len(prev):], next)
		return out
	}

	outLen := len(prev) + len(next) - actualOverlap
	out := make([]float32, outLen)

	// Non-overlapping head of prev.
	headEnd := len(prev) - actualOverlap
	copy(out, prev[:headEnd])

	// Blended region.
	for i := 0; i < actualOverlap; i++ {
		t := float32(i) / float32(actualOverlap)
		fadeOut := prev[headEnd+i] * (1 - t)
		fadeIn := next[i] * t
		out[headEnd+i] = fadeOut + fadeIn
	}

	// Non-overlapping tail of next.
	copy(out[headEnd+actualOverlap:], next[actualOverlap:])

	return out
}

// Ensure WriterAudioSink satisfies AudioSink at compile time.
var _ AudioSink = (*WriterAudioSink)(nil)
