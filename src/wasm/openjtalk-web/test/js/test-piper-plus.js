/**
 * Unit Tests for PiperPlus class (src/index.js)
 *
 * Run with: node --test test/js/test-piper-plus.js
 *
 * Browser APIs (fetch, AudioContext, indexedDB, ort) are mocked.
 * No actual model loading or ONNX inference is performed.
 */

import { describe, it, mock, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Minimal browser API mocks — saved originals for safe restoration
// ---------------------------------------------------------------------------

const ORIGINAL_FETCH = globalThis.fetch;
const ORIGINAL_ORT = globalThis.ort;
const ORIGINAL_INDEXEDDB = globalThis.indexedDB;

/** Default mock config.json returned by the mock fetch. */
function makeConfigJson(overrides = {}) {
  return {
    audio: { sample_rate: 22050 },
    inference: {
      noise_scale: 0.667,
      length_scale: 1.0,
      noise_w: 0.8,
    },
    phoneme_id_map: { _: [0], '^': [1], $: [2] },
    num_speakers: 1,
    num_languages: 6,
    ...overrides,
  };
}

/** Install default global mocks. */
function installGlobalMocks() {
  globalThis.fetch = async (url) => {
    if (typeof url === 'string' && url.endsWith('.json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        json: async () => makeConfigJson(),
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
        outputNames: ['output', 'durations'],
        run: async (feeds) => {
          const inputLen =
            (feeds?.input?.data && feeds.input.data.length) ||
            (feeds?.input?.dims && feeds.input.dims[1]) ||
            5;
          const durData = new Float32Array(inputLen);
          for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
          return {
            output: { data: new Float32Array(22050), dims: [1, 22050] },
            durations: { data: durData, dims: [1, inputLen] },
          };
        },
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
                clear: () => {
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

/** Restore all global mocks to their originals. */
function restoreGlobalMocks() {
  if (ORIGINAL_FETCH !== undefined) {
    globalThis.fetch = ORIGINAL_FETCH;
  } else {
    delete globalThis.fetch;
  }
  if (ORIGINAL_ORT !== undefined) {
    globalThis.ort = ORIGINAL_ORT;
  } else {
    delete globalThis.ort;
  }
  if (ORIGINAL_INDEXEDDB !== undefined) {
    globalThis.indexedDB = ORIGINAL_INDEXEDDB;
  } else {
    delete globalThis.indexedDB;
  }
}

// Install mocks before importing the module under test.
installGlobalMocks();

// ---------------------------------------------------------------------------
// Import the module under test (after mocks are in place)
// ---------------------------------------------------------------------------

let PiperPlus;
let WebGPUSessionManager, ModelManager;
let AudioResult, StreamingTTSPipeline;

let importError = null;
try {
  const mod = await import('../../src/index.js');
  PiperPlus = mod.PiperPlus;
  WebGPUSessionManager = mod.WebGPUSessionManager;
  ModelManager = mod.ModelManager;
  AudioResult = mod.AudioResult;
  StreamingTTSPipeline = mod.StreamingTTSPipeline;
} catch (e) {
  importError = e;
}

const skip = PiperPlus == null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Epsilon for float comparisons. */
const FLOAT_EPSILON = 1e-3;

/**
 * Assert that two numbers are within epsilon of each other.
 * @param {number} actual
 * @param {number} expected
 * @param {string} [message]
 */
function assertCloseTo(actual, expected, message) {
  assert.ok(
    Math.abs(actual - expected) < FLOAT_EPSILON,
    `${message || 'assertCloseTo'}: expected ${expected}, got ${actual} (epsilon=${FLOAT_EPSILON})`
  );
}

/**
 * Build a PiperPlus instance with mocked internals that behaves as if
 * _init() completed successfully. This centralises all private-field
 * setup so individual tests never touch underscored properties directly.
 *
 * @param {Object} [overrides]
 * @param {Object} [overrides.config]       - config.json contents
 * @param {Object} [overrides.sessionRun]   - mock for session.run()
 * @param {Object} [overrides.phonemizer]   - mock phonemizer methods
 * @returns {PiperPlus}
 */
function createInitializedInstance(overrides = {}) {
  const instance = new PiperPlus();

  // Config — simulates what _init() reads from config.json
  const config = overrides.config ?? {
    phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
  };

  // Session — simulates the ONNX session created by _init()
  const sessionRunFn = overrides.sessionRun ?? (async (feeds) => {
    const inputLen =
      (feeds?.input?.data && feeds.input.data.length) ||
      (feeds?.input?.dims && feeds.input.dims[1]) ||
      5;
    const durData = new Float32Array(inputLen);
    for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
    return {
      output: { data: new Float32Array(100), dims: [1, 100] },
      durations: { data: durData, dims: [1, inputLen] },
    };
  });
  const session = {
    run: typeof sessionRunFn === 'function' && sessionRunFn.mock
      ? sessionRunFn
      : mock.fn(sessionRunFn),
    release: mock.fn(),
  };

  // Phonemizer mock — simulates CompositePhonemizer after _init()
  // Use >= 40 phoneme IDs to bypass short-text mitigation (Strategy A+B)
  const longPhonemeIds = new Array(45).fill(7);
  longPhonemeIds[0] = 1;   // BOS
  longPhonemeIds[44] = 2;  // EOS
  const defaultPhonemizer = {
    detectLanguage: mock.fn(() => 'ja'),
    encode: mock.fn((text, language) => ({
      phonemeIds: longPhonemeIds,
      prosodyFeatures: null,
    })),
    dispose: mock.fn(),
    supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
  };
  const phonemizer = { ...defaultPhonemizer, ...(overrides.phonemizer || {}) };

  // Wire up the instance as _init() would
  instance._config = config;
  instance._session = session;
  instance._phonemizer = phonemizer;
  instance._ort = globalThis.ort;
  instance._initialized = true;

  return instance;
}

// ===========================================================================
// 1. PiperPlus クラスの存在確認
// ===========================================================================

describe('PiperPlus クラスの存在確認', { skip }, () => {
  it('src/index.js からインポートできる', () => {
    assert.ok(PiperPlus, 'PiperPlus should be defined');
    assert.equal(typeof PiperPlus, 'function');
  });

  it('PiperPlus.initialize は静的関数である', () => {
    assert.equal(typeof PiperPlus.initialize, 'function');
  });

  it('synthesize メソッドを公開している', () => {
    assert.equal(typeof PiperPlus.prototype.synthesize, 'function');
  });

  it('synthesizeStreaming メソッドを公開している', () => {
    assert.equal(typeof PiperPlus.prototype.synthesizeStreaming, 'function');
  });

  it('dispose メソッドを公開している', () => {
    assert.equal(typeof PiperPlus.prototype.dispose, 'function');
  });

  it('未初期化の isInitialized は false を返す', () => {
    // Arrange
    const instance = new PiperPlus();

    // Act & Assert
    assert.equal(instance.isInitialized, false);
  });

  it('未初期化の config は null を返す', () => {
    // Arrange
    const instance = new PiperPlus();

    // Act & Assert
    assert.equal(instance.config, null);
  });
});

// ===========================================================================
// 2. 再エクスポートの確認
// ===========================================================================

describe('再エクスポートの確認', { skip }, () => {
  it('WebGPUSessionManager がエクスポートされている', () => {
    assert.ok(WebGPUSessionManager);
    assert.equal(typeof WebGPUSessionManager, 'function');
  });

  it('ModelManager がエクスポートされている', () => {
    assert.ok(ModelManager);
    assert.equal(typeof ModelManager, 'function');
  });

  it('AudioResult がエクスポートされている', () => {
    assert.ok(AudioResult);
    assert.equal(typeof AudioResult, 'function');
  });

  it('StreamingTTSPipeline がエクスポートされている', () => {
    assert.ok(StreamingTTSPipeline);
    assert.equal(typeof StreamingTTSPipeline, 'function');
  });
});

// ===========================================================================
// 3. PiperPlus.initialize バリデーション
// ===========================================================================

describe('PiperPlus.initialize バリデーション', { skip }, () => {
  // Guarantee global mocks are always restored even if a test throws.
  afterEach(() => {
    installGlobalMocks();
  });

  it('model オプション未指定でリジェクトされる', async () => {
    await assert.rejects(
      () => PiperPlus.initialize({ ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      }
    );
  });

  it('model が空文字列でリジェクトされる', async () => {
    await assert.rejects(
      () => PiperPlus.initialize({ model: '', ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      }
    );
  });

  it('モデル名が解決できない場合リジェクトされる', async () => {
    // Arrange — fetch returns 404 for model resolution
    const savedFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
      if (typeof url === 'string' && url.includes('api/models')) {
        return { ok: false, status: 404, statusText: 'Not Found' };
      }
      return savedFetch(url);
    };

    // Act & Assert
    await assert.rejects(
      () => PiperPlus.initialize({ model: 'nonexistent/model', ort: globalThis.ort }),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      }
    );
    // afterEach handles restoration
  });

  it('ort が利用不可の場合 onnxruntime-web エラーでリジェクトされる', async () => {
    // Arrange
    delete globalThis.ort;

    // Act & Assert
    await assert.rejects(
      () => PiperPlus.initialize({ model: 'test' }),
      (err) => {
        assert.ok(err instanceof Error);
        assert.ok(
          err.message.includes('onnxruntime-web'),
          `メッセージに onnxruntime-web が含まれること: "${err.message}"`
        );
        return true;
      }
    );
    // afterEach handles restoration
  });
});

// ===========================================================================
// 4. SynthesizeOptions デフォルト値
// ===========================================================================

describe('SynthesizeOptions デフォルト値', { skip }, () => {
  it('language 未指定時は自動検出にフォールバックする', async () => {
    // Arrange
    const detectLanguageFn = mock.fn(() => 'ja');
    const instance = createInitializedInstance({
      phonemizer: {
        detectLanguage: detectLanguageFn,
        encode: mock.fn((text, language) => ({
          phonemeIds: [1, 7, 2],
          prosodyFeatures: null,
        })),
        dispose: mock.fn(),
        supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
      },
    });

    // Act
    await instance.synthesize('test text');

    // Assert — detectLanguage was called (language was auto-detected)
    assert.equal(detectLanguageFn.mock.callCount(), 1);
  });

  it('noiseScale のデフォルトは 0.667', async () => {
    // Arrange
    let capturedScales = null;
    const instance = createInitializedInstance({
      sessionRun: async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: new Float32Array(100), dims: [1, 100] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });

    // Act
    await instance.synthesize('a');

    // Assert
    assert.ok(capturedScales, 'scales が session.run に渡されること');
    assertCloseTo(capturedScales[0], 0.667, 'noiseScale デフォルト');
  });

  it('lengthScale のデフォルトは 1.0', async () => {
    // Arrange
    let capturedScales = null;
    const instance = createInitializedInstance({
      sessionRun: async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: new Float32Array(100), dims: [1, 100] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });

    // Act
    await instance.synthesize('a');

    // Assert
    assert.ok(capturedScales, 'scales が session.run に渡されること');
    assertCloseTo(capturedScales[1], 1.0, 'lengthScale デフォルト');
  });

  it('noiseW のデフォルトは 0.8', async () => {
    // Arrange
    let capturedScales = null;
    const instance = createInitializedInstance({
      sessionRun: async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: new Float32Array(100), dims: [1, 100] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });

    // Act
    await instance.synthesize('a');

    // Assert
    assert.ok(capturedScales, 'scales が session.run に渡されること');
    assertCloseTo(capturedScales[2], 0.8, 'noiseW デフォルト');
  });
});

// ===========================================================================
// 5. config.inference によるデフォルト上書き
// ===========================================================================

describe('config.inference によるデフォルト上書き', { skip }, () => {
  /** Shared capture helper for this suite. */
  function createInstanceWithConfigInference() {
    let capturedScales = null;
    const instance = createInitializedInstance({
      config: {
        inference: { noise_scale: 0.5, length_scale: 1.2, noise_w: 0.6 },
        phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
      },
      sessionRun: async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: new Float32Array(100), dims: [1, 100] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });
    return { instance, getCapturedScales: () => capturedScales };
  }

  it('config.inference.noise_scale がハードコードデフォルトより優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigInference();

    // Act
    await instance.synthesize('a');

    // Assert
    assertCloseTo(getCapturedScales()[0], 0.5, 'noiseScale from config');
  });

  it('config.inference.length_scale がハードコードデフォルトより優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigInference();

    // Act
    await instance.synthesize('a');

    // Assert
    assertCloseTo(getCapturedScales()[1], 1.2, 'lengthScale from config');
  });

  it('config.inference.noise_w がハードコードデフォルトより優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigInference();

    // Act
    await instance.synthesize('a');

    // Assert
    assertCloseTo(getCapturedScales()[2], 0.6, 'noiseW from config');
  });
});

// ===========================================================================
// 6. 明示的オプションによる上書き
// ===========================================================================

describe('明示的オプションによる上書き', { skip }, () => {
  /** Shared capture helper for this suite. */
  function createInstanceWithConfigAndExplicit() {
    let capturedScales = null;
    const instance = createInitializedInstance({
      config: {
        inference: { noise_scale: 0.5, length_scale: 1.2, noise_w: 0.6 },
        phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
      },
      sessionRun: async (feeds) => {
        capturedScales = Array.from(feeds.scales.data);
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: new Float32Array(100), dims: [1, 100] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });
    return { instance, getCapturedScales: () => capturedScales };
  }

  it('noiseScale の明示的オプションが config より優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigAndExplicit();

    // Act
    await instance.synthesize('a', { noiseScale: 0.3, lengthScale: 0.9, noiseW: 0.4 });

    // Assert
    assertCloseTo(getCapturedScales()[0], 0.3, 'noiseScale from explicit option');
  });

  it('lengthScale の明示的オプションが config より優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigAndExplicit();

    // Act
    await instance.synthesize('a', { noiseScale: 0.3, lengthScale: 0.9, noiseW: 0.4 });

    // Assert
    assertCloseTo(getCapturedScales()[1], 0.9, 'lengthScale from explicit option');
  });

  it('noiseW の明示的オプションが config より優先される', async () => {
    // Arrange
    const { instance, getCapturedScales } = createInstanceWithConfigAndExplicit();

    // Act
    await instance.synthesize('a', { noiseScale: 0.3, lengthScale: 0.9, noiseW: 0.4 });

    // Assert
    assertCloseTo(getCapturedScales()[2], 0.4, 'noiseW from explicit option');
  });
});

// ===========================================================================
// 7. synthesize() 正常系 (ハッピーパス)
// ===========================================================================

describe('synthesize() 正常系', { skip }, () => {
  it('テキストから AudioResult を返す', async () => {
    // Arrange
    const expectedSamples = new Float32Array([0.1, 0.2, 0.3, -0.1, -0.2]);
    const instance = createInitializedInstance({
      config: {
        audio: { sample_rate: 22050 },
        phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
      },
      sessionRun: async (feeds) => {
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: expectedSamples, dims: [1, expectedSamples.length] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });

    // Act
    const result = await instance.synthesize('テスト');

    // Assert
    assert.ok(result instanceof AudioResult, '戻り値は AudioResult のインスタンスであること');
  });

  it('返された AudioResult に正しい sampleRate が設定される', async () => {
    // Arrange
    const instance = createInitializedInstance({
      config: {
        audio: { sample_rate: 44100 },
        phoneme_id_map: { _: [0], '^': [1], $: [2], a: [7] },
      },
    });

    // Act
    const result = await instance.synthesize('テスト');

    // Assert
    assert.equal(result.sampleRate, 44100);
  });

  it('返された AudioResult に音声サンプルが含まれる', async () => {
    // Arrange
    const expectedSamples = new Float32Array([0.5, -0.5, 0.25]);
    const instance = createInitializedInstance({
      sessionRun: async (feeds) => {
        const inputLen =
          (feeds?.input?.data && feeds.input.data.length) ||
          (feeds?.input?.dims && feeds.input.dims[1]) ||
          5;
        const durData = new Float32Array(inputLen);
        for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
        return {
          output: { data: expectedSamples, dims: [1, expectedSamples.length] },
          durations: { data: durData, dims: [1, inputLen] },
        };
      },
    });

    // Act
    const result = await instance.synthesize('テスト');

    // Assert
    assert.ok(result.samples instanceof Float32Array, 'samples は Float32Array であること');
    assert.equal(result.samples.length, expectedSamples.length, '出力サンプル数が一致すること');
  });

  it('phonemize から infer までのパイプラインが実行される', async () => {
    // Arrange — use >= 40 phoneme IDs to bypass short-text mitigation
    const pipelineIds = new Array(45).fill(7);
    pipelineIds[0] = 1;
    pipelineIds[44] = 2;
    const encodeFn = mock.fn((text, language) => ({
      phonemeIds: pipelineIds,
      prosodyFeatures: null,
    }));
    const sessionRunFn = mock.fn(async (feeds) => {
      const inputLen =
        (feeds?.input?.data && feeds.input.data.length) ||
        (feeds?.input?.dims && feeds.input.dims[1]) ||
        5;
      const durData = new Float32Array(inputLen);
      for (let i = 0; i < inputLen; i++) durData[i] = 5 + ((i * 3) % 10);
      return {
        output: { data: new Float32Array(100), dims: [1, 100] },
        durations: { data: durData, dims: [1, inputLen] },
      };
    });

    const instance = createInitializedInstance({
      sessionRun: sessionRunFn,
      phonemizer: {
        detectLanguage: mock.fn(() => 'ja'),
        encode: encodeFn,
        dispose: mock.fn(),
        supportedLanguages: ['en', 'zh', 'es', 'fr', 'pt'],
      },
    });

    // Act
    await instance.synthesize('こんにちは');

    // Assert — each stage of the pipeline was invoked
    assert.equal(encodeFn.mock.callCount(), 1, 'encode が呼ばれること');
    assert.equal(sessionRunFn.mock.callCount(), 1, 'session.run が呼ばれること');
  });
});

// ===========================================================================
// 8. dispose()
// ===========================================================================

describe('dispose()', { skip }, () => {
  it('未初期化インスタンスでも例外を投げない', () => {
    // Arrange
    const instance = new PiperPlus();

    // Act & Assert
    assert.doesNotThrow(() => instance.dispose());
  });

  it('二重 dispose でも例外を投げない', () => {
    // Arrange
    const instance = createInitializedInstance();

    // Act
    instance.dispose();

    // Assert
    assert.doesNotThrow(() => instance.dispose());
  });

  it('ONNX セッションの release() を呼び出す', () => {
    // Arrange
    const instance = createInitializedInstance();
    const session = instance._session; // capture ref before dispose nulls it

    // Act
    instance.dispose();

    // Assert
    assert.equal(session.release.mock.callCount(), 1);
  });

  it('dispose 後にセッションが null になる', () => {
    // Arrange
    const instance = createInitializedInstance();

    // Act
    instance.dispose();

    // Assert
    assert.equal(instance._session, null);
  });

  it('phonemizer の dispose() を呼び出す', () => {
    // Arrange
    const instance = createInitializedInstance();
    const phonemizer = instance._phonemizer; // capture ref before dispose nulls it

    // Act
    instance.dispose();

    // Assert
    assert.equal(phonemizer.dispose.mock.callCount(), 1);
  });

  it('dispose 後に _phonemizer が null になる', () => {
    // Arrange
    const instance = createInitializedInstance();

    // Act
    instance.dispose();

    // Assert
    assert.equal(instance._phonemizer, null);
  });

  it('dispose 後に isInitialized が false になる', () => {
    // Arrange
    const instance = createInitializedInstance();
    assert.equal(instance.isInitialized, true);

    // Act
    instance.dispose();

    // Assert
    assert.equal(instance.isInitialized, false);
  });

  it('release メソッドのないセッションでも例外を投げない', () => {
    // Arrange
    const instance = createInitializedInstance();
    instance._session = {}; // overwrite with no release()

    // Act & Assert
    assert.doesNotThrow(() => instance.dispose());
  });

  it('dispose 後の synthesize() はリジェクトされる', async () => {
    // Arrange
    const instance = createInitializedInstance();
    instance.dispose();

    // Act & Assert
    await assert.rejects(
      () => instance.synthesize('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// 9. synthesize() 入力バリデーション
// ===========================================================================

describe('synthesize() 入力バリデーション', { skip }, () => {
  let instance;

  beforeEach(() => {
    instance = createInitializedInstance();
  });

  it('空文字列でリジェクトされる', async () => {
    await assert.rejects(
      () => instance.synthesize(''),
      (err) => {
        assert.ok(err.message.includes('text'));
        return true;
      }
    );
  });

  it('null でリジェクトされる', async () => {
    await assert.rejects(
      () => instance.synthesize(null),
      (err) => {
        assert.ok(err instanceof Error);
        return true;
      }
    );
  });

  it('初期化前に呼び出すとリジェクトされる', async () => {
    // Arrange — raw uninitialized instance
    const raw = new PiperPlus();

    // Act & Assert
    await assert.rejects(
      () => raw.synthesize('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// 10. synthesizeStreaming() 入力バリデーション
// ===========================================================================

describe('synthesizeStreaming() 入力バリデーション', { skip }, () => {
  it('空文字列でリジェクトされる', async () => {
    // Arrange
    const instance = createInitializedInstance();

    // Act & Assert
    await assert.rejects(
      () => instance.synthesizeStreaming(''),
      (err) => {
        assert.ok(err.message.includes('text'));
        return true;
      }
    );
  });

  it('初期化前に呼び出すとリジェクトされる', async () => {
    // Arrange
    const raw = new PiperPlus();

    // Act & Assert
    await assert.rejects(
      () => raw.synthesizeStreaming('hello'),
      (err) => {
        assert.ok(err.message.includes('not initialized'));
        return true;
      }
    );
  });
});

// ===========================================================================
// インポートエラーの報告
// ===========================================================================

if (importError) {
  describe('import error', () => {
    it('should not have an import error', () => {
      assert.fail(`Failed to import src/index.js: ${importError.message}`);
    });
  });
}
