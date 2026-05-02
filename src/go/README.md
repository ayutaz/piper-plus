# Piper Plus Go Bindings

## Overview / 概要

Go 1.26+ bindings for [Piper Plus](https://github.com/ayutaz/piper-plus) neural text-to-speech synthesis.
Built on the VITS architecture, these bindings provide idiomatic Go access to high-quality multilingual TTS
with ONNX Runtime inference via [yalue/onnxruntime_go](https://github.com/yalue/onnxruntime_go).

**Supported languages (対応言語):** Japanese (JA), English (EN), Chinese (ZH), Korean (KO), Spanish (ES), French (FR), Portuguese (PT), Swedish (SV)

**Key features:**
- Text-to-speech with automatic phonemization for 8 languages
- Streaming synthesis with sentence-level chunking
- GPU acceleration: CUDA, CoreML, DirectML, TensorRT (with automatic fallback to CPU)
- Built-in HTTP API server
- Session pooling for concurrent synthesis (`VoicePool`)
- Phoneme timing extraction (JSON/TSV)
- Model management with automatic download and caching
- Direct phoneme ID input via JSONL
- WAV output with peak normalization

## Requirements / 必要要件

- **Go 1.26+**
- **ONNX Runtime shared library** (download from [GitHub releases](https://github.com/microsoft/onnxruntime/releases))
  - Linux: `libonnxruntime.so`
  - macOS: `libonnxruntime.dylib`
  - Windows: `onnxruntime.dll`
- Set the `ONNX_RUNTIME_SHARED_LIBRARY_PATH` environment variable, or pass the path to `piperplus.Init()`

## Installation / インストール

```bash
go get github.com/ayutaz/piper-plus/src/go@latest
```

### G2P Only (Standalone) / G2Pのみ使用する場合

Phonemization (G2P) だけを使用したい場合は、TTS エンジン全体をインストールせずに `phonemize` スタンドアロンモジュールのみ取得できます:

```bash
go get github.com/ayutaz/piper-plus/src/go/phonemize@latest
```

詳細は [`phonemize/README.md`](phonemize/README.md) を参照してください。

## Quick Start / クイックスタート

```go
package main

import (
    "context"
    "log"
    "os"

    "github.com/ayutaz/piper-plus/src/go/piperplus"
)

func main() {
    // Initialize ONNX Runtime (uses ONNX_RUNTIME_SHARED_LIBRARY_PATH env var).
    if err := piperplus.Init(""); err != nil {
        log.Fatal(err)
    }
    defer piperplus.Shutdown()

    // Load a voice model. Config is auto-detected from model.onnx.json or config.json.
    voice, err := piperplus.LoadVoice(context.Background(), "model.onnx")
    if err != nil {
        log.Fatal(err)
    }
    defer voice.Close()

    // Synthesize text to speech.
    result, err := voice.Synthesize(context.Background(), "Hello, world!",
        piperplus.WithLanguage("en"),
    )
    if err != nil {
        log.Fatal(err)
    }

    // Write WAV output.
    f, _ := os.Create("output.wav")
    defer f.Close()
    result.WriteTo(f)
}
```

### Multilingual example / 多言語の例

```go
// Japanese
result, _ := voice.Synthesize(ctx, "こんにちは、今日は良い天気ですね。",
    piperplus.WithLanguage("ja"))

// Chinese
result, _ := voice.Synthesize(ctx, "你好，今天天气很好。",
    piperplus.WithLanguage("zh"))

// Spanish
result, _ := voice.Synthesize(ctx, "Hola, como estas hoy?",
    piperplus.WithLanguage("es"))

// Swedish
result, _ := voice.Synthesize(ctx, "Hej, hur mår du idag?",
    piperplus.WithLanguage("sv"))
```

## CLI Usage / CLIの使い方

### Install the CLI

```bash
go install github.com/ayutaz/piper-plus/src/go/cmd/piper-plus@latest
```

### Text mode (single utterance)

```bash
piper-plus -m model.onnx -t "Hello world" -f output.wav
```

### JSONL from stdin

```bash
echo '{"text":"Hello","language":"en"}' | piper-plus -m model.onnx -d output/
```

### Batch mode (one line per utterance)

```bash
piper-plus -m model.onnx --batch input.txt -d output/
```

### Streaming (raw PCM to stdout)

```bash
piper-plus -m model.onnx -t "Hello" --streaming | aplay -r 22050 -f S16_LE
```

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `-m, --model` | `$PIPER_DEFAULT_MODEL` | Path to ONNX model file |
| `-c, --config` | auto-detected | Path to config.json |
| `-t, --text` | | Text to synthesize (single utterance) |
| `--language` | | Language code (ja, en, zh, es, fr, pt, sv) |
| `-s, --speaker` | `0` | Speaker ID for multi-speaker models |
| `-f, --output-file` | | Output WAV path (`-` for stdout) |
| `-d, --output-dir` | `.` | Output directory for generated files |
| `--noise-scale` | `0.667` | Generation noise scale |
| `--length-scale` | `1.0` | Speech rate (length scale) |
| `--noise-w` | `0.8` | Duration predictor noise scale |
| `--sentence-silence` | `0.2` | Silence between sentences (seconds) |
| `--device` | `cpu` | Inference device (cpu, cuda, coreml, directml) |
| `--streaming` | `false` | Write raw PCM int16 to stdout |
| `--batch` | | Batch file with one text line per utterance |
| `--output-timing` | | Write phoneme timing to file |
| `--timing-format` | `json` | Timing output format (json or tsv) |
| `--debug` | `false` | Enable debug logging |

## API Reference / APIリファレンス

### Initialization / 初期化

| Function | Description |
|----------|-------------|
| `piperplus.Init(libraryPath string) error` | Initialize ONNX Runtime. If `libraryPath` is empty, uses `ONNX_RUNTIME_SHARED_LIBRARY_PATH` env var. Thread-safe; only the first call takes effect. |
| `piperplus.Shutdown() error` | Destroy the ONNX Runtime environment. Safe to call multiple times. |

### Voice / 音声モデル

| Function / Method | Description |
|-------------------|-------------|
| `piperplus.LoadVoice(ctx, modelPath, opts...) (*Voice, error)` | Load a TTS model. Config is auto-discovered. |
| `voice.Synthesize(ctx, text, opts...) (*SynthesisResult, error)` | High-level: phonemize text and run inference. |
| `voice.SynthesizeFromIDs(ctx, *SynthesisRequest) (*SynthesisResult, error)` | Low-level: synthesize from pre-computed phoneme IDs. |
| `voice.SynthesizeStream(ctx, text, AudioSink, opts...) error` | Stream synthesis sentence by sentence to an AudioSink. |
| `voice.Config() *VoiceConfig` | Return the loaded voice configuration (read-only). |
| `voice.Capabilities() ModelCapabilities` | Return detected model capabilities (multi-speaker, multilingual, prosody). |
| `voice.Close() error` | Release all resources. Safe to call multiple times. Implements `io.Closer`. |

### SynthesisResult / 合成結果

| Method | Description |
|--------|-------------|
| `result.WriteTo(w io.Writer) (int64, error)` | Write WAV output. Implements `io.WriterTo`. |
| `result.WriteWAV(w io.Writer) error` | Convenience wrapper for `WriteTo`. |
| `result.RawPCMReader() io.Reader` | Raw PCM int16 little-endian bytes (no WAV header). |
| `result.RTF() float64` | Real-Time Factor (`InferTime / Duration`). < 1.0 = faster than real-time. |
| `result.AudioFloat32() []float32` | Convert int16 PCM back to float32 [-1.0, 1.0]. |

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `Audio` | `[]int16` | PCM samples (mono, 16-bit, peak-normalized) |
| `SampleRate` | `int` | Sample rate (e.g., 22050) |
| `Duration` | `time.Duration` | Audio duration |
| `InferTime` | `time.Duration` | Wall-clock inference time |
| `Durations` | `[]float32` | Per-phoneme durations in frames (nil if unavailable) |

### Voice Pool / セッションプール

| Function / Method | Description |
|-------------------|-------------|
| `piperplus.NewVoicePool(modelPath, concurrency, opts...) *VoicePool` | Create a pool with bounded concurrency. Voices are created lazily and recycled. |
| `pool.Synthesize(ctx, text, opts...) (*SynthesisResult, error)` | Acquire a voice, synthesize, and return to pool. |
| `pool.SynthesizeFromIDs(ctx, *SynthesisRequest) (*SynthesisResult, error)` | Pool-managed low-level synthesis. |
| `pool.Close() error` | Close all pooled voices. Idempotent. |

### HTTP Server / HTTPサーバー

| Function / Method | Description |
|-------------------|-------------|
| `piperplus.NewServer(voice, logger) *Server` | Create an HTTP TTS server. |
| `server.Handler() http.Handler` | Return the `http.Handler` for embedding in custom servers. |
| `server.ListenAndServe(addr string) error` | Start the HTTP server. |

### Streaming / ストリーミング

| Type / Function | Description |
|-----------------|-------------|
| `AudioSink` (interface) | Receives audio chunks: `WriteAudio(samples []int16, sampleRate int) error` and `Close() error`. |
| `piperplus.NewWriterAudioSink(w io.Writer) *WriterAudioSink` | Wraps an `io.Writer` to write raw PCM int16 LE bytes. |

### Model Manager / モデル管理

| Function / Method | Description |
|-------------------|-------------|
| `piperplus.NewModelManager(cacheDir, logger) *ModelManager` | Create a model manager. Uses platform default cache dir if empty. |
| `piperplus.DefaultCacheDir() string` | Platform-specific cache: `~/Library/Application Support/piper-plus/models` (macOS), `~/.local/share/piper-plus/models` (Linux), `%APPDATA%\piper-plus\models` (Windows). Override with `PIPER_MODEL_DIR`. |
| `manager.ListModels() ([]ModelInfo, error)` | List all cached `.onnx` models. |
| `manager.FindModel(name) (string, error)` | Locate a model by name in the cache. |
| `manager.DownloadModel(ctx, url) (string, error)` | Download a model to the cache (atomic write). |

### Timing / タイミング

| Function / Method | Description |
|-------------------|-------------|
| `piperplus.DurationsToTiming(durations, tokens, sampleRate, hopLength) (*TimingResult, error)` | Convert per-phoneme duration frames to timestamps. |
| `timing.ToJSON() ([]byte, error)` | Pretty-printed JSON output. |
| `timing.ToTSV() string` | Tab-separated values with header. |

### JSONL Input / JSONL入力

| Function | Description |
|----------|-------------|
| `piperplus.ParseJSONLLine(line []byte) (*JSONLInput, error)` | Parse a single JSONL line. Must contain `phoneme_ids` or `text`. |
| `piperplus.ReadJSONL(ctx, io.Reader) (<-chan *JSONLInput, <-chan error)` | Read JSONL from a reader into channels. Empty lines and `//` comments are skipped. |
| `input.ToSynthesisRequest(defaults) *SynthesisRequest` | Convert JSONL input to a synthesis request. |

## Configuration Options / 設定オプション

### LoadOption (for `LoadVoice`)

| Function | Description |
|----------|-------------|
| `WithConfig(path string)` | Set an explicit config.json path. If omitted, auto-discovered from: `model.onnx.json` sidecar, then `config.json` in the model directory. |
| `WithDevice(device string)` | Set inference device (default: `"cpu"`). See GPU Support below. |
| `WithLogger(logger *slog.Logger)` | Set a custom structured logger. |

### SynthesisOption (for `Synthesize`)

| Function | Default | Description |
|----------|---------|-------------|
| `WithLanguage(lang string)` | `""` | Target language code (ja, en, zh, es, fr, pt, sv). |
| `WithSpeakerID(id int64)` | `0` | Speaker ID for multi-speaker models. |
| `WithNoiseScale(v float32)` | `0.667` | Generation noise scale (higher = more variation). |
| `WithLengthScale(v float32)` | `1.0` | Speech rate (< 1.0 = faster, > 1.0 = slower). |
| `WithNoiseW(v float32)` | `0.8` | Duration predictor noise scale. |
| `WithSentenceSilence(seconds float64)` | `0.2` | Silence between sentences in streaming mode. |

## GPU Support / GPUサポート

Pass a device string to `WithDevice()` or the `--device` CLI flag. If the requested provider is unavailable, the engine falls back to CPU automatically.

| Device string | Provider | Notes |
|---------------|----------|-------|
| `cpu` | CPU | Default. No additional dependencies. |
| `cuda` | CUDA | Requires CUDA-enabled ONNX Runtime build. |
| `cuda:N` | CUDA | Use GPU device N (e.g., `cuda:1`). |
| `coreml` | CoreML | macOS only. |
| `directml` | DirectML | Windows only. |
| `directml:N` | DirectML | Use GPU device N. |
| `tensorrt` | TensorRT | Requires TensorRT-enabled ONNX Runtime build. |
| `tensorrt:N` | TensorRT | Use GPU device N. |
| `auto` | Auto-detect | Tries CUDA, CoreML, DirectML in order, falls back to CPU. |

```go
// GPU example
voice, err := piperplus.LoadVoice(ctx, "model.onnx",
    piperplus.WithDevice("cuda"),
)
```

## HTTP API

Start the server:

```go
srv := piperplus.NewServer(voice, logger)
log.Fatal(srv.ListenAndServe(":8080"))
```

### Endpoints

#### `GET/POST /synthesize`

Synthesize text to WAV audio.

**GET query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | string | Text to synthesize (required) |
| `lang` | string | Language code |
| `speaker` | int | Speaker ID |
| `noise_scale` | float | Generation noise |
| `length_scale` | float | Speech rate |
| `noise_w` | float | Duration predictor noise |

**POST JSON body:**

```json
{
  "text": "Hello, world!",
  "language": "en",
  "speaker_id": 0,
  "noise_scale": 0.667,
  "length_scale": 1.0,
  "noise_w": 0.8
}
```

**Response:** `audio/wav` (200) or `application/json` error.

```bash
# GET example
curl "http://localhost:8080/synthesize?text=Hello&lang=en" -o output.wav

# POST example
curl -X POST http://localhost:8080/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello","language":"en"}' \
  -o output.wav
```

#### `GET /health`

Returns `{"status": "ok"}`.

#### `GET /info`

Returns model information:

```json
{
  "num_speakers": 571,
  "num_languages": 6,
  "languages": {"ja": 0, "en": 1, "zh": 2, "es": 3, "fr": 4, "pt": 5},
  "capabilities": {
    "HasSpeakerID": true,
    "HasLanguageID": true,
    "HasProsody": true,
    "HasDurationOutput": true
  },
  "sample_rate": 22050
}
```

## Docker / Dockerでの使用

### Build (multi-arch / マルチアーキテクチャ)

```bash
# Native build (host arch) — produces a locally runnable image tag
docker build -t piper-plus-go -f src/go/docker/Dockerfile .

# Cross-platform single-arch build via buildx, loaded into the local image store
# (use --load for "docker run" usability; --load is incompatible with multi-platform)
docker buildx build \
  --platform linux/arm64 \
  -t piper-plus-go \
  --load \
  -f src/go/docker/Dockerfile .

# Cross-platform multi-arch build that pushes directly to a registry
# (--push is required when --platform lists more than one platform)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t <registry>/piper-plus-go:latest \
  --push \
  -f src/go/docker/Dockerfile .
```

The Dockerfile uses `TARGETARCH` (multi-arch ready, PR #366) so the same Dockerfile builds amd64 and arm64 images. The runtime stage downloads the architecture-matching ONNX Runtime tarball automatically.

### Run

```bash
# Single utterance
docker run -v /path/to/models:/models \
  piper-plus-go -m /models/model.onnx -t "Hello" -f /models/output.wav

# HTTP server mode — see "serve subcommand" below
docker run -p 8080:8080 -v /path/to/models:/models \
  piper-plus-go serve -m /models/model.onnx --addr :8080
```

The Dockerfile uses a multi-stage build: a Debian-based Go builder that compiles OpenJTalk from source for Japanese G2P support, and a `debian:trixie-slim` runtime with ONNX Runtime `v1.24.4`. Override `ORT_VERSION` for other ONNX Runtime versions, and `TARGETARCH` is honored automatically by `docker buildx`.

## `serve` subcommand / `serve` サブコマンド

The CLI binary doubles as an HTTP server when invoked with `serve` as the first argument. Endpoints (`/synthesize`, `/health`, `/info`) are described in [HTTP API](#http-api) below.

```bash
# Local serve (host)
piper-plus serve -m model.onnx --addr :8080

# Streaming + custom dictionary
piper-plus serve -m model.onnx --addr :8080 --custom-dict dict.json

# In Docker (port-forwarded)
docker run -p 8080:8080 -v /path/to/models:/models \
  piper-plus-go serve -m /models/model.onnx --addr :8080
```

| Flag | Default | Description |
|------|---------|-------------|
| `--addr` | `:8080` | HTTP listen address |
| `-m, --model` | (required) | ONNX model path |
| `-c, --config` | auto-detected | `config.json` path |
| `--custom-dict` | | Custom dictionary path (JSON v1/v2 or TSV) |
| `--device` | `cpu` | Inference device (`cpu`, `cuda`, `coreml`, `directml`) |

## Environment Variables / 環境変数

| Variable | Description |
|----------|-------------|
| `ONNX_RUNTIME_SHARED_LIBRARY_PATH` | Path to the ONNX Runtime shared library. Required unless passed to `Init()`. |
| `PIPER_DEFAULT_MODEL` | Default model path when `--model` is not specified. |
| `PIPER_DEFAULT_CONFIG` | Default config.json path. Used when no explicit config is provided and no sidecar/directory config is found. |
| `PIPER_MODEL_DIR` | Override the default model cache directory for `ModelManager`. |

## Error Types / エラー型

| Type | Description |
|------|-------------|
| `ModelLoadError` | Model loading failure (wraps underlying error). |
| `ConfigError` | Configuration file error (missing, invalid JSON, validation). |
| `InferenceError` | ONNX Runtime inference error. |
| `PhonemeError` | Phonemization error for a specific language/phoneme. |
| `PhonemeIDNotFoundError` | Missing phoneme in the ID map. |

**Sentinel errors:**

| Error | Description |
|-------|-------------|
| `ErrModelClosed` | Voice has been closed. |
| `ErrEmptyText` | Empty text passed to Synthesize. |
| `ErrEmptyPhonemeIDs` | Empty phoneme_ids passed to inference. |
| `ErrUnsupportedLang` | Unsupported language code. |
| `ErrPoolClosed` | VoicePool has been closed. |

## Project Structure / プロジェクト構造

```
src/go/
  go.mod                          # Module: github.com/ayutaz/piper-plus/src/go
  go.sum
  cmd/
    piper-plus/
      main.go                     # CLI application (cobra)
  piperplus/
    doc.go                        # Package documentation
    init.go                       # Init() / Shutdown() — ONNX Runtime lifecycle
    voice.go                      # Voice type, LoadVoice(), Close()
    synthesize.go                 # Synthesize(), phonemizer integration
    engine.go                     # OnnxEngine — ONNX session management
    options.go                    # LoadOption, SynthesisOption (functional options)
    config.go                     # VoiceConfig, LoadConfig(), FindConfigPath()
    device.go                     # DeviceType, ParseDevice(), GPU provider setup
    wav.go                        # SynthesisResult, WAV encoding, peak normalization
    streaming.go                  # AudioSink, SynthesizeStream(), crossfade
    pool.go                       # VoicePool — concurrent session pooling
    server.go                     # HTTP TTS server
    jsonl.go                      # JSONL input parsing
    text_splitter.go              # SplitSentences() — multilingual sentence splitting
    timing.go                     # Phoneme timing (DurationsToTiming)
    model_manager.go              # ModelManager — download, cache, discovery
    errors.go                     # Error types and sentinel errors
    *_test.go                     # Unit tests
    testdata/                     # Test fixtures (config JSONs)
  phonemize/
    phonemizer.go                 # Phonemizer interface, TokensToIDs, PostProcessIDs
    multilingual.go               # MultilingualPhonemizer — language routing
    unicode_detect.go             # UnicodeLanguageDetector — script-based detection
    pua.go                        # PUA (Private Use Area) token mapping
    dict.go                       # Dictionary-based G2P
    english.go                    # English phonemizer
    japanese.go                   # Japanese phonemizer
    chinese.go                    # Chinese phonemizer
    spanish.go                    # Spanish phonemizer
    french.go                     # French phonemizer
    portuguese.go                 # Portuguese phonemizer
    swedish.go                    # Swedish phonemizer
    *_test.go                     # Unit tests
  docker/
    Dockerfile                    # Multi-stage build (Go + ONNX Runtime)
    .dockerignore
  examples/
    basic/                        # Basic synthesis example
    batch/                        # Batch processing example
    pool/                         # VoicePool concurrency example
    server/                       # HTTP server example
    streaming/                    # Streaming synthesis example
```

## Config Resolution / 設定ファイルの探索順序

When no explicit config path is provided, `LoadVoice` searches in this order:

1. `--config` flag or `WithConfig()` option (must exist)
2. `PIPER_DEFAULT_CONFIG` environment variable (if set and file exists)
3. `{modelPath}.json` sidecar (e.g., `model.onnx.json`)
4. `{modelDir}/config.json`

## License / ライセンス

MIT
