/**
 * TDD Tests for ModelManager.loadModel() success cases
 * Phase 2: モデルロード成功パス
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 */

import { strict as assert } from 'assert';
import { describe, it, afterEach } from 'node:test';

// --- モック定義 ---

/** サンプル config.json (全テスト共通) */
const SAMPLE_CONFIG = {
  audio: { sample_rate: 22050 },
  num_speakers: 1,
  num_symbols: 173,
  espeak: { voice: 'ja' },
  language: { code: 'ja' },
};

/** サンプル ONNX モデルデータ (8 バイトのダミー) */
const SAMPLE_MODEL_BUFFER = new ArrayBuffer(8);

/**
 * Minimal mock for IndexedDB that satisfies ModelManager._getDb().
 * Stores values in a plain Map keyed by the IDBObjectStore key argument.
 */
function createMockIndexedDB() {
  const store = new Map();

  return {
    transaction(_storeName, _mode) {
      return {
        objectStore(_name) {
          return {
            get(key) {
              return wrapMockResult(store.get(key) ?? undefined);
            },
            put(value, key) {
              store.set(key, value);
              return wrapMockResult(undefined);
            },
            clear() {
              store.clear();
              return wrapMockResult(undefined);
            },
          };
        },
      };
    },
    _store: store,
  };
}

/** Turn a synchronous result into an IDBRequest-shaped object. */
function wrapMockResult(result) {
  const req = { result, error: null, onsuccess: null, onerror: null };
  queueMicrotask(() => { if (req.onsuccess) req.onsuccess(); });
  return req;
}

/**
 * Stub globalThis.indexedDB.open() so that openDatabase() inside
 * model-manager.js receives our mock DB handle.
 */
function installIndexedDBMock(mockDb) {
  const fakeOpen = (_name, _version) => {
    const req = { result: mockDb, error: null, onsuccess: null, onerror: null, onupgradeneeded: null };
    queueMicrotask(() => { if (req.onsuccess) req.onsuccess(); });
    return req;
  };
  globalThis.indexedDB = { open: fakeOpen };
}

/**
 * Build a mock globalThis.fetch that returns pre-configured responses
 * based on URL matching.  Records all fetched URLs for assertion.
 *
 * @param {Map<string|RegExp, Object>} routes
 * @returns {{fetch: Function, calledUrls: string[]}}
 */
function createMockFetch(routes) {
  const calledUrls = [];

  const fetchFn = async (url) => {
    calledUrls.push(url);
    for (const [pattern, handler] of routes) {
      const matches = typeof pattern === 'string'
        ? url === pattern
        : pattern.test(url);
      if (matches) {
        return {
          ok: handler.ok ?? true,
          status: handler.status ?? 200,
          statusText: handler.statusText ?? 'OK',
          headers: handler.headers ?? new Map(),
          json: handler.json ?? (() => Promise.reject(new Error('no json handler'))),
          arrayBuffer: handler.arrayBuffer ?? (() => Promise.resolve(new ArrayBuffer(0))),
          body: handler.body ?? null,
        };
      }
    }
    return { ok: false, status: 404, statusText: 'Not Found' };
  };

  return { fetch: fetchFn, calledUrls };
}

/**
 * Build a standard set of routes for HuggingFace-based model loading.
 *
 * @param {Object}      [options]
 * @param {string[]}    [options.siblings]       - filenames in the HF repo
 * @param {Object}      [options.config]         - config.json content
 * @param {ArrayBuffer}  [options.modelBuffer]   - ONNX model data
 * @returns {Map<string|RegExp, Object>}
 */
