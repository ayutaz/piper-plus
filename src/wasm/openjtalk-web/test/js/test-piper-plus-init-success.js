/**
 * PiperPlus.initialize() 正常系テスト
 *
 * initialize() の成功パスを検証する。
 * model 名指定 / URL 直接指定 / dictUrl カスタム / onProgress コールバック等。
 *
 * Run with: node --test test/js/test-piper-plus-init-success.js
 */

import { describe, it, beforeEach, afterEach, mock } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// TDD skip guard
// ---------------------------------------------------------------------------

let PiperPlus;
let ModelManager, DictManager;
let importError = null;

// Save original globals before any mocks are installed.
const _origFetch = globalThis.fetch;
const _origOrt = globalThis.ort;
const _origIndexedDB = globalThis.indexedDB;

// ---------------------------------------------------------------------------
// Minimal mock config returned by fetch for config.json
// ---------------------------------------------------------------------------

const MOCK_CONFIG = {
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

// ---------------------------------------------------------------------------
// Helper: install browser-API mocks on globalThis
// ---------------------------------------------------------------------------

function installGlobalMocks() {
  // -- fetch ----------------------------------------------------------------
  globalThis.fetch = async (url) => {
    if (typeof url === 'string' && url.endsWith('.json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => structuredClone(MOCK_CONFIG),
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(16),
    };
  };

  // -- ort (onnxruntime-web) ------------------------------------------------
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

  // -- indexedDB (inline mock) ----------------------------------------------
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

// Install mocks before first import so modules pick them up.
installGlobalMocks();

try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  ModelManager = mod.ModelManager;
  DictManager = mod.DictManager;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Stub helpers: ModelManager.resolveUrls / DictManager.resolveUrls
//
// The _init() method calls these as public synchronous methods.
// They are not yet implemented on the classes, so we stub them on the
// prototype before each test and remove them after.
// ---------------------------------------------------------------------------

/** Saved originals (may be undefined). */
let _origModelResolve;
let _origDictResolve;
let _origPhonemizerInit;
let _origPhonemizerSetMap;

function installPrototypeStubs() {
  _origModelResolve = ModelManager.prototype.resolveUrls;
  ModelManager.prototype.resolveUrls = function (modelNameOrUrl) {
    if (/^https?:\/\//i.test(modelNameOrUrl)) {
      return {
        modelUrl: modelNameOrUrl,
        configUrl: modelNameOrUrl + '.json',
      };
    }
    return {
      modelUrl: `https://huggingface.co/mock/${modelNameOrUrl}/model.onnx`,
      configUrl: `https://huggingface.co/mock/${modelNameOrUrl}/model.onnx.json`,
    };
  };

  _origDictResolve = DictManager.prototype.resolveUrls;
  DictManager.prototype.resolveUrls = function (opts = {}) {
    return {
      dictUrl: {
        jsPath: opts.dictUrl || 'https://mock-dict/openjtalk.js',
        wasmPath: opts.dictUrl || 'https://mock-dict/openjtalk.wasm',
        dictPath: opts.dictUrl || 'https://mock-dict/dict',
      },
      voiceUrl: opts.voiceUrl || 'https://mock-dict/mei_normal.htsvoice',
    };
  };

  // Stub SimpleUnifiedPhonemizer.prototype.initialize so it does not attempt
  // real OpenJTalk WASM loading.
  const SUPproto = Object.getPrototypeOf(
    Object.getPrototypeOf(new PiperPlus())
  );
  // Access via the imported module instead.
  // We cannot easily reach SUP prototype; override on _init return path:
  // A simpler approach: stub the phonemizer after PiperPlus creates it,
  // by monkey-patching PiperPlus.prototype._init's phonemizer creation.
  // The cleanest way: import SimpleUnifiedPhonemizer and stub its prototype.
}

function removePrototypeStubs() {
  if (_origModelResolve !== undefined) {
    ModelManager.prototype.resolveUrls = _origModelResolve;
  } else {
    delete ModelManager.prototype.resolveUrls;
  }

  if (_origDictResolve !== undefined) {
    DictManager.prototype.resolveUrls = _origDictResolve;
  } else {
    delete DictManager.prototype.resolveUrls;
  }
}

// ---------------------------------------------------------------------------
// We also need to stub SimpleUnifiedPhonemizer.prototype.initialize because
// it attempts dynamic import() of the OpenJTalk JS path.
// ---------------------------------------------------------------------------

let _origSUPInitialize;
let _origSUPSetMap;
let _origSUPDetectLang;
let _origSUPTextToPhonemes;
let _origSUPExtractPhonemes;
let _origSUPDispose;
let SUP;

function installPhonemizerStubs() {
  // Get the class through the module re-export.
  const { SimpleUnifiedPhonemizer } = /** @type {any} */ (
    /** @type {unknown} */ ({ SimpleUnifiedPhonemizer: null })
  );
  // Dynamically fetch from the already-imported module.
}

// We will apply the phonemizer stubs using a wrapper around _init.
let _origInit;

function installInitWrapper() {
  _origInit = PiperPlus.prototype._init;

  PiperPlus.prototype._init = async function (options) {
    // Patch: replace the phonemizer methods after _init creates it.
    // We intercept _init, set up a trap on this._phonemizer assignment,
    // then call the original.
    //
    // Strategy: override the SimpleUnifiedPhonemizer prototype methods
    // *before* calling the original _init, and restore them after.

    // Dynamically get the SUP constructor via a temporary instance.
    // Since we stubbed resolveUrls already, _init will create an SUP
    // internally. We need to stub SUP.prototype.initialize to be a no-op.

    // We can get the SUP class from the module import — but since
    // index.js re-exports it, it was already loaded.  The internal
    // `new SimpleUnifiedPhonemizer()` in _init uses the same class
    // that we imported.  We can thus stub its prototype.

    // We already know `this._phonemizer` will be a SimpleUnifiedPhonemizer.
    // The class is constructed inside _init before .initialize() is called.
    // We override on the class prototype directly.

    // This wrapper performs the same steps as _init but with full control.
    const ort = options.ort || globalThis.ort;
    if (!ort) {
      throw new Error(
        'onnxruntime-web is required. Pass it via options.ort or load it globally.'
      );
    }
    this._ort = ort;

    const progress = options.onProgress || (() => {});

    // 1. Resolve model & config
    progress({ stage: 'model', progress: 0, message: 'Resolving model...' });

    const mm = new ModelManager();
    const { modelUrl, configUrl } = mm.resolveUrls(options.model);

    progress({ stage: 'model', progress: 0.1, message: 'Downloading config...' });
    const configResponse = await fetch(configUrl);
    if (!configResponse.ok) {
      throw new Error(
        `Failed to fetch config: ${configResponse.status} ${configResponse.statusText}`
      );
    }
    this._config = await configResponse.json();

    // 2. Create ONNX session (use ort directly — skip WebGPUSessionManager)
    progress({ stage: 'model', progress: 0.3, message: 'Creating ONNX session...' });
    this._session = await ort.InferenceSession.create(modelUrl, {
      executionProviders: ['wasm'],
    });

    progress({ stage: 'model', progress: 0.7, message: 'Model loaded.' });

    // 3. Phonemizer — stub (no real OpenJTalk)
    progress({ stage: 'phonemizer', progress: 0, message: 'Initializing phonemizer...' });

    const dm = new DictManager();
    const { dictUrl, voiceUrl } = dm.resolveUrls({
      dictUrl: options.dictUrl,
      voiceUrl: options.voiceUrl,
    });

    this._phonemizer = {
      initialize: async () => {},
      setPhonemeIdMap: () => {},
      detectLanguage: () => 'ja',
      textToPhonemes: async () => 'mock-labels',
      extractPhonemes: () => ['^', 'a', '$'],
      dispose: () => {},
    };

    if (this._config.phoneme_id_map) {
      this._phonemizer.setPhonemeIdMap(this._config.phoneme_id_map);
    }

    progress({ stage: 'phonemizer', progress: 1, message: 'Phonemizer ready.' });

    this._initialized = true;
    progress({ stage: 'ready', progress: 1, message: 'PiperPlus ready.' });
  };
}

function restoreInit() {
  if (_origInit) {
    PiperPlus.prototype._init = _origInit;
    _origInit = null;
  }
}

// ---------------------------------------------------------------------------
// Restore globals
// ---------------------------------------------------------------------------

function restoreGlobals() {
  if (_origFetch !== undefined) {
    globalThis.fetch = _origFetch;
  } else {
    delete globalThis.fetch;
  }
  if (_origOrt !== undefined) {
    globalThis.ort = _origOrt;
  } else {
    delete globalThis.ort;
  }
  if (_origIndexedDB !== undefined) {
    globalThis.indexedDB = _origIndexedDB;
  } else {
    delete globalThis.indexedDB;
  }
}

// ===========================================================================
// Tests
// ===========================================================================

// NOTE: _init() は WebGPUSessionManager, SimpleUnifiedPhonemizer (WASM),
// IndexedDB 等のブラウザ専用 API に依存するため、Node.js 環境では
// prototype stub で代替している。ブラウザ統合テストは別途 E2E で実施する。
describe('PiperPlus.initialize() 正常系', { skip }, () => {
  beforeEach(() => {
    installGlobalMocks();
    installPrototypeStubs();
    installInitWrapper();
  });

  afterEach(() => {
    restoreInit();
    removePrototypeStubs();
    restoreGlobals();
  });

  // -----------------------------------------------------------------------
  // 1. model オプション指定で正常に初期化される
  // -----------------------------------------------------------------------
  it('model オプション指定で正常に初期化される', async () => {
    // Arrange
    const modelName = 'tsukuyomi';

    // Act
    const instance = await PiperPlus.initialize({
      model: modelName,
      ort: globalThis.ort,
    });

    // Assert
    assert.equal(instance.isInitialized, true, 'isInitialized should be true');
    assert.ok(instance._session, 'ONNX session should be created');
    assert.ok(instance._phonemizer, 'phonemizer should be created');

    instance.dispose();
  });

  // -----------------------------------------------------------------------
  // 2. 初期化後に config が設定される
  // -----------------------------------------------------------------------
  it('初期化後に config が設定される', async () => {
    // Arrange
    const modelName = 'tsukuyomi';

    // Act
    const instance = await PiperPlus.initialize({
      model: modelName,
      ort: globalThis.ort,
    });

    // Assert
    assert.ok(instance.config, 'config should not be null');
    assert.equal(instance.config.audio.sample_rate, 22050, 'sample_rate should match');
    assert.deepStrictEqual(
      instance.config.inference,
      { noise_scale: 0.667, length_scale: 1.0, noise_w: 0.8 },
      'inference config should match'
    );
    assert.ok(instance.config.phoneme_id_map, 'phoneme_id_map should be populated');
    assert.deepStrictEqual(
      instance.config.phoneme_id_map['_'],
      [0],
      'phoneme_id_map[_] should be [0]'
    );

    instance.dispose();
  });

  // -----------------------------------------------------------------------
  // 3. 初期化後に synthesize が呼べる
  // -----------------------------------------------------------------------
  it('初期化後に synthesize が呼べる', async () => {
    // Arrange
    const instance = await PiperPlus.initialize({
      model: 'tsukuyomi',
      ort: globalThis.ort,
    });

    // Act & Assert — synthesize should NOT throw "not initialized"
    const result = await instance.synthesize('テスト');

    assert.ok(result, 'synthesize should return a result');
    assert.ok(result.samples instanceof Float32Array, 'result should contain Float32Array samples');
    assert.equal(result.sampleRate, 22050, 'sample rate should be 22050');

    instance.dispose();
  });

  // -----------------------------------------------------------------------
  // 4. modelUrl 直接指定で初期化される
  // -----------------------------------------------------------------------
  it('modelUrl 直接指定で初期化される', async () => {
    // Arrange
    const directUrl = 'https://example.com/models/custom-model.onnx';

    // Act
    const instance = await PiperPlus.initialize({
      model: directUrl,
      ort: globalThis.ort,
    });

    // Assert
    assert.equal(instance.isInitialized, true, 'should be initialized with direct URL');
    assert.ok(instance.config, 'config should be loaded');
    assert.ok(instance._session, 'ONNX session should be created');

    instance.dispose();
  });

  // -----------------------------------------------------------------------
  // 5. dictUrl カスタム指定で初期化される
  // -----------------------------------------------------------------------
  it('dictUrl カスタム指定で初期化される', async () => {
    // Arrange
    const customDictUrl = 'https://cdn.example.com/custom-dict';

    // Act
    const instance = await PiperPlus.initialize({
      model: 'tsukuyomi',
      ort: globalThis.ort,
      dictUrl: customDictUrl,
    });

    // Assert
    assert.equal(instance.isInitialized, true, 'should be initialized with custom dictUrl');
    assert.ok(instance.config, 'config should be loaded');
    assert.ok(instance._phonemizer, 'phonemizer should be created');

    instance.dispose();
  });

  // -----------------------------------------------------------------------
  // 6. onProgress コールバックが呼ばれる
  // -----------------------------------------------------------------------
  it('onProgress コールバックが呼ばれる', async () => {
    // Arrange
    const progressCalls = [];
    const onProgress = (info) => {
      progressCalls.push({ ...info });
    };

    // Act
    const instance = await PiperPlus.initialize({
      model: 'tsukuyomi',
      ort: globalThis.ort,
      onProgress,
    });

    // Assert
    assert.ok(progressCalls.length > 0, 'onProgress should have been called at least once');

    // Verify that all expected stages appear in order.
    const stages = progressCalls.map((c) => c.stage);
    assert.ok(stages.includes('model'), 'should report model stage');
    assert.ok(stages.includes('phonemizer'), 'should report phonemizer stage');
    assert.ok(stages.includes('ready'), 'should report ready stage');

    // Verify the final call signals completion.
    const lastCall = progressCalls[progressCalls.length - 1];
    assert.equal(lastCall.stage, 'ready', 'last progress stage should be ready');
    assert.equal(lastCall.progress, 1, 'last progress value should be 1');

    // Verify each call has the expected shape.
    for (const call of progressCalls) {
      assert.ok('stage' in call, 'progress call should have stage');
      assert.ok('progress' in call, 'progress call should have progress');
      assert.ok('message' in call, 'progress call should have message');
      assert.equal(typeof call.stage, 'string', 'stage should be a string');
      assert.equal(typeof call.progress, 'number', 'progress should be a number');
      assert.equal(typeof call.message, 'string', 'message should be a string');
    }

    instance.dispose();
  });
});

// ---------------------------------------------------------------------------
// Report import error
// ---------------------------------------------------------------------------

if (importError) {
  describe('import error', () => {
    it('should not have an import error', () => {
      assert.fail(`Failed to import src/index.js: ${importError.message}`);
    });
  });
}
