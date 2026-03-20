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
	return &input, nil
}

// ReadJSONL reads JSONL from an io.Reader, returning channels for parsed inputs
// and errors. Both channels are closed when the reader is exhausted or ctx is
// cancelled. Empty lines and lines starting with "//" are skipped.
func ReadJSONL(ctx context.Context, r io.Reader) (<-chan *JSONLInput, <-chan error) {
	inputCh := make(chan *JSONLInput)
	errCh := make(chan error, 1)

	go func() {
		defer close(inputCh)
		defer close(errCh)

		scanner := bufio.NewScanner(r)
		for scanner.Scan() {
			line := strings.TrimSpace(scanner.Text())
			if line == "" || strings.HasPrefix(line, "//") {
				continue
			}

			input, err := ParseJSONLLine([]byte(line))
			if err != nil {
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
