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
# Download the canonical reference-free model from HuggingFace
curl -LO https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/tsukuyomi-chan-6lang-fp16.onnx
curl -L https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/config.json \
  -o tsukuyomi-chan-6lang-fp16.onnx.json
```

> **Model terms:** the C API takes a model path only, so it does not show the usage
> notice that the CLIs print. If your app ships the Tsukuyomi-chan model
> (`tsukuyomi-chan-6lang-fp16.onnx` or `tsukuyomi.onnx`), show its terms to your users:
> the credit "Piper Plus:つくよみちゃん" is required on generated audio, and the
> prohibited uses are on the [model page](https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan).
> The model is unofficial: Rei Yumesaki (the corpus rights holder) is not involved in its
> development or support, so send questions to the developer through
> [GitHub Issues](https://github.com/ayutaz/piper-plus/issues), not to Rei Yumesaki.
> The notice text is in `test/model_resolution_vectors.json` (`notice`); see
> [model-resolution.md §9](../../docs/reference/model-resolution.md#9-利用案内-model-notice).

This C API example demonstrates reference-free synthesis. C++ reference-audio
speaker-encoder inference is not implemented; use the published
[`zs-v1` README](https://huggingface.co/ayousanz/piper-plus-base/blob/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/README.md)
for the canonical embedding-precomputation workflow before using a compatible
pre-computed embedding with another runtime.

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
./basic tsukuyomi-chan-6lang-fp16.onnx /usr/local/share/open_jtalk/dic "Hello world." output.wav

# Streaming synthesis (outputs WAV file)
./streaming tsukuyomi-chan-6lang-fp16.onnx /usr/local/share/open_jtalk/dic "First. Second. Third." streaming.wav

# Multi-language synthesis (outputs one WAV per language)
./multi_language tsukuyomi-chan-6lang-fp16.onnx /usr/local/share/open_jtalk/dic
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
