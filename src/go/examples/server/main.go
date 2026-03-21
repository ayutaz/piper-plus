// Example: HTTP TTS server with piper-plus.
//
// Usage:
//
//	export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so
//	go run . -model model.onnx -addr :8080
//
// Test:
//
//	curl "http://localhost:8080/synthesize?text=Hello&lang=en" -o output.wav
//	curl http://localhost:8080/health
//	curl http://localhost:8080/info
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"log/slog"
	"os"
	"os/signal"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
	modelPath := flag.String("model", "", "Path to ONNX model")
	addr := flag.String("addr", ":8080", "Listen address")
	device := flag.String("device", "cpu", "Device")
	flag.Parse()

	if *modelPath == "" {
		log.Fatal("--model is required")
	}

	logger := slog.Default()

	// Init ONNX Runtime
	if err := piperplus.Init(""); err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer piperplus.Shutdown()

	// Load voice
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
	defer cancel()

	voice, err := piperplus.LoadVoice(ctx, *modelPath,
		piperplus.WithDevice(*device),
		piperplus.WithLogger(logger),
	)
	if err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer voice.Close()

	// Start server
	server := piperplus.NewServer(voice, logger)
	fmt.Printf("Starting TTS server on %s\n", *addr)
	fmt.Println("Endpoints:")
	fmt.Println("  GET/POST /synthesize?text=...&lang=...")
	fmt.Println("  GET      /health")
	fmt.Println("  GET      /info")

	if err := server.ListenAndServe(*addr); err != nil {
		log.Fatal(err)
	}
}
