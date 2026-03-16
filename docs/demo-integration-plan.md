# Demo Integration Plan: WebGPU Optimization Components into demo/index.html

**Branch**: `feature/webgpu-optimization`
**Created**: 2026-03-16
**Target file**: `src/wasm/openjtalk-web/demo/index.html`
**Status**: Plan only -- do NOT modify index.html yet

---

## 1. Current Architecture

### 1.1 File Structure

The demo is a single-file HTML application at `src/wasm/openjtalk-web/demo/index.html` (830 lines). All logic lives inside a `<script type="module">` block (lines 308-828).

### 1.2 Module Imports (lines 309-311)

```javascript
import { SimpleUnifiedPhonemizer } from '../src/simple_unified_api.js';
import { ESpeakPhonemeExtractor } from '../src/espeak_phoneme_extractor.js';
import { CustomDictionary } from '../src/custom_dictionary.js';
```

### 1.3 Global State (lines 313-318)

```javascript
let unifiedPhonemizer = null;
let espeakExtractor = null;
let onnxSession = null;       // raw ort.InferenceSession
let customDict = null;
let currentModelConfig = null;
let currentLanguage = 'ja';
```

### 1.4 Initialization Flow (lines 361-430)

The `init()` function executes these steps sequentially:

1. **Custom dictionary loading** (lines 366-382) -- loads 4 JSON dictionaries via `customDict.loadFromJSON(dictionaries)`
2. **Phonemizer initialization** (lines 384-403) -- creates `SimpleUnifiedPhonemizer`, calls `initialize()` with OpenJTalk WASM/dict/voice paths
3. **eSpeak-ng initialization** (lines 405-409) -- creates `ESpeakPhonemeExtractor`, calls `initialize()`
4. **ONNX Runtime loading** (line 412) -- dynamically injects a `<script>` tag for the CDN URL
5. **Model loading** (lines 414-415) -- calls `loadModel(currentLanguage)`
6. **UI setup** (lines 417-424) -- enables synthesize button, populates templates, attaches event listeners

### 1.5 Dictionary Loading

Dictionaries are plain JSON files loaded via the `CustomDictionary` class. The OpenJTalk WASM dictionary (MeCab binary files) is loaded separately inside `SimpleUnifiedPhonemizer.initialize()` using raw `fetch` calls -- there is **no IndexedDB caching** anywhere.

The four custom dictionaries (lines 370-375):
- `../assets/custom_dictionary.json`
- `../assets/default_tech_dict.json`
- `../assets/default_common_dict.json`
- `../assets/additional_tech_dict.json`

### 1.6 ONNX Model Loading

**`loadModel()` function** (lines 528-545):

```javascript
async function loadModel(lang) {
    const config = languageConfigs[lang];
    const modelPath = `../models/${config.model}`;
    const configPath = `../models/${config.model}.json`;

    const configResponse = await fetch(configPath);
    currentModelConfig = await configResponse.json();

    onnxSession = await ort.InferenceSession.create(modelPath, {
        executionProviders: ['wasm'],
        graphOptimizationLevel: 'extended',
        enableMemPattern: true
    });
}
```

Key observations:
- Hardcoded `['wasm']` execution provider -- no WebGPU, no SIMD fallback
- Model is fetched from network every time -- no caching
- Config JSON is also fetched every time -- no caching
- The `onnxSession` is a raw `ort.InferenceSession` stored as a global

### 1.7 Language Configurations (lines 320-347)

```javascript
const languageConfigs = {
    'ja': {
        name: '日本語',
        model: 'ja_JP-test-medium.onnx',
        phonemizer: 'openjtalk',
        testText: 'こんにちは、世界！...',
        templates: [...]
    },
    'en': {
        name: '英語 (eSpeak-ng)',
        model: 'test_voice.onnx',
        phonemizer: 'espeak-ng',
        testText: 'Hello world!...',
        templates: [...]
    }
};
```

---

## 2. ORT Version and CDN URL

### 2.1 Current CDN URL

**Line 412**:
```javascript
await loadScript('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js');
```

- **Version**: 1.21.0
- **Loaded via**: dynamic `<script>` tag injection (`loadScript()` at lines 779-787)
- **Format**: global `ort` object (not an ES module import)

### 2.2 loadScript helper (lines 779-787)

```javascript
function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}
```

### 2.3 Note on ORT version

The `docs/webgpu-optimization-plan.md` references version 1.17.1 in some sections, but the actual demo already uses **1.21.0**. The WebGPUSessionManager integration should work with this version since ONNX Runtime Web 1.19+ supports `webgpu` and `wasm-simd` execution providers.

