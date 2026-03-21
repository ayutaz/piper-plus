package piperplus

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

// JSONLInput represents a single JSONL input line.
type JSONLInput struct {
	// Direct phoneme ID input
	PhonemeIDs      []int64    `json:"phoneme_ids,omitempty"`
	ProsodyFeatures [][3]int64 `json:"prosody_features,omitempty"`

	// Text input (requires phonemizer)
	Text     string `json:"text,omitempty"`
	Language string `json:"language,omitempty"`

	// Shared options
	SpeakerID  *int64 `json:"speaker_id,omitempty"`
	LanguageID *int64 `json:"language_id,omitempty"`
	OutputFile string `json:"output_file,omitempty"`
}

// ParseJSONLLine parses a single JSONL line.
// Returns an error for invalid JSON or when neither phoneme_ids nor text is set.
func ParseJSONLLine(line []byte) (*JSONLInput, error) {
	var input JSONLInput
	if err := json.Unmarshal(line, &input); err != nil {
		return nil, fmt.Errorf("piperplus: invalid JSON: %w", err)
	}
	if len(input.PhonemeIDs) == 0 && input.Text == "" {
		return nil, fmt.Errorf("piperplus: JSONL line must contain phoneme_ids or text")
	}
	for i, id := range input.PhonemeIDs {
		if id < 0 {
			return nil, fmt.Errorf("piperplus: negative phoneme_id at index %d: %d", i, id)
		}
	}
	return &input, nil
}

// ReadJSONL reads JSONL from an io.Reader, returning channels for parsed inputs
// and errors. Both channels are closed when the reader is exhausted or ctx is
// canceled. Empty lines and lines starting with "//" are skipped.
//
// By default, the first parse error stops processing. Use ContinueOnError to
// send errors on errCh and keep reading subsequent lines instead.
func ReadJSONL(ctx context.Context, r io.Reader, opts ...JSONLOption) (<-chan *JSONLInput, <-chan error) {
	cfg := jsonlConfig{}
	for _, o := range opts {
		o(&cfg)
	}

	inputCh := make(chan *JSONLInput)
	errCh := make(chan error, 64)

	go func() {
		defer close(inputCh)
		defer close(errCh)

		scanner := bufio.NewScanner(r)
		scanner.Buffer(make([]byte, 0, 64*1024), 1*1024*1024) // max 1 MB per line
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" || strings.HasPrefix(line, "//") {
				continue
			}

			input, err := ParseJSONLLine([]byte(line))
			if err != nil {
				if cfg.continueOnError {
					select {
					case errCh <- err:
					case <-ctx.Done():
						return
					}
					continue
				}
				select {
				case errCh <- err:
				case <-ctx.Done():
					return
				}
				return
			}

			select {
			case inputCh <- input:
			case <-ctx.Done():
				return
			}
		}

		if err := scanner.Err(); err != nil {
			select {
			case errCh <- fmt.Errorf("piperplus: read error: %w", err):
			case <-ctx.Done():
			}
		}
	}()

	return inputCh, errCh
}

// jsonlConfig holds configuration for ReadJSONL.
type jsonlConfig struct {
	continueOnError bool
}

// JSONLOption configures ReadJSONL behavior.
type JSONLOption func(*jsonlConfig)

// ContinueOnError makes ReadJSONL skip lines that fail to parse instead of
// stopping. Parse errors are still sent on the error channel.
func ContinueOnError() JSONLOption {
	return func(c *jsonlConfig) {
		c.continueOnError = true
	}
}

// ToSynthesisRequest converts JSONLInput to a SynthesisRequest.
// Returns nil if the input uses text mode (needs phonemization first).
// Fields not set on the JSONLInput fall back to the provided defaults.
func (j *JSONLInput) ToSynthesisRequest(defaults SynthesisOptions) *SynthesisRequest {
	if len(j.PhonemeIDs) == 0 {
		return nil
	}

	req := &SynthesisRequest{
		PhonemeIDs:      j.PhonemeIDs,
		SpeakerID:       defaults.SpeakerID,
		NoiseScale:      defaults.NoiseScale,
		LengthScale:     defaults.LengthScale,
		NoiseW:          defaults.NoiseW,
		ProsodyFeatures: j.ProsodyFeatures,
	}

	if j.SpeakerID != nil {
		req.SpeakerID = *j.SpeakerID
	}
	if j.LanguageID != nil {
		req.LanguageID = *j.LanguageID
	}

	return req
}
