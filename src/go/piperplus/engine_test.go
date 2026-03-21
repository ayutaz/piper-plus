//go:build integration

package piperplus

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	"os"
	"testing"
)

// testModelPath returns the PIPER_TEST_MODEL env var or skips the test.
func testModelPath(t *testing.T) string {
	t.Helper()
	path := os.Getenv("PIPER_TEST_MODEL")
	if path == "" {
		t.Skip("PIPER_TEST_MODEL not set")
	}
	return path
}

func TestDetectCapabilities(t *testing.T) {
	modelPath := testModelPath(t)

	caps, err := detectCapabilities(modelPath)
	if err != nil {
		t.Fatalf("detectCapabilities failed: %v", err)
	}

	// The test model (multilingual-test-medium.onnx) is a single-speaker
	// finetuned model, so it does NOT have a speaker_id input.
	if caps.HasSpeakerID {
		t.Error("expected HasSpeakerID to be false for single-speaker finetuned model")
	}
	if !caps.HasLanguageID {
		t.Error("expected HasLanguageID to be true for multilingual model")
	}
	if !caps.HasDurationOutput {
		t.Error("expected HasDurationOutput to be true")
	}
	if !caps.HasProsody {
		t.Error("expected HasProsody to be true")
	}
}

func TestOnnxEngine_Synthesize(t *testing.T) {
	modelPath := testModelPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	req := &SynthesisRequest{
		PhonemeIDs:  []int64{1, 10, 57, 14, 2}, // ^, a, n, o, $
		SpeakerID:   0,
		LanguageID:  0, // ja
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}

	result, err := engine.Synthesize(context.Background(), req)
	if err != nil {
		t.Fatalf("Synthesize failed: %v", err)
	}

	if result == nil {
		t.Fatal("expected non-nil result")
	}
	if len(result.Audio) == 0 {
		t.Error("expected non-empty audio")
	}
	if result.SampleRate != 22050 {
		t.Errorf("expected SampleRate 22050, got %d", result.SampleRate)
	}
	if result.InferTime <= 0 {
		t.Error("expected InferTime > 0")
	}
	if result.Duration <= 0 {
		t.Error("expected Duration > 0")
	}
	if result.Durations == nil {
		t.Error("expected non-nil Durations")
	}
	if len(result.Durations) != len(req.PhonemeIDs) {
		t.Errorf("expected Durations length %d, got %d", len(req.PhonemeIDs), len(result.Durations))
	}
}

func TestOnnxEngine_SynthesizeEmpty(t *testing.T) {
	modelPath := testModelPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	req := &SynthesisRequest{
		PhonemeIDs: []int64{},
	}

	_, err = engine.Synthesize(context.Background(), req)
	if !errors.Is(err, ErrEmptyPhonemeIDs) {
		t.Errorf("expected ErrEmptyPhonemeIDs, got %v", err)
	}
}

func TestVoice_LoadAndSynthesize(t *testing.T) {
	modelPath := testModelPath(t)

	voice, err := LoadVoice(context.Background(), modelPath)
	if err != nil {
		t.Fatalf("LoadVoice failed: %v", err)
	}
	defer voice.Close()

	if voice.Config() == nil {
		t.Fatal("expected non-nil Config")
	}
	if !voice.Capabilities().HasLanguageID {
		t.Error("expected HasLanguageID to be true")
	}

	req := &SynthesisRequest{
		PhonemeIDs:  []int64{1, 10, 57, 14, 2},
		SpeakerID:   0,
		LanguageID:  0,
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}

	result, err := voice.SynthesizeFromIDs(context.Background(), req)
	if err != nil {
		t.Fatalf("SynthesizeFromIDs failed: %v", err)
	}
	if len(result.Audio) == 0 {
		t.Error("expected non-empty audio")
	}

	// Verify WAV writability.
	var buf bytes.Buffer
	if err := result.WriteWAV(&buf); err != nil {
		t.Fatalf("WriteWAV failed: %v", err)
	}
	if buf.Len() <= 44 {
		t.Errorf("expected WAV size > 44 bytes, got %d", buf.Len())
	}
}

func TestVoice_Close(t *testing.T) {
	modelPath := testModelPath(t)

	voice, err := LoadVoice(context.Background(), modelPath)
	if err != nil {
		t.Fatalf("LoadVoice failed: %v", err)
	}

	// First close should succeed.
	if err := voice.Close(); err != nil {
		t.Fatalf("first Close returned error: %v", err)
	}

	// Second close should be idempotent (no error).
	if err := voice.Close(); err != nil {
		t.Fatalf("second Close returned error: %v", err)
	}

	// SynthesizeFromIDs after close should return ErrModelClosed.
	req := &SynthesisRequest{
		PhonemeIDs:  []int64{1, 10, 57, 14, 2},
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}
	_, err = voice.SynthesizeFromIDs(context.Background(), req)
	if !errors.Is(err, ErrModelClosed) {
		t.Errorf("expected ErrModelClosed after Close, got %v", err)
	}
}

func TestSynthesisResult_WriteWAV(t *testing.T) {
	modelPath := testModelPath(t)

	config, err := LoadConfig(modelPath + ".json")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	engine, err := newOnnxEngine(modelPath, config, nil, slog.Default())
	if err != nil {
		t.Fatalf("newOnnxEngine failed: %v", err)
	}
	defer engine.Close()

	req := &SynthesisRequest{
		PhonemeIDs:  []int64{1, 10, 57, 14, 2},
		SpeakerID:   0,
		LanguageID:  0,
		NoiseScale:  0.667,
		LengthScale: 1.0,
		NoiseW:      0.8,
	}

	result, err := engine.Synthesize(context.Background(), req)
	if err != nil {
		t.Fatalf("Synthesize failed: %v", err)
	}

	var buf bytes.Buffer
	if err := result.WriteWAV(&buf); err != nil {
		t.Fatalf("WriteWAV failed: %v", err)
	}

	wavBytes := buf.Bytes()

	// First 4 bytes must be "RIFF".
	if len(wavBytes) < 4 || string(wavBytes[:4]) != "RIFF" {
		t.Errorf("expected first 4 bytes to be \"RIFF\", got %q", wavBytes[:4])
	}

	// WAV must be larger than the 44-byte header.
	if buf.Len() <= 44 {
		t.Errorf("expected WAV size > 44 bytes, got %d", buf.Len())
	}
}