function createHuggingFaceRoutes(options = {}) {
  const siblings = (options.siblings || ['model.onnx', 'config.json']).map((f) => ({ rfilename: f }));
  const config = options.config || SAMPLE_CONFIG;
  const modelBuffer = options.modelBuffer || SAMPLE_MODEL_BUFFER;

  return new Map([
    [/huggingface\.co\/api\/models\//, {
      ok: true,
      json: () => Promise.resolve({ siblings }),
    }],
    [/huggingface\.co\/.*\/resolve\/main\/(?:.*\.onnx\.json|config\.json)$/, {
      ok: true,
      json: () => Promise.resolve(config),
    }],
    [/huggingface\.co\/.*\/resolve\/main\/.*\.onnx$/, {
      ok: true,
      arrayBuffer: () => Promise.resolve(modelBuffer),
    }],
  ]);
}

/**
 * Build routes for direct-URL model loading.
 *
 * @param {string}       modelUrl
 * @param {Object}      [options]
 * @param {Object}      [options.config]
 * @param {ArrayBuffer}  [options.modelBuffer]
 * @returns {Map<string, Object>}
 */
function createDirectUrlRoutes(modelUrl, options = {}) {
  const config = options.config || SAMPLE_CONFIG;
  const modelBuffer = options.modelBuffer || SAMPLE_MODEL_BUFFER;

  return new Map([
    [modelUrl + '.json', {
      ok: true,
      json: () => Promise.resolve(config),
    }],
    [modelUrl, {
      ok: true,
      arrayBuffer: () => Promise.resolve(modelBuffer),
    }],
  ]);
}

// --- Import with TDD skip guard ---

let ModelManager;
try {
  const mod = await import('../../src/model-manager.js');
  ModelManager = mod.ModelManager || mod.default;
} catch {
  ModelManager = null;
}

const skip = ModelManager === null;

// --- Tests ---

