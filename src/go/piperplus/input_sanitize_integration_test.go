//go:build integration

package piperplus

// A dirty text and its clean form give the same audio with a real model.
// Contract: docs/spec/input-sanitize-contract.toml (runtime "go"). The
// model-free tests in input_sanitize_test.go show the text that reaches G2P;
// this one shows the result the caller gets. noise_w = 0 makes the durations
// deterministic, so the audio lengths are compared.

import (
	"context"
	"testing"
)

type countingSink struct{ samples int }

func (s *countingSink) WriteAudio(samples []int16, _ int) error {
	s.samples += len(samples)
	return nil
}

func (s *countingSink) Close() error { return nil }

func TestInputSanitize_RealModelReadsDirtyLikeClean(t *testing.T) {
	voice, err := LoadVoice(context.Background(), testModelPath(t))
	if err != nil {
		t.Fatalf("LoadVoice: %v", err)
	}
	defer voice.Close()

	opts := []SynthesisOption{WithLanguage("es"), WithNoiseW(0)}
	synthesize := func(text string) int {
		result, err := voice.Synthesize(context.Background(), text, opts...)
		if err != nil {
			t.Fatalf("Synthesize(%q): %v", text, err)
		}
		return len(result.Audio)
	}
	stream := func(text string) int {
		sink := &countingSink{}
		if err := voice.SynthesizeStream(context.Background(), text, sink, opts...); err != nil {
			t.Fatalf("SynthesizeStream(%q): %v", text, err)
		}
		return sink.samples
	}

	for _, c := range append(sanitizeCasesFor(t, "es"), goLocalSanitizeCases...) {
		if c.Control != "" && c.Control != "U+0000" && c.Control != "U+000C" {
			continue // one removed and one space-like control per word case
		}
		if dirty, clean := synthesize(c.Dirty), synthesize(c.Clean); dirty != clean {
			t.Errorf("%s: Synthesize gave %d samples, want %d", c.label(), dirty, clean)
		}
		if dirty, clean := stream(c.Dirty), stream(c.Clean); dirty != clean {
			t.Errorf("%s: SynthesizeStream gave %d samples, want %d", c.label(), dirty, clean)
		}
	}
}
