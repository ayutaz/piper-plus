/**
 * PiperPlus G2P.create() integration tests
 *
 * Verifies that PiperPlus._init() calls G2P.create() with the correct
 * parameters derived from the model config. This catches bugs where:
 *
 * - G2P.create() is called with 'ja' in languages but missing openjtalkModule
 * - G2P.create() parameters don't match what the config specifies
 * - language_id_map extraction is incorrect
 *
 * These tests exercise the REAL _init() code path (not a stub), with only
 * G2P.create() and ONNX session creation mocked at the boundary.
 *
 * Run: node --test test/js/test-piper-plus-g2p-init.js
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
// Global mocks (must be installed before importing PiperPlus)
// ---------------------------------------------------------------------------

/** Config returned by mock fetch — overridden per test via `setMockConfig()`. */
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
        json: async () => structuredClone(mockConfig),
      };
    }
    return {
      ok: true,
      status: 200,
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

/** Stub ModelManager.resolveUrls */
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

/** Mock G2P instance returned by our spy. */
function createMockG2PInstance() {
  return {
    detectLanguage: () => 'en',
    encode: (text, language) => ({ phonemeIds: [1, 7, 2], prosodyFeatures: null }),
    phonemize: () => ({ tokens: ['h', 'e', 'l', 'o'], prosody: [null, null, null, null], language: 'en' }),
    dispose: () => {},
  };
}

/**
 * Install a spy on G2P.create() that records calls and returns a mock instance.
 * Returns an object with:
 *   - calls: array of options objects passed to G2P.create()
 *   - restore: function to restore the original G2P.create()
 */
function spyOnG2PCreate() {
  const original = G2P.create;
  const calls = [];

  G2P.create = async (options) => {
    calls.push(structuredClone(options || {}));
    return createMockG2PInstance();
  };

  return {
    calls,
    restore: () => { G2P.create = original; },
  };
}

// ---------------------------------------------------------------------------
// Base config
// ---------------------------------------------------------------------------

const BASE_CONFIG = {
  audio: { sample_rate: 22050 },
  inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
  phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
  num_speakers: 1,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PiperPlus G2P.create() integration', { skip: skip ? 'Import failed' : false }, () => {
  let g2pSpy;

  beforeEach(() => {
    installModelManagerStub();
    g2pSpy = spyOnG2PCreate();
  });

  afterEach(() => {
    removeModelManagerStub();
    g2pSpy.restore();
  });

  it('config with language_id_map (no WASM-required) passes languages to G2P.create()', async () => {
    setMockConfig({
      ...BASE_CONFIG,
      language_id_map: { en: 0, es: 1, fr: 2 },
    });

    const piper = await PiperPlus.initialize({ model: 'test', ort: globalThis.ort });
    piper.dispose();

    assert.equal(g2pSpy.calls.length, 1, 'G2P.create() should be called once');
    const langs = g2pSpy.calls[0].languages;
    assert.deepEqual(langs.sort(), ['en', 'es', 'fr'], 'should pass languages from language_id_map');
  });

  it('config without language_id_map passes undefined languages', async () => {
    setMockConfig({ ...BASE_CONFIG });

    const piper = await PiperPlus.initialize({ model: 'test', ort: globalThis.ort });
    piper.dispose();

    assert.equal(g2pSpy.calls.length, 1);
    assert.equal(g2pSpy.calls[0].languages, undefined, 'languages should be undefined when no language_id_map');
  });

  it('config with ja+zh excludes WASM-required langs from JS G2P on WASM fallback', async () => {
    setMockConfig({
      ...BASE_CONFIG,
      language_id_map: { ja: 0, en: 1, zh: 2, es: 3, fr: 4, pt: 5 },
    });

    const piper = await PiperPlus.initialize({ model: 'test', ort: globalThis.ort });
    piper.dispose();

    assert.equal(g2pSpy.calls.length, 1);
    const langs = g2pSpy.calls[0].languages;
    assert.ok(!langs.includes('ja'), 'ja should be excluded from JS G2P languages');
    assert.ok(!langs.includes('zh'), 'zh should be excluded from JS G2P languages');
    assert.deepEqual(langs.sort(), ['en', 'es', 'fr', 'pt']);
  });

  it('G2P.create() failure propagates to PiperPlus.initialize()', async () => {
    setMockConfig({
      ...BASE_CONFIG,
      language_id_map: { ja: 0, en: 1 },
    });

    // Replace spy with one that throws (simulates missing openjtalkModule)
    g2pSpy.restore();
    const original = G2P.create;
    G2P.create = async () => {
      throw new Error('openjtalkModule is required.');
    };

    try {
      await assert.rejects(
        () => PiperPlus.initialize({ model: 'test', ort: globalThis.ort }),
        (err) => err.message.includes('openjtalkModule'),
        'PiperPlus.initialize should propagate G2P.create() errors'
      );
    } finally {
      G2P.create = original;
    }
  });

  it('real G2P.create() with ja and no openjtalkModule initializes without ja', async () => {
    setMockConfig({
      ...BASE_CONFIG,
      language_id_map: { ja: 0, en: 1 },
    });

    // Use real G2P.create() (restore spy)
    g2pSpy.restore();

    // Should succeed — ja is excluded, en is initialized
    const piper = await PiperPlus.initialize({ model: 'test', ort: globalThis.ort });
    assert.ok(piper, 'Should initialize successfully with ja excluded');
    piper.dispose();
  });

  it('config with only non-ja languages initializes successfully', async () => {
    setMockConfig({
      ...BASE_CONFIG,
      language_id_map: { en: 0, zh: 1, es: 2 },
    });

    // Use real G2P.create() (restore spy)
    g2pSpy.restore();

    const piper = await PiperPlus.initialize({ model: 'test', ort: globalThis.ort });
    assert.ok(piper, 'Should initialize successfully without ja');
    piper.dispose();
  });
});

// ---------------------------------------------------------------------------
// Restore globals on exit
// ---------------------------------------------------------------------------

afterEach(() => {
  // Not strictly needed since process exits, but good hygiene
});

// Restore on module unload
process.on('exit', () => {
  globalThis.fetch = _origFetch;
  globalThis.ort = _origOrt;
  globalThis.indexedDB = _origIndexedDB;
});
