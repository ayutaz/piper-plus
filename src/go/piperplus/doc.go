// Package piperplus provides Go bindings for Piper Plus text-to-speech synthesis.
//
// Piper Plus is a neural TTS system using the VITS architecture, supporting
// 8 languages (Japanese, English, Chinese, Korean, Spanish, French, Portuguese, Swedish).
// This package wraps ONNX Runtime for inference via github.com/yalue/onnxruntime_go.
//
// # Architecture
//
// The package is organized around four layers:
//
//   - Initialization: [Init] / [Shutdown] manage the ONNX Runtime environment.
//   - Voice: [Voice] loads an ONNX model and provides synthesis methods.
//   - Pooling: [VoicePool] manages concurrent access with lazy voice creation.
//   - Server: [Server] exposes an HTTP API for TTS over the network.
//
// Supporting types include [VoiceConfig] for model configuration,
// [SynthesisResult] for output audio with WAV encoding, [ModelManager] for
// model caching and download, and [DeviceType] for execution provider selection.
//
// # Quick Start
//
// Initialize the ONNX Runtime environment, load a model, and synthesize text:
//
//	package main
//
//	import (
//	    "context"
//	    "log"
//	    "os"
//
//	    "github.com/ayutaz/piper-plus/src/go/piperplus"
//	)
//
//	func main() {
//	    // Initialize ONNX Runtime (once per process).
//	    if err := piperplus.Init("/path/to/libonnxruntime.so"); err != nil {
//	        log.Fatal(err)
//	    }
//	    defer piperplus.Shutdown()
//
//	    // Load a voice model.
//	    voice, err := piperplus.LoadVoice(context.Background(), "model.onnx",
//	        piperplus.WithConfig("config.json"),
//	        piperplus.WithDevice("cpu"),
//	    )
//	    if err != nil {
//	        log.Fatal(err)
//	    }
//	    defer voice.Close()
//
//	    // Synthesize text to speech.
//	    result, err := voice.Synthesize(context.Background(), "Hello, world!",
//	        piperplus.WithLanguage("en"),
//	        piperplus.WithNoiseScale(0.667),
//	        piperplus.WithLengthScale(1.0),
//	    )
//	    if err != nil {
//	        log.Fatal(err)
//	    }
//
//	    // Write WAV output.
//	    f, _ := os.Create("output.wav")
//	    defer f.Close()
//	    result.WriteTo(f)
//
//	    log.Printf("duration=%v rtf=%.2f", result.Duration, result.RTF())
//	}
//
// # Streaming Synthesis
//
// For long text, [Voice.SynthesizeStream] splits input into sentences and
// delivers audio chunks incrementally via an [AudioSink]:
//
//	f, _ := os.Create("stream.wav")
//	defer f.Close()
//	sink := piperplus.NewWriterAudioSink(f)
//
//	err := voice.SynthesizeStream(ctx, longText, sink,
//	    piperplus.WithLanguage("ja"),
//	    piperplus.WithSentenceSilence(0.3),
//	)
//
// Custom sinks can be implemented by satisfying the [AudioSink] interface.
// Sentence splitting is handled by [SplitSentences], which supports
// Japanese, Chinese, and Western punctuation.
//
// # HTTP Server
//
// [Server] provides a ready-made HTTP API with three endpoints:
//
//	server := piperplus.NewServer(voice, logger)
//	log.Fatal(server.ListenAndServe(":8080"))
//
// Endpoints:
//
//   - POST /synthesize: accepts JSON {"text":"...", "language":"en", ...},
//     returns audio/wav.
//   - GET /synthesize?text=...&lang=en: query-parameter variant.
//   - GET /health: returns {"status":"ok"}.
//   - GET /info: returns model capabilities, languages, and sample rate.
//
// # VoicePool
//
// [VoicePool] manages a bounded pool of [Voice] instances for concurrent
// synthesis, modeled after database/sql.DB. Voices are created lazily
// and recycled after use:
//
//	pool := piperplus.NewVoicePool("model.onnx", 4,
//	    piperplus.WithConfig("config.json"),
//	)
//	defer pool.Close()
//
//	// Safe for concurrent use from multiple goroutines.
//	result, err := pool.Synthesize(ctx, "Hello!",
//	    piperplus.WithLanguage("en"),
//	)
//
// # Low-Level API
//
// For pre-computed phoneme IDs (e.g., from JSONL input), use
// [Voice.SynthesizeFromIDs] directly:
//
//	req := &piperplus.SynthesisRequest{
//	    PhonemeIDs:  []int64{1, 8, 5, 39, 2},
//	    SpeakerID:   0,
//	    NoiseScale:  0.667,
//	    LengthScale: 1.0,
//	    NoiseW:      0.8,
//	}
//	result, err := voice.SynthesizeFromIDs(ctx, req)
//
// JSONL batch input is supported via [ReadJSONL] and [ParseJSONLLine],
// which accept both phoneme_ids and text fields.
//
// # Model Management
//
// [ModelManager] handles model discovery, download, and caching in a
// platform-specific cache directory:
//
//	mgr := piperplus.NewModelManager("", nil) // uses default cache dir
//	models, _ := mgr.ListModels()
//	path, _ := mgr.FindModel("tsukuyomi-6lang-v2")
//	downloaded, _ := mgr.DownloadModel(ctx, "https://example.com/model.onnx")
//
// # Phoneme Timing
//
// When the model outputs per-phoneme durations, [DurationsToTiming] converts
// them to millisecond timestamps:
//
//	timing, err := piperplus.DurationsToTiming(
//	    result.Durations, phonemeTokens, 22050, piperplus.DefaultHopLength,
//	)
//	tsv := timing.ToTSV()
//
// # Device Selection
//
// Inference device is configured via [WithDevice] or [ParseDevice].
// Supported providers: cpu, cuda, cuda:N, coreml, directml, directml:N,
// tensorrt, tensorrt:N, and auto (tries CUDA, CoreML, DirectML, then CPU).
// GPU providers fall back to CPU automatically on configuration failure.
//
// # Environment Variables
//
//   - ONNX_RUNTIME_SHARED_LIBRARY_PATH: Path to the ONNX Runtime shared
//     library. Used by [Init] when no explicit path is provided.
//   - PIPER_DEFAULT_MODEL: Default model path.
//   - PIPER_DEFAULT_CONFIG: Default config.json path, checked by
//     [FindConfigPath].
//   - PIPER_MODEL_DIR: Override the default model cache directory
//     used by [ModelManager].
//
// # Key Types
//
// Initialization:
//   - [Init], [Shutdown]: ONNX Runtime lifecycle.
//
// Voice loading and synthesis:
//   - [Voice]: loaded model; provides [Voice.Synthesize],
//     [Voice.SynthesizeFromIDs], [Voice.SynthesizeStream].
//   - [LoadVoice]: constructor with [LoadOption] functional options
//     ([WithConfig], [WithDevice], [WithLogger]).
//   - [SynthesisOption]: functional options for synthesis
//     ([WithLanguage], [WithSpeakerID], [WithNoiseScale],
//     [WithLengthScale], [WithNoiseW], [WithSentenceSilence]).
//
// Results and output:
//   - [SynthesisResult]: audio samples, duration, RTF, WAV encoding
//     ([SynthesisResult.WriteTo], [SynthesisResult.WriteWAV],
//     [SynthesisResult.RawPCMReader], [SynthesisResult.AudioFloat32]).
//   - [SynthesisRequest]: low-level request with phoneme IDs, speaker/language
//     IDs, scales, and prosody features.
//
// Streaming:
//   - [AudioSink]: interface for receiving audio chunks.
//   - [WriterAudioSink]: adapts an [io.Writer] to [AudioSink].
//
// Concurrency:
//   - [VoicePool]: bounded pool of voices for concurrent synthesis.
//
// HTTP:
//   - [Server]: HTTP TTS server with /synthesize, /health, /info endpoints.
//
// Configuration:
//   - [VoiceConfig], [AudioConfig], [InferenceConfig]: model config.json.
//   - [LoadConfig], [FindConfigPath]: config loading and discovery.
//   - [ModelCapabilities]: detected ONNX graph features.
//
// Model management:
//   - [ModelManager], [ModelInfo]: cache-based model discovery and download.
//
// Timing:
//   - [DurationsToTiming], [TimingResult], [PhonemeTimingInfo]: phoneme timing.
//
// Device:
//   - [DeviceType], [ParseDevice]: execution provider selection.
//
// Text processing:
//   - [SplitSentences]: multilingual sentence splitting.
//   - [SplitTextChunks]: chunk text at sentence boundaries.
//
// JSONL:
//   - [JSONLInput], [ParseJSONLLine], [ReadJSONL]: batch input parsing.
//
// Errors:
//   - [ErrModelClosed], [ErrEmptyText], [ErrEmptyPhonemeIDs], [ErrUnsupportedLang]:
//     sentinel errors.
//   - [ModelLoadError], [ConfigError], [InferenceError], [PhonemeError],
//     [PhonemeIDNotFoundError]: structured error types.
package piperplus
