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
- **IndexedDB caching** -- models and dictionaries are cached after the first download
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

// Initialize (downloads and caches model + dictionary automatically)
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

Static async factory that downloads (and caches) the ONNX model, config, OpenJTalk dictionary, and HTS voice file, then creates an ONNX inference session.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | `string` | -- | **Required.** HuggingFace repo name (e.g. `"ayousanz/piper-plus-tsukuyomi-chan"`), registry shortcut (e.g. `"tsukuyomi"`), or direct URL to an ONNX file. |
| `ort` | `object` | `globalThis.ort` | `onnxruntime-web` module instance. |
| `dictUrl` | `string` | auto | Custom URL for OpenJTalk dictionary files. |
| `voiceUrl` | `string` | auto | Custom URL for the HTS voice file. |
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

### `dictManager.resolveUrls(options?)`

Returns resolved dictionary and voice URLs without downloading.

- `options.dictUrl` -- Custom base URL for dictionary files (default: HuggingFace)
- `options.voiceUrl` -- Custom URL for HTS voice file (default: HuggingFace)
- Returns: `{ dictBaseUrl: string, voiceUrl: string }`

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
| Japanese | `ja` | OpenJTalk (WASM) | Full phoneme analysis with prosody features (A1/A2/A3) |
| English | `en` | Dictionary + rules (JS) | Built-in dictionary-based G2P |
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

## Advanced Usage

### Using SimpleUnifiedPhonemizer Directly

For phonemization without ONNX inference:

```javascript
import { SimpleUnifiedPhonemizer } from "piper-plus";

const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({
  openjtalk: {
    jsPath: "./dist/openjtalk.js",
    wasmPath: "./dist/openjtalk.wasm",
    dictPath: "./assets/dict",
    voicePath: "./assets/voice/mei_normal.htsvoice",
  },
});

// Japanese: returns OpenJTalk full-context labels
const jaLabels = await phonemizer.textToPhonemes("こんにちは", "ja");
const jaPhonemes = phonemizer.extractPhonemes(jaLabels, "ja");

// English: returns IPA string
const enIPA = await phonemizer.textToPhonemes("Hello world", "en");
const enPhonemes = phonemizer.extractPhonemes(enIPA, "en");

phonemizer.dispose();
```

### Cache Management

Models and dictionaries are cached in IndexedDB. You can manage caches programmatically:

```javascript
import { ModelManager, DictManager } from "piper-plus";

// Check if dictionaries are already cached
const dictManager = new DictManager();
const isCached = await dictManager.isCached();

// Clear model cache
const modelManager = new ModelManager();
await modelManager.clearCache();

// Clear dictionary cache
await dictManager.clearCache();
```

### URL Resolution

Resolve model or dictionary URLs without downloading:

```javascript
import { ModelManager, DictManager } from "piper-plus";

// Resolve model URL from a shortcut or repo name
const modelMgr = new ModelManager();
const { modelUrl, configUrl, cacheKey } = await modelMgr.resolveUrls("tsukuyomi");
console.log(modelUrl);  // https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/main/...

// Resolve dictionary URLs
const dictMgr = new DictManager();
const { dictBaseUrl, voiceUrl } = dictMgr.resolveUrls({
  dictUrl: "https://custom-cdn.example.com/dict",
});
console.log(dictBaseUrl);  // https://custom-cdn.example.com/dict (trailing slash removed)
```

### Sub-path Imports

The package exposes additional entry points for selective imports:

```javascript
// Phonemizer only (no ONNX dependency)
import { SimpleUnifiedPhonemizer } from "piper-plus/phonemizer";

// Streaming pipeline
import { StreamingTTSPipeline, TextChunker } from "piper-plus/streaming";
```

## License

MIT
