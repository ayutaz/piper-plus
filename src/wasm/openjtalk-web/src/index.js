/**
 * piper-plus — Browser-based multilingual neural TTS
 *
 * High-level API that orchestrates phonemization (Rust WASM + rule-based),
 * ONNX inference (via onnxruntime-web), and audio output.
 *
 * @module piper-plus
 */

// ---------------------------------------------------------------------------
// Re-exports
// ---------------------------------------------------------------------------

export { WebGPUSessionManager } from './webgpu-session-manager.js';
export { StreamingTTSPipeline, TextChunker } from './streaming-pipeline.js';
export { AudioBackendFactory } from './audio-backend-factory.js';
export { CacheManager } from './cache-manager.js';
export { ModelManager } from './model-manager.js';
export { AudioResult } from './audio-result.js';
export { SpeakerEncoder } from './speaker-encoder.js';

// Re-export timing utilities from the main package entry so that users can
// bring them in alongside the high-level PiperPlus and AudioResult APIs
// without needing a separate subpath import.
export {
  DEFAULT_HOP_LENGTH,
  buildPhonemeIdToTokenMap,
  durationsToTiming,
  timingToJson,
  timingToJsonCompact,
  timingToSrt,
  timingToTsv,
} from './timing.js';

// ---------------------------------------------------------------------------
// Imports used by PiperPlus
// ---------------------------------------------------------------------------

import { checkPuaCompat } from '@piper-plus/g2p';
import { WebGPUSessionManager } from './webgpu-session-manager.js';
import { StreamingTTSPipeline, TextChunker } from './streaming-pipeline.js';
import { ModelManager } from './model-manager.js';
import { AudioResult } from './audio-result.js';
import {
  DEFAULT_HOP_LENGTH,
  buildPhonemeIdToTokenMap,
  durationsToTiming,
  timingToJson,
  timingToJsonCompact,
  timingToSrt,
  timingToTsv,
} from './timing.js';
import { RustWasmAdapter } from './phonemizer/rust-wasm-adapter.js';
import { JsG2pAdapter } from './phonemizer/js-g2p-adapter.js';
import { CompositePhonemizer } from './phonemizer/composite-phonemizer.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_NOISE_SCALE = 0.667;
const DEFAULT_LENGTH_SCALE = 1.0;
const DEFAULT_NOISE_W = 0.8;
const DEFAULT_SAMPLE_RATE = 22050;

// Short-text mitigation constants (keep in sync with other runtimes —
// docs/spec/short-text-contract.toml).
//
// Issue #356: MIN_PHONEME_IDS was 40, but tsukuyomi 6lang testing showed
// synthesis is stable down to ~8 IDs. 40 caused Strategy A to fire on
// already-stable inputs and leak padding artifacts. 15 keeps Strategy A
// active for genuinely tiny inputs only. MIN_BODY_FOR_STRATEGY_A = 3
// additionally bypasses Strategy A when the body (= phoneme IDs minus
// BOS/EOS) is too small for padding to outweigh content (e.g. 「あ。」).
export const MIN_PHONEME_IDS = 15;
export const MIN_BODY_FOR_STRATEGY_A = 3;
// Number of EOS frames retained by the durations-based Strategy A trim.
// 0 = drop the entire EOS region (issue #356).
export const TRIM_EOS_MAX_FRAMES = 0;
// Default hop length when config.json does not declare audio.hop_size.
export const DEFAULT_HOP_SIZE = 256;
const TRIM_THRESHOLD_RMS = 0.01;
const TRIM_MIN_SAMPLES = 2205; // 22050 Hz * 0.1 s

// ---------------------------------------------------------------------------
// Short-text mitigation helpers (Strategy A + B)
// ---------------------------------------------------------------------------

