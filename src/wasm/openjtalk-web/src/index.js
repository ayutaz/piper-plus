/**
 * piper-plus — Browser-based multilingual neural TTS
 *
 * High-level API that orchestrates phonemization (OpenJTalk WASM + rule-based),
 * ONNX inference (via onnxruntime-web), and audio output.
 *
 * @module piper-plus
 */

// ---------------------------------------------------------------------------
// Re-exports
// ---------------------------------------------------------------------------

export { SimpleUnifiedPhonemizer } from './simple_unified_api.js';
export { WebGPUSessionManager } from './webgpu-session-manager.js';
export { StreamingTTSPipeline, TextChunker } from './streaming-pipeline.js';
export { AudioBackendFactory } from './audio-backend-factory.js';
export { CacheManager } from './cache-manager.js';
export { ModelManager } from './model-manager.js';
export { DictManager } from './dict-manager.js';
export { AudioResult } from './audio-result.js';

// ---------------------------------------------------------------------------
// Imports used by PiperPlus
// ---------------------------------------------------------------------------

import { SimpleUnifiedPhonemizer } from './simple_unified_api.js';
import { WebGPUSessionManager } from './webgpu-session-manager.js';
import { StreamingTTSPipeline, TextChunker } from './streaming-pipeline.js';
import { ModelManager } from './model-manager.js';
import { DictManager } from './dict-manager.js';
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
    this._phonemizer = null;
    this._ort = null;
    this._initialized = false;
  }

  // -------------------------------------------------------------------------
  // Static factory
  // -------------------------------------------------------------------------

  /**
   * Initialize PiperPlus.  Downloads (and caches) the ONNX model, config,
   * OpenJTalk dictionary, and HTS voice, then creates an ONNX inference
   * session.
   *
   * @param {Object} options
   * @param {string} options.model - HuggingFace model name
   *   (e.g. "ayousanz/piper-plus-tsukuyomi-chan") or direct URL to an ONNX file.
   * @param {Object} [options.ort] - onnxruntime-web instance.  When omitted
   *   the global `globalThis.ort` is used.
   * @param {string} [options.dictUrl] - OpenJTalk dictionary URL.  Defaults to
   *   the DictManager auto-resolution.
   * @param {string} [options.voiceUrl] - HTS voice URL.  Defaults to the
   *   DictManager auto-resolution.
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
   * @param {string} [options.language] - 'ja'|'en'|'zh'|'ko'|'es'|'fr'|'pt'.
   *   Omit for auto-detection.
   * @param {number} [options.noiseScale]
   * @param {number} [options.lengthScale]
   * @param {number} [options.noiseW]
   * @returns {Promise<AudioResult>}
   */
  async synthesize(text, options = {}) {
    this._assertReady();
    if (!text) {
      throw new Error('text is required');
    }

    const language = options.language || this._phonemizer.detectLanguage(text);
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

    const language = options.language || this._phonemizer.detectLanguage(text);
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
    if (this._phonemizer) {
      this._phonemizer.dispose();
      this._phonemizer = null;
    }
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

    // --- 1. Resolve model & config -------------------------------------------

    progress({ stage: 'model', progress: 0, message: 'Resolving model...' });

    const modelManager = new ModelManager();
    const { modelUrl, configUrl } = await modelManager.resolveUrls(options.model);

    progress({ stage: 'model', progress: 0.1, message: 'Downloading config...' });
    const configResponse = await fetch(configUrl);
    if (!configResponse.ok) {
      throw new Error(`Failed to fetch config: ${configResponse.status} ${configResponse.statusText}`);
    }
    this._config = await configResponse.json();

    // --- 2. Download & cache ONNX model, create session ----------------------

    progress({ stage: 'model', progress: 0.3, message: 'Creating ONNX session...' });

    const sessionManager = new WebGPUSessionManager({
      ort,
      gpu: typeof navigator !== 'undefined' ? navigator.gpu : undefined,
    });
    this._session = await sessionManager.createSession(modelUrl);

    progress({ stage: 'model', progress: 0.7, message: 'Model loaded.' });

    // --- 3. Initialise phonemizer (OpenJTalk + dict + voice) -----------------

    progress({ stage: 'phonemizer', progress: 0, message: 'Downloading dictionary...' });

    const dictManager = new DictManager();
    const { dictFiles, voiceData } = await dictManager.loadDictionary({
      dictUrl: options.dictUrl,
      voiceUrl: options.voiceUrl,
      onProgress: ({ phase, overallPercent }) => {
        progress({
          stage: 'phonemizer',
          progress: overallPercent / 100 * 0.8,
          message: phase === 'dict' ? 'Downloading dictionary...' : 'Downloading voice...',
        });
      },
    });

    progress({ stage: 'phonemizer', progress: 0.8, message: 'Initializing phonemizer...' });

    this._phonemizer = new SimpleUnifiedPhonemizer();
    await this._phonemizer.initialize({
      openjtalk: {
        dictData: dictFiles,
        voiceData: voiceData,
      },
    });

    // Provide phoneme_id_map from model config so zh/ko/es/fr/pt fallback works
    if (this._config.phoneme_id_map) {
      this._phonemizer.setPhonemeIdMap(this._config.phoneme_id_map);
    }

    progress({ stage: 'phonemizer', progress: 1, message: 'Phonemizer ready.' });

    // --- Done ----------------------------------------------------------------

    this._initialized = true;
    progress({ stage: 'ready', progress: 1, message: 'PiperPlus ready.' });
  }

  /**
   * Convert text to phoneme IDs (and optional prosody features).
   * @private
   */
  async _textToPhonemeIds(text, language) {
    // For zh/ko/es/fr/pt the phonemizer returns IDs directly
    if (['zh', 'ko', 'es', 'fr', 'pt'].includes(language)) {
      const ids = await this._phonemizer.textToPhonemes(text, language);
      return { phonemeIds: ids, prosodyFeatures: null };
    }

    // ja / en — phonemizer returns labels (ja) or IPA string (en)
    const rawOutput = await this._phonemizer.textToPhonemes(text, language);
    const phonemes = this._phonemizer.extractPhonemes(rawOutput, language);

    const phonemeIds = this._phonemesToIds(phonemes, language);

    // Prosody features are only available for Japanese (from OpenJTalk labels)
    let prosodyFeatures = null;
    if (language === 'ja' && this._config.prosody_id_map) {
      prosodyFeatures = this._extractProsodyFromLabels(rawOutput, phonemeIds.length);
    }

    return { phonemeIds, prosodyFeatures };
  }

  /**
   * Map phoneme tokens to integer IDs using the model's phoneme_id_map.
   * Mirrors the demo/index.html `phonemesToIds` logic.
   * @private
   */
  _phonemesToIds(phonemes, language) {
    const phonemeIdMap = this._config.phoneme_id_map;
    if (!phonemeIdMap) {
      throw new Error('Model config is missing phoneme_id_map');
    }

    const ids = [];
    for (const phoneme of phonemes) {
      if (phonemeIdMap[phoneme]) {
        ids.push(...phonemeIdMap[phoneme]);
      } else {
        // Fallback: silence/space token
        if (language === 'ja') {
          ids.push(...(phonemeIdMap['_'] || [0]));
        } else {
          ids.push(...(phonemeIdMap[' '] || [3]));
        }
      }
    }
    return ids;
  }

  /**
   * Extract A1/A2/A3 prosody features from OpenJTalk full-context labels.
   * Mirrors the demo/index.html `extractProsodyFromLabels` logic.
   * @private
   */
  _extractProsodyFromLabels(labels, phonemeCount) {
    const lines = labels.split('\n').filter(line => line.trim());
    const prosodyPerPhoneme = [];

    const reA1 = /\/A:([\d-]+)\+/;
    const reA2 = /\+([0-9]+)\+/;
    const reA3 = /\+([0-9]+)\//;

    // BOS gets default prosody
    prosodyPerPhoneme.push([0, 0, 0]);

    for (const line of lines) {
      const match = line.match(/-([^+]+)\+/);
      if (match && match[1] !== 'sil' && match[1] !== 'pau') {
        const mA1 = reA1.exec(line);
        const mA2 = reA2.exec(line);
        const mA3 = reA3.exec(line);
        const a1 = mA1 ? Math.max(0, Math.min(10, parseInt(mA1[1]) + 5)) : 0;
        const a2 = mA2 ? Math.min(10, parseInt(mA2[1])) : 0;
        const a3 = mA3 ? Math.min(10, parseInt(mA3[1])) : 0;
        prosodyPerPhoneme.push([a1, a2, a3]);
      }
    }

    // EOS gets default prosody
    prosodyPerPhoneme.push([0, 0, 0]);

    // Pad or trim to match phoneme count
    while (prosodyPerPhoneme.length < phonemeCount) {
      prosodyPerPhoneme.push([0, 0, 0]);
    }
    return prosodyPerPhoneme.slice(0, phonemeCount);
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
      new BigInt64Array(phonemeIds.map(id => BigInt(id))),
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
   * Guard that throws if the instance has not been initialized.
   * @private
   */
  _assertReady() {
    if (!this._initialized) {
      throw new Error('PiperPlus is not initialized. Call PiperPlus.initialize() first.');
    }
  }
}
