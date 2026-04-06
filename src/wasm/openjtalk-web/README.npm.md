# piper-plus

[![npm version](https://img.shields.io/npm/v/piper-plus)](https://www.npmjs.com/package/piper-plus)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Browser-based multilingual neural TTS powered by VITS. No server required.

## Features

- **8 languages** -- Japanese, English, Chinese, Korean, Spanish, French, Portuguese, and Swedish
- **Runs entirely in the browser** -- WebAssembly + ONNX Runtime Web, no backend needed
- **No server or API key required** -- all processing happens client-side
- **Streaming synthesis** -- sentence-by-sentence generation with chunk callbacks
- **WebGPU acceleration** -- automatic fallback to WASM when WebGPU is unavailable
- **IndexedDB caching** -- models are cached after the first download
- **Bundled Japanese dictionary** -- NAIST-JDIC compiled into WASM binary (~19MB gzip), no separate download
- **Structured error codes** -- errors carry a `.code` property for programmatic handling
- **~4 MB npm package** -- models are downloaded on demand from HuggingFace

## Install

```bash
npm install piper-plus onnxruntime-web
```

`onnxruntime-web` is a peer dependency and must be installed alongside `piper-plus`.

## Quick Start

### Basic Usage

```javascript
import { PiperPlus } from "piper-plus";
import * as ort from "onnxruntime-web";

// Initialize (downloads and caches model automatically; dictionary is bundled in WASM)
const tts = await PiperPlus.initialize({
  model: "ayousanz/piper-plus-tsukuyomi-chan",
  ort,
});

// Synthesize speech
const audio = await tts.synthesize("Hello, how are you today?", {
  language: "en",
});

// Play through the browser's audio output
await audio.play();

// Clean up when done
tts.dispose();
```

### Streaming Synthesis

For long texts, streaming mode splits the input into sentences and delivers audio chunks as they are generated:

```javascript
const tts = await PiperPlus.initialize({
  model: "ayousanz/piper-plus-tsukuyomi-chan",
  ort,
});

await tts.synthesizeStreaming(
  "This is a long paragraph. It will be split into sentences. Each sentence is synthesized separately.",
  {
    language: "en",
    onChunk: (audioChunk) => {
      // audioChunk is a Float32Array of PCM samples
      console.log(`Received ${audioChunk.length} samples`);
    },
  }
);
```

### Language Selection

Pass a `language` option to select the target language, or omit it for automatic detection (Japanese and Chinese are detected by character ranges; Latin-script languages default to English):

```javascript
// Japanese (auto-detected from Kana characters)
await tts.synthesize("こんにちは、今日は良い天気ですね。");

// English (explicit)
await tts.synthesize("Good morning!", { language: "en" });

// Chinese (auto-detected from CJK characters without Kana)
await tts.synthesize("你好，今天天气很好。");

// Spanish (must be specified explicitly)
await tts.synthesize("Hola, buenos dias.", { language: "es" });
```

### Progress Tracking

Monitor download progress during initialization:

```javascript
const tts = await PiperPlus.initialize({
  model: "ayousanz/piper-plus-tsukuyomi-chan",
  ort,
  onProgress: ({ stage, progress, message }) => {
    console.log(`[${stage}] ${Math.round(progress * 100)}% - ${message}`);
  },
});
```

## API Reference

### `PiperPlus.initialize(options)`

Static async factory that downloads (and caches) the ONNX model and config, then creates an ONNX inference session and initializes the Rust WASM phonemizer. The Japanese dictionary (NAIST-JDIC) is bundled in the WASM binary and requires no separate download.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | `string` | -- | **Required.** HuggingFace repo name (e.g. `"ayousanz/piper-plus-tsukuyomi-chan"`), registry shortcut (e.g. `"tsukuyomi"`), or direct URL to an ONNX file. |
| `ort` | `object` | `globalThis.ort` | `onnxruntime-web` module instance. |
| `onProgress` | `function` | -- | Callback receiving `{ stage, progress, message }`. |

Returns `Promise<PiperPlus>`.

### `tts.synthesize(text, options?)`

Synthesize speech from text.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `language` | `string` | auto-detect | `'ja'` \| `'en'` \| `'zh'` \| `'ko'` \| `'es'` \| `'fr'` \| `'pt'` \| `'sv'` |
| `noiseScale` | `number` | `0.667` | Controls voice variation. |
| `lengthScale` | `number` | `1.0` | Controls speech speed (lower = faster). |
| `noiseW` | `number` | `0.8` | Controls phoneme duration variation. |

Returns `Promise<AudioResult>`.

### `tts.synthesizeStreaming(text, options?)`

Streaming synthesis that splits text into sentences and delivers audio chunks via a callback.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `language` | `string` | auto-detect | Target language code. |
| `noiseScale` | `number` | `0.667` | Controls voice variation. |
| `lengthScale` | `number` | `1.0` | Controls speech speed. |
| `noiseW` | `number` | `0.8` | Controls phoneme duration variation. |
| `onChunk` | `function` | -- | Callback receiving a `Float32Array` of PCM samples per sentence. |

Returns `Promise<void>`.

### `tts.dispose()`

Release all held resources (ONNX session, phonemizer, WASM module). The instance cannot be used after calling this method.

### `tts.isInitialized`

`boolean` -- whether the instance is ready for synthesis.

### `tts.config`

`Object | null` -- the model's `config.json` contents after initialization.

### `AudioResult`

Returned by `synthesize()`. Wraps raw PCM audio samples.

| Method / Property | Returns | Description |
|-------------------|---------|-------------|
| `play()` | `Promise<void>` | Play through the browser's audio output. Resolves when playback ends. |
| `toBlob()` | `Blob` | Generate a WAV `Blob` (`audio/wav`). |
| `toWav()` | `ArrayBuffer` | Generate a WAV `ArrayBuffer` (PCM 16-bit, mono). |
| `download(filename?)` | `void` | Trigger a WAV file download. Default filename: `'output.wav'`. |
| `samples` | `Float32Array` | Raw audio sample data. |
| `sampleRate` | `number` | Sample rate in Hz (typically 22050). |
| `duration` | `number` | Audio duration in seconds. |

### `modelManager.resolveUrls(modelNameOrUrl)`

Resolves a model identifier to concrete URLs without downloading.

- `modelNameOrUrl` -- Registry shortcut (`"tsukuyomi"`), HuggingFace repo (`"ayousanz/piper-plus-tsukuyomi-chan"`), or direct URL
- Returns: `Promise<{ modelUrl: string, configUrl: string, cacheKey: string }>`

## Available Models

| Model | HuggingFace Repo | Description |
|-------|-------------------|-------------|
| Tsukuyomi-chan | `ayousanz/piper-plus-tsukuyomi-chan` | Japanese female voice, single-speaker, 6-language support |
| CSS10 Japanese | `ayousanz/piper-plus-css10-ja-6lang` | Japanese voice, single-speaker, 6-language support |
| Base (571 speakers) | `ayousanz/piper-plus-base` | Multi-speaker base model, 571 speakers across 6 languages |

Models can be specified by full HuggingFace repo name or shortcut:

```javascript
// Full repo name
const tts = await PiperPlus.initialize({ model: "ayousanz/piper-plus-tsukuyomi-chan", ort });

// Shortcut
const tts = await PiperPlus.initialize({ model: "tsukuyomi", ort });
```

### Using a Custom Model URL

You can point to any ONNX model hosted on your own server:

```javascript
const tts = await PiperPlus.initialize({
  model: "https://your-server.com/path/to/model.onnx",
  ort,
});
```

The config file is expected at `<model-url>.json` (e.g. `model.onnx.json`).

## Supported Languages

| Language | Code | Phonemization Engine | Notes |
|----------|------|---------------------|-------|
| Japanese | `ja` | jpreprocess (Rust WASM) | Full phoneme analysis with prosody features (A1/A2/A3); NAIST-JDIC dictionary bundled |
| English | `en` | Rule-based (JS) | SimpleEnglishPhonemizer |
| Chinese | `zh` | Character-based mapping | Maps characters through the model's phoneme_id_map |
| Spanish | `es` | Character-based mapping | Maps characters through the model's phoneme_id_map |
| French | `fr` | Character-based mapping | Maps characters through the model's phoneme_id_map |
| Portuguese | `pt` | Character-based mapping | Maps characters through the model's phoneme_id_map |
| Korean | `ko` | Hangul decomposition + mapping | Decomposes Hangul syllables to Jamo, then maps via the model's phoneme_id_map |
| Swedish | `sv` | Character-based mapping | Maps characters through the model's phoneme_id_map |

Language auto-detection works reliably for Japanese (Kana characters), Chinese (CJK without Kana), and Korean (Hangul characters). For Spanish, French, Portuguese, and Swedish, specify the language explicitly since their Latin-script characters cannot be distinguished from English.

## Browser Compatibility

| Browser | WebGPU | WASM (fallback) |
|---------|--------|-----------------|
| Chrome 113+ | Yes | Yes |
| Edge 113+ | Yes | Yes |
| Firefox | No | Yes |
| Safari 18+ | Yes | Yes |

WebGPU is used automatically when available for faster inference. When WebGPU is not supported, the runtime falls back to the WASM execution provider.

**Note:** The Rust WASM phonemizer binary (with bundled Japanese dictionary) is ~58MB uncompressed (~19MB gzip transfer). It is fetched at runtime via `fetch()` and cached by the browser's WASM compilation cache, so subsequent page loads are fast (0.3-1s).

## Advanced Usage

### Using G2P Directly

For phonemization without ONNX inference:

```javascript
import { G2P, Encoder } from "piper-plus/phonemizer";

const g2p = await G2P.create({ languages: ['ja', 'en'] });

// Japanese: phonemized via Rust WASM (jpreprocess) with bundled dictionary
const jaResult = g2p.phonemize("こんにちは", { language: "ja" });
// jaResult.tokens: string[], jaResult.language: "ja"

// English
const enResult = g2p.phonemize("Hello world", { language: "en" });
// enResult.tokens: string[]

// Encode tokens to Piper phoneme IDs for ONNX inference
const encoder = new Encoder(modelConfig.phoneme_id_map);
const { phonemeIds } = encoder.encode(jaResult.tokens);

g2p.dispose();
```

### Cache Management

Models are cached in IndexedDB. You can manage caches programmatically:

```javascript
import { ModelManager } from "piper-plus";

// Clear model cache
const modelManager = new ModelManager();
await modelManager.clearCache();
```

> **Note:** In v0.2.0, the Japanese dictionary is bundled in the WASM binary. There is no separate dictionary cache. If upgrading from v0.1.x, see [MIGRATION.md](./MIGRATION.md) for instructions on cleaning up legacy IndexedDB dictionary data.

### URL Resolution

Resolve model URLs without downloading:

```javascript
import { ModelManager } from "piper-plus";

// Resolve model URL from a shortcut or repo name
const modelMgr = new ModelManager();
const { modelUrl, configUrl, cacheKey } = await modelMgr.resolveUrls("tsukuyomi");
console.log(modelUrl);  // https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/...
```

### Sub-path Imports

The package exposes additional entry points for selective imports:

```javascript
// G2P only (no ONNX dependency)
import { G2P, Encoder } from "piper-plus/phonemizer";

// Streaming pipeline
import { StreamingTTSPipeline, TextChunker } from "piper-plus/streaming";
```

## Upgrading from v0.1.x

See [MIGRATION.md](./MIGRATION.md) for a detailed migration guide covering all breaking changes, removed exports, and step-by-step upgrade instructions.

See [CHANGELOG.md](./CHANGELOG.md) for the full list of changes in each release.

## License

MIT
