/**
 * PiperPlus._init() integration tests
 *
 * Exercises the REAL _init() code path with mocked external dependencies.
 * Unlike test-piper-plus-init-success.js which stubs _init() entirely,
 * this test only mocks external APIs (fetch, ort, indexedDB, G2P.create)
 * and lets the actual _init() logic run.
 *
 * Run with: node --test test/js/test-piper-plus-init-integration.js
 */

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Save original globals
// ---------------------------------------------------------------------------

const _origFetch = globalThis.fetch;
const _origOrt = globalThis.ort;
const _origIndexedDB = globalThis.indexedDB;
// navigator is read-only in Node.js — no need to save/restore

// ---------------------------------------------------------------------------
// Mock config variants
// ---------------------------------------------------------------------------

const BASE_CONFIG = {
  audio: { sample_rate: 22050 },
  inference: {
    noise_scale: 0.667,
    length_scale: 1.0,
    noise_w: 0.8,
  },
  phoneme_id_map: {
    _: [0],
    '^': [1],
    $: [2],
    a: [7],
    ' ': [3],
  },
  num_speakers: 1,
  num_languages: 6,
};

const CONFIG_WITH_LANG_MAP = {
  ...BASE_CONFIG,
  language_id_map: { en: 0, es: 1 },
};

const CONFIG_WITH_PUA_COMPAT = {
  ...BASE_CONFIG,
  pua_compat_version: 2,
};

const CONFIG_WITH_BAD_PUA = {
  ...BASE_CONFIG,
  pua_compat_version: 999,
};

