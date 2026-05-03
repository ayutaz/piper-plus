# PiperPlus.Core

[![NuGet](https://img.shields.io/nuget/v/PiperPlus.Core.svg)](https://www.nuget.org/packages/PiperPlus.Core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 日本語の概要は [リポジトリ ルート README (日本語)](https://github.com/ayutaz/piper-plus/blob/dev/README.md) と [`CLAUDE.md`](https://github.com/ayutaz/piper-plus/blob/dev/CLAUDE.md) を参照してください。

`PiperPlus.Core` is the .NET library that powers [Piper Plus](https://github.com/ayutaz/piper-plus) — a fast, high-quality neural text-to-speech engine based on the VITS architecture. It bundles ONNX inference, 8-language phonemization, dictionary management, SSML parsing, and streaming text splitting in a single library targeting `net10.0`.

Use this package when you want to embed Piper Plus directly in a .NET application; for a ready-to-run command-line tool, see [`PiperPlus.Cli`](https://www.nuget.org/packages/PiperPlus.Cli/).

## Install

```bash
dotnet add package PiperPlus.Core
```

You also need to register a G2P engine for each language you intend to phonemize (e.g. [`DotNetG2P`](https://www.nuget.org/packages/DotNetG2P/), [`DotNetG2P.MeCab`](https://www.nuget.org/packages/DotNetG2P.MeCab/), [`DotNetG2P.English`](https://www.nuget.org/packages/DotNetG2P.English/), `DotNetG2P.Chinese / Spanish / French / Portuguese`, all at v1.8.0). The CLI project shows a complete example of wiring them up.

## Quick start

```csharp
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Config;
using PiperPlus.Core.Inference;
using PiperPlus.Core.Phonemize;

// 1. Load model + config
PiperConfig config = PiperConfig.LoadFromFile("models/tsukuyomi.onnx.json");
InferenceSession session = SessionFactory.Create("models/tsukuyomi.onnx");
using var model = new PiperModel(session, config);

// 2. Phonemize text. JapanesePhonemizer requires an IJapaneseG2PEngine
//    implementation that wraps the DotNetG2P NuGet packages
//    (DotNetG2P + DotNetG2P.MeCab + DotNetG2P.Engine — bring your own
//    adapter, or copy the one in PiperPlus.Cli/DotNetG2PEngine.cs which is
//    internal). The same pattern applies to EnglishPhonemizer / ChinesePhonemizer.
IJapaneseG2PEngine g2pEngine = /* your IJapaneseG2PEngine implementation */;
IPhonemizer phonemizer = new JapanesePhonemizer(g2pEngine);
var phonemeIdMap = phonemizer.GetPhonemeIdMap() ?? config.PhonemeIdMap;
var (phonemeIds, prosody) = PhonemeEncoder.EncodeDirect(
    phonemizer, "こんにちは、世界。", phonemeIdMap);

// 3. Run synthesis
var piper = new PiperSession(model);
short[] audio = piper.Synthesize(new SynthesisInput(
    PhonemeIds: phonemeIds,
    SpeakerId: 0,
    LanguageId: 0,
    ProsodyFeatures: model.HasProsody ? prosody : null,
    NoiseScale: 0.667f,
    LengthScale: 1.0f,
    NoiseW: 0.8f));

// 4. Persist as WAV (16-bit PCM, sample rate from config)
WavWriter.Write("hello.wav", audio, model.SampleRate);
```

Capabilities like multi-speaker (`HasSpeakerId`), multilingual (`HasLanguageId`), prosody features (`HasProsody`), per-phoneme durations (`HasDurationOutput`), and voice cloning (`HasSpeakerEmbedding`) are auto-detected from the ONNX model's input/output metadata.

## Key types

| Namespace | Type | Purpose |
|-----------|------|---------|
| `PiperPlus.Core.Config` | `PiperConfig`, `VoiceCatalog`, `ModelManager`, `DictionaryManager` | Load `config.json`, resolve / download models, manage default dictionaries |
| `PiperPlus.Core.Inference` | `PiperModel`, `PiperSession`, `SessionFactory`, `WavWriter`, `StreamingWriter`, `TimingWriter` | ONNX session lifecycle, synthesis, WAV / streaming / phoneme-timing output |
| `PiperPlus.Core.Inference` | `ShortTextProcessor`, `PhonemeSilenceProcessor`, `SpeakerEncoder` | Short-text quality strategies, phoneme-level silence, voice cloning helper |
| `PiperPlus.Core.Phonemize` | `IPhonemizer`, `JapanesePhonemizer`, `EnglishPhonemizer`, `ChinesePhonemizer`, `KoreanPhonemizer`, `SpanishPhonemizer`, `PortuguesePhonemizer`, `FrenchPhonemizer`, `SwedishPhonemizer`, `MultilingualPhonemizer` | 8-language G2P pipeline + Unicode-based language detection |
| `PiperPlus.Core.Phonemize` | `PhonemeEncoder`, `RawPhonemeParser`, `InlinePhonemeParser`, `IpaTokenizer`, `CustomDictionary`, `TextSplitter` | Phoneme encoding, `[[ phoneme ]]` notation, sentence-level streaming splitter |
| `PiperPlus.Core.Mapping` | `OpenJTalkToPiperMapping` | OpenJTalk → Piper PUA token mapping |
| `PiperPlus.Core.Ssml` | `SsmlParser`, `SsmlSegment` | W3C SSML subset (`<speak>`, `<break>`, `<prosody rate="...">`) |

## Features

- **8 languages** — Japanese, English, Chinese, Korean, Spanish, French, Portuguese, Swedish; combined codes auto-route to per-segment phonemizers via `MultilingualPhonemizer`.
- **Voice cloning** — `SpeakerEncoder` extracts a 256-dim L2-normalized embedding from a reference WAV and feeds it through the ONNX `speaker_embedding` input.
- **SSML basic profile** — `SsmlParser` covers `<speak>`, `<break time="...">`, `<prosody rate="...">`; matches the Python / Rust / Go runtimes.
- **Phoneme timing** — when the model exposes a `durations` output, `PiperSession.Synthesize` returns timing data that `TimingWriter` can serialize as JSON / TSV / SRT.
- **Custom dictionaries** — JSON v1.0/v2.0 (C++/Rust互換) and TSV formats supported via `CustomDictionary.LoadDictionaries`; default dictionaries auto-loaded by `LoadDefaults`.
- **Inline phoneme notation** — `[[ k o N n i ch i w a ]]` segments parsed by `InlinePhonemeParser` and concatenated with proper BOS/EOS handling.
- **Streaming sentence splitter** — `TextSplitter.SplitSentences` reproduces the Rust `text_splitter` contract (single source of truth: `docs/spec/text-splitter-contract.toml`).
- **Short-text quality strategies** — Strategy A (silence padding + post-trim) and Strategy B (dynamic scales) are implemented in `ShortTextProcessor`.
- **OpenJTalk dictionary auto-download** — `DictionaryManager` mirrors the C++ `openjtalk_dictionary_manager.c` behavior so Japanese G2P "just works" out of the box.
- **Optimized ORT sessions** — `SessionFactory.Create` applies the unified Tier-1/Tier-2 settings (graph optimization, intra-op thread tuning, optimized model cache) defined in `docs/spec/ort-session-contract.toml`. Call `SessionFactory.Warmup` once after creation to eliminate JIT delay.

## Target framework

- `net10.0` (the `PiperPlus.Cli` tool that consumes this library also targets `net10.0`).
- Depends on `Microsoft.ML.OnnxRuntime.Managed` 1.24.x and `Microsoft.Extensions.Logging.Abstractions` 8.x.

## Related packages

- [`PiperPlus.Cli`](https://www.nuget.org/packages/PiperPlus.Cli/) — global `dotnet tool` (`piper-plus`) built on top of this library.
- Repository: <https://github.com/ayutaz/piper-plus> (full pipeline including training, ONNX export, multilingual datasets, and runtimes for Python / Rust / Go / WASM / C++).

## License

MIT. See [LICENSE](https://github.com/ayutaz/piper-plus/blob/dev/LICENSE).
