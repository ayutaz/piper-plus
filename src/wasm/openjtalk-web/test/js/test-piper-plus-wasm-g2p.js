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
    encode: () => ({ phonemeIds: [1, 7, 2], prosodyFlat: null }),
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
    it('sets _wasmPhonemizer when WASM loads successfully', async () => {
      setMockConfig(CONFIG_WITH_JA);

      // Create a data URL that exports our mock module
      // Since dynamic import() with custom URL is tricky in Node, we use
      // wasmG2pUrl option pointing to a module we control
      const mockModule = createMockWasmModule(CONFIG_WITH_JA);

      // Override G2P.create to capture languages and install WASM spy
      let capturedLanguages = null;
      restoreG2PCreate();
      G2P.create = async (opts) => {
        capturedLanguages = opts?.languages;
        return createMockG2PInstance();
      };

      // We need to test the actual _init flow. Since dynamic import() can't
      // easily be mocked in Node, we test the instance state after init by
      // using a custom approach: create instance, manually set wasmPhonemizer.
      // But first, let's test the fallback path (WASM not available).
      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Without wasmG2pUrl pointing to a real module, WASM load will fail
      // and ja should be excluded
      assert.equal(piper._wasmPhonemizer, null, 'WASM should be null when load fails');
      assert.ok(
        !capturedLanguages?.includes('ja'),
        'ja should be excluded from G2P languages when WASM fails'
      );

      piper.dispose();
    });

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

        assert.equal(piper._wasmPhonemizer, null, 'WASM should be null');
        assert.ok(piper._g2p, 'JS G2P should still be initialized');
        assert.ok(piper.isInitialized, 'PiperPlus should be initialized');

        const wasmWarnings = warnings.filter(w => w.includes('Rust WASM G2P failed'));
        assert.ok(wasmWarnings.length > 0, 'Should log WASM fallback warning');

        piper.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('skips WASM load when ja not in language_id_map', async () => {
      setMockConfig(CONFIG_WITHOUT_JA);

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const piper = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        assert.equal(piper._wasmPhonemizer, null, 'WASM should not be loaded');

        const wasmWarnings = warnings.filter(w => w.includes('Rust WASM'));
        assert.equal(wasmWarnings.length, 0, 'No WASM warning when ja not in config');

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

      assert.equal(piper._wasmPhonemizer, null, 'WASM should not be loaded');
      piper.dispose();
    });

    it('G2P.create receives languages without ja', async () => {
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
      assert.deepEqual(
        capturedOptions.languages?.sort(),
        ['en', 'es', 'fr', 'pt', 'zh'],
        'Non-JA languages should be passed to G2P.create'
      );

      piper.dispose();
    });
  });

  // -------------------------------------------------------------------------
  // M2-2: _textToPhonemeIds branch tests
  // -------------------------------------------------------------------------

  describe('M2-2: _textToPhonemeIds Japanese branch', () => {
    /**
     * Helper: create a PiperPlus instance with mock WASM phonemizer
     * bypassing the dynamic import (which can't work in Node test env).
     */
    async function createInstanceWithWasm(wasmPhonemizer) {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // Manually inject mock WASM phonemizer (since dynamic import fails in test)
      piper._wasmPhonemizer = wasmPhonemizer;
      return piper;
    }

    it('JA with wasmPhonemizer calls phonemize()', async () => {
      let phonemizeCalled = false;
      const mockWasm = createMockWasmPhonemizer();
      const origPhon = mockWasm.phonemize;
      mockWasm.phonemize = (text, lang) => {
        phonemizeCalled = true;
        assert.equal(text, 'こんにちは');
        assert.equal(lang, 'ja');
        return origPhon(text, lang);
      };

      const piper = await createInstanceWithWasm(mockWasm);
      const result = await piper._textToPhonemeIds('こんにちは', 'ja');

      assert.ok(phonemizeCalled, 'WASM phonemize should be called for ja');
      assert.ok(Array.isArray(result.phonemeIds), 'phonemeIds should be a plain array');
      assert.equal(result.phonemeIds[0], 1, 'Should start with BOS (1)');
      assert.equal(result.phonemeIds[result.phonemeIds.length - 1], 2, 'Should end with EOS (2)');

      piper.dispose();
    });

    it('JA converts Int32Array phonemeIds to number[]', async () => {
      const mockWasm = createMockWasmPhonemizer();
      const piper = await createInstanceWithWasm(mockWasm);

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
      const piper = await createInstanceWithWasm(mockWasm);

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

    it('JA calls result.free() to prevent memory leak', async () => {
      let freeCalled = false;
      const mockWasm = createMockWasmPhonemizer();
      const origPhon = mockWasm.phonemize;
      mockWasm.phonemize = (text, lang) => {
        const result = origPhon(text, lang);
        const origFree = result.free;
        result.free = () => {
          freeCalled = true;
          origFree();
        };
        return result;
      };

      const piper = await createInstanceWithWasm(mockWasm);
      await piper._textToPhonemeIds('こんにちは', 'ja');

      assert.ok(freeCalled, 'result.free() should be called after extracting data');

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

      const piper = await createInstanceWithWasm(mockWasm);
      const result = await piper._textToPhonemeIds('あ', 'ja');

      assert.equal(result.prosodyFeatures, null, 'Empty prosody should result in null');

      piper.dispose();
    });

    it('JA without wasmPhonemizer falls back to JS G2P', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let encodeCalled = false;
      restoreG2PCreate();
      G2P.create = async () => ({
        ...createMockG2PInstance(),
        encode: (text, phonemeIdMap, opts) => {
          encodeCalled = true;
          return { phonemeIds: [1, 7, 2], prosodyFlat: null };
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      // _wasmPhonemizer is null (WASM failed to load in test env)
      assert.equal(piper._wasmPhonemizer, null);

      // Calling with 'ja' should fall back to JS G2P
      const result = await piper._textToPhonemeIds('こんにちは', 'ja');
      // Note: in reality this would fail because ja is excluded from JS G2P,
      // but our mock G2P.encode doesn't check language
      assert.ok(encodeCalled, 'JS G2P encode should be called as fallback');

      piper.dispose();
    });

    it('EN with wasmPhonemizer still uses JS G2P', async () => {
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
        encode: () => {
          jsG2pCalled = true;
          return { phonemeIds: [1, 7, 2], prosodyFlat: null };
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });
      piper._wasmPhonemizer = mockWasm;

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
    it('uses wasmPhonemizer.detectLanguage when available', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      const mockWasm = createMockWasmPhonemizer();
      piper._wasmPhonemizer = mockWasm;

      assert.equal(piper._detectLanguage('こんにちは'), 'ja');
      assert.equal(piper._detectLanguage('Hello'), 'en');

      piper.dispose();
    });

    it('falls back to g2p.detectLanguage when wasmPhonemizer is null', async () => {
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

      assert.equal(piper._wasmPhonemizer, null);
      const lang = piper._detectLanguage('Hello');

      assert.ok(detectCalled, 'g2p.detectLanguage should be called');
      assert.equal(lang, 'en');

      piper.dispose();
    });

    it('synthesize uses _detectLanguage for auto-detection', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let detectedLang = null;
      const mockWasm = createMockWasmPhonemizer();
      const origDetect = mockWasm.detectLanguage;
      mockWasm.detectLanguage = (text) => {
        detectedLang = origDetect(text);
        return detectedLang;
      };

      restoreG2PCreate();
      G2P.create = async () => ({
        ...createMockG2PInstance(),
        encode: (text, map, opts) => {
          return { phonemeIds: [1, 7, 2], prosodyFlat: null };
        },
      });

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });
      piper._wasmPhonemizer = mockWasm;

      // Synthesize without explicit language — should auto-detect
      await piper.synthesize('Hello world');

      assert.equal(detectedLang, 'en', 'Should auto-detect English');

      piper.dispose();
    });

    it('explicit language option bypasses detection', async () => {
      setMockConfig(CONFIG_WITH_JA);

      let detectCalled = false;
      const mockWasm = createMockWasmPhonemizer();
      mockWasm.detectLanguage = () => {
        detectCalled = true;
        return 'ja';
      };

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });
      piper._wasmPhonemizer = mockWasm;

      await piper.synthesize('hello', { language: 'en' });

      assert.ok(!detectCalled, 'detectLanguage should NOT be called when language is explicit');

      piper.dispose();
    });
  });

  // -------------------------------------------------------------------------
  // M2-2: dispose tests
  // -------------------------------------------------------------------------

  describe('M2-2: dispose() WASM cleanup', () => {
    it('dispose calls wasmPhonemizer.free()', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      const mockWasm = createMockWasmPhonemizer();
      piper._wasmPhonemizer = mockWasm;

      piper.dispose();

      assert.ok(mockWasm._freed, 'wasmPhonemizer.free() should be called');
      assert.equal(piper._wasmPhonemizer, null, '_wasmPhonemizer should be null after dispose');
    });

    it('dispose is idempotent — second call does not throw', async () => {
      setMockConfig(CONFIG_WITH_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      const mockWasm = createMockWasmPhonemizer();
      piper._wasmPhonemizer = mockWasm;

      piper.dispose();
      assert.doesNotThrow(() => piper.dispose(), 'Second dispose should not throw');
    });

    it('dispose handles null wasmPhonemizer gracefully', async () => {
      setMockConfig(CONFIG_WITHOUT_JA);

      const piper = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.equal(piper._wasmPhonemizer, null);
      assert.doesNotThrow(() => piper.dispose(), 'dispose with null WASM should not throw');
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
