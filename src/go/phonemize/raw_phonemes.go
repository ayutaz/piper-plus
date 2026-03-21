package phonemize

import (
	"errors"
	"strings"
)

// ErrEmptyInput is returned when raw phoneme input is empty.
var ErrEmptyInput = errors.New("phonemize: empty input")

// ParseRawPhonemes splits a space-separated phoneme string into individual tokens.
func ParseRawPhonemes(input string) ([]string, error) {
	tokens := strings.Fields(input)
	if len(tokens) == 0 {
		return nil, ErrEmptyInput
	}
	return tokens, nil
}