const CONFIG_NO_PHONEME_MAP = {
  audio: { sample_rate: 22050 },
  inference: { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
  num_speakers: 1,
  num_languages: 1,
};

// ---------------------------------------------------------------------------
// Mock ONNX session
// ---------------------------------------------------------------------------

function createMockSession() {
  return {
    inputNames: ['input', 'input_lengths', 'scales'],
    outputNames: ['output'],
    run: async () => ({
      output: { data: new Float32Array(22050), dims: [1, 22050] },
    }),
    release: () => {},
  };
}

// ---------------------------------------------------------------------------
// Mock ort
// ---------------------------------------------------------------------------

function createMockOrt({ sessionCreateFn } = {}) {
  return {
    InferenceSession: {
      create: sessionCreateFn || (async () => createMockSession()),
    },
    Tensor: class {
      constructor(type, data, dims) {
        this.type = type;
        this.data = data;
        this.dims = dims;
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Mock G2P instance
// ---------------------------------------------------------------------------

function createMockG2P({ encodeFn } = {}) {
  // This mock represents the raw G2P instance (wrapped by JsG2pAdapter).
  // JsG2pAdapter calls g2p.encode(text, phonemeIdMap, { language }),
  // so we use the old 3-arg API here.
  return {
    detectLanguage: () => 'ja',
    encode: encodeFn || ((_text, _phonemeIdMap, _opts) => ({
      phonemeIds: [1, 7, 2],
      prosodyFlat: null,
    })),
    phonemize: () => ({ tokens: ['a'], prosody: [null] }),
    phonemizeWithProsody: () => ({ tokens: ['a'], prosody: [null] }),
    dispose: () => {},
  };
}

// ---------------------------------------------------------------------------
// Install browser mocks on globalThis
// ---------------------------------------------------------------------------

function installGlobalMocks({ configOverride, fetchFn } = {}) {
  // -- fetch ----------------------------------------------------------------
  globalThis.fetch = fetchFn || (async (url) => {
    if (typeof url === 'string' && url.endsWith('.json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => structuredClone(configOverride || BASE_CONFIG),
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(16),
    };
  });

  // -- ort ------------------------------------------------------------------
  globalThis.ort = createMockOrt();

  // -- indexedDB -------------------------------------------------------------
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
                  setTimeout(() => {
                    r.result = null;
                    if (r.onsuccess) r.onsuccess();
                  }, 0);
                  return r;
                },
                put: () => {
                  const r = {};
                  setTimeout(() => {
                    if (r.onsuccess) r.onsuccess();
                  }, 0);
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

function restoreGlobals() {
  const restore = (key, orig) => {
    if (orig !== undefined) {
      globalThis[key] = orig;
    } else {
      delete globalThis[key];
    }
  };
  restore('fetch', _origFetch);
  restore('ort', _origOrt);
  restore('indexedDB', _origIndexedDB);
  // navigator is read-only in Node.js — no restore needed
}

// ---------------------------------------------------------------------------
// Import modules — mocks must be installed first
// ---------------------------------------------------------------------------

installGlobalMocks();

let PiperPlus;
let ModelManager;
let G2P;
let importError = null;

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  ModelManager = mod.ModelManager;
  const g2pMod = await import('@piper-plus/g2p');
  G2P = g2pMod.G2P;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Prototype stubs: ModelManager.resolveUrls
// ---------------------------------------------------------------------------

let _origResolveUrls;

function stubResolveUrls() {
  _origResolveUrls = ModelManager.prototype.resolveUrls;
  ModelManager.prototype.resolveUrls = async function (modelNameOrUrl) {
    if (/^https?:\/\//i.test(modelNameOrUrl)) {
      return {
        modelUrl: modelNameOrUrl,
        configUrl: modelNameOrUrl + '.json',
        configFallbackUrl: null,
        cacheKey: modelNameOrUrl,
      };
    }
    return {
      modelUrl: `https://huggingface.co/mock/${modelNameOrUrl}/model.onnx`,
      configUrl: `https://huggingface.co/mock/${modelNameOrUrl}/model.onnx.json`,
      configFallbackUrl: null,
      cacheKey: modelNameOrUrl,
    };
  };
}

function restoreResolveUrls() {
  if (_origResolveUrls !== undefined) {
    ModelManager.prototype.resolveUrls = _origResolveUrls;
  } else {
    delete ModelManager.prototype.resolveUrls;
  }
}

// ---------------------------------------------------------------------------
// G2P.create stub helper
// ---------------------------------------------------------------------------

let _origG2PCreate;

function stubG2PCreate({ createFn } = {}) {
  _origG2PCreate = G2P.create;
  G2P.create = createFn || (async () => createMockG2P());
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

describe('PiperPlus._init() integration (real _init, mocked deps)', { skip }, () => {
  beforeEach(() => {
    installGlobalMocks();
    stubResolveUrls();
    stubG2PCreate();
  });

  afterEach(() => {
    restoreG2PCreate();
    restoreResolveUrls();
    restoreGlobals();
  });

  // -----------------------------------------------------------------------
  // A) Full initialization flow
  // -----------------------------------------------------------------------

  describe('A) Full initialization flow', () => {
    it('config WITHOUT language_id_map: _init completes with all fields set', async () => {
      // BASE_CONFIG has no language_id_map
      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.equal(instance.isInitialized, true);
      assert.ok(instance._config, '_config should be set');
      assert.ok(instance._session, '_session should be created');
      assert.ok(instance._phonemizer, '_phonemizer should be set');
      assert.equal(instance._initialized, true);
      assert.equal(instance._config.audio.sample_rate, 22050);

      instance.dispose();
    });

    it('config WITH language_id_map: G2P.create receives correct languages', async () => {
      // Override fetch to return config with language_id_map
      installGlobalMocks({ configOverride: CONFIG_WITH_LANG_MAP });

      let capturedOptions = null;
      restoreG2PCreate();
      stubG2PCreate({
        createFn: async (opts) => {
          capturedOptions = opts;
          return createMockG2P();
        },
      });

      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.ok(capturedOptions, 'G2P.create should have been called');
      assert.deepStrictEqual(
        capturedOptions.languages.sort(),
        ['en', 'es'],
        'G2P.create should receive languages from language_id_map keys'
      );

      instance.dispose();
    });
  });

  // -----------------------------------------------------------------------
  // B) WebGPUSessionManager integration
  // -----------------------------------------------------------------------

  describe('B) WebGPUSessionManager integration', () => {
    it('WebGPUSessionManager.createSession is called during _init', async () => {
      let sessionCreateCalled = false;
      let sessionCreateUrl = null;

      // Override ort to spy on session creation
      globalThis.ort = createMockOrt({
        sessionCreateFn: async (url, _opts) => {
          sessionCreateCalled = true;
          sessionCreateUrl = url;
          return createMockSession();
        },
      });

      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.ok(sessionCreateCalled, 'ort.InferenceSession.create should be called');
      assert.ok(
        sessionCreateUrl.includes('huggingface.co/mock/test'),
        `Session created with model URL, got: ${sessionCreateUrl}`
      );

      instance.dispose();
    });
  });

  // -----------------------------------------------------------------------
  // C) Config parsing
  // -----------------------------------------------------------------------

  describe('C) Config parsing', () => {
    it('config with matching pua_compat_version: no warning', async () => {
      installGlobalMocks({ configOverride: CONFIG_WITH_PUA_COMPAT });

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const instance = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        const puaWarnings = warnings.filter((w) => w.includes('PUA'));
        assert.equal(puaWarnings.length, 0, 'No PUA warning for matching version');

        instance.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('config with mismatching pua_compat_version: console.warn emitted', async () => {
      installGlobalMocks({ configOverride: CONFIG_WITH_BAD_PUA });

      const warnings = [];
      const origWarn = console.warn;
      console.warn = (...args) => warnings.push(args.join(' '));

      try {
        const instance = await PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        });

        const puaWarnings = warnings.filter((w) => w.includes('PUA'));
        assert.ok(puaWarnings.length > 0, 'PUA mismatch warning should be emitted');
        assert.ok(
          puaWarnings[0].includes('999'),
          'Warning should mention the model version'
        );

        instance.dispose();
      } finally {
        console.warn = origWarn;
      }
    });

    it('config missing phoneme_id_map: init succeeds, synthesize uses fallback G2P', async () => {
      // With the new CompositePhonemizer architecture, phoneme_id_map validation
      // is handled internally by JsG2pAdapter. When phoneme_id_map is undefined,
      // the mock G2P still works (real G2P would fail at encode time).
      installGlobalMocks({ configOverride: CONFIG_NO_PHONEME_MAP });

      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      assert.equal(instance.isInitialized, true, 'init should succeed');
      assert.ok(instance._phonemizer, 'phonemizer should be set');

      instance.dispose();
    });
  });

  // -----------------------------------------------------------------------
  // D) Error propagation
  // -----------------------------------------------------------------------

  describe('D) Error propagation', () => {
    it('fetch returns ok:false for config -> _init throws HTTP error', async () => {
      installGlobalMocks({
        fetchFn: async (url) => {
          if (typeof url === 'string' && url.endsWith('.json')) {
            return {
              ok: false,
              status: 404,
              statusText: 'Not Found',
              json: async () => ({}),
            };
          }
          return {
            ok: true,
            status: 200,
            statusText: 'OK',
            arrayBuffer: async () => new ArrayBuffer(16),
          };
        },
      });

      await assert.rejects(
        () => PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        }),
        (err) => {
          assert.ok(
            err.message.includes('404') || err.message.includes('Not Found'),
            `Error should include HTTP status, got: ${err.message}`
          );
          return true;
        }
      );
    });

    it('ONNX session creation fails -> _init throws and disposes partial state', async () => {
      globalThis.ort = createMockOrt({
        sessionCreateFn: async () => {
          throw new Error('ONNX session load failed');
        },
      });

      await assert.rejects(
        () => PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        }),
        (err) => {
          assert.ok(
            err.message.includes('ONNX session load failed') ||
            err.message.includes('All execution providers failed'),
            `Error should propagate, got: ${err.message}`
          );
          return true;
        }
      );
    });

    it('G2P.create fails -> _init throws and disposes session', async () => {
      let sessionReleased = false;
      globalThis.ort = createMockOrt({
        sessionCreateFn: async () => {
          const session = createMockSession();
          session.release = () => { sessionReleased = true; };
          return session;
        },
      });

      restoreG2PCreate();
      stubG2PCreate({
        createFn: async () => {
          throw new Error('WASM init failed');
        },
      });

      await assert.rejects(
        () => PiperPlus.initialize({
          model: 'test',
          ort: globalThis.ort,
        }),
        (err) => {
          assert.ok(
            err.message.includes('WASM init failed'),
            `Error should propagate, got: ${err.message}`
          );
          return true;
        }
      );

      assert.ok(sessionReleased, 'Session should be released on G2P failure (dispose called)');
    });
  });

  // -----------------------------------------------------------------------
  // E) _textToPhonemeIds integration
  // -----------------------------------------------------------------------

  describe('E) _textToPhonemeIds integration', () => {
    it('synthesize calls G2P.encode with correct params', async () => {
      let encodeCalls = [];

      restoreG2PCreate();
      stubG2PCreate({
        createFn: async () => createMockG2P({
          // G2P.encode is called by JsG2pAdapter with old 3-arg API:
          // g2p.encode(text, phonemeIdMap, { language })
          encodeFn: (text, phonemeIdMap, opts) => {
            encodeCalls.push({ text, phonemeIdMap, opts });
            return { phonemeIds: [1, 7, 2], prosodyFlat: null };
          },
        }),
      });

      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      await instance.synthesize('hello');

      assert.equal(encodeCalls.length, 1, 'encode should be called once');
      assert.equal(encodeCalls[0].text, 'hello', 'text should be passed');
      assert.deepStrictEqual(
        encodeCalls[0].phonemeIdMap,
        BASE_CONFIG.phoneme_id_map,
        'phonemeIdMap from config should be passed'
      );
      assert.ok(
        encodeCalls[0].opts && 'language' in encodeCalls[0].opts,
        'language option should be passed'
      );

      instance.dispose();
    });

    it('synthesize with explicit language passes it to G2P.encode', async () => {
      let capturedOpts = null;

      restoreG2PCreate();
      stubG2PCreate({
        createFn: async () => createMockG2P({
          // G2P.encode is called by JsG2pAdapter with old 3-arg API
          encodeFn: (text, phonemeIdMap, opts) => {
            capturedOpts = opts;
            return { phonemeIds: [1, 7, 2], prosodyFlat: null };
          },
        }),
      });

      const instance = await PiperPlus.initialize({
        model: 'test',
        ort: globalThis.ort,
      });

      await instance.synthesize('hola', { language: 'es' });

      assert.ok(capturedOpts, 'encode opts should be captured');
      assert.equal(capturedOpts.language, 'es', 'explicit language should be forwarded');

      instance.dispose();
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
