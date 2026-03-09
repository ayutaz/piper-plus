![Piper logo](etc/logo.png)

English | [日本語](README.md) | [中文](README_ZH.md) | [Français](README_FR.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
[![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-orange)](https://huggingface.co/ayousanz/piper-plus-base)

A fast, high-quality neural text-to-speech (TTS) system. Built on the [VITS](https://github.com/jaywalnut310/vits/) architecture with multi-speaker support for Japanese and English. A fork of [Piper](https://github.com/rhasspy/piper) with significantly enhanced Japanese support, improved voice quality, and advanced training features.

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

- **Japanese TTS** — OpenJTalk integration, prosody features (A1/A2/A3), question markers (#204), context-dependent "N" variants (#207)
- **English TTS** — GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), no espeak-ng dependency
- **Multi-speaker** — 20+ speakers, SpeakerBalancedBatchSampler
- **Custom Dictionary** — 200+ built-in technical term pronunciations — [Guide](docs/features/custom_dictionary.md)
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
- **PyPI** — `pip install piper-tts-plus`

### Platforms

| Platform | Architecture | Notes |
|---|---|---|
| Linux | x86_64 / ARM64 | Full support |
| macOS | ARM64 (Apple Silicon) only | M1/M2/M3+ |
| Windows | x64 | Full support |
| Web | WebAssembly | Chrome/Edge/Firefox/Safari |

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
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav
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
pip install piper-tts-plus
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

---

## Usage

### C++ CLI

```sh
# Basic usage
echo "Hello world" | ./piper --model en_model.onnx --output_file output.wav

# Streaming (low latency)
echo "Long text..." | ./piper --model en_model.onnx --output_file output.wav --streaming

# GPU inference
echo "Hello" | ./piper --model en_model.onnx --use-cuda --output_file output.wav

# Phoneme timing output (for lip-sync, subtitles)
echo "Hello world" | ./piper --model en_model.onnx -f speech.wav --output-timing timing.json

# Custom dictionary
echo "DockerとGitHubを使います" | ./piper --model ja_model.onnx --custom-dict my_dict.json -f output.wav

# Inline phoneme input
echo 'Hello [[ h ə l oʊ ]] world' | ./piper --model en_model.onnx -f output.wav

# Raw phoneme input
echo 'h ə l oʊ _ w ɜː l d' | ./piper --model en_model.onnx --raw-phonemes -f output.wav

# Streaming raw audio output
echo 'Long text...' | ./piper --model en_model.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

Key options:

| Option | Description | Default |
|---|---|---|
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

Run `piper --help` for all options.

### JSON Input

Use `--json-input` flag for JSON input:

```json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
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

Multi-GPU automatically configures DDP (Distributed Data Parallel). NCCL environment variables are required. See [Multi-GPU Training Guide](docs/guides/training/multi-gpu-training.md).

### ONNX Export

```bash
# Standard model
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt /path/to/output.onnx

# WavLM model (--stochastic required)
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
```

### Checkpoint Management

- `--resume_from_checkpoint` — Resume training from checkpoint
- `--resume_from_single_speaker_checkpoint` — Convert single-speaker to multi-speaker model

### Voice Evaluation

MCD, PESQ, and UTMOS evaluation tools are available in `scripts/evaluation/`.

---

## Pre-trained Models

Pre-trained base models for Japanese TTS fine-tuning are available on Hugging Face.

| Model | Description | License |
|---|---|---|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | Japanese TTS base model (VITS + WavLM + Prosody) | CC-BY-SA-4.0 |
| [piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | Tsukuyomi-chan fine-tuned model | See model card |

**piper-plus-base features:**

- Architecture: VITS + WavLM Discriminator
- Training data: 60,164 utterances (20 speakers)
- Sample rate: 22,050 Hz
- Prosody Features: A1/A2/A3 prosody information
- Extended phonemes: Question markers, context-dependent "N" variants (65 phonemes)

Upstream Piper checkpoints also available: [piper-checkpoints](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)

---

## Japanese TTS

High-quality Japanese speech synthesis with OpenJTalk integration. Dictionary and voice files are automatically downloaded on first run.

**Environment Variables (optional):**

| Variable | Description |
|---|---|
| `OPENJTALK_DICTIONARY_PATH` | OpenJTalk dictionary path (auto-downloads if not set) |
| `PIPER_AUTO_DOWNLOAD_DICT` | Set to `0` to disable auto-download |
| `PIPER_OFFLINE_MODE` | Set to `1` for offline mode |

See [Japanese Usage Guide](docs/guides/japanese/japanese-usage.md) and [Phoneme Mapping Reference](docs/api-reference/phoneme-mapping.md).

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

[Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md) · [Rhasspy 3](https://github.com/rhasspy/rhasspy3/) · [NVDA](https://www.nvaccess.org/post/in-process-8th-may-2023/#voices) · [Open Voice OS](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper) · [LocalAI](https://github.com/go-skynet/LocalAI) · [JetsonGPT](https://github.com/shahizat/jetsonGPT) · [mintPiper](https://github.com/evuraan/mintPiper) · [Vim-Piper](https://github.com/wolandark/vim-piper)

---

## Documentation

| Category | Links |
|---|---|
| Japanese TTS | [Japanese Usage Guide](docs/guides/japanese/japanese-usage.md) |
| Training | [Training Guide](docs/guides/training/training-guide.md) · [Multi-GPU](docs/guides/training/multi-gpu-training.md) |
| API | [Phoneme Mapping](docs/api-reference/phoneme-mapping.md) · [Environment Variables](docs/getting-started/environment-variables.md) |
| Features | [WebUI](docs/features/webui.md) · [CLI Enhancements](docs/features/cli-enhancements.md) · [Streaming](docs/features/streaming-mode.md) |
| Setup | [Quick Start (Japanese)](docs/getting-started/quick_start_japanese.md) · [Windows](docs/getting-started/windows-setup.md) · [Troubleshooting](docs/getting-started/troubleshooting.md) |
| Docker | [Docker Environments](docker/README.md) |
| WebAssembly | [Technical Details](src/wasm/openjtalk-web/README.md) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

[![A library from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-library.png)](https://www.openhomefoundation.org/)
