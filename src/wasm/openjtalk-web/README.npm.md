# piper-plus

[![npm version](https://img.shields.io/npm/v/piper-plus)](https://www.npmjs.com/package/piper-plus)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Browser-based multilingual neural TTS powered by VITS. No server required.

## Why piper-plus?

piper-plus is built for projects that need high-quality multilingual TTS in the browser -- particularly Japanese. Unlike packages that rely on espeak-ng (GPL-licensed, limited Japanese prosody), piper-plus ships its own rule-based G2P for each language, with a full OpenJTalk-based phonemizer for Japanese that handles pitch accent and prosody correctly. The entire stack is MIT-licensed with no GPL dependencies.

| Feature | piper-plus | kokoro-js | @mintplex-labs/piper-tts-web |
|---------|-----------|-----------|------------------------------|
| License | MIT | Apache 2.0 | MIT |
| Japanese G2P | OpenJTalk (prosody, accent) | espeak-ng (limited) | espeak-ng |
| Languages | 8 (JA/EN/ZH/KO/ES/FR/PT/SV) | Multiple (English-optimized) | Depends on Piper model |
| espeak-ng dependency | None (GPL-free) | Required | Required |
| Custom G2P per language | Yes (rule-based) | No | No |
| Browser-only (no server) | Yes | Yes | Yes |

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

### importmap (No Bundler)

```html
<script type="importmap">
{
  "imports": {
    "piper-plus": "https://cdn.jsdelivr.net/npm/piper-plus@0.5.0/src/index.js",
    "onnxruntime-web": "https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/ort.min.mjs"
  }
}
</script>
<script type="module">
  import { PiperPlus } from "piper-plus";
  const piper = await PiperPlus.initialize("tsukuyomi");
  const audio = await piper.synthesize("Hello, world!");
  audio.play();
</script>
```

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

## Phoneme Timing (Lip-sync, subtitles, karaoke)

`piper-plus` can extract precise phoneme-level timing from the VITS duration
predictor. This enables lip-sync animation, subtitle generation, karaoke-style
text highlighting, and phoneme-level analytics — all entirely in the browser.

### Basic usage

```javascript
import { PiperPlus } from 'piper-plus';

const piper = await PiperPlus.initialize({ model: 'tsukuyomi' });
const result = await piper.synthesize('こんにちは');

if (result.hasTimingInfo) {
  for (const p of result.timing.phonemes) {
    console.log(
      `${p.phoneme}: ${p.start_ms.toFixed(1)} → ${p.end_ms.toFixed(1)} ms`,
    );
  }
  console.log(`Total: ${result.timing.total_duration_ms.toFixed(1)} ms`);
}
```

Example output:

```
^: 0.0 → 58.0 ms
k: 58.0 → 150.8 ms
o: 150.8 → 290.0 ms
N: 290.0 → 406.0 ms
n: 406.0 → 487.2 ms
i: 487.2 → 591.6 ms
ch: 591.6 → 661.2 ms
i: 661.2 → 788.8 ms
w: 788.8 → 881.6 ms
a: 881.6 → 1044.0 ms
$: 1044.0 → 1102.0 ms
Total: 1102.0 ms
```

### Output formats

piper-plus provides four serialization helpers compatible with
Rust/Go/Python/C#/C++ runtimes (byte-for-byte output):

```javascript
import {
  timingToJson,         // Pretty-printed JSON
  timingToJsonCompact,  // Single-line JSON
  timingToTsv,          // Tab-separated values with header
  timingToSrt,          // SubRip subtitle format
} from 'piper-plus';

const jsonStr = timingToJson(result.timing);
const tsvStr = timingToTsv(result.timing);
const srtStr = timingToSrt(result.timing);
```

**SRT output** can be saved alongside the audio for playback in media players:

```
1
00:00:00,000 --> 00:00:00,058
^

2
00:00:00,058 --> 00:00:00,151
k

3
00:00:00,151 --> 00:00:00,290
o
...
```

### Lip-sync example (Viseme mapping)

```javascript
// Japanese phoneme → simplified viseme (mouth shape)
const PHONEME_TO_VISEME = {
  a: 'A', i: 'I', u: 'U', e: 'E', o: 'O',
  k: 'K', g: 'K',
  s: 'S', sh: 'S', z: 'S',
  t: 'T', d: 'T', ts: 'T', ch: 'T',
  n: 'N', N: 'N',
  m: 'M', b: 'M', p: 'M',
  w: 'W', y: 'Y',
  h: 'H', f: 'H',
  r: 'R',
  '^': 'SILENT', $: 'SILENT', _: 'SILENT',
};

function playLipSync(result) {
  if (!result.hasTimingInfo) return;

  const startAt = performance.now();
  for (const p of result.timing.phonemes) {
    const delay = p.start_ms - (performance.now() - startAt);
    setTimeout(() => {
      const viseme = PHONEME_TO_VISEME[p.phoneme] ?? 'SILENT';
      updateMouthShape(viseme); // your animation function
    }, Math.max(0, delay));
  }
}

const result = await piper.synthesize('こんにちは');
await result.play();
playLipSync(result);
```

### Manual timing extraction

If you already have a `durations` tensor from another source, use
`durationsToTiming` directly:

```javascript
import { durationsToTiming } from 'piper-plus';

const durations = new Float32Array([10, 15, 12, 8]); // frame counts
const sampleRate = 22050;
const hopLength = 256; // VITS default
const tokens = ['a', 'e', 'i', 'o']; // optional; defaults to ph_0, ph_1, ...

const timing = durationsToTiming(durations, sampleRate, hopLength, tokens);
```

### API reference

| Export | Description |
|---|---|
| `AudioResult.timing` | `TimingResult \| null` |
| `AudioResult.hasTimingInfo` | `boolean` |
| `durationsToTiming(durations, sampleRate, hopLength?, phonemeTokens?)` | Convert frame counts to `TimingResult` |
| `timingToJson(result)` | Pretty-printed JSON string |
| `timingToJsonCompact(result)` | Single-line JSON string |
| `timingToTsv(result)` | TSV with header line |
| `timingToSrt(result)` | SubRip subtitle format |
| `buildPhonemeIdToTokenMap(phonemeIdMap, puaToMultiChar?)` | Reverse map from phoneme ID to token string |
| `DEFAULT_HOP_LENGTH` | `256` (VITS default) |

> **Note**: Field names use `snake_case` (`start_ms`, `end_ms`, `duration_ms`,
> `total_duration_ms`, `sample_rate`) to maintain byte-for-byte JSON
> compatibility with the Rust / Go / Python / C# / C++ runtimes.

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

## piper-plus vs Kokoro.js

| Feature | piper-plus | Kokoro.js |
|---------|-----------|-----------|
| Languages | 8 (JA/EN/ZH/KO/ES/FR/PT/SV) | 1 (EN-optimized) |
| espeak-ng dependency | None | Required |
| License | MIT | Apache-2.0 |
| Model size (WASM) | ~38 MB (FP16) | ~320 MB |
| Offline capable | Yes | Yes |
| G2P | Built-in (8 languages) | espeak-ng based |
| Japanese quality | Native quality (OpenJTalk) | Limited |

## License

MIT
