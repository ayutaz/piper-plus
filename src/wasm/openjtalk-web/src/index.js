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

// ---------------------------------------------------------------------------
// Imports used by PiperPlus
// ---------------------------------------------------------------------------

import { G2P, checkPuaCompat } from '@piper-plus/g2p';
import { WebGPUSessionManager } from './webgpu-session-manager.js';
import { StreamingTTSPipeline, TextChunker } from './streaming-pipeline.js';
import { ModelManager } from './model-manager.js';
import { AudioResult } from './audio-result.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_NOISE_SCALE = 0.667;
const DEFAULT_LENGTH_SCALE = 1.0;
const DEFAULT_NOISE_W = 0.8;
const DEFAULT_SAMPLE_RATE = 22050;

// ---------------------------------------------------------------------------
// PiperPlus
// ---------------------------------------------------------------------------

export class PiperPlus {
  /** @private — use PiperPlus.initialize() */
  constructor() {
    this._session = null;
    this._config = null;
    this._g2p = null;
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
   *   (e.g. "ayousanz/piper-plus-tsukuyomi-chan") or direct URL to an ONNX file.
   * @param {Object} [options.ort] - onnxruntime-web instance.  When omitted
   *   the global `globalThis.ort` is used.
   * @param {Function} [options.onProgress] - Progress callback receiving
   *   `{ stage: string, progress: number, message: string }`.
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

    const language = options.language || this._g2p.detectLanguage(text);
    const noiseScale = options.noiseScale ?? this._config.inference?.noise_scale ?? DEFAULT_NOISE_SCALE;
    const lengthScale = options.lengthScale ?? this._config.inference?.length_scale ?? DEFAULT_LENGTH_SCALE;
    const noiseW = options.noiseW ?? this._config.inference?.noise_w ?? DEFAULT_NOISE_W;

    // 1. Phonemize
    const { phonemeIds, prosodyFeatures } = await this._textToPhonemeIds(text, language);

    // 2. ONNX inference
    const audioData = await this._infer(phonemeIds, prosodyFeatures, {
      noiseScale,
      lengthScale,
      noiseW,
    });

    // 3. Wrap result
    const sampleRate = this._config.audio?.sample_rate ?? DEFAULT_SAMPLE_RATE;
    return new AudioResult(audioData, sampleRate);
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

    const language = options.language || this._g2p.detectLanguage(text);
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
        return this._infer(ids, null, { noiseScale, lengthScale, noiseW });
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
      // onnxruntime-web sessions expose release()
      if (typeof this._session.release === 'function') {
        this._session.release();
      }
      this._session = null;
    }
    if (this._g2p) {
      this._g2p.dispose();
      this._g2p = null;
    }
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

      const sessionManager = new WebGPUSessionManager({
        ort,
        gpu: typeof navigator !== 'undefined' ? navigator.gpu : undefined,
      });
      this._session = await sessionManager.createSession(modelUrl);

      progress({ stage: 'model', progress: 0.7, message: 'Model loaded.' });

      // --- 3. Initialise phonemizer (@piper-plus/g2p) --------------------------

      progress({ stage: 'phonemizer', progress: 0, message: 'Initializing phonemizer...' });

      let languages = this._config.language_id_map
        ? Object.keys(this._config.language_id_map)
        : undefined;

      // Japanese G2P requires an OpenJTalk WASM module injected via options.
      // When not provided, exclude 'ja' so the remaining languages still work.
      const g2pOptions = {};
      if (options.openjtalkModule) {
        g2pOptions.openjtalkModule = options.openjtalkModule;
        if (options.jaDict) g2pOptions.jaDict = options.jaDict;
      } else if (languages && languages.includes('ja')) {
        languages = languages.filter((l) => l !== 'ja');
      }
      g2pOptions.languages = languages;

      this._g2p = await G2P.create(g2pOptions);

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
   * Convert text to phoneme IDs (and optional prosody features).
   * @private
   */
  async _textToPhonemeIds(text, language) {
    const phonemeIdMap = this._config.phoneme_id_map;
    if (!phonemeIdMap) {
      throw new Error('Model config is missing phoneme_id_map');
    }
    const result = this._g2p.encode(text, phonemeIdMap, { language });

    // Convert flat prosodyFlat [a1,a2,a3,...] to nested [[a1,a2,a3],...] for #infer()
    let prosodyFeatures = null;
    if (result.prosodyFlat && result.prosodyFlat.length > 0) {
      const flat = result.prosodyFlat;
      prosodyFeatures = [];
      for (let i = 0; i < flat.length; i += 3) {
        prosodyFeatures.push([flat[i], flat[i + 1], flat[i + 2]]);
      }
    }

    return { phonemeIds: result.phonemeIds, prosodyFeatures };
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
  async _infer(phonemeIds, prosodyFeatures, { noiseScale, lengthScale, noiseW }) {
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

    const results = await this._session.run(feeds);
    const audioTensor = results.output || results[Object.keys(results)[0]];
    return new Float32Array(audioTensor.data);
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
