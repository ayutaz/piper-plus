# piper-plus C API Examples

Minimal examples demonstrating the piper-plus C shared library.

> **CI verification status**: builds are exercised by `.github/workflows/_build-test-cpp.yml` as part of the C++ CMake build. End-to-end runtime synthesis verification with downloaded models is **not** part of the regular CI matrix — please report issues if any sample fails to build or run after extracting a release archive.

## Prerequisites

Download a release archive from [GitHub Releases](https://github.com/ayutaz/piper-plus/releases) and extract it:

```bash
tar -xzf piper-plus-shared-linux-x64.tar.gz -C /usr/local
```

### Download a model

```bash
# Download the test model from HuggingFace
curl -LO https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx
curl -LO https://huggingface.co/ayousanz/piper-plus-base/resolve/main/multilingual-test-medium.onnx.json
```

The OpenJTalk dictionary is bundled in the release archive at `share/open_jtalk/dic/`.

## Build with Makefile (pkg-config)

```bash
PKG_CONFIG_PATH=/usr/local/lib/pkgconfig make
```

## Build with CMake

```bash
cmake -B build -DCMAKE_PREFIX_PATH=/usr/local
cmake --build build
```

## Run

```bash
# One-shot synthesis (outputs WAV file)
./basic multilingual-test-medium.onnx /usr/local/share/open_jtalk/dic "Hello world." output.wav

# Streaming synthesis (outputs WAV file)
./streaming multilingual-test-medium.onnx /usr/local/share/open_jtalk/dic "First. Second. Third." streaming.wav

# Multi-language synthesis (outputs one WAV per language)
./multi_language multilingual-test-medium.onnx /usr/local/share/open_jtalk/dic
```

### Multi-language example

`multi_language` demonstrates synthesizing text in 6 languages (JA, EN, ZH, ES, FR, PT)
using both explicit `language_id` and auto-detection (`language_id = -1`).

It produces 12 WAV files: `output_JA.wav`, `output_EN.wav`, ... (explicit) and
`output_JA_auto.wav`, `output_EN_auto.wav`, ... (auto-detected).

```bash
./multi_language <model.onnx> [dict_dir] [config.json]
```

A multi-language model is recommended. A single-language model will still run but
only the matching language will produce meaningful audio.