/**
 * Strategy A: Pad short phoneme ID sequences with silence tokens.
 *
 * Inserts pause tokens (ID = 0) evenly after BOS and before EOS until the
 * sequence reaches MIN_PHONEME_IDS length.  Also pads prosodyFeatures with
 * zero triplets at matching positions when present.
 *
 * Strategy A is skipped when the body (= phoneme IDs minus BOS / EOS) is
 * shorter than MIN_BODY_FOR_STRATEGY_A — see issue #356.
 *
 * The returned object now also carries `frontPad` / `backPad` (the number
 * of pad tokens inserted on each side) so the durations-based post-trim
 * can locate the padding precisely. Existing callers that only consumed
 * `phonemeIds` / `prosodyFeatures` / `wasPadded` continue to work
 * unchanged (object extension, not breaking).
 *
 * @param {number[]} phonemeIds
 * @param {number[][]|null} prosodyFeatures
 * @returns {{ phonemeIds: number[], prosodyFeatures: number[][]|null, wasPadded: boolean, frontPad: number, backPad: number }}
 */
export function padPhonemeIds(phonemeIds, prosodyFeatures) {
  const n = phonemeIds.length;
  const bodyLen = n - 2; // exclude BOS / EOS
  if (bodyLen < MIN_BODY_FOR_STRATEGY_A) {
    return { phonemeIds, prosodyFeatures, wasPadded: false, frontPad: 0, backPad: 0 };
  }
  if (n >= MIN_PHONEME_IDS) {
    return { phonemeIds, prosodyFeatures, wasPadded: false, frontPad: 0, backPad: 0 };
  }

  const padTotal = MIN_PHONEME_IDS - n;
  const padFront = Math.floor(padTotal / 2);
  const padBack = padTotal - padFront;

  // phonemeIds layout: [BOS, ...body..., EOS]
  const bos = phonemeIds.slice(0, 1);
  const body = phonemeIds.slice(1, -1);
  const eos = phonemeIds.slice(-1);

  const padded = [
    ...bos,
    ...new Array(padFront).fill(0),
    ...body,
    ...new Array(padBack).fill(0),
    ...eos,
  ];

  let paddedProsody = null;
  if (prosodyFeatures != null) {
    const pBos = prosodyFeatures.slice(0, 1);
    const pBody = prosodyFeatures.slice(1, -1);
    const pEos = prosodyFeatures.slice(-1);
    paddedProsody = [
      ...pBos,
      ...new Array(padFront).fill(null).map(() => [0, 0, 0]),
      ...pBody,
      ...new Array(padBack).fill(null).map(() => [0, 0, 0]),
      ...pEos,
    ];
  }

  return {
    phonemeIds: padded,
    prosodyFeatures: paddedProsody,
    wasPadded: true,
    frontPad: padFront,
    backPad: padBack,
  };
}

/**
 * Strategy A precise post-trim using the model's duration output.
 * Mirrors the Python reference (src/python_run/piper/voice.py
 * `_trim_padding_by_durations`) so all runtimes produce byte-equal output
 * for the same inputs (issue #356).
 *
 * Padded layout: `[BOS, pad×frontPad, ...body..., pad×backPad, EOS]`.
 *
 * Trimming policy:
 *   - BOS + front padding: stripped completely
 *   - Back padding: stripped completely
 *   - EOS: keep only `eosMaxFrames` frames (default 0 — drop the entire EOS)
 *
 * All frame→sample conversions use `Math.trunc()` (truncation toward zero),
 * matching `int()` in Python and `as i64` in Rust. `Math.round()` is *not*
 * used because it would diverge from the other runtimes.
 *
 * @param {Float32Array} audio  Audio samples in the range -1.0 to 1.0
 * @param {number[]|Float32Array|null} durations  Per-phoneme frame counts
 * @param {number} frontPad
 * @param {number} backPad
 * @param {number} hopSize  VITS hop length (samples per frame)
 * @param {number} [eosMaxFrames=TRIM_EOS_MAX_FRAMES]
 * @returns {Float32Array} Trimmed audio (or the original if inputs are inconsistent)
 */