---

## 3. Audio Playback (Current Implementation)

### 3.1 Current approach: WAV blob + HTML `<audio>` element

The demo does **not** use ScriptProcessor directly. Instead it:

1. Generates raw Float32Array audio from ONNX inference (line 758-759)
2. Converts to WAV blob via `createWAV()` (line 619)
3. Sets the WAV blob URL on the `<audio>` element (lines 620-621)

### 3.2 createWAV function (lines 789-824)

```javascript
function createWAV(audioData, sampleRate) {
    const length = audioData.length;
    const arrayBuffer = new ArrayBuffer(44 + length * 2);
    const view = new DataView(arrayBuffer);

    // WAV header (lines 795-813)
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);     // PCM
    view.setUint16(22, 1, true);     // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);     // block align
    view.setUint16(34, 16, true);    // bits per sample
    writeString(36, 'data');
    view.setUint32(40, length * 2, true);

    // Float32 -> Int16 conversion (lines 816-821)
    for (let i = 0; i < length; i++) {
        const val = Math.max(-1, Math.min(1, audioData[i]));
        const int16 = val < 0 ? val * 0x8000 : val * 0x7FFF;
        view.setInt16(offset + i * 2, int16, true);
    }

    return new Blob([arrayBuffer], { type: 'audio/wav' });
}
```

### 3.3 Audio playback wiring (lines 619-621)

```javascript
const wavBlob = createWAV(audio, currentModelConfig.audio.sample_rate);
const audioUrl = URL.createObjectURL(wavBlob);
audioPlayer.src = audioUrl;
```

### 3.4 Stop button (lines 453-457)

```javascript
stopBtn.addEventListener('click', () => {
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
    stopBtn.disabled = true;
});
```

### 3.5 Audio element in HTML (line 293)

```html
<audio id="audioPlayer" controls style="width: 100%;"></audio>
```

### 3.6 Key issue

The model outputs audio at its native sample rate (typically 22050 Hz from `currentModelConfig.audio.sample_rate`). The WAV is created at that rate and played through the `<audio>` element. There is **no resampling** and **no AudioWorklet/ScriptProcessor** usage.

---

## 4. ONNX Inference (Current Implementation)

### 4.1 synthesizeAudio function (lines 718-760)

```javascript
async function synthesizeAudio(phonemeIds, prosodyFeatures) {
    const inputTensor = new ort.Tensor('int64',
        new BigInt64Array(phonemeIds.map(id => BigInt(id))),
        [1, phonemeIds.length]
    );
    const lengthTensor = new ort.Tensor('int64',
        new BigInt64Array([BigInt(phonemeIds.length)]),
        [1]
    );
    const scalesTensor = new ort.Tensor('float32',
        new Float32Array([
            currentModelConfig.inference.noise_scale || 0.667,
            currentModelConfig.inference.length_scale || 1.0,
            currentModelConfig.inference.noise_w || 0.8
        ]),
        [3]
    );
    const feeds = {
        'input': inputTensor,
        'input_lengths': lengthTensor,
        'scales': scalesTensor
    };
    // Optional prosody features (lines 745-754)
    if (prosodyFeatures && currentModelConfig.prosody_id_map) {
        // ... adds prosody_features tensor
    }
    const results = await onnxSession.run(feeds);
    const audioTensor = results['output'] || results[Object.keys(results)[0]];
    return new Float32Array(audioTensor.data);
}
```

### 4.2 TypedArray allocations per inference

| Line(s) | Type | Purpose | Size |
|---------|------|---------|------|
| 719-721 | BigInt64Array | phoneme IDs | variable (8 * N bytes) |
| 724-726 | BigInt64Array | input lengths | 8 bytes |
| 729-734 | Float32Array | scales | 12 bytes |
| 747-749 | BigInt64Array | prosody features | variable (24 * N bytes) |
| 759 | Float32Array | audio output | ~110-220 KB |
| 791 | ArrayBuffer | WAV buffer | ~110-220 KB |

All of these are freshly allocated on every inference call.

---

## 5. Integration Plan

### 5.1 New Imports

Add these imports at the top of the `<script type="module">` block (after line 311):

```javascript
import { SimpleUnifiedPhonemizer } from '../src/simple_unified_api.js';
import { ESpeakPhonemeExtractor } from '../src/espeak_phoneme_extractor.js';
import { CustomDictionary } from '../src/custom_dictionary.js';
// --- NEW IMPORTS ---
import { CacheManager } from '../src/cache-manager.js';
import { WebGPUSessionManager } from '../src/webgpu-session-manager.js';
import { AudioBackendFactory } from '../src/audio-backend-factory.js';
import { SimpleResampler } from '../src/resampler.js';
import { BenchmarkRunner } from '../src/benchmark.js';
```

