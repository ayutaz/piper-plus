# PiperPlus.Cli

[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Cli.svg)](https://www.nuget.org/packages/PiperPlus.Cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 日本語の概要は [リポジトリ ルート README (日本語)](https://github.com/ayutaz/piper-plus/blob/dev/README.md) と [`CLAUDE.md`](https://github.com/ayutaz/piper-plus/blob/dev/CLAUDE.md) を参照してください。

`piper-plus` is a fast, high-quality neural text-to-speech engine based on the VITS architecture. **PiperPlus.Cli** is the cross-platform .NET command-line tool, packaged as a [`dotnet tool`](https://learn.microsoft.com/dotnet/core/tools/global-tools). It exposes the full Piper Plus pipeline (8-language phonemization + ONNX inference) without any espeak-ng / GPL dependencies.

## Install

```bash
dotnet tool install -g PiperPlus.Cli
```

Requires the [.NET 10 runtime](https://dotnet.microsoft.com/download). The installed binary is named `piper-plus`.

## Quick start

```bash
# 1. List available models
piper-plus --list-models
piper-plus --list-models ja

# 2. Auto-download a model (resolved via alias)
piper-plus --download-model tsukuyomi

# 3. Synthesize Japanese speech
piper-plus --model tsukuyomi \
           --text "こんにちは、今日は良い天気ですね。" \
           --output_file hello.wav

# 4. Synthesize multilingual text (auto language detection per segment)
piper-plus --model tsukuyomi \
           --language ja-en-zh-ko-es-fr-pt-sv \
           --text "Hello, 世界。" \
           --output_file mixed.wav
```

`--model` accepts either a file path (`models/tsukuyomi.onnx`) or a model name / alias (`tsukuyomi`); aliases are resolved against the bundled voice catalog and downloaded on demand. Set `PIPER_DEFAULT_MODEL` / `PIPER_MODEL_DIR` to override defaults.

## Common options

| Flag | Description |
|------|-------------|
| `--model`, `-m` | Path to `.onnx` model **or** name / alias for auto-download |
| `--config`, `-c` | Explicit `config.json` path (otherwise auto-detected) |
| `--text`, `-t` | Text to synthesize (alternative to JSONL stdin) |
| `--language` | Language code: `ja`, `en`, `zh`, `ko`, `es`, `fr`, `pt`, `sv`, or combined (e.g. `ja-en-zh-ko-es-fr-pt-sv`) |
| `--speaker`, `-s` | Speaker ID for multi-speaker models (default: `0`) |
| `--output_file`, `-f` | Output WAV path (`-` for stdout) |
| `--output_dir`, `-d` | Output directory (default: cwd) |
| `--output_raw` | Raw 16-bit PCM stdout (no WAV header) |
| `--streaming` | Sentence-level streaming raw PCM to stdout |
| `--noise_scale` / `--length_scale` / `--noise_w` | Synthesis params (defaults `0.667 / 1.0 / 0.8`) |
| `--sentence_silence` | Silence after each sentence (default: `0.2` s) |
| `--phoneme_silence` | Insert silence around specific phonemes (`"<phoneme> <seconds>"`) |
| `--custom-dict` | Comma-separated custom dictionary files (JSON v1.0/v2.0 + TSV) |
| `--raw-phonemes` | Treat stdin as space-separated phonemes |
| `--reference-audio` | Reference WAV for voice cloning |
| `--speaker-encoder-model` | Speaker encoder ONNX (required with `--reference-audio`) |
| `--speaker-embedding` | Pre-computed speaker embedding (raw float32) |
| `--use-cuda` / `--gpu-device-id` | Enable CUDA execution provider |
| `--no-warmup` | Skip ORT warmup (dummy inference at startup) |
| `--list-models [LANG]` / `--download-model NAME` | Catalog management |
| `--debug` / `--quiet` / `--version` | Misc. controls |

Run `piper-plus --help` for the full set (model resolution, JSONL stdin, `--test-mode`, etc.).

## Voice cloning (Speaker Encoder)

```bash
piper-plus --model tsukuyomi \
           --speaker-encoder-model models/speaker_encoder.onnx \
           --reference-audio reference.wav \
           --text "Cloned voice example." \
           --output_file cloned.wav
```

The speaker encoder produces a 256-dim L2-normalized embedding (ECAPA-TDNN) that is fed to the VITS model via the `speaker_embedding` input.

## Streaming + sentence splitting

```bash
piper-plus --model tsukuyomi --streaming \
           --text "First sentence. Second sentence! 三つ目の文。" \
           > stream.pcm
```

Multi-sentence text is split via `TextSplitter.SplitSentences` and synthesized per sentence to minimize time-to-first-audio. Streaming output is raw 16-bit PCM.

## Custom dictionaries / inline phonemes

```bash
# JSON v1.0/v2.0 (C++/Rust互換) and TSV are supported
piper-plus --model tsukuyomi --custom-dict mydict.json,extras.tsv \
           --text "TTS と AGI を発音します。" \
           --output_file out.wav

# Inline phoneme notation: [[ ... ]]
piper-plus --model tsukuyomi \
           --text "通常テキスト [[ k o N n i ch i w a ]] 通常テキスト。" \
           --output_file inline.wav
```

The CLI ships with the same default dictionaries as the C++ / Rust runtimes; explicit `--custom-dict` files are layered on top via the priority system.

## Supported languages

| Code | Language | G2P backend |
|------|----------|-------------|
| `ja` | Japanese | DotNetG2P + DotNetG2P.MeCab (OpenJTalk-compatible, dictionary auto-download) |
| `en` | English | DotNetG2P.English (Apache-2.0) |
| `zh` | Chinese | DotNetG2P.Chinese (pinyin) |
| `ko` | Korean | Built-in rule-based engine |
| `es` | Spanish | DotNetG2P.Spanish |
| `fr` | French | DotNetG2P.French |
| `pt` | Portuguese | DotNetG2P.Portuguese |
| `sv` | Swedish | Built-in rule-based engine |

Combined codes (e.g. `ja-en-zh-es-fr-pt`) instantiate a `MultilingualPhonemizer` that selects per-segment language by Unicode block detection.

## Platforms

- **TFM:** `net10.0` (built with `Microsoft.NET.Sdk` + `PublishReadyToRun=true`)
- **OS:** Windows / Linux / macOS — CI runs on all three (`csharp-ci.yml`)
- **Hardware:** CPU by default; CUDA via `--use-cuda` (requires the matching `Microsoft.ML.OnnxRuntime` GPU runtime)

## Build from source

```bash
git clone https://github.com/ayutaz/piper-plus.git
cd piper-plus
dotnet build src/csharp/PiperPlus.sln -c Release
dotnet run --project src/csharp/PiperPlus.Cli -- --help
```

The solution also contains `PiperPlus.Core` (library) and `PiperPlus.Core.Tests` (~1000 xUnit v3 tests).

## Related packages

- [`PiperPlus.Core`](https://www.nuget.org/packages/PiperPlus.Core/) — library used by this CLI; embed it directly to drive synthesis from C# code.
- Repository: <https://github.com/ayutaz/piper-plus>

## License

MIT. See [LICENSE](https://github.com/ayutaz/piper-plus/blob/dev/LICENSE).