export function trimPaddingByDurations(
  audio,
  durations,
  frontPad,
  backPad,
  hopSize,
  eosMaxFrames = TRIM_EOS_MAX_FRAMES,
) {
  if (frontPad <= 0 && backPad <= 0) return audio;
  if (durations == null || hopSize <= 0) return audio;
  const expectedLen = 1 + frontPad + backPad + 1; // BOS + pads + EOS
  if (durations.length < expectedLen) return audio;

  // Front: BOS + front padding samples (truncated).
  let frontSum = 0;
  for (let i = 0; i < 1 + frontPad; i++) {
    frontSum += durations[i];
  }
  const frontSamples = Math.trunc(frontSum * hopSize);

  // Back: back padding samples + EOS excess (over eosMaxFrames).
  let backPadSum = 0;
  if (backPad > 0) {
    // Equivalent to durations[-(1+backPad) : -1] in Python.
    const start = durations.length - 1 - backPad;
    for (let i = start; i < durations.length - 1; i++) {
      backPadSum += durations[i];
    }
  }
  const backPadSamples = Math.trunc(backPadSum * hopSize);
  const eosFrames = durations[durations.length - 1];
  const eosExcess = Math.max(0, eosFrames - eosMaxFrames);
  const backSamples = backPadSamples + Math.trunc(eosExcess * hopSize);

  const total = audio.length;
  const start = Math.max(0, frontSamples);
  let end = total - backSamples;
  if (end < start) end = start;
  if (start >= total || end <= 0 || start >= end) return audio;

  // subarray() avoids a copy; subscribers that mutate must already clone.
  return audio.subarray(start, end);
}

/**
 * Strategy A (post-step): Trim leading and trailing silence from Float32Array
 * audio using a sliding RMS window.
 *
 * Keeps at least TRIM_MIN_SAMPLES to avoid producing empty audio.
 *
 * @param {Float32Array} audio - Audio samples in the range -1.0 to 1.0
 * @param {number} [windowSize=256] - RMS window size in samples
 * @returns {Float32Array}
 */
export function trimSilence(audio, windowSize = 256) {
  const n = audio.length;
  if (n <= TRIM_MIN_SAMPLES) {
    return audio;
  }

  const nWindows = Math.floor(n / windowSize);
  if (nWindows === 0) {
    return audio;
  }

  // Compute per-window RMS
  let firstAbove = -1;
  let lastAbove = -1;
  for (let w = 0; w < nWindows; w++) {
    const offset = w * windowSize;
    let sumSq = 0;
    for (let j = 0; j < windowSize; j++) {
      const s = audio[offset + j];
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / windowSize);
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) firstAbove = w;
      lastAbove = w;
    }
  }

  // Check partial window (remainder samples after the last full window)
  const remainder = n % windowSize;
  if (remainder > 0) {
    const offset = nWindows * windowSize;
    let sumSq = 0;
    for (let j = 0; j < remainder; j++) {
      const s = audio[offset + j];
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / remainder);
    if (rms > TRIM_THRESHOLD_RMS) {
      if (firstAbove < 0) firstAbove = nWindows; // virtual window index for the partial
      lastAbove = nWindows;
    }
  }

  if (firstAbove < 0) {
    // All silence — return minimum-length slice from the start
    return audio.slice(0, TRIM_MIN_SAMPLES);
  }

  let startSample = firstAbove * windowSize;
  let endSample = Math.min((lastAbove + 1) * windowSize, n);

  // Ensure minimum length
  let length = endSample - startSample;
  if (length < TRIM_MIN_SAMPLES) {
    const center = Math.floor((startSample + endSample) / 2);
    const half = Math.floor(TRIM_MIN_SAMPLES / 2);
    startSample = Math.max(0, center - half);
    endSample = Math.min(n, startSample + TRIM_MIN_SAMPLES);
    startSample = Math.max(0, endSample - TRIM_MIN_SAMPLES);
  }

  return audio.slice(startSample, endSample);
}

/**
 * Strategy B: Adjust noise scales for short inputs.
 *
 * For inputs shorter than MIN_PHONEME_IDS, attenuate noiseScale and noiseW
 * proportionally while keeping lengthScale unchanged.
 *
 * @param {number} phonemeCount - Number of phoneme IDs
 * @param {number} noiseScale
 * @param {number} noiseW
 * @returns {{ noiseScale: number, noiseW: number }}
 */
export function adjustScalesForShortInput(phonemeCount, noiseScale, noiseW) {
  if (phonemeCount >= MIN_PHONEME_IDS) {
    return { noiseScale, noiseW };
  }

  const ratio = Math.min(1.0, phonemeCount / MIN_PHONEME_IDS);
  return {
    noiseScale: noiseScale * Math.max(0.5, ratio),
    noiseW: noiseW * Math.max(0.4, ratio),
  };
}

// ---------------------------------------------------------------------------
// PiperPlus
// ---------------------------------------------------------------------------