### 5.2 New Global State

Add after the existing globals (line 318):

```javascript
// --- NEW GLOBALS ---
let cacheManager = null;
let sessionManager = null;
let audioBackend = null;
let resampler = null;
let benchmark = new BenchmarkRunner();
```

---

### 5.3 Component 1: CacheManager (IndexedDB Caching)

**Source**: `src/wasm/openjtalk-web/src/cache-manager.js`

**Purpose**: Cache ONNX model files and model config JSON in IndexedDB so they are not re-downloaded on every page load.

**Integration points**:

#### 5.3.1 Initialization

Insert inside `init()`, before dictionary loading (before line 366):

```javascript
// Initialize CacheManager with real IndexedDB
updateStatus('キャッシュを初期化しています...');
cacheManager = new CacheManager({
    dbFactory: () => {
        // Open (or create) the IndexedDB database
        // CacheManager expects a db object with transaction() method
        // We need a thin wrapper around real IndexedDB
        return openCacheDB();
    }
});
```

**Important note**: The `CacheManager` constructor expects `dbFactory` to return an object with `transaction(storeName, mode)` that returns `{ objectStore() }`. The current implementation is designed for both a mock IDB (tests) and real IDB. For real browser integration, a thin wrapper around `indexedDB.open()` is needed:

```javascript
async function openCacheDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('piper-tts-cache', 1);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains('cache')) {
                db.createObjectStore('cache', { keyPath: 'key' });
            }
        };
        request.onsuccess = () => {
            const db = request.result;
            // Wrap to match CacheManager's expected interface
            resolve({
                transaction(storeName, mode) {
                    const tx = db.transaction(storeName, mode);
                    return {
                        objectStore() {
                            return tx.objectStore(storeName);
                        }
                    };
                }
            });
        };
        request.onerror = () => reject(request.error);
    });
}
```

Because `CacheManager` constructor calls `dbFactory()` synchronously, but `indexedDB.open()` is async, the CacheManager initialization must happen after the DB is opened. The integration agent should either:
- **(Option A)** Open the DB first, then pass the wrapper into the constructor.
- **(Option B)** Modify `CacheManager` to accept an async `dbFactory`.

**Recommended: Option A**:

```javascript
const db = await openCacheDB();
cacheManager = new CacheManager({ dbFactory: () => db });
```

#### 5.3.2 Caching Model Files

Replace the `loadModel()` function (lines 528-545) with:

```javascript
async function loadModel(lang) {
    const config = languageConfigs[lang];
    const modelPath = `../models/${config.model}`;
    const configPath = `../models/${config.model}.json`;
    const modelVersion = 'v1.0';  // Bump when models change

    // Load model config (with cache)
    if (cacheManager) {
        const cachedConfig = await cacheManager.getOrFetch(
            `config:${config.model}`,
            modelVersion,
            async () => {
                const resp = await fetch(configPath);
                const json = await resp.json();
                // Store as ArrayBuffer for CacheManager compatibility
                return new TextEncoder().encode(JSON.stringify(json)).buffer;
            }
        );
        currentModelConfig = JSON.parse(new TextDecoder().decode(cachedConfig));
    } else {
        const configResponse = await fetch(configPath);
        currentModelConfig = await configResponse.json();
    }

    // Load ONNX model (with cache)
    let modelData;
    if (cacheManager) {
        modelData = await cacheManager.getOrFetch(
            `model:${config.model}`,
            modelVersion,
            async () => {
                const resp = await fetch(modelPath);
                return await resp.arrayBuffer();
            }
        );
    } else {
        const resp = await fetch(modelPath);
        modelData = await resp.arrayBuffer();
    }

    // Create session via WebGPUSessionManager (see 5.4)
    // or fall back to direct creation
    if (sessionManager) {
        onnxSession = await sessionManager.createSession(modelData);
    } else {
        onnxSession = await ort.InferenceSession.create(modelData, {
            executionProviders: ['wasm'],
            graphOptimizationLevel: 'extended',
            enableMemPattern: true
        });
    }

    console.log(`Loaded ${config.name} model (provider: ${sessionManager?.currentProvider || 'wasm'})`);
}
```

