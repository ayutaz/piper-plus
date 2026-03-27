# Piper Plus

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fast, high-quality neural text-to-speech (TTS) system. Built on the [VITS](https://github.com/jaywalnut310/vits/) architecture with multi-speaker support for 6 languages. A fork of [Piper](https://github.com/rhasspy/piper) with significantly enhanced Japanese support, improved voice quality, and advanced training features.

**[Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** | **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** | **[GitHub](https://github.com/ayutaz/piper-plus)**

## Key Features

- **6-Language Support** - Japanese, English, Mandarin Chinese, Spanish, French, Portuguese
- **Japanese TTS** - OpenJTalk integration, prosody features (A1/A2/A3), context-dependent phoneme variants
- **English TTS** - GPL-free G2P ([g2p-en](https://github.com/Kyubyong/g2p), Apache-2.0), no espeak-ng dependency
- **Multi-speaker** - 571 speakers in base model with language-balanced sampling
- **Custom Dictionary** - 200+ built-in technical term pronunciations
- **Phoneme Input** - Direct phoneme specification with `[[ phonemes ]]` notation
- **Cross-platform** - Linux (x86_64/ARM64), macOS (Apple Silicon), Windows (x64)

## Installation

```bash
pip install piper-tts-plus

# GPU support
pip install "piper-tts-plus[gpu]"
```

Requires Python 3.11+.

## Quick Start

### Command Line

```bash
# List available models
piper --list-models
piper --list-models ja

# Download a model
piper --download-model tsukuyomi

# Generate speech
piper --model tsukuyomi --text "Hello, world!" --output_file output.wav
```

### Python API

```python
from piper import PiperVoice

voice = PiperVoice.load("path/to/model.onnx", config_path="path/to/config.json")
wav_bytes = voice.synthesize("Hello, world!")
```

## Pre-trained Models

| Model | Languages | Speakers | Download |
|-------|-----------|----------|----------|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | 6 (ja/en/zh/es/fr/pt) | 571 | `piper --download-model base` |
| [tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | 6 (ja/en/zh/es/fr/pt) | 1 | `piper --download-model tsukuyomi` |

## Supported Languages

| Language | Code | Phonemizer | Dependency |
|----------|------|------------|------------|
| Japanese | ja | OpenJTalk | pyopenjtalk-plus |
| English | en | g2p-en | g2p-en (Apache-2.0) |
| Mandarin Chinese | zh | pypinyin | pypinyin |
| Spanish | es | Rule-based | None |
| French | fr | Rule-based | None |
| Portuguese | pt | Rule-based | None |

## Other Interfaces

Piper Plus is also available as:

- **[C++ CLI](https://github.com/ayutaz/piper-plus/releases)** - Prebuilt binaries with streaming, CUDA inference, custom dictionary
- **[Rust CLI](https://github.com/ayutaz/piper-plus/tree/dev/src/rust)** - Streaming, CUDA/CoreML/DirectML support
- **[C# CLI (.NET)](https://github.com/ayutaz/piper-plus/tree/dev/src/csharp)** - Cross-platform .NET 8/9
- **[WebAssembly](https://ayutaz.github.io/piper-plus/)** - Runs entirely in browser
- **[Docker](https://github.com/ayutaz/piper-plus/tree/dev/docker)** - Inference, training, and WebUI images

## Links

- [GitHub Repository](https://github.com/ayutaz/piper-plus)
- [Hugging Face Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)
- [Hugging Face Models](https://huggingface.co/ayousanz/piper-plus-base)
- [Documentation](https://github.com/ayutaz/piper-plus/tree/dev/docs)

## License

MIT License - see [LICENSE](https://github.com/ayutaz/piper-plus/blob/dev/LICENSE.md) for details.
