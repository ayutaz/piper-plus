![Piper logo](etc/logo.png)

English | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md) | [한국어](README_KO.md) | [Español](README_ES.md) | [Português](README_PT.md) | [Deutsch](README_DE.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1)
[![Try in Browser](https://img.shields.io/badge/Try%20in%20Browser-WebAssembly-blueviolet)](https://ayutaz.github.io/piper-plus/)

**Packages:**

[![PyPI](https://img.shields.io/pypi/v/piper-plus?label=PyPI%3A%20piper-plus&color=blue)](https://pypi.org/project/piper-plus/)
[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core?label=NuGet%3A%20PiperPlus.Core&color=blue)](https://www.nuget.org/packages/PiperPlus.Core/)
[![crates.io](https://img.shields.io/crates/v/piper-plus-g2p?label=crates.io%3A%20piper-plus-g2p&color=orange)](https://crates.io/crates/piper-plus-g2p)
[![npm](https://img.shields.io/npm/v/piper-plus?label=npm%3A%20piper-plus&color=cb3837)](https://www.npmjs.com/package/piper-plus)
[![Maven Central](https://img.shields.io/maven-central/v/io.github.ayutaz/piper-plus-g2p-android?label=Maven%20Central%3A%20piper-plus-g2p-android&color=blue)](https://central.sonatype.com/artifact/io.github.ayutaz/piper-plus-g2p-android)

> **🔑 The only MIT-licensed Piper fork** — The original [rhasspy/piper](https://github.com/rhasspy/piper) was archived in October 2025. [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) has moved to GPL-3.0. piper-plus is the only MIT-compatible fork with no espeak-ng dependency. Its own G2P implementation covers 8 languages (JA/EN/ZH/KO/ES/FR/PT/SV), making it suitable for commercial and embedded use.

> **📢 v2.0.0 Breaking changes:** Default Docker images use CUDA 12.8 + Ubuntu 24.04 + Python 3.13 (host NVIDIA driver **R570+** required). Training uses torch **2.11.0** + CUDA 12.8, with TF32 + bf16-mixed enabled by default. Resuming torch 2.2 checkpoints is unsupported. Python imports and CLI are now `piper_plus` and `piper-plus`. To upgrade from 1.13.0 to the current public release, run `pip install --upgrade "piper-plus[cpu]==2.0.2"`. See the [migration guide](docs/migration/v1.12-to-v2.0.md).

A fast, high-quality neural text-to-speech (TTS) system. Built on the [VITS](https://github.com/jaywalnut310/vits/) architecture, it supports G2P/phonemization in 8 languages and multi-speaker synthesis with current trained models in 6 languages. A fork of [Piper](https://github.com/rhasspy/piper) with significantly enhanced Japanese support, improved voice quality, and expanded training features.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (runs in the browser, no server needed)

---

## Table of Contents

- [Benchmark](#benchmark)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Training](#training-1)
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

> **Note**: RTF (Real-Time Factor) — lower is faster. `Latency P50` is the median single-inference time and is the most direct measure of responsiveness. piper-plus's MB-iSTFT unified decoder achieves the lowest P50 (27 ms; -23% vs. Piper original at 35 ms, -49% vs. sherpa-onnx at 53 ms) at one of the smallest model sizes (38 MB). It is also -38% faster than the previous piper-plus HiFi-GAN baseline (P50 43.3 ms).
>
> **†** rows were not re-measured in this PR (`piper1-gpl` shares architecture and ONNX format with Piper original, so it should be roughly equivalent to the Piper original row; `Kokoro-82M` uses a different architecture and `eSpeak-NG` is a non-neural CLI, neither of which fits the tensor contract that `scripts/benchmark.py` assumes — they would need separate harnesses). Their values are from prior benchmarks taken on Apple M2 Max.

### Multi-Runtime RTF Benchmark (Latest Results)

We publish the latest RTF and latency results measured across 6 runtimes (Python / Rust / Go / C# / C++ / WASM) with `multilingual-test-medium.onnx`. The results are updated automatically on every merge into the dev branch.

👉 **[Multi-Runtime RTF Benchmark](https://ayutaz.github.io/piper-plus/bench/multi-runtime/)**

---

## Key Features

### Speech Synthesis

- **8-Language G2P/phonemization** — Japanese, English, Mandarin Chinese, Spanish, French, Portuguese, Swedish, Korean (ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6, ko=7). Current trained models cover 6 languages (JA/EN/ZH/ES/FR/PT)
- **Japanese TTS** — OpenJTalk integration, prosody features (A1/A2/A3), question markers (#204), context-dependent "N" variants (#207)
- **English TTS** — v2.0.2 bundles G2P based on [g2p-en](https://github.com/Kyubyong/g2p), with Apache-2.0 inference code and the Tacotron MIT notice. No external `g2p-en`/`Distance` or espeak-ng is needed. Older PyPI 2.0.1 metadata is unchanged. See the [migration guide](docs/migration/python-g2p-license.md)
- **Multi-speaker** — 571 speakers (training base model), SpeakerBalancedBatchSampler, language-balanced sampling
- **Custom Dictionary** — 200+ built-in technical term pronunciations
- **Phoneme Input** — Direct phoneme specification with `[[ phonemes ]]` notation — [Guide](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS +0.15-0.25 improvement (enabled by default, training only)
- **MB-iSTFT-VITS2 Decoder** — Decoder unified on MB-iSTFT + PQMF, 2.21x faster CPU inference. ONNX format unchanged, compatible with existing runtimes
- **BF16 Mixed Precision** — `--precision bf16-mixed` is the default (TF32 is also enabled by default). Numerically more stable than FP16, with no loss scaling needed. On GPUs without BF16 support (T4, etc.), specify `--precision 16-mixed`
- **EMA** — Exponential Moving Average for training stability (enabled by default)
- **Multi-GPU** — DDP support, automatic learning rate scaling
- **Prosody Features** — Prosody injection into the Duration Predictor (`--prosody-dim 16`)
- **Wandb Integration** — Real-time metrics monitoring

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inference and Docker support. The local Training Tab still sends obsolete CLI arguments; use the [Training Guide](docs/guides/training/training-guide.md) for training.
- **C++ CLI** — Streaming, CUDA inference, **phoneme timing output (JSON/TSV/SRT)**, custom dictionary
- **[C API Shared Library](examples/c-api/README.md)** — `libpiper_plus.so/.dylib/.dll`, FFI-ready (Flutter/Godot/Swift etc.), streaming API
- **[iOS xcframework + SPM](docs/guides/platform/ios-integration.md)** — `PiperPlus` (Swift Package), synthesis engine shipped as an iOS arm64 device + simulator universal xcframework
- **[iOS Swift G2P (SPM)](docs/guides/platform/swift-g2p-integration.md)** — `PiperPlusG2P` standalone library: 8-language G2P on iOS without ONNX Runtime (Issue #387)
- **[WebAssembly](src/wasm/openjtalk-web/README.npm.md)** — Fully runs in the browser, **phoneme timing output (JSON/TSV/SRT)**, no server needed
- **[Docker](docker/README.md)** — 6 images for inference, training, WebUI, C++ (inference/development), and Wyoming (Home Assistant)
- **PyPI** — Easy install with `pip install piper-plus`, 8-language G2P/phonemization (current trained models cover 6 languages), **phoneme timing output (JSON/TSV/SRT)**, streaming, HTTP API
- **C# CLI** — .NET 10 cross-platform, 8-language G2P/phonemization (current trained models cover 6 languages), ONNX inference, **phoneme timing output (JSON/TSV/SRT)**
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML support, **phoneme timing output (JSON/TSV/SRT)**, automatic dictionary download
- **[Go CLI](src/go/README.md)** — HTTP API server, session pooling, Docker support, single binary, **phoneme timing output (JSON/TSV/SRT)**
- **Voice Cloning (Speaker Encoder + speaker_embedding)** — All 6 runtimes (Python/Rust/C#/Go/WASM/C++) accept model-compatible precomputed `speaker_embedding` input. The C++ CLI and C API accept precomputed embeddings only; extraction via `--reference-audio` is not implemented. Public `zs-v1` inference was functionally verified only with Python `piper-plus==2.0.0`. Public CI run `38189966578` confirmed six-runtime inference from shared Python phoneme IDs; native G2P and human listening quality are outside its scope, and quality approval has not been granted.
- **SSML support** — The SSML parser contract is implemented in Python/Rust/Go/C#/WASM/C++. Synthesis supports it in Python/Rust/Go/WASM/C++; C# Core includes the parser, but the CLI `--text` path is not connected to it. C++ is exposed through CLI `--ssml` (not exported by the C API).
- **Short-text quality improvements (Strategy A/B/C)** — Strategies A/B are implemented in each runtime. Strategy C (automatic SSML `<break>` injection) covers Python inference/Rust/Go/C#; training Python, WASM, and C++ are out of scope. See the [short-text contract](docs/spec/short-text-contract.toml) for details.

### Runtime Feature Support

All 6 runtimes (Python/Rust/C#/Go/JS-WASM/C++) synthesize the 6 languages of the current trained models and also provide 8-language G2P/phonemization. Phoneme timing, streaming (including sentence splitting), Voice Cloning with model-compatible precomputed embeddings, and custom dictionaries are supported as runtime features. C++ accepts precomputed embeddings only, and `--reference-audio` is not implemented. Public `zs-v1` inference was verified only with Python `piper-plus==2.0.0`. Public CI run `38189966578` confirms six-runtime inference from shared Python phoneme IDs, but native G2P and human listening quality are outside its scope, and quality approval has not been granted. SSML synthesis is supported in Python/Rust/Go/WASM/C++ (C++ via CLI `--ssml`, not exported by the C API). The C# Core parser is not connected to CLI `--text`, and the HTTP API is available in 2 runtimes (Python/Go).

---

## Quick Start

### Prebuilt Binary (No Build Required)

Download prebuilt binaries from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) and start synthesizing speech right away.

**1. Download the binary**

Download and extract the archive for your OS.

**Windows (PowerShell):**

```powershell
Invoke-WebRequest -Uri "https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-windows-x64.zip" -OutFile piper-plus-cpp.zip
Expand-Archive piper-plus-cpp.zip -DestinationPath .
cd piper-plus
```

**macOS (Apple Silicon):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-macos-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
xattr -cr .
```

**Linux (x86_64):**

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-x64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARM64, Raspberry Pi 4/5):**

**ARM64 compatibility:** The v2.0.2 Linux ARM64 C++ archive is checked against a glibc 2.31 ABI ceiling. Startup and Japanese synthesis are validated under QEMU on Debian Bullseye / Bookworm / Trixie (64-bit). Raspberry Pi hardware and Raspberry Pi OS itself remain untested. The older v2.0.1 archive requires glibc 2.38 or later, so use v2.0.2.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-arm64.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**Linux (ARMv7, 32-bit ARM):**

The ARMv7 release provides the C++ CLI only. CI verifies the build and Japanese synthesis on Debian Trixie (32-bit ARM) under QEMU. Raspberry Pi hardware remains untested.

```bash
curl -L -o piper-plus-cpp.tar.gz https://github.com/ayutaz/piper-plus/releases/latest/download/piper-plus-cpp-linux-armv7.tar.gz
tar xzf piper-plus-cpp.tar.gz
cd piper-plus
```

**2. Download a model & generate speech**

```sh
# Download the Tsukuyomi-chan model
./bin/piper-plus --download-model tsukuyomi

# Generate speech (the model name is enough — downloaded models are resolved automatically)
./bin/piper-plus --model tsukuyomi --text "こんにちは、今日は良い天気ですね。" --output_file output.wav
```

> **Windows cmd code page note:** The `--text` option internally uses `GetCommandLineW()` (UTF-16), so it works regardless of the code page. Only when using pipe input (`echo ... | piper-plus`) do you need to switch to UTF-8 first with `chcp 65001`.
>
> **output.wav location:** Generated in the current directory (where you ran `cd piper-plus`).

> **Which binary should I pick?** Besides `piper-plus-cpp-*` (C++), Releases also include the `piper-plus-cli-*` (C# .NET) and `piper-plus-rs-cli-*` (Rust) CLIs. The **C++ CLI (`piper-plus-cpp-*`)** used in the Quick Start above supports the most platforms and is recommended. See [Choosing a CLI binary](docs/getting-started/binary-selection.md) for details.

### Python Inference

```bash
# Install
# Run from the repository root of a source checkout
uv sync --extra inference

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

Key options: `--speaker-id` (speaker ID), `--device auto|cpu|gpu`, `--noise-scale` (audio variation), `--length-scale` (speech speed), `--noise-scale-w` (phoneme length variation, default: 0.5)

> **Recommended setting for WavLM models:** Models trained with the WavLM Discriminator (such as Tsukuyomi-chan) sound best with `--noise-scale 0.5` (the default is 0.4).

#### Python CLI Model Management

```bash
# List available models
uv run --no-sync python -m piper_plus --list-models
uv run --no-sync python -m piper_plus --list-models ja

# Download a model
uv run --no-sync python -m piper_plus --download-model tsukuyomi
uv run --no-sync python -m piper_plus --download-model ja_JP-tsukuyomi-chan-medium

# Use after downloading
uv run --no-sync python -m piper_plus --model ja_JP-tsukuyomi-chan-medium -f output.wav "こんにちは"
```

### WebUI

```bash
uv sync --project environments/webui --locked
uv run --project environments/webui --no-sync python -m piper_plus.webui --data-dir /path/to/models
# → http://localhost:7860
```

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
docker pull ghcr.io/ayutaz/piper-plus/wyoming:dev
```

See [docker/README.md](docker/README.md) for details.

---

## Installation

### Python

Python 3.13+ recommended (3.11+ supported). [uv](https://docs.astral.sh/uv/) is recommended for dependency management.

```bash
# CPU inference
uv sync --extra inference

# GPU inference (requires a CUDA environment)
uv sync --no-group cpu --extra inference-gpu

# Training
uv sync --extra train

# Development (includes tests and linters)
uv sync --extra dev
```

Also installable from the PyPI package:

```bash
pip install piper-plus
```

### Install from Packages

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
piper-plus = "0.5"
```

### Building from Source

If prebuilt binaries are not available for your platform or you want to modify piper-plus, you can build from source. See the **[Building from Source Guide](docs/guides/development/building-from-source.md)** for build instructions for the C++ / C# / Rust runtimes.

---

## Usage

For detailed C++ CLI command-line options, the JSON input format, model management, environment variables, and the Windows helper scripts, see the **[CLI Usage Guide](docs/guides/development/cli-usage.md)**.

Simple example:

```bash
./bin/piper-plus --model tsukuyomi --text "こんにちは" --output_file hello.wav
```

---

## Training

For how to train and fine-tune piper-plus models (basic setup, multi-speaker / multi-GPU, ONNX export, checkpoint management, voice evaluation), see the **[Training Guide](docs/guides/training/training-guide.md)**.

Production command templates for 6-language pretraining and Tsukuyomi-chan fine-tuning are in [CLAUDE.md](CLAUDE.md).

---

## Pre-trained Models

For the list of published piper-plus models, download instructions, features of the 6-language base model, and Japanese TTS details, see the **[Pre-trained Models Guide](docs/guides/development/pretrained-models.md)**.

Main models: `tsukuyomi` (Japanese), `zs-v1` (experimental 6-language Zero-Shot/FT base), `bilingual-ja-en-v4` (Japanese-English bilingual) — for details, see the pinned HuggingFace [zs-v1 bundle](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) and [ayousanz/piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).

> **Zero-Shot/FT base (`zs-v1`, 2026-10-10):** The pinned public bundle is the existing v7 epoch 32 experimental base (JA/EN/ZH/ES/FR/PT, 571 speakers, 173 phonemes, CAM++ 192-dim). For Zero-Shot inference, use `base.onnx` with a reference embedding extracted by the bundled `campplus.onnx`; for fine-tuning, use `base.ckpt` with the bundled `config.json`. The public examples were functionally verified with PyPI `piper-plus==2.0.0`, but this does not mean quality approval, a passed human listening test, or the latest/best quality. The `base` / `zero-shot-base-zs-v1` aliases are included in v2.0.2 (not in 2.0.0 / 2.0.1). The root `model.ckpt` is treated separately as a legacy generation.

> **Tsukuyomi-chan FT (`zs-v1`, 2026-10-15):** We published a [pinned public model](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/tree/93c1fb6d67c29accc9ddf52326bb4582b1b52a3d/releases/zs-v1) fine-tuned from the same public base generation. Combining `tsukuyomi.onnx` with `tsukuyomi.onnx.json` generates speech without reference audio or CAM++. A human review of three Japanese sentences was recorded, and publication as an experimental release was approved (`quality_approval=false`; this is not quality approval). The existing `tsukuyomi` alias still selects the legacy root model, so download the new model from the pinned URLs in the [model guide](docs/guides/development/pretrained-models.md).

---

## Platforms

- **macOS**: Native Apple Silicon (arm64) support. See [macOS setup](docs/getting-started/binary-selection.md#macos-開発元を確認できないため開けません) for details
- **Windows**: C++ release assets are x64; the C# CLI is x64 / arm64. For OpenJTalk setup, see the [Windows Setup Guide](docs/getting-started/windows-setup.md)
- **WebAssembly**: Fully offline in-browser execution. [Demo](https://ayutaz.github.io/piper-plus/) | [npm package](https://www.npmjs.com/package/piper-plus)

---

## Related Links

### Unity — uPiper

Unity plugin for Piper: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android support
- Japanese & English support, async API, streaming

### Voices

piper-plus models: [zs-v1 Zero-Shot/FT base](https://huggingface.co/ayousanz/piper-plus-base/tree/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1) · [Tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan)

> **Note:** piper-plus uses its own G2P and phoneme system, so it is not compatible with upstream Piper (rhasspy/piper-voices) models.

### Related Articles (Japanese)

- [Creating an English Piper pre-trained model using LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
- [Creating a Piper Japanese model using the JVS voice dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
- [Fine-tuning a Piper model using the Tsukuyomi-chan dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

### piper-plus-g2p (Standalone G2P Package)

Multilingual G2P (Grapheme-to-Phoneme) is available as standalone packages:

- **Python**: `pip install piper-plus-g2p` — [Source](src/python/g2p/)
- **Rust**: `cargo add piper-plus-g2p` — [Source](src/rust/piper-plus-g2p/)
- **Go**: `go get github.com/ayutaz/piper-plus/src/go/phonemize` — [Source](src/go/phonemize/)
- **JavaScript/WASM**: `npm install @piper-plus/g2p` — [Source](src/wasm/g2p/)
- **Kotlin/Android**: `implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.1")` — [Source](android/piper-plus-g2p/) · [Dictionary distribution guide](docs/guides/platform/android-g2p-dictionary.md)

### People using Piper

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://github.com/nvaccess/nvda/wiki/ExtraVoices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Category | Links |
|---|---|
| Japanese TTS | Japanese speech synthesis guide |
| Training | [Training Guide](docs/guides/training/training-guide.md) · Multi-GPU |
| API | [Phoneme Mapping](docs/api-reference/phoneme-mapping.md) · [Environment Variables](docs/getting-started/environment-variables.md) |
| Features | [WebUI](docs/features/webui.md) · CLI enhancements · Streaming |
| Setup | Quick Start (Japanese) · [Windows](docs/getting-started/windows-setup.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| Docker | [Docker environments](docker/README.md) |
| WebAssembly | [Technical details](src/wasm/openjtalk-web/README.npm.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please send questions and bug reports to [Issues](https://github.com/ayutaz/piper-plus/issues). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the code of conduct.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Acknowledgements

GPU experiments for piper-plus are supported by an AI Builder Grant (GPU credits) from [CloudRift](https://www.cloudrift.ai/).