**Note on `createSession` with ArrayBuffer**: The `WebGPUSessionManager.createSession()` currently accepts a `modelPath` string. When integrating with cache, the model data will be an `ArrayBuffer` from IndexedDB rather than a URL. `ort.InferenceSession.create()` accepts both a URL string and a `Uint8Array`/`ArrayBuffer`, so passing cached data directly works. The `WebGPUSessionManager.createSession()` method may need a minor adaptation to accept `ArrayBuffer` input as well as path strings. See section 5.4.3.

#### 5.3.3 Cache Priority

Set model data to `medium` priority and dictionary data to `high` priority to comply with iOS 50MB quota management:

```javascript
// After caching model data
await cacheManager.set(`model:${config.model}`, modelData, {
    version: modelVersion,
    priority: 'medium'  // Models can be evicted if space is needed
});
```

---

### 5.4 Component 2: WebGPUSessionManager

**Source**: `src/wasm/openjtalk-web/src/webgpu-session-manager.js`

**Purpose**: Replace the hardcoded `executionProviders: ['wasm']` with automatic fallback: `webgpu -> wasm-simd -> wasm`.

#### 5.4.1 Initialization

Insert inside `init()`, after ONNX Runtime script is loaded (after line 412):

```javascript
// Initialize WebGPUSessionManager
sessionManager = new WebGPUSessionManager({
    ort: ort,
    gpu: navigator.gpu || undefined
});
```

#### 5.4.2 Replace Session Creation

In `loadModel()` (currently line 538-542), replace:

```javascript
// BEFORE:
onnxSession = await ort.InferenceSession.create(modelPath, {
    executionProviders: ['wasm'],
    graphOptimizationLevel: 'extended',
    enableMemPattern: true
});

// AFTER:
onnxSession = await sessionManager.createSession(modelPath);
```

#### 5.4.3 ArrayBuffer Support

The current `WebGPUSessionManager.createSession()` passes `modelPath` directly to `ort.InferenceSession.create()`. Since ORT accepts both URL strings and `Uint8Array`/`ArrayBuffer`, when combining with CacheManager the cached ArrayBuffer can be passed directly:

```javascript
// Works with both URL string and ArrayBuffer/Uint8Array
onnxSession = await sessionManager.createSession(modelData);
```

However, if the cached data is an `ArrayBuffer`, pass it as `new Uint8Array(modelData)` to be safe:

```javascript
if (modelData instanceof ArrayBuffer) {
    onnxSession = await sessionManager.createSession(new Uint8Array(modelData));
} else {
    onnxSession = await sessionManager.createSession(modelData);
}
```

#### 5.4.4 Display Active Provider

After model loading, display which execution provider was selected:

```javascript
console.log(`Active execution provider: ${sessionManager.currentProvider}`);
// Optionally show in status bar
updateStatus(`準備完了！ (${sessionManager.currentProvider})`, 'success');
```

---

### 5.5 Component 3: AudioBackendFactory

**Source**: `src/wasm/openjtalk-web/src/audio-backend-factory.js`

**Purpose**: Replace the `createWAV()` + `<audio>` element approach with a proper audio backend that supports AudioWorklet (low latency) with ScriptProcessor and HTMLAudio fallbacks.

#### 5.5.1 Initialization

Insert inside `init()`, after the ORT script load and before model loading (between lines 412 and 414):

```javascript
// Initialize audio backend
updateStatus('オーディオバックエンドを初期化しています...');
audioBackend = await AudioBackendFactory.create({
    workletUrl: '../src/audio-worklet-processor.js',
    sampleRate: 48000  // Target output sample rate
});
console.log(`Audio backend: ${audioBackend.type}`);
```

#### 5.5.2 Initialize Resampler

The model outputs audio at its native rate (typically 22050 Hz). The AudioWorklet/ScriptProcessor backend operates at 48000 Hz. A resampler is needed:

```javascript
// Initialize after model config is loaded (inside loadModel or after it returns)
const modelSampleRate = currentModelConfig.audio.sample_rate;  // typically 22050
resampler = new SimpleResampler(modelSampleRate, 48000);
```

**Note**: The resampler must be re-created when switching languages/models if they have different sample rates.

#### 5.5.3 Replace Audio Playback in synthesize()

Replace the current WAV blob approach (lines 619-621 of `synthesize()`) with:

```javascript
// BEFORE (lines 619-621):
const wavBlob = createWAV(audio, currentModelConfig.audio.sample_rate);
const audioUrl = URL.createObjectURL(wavBlob);
audioPlayer.src = audioUrl;

// AFTER:
const resampledAudio = resampler.resample(audio);
await audioBackend.play(resampledAudio);
```

