package piperplus

import (
	"context"
	"fmt"
	"io"
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

	so := applySynthesisOptions(opts)
	sentenceSilence := so.SentenceSilence

	for i, sentence := range sentences {
		if err := ctx.Err(); err != nil {
			return err
		}

		result, err := v.Synthesize(ctx, sentence, opts...)
		if err != nil {
			return fmt.Errorf("piperplus: streaming synthesis failed on sentence %d: %w", i, err)
		}

		if err := sink.WriteAudio(result.Audio, result.SampleRate); err != nil {
			return fmt.Errorf("piperplus: sink write failed: %w", err)
		}

		// Insert silence between sentences (not after the last one).
		if i < len(sentences)-1 && sentenceSilence > 0 && result.SampleRate > 0 {
			silenceSamples := int(sentenceSilence * float64(result.SampleRate))
			if err := sink.WriteAudio(make([]int16, silenceSamples), result.SampleRate); err != nil {
				return fmt.Errorf("piperplus: sink write failed: %w", err)
			}
		}
	}

	return sink.Close()
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
		out[offset+i] = int16(p + n)
	}

	// Copy the non-overlapping tail of next.
	copy(out[offset+overlapSamples:], next[overlapSamples:])

	return out
}

// Ensure WriterAudioSink satisfies AudioSink at compile time.
var _ AudioSink = (*WriterAudioSink)(nil)