export class PiperPlus {
  /** @private — use PiperPlus.initialize() */
  constructor() {
    this._session = null;
    this._config = null;
    this._phonemizer = null;
    this._ort = null;
    this._initialized = false;
    this._warmupPromise = null;
  }

  // -------------------------------------------------------------------------
  // Static factory
  // -------------------------------------------------------------------------

  /**
   * Initialize PiperPlus.  Downloads (and caches) the ONNX model and config,
   * then creates an ONNX inference session and initialises the Rust WASM
   * phonemizer.
   *
   * @param {Object} options
   * @param {string} options.model - HuggingFace model name
   *   (e.g. "ayousanz/piper-plus-css10-ja-6lang") or direct URL to an ONNX file.
   * @param {Object} [options.ort] - onnxruntime-web instance.  When omitted
   *   the global `globalThis.ort` is used.
   * @param {Function} [options.onProgress] - Progress callback receiving
   *   `{ stage: string, progress: number, message: string }`.
   * @param {string} [options.wasmG2pUrl] - Custom URL for Rust WASM G2P module.
   *   Defaults to `../dist/rust-wasm/piper_plus_wasm.js`.
   * @param {Function} [options.wasmLoader] - DI: async function returning WASM
   *   module for testing. Takes precedence over wasmG2pUrl.
   * @returns {Promise<PiperPlus>}
   */
  static async initialize(options = {}) {
    const instance = new PiperPlus();
    await instance._init(options);
    return instance;
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /**
   * Synthesize speech from text.
   *
   * @param {string} text
   * @param {Object} [options]
   * @param {string} [options.language] - 'ja'|'en'|'zh'|'ko'|'es'|'fr'|'pt'|'sv'.
   *   Omit for auto-detection.
   * @param {number} [options.noiseScale]
   * @param {number} [options.lengthScale]
   * @param {number} [options.noiseW]
   * @returns {Promise<AudioResult>}
   */
  async synthesize(text, options = {}) {
    this._assertReady();
    if (this._warmupPromise) {
      await this._warmupPromise;
      this._warmupPromise = null;
    }
    if (!text) {
      throw new Error('text is required');
    }

    const language = options.language || this._detectLanguage(text);
    let noiseScale = options.noiseScale ?? this._config.inference?.noise_scale ?? DEFAULT_NOISE_SCALE;
    const lengthScale = options.lengthScale ?? this._config.inference?.length_scale ?? DEFAULT_LENGTH_SCALE;
    let noiseW = options.noiseW ?? this._config.inference?.noise_w ?? DEFAULT_NOISE_W;

    // 1. Phonemize
    let { phonemeIds, prosodyFeatures } = await this._textToPhonemeIds(text, language);

    // --- Strategy B: Dynamic Scales Adjustment for short inputs ---
    const originalLength = phonemeIds.length;
    const adjusted = adjustScalesForShortInput(originalLength, noiseScale, noiseW);
    noiseScale = adjusted.noiseScale;
    noiseW = adjusted.noiseW;

    // --- Strategy A: Silence Padding for short inputs ---
    // Save original (pre-padding) phoneme IDs for timing calculation.
    const originalPhonemeIds = phonemeIds;
    const padResult = padPhonemeIds(phonemeIds, prosodyFeatures);
    phonemeIds = padResult.phonemeIds;
    prosodyFeatures = padResult.prosodyFeatures;
    const wasPadded = padResult.wasPadded;
    const frontPad = padResult.frontPad;
    const backPad = padResult.backPad;

    // 2. ONNX inference
    const inferResult = await this._infer(phonemeIds, prosodyFeatures, {
      noiseScale,
      lengthScale,
      noiseW,
      language,
    });
    let audioData = inferResult.audio;
    const durations = inferResult.durations;

    // --- Strategy A (post-step): Trim padding-induced audio ---
    // Prefer the durations-based precise trim (issue #356); fall back to
    // the legacy RMS trim only when durations are unavailable.
    if (wasPadded) {
      if (durations != null) {
        const hopSize = this._config.audio?.hop_size ?? DEFAULT_HOP_SIZE;
        audioData = trimPaddingByDurations(
          audioData,
          durations,
          frontPad,
          backPad,
          hopSize > 0 ? hopSize : DEFAULT_HOP_SIZE,
        );
      } else {
        audioData = trimSilence(audioData);
      }
    }

    // 3. Wrap result — include phoneme timing when the model supports it
    const sampleRate = this._config.audio?.sample_rate ?? DEFAULT_SAMPLE_RATE;
    const timing = this._createTiming(durations, originalPhonemeIds);
    return new AudioResult(audioData, sampleRate, timing);
  }

  /**
   * Synthesize speech with voice cloning from a reference audio.
   *
   * Requires a SpeakerEncoder to have been initialized separately.
   * The reference audio is encoded into a speaker embedding, which
   * is then passed to the ONNX model during inference.
   *
   * @param {string} text - Text to synthesize.
   * @param {Float32Array} speakerEmbedding - Speaker embedding from SpeakerEncoder.encode().
   * @param {Object} [options] - Same options as synthesize().
   * @returns {Promise<AudioResult>}
   */
  async synthesizeWithVoiceCloning(text, speakerEmbedding, options = {}) {
    this._assertReady();
    if (this._warmupPromise) {
      await this._warmupPromise;
      this._warmupPromise = null;
    }
    if (!text) {
      throw new Error('text is required');
    }
    if (!speakerEmbedding || !(speakerEmbedding instanceof Float32Array)) {
      throw new Error('speakerEmbedding must be a Float32Array');
    }

    const language = options.language || this._detectLanguage(text);
    const noiseScale = options.noiseScale ?? this._config.inference?.noise_scale ?? DEFAULT_NOISE_SCALE;
    const lengthScale = options.lengthScale ?? this._config.inference?.length_scale ?? DEFAULT_LENGTH_SCALE;
    const noiseW = options.noiseW ?? this._config.inference?.noise_w ?? DEFAULT_NOISE_W;

    // 1. Phonemize
    const { phonemeIds, prosodyFeatures } = await this._textToPhonemeIds(text, language);

    // 2. ONNX inference with speaker embedding
    const inferResult = await this._infer(phonemeIds, prosodyFeatures, {
      noiseScale,
      lengthScale,
      noiseW,
      language,
      speakerEmbedding,
    });
    const audioData = inferResult.audio;
    const durations = inferResult.durations;

    // 3. Wrap result — include phoneme timing when the model supports it
    const sampleRate = this._config.audio?.sample_rate ?? DEFAULT_SAMPLE_RATE;
    const timing = this._createTiming(durations, phonemeIds);
    return new AudioResult(audioData, sampleRate, timing);
  }

  /**
   * Streaming synthesis — splits text into sentences and invokes
   * `options.onChunk` for each generated audio chunk.
   *
   * @param {string} text
   * @param {Object} [options]
   * @param {string} [options.language]
   * @param {Function} [options.onChunk] - Called with a Float32Array per chunk.
   * @returns {Promise<void>}
   */
  async synthesizeStreaming(text, options = {}) {
    this._assertReady();
    if (!text) {
      throw new Error('text is required');
    }

    const language = options.language || this._detectLanguage(text);
    const noiseScale = options.noiseScale ?? this._config.inference?.noise_scale ?? DEFAULT_NOISE_SCALE;
    const lengthScale = options.lengthScale ?? this._config.inference?.length_scale ?? DEFAULT_LENGTH_SCALE;
    const noiseW = options.noiseW ?? this._config.inference?.noise_w ?? DEFAULT_NOISE_W;
    const onChunk = options.onChunk || (() => {});

    const pipeline = new StreamingTTSPipeline({
      phonemize: async (chunk) => {
        const { phonemeIds } = await this._textToPhonemeIds(chunk, language);
        return phonemeIds;
      },
      synthesize: async (ids) => {
        // Streaming path skips prosody for simplicity — prosody extraction
        // requires the full labels which are language-specific.
        // The streaming pipeline expects a Float32Array, so unwrap .audio
        // from the { audio, durations } object returned by _infer().
        const inferResult = await this._infer(ids, null, { noiseScale, lengthScale, noiseW, language });
        return inferResult.audio;
      },
      onAudioChunk: onChunk,
    });

    await pipeline.synthesizeAndPlay(text, language);
  }

  /**
   * Release all held resources (ONNX session, phonemizer, etc.).
   */
  dispose() {
    if (this._session) {
      if (typeof this._session.release === 'function') {
        this._session.release();
      }
      this._session = null;
    }
    if (this._phonemizer) {
      this._phonemizer.dispose();
      this._phonemizer = null;
    }
    this._sessionManager = null;
    this._modelUrl = null;
    this._warmupPromise = null;
    this._initialized = false;
  }

  /** @returns {boolean} */
  get isInitialized() {
    return this._initialized;
  }

  /** @returns {Object|null} Model configuration (config.json contents). */
  get config() {
    return this._config;
  }

  // -------------------------------------------------------------------------
  // Internals
  // -------------------------------------------------------------------------

  /**
   * Core initialisation sequence.
   * @private
   */
  async _init(options) {
    const ort = options.ort || globalThis.ort;
    if (!ort) {
      throw new Error(
        'onnxruntime-web is required. Pass it via options.ort or load it globally.'
      );
    }
    this._ort = ort;

    const progress = options.onProgress || (() => {});

    try {
      // --- 1. Resolve model & config -----------------------------------------

      progress({ stage: 'model', progress: 0, message: 'Resolving model...' });

      const modelManager = new ModelManager();
      const { modelUrl, configUrl, configFallbackUrl } = await modelManager.resolveUrls(options.model);

      progress({ stage: 'model', progress: 0.1, message: 'Downloading config...' });
      let configResponse = await fetch(configUrl);
      if (!configResponse.ok && configResponse.status === 404 && configFallbackUrl) {
        configResponse = await fetch(configFallbackUrl);
      }
      if (!configResponse.ok) {
        throw new Error(`Failed to fetch config: ${configResponse.status} ${configResponse.statusText}`);
      }
      this._config = await configResponse.json();

      // --- PUA compatibility check ------------------------------------------
      const puaCheck = checkPuaCompat(this._config.pua_compat_version);
      if (!puaCheck.compatible) {
        console.warn(`[piper-plus] ${puaCheck.message}`);
      }

      // --- 2. Download & cache ONNX model, create session --------------------

      progress({ stage: 'model', progress: 0.3, message: 'Creating ONNX session...' });

      // VITS models use int64 tensors (input, input_lengths, lid, prosody_features)
      // which WebGPU (WGSL) does not support. Always use WASM CPU backend.
      this._sessionManager = new WebGPUSessionManager({
        ort,
        gpu: undefined,
      });
      this._modelUrl = modelUrl;
      this._session = await this._sessionManager.createSession(modelUrl);

      progress({ stage: 'model', progress: 0.7, message: 'Model loaded.' });

      // --- 3. Initialise phonemizer (Adapter pattern) --------------------------

      progress({ stage: 'phonemizer', progress: 0, message: 'Initializing phonemizer...' });

      let languages = this._config.language_id_map
        ? Object.keys(this._config.language_id_map)
        : undefined;

      const phonemizerMap = new Map();
      let wasmAdapter = null;

      // Languages that REQUIRE Rust WASM (no functional JS G2P fallback):
      //   ja — needs jpreprocess (no JS equivalent)
      //   zh — needs pinyin dictionary (JS G2P has no pinyin conversion)
      const WASM_REQUIRED_LANGUAGES = new Set(['ja', 'zh']);

      // Load Rust WASM phonemizer when any model language benefits from it.
      // When loaded, route ALL languages through WASM — the Rust
      // MultilingualPhonemizer now respects language hints for Latin-script
      // languages (es/fr/pt/sv), so they are phonemized correctly.
      const needsWasm = languages && languages.some(l => WASM_REQUIRED_LANGUAGES.has(l));
      if (needsWasm) {
        try {
          wasmAdapter = await RustWasmAdapter.create(
            JSON.stringify(this._config),
            {
              wasmUrl: options.wasmG2pUrl || '../../dist/rust-wasm/piper_plus_wasm.js',
              wasmLoader: options.wasmLoader,
            },
          );
          // Route all languages through WASM
          const wasmLangs = wasmAdapter.supportedLanguages;
          for (const lang of languages) {
            if (wasmLangs.includes(lang)) {
              phonemizerMap.set(lang, wasmAdapter);
            }
          }
        } catch (err) {
          const excluded = languages.filter(l => WASM_REQUIRED_LANGUAGES.has(l));
          console.warn(
            `[piper-plus] Rust WASM G2P failed to load, excluding ${excluded.join(', ')}:`,
            err.message,
          );
          languages = languages.filter(l => !WASM_REQUIRED_LANGUAGES.has(l));
        }
      }

      // Languages not covered by WASM use JS G2P as fallback.
      // When languages is undefined (no language_id_map), pass undefined to
      // JsG2pAdapter so G2P.create() initialises all available languages.
      const jsLanguages = languages?.filter(l => !phonemizerMap.has(l));
      const needsJsAdapter = !jsLanguages || jsLanguages.length > 0;
      let jsAdapter = null;
      if (needsJsAdapter) {
        jsAdapter = await JsG2pAdapter.create(
          jsLanguages,  // undefined when no language_id_map
          this._config.phoneme_id_map,
        );
        if (jsLanguages) {
          for (const lang of jsLanguages) {
            phonemizerMap.set(lang, jsAdapter);
          }
        }
      }

      this._phonemizer = new CompositePhonemizer({
        phonemizers: phonemizerMap,
        fallback: jsAdapter || wasmAdapter,
        detector: wasmAdapter || jsAdapter,
      });

      progress({ stage: 'phonemizer', progress: 1, message: 'Phonemizer ready.' });

      // --- Done --------------------------------------------------------------

      this._initialized = true;
      progress({ stage: 'ready', progress: 1, message: 'PiperPlus ready.' });
    } catch (error) {
      // Clean up any partially-initialized resources so the instance
      // does not leak sessions, WASM memory, etc.
      this.dispose();
      throw error;
    }
  }

  /**
   * Detect language of text via the composite phonemizer.
   * @private
   */
  _detectLanguage(text) {
    return this._phonemizer.detectLanguage(text);
  }

  /**
   * Convert text to phoneme IDs (and optional prosody features).
   * Delegates to the appropriate adapter via CompositePhonemizer.
   * @private
   */
  async _textToPhonemeIds(text, language) {
    return this._phonemizer.encode(text, language);
  }

  /**
   * Build a cached phoneme-ID → token reverse map from the current config.
   * The map is lazily built once per model load.
   * @private
   */
  _getPhonemeIdToTokenMap() {
    if (this._phonemeIdToTokenMap === undefined) {
      this._phonemeIdToTokenMap = buildPhonemeIdToTokenMap(
        this._config?.phoneme_id_map ?? null
      );
    }
    return this._phonemeIdToTokenMap;
  }

  /**
   * Convert ONNX `durations` output to a TimingResult using the model's
   * phoneme ID map for human-readable phoneme tokens.
   *
   * @param {Float32Array} durations - Raw duration frames from ONNX
   * @param {number[]} phonemeIds - Phoneme IDs corresponding to each duration
   *   (may be longer than durations if padding was applied; truncated to min)
   * @returns {object} TimingResult
   * @private
   */
  _createTiming(durations, phonemeIds) {
    if (!durations) return null;

    const sampleRate = this._config?.audio?.sample_rate ?? DEFAULT_SAMPLE_RATE;
    const idToToken = this._getPhonemeIdToTokenMap();

    // Build phoneme tokens from the original (pre-padding) IDs.
    // Durations length may differ from phonemeIds length if the model
    // applies internal padding; align to the minimum of the two.
    const minLen = Math.min(durations.length, phonemeIds.length);
    const tokens = new Array(minLen);
    for (let i = 0; i < minLen; i++) {
      tokens[i] = idToToken[phonemeIds[i]] ?? `ph_${i}`;
    }

    // Create a truncated durations view if needed.
    const alignedDurations =
      minLen === durations.length
        ? durations
        : durations.subarray
        ? durations.subarray(0, minLen)
        : Array.from(durations).slice(0, minLen);

    return durationsToTiming(
      alignedDurations,
      sampleRate,
      DEFAULT_HOP_LENGTH,
      tokens,
    );
  }

  /**
   * Run ONNX inference.  Builds tensors matching the VITS model inputs:
   *   - input        (int64)   [1, seq_len]
   *   - input_lengths (int64)  [1]
   *   - scales       (float32) [3]
   *   - prosody_features (int64, optional) [1, seq_len, 3]
   *
   * Returns raw Float32Array of audio samples.
   * @private
   */
  async _infer(phonemeIds, prosodyFeatures, { noiseScale, lengthScale, noiseW, language, speakerEmbedding }) {
    const ort = this._ort;

    const inputTensor = new ort.Tensor(
      'int64',
      new BigInt64Array(Array.from(phonemeIds, id => BigInt(id))),
      [1, phonemeIds.length]
    );

    const lengthTensor = new ort.Tensor(
      'int64',
      new BigInt64Array([BigInt(phonemeIds.length)]),
      [1]
    );

    const scalesTensor = new ort.Tensor(
      'float32',
      new Float32Array([noiseScale, lengthScale, noiseW]),
      [3]
    );

    const feeds = {
      input: inputTensor,
      input_lengths: lengthTensor,
      scales: scalesTensor,
    };

    // Attach language ID tensor for multilingual models
    if (this._config.language_id_map && language) {
      const langId = this._config.language_id_map[language];
      if (langId !== undefined) {
        feeds.lid = new ort.Tensor(
          'int64',
          new BigInt64Array([BigInt(langId)]),
          [1]
        );
      }
    }

    // Attach speaker embedding for voice cloning
    if (speakerEmbedding && speakerEmbedding.length > 0) {
      feeds.speaker_embedding = new ort.Tensor(
        'float32',
        speakerEmbedding,
        [1, speakerEmbedding.length]
      );
      feeds.speaker_embedding_mask = new ort.Tensor(
        'int64',
        new BigInt64Array([1n]),
        [1]
      );
    }

    // Attach prosody features when the model supports them
    if (prosodyFeatures && this._config.prosody_id_map) {
      const flat = [];
      for (const [a1, a2, a3] of prosodyFeatures) {
        flat.push(BigInt(a1), BigInt(a2), BigInt(a3));
      }
      feeds.prosody_features = new ort.Tensor(
        'int64',
        new BigInt64Array(flat),
        [1, phonemeIds.length, 3]
      );
    }

    let results;
    try {
      results = await this._session.run(feeds);
    } catch (e) {
      // Detect WebGPU int64 kernel failure and fall back to WASM
      if (this._sessionManager?.currentProvider === 'webgpu'
          && e?.message?.includes('Unsupported data type')) {
        console.warn(
          '[piper-plus] WebGPU inference failed (likely int64 unsupported). '
          + 'Recreating session with WASM backend.',
          e.message
        );
        if (typeof this._session.release === 'function') {
          await this._session.release();
        }
        // Force WASM by removing GPU reference
        this._sessionManager._gpu = undefined;
        this._session = await this._sessionManager.createSession(this._modelUrl);
        results = await this._session.run(feeds);
      } else {
        throw e;
      }
    }
    const audioTensor = results.output || results[Object.keys(results)[0]];
    const audio = new Float32Array(audioTensor.data);

    // Extract durations tensor if the model supports it (optional output)
    let durations = null;
    if (results.durations && results.durations.data) {
      durations = new Float32Array(results.durations.data);
    }

    return { audio, durations };
  }

  /**
   * ORT グラフ最適化キャッシュをバックグラウンドで温める。
   * 本番と同程度の形状 (長さ100) でダミー推論を実行する。
   * @private
   */
  async _runWarmup(runs = 2) {
    const WARMUP_LENGTH = 100;
    const dummyIds = new Array(WARMUP_LENGTH);
    dummyIds[0] = 1; // BOS
    for (let i = 1; i < WARMUP_LENGTH - 1; i++) dummyIds[i] = 8;
    dummyIds[WARMUP_LENGTH - 1] = 2; // EOS

    for (let i = 0; i < runs; i++) {
      try {
        await this._infer(dummyIds, null, {
          noiseScale: DEFAULT_NOISE_SCALE,
          lengthScale: DEFAULT_LENGTH_SCALE,
          noiseW: DEFAULT_NOISE_W,
        });
      } catch (e) {
        console.warn(`[piper-plus] warmup run ${i + 1}/${runs} failed:`, e);
        return;
      }
    }
  }

  /**
   * Guard that throws if the instance has not been initialized.
   * @private
   */
  _assertReady() {
    if (!this._initialized) {
      throw new Error('PiperPlus is not initialized. Call PiperPlus.initialize() first.');
    }
  }
}
