# Building from Source

If pre-built binaries (see [README](../../../README_EN.md)) don't fit your platform or you need to modify piper-plus, build from source. This guide covers C++, C#, and Rust runtimes.

## Development environment setup (one-time)

After cloning the repository, install the `pre-commit` hook once so that ruff
(check + format) and PUA consistency are auto-applied on every local commit:

```bash
pip install pre-commit   # or: uvx pre-commit
pre-commit install       # generates .git/hooks/pre-commit
```

This catches lint / format drift before pushing (mirrors `.github/workflows/pre-commit.yml`).
Run `pre-commit run --all-files` for a one-shot full sweep.

> **v1.12.0 notes:** Python runtime now uses FastAPI (not Flask) for the HTTP server,
> and the HTS-voice dependency has been removed from the Python runtime
> (C++/Go/Rust/WASM continue to use OpenJTalk + HTS-voice). HiFi-GAN decoder ckpts
> are no longer supported — use the MB-iSTFT base model `piper-plus-base` for
> resume / fine-tuning. See `docs/migration/v1.11-to-v1.12.md`.

## Building C++ CLI

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

Prerequisites: C++17 compiler, CMake 3.15+

- **Linux**: Dependencies (ONNX Runtime, OpenJTalk, etc.) are downloaded automatically by CMake
- **Windows**: See [Windows Setup Guide](../../getting-started/windows-setup.md)
- **macOS**: Dependencies are downloaded automatically

## Building C# CLI (PiperPlus)

```bash
# C# CLI build
dotnet build src/csharp/PiperPlus.sln -c Release
# Test
dotnet test src/csharp/PiperPlus.Core.Tests/
```

Prerequisites: .NET 10 SDK or later

### C# CLI Usage Examples

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

### Rust CLI Usage Examples

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

> **Note:** Install C# CLI with `dotnet tool install -g PiperPlus.Cli` and Rust CLI with `cargo install piper-plus-cli`. Both support 8 languages, custom dictionaries, and streaming.

## Building Rust CLI

```bash
# Rust CLI build
cargo build --release -p piper-plus-cli
# Test
cargo test -p piper-plus
```

Prerequisites: Rust 1.88+, cargo

---

→ Back to [README](../../../README_EN.md)
