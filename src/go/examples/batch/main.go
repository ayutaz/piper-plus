// Example: Batch processing — synthesize multiple texts from a file.
//
// Usage:
//
//	export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so
//	go run . -model model.onnx -input texts.txt -outdir output/
//
// Input file format (one text per line):
//
//	Hello, how are you?
//	Good morning!
//	こんにちは、今日はいい天気ですね。
package main

import (
	"bufio"
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
	modelPath := flag.String("model", "", "Path to ONNX model")
	inputFile := flag.String("input", "", "Input text file (one line per utterance)")
	outDir := flag.String("outdir", "output", "Output directory")
	language := flag.String("lang", "en", "Language")
	device := flag.String("device", "cpu", "Device")
	flag.Parse()

	if *modelPath == "" || *inputFile == "" {
		log.Fatal("--model and --input are required")
	}

	if err := piperplus.Init(""); err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer piperplus.Shutdown()

	ctx := context.Background()
	voice, err := piperplus.LoadVoice(ctx, *modelPath, piperplus.WithDevice(*device))
	if err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer voice.Close()

	// Read input file
	f, err := os.Open(*inputFile)
	if err != nil {
		log.Fatal(err)
	}
	defer f.Close()

	os.MkdirAll(*outDir, 0755)

	scanner := bufio.NewScanner(f)
	lineNum := 0
	totalStart := time.Now()

	for scanner.Scan() {
		text := scanner.Text()
		if text == "" {
			continue
		}
		lineNum++

		outPath := filepath.Join(*outDir, fmt.Sprintf("line_%03d.wav", lineNum))
		start := time.Now()

		result, err := voice.Synthesize(ctx, text, piperplus.WithLanguage(*language))
		if err != nil {
			log.Printf("Line %d failed: %v", lineNum, err)
			continue
		}

		w, err := os.Create(outPath)
		if err != nil {
			log.Printf("Failed to create %s: %v", outPath, err)
			continue
		}
		result.WriteTo(w)
		w.Close()

		elapsed := time.Since(start)

		fmt.Printf("[%d] %s (%.2fs audio, %dms infer, RTF=%.3f)\n",
			lineNum, outPath, result.Duration.Seconds(),
			elapsed.Milliseconds(), result.RTF())
	}

	fmt.Printf("\nBatch complete: %d files in %v\n", lineNum, time.Since(totalStart))
}