describe('ModelManager.loadModel() 成功ケース', { skip }, () => {
  let originalFetch;
  let originalIndexedDB;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.indexedDB = originalIndexedDB;
  });

  // Save originals before anything else runs.
  // (Using a self-executing block since beforeEach re-runs per test;
  //  we capture once at module level and restore in afterEach.)
  originalFetch = globalThis.fetch;
  originalIndexedDB = globalThis.indexedDB;

  // =====================================================================
  // 1. レジストリショートカットでモデルをロードできる
  // =====================================================================

  it('レジストリショートカットでモデルをロードできる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const { fetch: mockFetch } = createMockFetch(
      createHuggingFaceRoutes({ siblings: ['tsukuyomi.onnx', 'config.json'] })
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('tsukuyomi');

    // Assert
    assert.ok(result, 'loadModel should return a result');
    assert.ok(result.modelData instanceof ArrayBuffer, 'modelData should be an ArrayBuffer');
    assert.ok(result.config, 'config should be present');
    assert.equal(result.config.num_symbols, 173);
  });

  // =====================================================================
  // 2. HuggingFace リポジトリ名でモデルをロードできる
  // =====================================================================

  it('HuggingFace リポジトリ名でモデルをロードできる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const { fetch: mockFetch, calledUrls } = createMockFetch(
      createHuggingFaceRoutes({ siblings: ['model-fp16.onnx', 'README.md', 'config.json'] })
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('ayousanz/piper-plus-tsukuyomi-chan');

    // Assert
    assert.ok(result.modelData, 'modelData should be present');
    assert.ok(result.config, 'config should be present');

    // Verify the HuggingFace API was queried
    const apiCall = calledUrls.find((u) => u.includes('huggingface.co/api/models/'));
    assert.ok(apiCall, 'HuggingFace API should have been queried');
  });

  // =====================================================================
  // 3. 直接 URL でモデルをロードできる
  // =====================================================================

  it('直接 URL でモデルをロードできる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/model.onnx';
    const { fetch: mockFetch, calledUrls } = createMockFetch(
      createDirectUrlRoutes(modelUrl)
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel(modelUrl);

    // Assert
    assert.ok(result.modelData, 'modelData should be present');
    assert.ok(result.config, 'config should be present');

    // Direct URL should NOT query the HuggingFace API
    const apiCall = calledUrls.find((u) => u.includes('huggingface.co/api/'));
    assert.equal(apiCall, undefined, 'HuggingFace API should not be queried for direct URLs');

    // Should have fetched both the model and config URLs
    assert.ok(calledUrls.includes(modelUrl), 'model URL should be fetched');
    assert.ok(calledUrls.includes(modelUrl + '.json'), 'config URL should be fetched');
  });

  // =====================================================================
  // 4. loadModel が config と modelBuffer を返す
  // =====================================================================

  it('loadModel が config と modelData を返す', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const customConfig = {
      audio: { sample_rate: 22050 },
      num_speakers: 571,
      num_symbols: 173,
      language: { code: 'ja' },
      speaker_id_map: { speaker_0: 0 },
    };
    const modelBuffer = new ArrayBuffer(1024);

    const { fetch: mockFetch } = createMockFetch(
      createDirectUrlRoutes('https://example.com/test.onnx', {
        config: customConfig,
        modelBuffer,
      })
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('https://example.com/test.onnx');

    // Assert -- verify return value structure
    assert.ok('modelData' in result, 'result should have modelData property');
    assert.ok('config' in result, 'result should have config property');
    assert.equal(Object.keys(result).length, 2, 'result should have exactly two properties');

    // Verify modelData
    assert.ok(result.modelData instanceof ArrayBuffer, 'modelData should be an ArrayBuffer');
    assert.equal(result.modelData.byteLength, 1024, 'modelData should match the mock buffer size');

    // Verify config content
    assert.equal(result.config.num_speakers, 571);
    assert.equal(result.config.num_symbols, 173);
    assert.equal(result.config.audio.sample_rate, 22050);
    assert.deepEqual(result.config.speaker_id_map, { speaker_0: 0 });
  });

  // =====================================================================
  // 5. fp16 モデルが存在する場合はそちらが優先される
  // =====================================================================

  it('fp16 モデルが存在する場合はそちらが優先される', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const fp16Buffer = new ArrayBuffer(512);
    const regularBuffer = new ArrayBuffer(1024);

    // Return both fp16 and regular .onnx in siblings
    const routes = new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [
            { rfilename: 'README.md' },
            { rfilename: 'tsukuyomi-medium.onnx' },
            { rfilename: 'tsukuyomi-medium-fp16.onnx' },
            { rfilename: 'config.json' },
          ],
        }),
      }],
      [/config\.json$/, {
        ok: true,
        json: () => Promise.resolve(SAMPLE_CONFIG),
      }],
      [/fp16\.onnx$/, {
        ok: true,
        arrayBuffer: () => Promise.resolve(fp16Buffer),
      }],
      [/medium\.onnx$/, {
        ok: true,
        arrayBuffer: () => Promise.resolve(regularBuffer),
      }],
    ]);

    const { fetch: mockFetch, calledUrls } = createMockFetch(routes);
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('ayousanz/piper-plus-tsukuyomi-chan');

    // Assert -- the fp16 file should have been selected
    const modelFetchUrl = calledUrls.find(
      (u) => u.includes('/resolve/main/') && u.endsWith('.onnx') && !u.endsWith('.onnx.json')
    );
    assert.ok(modelFetchUrl, 'a model URL should have been fetched');
    assert.ok(modelFetchUrl.includes('fp16'), 'fp16 model should be preferred');
    assert.equal(result.modelData.byteLength, 512, 'modelData should match fp16 buffer size');
  });

  // =====================================================================
  // 6. 2回目のロードでキャッシュが使用される
  // =====================================================================

  it('2回目のロードでキャッシュが使用される', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    let fetchCallCount = 0;
    const routes = createDirectUrlRoutes('https://example.com/cached.onnx');
    const wrappedRoutes = new Map();
    for (const [pattern, handler] of routes) {
      wrappedRoutes.set(pattern, {
        ...handler,
        json: handler.json
          ? () => { fetchCallCount++; return handler.json(); }
          : undefined,
        arrayBuffer: handler.arrayBuffer
          ? () => { fetchCallCount++; return handler.arrayBuffer(); }
          : undefined,
      });
    }

    const { fetch: mockFetch } = createMockFetch(wrappedRoutes);
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act -- first call fetches from network
    const result1 = await mgr.loadModel('https://example.com/cached.onnx');
    const fetchCountAfterFirst = fetchCallCount;

    // Act -- second call should use cache
    const result2 = await mgr.loadModel('https://example.com/cached.onnx');
    const fetchCountAfterSecond = fetchCallCount;

    // Assert
    assert.ok(result1.modelData, 'first load should return modelData');
    assert.ok(result2.modelData, 'second load should return modelData');
    assert.ok(result2.config, 'second load should return config');

    // No additional fetch calls on the second load
    assert.equal(
      fetchCountAfterSecond,
      fetchCountAfterFirst,
      'second loadModel should not trigger any additional fetch calls'
    );
  });

  // =====================================================================
  // 7. onProgress コールバックが呼ばれる
  // =====================================================================

  it('onProgress コールバックが呼ばれる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const totalSize = 1024;
    const chunkSize = 256;
    const numChunks = totalSize / chunkSize;

    const modelUrl = 'https://example.com/progress-model.onnx';

    // Build a ReadableStream body that delivers data in chunks
    const routes = new Map([
      [modelUrl + '.json', {
        ok: true,
        json: () => Promise.resolve(SAMPLE_CONFIG),
      }],
      [modelUrl, {
        ok: true,
        headers: new Map([['Content-Length', String(totalSize)]]),
        // Provide a body with a getReader() to trigger the progress path
        body: {
          getReader() {
            let bytesDelivered = 0;
            return {
              async read() {
                if (bytesDelivered >= totalSize) {
                  return { done: true, value: undefined };
                }
                const chunk = new Uint8Array(chunkSize);
                chunk.fill(0xAA);
                bytesDelivered += chunkSize;
                return { done: false, value: chunk };
              },
            };
          },
        },
        // arrayBuffer fallback should not be called when body is present
        arrayBuffer: () => { throw new Error('should not call arrayBuffer when body exists'); },
      }],
    ]);

    const { fetch: mockFetch } = createMockFetch(routes);
    globalThis.fetch = mockFetch;

    const progressEvents = [];
    const onProgress = (event) => {
      progressEvents.push({ ...event });
    };

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel(modelUrl, { onProgress });

    // Assert
    assert.ok(result.modelData, 'loadModel should succeed');
    assert.ok(progressEvents.length > 0, 'onProgress should have been called at least once');
    assert.equal(progressEvents.length, numChunks, `onProgress should be called ${numChunks} times`);

    // Verify progress events are monotonically increasing
    for (let i = 1; i < progressEvents.length; i++) {
      assert.ok(
        progressEvents[i].loaded > progressEvents[i - 1].loaded,
        'loaded bytes should increase with each progress event'
      );
    }

    // Verify the last event has full data
    const lastEvent = progressEvents[progressEvents.length - 1];
    assert.equal(lastEvent.loaded, totalSize, 'final loaded should equal total size');
    assert.equal(lastEvent.total, totalSize, 'total should be reported from Content-Length');
    assert.equal(lastEvent.percentage, 100, 'final percentage should be 100');
  });

  // =====================================================================
  // 8. config.json のパースに成功する
  // =====================================================================

  it('config.json のパースに成功する', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const detailedConfig = {
      audio: {
        sample_rate: 22050,
        quality: 'medium',
      },
      num_speakers: 1,
      num_symbols: 173,
      num_languages: 6,
      espeak: { voice: 'ja' },
      language: { code: 'ja' },
      language_id_map: {
        ja: 0,
        en: 1,
        zh: 2,
        es: 3,
        fr: 4,
        pt: 5,
      },
      phoneme_id_map: {
        '_': [0],
        '^': [1],
        '$': [2],
      },
      inference: {
        noise_scale: 0.667,
        length_scale: 1.0,
        noise_w: 0.8,
      },
    };

    const { fetch: mockFetch } = createMockFetch(
      createDirectUrlRoutes('https://example.com/config-test.onnx', {
        config: detailedConfig,
      })
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('https://example.com/config-test.onnx');

    // Assert -- config is parsed as a full object, not a string
    assert.equal(typeof result.config, 'object', 'config should be an object');
    assert.notEqual(result.config, null, 'config should not be null');

    // Verify nested structures are preserved
    assert.equal(result.config.audio.sample_rate, 22050);
    assert.equal(result.config.audio.quality, 'medium');
    assert.equal(result.config.num_languages, 6);

    // Verify language_id_map
    assert.deepEqual(result.config.language_id_map, {
      ja: 0, en: 1, zh: 2, es: 3, fr: 4, pt: 5,
    });

    // Verify phoneme_id_map arrays
    assert.deepEqual(result.config.phoneme_id_map['_'], [0]);
    assert.deepEqual(result.config.phoneme_id_map['^'], [1]);

    // Verify inference params
    assert.equal(result.config.inference.noise_scale, 0.667);
    assert.equal(result.config.inference.length_scale, 1.0);
    assert.equal(result.config.inference.noise_w, 0.8);
  });

  // =====================================================================
  // 9. HF リポジトリが config.json のみの場合にロードできる
  // =====================================================================

  it('HF リポジトリが config.json のみ（サイドカーなし）でロードできる', async () => {
    // Arrange — 実際の ayousanz/piper-plus-tsukuyomi-chan と同じ構造
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const customConfig = { audio: { sample_rate: 22050 }, num_speakers: 1 };

    const routes = new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [
            { rfilename: 'tsukuyomi-chan-6lang-fp16.onnx' },
            { rfilename: 'config.json' },
            { rfilename: 'README.md' },
          ],
        }),
      }],
      [/resolve\/main\/config\.json$/, {
        ok: true,
        json: () => Promise.resolve(customConfig),
      }],
      [/resolve\/main\/.*\.onnx$/, {
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(64)),
      }],
    ]);

    const { fetch: mockFetch, calledUrls } = createMockFetch(routes);
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel('ayousanz/piper-plus-tsukuyomi-chan');

    // Assert
    assert.ok(result.modelData instanceof ArrayBuffer);
    assert.deepEqual(result.config, customConfig);

    // config.json が取得されていることを確認
    const configFetch = calledUrls.find((u) => u.includes('/resolve/main/config.json'));
    assert.ok(configFetch, 'config.json should have been fetched');
  });

  // =====================================================================
  // 10. 直接 URL で primary config が 404 の場合フォールバックする
  // =====================================================================

  it('直接 URL で primary config 404 時に config.json にフォールバックする', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const customConfig = { audio: { sample_rate: 22050 }, num_speakers: 1 };
    const modelUrl = 'https://example.com/models/my-model.onnx';

    const routes = new Map([
      // Primary config URL returns 404
      [modelUrl + '.json', {
        ok: false,
        status: 404,
        statusText: 'Not Found',
      }],
      // Fallback config.json succeeds
      ['https://example.com/models/config.json', {
        ok: true,
        json: () => Promise.resolve(customConfig),
      }],
      [modelUrl, {
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(128)),
      }],
    ]);

    const { fetch: mockFetch, calledUrls } = createMockFetch(routes);
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // Act
    const result = await mgr.loadModel(modelUrl);

    // Assert
    assert.ok(result.modelData instanceof ArrayBuffer);
    assert.deepEqual(result.config, customConfig);

    // 両方のconfig URLが試行されたことを確認
    assert.ok(calledUrls.includes(modelUrl + '.json'), 'primary config URL should be tried first');
    assert.ok(calledUrls.includes('https://example.com/models/config.json'), 'fallback config.json should be tried');
  });
});