#### 5.5.4 Replace Stop Button Handler

Replace the stop button handler (lines 453-457):

```javascript
// BEFORE:
stopBtn.addEventListener('click', () => {
    audioPlayer.pause();
    audioPlayer.currentTime = 0;
    stopBtn.disabled = true;
});

// AFTER:
stopBtn.addEventListener('click', () => {
    if (audioBackend) {
        audioBackend.stop();
    }
    stopBtn.disabled = true;
});
```

#### 5.5.5 HTMLAudioElement Fallback Consideration

The `AudioBackendFactory` already includes an `HTMLAudioBackend` as the last fallback. This backend internally uses `_encodeWav()` which is functionally identical to the demo's existing `createWAV()`. On iOS Safari where AudioWorklet is unavailable, this fallback ensures continued functionality.

#### 5.5.6 Retain `<audio>` Element for Visual Controls

The existing `<audio id="audioPlayer" controls>` element provides a visual waveform/progress bar. When using AudioWorklet or ScriptProcessor backends, this element is bypassed. Options:

- **(A)** Hide the `<audio>` element when using AudioWorklet/ScriptProcessor; show custom playback controls instead.
- **(B)** Keep the `<audio>` element as a secondary output -- generate WAV blob as before for the visual player, but use AudioBackend for actual playback.
- **(C, recommended)** Keep both: use `audioBackend.play()` for real-time playback, and simultaneously set `audioPlayer.src` to the WAV blob for the visual controls and download capability.

```javascript
// Option C implementation:
const resampledAudio = resampler.resample(audio);
await audioBackend.play(resampledAudio);

// Also update the <audio> element for visual controls
const wavBlob = createWAV(audio, currentModelConfig.audio.sample_rate);
audioPlayer.src = URL.createObjectURL(wavBlob);
```

---

### 5.6 Component 4: SimpleResampler

**Source**: `src/wasm/openjtalk-web/src/resampler.js`

**Purpose**: Convert model output (22050 Hz) to AudioContext sample rate (48000 Hz).

#### 5.6.1 Initialization

Create the resampler after model config is known:

```javascript
// Inside loadModel(), after currentModelConfig is set:
const modelSampleRate = currentModelConfig.audio.sample_rate;
resampler = new SimpleResampler(modelSampleRate, 48000);
```

#### 5.6.2 Usage in Synthesis

```javascript
// In synthesize(), after getting raw audio from ONNX:
const audio = await synthesizeAudio(phonemeIds, prosodyFeatures);
const resampledAudio = resampler.resample(audio);
```

#### 5.6.3 Edge Cases

- If model sample rate equals 48000, `SimpleResampler.resample()` returns a copy (identity case handled at line 33-35 of resampler.js).
- If the model sample rate changes when switching languages, the resampler must be re-instantiated.

---

### 5.7 Component 5: BenchmarkRunner

**Source**: `src/wasm/openjtalk-web/src/benchmark.js`

**Purpose**: Measure timing of each pipeline stage and display in the details output.

#### 5.7.1 Initialization

Already done in globals:

```javascript
let benchmark = new BenchmarkRunner();
```

#### 5.7.2 Wrap Init Stages

In `init()`, wrap each stage with `benchmark.measureAsync()`:

```javascript
async function init() {
    try {
        benchmark.reset();

        await benchmark.measureAsync('Cache Init', async () => {
            const db = await openCacheDB();
            cacheManager = new CacheManager({ dbFactory: () => db });
        });

        await benchmark.measureAsync('Dict Load', async () => {
            customDict = new CustomDictionary();
            await customDict.loadFromJSON(dictionaries);
        });

        await benchmark.measureAsync('Phonemizer Init', async () => {
            unifiedPhonemizer = new SimpleUnifiedPhonemizer({ deploymentConfig });
            await unifiedPhonemizer.initialize({ ... });
        });

        await benchmark.measureAsync('eSpeak Init', async () => {
            espeakExtractor = new ESpeakPhonemeExtractor();
            await espeakExtractor.initialize();
        });

        await benchmark.measureAsync('ORT Load', async () => {
            await loadScript('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js');
        });

        await benchmark.measureAsync('Audio Backend Init', async () => {
            audioBackend = await AudioBackendFactory.create({
                workletUrl: '../src/audio-worklet-processor.js',
                sampleRate: 48000
            });
        });

        await benchmark.measureAsync('Model Load', async () => {
            await loadModel(currentLanguage);
        });

        console.log('Init benchmark:', benchmark.getSummary());
    } catch (error) { ... }
}
```

#### 5.7.3 Wrap Synthesis Stages

