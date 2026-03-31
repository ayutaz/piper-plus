![Piper logo](etc/logo.png)

English | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-plus)](https://pypi.org/project/piper-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-plus)](https://pypi.org/project/piper-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

A fast, high-quality neural text-to-speech (TTS) system. Built on the [VITS](https://github.com/jaywalnut310/vits/) architecture with multi-speaker support for 7 languages (Japanese, English, Mandarin Chinese, Spanish, French, Portuguese, Swedish). A fork of [Piper](https://github.com/rhasspy/piper) with significantly enhanced Japanese support, improved voice quality, and advanced training features.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** (runs in browser, no server needed)

---

## Table of Contents

- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Training](#training)
- [Pre-trained Models](#pre-trained-models)
- [Japanese TTS](#japanese-tts)
- [Platforms](#platforms)
- [Related Links](#related-links)

---

## Key Features

### Speech Synthesis

- **7-Language Support** — Japanese, English, Mandarin Chinese, Spanish, French, Portuguese, Swedish (language codes: ja=0, en=1, zh=2, es=3, fr=4, pt=5, sv=6)
- **Japanese TTS** — OpenJTalk integration, prosody features (A1/A2/A3), question markers (#204), context-dependent "N" variants (#207)
- **English TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), no espeak-ng dependency
- **Multi-speaker** — 571 speakers in 6-language base model (code supports 7 languages including Swedish), SpeakerBalancedBatchSampler with language-balanced sampling
- **Custom Dictionary** — 200+ built-in technical term pronunciations
- **Phoneme Input** — Direct phoneme specification with `[[ phonemes ]]` notation — [Guide](docs/features/phoneme-input.md)

### Training

- **WavLM Discriminator** — MOS +0.15-0.25 improvement (enabled by default, training only)
- **FP16 Mixed Precision** — 2-3x faster training, ~50% memory reduction (enabled by default)
- **EMA** — Exponential Moving Average for training stability (enabled by default)
- **Multi-GPU** — DDP support, automatic learning rate scaling
- **Prosody Features** — Prosody injection into Duration Predictor (`--prosody-dim 16`)
- **Wandb Integration** — Real-time metrics monitoring

### Interfaces

- **[WebUI (Gradio)](docs/features/webui.md)** — Inference and training, Docker-ready
- **C++ CLI** — Streaming, CUDA inference, phoneme timing output, custom dictionary
- **[WebAssembly](src/wasm/openjtalk-web/README.md)** — Fully runs in browser, no server
- **[Docker](docker/README.md)** — 5 images for inference, training, WebUI, and C++
- **PyPI** — `pip install piper-plus`
- **C# CLI** — .NET 8/9 cross-platform, 7-language multilingual, ONNX inference
- **Rust CLI** — piper-plus/piper-plus-cli, streaming, CUDA/CoreML/DirectML support, auto dictionary download

### Platforms

| Platform | Architecture | Notes |
|---|---|---|
| Linux | x86_64 / ARM64 | Full support |
| macOS | ARM64 (Apple Silicon) only | M1/M2/M3+ |
| Windows | x64 | Full support |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |
| C# (.NET) | x64 / ARM64 | .NET 8/9, Linux/macOS/Windows |
| Rust | x64 / ARM64 | Linux/macOS/Windows, CUDA/CoreML/DirectML |

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

Key options: `--speaker-id` (speaker ID), `--device auto|cpu|gpu`, `--noise-scale` (audio variation), `--length-scale` (speech speed)

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

### C++ Binary

Download from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) (amd64 / arm64).

```sh
./bin/piper --text 'Welcome to the world of speech synthesis!' \
  --model en_US-lessac-medium.onnx --output_file welcome.wav
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
docker pull ghcr.io/ayutaz/piper-plus/python-inference:main
docker pull ghcr.io/ayutaz/piper-plus/python-train:main
docker pull ghcr.io/ayutaz/piper-plus/webui:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-inference:main
docker pull ghcr.io/ayutaz/piper-plus/cpp-dev:main
```

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
piper-plus = "0.1.0"
```

### Building from Source (C++)

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Prerequisites: C++17 compiler, CMake 3.13+

- **Linux**: Place [piper-phonemize](https://github.com/rhasspy/piper-phonemize) at `lib/Linux-$(uname -m)/piper_phonemize` before building
- **Windows**: See [Windows Setup Guide](docs/getting-started/windows-setup.md)
- **macOS**: Dependencies are downloaded automatically

### Building from Source (C#)

```bash
# C# CLI build
dotnet build src/csharp/PiperPlus.sln -c Release
# Test
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Prerequisites: .NET 8 SDK or later

#### C# CLI Usage Examples

```bash
# Inference with model name (auto-download supported, defaults to output.wav)
piper-plus --model tsukuyomi --text "こんにちは" --language ja

# English
piper-plus --model model.onnx --text "Hello world" --language en

# Multilingual (automatic language detection)
piper-plus --model model.onnx --text "こんにちはHello你好" --language ja-en-zh

# Inline phoneme notation
piper-plus --model model.onnx --text "Hello [[ h ə l oʊ ]] world" --language en

# Streaming (progressive PCM output per sentence)
piper-plus --model model.onnx --text "First sentence. Second sentence." --language en --streaming | aplay -r 22050 -f S16_LE

# Custom dictionary (JSON v1/v2 or TSV)
piper-plus --model model.onnx --text "AI technology" --language en --custom-dict my_dict.json

# Model management
piper-plus --download-model tsukuyomi
piper-plus --list-models ja

# Test mode (verify phoneme IDs without ONNX inference)
piper-plus --model model.onnx --test-mode --text "hello" --language en
```

#### Rust CLI Usage Examples

```bash
# Inference with model name (auto-download supported)
piper-plus-cli --model tsukuyomi --text "こんにちは" --language ja

# English
piper-plus-cli --model model.onnx --text "Hello world" --language en

# Model management
piper-plus-cli --download-model tsukuyomi
piper-plus-cli --list-models ja

# Streaming (sentence-by-sentence synthesis)
piper-plus-cli --model model.onnx --text "First sentence. Second sentence." --stream --output-dir chunks/

# Custom dictionary
piper-plus-cli --model model.onnx --text "AI technology" --custom-dict my_dict.json

# GPU inference
piper-plus-cli --model model.onnx --text "Hello" --device cuda

# Test mode / quiet mode
piper-plus-cli --model model.onnx --test-mode --text "hello" --language en
piper-plus-cli --model model.onnx --text "hello" --language en --quiet

# Raw PCM output (no WAV header)
piper-plus-cli --model model.onnx --text "hello" --language en --output-raw | aplay -r 22050 -f S16_LE
```

> **Note:** Install C# CLI with `dotnet tool install -g PiperPlus.Cli` and Rust CLI with `cargo install piper-plus-cli`. Both support 7 languages, custom dictionaries, and streaming.

### Building from Source (Rust)

```bash
# Rust CLI build
cargo build --release -p piper-plus-cli
# Test
cargo test -p piper-plus
```

Prerequisites: Rust 1.70+, cargo

---

## Usage

### C++ CLI

#### Direct Text Input (Recommended)

The `--text` option allows direct text input without piping:

```sh
# Simple text-to-speech
./bin/piper --model model.onnx --text "Hello, how are you?" -f output.wav

# Japanese text (no encoding issues on Windows)
bin\piper.exe --model models\tsukuyomi.onnx --text "こんにちは、今日は良い天気ですね。" -f output.wav

# With speaker selection
./bin/piper --model model.onnx --text "Hello" --speaker 3 -f output.wav
```

#### Pipe Input

```sh
# Basic usage
echo "Hello world" | ./bin/piper --model en_model.onnx --output_file output.wav

# Streaming (low latency)
echo "Long text..." | ./bin/piper --model en_model.onnx --output_file output.wav --streaming

# GPU inference
echo "Hello" | ./bin/piper --model en_model.onnx --use-cuda --output_file output.wav

# Phoneme timing output (for lip-sync, subtitles)
echo "Hello world" | ./bin/piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Custom dictionary
echo "DockerとGitHubを使います" | ./bin/piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Inline phoneme input
echo 'Hello [[ h ə l oʊ ]] world' | ./bin/piper --model en_model.onnx -f output.wav

# Raw phoneme input
echo 'h ə l oʊ _ w ɜː l d' | ./bin/piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming raw audio output
echo 'Long text...' | ./bin/piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Key options:

| Option | Description | Default |
|---|---|---|
| `--model PATH\|NAME` | Model file path, or model name (auto-resolves downloaded models) | - |
| `--text TEXT` | Direct text input (no piping required) | - |
| `--streaming` | Chunk-based streaming mode | off |
| `--use-cuda` | Enable CUDA GPU inference | off |
| `--gpu-device-id NUM` | GPU device ID | 0 |
| `--length-scale VAL` | Speech speed (smaller = faster) | 1.0 |
| `--noise-scale VAL` | Audio variation control | 0.667 |
| `--noise-w VAL` | Phoneme duration variation | 0.8 |
| `--sentence-silence SEC` | Silence between sentences | 0.2 |
| `--speaker NUM` | Speaker number for multi-speaker models | 0 |
| `--phoneme-silence PHONEME SEC` | Silence duration for specific phonemes | - |
| `--raw-phonemes` | Interpret input as phonemes | off |
| `--output-timing FILE` | Phoneme timing output (JSON/TSV) | - |
| `--custom-dict FILE` | Custom dictionary (comma-separated for multiple) | - |
| `--json-input` | JSON input mode | off |
| `--list-models [LANG]` | List available models | - |
| `--download-model NAME` | Download a model | - |
| `--model-dir DIR` | Model download directory | - |
| `--version` | Show version | - |

Run `piper --help` for all options.

### JSON Input

Use `--json-input` flag for JSON input:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```

### Model Management

#### List Available Models

```bash
# List all available models
./bin/piper --list-models

# Filter by language
./bin/piper --list-models ja
./bin/piper --list-models en
```

#### Download Models

```bash
# Download a model by name (aliases also work)
./bin/piper --download-model tsukuyomi
./bin/piper --download-model en_US-lessac-medium

# Specify download directory
./bin/piper --download-model tsukuyomi --model-dir /path/to/models

# After download, use by model name (no full path needed)
./bin/piper --model tsukuyomi --text "こんにちは"
```

### Environment Variables (C++ CLI)

| Variable | Description | Example |
|---|---|---|
| `PIPER_DEFAULT_MODEL` | Default model path when `--model` is not specified | `/path/to/model.onnx` |
| `PIPER_DEFAULT_CONFIG` | Default config path when `--config` is not specified | `/path/to/config.json` |
| `PIPER_MODEL_DIR` | Directory for downloaded models | `~/.local/share/piper/models` |
| `PIPER_GPU_DEVICE_ID` | GPU device ID for CUDA | `0` |

### Helper Scripts (Windows)

For Windows users, helper scripts are provided in the `scripts/` directory:

**PowerShell:**

```powershell
.\scripts\speak.ps1 "こんにちは、今日は良い天気ですね。"
.\scripts\speak.ps1 -Model "models\tsukuyomi.onnx" -Text "テスト"
```

**Command Prompt:**

```cmd
scripts\speak.bat "こんにちは、今日は良い天気ですね。"
scripts\speak.bat --model models\tsukuyomi.onnx "テスト"
```

---

## Training

See the [Training Guide](docs/guides/training/training-guide.md) for detailed instructions.

### Basic

```bash
uv pip install ".[train]"

uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --accelerator gpu --devices 1 --precision 16-mixed \
  --max_epochs 200 --batch-size 16 \
  --quality medium \
  --prosody-dim 16 \
  --ema-decay 0.9995
```

### Multi-speaker / Multi-GPU

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995
```

Multi-GPU automatically configures DDP (Distributed Data Parallel). NCCL environment variables are required. See the Multi-GPU Training Guide for details.

### ONNX Export

FP16 conversion is applied by default, reducing model size by ~50%. Use `--no-fp16` to disable.

```bash
# Standard model (FP16 by default)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# Full precision (FP32)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-fp16 /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM model (--stochastic required)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Checkpoint Management

- `--resume_from_checkpoint` — Resume training from checkpoint
- `--resume_from_single_speaker_checkpoint` — Convert single-speaker to multi-speaker model
- `--resume-from-multispeaker-checkpoint` — Convert multi-speaker to single-speaker for fine-tuning (auto-enables `--freeze-dp`)

### Voice Evaluation

MCD, PESQ, and UTMOS evaluation tools are available in `scripts/evaluation/`.

---

## Pre-trained Models

Pre-trained models for multilingual TTS and fine-tuning are available on Hugging Face.

**Inference Models (ready to use):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| Tsukuyomi-chan 6lang | JA/EN/ZH/ES/FR/PT | 1 | Tsukuyomi-chan voice, 6-language, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) |
| CSS10 Japanese 6lang | JA/EN/ZH/ES/FR/PT | 1 | CSS10 Japanese voice, 6-language, FP16 | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-css10-ja-6lang) |

**Base Models (for fine-tuning):**

| Model | Languages | Speakers | Description | Download |
|---|---|---|---|---|
| 6-Language Base | JA/EN/ZH/ES/FR/PT | 571 | Multilingual pre-trained (508,187 utterances, VITS + Prosody) | [HuggingFace](https://huggingface.co/ayousanz/piper-plus-base) |

**6-Language Base Model features:**

- Architecture: VITS + Prosody Features
- Training data: 508,187 utterances (571 speakers across 6 languages)
- Languages: Japanese (20 speakers), English (310 speakers), Mandarin Chinese (142 speakers), Spanish (63 speakers), French (28 speakers), Portuguese (8 speakers)
- Language codes: ja=0, en=1, zh=2, es=3, fr=4, pt=5
- Sample rate: 22,050 Hz
- Phonemes: 173 symbols (unified multilingual phoneme inventory)
- Prosody Features: A1/A2/A3 prosody information (Japanese)
- Extended phonemes: Question markers, context-dependent "N" variants

> **Note:** piper-plus has custom architecture extensions (multilingual embeddings, Prosody A1/A2/A3, 173 symbols) that make it incompatible with upstream Piper checkpoints/ONNX models. Please use piper-plus specific models.

---

## Japanese TTS

High-quality Japanese speech synthesis with OpenJTalk integration. Dictionary and voice files are automatically downloaded on first run.

**Environment Variables (optional):**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk dictionary path (auto-downloads if not set) |
| `PIPER_AUTO_DOWNLOAD_DICT` | Set to `0` to disable auto-download |
| `PIPER_OFFLINE_MODE` | Set to `1` for offline mode |

See the Japanese Usage Guide and [Phoneme Mapping Reference](docs/api-reference/phoneme-mapping.md).

---

## Platforms

### macOS

**Apple Silicon (M1/M2/M3+) only.** Intel Mac users should use Docker or build from source.

For security warnings on first run:

```bash
xattr -cr piper/
```

### Windows

The espeak-ng-data directory is required. See [Windows Setup Guide](docs/getting-started/windows-setup.md) for details.

```cmd
set ESPEAK_DATA_PATH=C:\path\to\espeak-ng-data
piper.exe --model en_US-lessac-medium.onnx -f output.wav
```

### WebAssembly

Japanese TTS running directly in browsers. No server needed, offline capable.

- **[Online Demo](https://ayutaz.github.io/piper-plus/)**
- **[Technical Details & Integration Guide](src/wasm/openjtalk-web/README.md)**

---

## Related Links

### Unity — uPiper

Unity plugin for Piper: [github.com/ayutaz/uPiper](https://github.com/ayutaz/uPiper)

- Unity 6000.0.35f1+, Unity.InferenceEngine
- Windows / macOS (Apple Silicon) / Linux / Android
- Japanese & English, async API, streaming

### Voices

Upstream Piper voice models (30+ languages) are also available: [piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0)

Each voice requires a `.onnx` model and `.onnx.json` config file. [Voice samples](https://rhasspy.github.io/piper-samples) | [Video tutorial](https://youtu.be/rjq5eZoWWSo)

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
| WebAssembly | [Technical Details](src/wasm/openjtalk-web/README.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.
