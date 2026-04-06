/**
 * PiperPlus Rust WASM G2P integration tests (M2-1 + M2-2)
 *
 * Tests the Rust WASM phonemizer integration in PiperPlus:
 * - _init() WASM loader (M1-1)
 * - _textToPhonemeIds() Japanese branch (M1-2)
 * - _detectLanguage() with WASM (M1-3)
 * - dispose() WASM cleanup (M1-4)
 *
 * Uses mocked WASM module to test without real WASM binary.
 *
 * Run: node --test test/js/test-piper-plus-wasm-g2p.js
 */

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Save originals
// ---------------------------------------------------------------------------

const _origFetch = globalThis.fetch;
const _origOrt = globalThis.ort;
const _origIndexedDB = globalThis.indexedDB;

// ---------------------------------------------------------------------------
// Mock WASM module — simulates Rust WASM WasmPhonemizer
// ---------------------------------------------------------------------------

function createMockWasmPhonemizer(config) {
  let freed = false;
  return {
    phonemize(text, lang) {
      if (freed) throw new Error('WasmPhonemizer already freed');
      // Return realistic phoneme IDs (BOS=1, PAD=0, EOS=2) with prosody
      return {
        phonemeIds: new Int32Array([1, 0, 8, 15, 22, 0, 2]),
        prosodyFeatures: new Int32Array([
          -2, 1, 5,   // mora 1
          -1, 2, 5,   // mora 2
          0, 3, 5,    // mora 3
        ]),
        phonemeCount: 7,
        free() { /* individual result free */ },
      };
    },
    detectLanguage(text) {
      // Simple heuristic matching Rust WASM behaviour
      if (/[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]/.test(text)) return 'ja';
      if (/[\u4E00-\u9FFF]/.test(text) && !/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return 'zh';
      return 'en';
    },
    getSupportedLanguages() {
      return ['ja', 'en', 'zh', 'ko', 'es', 'fr', 'pt', 'sv'];
    },
    free() {
      freed = true;
    },
    get _freed() { return freed; },
  };
}

/** Creates a mock WASM module that mimics the dynamic import result */
function createMockWasmModule(config) {
  let phonemizer = null;
  return {
    // default export = init() function
    default: async () => { /* WASM binary loaded */ },
    WasmPhonemizer: class {
      constructor(configJson) {
        phonemizer = createMockWasmPhonemizer(JSON.parse(configJson));
        // Copy methods to this
        Object.assign(this, phonemizer);
        this._inner = phonemizer;
      }
    },
    _getLastPhonemizer: () => phonemizer,
  };
}

// ---------------------------------------------------------------------------
// Global mocks
// ---------------------------------------------------------------------------

let mockConfig = {};

function setMockConfig(config) {
  mockConfig = config;
}

function installGlobalMocks() {
  globalThis.fetch = async (url) => {
    if (typeof url === 'string' && url.endsWith('.json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => structuredClone(mockConfig),
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(16),
    };
  };

  globalThis.ort = {
    InferenceSession: {
      create: async () => ({
        inputNames: ['input', 'input_lengths', 'scales'],
        outputNames: ['output'],
        run: async () => ({
          output: { data: new Float32Array(22050), dims: [1, 22050] },
        }),
        release: () => {},
      }),
    },
    Tensor: class {
      constructor(type, data, dims) {
        this.type = type;
        this.data = data;
        this.dims = dims;
      }
    },
  };

  globalThis.indexedDB = {
    open: () => {
      const req = {};
      setTimeout(() => {
        if (req.onupgradeneeded) {
          req.onupgradeneeded({
            target: {
              result: {
                objectStoreNames: { contains: () => false },
                createObjectStore: () => ({}),
              },
            },
          });
        }
        if (req.onsuccess) {
          req.result = {
            transaction: () => ({
              objectStore: () => ({
                get: () => {
                  const r = {};
                  setTimeout(() => { r.result = null; if (r.onsuccess) r.onsuccess(); }, 0);
                  return r;
                },
                put: () => {
                  const r = {};
                  setTimeout(() => { if (r.onsuccess) r.onsuccess(); }, 0);
                  return r;
                },
              }),
            }),
          };
          req.onsuccess();
        }
      }, 0);
      return req;
    },
  };
}

installGlobalMocks();

// ---------------------------------------------------------------------------
// Import modules (after mocks are installed)
// ---------------------------------------------------------------------------

let PiperPlus, ModelManager, G2P;
let importError = null;

try {
  const piperMod = await import('../../src/index.js');
  PiperPlus = piperMod.PiperPlus;
  ModelManager = piperMod.ModelManager;

  const g2pMod = await import('@piper-plus/g2p');
  G2P = g2pMod.G2P;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null || G2P == null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const BASE_CONFIG = {
  audio: { sample_rate: 22050 },
  inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
  phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
  num_speakers: 1,
};

const CONFIG_WITH_JA = {
  ...BASE_CONFIG,
  language_id_map: { ja: 0, en: 1, zh: 2, es: 3, fr: 4, pt: 5 },
};

const CONFIG_WITHOUT_JA = {
  ...BASE_CONFIG,
  language_id_map: { en: 0, zh: 1, es: 2 },
};

const CONFIG_NO_WASM_LANGS = {
  ...BASE_CONFIG,
  language_id_map: { en: 0, es: 1, fr: 2 },
};

let _origResolve;
function installModelManagerStub() {
  _origResolve = ModelManager.prototype.resolveUrls;
  ModelManager.prototype.resolveUrls = function () {
    return {
      modelUrl: 'https://mock/model.onnx',
      configUrl: 'https://mock/model.onnx.json',
    };
  };
}
function removeModelManagerStub() {
  if (_origResolve !== undefined) {
    ModelManager.prototype.resolveUrls = _origResolve;
  } else {
    delete ModelManager.prototype.resolveUrls;
  }
}

function createMockG2PInstance() {
  return {
    detectLanguage: () => 'en',
    encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
    phonemize: () => ({ tokens: ['h', 'e', 'l', 'o'], prosody: [null, null, null, null], language: 'en' }),
    dispose: () => {},
  };
}

let _origG2PCreate;
function stubG2PCreate() {
  _origG2PCreate = G2P.create;
  G2P.create = async () => createMockG2PInstance();
}
function restoreG2PCreate() {
  if (_origG2PCreate) {
    G2P.create = _origG2PCreate;
    _origG2PCreate = null;
  }
}

// ===========================================================================
// Tests
// ===========================================================================

describe('PiperPlus WASM G2P integration', { skip: skip ? 'Import failed' : false }, () => {
  beforeEach(() => {
    installGlobalMocks();
    installModelManagerStub();
    stubG2PCreate();
  });

  afterEach(() => {
    restoreG2PCreate();
    removeModelManagerStub();
  });

  // -------------------------------------------------------------------------
  // M2-1: WASM loader tests
  // -------------------------------------------------------------------------

  describe('M2-1: WASM loader in _init()', () => {
    it('falls back gracefully when WASM import fails', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const piper = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        assert.ok(piper._phonemizer, 'Phonemizer should still be initialized');
        assert.ok(piper.isInitialized, 'PiperPlus should be initialized');

        const wasmWarnings = warnings.filter(w => w.includes('Rust WASM G2P failed'));
        assert.ok(wasmWarnings.length > 0, 'Should log WASM fallback warning');

        piper.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('loads WASM when zh (WASM-required) is in config even without ja', async () => {
      setMockConfig(CONFIG_WITHOUT_JA); // has zh but no ja

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const piper = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        assert.ok(piper._phonemizer, 'Phonemizer should be initialized');

        // WASM should be attempted (and fail in test env), excluding zh
        const wasmWarnings = warnings.filter(w => w.includes('Rust WASM G2P failed'));
        assert.ok(wasmWarnings.length > 0, 'WASM should be attempted for zh');
        assert.ok(wasmWarnings[0].includes('zh'), 'Warning should mention zh');

        piper.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('skips WASM load when no WASM-required languages in config', async () => {
      setMockConfig(CONFIG_NO_WASM_LANGS); // en, es, fr only

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const piper = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        assert.ok(piper._phonemizer, 'Phonemizer should be initialized');

        const wasmWarnings = warnings.filter(w => w.includes('Rust WASM'));
        assert.equal(wasmWarnings.length, 0, 'No WASM attempt when no WASM-required langs');

        piper.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('skips WASM load when no language_id_map in config', async () => {
      setMockConfig(BASE_CONFIG); // no language_id_map

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.ok(piper._phonemizer, 'Phonemizer should be initialized');
      piper.dispose();
    });

    it('G2P.create receives languages without WASM-required langs (ja, zh)', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let capturedOptions = null;
      restoreG2PCreate();
      G2P.create = async (opts) => {
        capturedOptions = opts;
        return createMockG2PInstance();
      };

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.ok(capturedOptions, 'G2P.create should have been called');
      assert.ok(
        !capturedOptions.languages?.includes('ja'),
        'ja should not be in G2P languages'
      );
      assert.ok(
        !capturedOptions.languages?.includes('zh'),
        'zh should not be in G2P languages (WASM-required)'
      );
      assert.deepEqual(
        capturedOptions.languages?.sort(),
        ['en', 'es', 'fr', 'pt'],
        'Only JS G2P-capable languages should be passed to G2P.create'
      );

      piper.dispose();
    });
  });

  // -------------------------------------------------------------------------
  // M2-2: _textToPhonemeIds branch tests
  // -------------------------------------------------------------------------

  describe('M2-2: _textToPhonemeIds Japanese branch', () => {
    /**
     * Helper: create a PiperPlus instance with mock phonemizer that wraps
     * the WASM mock. Since CompositePhonemizer is now the single _phonemizer
     * on the PiperPlus instance, we inject it directly.
     */
    async function createInstanceWithWasmPhonemizer(wasmPhonemizer) {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Build a mock CompositePhonemizer that routes JA to WASM, others to JS G2P
      const jsG2p = createMockG2PInstance();
      piper._phonemizer = {
        encode: (text, language) => {
          if (language === 'ja') {
            const result = wasmPhonemizer.phonemize(text, language);
            const phonemeIds = Array.from(result.phonemeIds);
            const raw = result.prosodyFeatures;
            let prosodyFeatures = null;
            if (raw && raw.length > 0) {
              prosodyFeatures = [];
              for (let i = 0; i < raw.length; i += 3) {
                prosodyFeatures.push([raw[i], raw[i + 1], raw[i + 2]]);
              }
            }
            if (typeof result.free === 'function') result.free();
            return { phonemeIds, prosodyFeatures };
          }
          return jsG2p.encode(text, language);
        },
        detectLanguage: (text) => wasmPhonemizer.detectLanguage(text),
        dispose: () => {
          wasmPhonemizer.free();
          jsG2p.dispose();
        },
        supportedLanguages: ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
      };
      return piper;
    }

    it('JA via phonemizer calls WASM phonemize()', async () => {
      let phonemizeCalled = false;
      const mockWasm = createMockWasmPhonemizer();
      const origPhon = mockWasm.phonemize;
      mockWasm.phonemize = (text, lang) => {
        phonemizeCalled = true;
        assert.equal(text, 'こんにちは');
        assert.equal(lang, 'ja');
        return origPhon(text, lang);
      };

      const piper = await createInstanceWithWasmPhonemizer(mockWasm);
      const result = await piper._textToPhonemeIds('こんにちは', 'ja');

      assert.ok(phonemizeCalled, 'WASM phonemize should be called for ja');
      assert.ok(Array.isArray(result.phonemeIds), 'phonemeIds should be a plain array');
      assert.equal(result.phonemeIds[0], 1, 'Should start with BOS (1)');
      assert.equal(result.phonemeIds[result.phonemeIds.length - 1], 2, 'Should end with EOS (2)');

      piper.dispose();
    });

    it('JA converts Int32Array phonemeIds to number[]', async () => {
      const mockWasm = createMockWasmPhonemizer();
      const piper = await createInstanceWithWasmPhonemizer(mockWasm);

      const result = await piper._textToPhonemeIds('テスト', 'ja');

      assert.ok(Array.isArray(result.phonemeIds), 'Should be plain Array, not Int32Array');
      assert.ok(!(result.phonemeIds instanceof Int32Array), 'Must not be Int32Array');
      for (const id of result.phonemeIds) {
        assert.equal(typeof id, 'number', 'Each element should be a number');
      }

      piper.dispose();
    });

    it('JA groups flat prosody into nested [[a1,a2,a3],...]', async () => {
      const mockWasm = createMockWasmPhonemizer();
      const piper = await createInstanceWithWasmPhonemizer(mockWasm);

      const result = await piper._textToPhonemeIds('テスト', 'ja');

      assert.ok(result.prosodyFeatures, 'prosodyFeatures should not be null');
      assert.ok(Array.isArray(result.prosodyFeatures), 'Should be an array');
      assert.equal(result.prosodyFeatures.length, 3, 'Should have 3 prosody groups (9/3)');

      for (const group of result.prosodyFeatures) {
        assert.ok(Array.isArray(group), 'Each group should be an array');
        assert.equal(group.length, 3, 'Each group should have 3 elements [a1, a2, a3]');
      }

      assert.deepEqual(result.prosodyFeatures[0], [-2, 1, 5]);
      assert.deepEqual(result.prosodyFeatures[1], [-1, 2, 5]);
      assert.deepEqual(result.prosodyFeatures[2], [0, 3, 5]);

      piper.dispose();
    });

    it('JA with empty prosody returns null prosodyFeatures', async () => {
      const mockWasm = createMockWasmPhonemizer();
      mockWasm.phonemize = () => ({
        phonemeIds: new Int32Array([1, 8, 2]),
        prosodyFeatures: new Int32Array([]),
        phonemeCount: 3,
        free() {},
      });

      const piper = await createInstanceWithWasmPhonemizer(mockWasm);
      const result = await piper._textToPhonemeIds('あ', 'ja');

      assert.equal(result.prosodyFeatures, null, 'Empty prosody should result in null');

      piper.dispose();
    });

    it('JA without WASM falls back to JS G2P via phonemizer', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let encodeCalled = false;
      restoreG2PCreate();
      G2P.create = async () => ({
        ...createMockG2PInstance(),
        encode: (text, language) => {
          encodeCalled = true;
          return { phonemeIds: [1, 7, 2], prosodyFeatures: null };
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // phonemizer is set (CompositePhonemizer with JS fallback, no WASM)
      assert.ok(piper._phonemizer, 'phonemizer should be set');

      // Calling with 'ja' should fall back to JS G2P via CompositePhonemizer fallback
      const result = await piper._textToPhonemeIds('こんにちは', 'ja');
      assert.ok(encodeCalled, 'JS G2P encode should be called as fallback');

      piper.dispose();
    });

    it('EN via phonemizer uses JS G2P (not WASM)', async () => {
      let wasmCalled = false;
      let jsG2pCalled = false;

      const mockWasm = createMockWasmPhonemizer();
      const origPhon = mockWasm.phonemize;
      mockWasm.phonemize = (text, lang) => {
        wasmCalled = true;
        return origPhon(text, lang);
      };

      setMockConfig(CONFIG_WITH_JA);

      restoreG2PCreate();
      G2P.create = async () => ({
        ...createMockG2PInstance(),
        encode: (text, language) => {
          jsG2pCalled = true;
          return { phonemeIds: [1, 7, 2], prosodyFeatures: null };
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Inject a mock phonemizer that routes JA to WASM, EN to JS
      const jsG2p = createMockG2PInstance();
      jsG2p.encode = (text, language) => {
        jsG2pCalled = true;
        return { phonemeIds: [1, 7, 2], prosodyFeatures: null };
      };
      piper._phonemizer = {
        encode: (text, language) => {
          if (language === 'ja') {
            wasmCalled = true;
            return { phonemeIds: [1, 7, 2], prosodyFeatures: null };
          }
          return jsG2p.encode(text, language);
        },
        detectLanguage: (text) => 'en',
        dispose: () => {},
        supportedLanguages: ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
      };

      await piper._textToPhonemeIds('hello', 'en');

      assert.ok(!wasmCalled, 'WASM should NOT be called for non-ja');
      assert.ok(jsG2pCalled, 'JS G2P should be called for en');

      piper.dispose();
    });
  });

  // -------------------------------------------------------------------------
  // M2-2: _detectLanguage tests
  // -------------------------------------------------------------------------

  describe('M2-2: _detectLanguage', () => {
    it('uses phonemizer.detectLanguage', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Inject a mock phonemizer with WASM-like detection
      const mockWasm = createMockWasmPhonemizer();
      piper._phonemizer = {
        encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
        detectLanguage: (text) => mockWasm.detectLanguage(text),
        dispose: () => {},
        supportedLanguages: ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
      };

      assert.equal(piper._detectLanguage('こんにちは'), 'ja');
      assert.equal(piper._detectLanguage('Hello'), 'en');

      piper.dispose();
    });

    it('falls back to phonemizer.detectLanguage when no WASM', async () => {
      setMockConfig(CONFIG_WITHOUT_JA);

      let detectCalled = false;
      restoreG2PCreate();
      G2P.create = async () => ({
        ...createMockG2PInstance(),
        detectLanguage: (text) => {
          detectCalled = true;
          return 'en';
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      const lang = piper._detectLanguage('Hello');

      // The phonemizer delegates to its internal detector
      assert.equal(lang, 'en');

      piper.dispose();
    });

    it('synthesize uses _detectLanguage for auto-detection', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let detectedLang = null;
      const mockWasm = createMockWasmPhonemizer();
      const origDetect = mockWasm.detectLanguage;

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Inject mock phonemizer with detection tracking
      piper._phonemizer = {
        encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
        detectLanguage: (text) => {
          detectedLang = origDetect(text);
          return detectedLang;
        },
        dispose: () => {},
        supportedLanguages: ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
      };

      // Synthesize without explicit language — should auto-detect
      await piper.synthesize('Hello world');

      assert.equal(detectedLang, 'en', 'Should auto-detect English');

      piper.dispose();
    });

    it('explicit language option bypasses detection', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let detectCalled = false;

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Inject mock phonemizer with detection tracking
      piper._phonemizer = {
        encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
        detectLanguage: () => {
          detectCalled = true;
          return 'ja';
        },
        dispose: () => {},
        supportedLanguages: ['ja', 'en', 'zh', 'es', 'fr', 'pt'],
      };

      await piper.synthesize('hello', { language: 'en' });

      assert.ok(!detectCalled, 'detectLanguage should NOT be called when language is explicit');

      piper.dispose();
    });
  });

  // -------------------------------------------------------------------------
  // M2-2: dispose tests
  // -------------------------------------------------------------------------

  describe('M2-2: dispose() phonemizer cleanup', () => {
    it('dispose calls phonemizer.dispose()', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      let disposed = false;
      piper._phonemizer = {
        encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
        detectLanguage: () => 'ja',
        dispose: () => { disposed = true; },
        supportedLanguages: ['ja', 'en'],
      };

      piper.dispose();

      assert.ok(disposed, 'phonemizer.dispose() should be called');
      assert.equal(piper._phonemizer, null, '_phonemizer should be null after dispose');
    });

    it('dispose is idempotent — second call does not throw', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      piper.dispose();
      assert.doesNotThrow(() => piper.dispose(), 'Second dispose should not throw');
    });

    it('dispose handles null phonemizer gracefully', async () => {
      setMockConfig(CONFIG_WITHOUT_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      piper._phonemizer = null;
      assert.doesNotThrow(() => piper.dispose(), 'dispose with null phonemizer should not throw');
    });

    it('dispose cleans up on partial init failure', async () => {
      setMockConfig(CONFIG_WITH_JA);

      // Make G2P.create fail to trigger partial init cleanup
      restoreG2PCreate();
      G2P.create = async () => { throw new Error('G2P init failed'); };

      try {
        await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });
        assert.fail('Should have thrown');
      } catch (err) {
        assert.ok(err.message.includes('G2P init failed'));
        // dispose() was called internally — no leaked resources
      }
    });
  });
});

// ---------------------------------------------------------------------------
// Report import error
// ---------------------------------------------------------------------------

if (importError) {
  describe('import error', () => {
    it('should not have an import error', () => {
      assert.fail(`Failed to import modules: ${importError.message}`);
    });
  });
}

// ---------------------------------------------------------------------------
// Restore globals on exit
// ---------------------------------------------------------------------------

process.on('exit', () => {
  globalThis.fetch = _origFetch;
  globalThis.ort = _origOrt;
  globalThis.indexedDB = _origIndexedDB;
});