In `synthesize()`:

```javascript
async function synthesize() {
    const text = inputText.value.trim();
    if (!text) { ... return; }

    try {
        benchmark.reset();

        const result = await benchmark.measureAsync('Phonemization', async () => {
            return await getPhonemes(text, currentLanguage);
        });
        const phonemes = result.phonemes;

        const phonemeIds = phonemesToIds(phonemes);

        const audio = await benchmark.measureAsync('Inference', async () => {
            return await synthesizeAudio(phonemeIds, prosodyFeatures);
        });

        const resampledAudio = await benchmark.measureAsync('Resampling', async () => {
            return resampler.resample(audio);
        });

        await benchmark.measureAsync('Audio Playback', async () => {
            await audioBackend.play(resampledAudio);
        });

        // Display benchmark results in details output
        const benchmarkSummary = benchmark.getSummary();
        detailsOutput.textContent = JSON.stringify({
            text,
            language: currentLanguage,
            executionProvider: sessionManager?.currentProvider || 'wasm',
            audioBackend: audioBackend?.type || 'unknown',
            phonemes,
            phonemeIds,
            audioLength: audio.length,
            resampledLength: resampledAudio.length,
            duration: (audio.length / currentModelConfig.audio.sample_rate).toFixed(2) + ' seconds',
            sampleRate: currentModelConfig.audio.sample_rate,
            outputSampleRate: 48000,
            benchmark: benchmarkSummary
        }, null, 2);

    } catch (error) { ... }
}
```

---

## 6. Full Revised init() Function

Below is the complete revised `init()` showing how all components connect:

```javascript
async function init() {
    try {
        benchmark.reset();
        updateStatus('初期化中...');

        // Step 1: Cache Manager
        await benchmark.measureAsync('Cache Init', async () => {
            try {
                const db = await openCacheDB();
                cacheManager = new CacheManager({ dbFactory: () => db });
            } catch (e) {
                console.warn('IndexedDB not available, running without cache:', e.message);
                cacheManager = null;
            }
        });

        // Step 2: Custom Dictionary
        updateStatus('カスタム辞書を読み込んでいます...');
        await benchmark.measureAsync('Dict Load', async () => {
            customDict = new CustomDictionary();
            const dictionaries = [
                '../assets/custom_dictionary.json',
                '../assets/default_tech_dict.json',
                '../assets/default_common_dict.json',
                '../assets/additional_tech_dict.json'
            ];
            await customDict.loadFromJSON(dictionaries);
        });

        // Step 3: Phonemizer
        updateStatus('音素化エンジンを初期化しています...');
        await benchmark.measureAsync('Phonemizer Init', async () => {
            const isGitHubPages = window.location.hostname.includes('github.io');
            const deploymentConfig = {
                isGitHubPages,
                basePath: isGitHubPages ? '/' + window.location.pathname.split('/')[1] : ''
            };
            unifiedPhonemizer = new SimpleUnifiedPhonemizer({ deploymentConfig });
            await unifiedPhonemizer.initialize({
                openjtalk: {
                    jsPath: '../dist/openjtalk.js',
                    wasmPath: '../dist/openjtalk.wasm',
                    dictPath: '../assets/dict',
                    voicePath: '../assets/voice/mei_normal.htsvoice'
                }
            });
        });

        // Step 4: eSpeak-ng
        updateStatus('eSpeak-ngを初期化しています...');
        await benchmark.measureAsync('eSpeak Init', async () => {
            espeakExtractor = new ESpeakPhonemeExtractor();
            await espeakExtractor.initialize();
        });

        // Step 5: ONNX Runtime
        updateStatus('ONNX Runtimeを読み込んでいます...');
        await benchmark.measureAsync('ORT Load', async () => {
            await loadScript('https://cdn.jsdelivr.net/npm/onnxruntime-web@1.21.0/dist/ort.min.js');
        });

        // Step 6: WebGPU Session Manager (depends on ORT being loaded)
        sessionManager = new WebGPUSessionManager({
            ort: ort,
            gpu: navigator.gpu || undefined
        });

        // Step 7: Audio Backend
        updateStatus('オーディオバックエンドを初期化しています...');
        await benchmark.measureAsync('Audio Backend Init', async () => {
            audioBackend = await AudioBackendFactory.create({
                workletUrl: '../src/audio-worklet-processor.js',
                sampleRate: 48000
            });
        });

        // Step 8: Load Model (uses cacheManager + sessionManager)
        updateStatus(`${languageConfigs[currentLanguage].name}モデルを読み込んでいます...`);
        await benchmark.measureAsync('Model Load', async () => {
            await loadModel(currentLanguage);
        });

        // Step 9: Resampler (depends on model config)
        resampler = new SimpleResampler(
            currentModelConfig.audio.sample_rate,
            48000
        );

        // Log init benchmark
        console.log('Initialization benchmark:', benchmark.getSummary());

        const provider = sessionManager.currentProvider || 'wasm';
        const backend = audioBackend.type;
        updateStatus(`準備完了！ (推論: ${provider}, 音声: ${backend})`, 'success');
        synthesizeBtn.disabled = false;

        updateTemplates(currentLanguage);
        setupEventListeners();

    } catch (error) {
        console.error('Initialization failed:', error);
        updateStatus(`初期化エラー: ${error.message}`, 'error');
    }
}
```

