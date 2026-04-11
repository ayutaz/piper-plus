# Migration Guide: piper-plus v0.1.x to v0.2.0

## Overview

piper-plus v0.2.0 replaces the Emscripten-compiled OpenJTalk C WASM with a Rust-based jpreprocess WASM module. The Japanese dictionary (~103MB uncompressed) is now bundled directly into the WASM binary (~19MB gzip transfer), eliminating the separate dictionary download, IndexedDB caching, and the multi-step initialization pipeline. This results in faster startup (0.3-1s vs 3-5s), zero IndexedDB usage for dictionaries, and fixes several phonemization bugs.

## Breaking Changes

### 1. `SimpleUnifiedPhonemizer.initialize()` — new config format

The `initialize()` method now accepts a `PhonemizerInitConfig` object with a `configJson` property (the model's `config.json` as a string) instead of the previous empty-or-path-based initialization.

**v0.1.x:**
```js
const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize();
// or with deployment config:
await phonemizer.initialize({ basePath: '/my-app' });
```

**v0.2.0:**
```js
const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({
  configJson: JSON.stringify(modelConfig)  // model's config.json content
});
```

The `configJson` is required for the Rust WASM phonemizer to resolve `phoneme_id_map` and `language_id_map` from your model. Without it, the `WasmPhonemizer` instance will not be created, and Japanese phonemization will not work.

### 2. `DictManager` class removed

The `DictManager` class and all dictionary download/cache logic have been removed. The dictionary is now embedded in the WASM binary.

**v0.1.x:**
```js
import { DictManager } from 'piper-plus';

const dictManager = new DictManager();
await dictManager.loadDictionary();
// ... pass dictionary to phonemizer
```

**v0.2.0:**
```js
// No equivalent needed. Dictionary is bundled in WASM.
// Just initialize the phonemizer:
const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({ configJson: '...' });
```

If you were using `DictManager` to manage IndexedDB storage or check cache status, you can remove that code entirely.

### 3. Removed exports

The following exports are no longer available from the package:

| Removed Export | Reason |
|----------------|--------|
| `DictManager` | Dictionary bundled in WASM; no download needed |
| `ESpeakPhonemeExtractor` | eSpeak-ng integration removed (GPL risk) |
| `espeak_phonemizer` | eSpeak-ng integration removed |
| `openjtalk_wrapper` | Replaced by `WasmPhonemizer` |
| `api` (legacy ccall-based API) | Replaced by `WasmPhonemizer` |
| `unified_api` (eSpeak+OpenJTalk) | Replaced by `SimpleUnifiedPhonemizer` |

### 4. `textToPhonemes()` return type for Japanese

In v0.1.x, Japanese phonemization returned OpenJTalk fullcontext label strings that you had to parse yourself or pass through `extractPhonemes()`. In v0.2.0, when using the high-level `PiperPlus` API, phonemization is handled internally by the Rust WASM module which returns phoneme IDs and prosody features directly.

If you use `SimpleUnifiedPhonemizer.textToPhonemes()` directly, the return type for Japanese is still a string (for backward compatibility with `extractPhonemes()`), but the underlying processing now goes through Rust.

### 5. No more Emscripten WASM files

The following files no longer exist in the package:

- `dist/openjtalk.js` (Emscripten glue code)
- `dist/openjtalk.wasm` (Emscripten WASM binary)
- `dist/load-dictionary.js` (dictionary loader)

They are replaced by:

- `dist/rust-wasm/piper_plus_wasm.js` (wasm-bindgen glue code)
- `dist/rust-wasm/piper_plus_wasm_bg.wasm` (Rust WASM binary with bundled dictionary)

If you reference these paths directly (e.g., in a service worker or custom build), update them accordingly.

## Migration Steps

### Step 1: Update the package

```bash
npm install piper-plus@0.2.0
```

### Step 2: Remove DictManager usage

Search your codebase for `DictManager` and remove all references:

```bash
# Find files to update
grep -r "DictManager\|dict-manager\|loadDictionary" src/
```

Delete any IndexedDB cleanup code that was specific to the dictionary cache (`piper-dict-cache` or similar database names).

### Step 3: Update SimpleUnifiedPhonemizer initialization

If you use `SimpleUnifiedPhonemizer` directly:

**Before:**
```js
import { SimpleUnifiedPhonemizer } from 'piper-plus/phonemizer';

const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize();
```

**After:**
```js
import { SimpleUnifiedPhonemizer } from 'piper-plus/phonemizer';

const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({
  configJson: JSON.stringify(modelConfig)  // from your model's config.json
});
```

### Step 4: Update PiperPlus initialization (if using high-level API)

If you use the `PiperPlus` class, no code changes are needed. The `PiperPlus.initialize()` method handles the new phonemizer setup internally:

```js
import { PiperPlus } from 'piper-plus';

// This works the same as before
const tts = await PiperPlus.initialize({
  model: 'ayousanz/piper-plus-tsukuyomi-chan',
  ort: ort,
  onProgress: (info) => console.log(info.message),
});

const audio = await tts.synthesize('Hello, world!');
await audio.play();
```

### Step 5: Remove eSpeak-ng references

If you used `ESpeakPhonemeExtractor` or `espeak_phonemizer`, replace them with `SimpleUnifiedPhonemizer` which now handles all 8 languages through the Rust WASM backend:

**Before:**
```js
import { ESpeakPhonemeExtractor } from 'piper-plus';
const extractor = new ESpeakPhonemeExtractor();
```

**After:**
```js
import { SimpleUnifiedPhonemizer } from 'piper-plus/phonemizer';
const phonemizer = new SimpleUnifiedPhonemizer();
await phonemizer.initialize({ configJson: '...' });
const result = await phonemizer.textToPhonemes(text, 'en');
```

### Step 6: Update error handling (optional but recommended)

v0.2.0 adds structured error codes. You can now catch specific error types:

```js
try {
  const result = await phonemizer.textToPhonemes(text, 'ja');
} catch (error) {
  if (error.code === 'WASM_RUNTIME_ERROR') {
    // WASM-level error (e.g., memory, unreachable trap)
    console.error('WASM error:', error.message);
  } else {
    throw error;
  }
}
```

### Step 7: Clean up IndexedDB (optional)

If your users have existing dictionary caches from v0.1.x, you may want to clean them up on first load to reclaim ~103MB of storage:

```js
// One-time cleanup of v0.1.x dictionary cache
async function cleanupLegacyCache() {
  try {
    const databases = await indexedDB.databases();
    for (const db of databases) {
      if (db.name && db.name.includes('piper-dict')) {
        indexedDB.deleteDatabase(db.name);
        console.log(`Cleaned up legacy cache: ${db.name}`);
      }
    }
  } catch (_e) {
    // indexedDB.databases() not supported in all browsers
  }
}
```

## What's New

### Faster initialization

| Metric | v0.1.x | v0.2.0 |
|--------|--------|--------|
| First load | 3-5s (dict download + decompress + IndexedDB write) | 0.3-1s (single WASM load) |
| Subsequent loads | 1-2s (IndexedDB read + Emscripten FS write) | 0.3-1s (browser WASM cache) |
| Network requests | 2+ (dictionary tar.gz + voice file) | 1 (WASM binary) |

### No IndexedDB for dictionary

v0.1.x stored ~103MB of uncompressed dictionary data in IndexedDB. v0.2.0 uses zero IndexedDB for dictionary purposes (models are still cached in IndexedDB via `ModelManager`).

### Structured error codes

Errors from WASM operations now carry a `.code` property:

| Error Code | When |
|------------|------|
| `WASM_RUNTIME_ERROR` | WebAssembly runtime error (unreachable trap, out-of-bounds memory) |

Input validation also provides clear error messages:
- Text exceeding 100K characters is rejected before reaching WASM
- Disposed phonemizer instances throw immediately
- Uninitialized phonemizer access throws with a descriptive message

### 8-language support

All 8 languages are handled by the Rust WASM backend with proper phonemization:

| Language | Code | Phonemization |
|----------|------|---------------|
| Japanese | `ja` | jpreprocess (NAIST-JDIC dictionary bundled) |
| English | `en` | Rule-based (SimpleEnglishPhonemizer) |
| Chinese | `zh` | Character-based with pinyin decomposition |
| Korean | `ko` | Hangul jamo decomposition |
| Spanish | `es` | Rule-based |
| French | `fr` | Rule-based |
| Portuguese | `pt` | Rule-based |
| Swedish | `sv` | Rule-based |

### Bug fixes included in v0.2.0

- **Question markers**: Japanese question types (`?!`, `?.`, `?~`) are now correctly phonemized (were always mapped to declarative `$` in v0.1.x)
- **Prosody features**: A1/A2/A3 prosody features are now extracted and passed to the model (were missing in v0.1.x)
- **PUA mapping**: All 96 PUA character entries are now complete (3 were missing in v0.1.x)
- **Non-JA double-mapping**: Fixed a phoneme ID double-mapping bug for non-Japanese languages

### Initialization race condition protection

Calling `initialize()` multiple times concurrently is now safe. Only the first call runs initialization; subsequent calls await the same promise. If initialization fails, the next call will retry.

### 30-second WASM init timeout

If the WASM binary fails to load within 30 seconds (e.g., network issues), initialization rejects with a clear timeout error instead of hanging indefinitely.

## FAQ

### Are my existing ONNX models compatible with v0.2.0?

Yes. The ONNX model format is unchanged. Any model that worked with v0.1.x will work with v0.2.0. The phoneme ID mapping is read from the model's `config.json`, so model compatibility is automatic.

### Does the WASM binary size affect my bundle?

The Rust WASM binary is ~58MB uncompressed (~19MB gzip). It is loaded at runtime via `fetch()`, not included in your JavaScript bundle. CDN gzip/brotli compression applies automatically. The browser also caches the compiled WASM module, so repeat visits are fast.

Compared to v0.1.x, the total transfer is actually slightly smaller: v0.1.x transferred ~20.5MB across multiple requests (dictionary tar.gz + voice + Emscripten WASM), while v0.2.0 transfers ~19MB in a single request.

### Which browsers are supported?

Any browser with WebAssembly support (all modern browsers since 2017). The `WebAssembly.compileStreaming()` optimization is used when available; older browsers fall back to `arrayBuffer`-based loading automatically.

Minimum versions:
- Chrome 57+
- Firefox 52+
- Safari 11+
- Edge 16+

### Can I use a custom or subset dictionary?

Not currently. The NAIST-JDIC dictionary is compiled into the WASM binary at build time. Dictionary subsetting was evaluated but rejected due to quality degradation (loss of proper noun readings, compound word accent boundaries, and prosody features). If you need a custom dictionary build, you can build `piper-wasm` from source with a modified dictionary.

### Does v0.2.0 work with Node.js?

piper-plus is browser-only. The WASM module uses `import.meta.url` for path resolution and expects browser APIs (`fetch`, `WebAssembly`, `AudioContext`). For server-side TTS, use the Rust CLI (`piper-plus-cli`) or the Python bindings (`piper-plus-python`).

### I was using `DictManager` to show download progress. How do I show progress now?

Since the dictionary is bundled in the WASM binary, there is no separate dictionary download to track. If you want to show WASM loading progress, use the `PiperPlus.initialize()` `onProgress` callback:

```js
const tts = await PiperPlus.initialize({
  model: 'ayousanz/piper-plus-tsukuyomi-chan',
  ort: ort,
  onProgress: ({ stage, progress, message }) => {
    // stage: 'model' | 'phonemizer' | 'ready'
    updateProgressBar(progress);
    updateStatusText(message);
  },
});
```

### My app stored dictionary data in IndexedDB. Will that be cleaned up automatically?

No. v0.2.0 simply stops using IndexedDB for dictionary storage. The old data (~103MB) will remain until explicitly deleted. See Step 7 in the Migration Steps above for a cleanup snippet.

---

# Migration Guide: piper-plus v0.2.0 to v0.4.0

## Overview

piper-plus v0.3.0/v0.4.0 removes the HTS voice file dependency entirely. The `_openjtalk_initialize()` WASM function now takes only a dictionary path (1 parameter instead of 2). The `@piper-plus/g2p` package (v0.3.0) removes `voiceData` from its API.

If you are using the high-level `PiperPlus` API, **no code changes are required** — the API is unchanged. These are internal breaking changes that only affect direct WASM or `@piper-plus/g2p` usage.

## Breaking Changes

### 1. `@piper-plus/g2p` v0.3.0: `voiceData` removed

If you use `JapaneseG2P` or `DictLoader` directly from `@piper-plus/g2p`:

**Before (v0.2.0):**
```js
const ja = new JapaneseG2P({
  jaDict: { dictFiles: {...}, voiceData: {...} }
});
```

**After (v0.3.0+):**
```js
const loader = new DictLoader();
const jaDict = await loader.loadJaDict();
// jaDict = { dictFiles: { 'sys.dic': ArrayBuffer, ... } }
const ja = new JapaneseG2P({ jaDict });
```

`voiceData` is no longer accepted. `DictLoader.loadJaDict()` no longer accepts `includeVoice` or `voiceUrl` options.

### 2. WASM ABI change: `_openjtalk_initialize(dictPtr)`

If you call the WASM C function directly:

**Before:** `_openjtalk_initialize(dictPtr, voicePtr)`
**After:** `_openjtalk_initialize(dictPtr)`

### 3. IndexedDB cache cleanup

If upgrading from v0.2.0 or earlier, stale voice data may remain in IndexedDB. Clean it up:

```js
// Optional: clean up stale voice cache from older versions
const dbs = await indexedDB.databases();
for (const db of dbs) {
  if (db.name && db.name.includes('piper-g2p-cache')) {
    indexedDB.deleteDatabase(db.name);
  }
}
```

## Migration Steps

1. Update packages:
   ```bash
   npm install piper-plus@0.4.0
   ```

2. If using `@piper-plus/g2p` directly:
   ```bash
   npm install @piper-plus/g2p@0.3.0
   ```

3. Remove any `voiceData`, `includeVoice`, or `voiceUrl` references in your code.

4. No changes needed for `PiperPlus` high-level API users.
