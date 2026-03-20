// Package piperplus provides Go bindings for Piper Plus text-to-speech synthesis.
//
// Piper Plus is a neural TTS system using the VITS architecture, supporting
// 6 languages (Japanese, English, Chinese, Spanish, French, Portuguese).
// This package wraps ONNX Runtime for inference via github.com/yalue/onnxruntime_go.
//
// # Quick Start
//
// Initialize the ONNX Runtime environment once at program start:
//
//	if err := piperplus.Init("/path/to/libonnxruntime.so"); err != nil {
//	    log.Fatal(err)
//	}
//	defer piperplus.Shutdown()
//
// Load a voice model and synthesize speech:
//
//	voice, err := piperplus.LoadVoice(ctx, "model.onnx")
//	if err != nil {
//	    log.Fatal(err)
//	}
//	defer voice.Close()
//
//	result, err := voice.Synthesize(ctx, "こんにちは",
//	    piperplus.WithLanguage("ja"),
//	)
//	if err != nil {
//	    log.Fatal(err)
//	}
//
//	f, _ := os.Create("output.wav")
//	defer f.Close()
//	result.WriteTo(f)
//
// # Environment Variables
//
//   - ONNX_RUNTIME_SHARED_LIBRARY_PATH: Path to the ONNX Runtime shared library
//   - PIPER_DEFAULT_MODEL: Default model path
//   - PIPER_DEFAULT_CONFIG: Default config.json path
package piperplus