---

## 7. Full Revised synthesize() Function

```javascript
async function synthesize() {
    const text = inputText.value.trim();
    if (!text) {
        updateStatus('テキストを入力してください。', 'error');
        return;
    }

    try {
        benchmark.reset();
        updateStatus('音素を抽出中...');
        synthesizeBtn.disabled = true;

        // Phonemization
        const result = await benchmark.measureAsync('Phonemization', async () => {
            return await getPhonemes(text, currentLanguage);
        });
        const phonemes = result.phonemes;
        const labels = result.labels;

        displayPhonemes(phonemes);
        updateStatus('音声合成中...');

        // Phoneme-to-ID conversion
        const phonemeIds = phonemesToIds(phonemes);

        // Prosody extraction
        let prosodyFeatures = null;
        if (labels && currentModelConfig.prosody_id_map) {
            prosodyFeatures = extractProsodyFromLabels(labels, phonemeIds.length);
        }

        // ONNX Inference
        const audio = await benchmark.measureAsync('Inference', async () => {
            return await synthesizeAudio(phonemeIds, prosodyFeatures);
        });

        // Resampling (22kHz -> 48kHz)
        const resampledAudio = await benchmark.measureAsync('Resampling', async () => {
            return resampler.resample(audio);
        });

        // Audio playback via AudioBackend
        await benchmark.measureAsync('Audio Playback', async () => {
            await audioBackend.play(resampledAudio);
        });

        // Also set <audio> element for visual controls / download
        const wavBlob = createWAV(audio, currentModelConfig.audio.sample_rate);
        const audioUrl = URL.createObjectURL(wavBlob);
        audioPlayer.src = audioUrl;

        // Display details with benchmark data
        const benchmarkSummary = benchmark.getSummary();
        detailsOutput.textContent = JSON.stringify({
            text,
            language: currentLanguage,
            executionProvider: sessionManager?.currentProvider || 'wasm',
            audioBackendType: audioBackend?.type || 'unknown',
            phonemes,
            phonemeIds,
            audioLength: audio.length,
            resampledLength: resampledAudio.length,
            duration: (audio.length / currentModelConfig.audio.sample_rate).toFixed(2) + ' seconds',
            sampleRate: currentModelConfig.audio.sample_rate,
            outputSampleRate: 48000,
            benchmark: benchmarkSummary
        }, null, 2);

        outputSection.style.display = 'block';
        updateStatus('合成完了！', 'success');

    } catch (error) {
        console.error('Synthesis failed:', error);
        updateStatus(`合成エラー: ${error.message}`, 'error');
    } finally {
        synthesizeBtn.disabled = false;
    }
}
```

---

## 8. Full Revised switchLanguage() Function

```javascript
async function switchLanguage(lang) {
    currentLanguage = lang;

    document.querySelectorAll('.lang-button').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-lang') === lang);
    });

    const config = languageConfigs[lang];
    inputText.value = config.testText;
    updateTemplates(lang);
    updateLanguageInfo(lang);

    updateStatus(`${config.name}モデルを読み込んでいます...`);
    try {
        await loadModel(lang);

        // Re-create resampler for new model's sample rate
        resampler = new SimpleResampler(
            currentModelConfig.audio.sample_rate,
            48000
        );

        const provider = sessionManager?.currentProvider || 'wasm';
        updateStatus(`準備完了！ (推論: ${provider})`, 'success');
    } catch (error) {
        updateStatus(`モデルロードエラー: ${error.message}`, 'error');
    }
}
```

---

## 9. Functions That Can Be Removed

After integration, the following function is no longer needed for playback (but keep it for the `<audio>` element visual controls):

- **`createWAV()`** (lines 789-824): Retained for populating the `<audio>` element, but no longer the primary playback path.

