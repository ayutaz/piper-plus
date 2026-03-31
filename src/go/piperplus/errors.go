package piperplus

import (
	"errors"
	"fmt"
)

// Compile-time interface checks — ensure all error types satisfy the error interface.
var (
	_ error = (*ModelLoadError)(nil)
	_ error = (*ConfigError)(nil)
	_ error = (*InferenceError)(nil)
	_ error = (*PhonemeError)(nil)
	_ error = (*PhonemeIDNotFoundError)(nil)
)

// Sentinel errors.
var (
	ErrModelClosed     = errors.New("piperplus: voice is closed")
	ErrEmptyText       = errors.New("piperplus: empty text")
	ErrEmptyPhonemeIDs = errors.New("piperplus: empty phoneme_ids")
	ErrUnsupportedLang = errors.New("piperplus: unsupported language")
)

// ModelLoadError indicates a model loading failure.
type ModelLoadError struct {
	Path string
	Err  error
}

func (e *ModelLoadError) Error() string {
	return fmt.Sprintf("piperplus: failed to load model %q: %v", e.Path, e.Err)
}

func (e *ModelLoadError) Unwrap() error {
	return e.Err
}

// ConfigError indicates a configuration file error.
type ConfigError struct {
	Path string
	Err  error
}

func (e *ConfigError) Error() string {
	return fmt.Sprintf("piperplus: config error %q: %v", e.Path, e.Err)
}

func (e *ConfigError) Unwrap() error {
	return e.Err
}

// InferenceError indicates an ONNX inference error.
type InferenceError struct {
	Msg string
	Err error
}

func (e *InferenceError) Error() string {
	if e.Err == nil {
		return fmt.Sprintf("piperplus: inference error: %s", e.Msg)
	}
	return fmt.Sprintf("piperplus: inference error: %s: %v", e.Msg, e.Err)
}

func (e *InferenceError) Unwrap() error {
	return e.Err
}

// PhonemeError indicates a phonemization error.
// It intentionally does not implement Unwrap because it carries descriptive
// fields (Phoneme, Language, Msg) rather than wrapping an underlying error.
type PhonemeError struct {
	Phoneme  string
	Language string
	Msg      string
}

func (e *PhonemeError) Error() string {
	return fmt.Sprintf("piperplus: phoneme error [%s/%s]: %s", e.Language, e.Phoneme, e.Msg)
}

// PhonemeIDNotFoundError indicates a missing phoneme in the ID map.
type PhonemeIDNotFoundError struct {
	Token string
}

func (e *PhonemeIDNotFoundError) Error() string {
	return fmt.Sprintf("piperplus: phoneme ID not found for token %q", e.Token)
}
