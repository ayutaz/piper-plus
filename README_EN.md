![Piper logo](etc/logo.png)

English | [日本語](README.md)

[![CI](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/ayutaz/piper-plus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![Python](https://img.shields.io/pypi/pyversions/piper-tts-plus)](https://pypi.org/project/piper-tts-plus/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Hugging Face Demo](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Demo-blue)](https://huggingface.co/spaces/ayousanz/piper-plus-demo)

A fast, local neural text to speech system that sounds great and is optimized for the Raspberry Pi 4.
Piper is used in a [variety of projects](#people-using-piper).

🎙️ **[Try Piper TTS Demo on Hugging Face](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** - Experience Japanese and English text-to-speech in your browser!

## Table of Contents
- [Additional Features](#additional-features)
- [Related Articles](#related-articles)
- [Platform Support](#platform-support)
  - [Supported Platforms](#supported-platforms)
  - [⚠️ Important: Notice for macOS Users](#️-important-notice-for-macos-users)
- [Voices](#voices)
- [Installation](#installation)
- [Usage](#usage)
  - [Streaming Audio](#streaming-audio)
  - [JSON Input](#json-input)
- [People using Piper](#people-using-piper)
- [Unity Integration - uPiper](#unity-integration---upiper)
- [Pre-trained Models](#pre-trained-models)
- [Training](#training)
- [Running in Python](#running-in-python)

## Additional Features
* **🌐 WebUI (Gradio)** - Easy-to-use browser-based interface
  * 🚀 **[Online Demo](https://huggingface.co/spaces/ayousanz/piper-plus-demo)** - Try it now on Hugging Face Spaces!
  * 🌏 **[WebAssembly Demo](https://ayutaz.github.io/piper-plus/)** - Browser-based Japanese TTS demo (no server required)
  * See [WebUI Usage Guide](docs/features/webui-usage.md) for details
  * Supports both inference and training
  * Multilingual template system (Japanese, English, German, French)
  * Docker-ready for easy deployment
  * Usage example: `python -m piper.webui --data-dir ./models`
* **🎤 Phoneme Input Feature** - Direct phoneme specification using `[[ phonemes ]]` notation
  * See [Phoneme Input Guide](docs/features/phoneme-input.md) for details
  * Usage example: `echo "Hello [[ h ə l oʊ ]] world" | piper --model en.onnx -f out.wav`
  * Japanese example: `echo "今日は [[ ky o o w a ]] です" | piper --model ja.onnx -f out.wav`
* **📚 Custom Dictionary Feature** - Precisely control pronunciation of technical terms and proper nouns
  * See [Custom Dictionary Guide](docs/features/custom_dictionary.md) for details
  * Default dictionary with 200+ technical terms (Docker→docker, GitHub→github, etc.)
  * Usage example: `echo "Using Docker and GitHub" | piper --model en.onnx --custom-dict my_dict.json -f out.wav`
  * Both Python/C++ support, multiple dictionaries can be used simultaneously
* Japanese pre-training and fine-tuning/inference support (OpenJTalk integration)
  * See [Japanese Speech Synthesis Guide](docs/guides/japanese/japanese-usage.md) for detailed usage
  * **Windows Support**: See [Windows Setup Guide](docs/getting-started/windows-setup.md)
  * **API Documentation**: See [OpenJTalk API Reference](docs/guides/japanese/openjtalk-api.md)
  * Improved Japanese TTS accuracy with PUA phoneme mapping - [Technical Details](docs/api-reference/phoneme-mapping.md)
  * **Auto-download Feature**: Automatically downloads required dictionary and HTS voice files on first run
  * Environment variables (optional):
    - `OPENJTALK_DICTIONARY_DIR`: Path to OpenJTalk dictionary (auto-downloads if not set)
    - `OPENJTALK_VOICE`: Path to HTS voice model (.htsvoice) (auto-downloads if not set)
    - `PIPER_AUTO_DOWNLOAD_DICT`: Set to `0` to disable auto-download
    - `PIPER_OFFLINE_MODE`: Set to `1` for offline mode (no network connection required)
  * Existing Japanese models **require no retraining** - only config file updates needed
* Automated builds and binary distribution via GitHub Actions (see [Platform Support](#platform-support))
* Improved training to automatically skip corrupted preprocessed .pt files and continue
* Set `pin_memory=True` in DataLoader to optimize GPU transfers
* Added `--timeout-seconds` to `preprocess.py` to automatically timeout/skip hanging utterances
* Added `--num-workers` to `piper_train` to specify DataLoader worker count from command line
* Added `--save-top-k` to `piper_train` to specify checkpoint save count from command line
* Published as PyPI package `piper-tts-plus` for easy installation via `pip install`
* Added multilingual TTS test infrastructure with automatic CI/CD testing - [Details](docs/guides/testing/multilingual-testing.md)
* Added auto-download functionality for OpenJTalk dictionary and HTS voice models to simplify Japanese TTS setup
* **🌏 WebAssembly Support** - Japanese TTS running directly in browsers
  * Japanese phonemization with OpenJTalk WebAssembly edition
  * Neural speech synthesis with ONNX Runtime WebAssembly
  * Runs completely in-browser without server
  * Compact size: WASM < 400KB, JS < 40KB
  * Details: [OpenJTalk WebAssembly README](src/wasm/openjtalk-web/README.md)
* **🎯 Voice Quality Enhancement Features**
  * **EMA (Exponential Moving Average)**: Improved training stability and fine-tuning quality (enabled by default)
  * **Custom Dictionary**: Enhanced Japanese pronunciation accuracy (478 pronunciation entries included)
  * **Benefits**: Improved training stability, accurate pronunciation of Japanese compound words
  * Details: [EMA Implementation Documentation](src/python/docs/integrated-components-ja.md)
* Multi-GPU training support (PyTorch Lightning 2.4.0)
  * Multiple GPU parallel training with DDP (Distributed Data Parallel) strategy
  * Automatic learning rate scaling (`--auto_lr_scaling`)
  * Improved code quality (enhanced security, optimized distributed logging)
  * Usage example:
    ```bash
    python -m piper_train \
      --dataset-dir /path/to/dataset \
      --batch-size 64 \
      --devices 4 \
      --strategy ddp_find_unused_parameters_true \
      --ema-decay 0.9995 \
      --num-workers 80
    # Note: --auto_lr_scaling is enabled by default
    # EMA is also enabled by default, use --no-ema to disable
    ```
* Enhanced checkpoint management
  * `--resume_from_checkpoint` to resume training from checkpoint
  * `--resume_from_single_speaker_checkpoint` to convert from single-speaker to multi-speaker model
* GPU inference support (C++ binary)
  * Enable ONNX Runtime CUDA provider with `--use-cuda` option
* Advanced training options
  * `--gradient_clip_val` - Gradient clipping
  * `--accumulate_grad_batches` - Virtual batch size expansion via gradient accumulation
  * `--precision` - Mixed Precision Training support (e.g., 16-mixed)
  * `--detect_anomaly` - Anomaly detection during training
* Voice evaluation tools (`scripts/evaluation/`)
  * MCD (Mel-Cepstral Distortion) evaluation
  * PESQ (Perceptual Evaluation of Speech Quality) evaluation
  * UTMOS evaluation
* **🎵 CLI Enhancements** - [Detailed Documentation](docs/features/cli-enhancements.md)
  * **Volume Adjustment**: `--volume` option (0.1-2.0)
  * **Auto-play**: Automatically play after generation with `--auto-play`
  * **Direct Text Input**: `piper "text" --model model.onnx`
  * **File Input**: Multiple file support with `--input-file`
  * **Usage Examples**:
    ```bash
    # Auto-play with volume adjustment
    piper "Hello world" --model en_US-lessac.onnx --volume 1.2 --auto-play
    
    # Read from file
    piper --model en_US-lessac.onnx --input-file story.txt -f output.wav
    ```
* **🎯 Phoneme Timing Information Output** - [Detailed Documentation](docs/features/phoneme-timing.md)
  * Timing information for lip-sync, karaoke, subtitle synchronization
  * Output in JSON/TSV format
  * Usage example:
    ```bash
    echo "Hello world" | piper --model en_US-lessac.onnx \
      --output-file speech.wav --output-timing timing.json
    ```

## Related Articles
* [Creating English Piper Pre-trained Model using LJSpeech](https://ayousanz.hatenadiary.jp/entry/2025/05/26/230341)
* [Creating Piper Japanese Model using JVS Voice Dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/05/093217)
* [Fine-tuning from Piper Model using Tsukuyomi-chan Dataset](https://ayousanz.hatenadiary.jp/entry/2025/06/07/074232)

``` sh
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav

# Streaming mode for reduced latency (outputs audio chunks progressively)
echo 'This is a long text that will be processed in chunks for lower latency.' | \
  ./piper --model en_US-lessac-medium.onnx --output_file output.wav --streaming
```

### Streaming Mode

The `--streaming` flag enables chunk-based processing for reduced latency:
- **Dynamic chunk sizing**: Automatically adjusts chunk size based on punctuation density
- **Audio crossfading**: Smooth transitions between chunks to prevent clicks/artifacts
- **~15% latency reduction** for long texts

[Listen to voice samples](https://rhasspy.github.io/piper-samples) and check out a [video tutorial by Thorsten Müller](https://youtu.be/rjq5eZoWWSo)

Voices are trained with [VITS](https://github.com/jaywalnut310/vits/) and exported to the [onnxruntime](https://onnxruntime.ai/).

[![A library from the Open Home Foundation](https://www.openhomefoundation.org/badges/ohf-library.png)](https://www.openhomefoundation.org/)

## Platform Support

### Supported Platforms

| Platform | Architecture | OpenJTalk Support | Notes |
|----------|--------------|-------------------|-------|
| Linux | x86_64 (amd64) | ✅ | Full support |
| Linux | ARM64 | ✅ | Full support (use CMake build) |
| macOS | **ARM64 (Apple Silicon) only** | ✅ | M1/M2/M3 and later Macs only |
| Windows | x64 | ✅ | Full support |
| **Web (Browser)** | WebAssembly | ✅ | Chrome/Edge/Firefox/Safari supported |

### ⚠️ Important: Notice for macOS Users

**As of 2024, macOS support is limited to Apple Silicon (M1/M2/M3 and later) only.**

#### For Intel Mac Users
Intel Mac (x86_64) support has been discontinued. Please use the following alternatives:

1. **Use Docker (Recommended)**
   ```bash
   # Pull Docker image
   docker pull ghcr.io/ayutaz/piper-plus:latest
   
   # Example usage
   docker run --rm -v $(pwd):/data ghcr.io/ayutaz/piper-plus:latest \
     echo "Hello from Docker" | piper --model /data/model.onnx --output_file /data/output.wav
   ```

2. **Build from Source**
   ```bash
   # Install dependencies
   brew install cmake onnxruntime
   
   # Build
   git clone https://github.com/ayutaz/piper-plus.git
   cd piper-plus
   mkdir build && cd build
   cmake .. -DCMAKE_BUILD_TYPE=Release
   make -j$(sysctl -n hw.ncpu)
   ```

3. **Use Linux in a Virtual Machine**
   - Use UTM, Parallels Desktop, VMware Fusion, etc.

#### For Apple Silicon Users
You can download and use normally. For security warnings on first run, see below.

##### Handling macOS Security Warnings
When running downloaded binaries for the first time, macOS security features may show warnings. Remove quarantine attributes with the following command:

```bash
# After extracting downloaded files
xattr -cr piper/

# Or for specific binaries only
xattr -cr piper/bin/piper
xattr -cr piper/bin/open_jtalk  # If using Japanese TTS
```

This allows execution without Gatekeeper warnings.

### 🌐 WebAssembly Version (Browser Support)

Piper-plus runs directly in browsers using WebAssembly:

#### Features
- **Fully browser-based**: No server required, offline capable
- **Japanese support**: High-precision phonemization with OpenJTalk WebAssembly edition
- **Lightweight**: WASM < 400KB, JS < 40KB
- **Supported browsers**: Chrome, Edge, Firefox, Safari (latest versions)

#### Demo & Usage
- 🌏 **[Online Demo](https://ayutaz.github.io/piper-plus/)** - Try it now in your browser
- 📖 **[Technical Details](docs/webassembly/openjtalk-approach/README.md)** - Implementation details
- 🔧 **[Integration Guide](src/wasm/openjtalk-web/README.md)** - How to integrate into web apps

## Voices

Our goal is to support Home Assistant and the [Year of Voice](https://www.home-assistant.io/blog/2022/12/20/year-of-voice/).

[Download voices](docs/api-reference/available-voices.md) for the supported languages:

* العربية, Jordan (Arabic, ar_JO)
* Català, Spain (Catalan, ca_ES)
* Čeština, Czech Republic (Czech, cs_CZ)
* Cymraeg, Great Britain (Welsh, cy_GB)
* Dansk, Denmark (Danish, da_DK)
* Deutsch, Germany (German, de_DE)
* Ελληνικά, Greece (Greek, el_GR)
* English, Great Britain (English, en_GB)
* English, United States (English, en_US)
* Español, Argentina (Spanish, es_AR)
* Español, Spain (Spanish, es_ES)
* Español, Mexico (Spanish, es_MX)
* فارسی, Iran (Farsi, fa_IR)
* Suomi, Finland (Finnish, fi_FI)
* Français, France (French, fr_FR)
* Magyar, Hungary (Hungarian, hu_HU)
* íslenska, Iceland (Icelandic, is_IS)
* Italiano, Italy (Italian, it_IT)
* ქართული ენა, Georgia (Georgian, ka_GE)
* қазақша, Kazakhstan (Kazakh, kk_KZ)
* Lëtzebuergesch, Luxembourg (Luxembourgish, lb_LU)
* Latviešu, Latvia (Latvian, lv_LV)
* മലയാളം, India (Malayalam, ml_IN)
* हिंदी, India (Hindi, hi_IN)
* नेपाली, Nepal (Nepali, ne_NP)
* Nederlands, Belgium (Dutch, nl_BE)
* Nederlands, Netherlands (Dutch, nl_NL)
* Norsk, Norway (Norwegian, no_NO)
* Polski, Poland (Polish, pl_PL)
* Português, Brazil (Portuguese, pt_BR)
* Português, Portugal (Portuguese, pt_PT)
* Română, Romania (Romanian, ro_RO)
* Русский, Russia (Russian, ru_RU)
* Slovenčina, Slovakia (Slovak, sk_SK)
* Slovenščina, Slovenia (Slovenian, sl_SI)
* srpski, Serbia (Serbian, sr_RS)
* Svenska, Sweden (Swedish, sv_SE)
* Kiswahili, Democratic Republic of the Congo (Swahili, sw_CD)
* Türkçe, Turkey (Turkish, tr_TR)
* україї́нська мо́ва, Ukraine (Ukrainian, uk_UA)
* Tiếng Việt, Vietnam (Vietnamese, vi_VN)
* 简体中文, China (Chinese, zh_CN)

You will need two files per voice:

1. A `.onnx` model file, such as [`en_US-lessac-medium.onnx`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx)
2. A `.onnx.json` config file, such as [`en_US-lessac-medium.onnx.json`](https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json)

The `MODEL_CARD` file for each voice contains important licensing information. Piper is intended for text to speech research, and does not impose any additional restrictions on voice models. Some voices may have restrictive licenses, however, so please review them carefully!


## Quick Start - WebUI

The easiest way to get started with Piper is using the WebUI:

```bash
# Install WebUI dependencies
pip install gradio>=4.0.0

# Run WebUI
cd src/python_run
python -m piper.webui --data-dir /path/to/models
```

Or using Docker:

```bash
# Run with Docker
docker run -p 7860:7860 -v ./models:/models ghcr.io/rhasspy/piper-webui
```

Access the WebUI at http://localhost:7860

## Installation

You can [run Piper with Python](#running-in-python) or download a binary release:

* [amd64](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz) (64-bit desktop Linux)
* [arm64](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz) (64-bit Raspberry Pi 4)
* [armv7](https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_armv7.tar.gz) (32-bit Raspberry Pi 3/4)

### Building from Source

If you want to build from source, see the [CMakeLists.txt](CMakeLists.txt) and [C++ source](src/cpp).

#### Prerequisites

* C++ compiler with C++17 support
* CMake 3.13 or later
* Git

#### Build Steps

1. Clone the repository:
   ```bash
   git clone https://github.com/rhasspy/piper.git
   cd piper
   ```

2. Create build directory:
   ```bash
   mkdir build
   cd build
   ```

3. Configure and build:
   ```bash
   cmake ..
   cmake --build . --config Release
   ```

#### Platform-specific Notes

**Linux**: You must download and extract [piper-phonemize](https://github.com/rhasspy/piper-phonemize) to `lib/Linux-$(uname -m)/piper_phonemize` before building.
For example, `lib/Linux-x86_64/piper_phonemize/lib/libpiper_phonemize.so` should exist for AMD/Intel machines.

**Windows**: See the [Windows Setup Guide](docs/getting-started/windows-setup.md) for detailed instructions.

**macOS**: The build process will automatically download required dependencies.


## Usage

1. [Download a voice](#voices) and extract the `.onnx` and `.onnx.json` files
2. Run the `piper` binary with text on standard input, `--model /path/to/your-voice.onnx`, and `--output_file output.wav`

For example:

``` sh
echo 'Welcome to the world of speech synthesis!' | \
  ./piper --model en_US-lessac-medium.onnx --output_file welcome.wav
```

For multi-speaker models, use `--speaker <number>` to change speakers (default: 0).

### Additional Options

* `--use-cuda` - Enable GPU acceleration with CUDA
* `--gpu-device-id <number>` - GPU device ID for CUDA (default: 0)
* `--quiet` / `-q` - Disable logging output
* `--phoneme-silence <phoneme> <seconds>` - Set silence duration for specific phonemes
* `--length-scale <value>` - Adjust speech speed (default: 1.0, smaller = faster)
* `--noise-scale <value>` - Control audio variation (default: 0.667)
* `--noise-w <value>` - Control phoneme duration variation (default: 0.8)
* `--sentence-silence <seconds>` - Silence between sentences (default: 0.2)
* `--raw-phonemes` - Interpret input as raw phonemes (space-separated)

See `piper --help` for more options.

### Phoneme Input

Piper supports two methods for direct phoneme input:

1. **Inline phoneme notation** - Mix text with phonemes using `[[ ]]`:
   ```sh
   echo 'Hello [[ h ə l oʊ ]] world' | ./piper --model en_US-lessac-medium.onnx -f output.wav
   ```

2. **Raw phoneme mode** - Input only phonemes with `--raw-phonemes`:
   ```sh
   echo 'h ə l oʊ _ w ɜː l d' | ./piper --model en_US-lessac-medium.onnx --raw-phonemes -f output.wav
   ```

See [raw-phoneme-input.md](docs/features/raw-phoneme-input.md) for detailed documentation.

### Streaming Audio

Piper can stream raw audio to stdout as its produced:

``` sh
echo 'This sentence is spoken first. This sentence is synthesized while the first sentence is spoken.' | \
  ./piper --model en_US-lessac-medium.onnx --output-raw | \
  aplay -r 22050 -f S16_LE -t raw -
```

This is **raw** audio and not a WAV file, so make sure your audio player is set to play 16-bit mono PCM samples at the correct sample rate for the voice.

### JSON Input

The `piper` executable can accept JSON input when using the `--json-input` flag. Each line of input must be a JSON object with `text` field. For example:

``` json
{ "text": "First sentence to speak." }
{ "text": "Second sentence to speak." }
```

Optional fields include:

* `speaker` - string
    * Name of the speaker to use from `speaker_id_map` in config (multi-speaker voices only)
* `speaker_id` - number
    * Id of speaker to use from 0 to number of speakers - 1 (multi-speaker voices only, overrides "speaker")
* `output_file` - string
    * Path to output WAV file
    
The following example writes two sentences with different speakers to different files:

``` json
{ "text": "First speaker.", "speaker_id": 0, "output_file": "/tmp/speaker_0.wav" }
{ "text": "Second speaker.", "speaker_id": 1, "output_file": "/tmp/speaker_1.wav" }
```


## People using Piper

Piper has been used in the following projects/papers:

* [Home Assistant](https://github.com/home-assistant/addons/blob/master/piper/README.md)
* [Rhasspy 3](https://github.com/rhasspy/rhasspy3/)
* [NVDA - NonVisual Desktop Access](https://www.nvaccess.org/post/in-process-8th-may-2023/#voices)
* [Image Captioning for the Visually Impaired and Blind: A Recipe for Low-Resource Languages](https://www.techrxiv.org/articles/preprint/Image_Captioning_for_the_Visually_Impaired_and_Blind_A_Recipe_for_Low-Resource_Languages/22133894)
* [Open Voice Operating System](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper)
* [JetsonGPT](https://github.com/shahizat/jetsonGPT)
* [LocalAI](https://github.com/go-skynet/LocalAI)
* [Lernstick EDU / EXAM: reading clipboard content aloud with language detection](https://lernstick.ch/)
* [Natural Speech - A plugin for Runelite, an OSRS Client](https://github.com/phyce/rl-natural-speech)
* [mintPiper](https://github.com/evuraan/mintPiper)
* [Vim-Piper](https://github.com/wolandark/vim-piper)

## Unity Integration - uPiper

A Unity plugin called "uPiper" has been developed for using Piper in Unity:

* **GitHub**: https://github.com/ayutaz/uPiper
* **Unity 6000.0.35f1 or later supported**
* **ONNX model execution using Unity.InferenceEngine**
* Asynchronous API and streaming support
* Currently supports Japanese and English (more languages planned)
* **Supported Platforms**:
  - Windows (x64)
  - macOS (Apple Silicon supported, Intel via Docker only)
  - Linux (x64)
  - Android (ARM64)
  - iOS (not supported)
  - WebGL (planned)

uPiper provides a comprehensive solution for leveraging Piper TTS in game development and interactive applications.

## Pre-trained Models

Pre-trained base models for Japanese TTS fine-tuning are available on Hugging Face.

| Model | Description | License |
|-------|-------------|---------|
| [piper-plus-base](https://huggingface.co/ayousanz/piper-plus-base) | Japanese TTS base model (VITS + WavLM Discriminator + Prosody) | CC-BY-SA-4.0 |
| [piper-plus-tsukuyomi-chan](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan) | Tsukuyomi-chan fine-tuned model | See model card |

### piper-plus-base Features

- **Architecture**: VITS + WavLM Discriminator
- **Training data**: 60,164 utterances (20 speakers)
- **Sample rate**: 22,050 Hz
- **Prosody Features**: A1/A2/A3 prosody information (`--prosody-dim 16`)
- **Extended phonemes**: Question markers, context-dependent "N" variants
- **Total phonemes**: 65

For details, see the [Hugging Face model card](https://huggingface.co/ayousanz/piper-plus-base) and the [training guide](docs/guides/training/training-guide.md).

## Training

See the [training guide](docs/guides/training/training-guide.md) and the [source code](src/python).

Pretrained checkpoints are available on [Hugging Face](https://huggingface.co/datasets/rhasspy/piper-checkpoints/tree/main)


## Running in Python

See [src/python_run](src/python_run)

Install with `pip`:

``` sh
# Basic features only
pip install piper-tts-plus

# GPU version (with CUDA environment)
pip install "piper-tts-plus[gpu]"

# Including HTTP server functionality
pip install "piper-tts-plus[http]"

# GPU + HTTP
pip install "piper-tts-plus[gpu,http]"
```

This will automatically download [voice files](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0) the first time they're used. Use `--data-dir` and `--download-dir` to adjust where voices are found/downloaded.

If you'd like to use a GPU, install the `onnxruntime-gpu` package:


``` sh
.venv/bin/pip3 install onnxruntime-gpu
```

and then run `piper` with the `--cuda` argument. You will need to have a functioning CUDA environment, such as what's available in [NVIDIA's PyTorch containers](https://catalog.ngc.nvidia.com/orgs/nvidia/containers/pytorch).


## Documentation

For detailed documentation, see the [docs/](docs/) directory.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute to this project.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.