The following function remains unchanged:

- **`loadScript()`** (lines 779-787): Still needed for loading ORT from CDN.

---

## 10. Browser Compatibility Concerns

### 10.1 WebGPU

| Browser | Desktop | Mobile | Fallback |
|---------|---------|--------|----------|
| Chrome 113+ | Full | Android only | wasm-simd -> wasm |
| Edge 113+ | Full | Android only | wasm-simd -> wasm |
| Firefox | Flag only | No | wasm-simd -> wasm |
| Safari 18+ | Partial (Metal) | Limited (iOS 18+) | wasm-simd -> wasm |

**The `WebGPUSessionManager` handles fallback automatically.** No action required.

### 10.2 AudioWorklet

| Browser | Support | Fallback |
|---------|---------|----------|
| Chrome 66+ | Full | -- |
| Firefox 76+ | Full | -- |
| Safari 14.1+ | Partial | ScriptProcessor |
| iOS Safari | Not supported (2026-Q1) | HTMLAudioBackend |

**The `AudioBackendFactory` handles fallback automatically.** On iOS Safari, the `HTMLAudioBackend` generates a WAV blob internally, which is functionally identical to the current demo behavior.

### 10.3 IndexedDB

| Browser | Support | Notes |
|---------|---------|-------|
| All modern browsers | Full | -- |
| iOS Safari | 50 MB quota per origin | CacheManager eviction handles this |
| Private/Incognito mode | May be limited | Graceful fallback to no-cache |

**If IndexedDB is unavailable**, `cacheManager` is set to `null` and all code paths fall through to direct `fetch()`.

### 10.4 COOP/COEP Headers

The current demo does not require `SharedArrayBuffer`, so COOP/COEP headers are not needed for this integration. These would only become necessary in Phase 5 (SharedArrayBuffer optimization) of the roadmap.

### 10.5 CDN Resource with COEP

If COEP headers are later added, the CDN-loaded ORT script at `cdn.jsdelivr.net` will need `crossorigin` attribute:

```javascript
function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = src;
        script.crossOrigin = 'anonymous';  // Add this for COEP compatibility
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}
```

---

## 11. Summary of Changes

### Files to Modify
- `src/wasm/openjtalk-web/demo/index.html`

### Files Consumed (read-only, no changes needed)
- `src/wasm/openjtalk-web/src/cache-manager.js`
- `src/wasm/openjtalk-web/src/webgpu-session-manager.js`
- `src/wasm/openjtalk-web/src/audio-backend-factory.js`
- `src/wasm/openjtalk-web/src/audio-worklet-processor.js` (loaded by AudioBackendFactory)
- `src/wasm/openjtalk-web/src/resampler.js`
- `src/wasm/openjtalk-web/src/benchmark.js`

### Potential Minor Changes in Source Components

| File | Change | Reason |
|------|--------|--------|
| `webgpu-session-manager.js` | Accept `ArrayBuffer`/`Uint8Array` in `createSession()` (already works via ORT API) | Cache integration returns ArrayBuffer, not URL |
| `cache-manager.js` | None -- `dbFactory` interface is flexible | Real IDB wrapper is added in demo code |

### Changes NOT in Scope (future phases)
- `streaming-pipeline.js` / `TextChunker` / `RingBuffer` / `ChunkCrossfader` -- Phase 3
- `memory-pool.js` / `TypedArrayPool` -- Phase 3
- `dictionary-loader.js` -- already has its own CacheManager integration, but the demo does not use `DictionaryLoader` directly (it uses `SimpleUnifiedPhonemizer`)
- Responsive CSS / mobile optimization -- Phase 4
- SharedArrayBuffer -- Phase 5

---

## 12. Testing Checklist

After integration, verify the following:

- [ ] Japanese text synthesis works with WebGPU provider (Chrome)
- [ ] Japanese text synthesis falls back to WASM on Firefox/Safari
- [ ] English text synthesis works with language switching
- [ ] Model is cached in IndexedDB after first load
- [ ] Second page load uses cached model (verify via DevTools > Application > IndexedDB)
- [ ] AudioWorklet playback works on Chrome/Firefox
- [ ] ScriptProcessor fallback works when AudioWorklet fails
- [ ] HTMLAudio fallback works on iOS Safari
- [ ] Benchmark timings appear in the details output JSON
- [ ] Stop button works with new audio backend
- [ ] `<audio>` element visual controls still show waveform/progress
- [ ] No console errors on any supported browser
- [ ] Memory usage does not grow on repeated synthesis (check for URL.createObjectURL leaks)
