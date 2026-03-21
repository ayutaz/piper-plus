// Example: Streaming synthesis — generates audio sentence-by-sentence.
//
// Usage:
//
//	export ONNX_RUNTIME_SHARED_LIBRARY_PATH=/path/to/libonnxruntime.so
//	go run . -model model.onnx -text "First sentence. Second sentence. Third sentence."
//
// Pipe to audio player:
//
//	go run . -model model.onnx -text "..." | aplay -r 22050 -f S16_LE -c 1
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
	modelPath := flag.String("model", "", "Path to ONNX model")
	text := flag.String("text", "Hello world. How are you? I am fine.", "Text to synthesize")
	language := flag.String("lang", "en", "Language")
	output := flag.String("output", "", "Output WAV file (empty=stdout raw PCM)")
	flag.Parse()

	if *modelPath == "" {
		log.Fatal("--model required")
	}

	if err := piperplus.Init(""); err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer piperplus.Shutdown()

	ctx := context.Background()
	voice, err := piperplus.LoadVoice(ctx, *modelPath)
	if err != nil {
		log.Fatal(err) //nolint:gocritic // Fatal is acceptable in example programs
	}
	defer voice.Close()

	// Choose output: file (WAV) or stdout (raw PCM)
	var w *os.File
	if *output != "" {
		w, err = os.Create(*output)
		if err != nil {
			log.Fatal(err)
		}
		defer w.Close()
	} else {
		w = os.Stdout
	}

	sink := piperplus.NewWriterAudioSink(w)

	// Stream synthesis sentence by sentence
	fmt.Fprintf(os.Stderr, "Streaming synthesis: %q\n", *text)
	err = voice.SynthesizeStream(ctx, *text, sink,
		piperplus.WithLanguage(*language),
		piperplus.WithSentenceSilence(0.3),
	)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Fprintln(os.Stderr, "Done.")
}
