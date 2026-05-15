![Piper logo](etc/logo.png)

English | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md) | [Русский](README_RU.md) | [Svenska](README_SV.md) | [हिन्दी](README_HI.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

> **🔑 The only MIT-licensed Piper fork** — The original [rhasspy/piper](https://github.com/rhasspy/piper) was archived in October 2025. [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) has moved to GPL-3.0. piper-plus is the only MIT-compatible fork with no espeak-ng dependency. Custom G2P covers 8 languages (JA/EN/ZH/KO/ES/FR/PT/SV), suitable for commercial and embedded use.

> **📢 v1.12.0 Breaking changes (2026-05):** HiFi-GAN Decoder removed (unified to MB-iSTFT, `--mb-istft` flag retired) / Flask → FastAPI HTTP server / HTS-voice dependency removed (Python runtime only) / Unity UPM moved to a separate repo (`ayutaz/uPiper`) / all .NET projects upgraded to `net10.0` LTS. Details: [docs/migration/v1.11-to-v1.12.md](docs/migration/v1.11-to-v1.12.md)

A fast, high-quality neural text-to-speech (TTS) system. Built on the [VITS](https://github.com/jaywalnut310/vits/) architecture with multi-speaker support for 8 languages (Japanese, English, Mandarin Chinese, Korean, Spanish, French, Portuguese, Swedish). A fork of [Piper](https://github.com/rhasspy/piper) with significantly enhanced Japanese support, improved voice quality, and advanced training features.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (runs in browser, no server needed)

---

## Table of Contents

- [Benchmark](#benchmark)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Training](#training)
- [Pre-trained Models](#pre-trained-models)
- [Platforms](#platforms)
- [Related Links](#related-links)

---

## Benchmark

> **Environment**: Intel Xeon E5-2650 v4 @ 2.20GHz / 48 cores / Linux x86_64 / Python 3.12 / ONNX Runtime 1.24
> **Test text**: "Hello, how are you doing today?" (English, 25 phonemes)
> **Run config**: 5 warmup iterations + 30 measured iterations (intra-op threads = auto)
> **Models used**:
>
> - piper-plus: 6lang MB-iSTFT 75epoch ONNX (unified decoder introduced in PR #320)
> - Piper original: `en_US-lessac-medium` (rhasspy/piper-voices v1.0.0)
> - sherpa-onnx: `vits-piper-en_US-amy-low` (k2-fsa release)
>
> **Reproduce**: `uv run python scripts/benchmark.py --model <model.onnx> --config <config.json> --language en --text "Hello, how are you doing today?" --n-warmup 5 --n-runs 30 --format markdown`

| System | RTF ↓ | Latency P50 (ms) | Size (MB) | RAM (MB) | Cold Start (ms) | Parameters | Languages | License |
|--------|-------|------------------|-----------|---------|-----------------|-----------|-----------|---------|
| **piper-plus (MB-iSTFT)** | **0.078** | **27** | **38** | **208** | **1633** | **19.6 M** | **8** | **MIT** |
| Piper original (archived) | 0.066 | 35 | 60 | 185 | 2510 | 15.7 M | 1/model | MIT |
| sherpa-onnx (VITS Piper-fmt) | 0.075 | 53 | 60 | 202 | 2554 | 15.6 M | 1/model | Apache-2.0 |
| piper1-gpl (OHF fork) † | 0.06 | — | 75 | 150 | 400 | — | 1/model | GPL-3.0 |
| Kokoro-82M † | 0.12 | — | 320 | 450 | 800 | — | 1 | Apache-2.0 |
| eSpeak-NG † | 0.001 | — | 2 | 15 | 10 | — | 100+ | GPL-3.0 |

> **Note**: RTF (Real-Time Factor) — lower is faster. `Latency P50` is the median single-inference time and is the most direct measure of responsiveness. piper-plus's MB-iSTFT unified decoder achieves the lowest P50 (27 ms; -23% vs. Piper original at 35 ms, -49% vs. sherpa-onnx at 53 ms) at the smallest model size (38 MB). It is also -38% faster than the previous piper-plus HiFi-GAN baseline (P50 43.3 ms).
>
> **†** rows were not re-measured in this PR (`piper1-gpl` shares architecture and ONNX I/O with Piper original, so it should be roughly equivalent to the Piper original row; `Kokoro-82M` uses a different architecture and `eSpeak-NG` is a non-neural CLI, neither of which fits the tensor contract that `scripts/benchmark.py` assumes — they would need separate harnesses). Their values are from prior benchmarks taken on Apple M2 Max.

---

## Key Features

### Speech Synthesis

- **8-Language Support** — Japanese, English, Mandarin Chinese, Spanish, French, Portuguese, Swedish, Korean (language codes: ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7) *Trained model covers 6 languages (JA/EN/ZH/ES/FR/PT)*
- **Japanese TTS** — OpenJTalk integration, prosody features (A1/A2/A3), question markers (#204), context-dependent "N" variants (#207)
- **English TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), no espeak-ng dependency
- **Multi-speaker** — 571 speakers in 6-language base model (code supports 8 languages including Swedish and Korean), SpeakerBalancedBatchSampler with language-balanced sampling
- **Custom Dictionary** — 200+ built-in technical term pronunciations
- **Phoneme Input** — Direct phoneme specification with `[[ phonemes ]]` notation — [Guide](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS +0.15-0.25 improvement (enabled by default, training only)
- **MB-iSTFT-VITS2 Decoder** — VITS decoder uses MB-iSTFT + PQMF, delivering ~2.21x faster CPU inference. ONNX-compatible with existing runtimes
- **FP16 Mixed Precision** — 2-3x faster training, ~50% memory reduction (enabled by default)
- **EMA** — Exponential Moving Average for training stability (enabled by default)
- **Multi-GPU** — DDP support, automatic learning rate scaling
- **Prosody Features** — Prosody injection into Duration Predictor (`--prosody-dim 16`)
- **Wandb Integration** — Real-time metrics monitoring

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inference and training, Docker-ready
- **C++ CLI** — Streaming, CUDA inference, **phoneme timing output (JSON/TSV/SRT)**, custom dictionary
- **[C API Shared Library](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI-ready (Flutter/Godot/Swift etc.), streaming API
- **[iOS xcframework + SPM](docs/guides/ios-integration.md)** — `PiperPlus` Swift Package, synthesis engine shipped as iOS arm64 device + simulator universal xcframework
- **[iOS Swift G2P (SPM)](docs/guides/swift-g2p-integration.md)** — `PiperPlusG2P` standalone Swift Package: 8-language G2P on iOS without ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Fully runs in browser, **phoneme timing output (JSON/TSV/SRT)**, no server
- **[Docker](docker/README.md)** — 5 images for inference, training, WebUI, and C++
- **PyPI (`pip install piper-plus`)** — Easy install, multilingual, **phoneme timing output (JSON/TSV/SRT)**, streaming, HTTP API
- **C# CLI** — .NET 10 cross-platform, 8-language multilingual, ONNX inference, **phoneme timing output (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML support, **phoneme timing output (JSON/TSV/SRT)**, auto dictionary download
- **[Go CLI](src/go/README.md)** — HTTP API server, session pooling, Docker, single binary, **phoneme timing output (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — supported by all 6 runtimes (Python/Rust/C#/Go/WASM/C++). C++ exposes both the CLI binary and the `libpiper_plus` C API shared library. Extract speaker embedding from a reference audio via ECAPA-TDNN (`--reference-audio`).
- **SSML support** — `<speak>`, `<break>`, `<prosody rate="...">` implemented across 4 runtimes (Python/Rust/C#/Go).
- **Short-text quality improvements (Strategy A/B/C)** — silence padding, dynamic scales, SSML `<break>` auto-injection deployed across all 6 runtimes (`docs/spec/short-text-contract.toml`).
- Equivalent 8-language multilingual synthesis across 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++).

---

## Quick Start

### Python Inference

```bash
# Install
uv pip install ".[inference]"

# Japanese inference
uv run python -m piper_train.infer_onnx \
  --model /path/to/model.onnx \
  --config /path/to/config.json \
  --output-dir ./output \
  --text "こんにちは、今日は良い天気ですね。"

# English inference
uv run python -m piper_train.infer_onnx \
  --model /path/to/en_model.onnx \
  --config /path/to/en_model.onnx.json \
  --output-dir ./output \
  --text "Hello, how are you today?" \
  --language en
```

Key options: `--speaker-id` (speaker ID), `--device auto|cpu|gpu`, `--noise-scale` (audio variation), `--noise-scale-w` (phoneme length variation, default: 0.8), `--length-scale` (speech speed)

#### Python CLI Model Management

```bash
# List available models
python -m piper --list-models
python -m piper --list-models ja

# Download a model
python -m piper --download-model tsukuyomi
python -m piper --download-model ja_JP-tsukuyomi-chan-medium

# Use after downloading
python -m piper --model ja_JP-tsukuyomi-chan-medium --text "Hello" -f output.wav
```

### WebUI

```bash
uv pip install -r src/python_run/requirements_webui.txt
cd src/python_run
python -m piper.webui --data-dir /path/to/models
# → http://localhost:7860
```

### Prebuilt Binary (No Build Required)

Download prebuilt binaries from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) and start synthesizing speech immediately.

**1. Download the binary**

Download and extract for your OS:

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-windows-x64.zip" -OutFile piper.zip
Expand-Archive piper.zip -DestinationPath .
cd piper
```

**macOS (Apple Silicon):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-macos-arm64.tar.gz
tar xzf piper.tar.gz
cd piper
xattr -cr .
```

**Linux (x86_64):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-linux-x64.tar.gz
tar xzf piper.tar.gz
cd piper
```

**Linux (ARM64, Raspberry Pi 4/5):**

```bash
curl -L -o piper.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-linux-arm64.tar.gz
tar xzf piper.tar.gz
cd piper
```

**2. Download a model & generate speech**

```sh
# Download the Tsukuyomi-chan model
./bin/piper --download-model tsukuyomi

# Generate speech (just the model name is enough — downloaded models are auto-resolved)
./bin/piper --model tsukuyomi --text "Hello, how are you today?" --output_file output.wav
```

> **Windows cmd code page note:** The `--text` option internally uses `GetCommandLineW()` (UTF-16), so it works regardless of code page. Only when using pipe input (`echo ... | piper`) do you need to switch to UTF-8 first with `chcp 65001`.
>
> **output.wav location:** Generated in the current directory (where you ran `cd piper`).

> **Which binary should I pick?** Releases also include `piper-plus-cli-*` (C# .NET) and `piper-plus-rs-cli-*` (Rust) CLIs. The Quick Start above uses **C++ CLI (`piper-*`)**, which has the widest platform support and is recommended for most users. See [Choosing a CLI binary](docs/getting-started/binary-selection.md) for details.

### Docker

```bash
# WebUI
docker build -t piper-webui -f docker/webui/Dockerfile .
docker run -p 7860:7860 -v ./models:/models:ro piper-webui

# Python inference (CPU)
docker build -t piper-inference -f docker/python-inference/Dockerfile .
docker run --rm \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device cpu

# GPU inference (add --gpus all)
docker run --rm --gpus all \
  -v ./models:/app/models:ro -v ./output:/app/output \
  piper-inference \
  python -m piper_train.infer_onnx \
    --model /app/models/model.onnx --config /app/models/config.json \
    --output-dir /app/output --text "こんにちは" --device gpu
```

Pre-built CI/CD images:

```bash
docker pull ghcr.io/ayutaz/piper-plus/python-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/python-train:dev
docker pull ghcr.io/ayutaz/piper-plus/webui:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:dev
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:dev
```

> **Note:** The webui image is not automatically built by CI. Build manually with: `docker build -t piper-webui -f docker/webui/Dockerfile .`

See [docker/README.md](docker/README.md) for details.

---

## Installation

### Python

Requires Python 3.11+. [uv](https://docs.astral.sh/uv/) is recommended for dependency management.

```bash
# CPU inference
uv pip install ".[inference]"

# GPU inference (requires CUDA)
uv pip install ".[inference-gpu]"

# Training
uv pip install ".[train]"

# Development (includes testing and linting)
uv pip install ".[dev]"
```

Also available from PyPI:

```bash
pip install piper-plus
```

### Install from Package Managers

**Python (PyPI):**

```bash
pip install piper-plus
```

**npm (Browser WASM):**

```bash
npm install piper-plus onnxruntime-web
```

**C# CLI (.NET Global Tool):**

```bash
dotnet tool install -g PiperPlus.Cli
```

**Rust CLI (crates.io):**

```bash
cargo install piper-plus-cli
```

**C# Library (NuGet):**

```bash
dotnet add package PiperPlus.Core
```

**Rust Library (crates.io):**

```toml
[dependencies]
piper-plus = "0.4"
```

### Building from Source

If pre-built binaries aren't available for your platform or you need to modify piper-plus, build from source. See **[Building from Source Guide](docs/guides/building-from-source.md)** for C++, C#, and Rust runtime build instructions.

---

## Usage

For detailed C++ CLI command-line options, JSON input format, model management, environment variables, and Windows helper scripts, see **[CLI Usage Guide](docs/guides/cli-usage.md)**.

Simple example:

```bash
./bin/piper --model tsukuyomi --text "Hello" --output_file hello.wav
```

---

## Training

For training and fine-tuning piper-plus models (basic setup, multi-speaker / multi-GPU, ONNX export, checkpoint management, voice evaluation), see **[Training Guide](docs/guides/training.md)**.

Production-grade pretraining and fine-tuning command templates (6-language pretraining, Tsukuyomi-chan fine-tuning) are in [CLAUDE.md](CLAUDE.md).

---

## Pre-trained Models

For the list of available piper-plus models, download instructions, 6-language base model details, and Japanese TTS specifics, see **[Pre-trained Models Guide](docs/guides/pretrained-models.md)**.

Main models: `tsukuyomi` (Japanese), `multilingual-6lang` (8-language base), `bilingual-ja-en-v4` (Japanese-English) — see HuggingFace [ayousanz/piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) and [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

---

## Platforms

- **macOS**: Apple Silicon (arm64) native support. See [macOS notes](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) for Gatekeeper troubleshooting
- **Windows**: x64 / arm64 supported. For OpenJTalk setup, see [Windows Setup](docs/getting-started/windows-setup.md)
- **WebAssembly**: Fully offline in-browser inference. [Demo](https://ayutaz.github.io/piper-plus/) | [npm package](https://www.npmjs.com/package/piper-plus)

---

## Related Links

### Unity — uPiper

Unity plugin for Piper: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japanese & English, async API, streaming

### piper-plus-g2p (Standalone G2P Package)

Multilingual G2P (Grapheme-to-Phoneme) available as standalone packages:

- **Python**: `pip install piper-plus-g2p` — [Source](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Source](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Source](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Source](src/wasm/g2p/)

### Voices

piper-plus models: [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) (6-language base) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus uses its own G2P and phoneme system, so upstream Piper models (rhasspy/piper-voices) are NOT compatible.

### Articles (Japanese)

- [Creating English Piper Pre-trained Model using LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Creating Piper Japanese Model using JVS Voice Dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Fine-tuning from Piper Model using Tsukuyomi-chan Dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Category | Links |
|---|---|
| Japanese TTS | Japanese Usage Guide |
| Training | [Training Guide](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Phoneme Mapping](docs/api-reference/phoneme-mapping.md) · [Environment Variables](docs/getting-started/environment-variables.md) |
| Features | [WebUI](docs/features/webui.md) · CLI Enhancements · Streaming |
| Setup | Quick Start (Japanese) · [Windows](docs/getting-started/windows-setup.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| Docker | [Docker Environments](docker/README.md) |
| WebAssembly | [Technical Details](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.
