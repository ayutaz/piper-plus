// Example: Basic text-to-speech synthesis with piper-plus.
//
// Usage:
//
//	export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so
//	go run . -model model.onnx -text "Hello, world!" -output output.wav
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
	modelPath := flag.String("model", "", "Path to ONNX model")
	text := flag.String("text", "Hello, how are you today?", "Text to synthesize")
	output := flag.String("output", "output.wav", "Output WAV file path")
	language := flag.String("lang", "en", "Language code")
	device := flag.String("device", "cpu", "Device (cpu, cuda, auto)")
	flag.Parse()

	if *modelPath == "" {
		log.Fatal("--model is required")
	}

	// Initialize ONNX Runtime
	if err := piperplus.Init(""); err != nil {
		log.Fatalf("Failed to init ONNX Runtime: %v", err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer piperplus.Shutdown()

	// Load voice model
	ctx := context.Background()
	voice, err := piperplus.LoadVoice(ctx, *modelPath,
		piperplus.WithDevice(*device),
	)
	if err != nil {
		log.Fatalf("Failed to load voice: %v", err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer voice.Close()

	// Synthesize
	start := time.Now()
	result, err := voice.Synthesize(ctx, *text,
		piperplus.WithLanguage(*language),
	)
	if err != nil {
		log.Fatalf("Synthesis failed: %v", err)
	}

	// Write WAV
	f, err := os.Create(*output)
	if err != nil {
		log.Fatalf("Failed to create file: %v", err)
	}
	defer f.Close()
	result.WriteTo(f)

	fmt.Printf("Generated %s (%.2fs audio, %.2fs inference, RTF=%.3f)\n",
		*output, result.Duration.Seconds(), result.InferTime.Seconds(), result.RTF())
	fmt.Printf("Total wall time: %v\n", time.Since(start))
}
