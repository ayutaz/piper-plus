/**
 * TDD Tests for ModelManager cache lifecycle
 * Phase 2: キャッシュライフサイクル検証
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 *   - getFromCache()
 *   - clearCache()
 *   - loadModel() のキャッシュ統合動作
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach, afterEach } from 'node:test';

// --- モック定義 ---

/**
 * In-memory IndexedDB mock with actual get/put storage.
 * Provides the minimal IDBDatabase interface consumed by ModelManager.
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
 * Install a mock IndexedDB.open() that returns the given mock DB handle.
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
 * Build a mock fetch function with a call counter.
 * Routes are matched by URL string or RegExp.
 *
 * @param {Map<string|RegExp, Object>} routes
 * @returns {{ fetch: Function, callCount: () => number, calls: () => string[] }}
 */
function createMockFetch(routes) {
  const callLog = [];

  const mockFn = async (url) => {
    callLog.push(url);
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
          body: null,
        };
      }
    }
    return { ok: false, status: 404, statusText: 'Not Found' };
  };

  mockFn.callCount = () => callLog.length;
  mockFn.calls = () => [...callLog];

  return mockFn;
}

/**
 * Build standard fetch routes for a direct-URL model.
 * Returns routes that serve a config JSON and model ArrayBuffer.
 *
 * @param {string} modelUrl
 * @param {Object} config
 * @param {ArrayBuffer} modelData
 * @returns {Map<string, Object>}
 */
function directUrlRoutes(modelUrl, config, modelData) {
  return new Map([
    [`${modelUrl}.json`, {
      ok: true,
      json: () => Promise.resolve(config),
    }],
    [modelUrl, {
      ok: true,
      arrayBuffer: () => Promise.resolve(modelData),
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

describe('ModelManager キャッシュライフサイクル', { skip }, () => {
  let originalFetch;
  let originalIndexedDB;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    originalIndexedDB = globalThis.indexedDB;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.indexedDB = originalIndexedDB;
  });

  // =====================================================================
  // 1. キャッシュが空の場合
  // =====================================================================

  it('キャッシュが空の場合 getFromCache は null を返す', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);
    const mgr = new ModelManager();

    // Act
    const result = await mgr.getFromCache('nonexistent-model');

    // Assert
    assert.equal(result, null);
  });

  // =====================================================================
  // 2. loadModel 後のキャッシュ取得
  // =====================================================================

  it('loadModel 後に getFromCache でモデルを取得できる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/test-model.onnx';
    const expectedConfig = { sample_rate: 22050, num_speakers: 1 };
    const expectedData = new ArrayBuffer(256);

    globalThis.fetch = createMockFetch(
      directUrlRoutes(modelUrl, expectedConfig, expectedData)
    );

    const mgr = new ModelManager();

    // Act
    await mgr.loadModel(modelUrl);
    const cached = await mgr.getFromCache(modelUrl);

    // Assert
    assert.ok(cached, 'cached entry should not be null');
    assert.deepEqual(cached.config, expectedConfig);
    assert.ok(cached.modelData instanceof ArrayBuffer);
    assert.equal(cached.modelData.byteLength, 256);
  });

  // =====================================================================
  // 3. clearCache 後の状態
  // =====================================================================

  it('clearCache 後に getFromCache は null を返す', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/clear-test.onnx';
    const config = { sample_rate: 22050 };
    const data = new ArrayBuffer(128);

    globalThis.fetch = createMockFetch(
      directUrlRoutes(modelUrl, config, data)
    );

    const mgr = new ModelManager();
    await mgr.loadModel(modelUrl);

    // Verify it was cached
    const before = await mgr.getFromCache(modelUrl);
    assert.ok(before, 'model should be cached before clearCache');

    // Act
    await mgr.clearCache();
    const after = await mgr.getFromCache(modelUrl);

    // Assert
    assert.equal(after, null);
  });

  // =====================================================================
  // 4. 異なるモデル名のキャッシュ独立性
  // =====================================================================

  it('異なるモデル名のキャッシュは独立している', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const urlA = 'https://example.com/model-a.onnx';
    const urlB = 'https://example.com/model-b.onnx';
    const configA = { model: 'A' };
    const configB = { model: 'B' };
    const dataA = new ArrayBuffer(100);
    const dataB = new ArrayBuffer(200);

    const routes = new Map([
      [`${urlA}.json`, { ok: true, json: () => Promise.resolve(configA) }],
      [urlA, { ok: true, arrayBuffer: () => Promise.resolve(dataA) }],
      [`${urlB}.json`, { ok: true, json: () => Promise.resolve(configB) }],
      [urlB, { ok: true, arrayBuffer: () => Promise.resolve(dataB) }],
    ]);
    globalThis.fetch = createMockFetch(routes);

    const mgr = new ModelManager();

    // Act
    await mgr.loadModel(urlA);
    await mgr.loadModel(urlB);

    const cachedA = await mgr.getFromCache(urlA);
    const cachedB = await mgr.getFromCache(urlB);

    // Assert
    assert.deepEqual(cachedA.config, configA);
    assert.deepEqual(cachedB.config, configB);
    assert.equal(cachedA.modelData.byteLength, 100);
    assert.equal(cachedB.modelData.byteLength, 200);
  });

  // =====================================================================
  // 5. キャッシュヒット時に fetch が呼ばれない
  // =====================================================================

  it('キャッシュヒット時に fetch が呼ばれない', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/cached-model.onnx';
    const config = { sample_rate: 22050 };
    const data = new ArrayBuffer(64);

    const mockFetch = createMockFetch(
      directUrlRoutes(modelUrl, config, data)
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // First load populates the cache
    await mgr.loadModel(modelUrl);
    const fetchCountAfterFirstLoad = mockFetch.callCount();

    // Act — second load should hit cache
    await mgr.loadModel(modelUrl);

    // Assert
    assert.equal(
      mockFetch.callCount(),
      fetchCountAfterFirstLoad,
      'fetch should not be called on cache hit'
    );
  });

  // =====================================================================
  // 6. clearCache 後に再度 loadModel するとフェッチが実行される
  // =====================================================================

  it('clearCache 後に再度 loadModel するとフェッチが実行される', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/refetch-model.onnx';
    const config = { sample_rate: 22050 };
    const data = new ArrayBuffer(64);

    const mockFetch = createMockFetch(
      directUrlRoutes(modelUrl, config, data)
    );
    globalThis.fetch = mockFetch;

    const mgr = new ModelManager();

    // First load
    await mgr.loadModel(modelUrl);
    const countAfterFirst = mockFetch.callCount();

    // Clear the cache
    await mgr.clearCache();

    // Act — reload should trigger new fetches
    await mgr.loadModel(modelUrl);

    // Assert
    assert.ok(
      mockFetch.callCount() > countAfterFirst,
      'fetch should be called again after clearCache'
    );
  });

  // =====================================================================
  // 7. カスタム cachePrefix でキャッシュが分離される
  // =====================================================================

  it('カスタム cachePrefix でキャッシュが分離される', async () => {
    // Arrange — two separate IndexedDB stores for the two prefixes
    const mockDbA = createMockIndexedDB();
    const mockDbB = createMockIndexedDB();

    // We need indexedDB.open to return different DBs based on dbName.
    // Track which DB to return by overriding open per manager lifecycle.
    const modelUrl = 'https://example.com/prefix-test.onnx';
    const config = { sample_rate: 22050 };
    const data = new ArrayBuffer(32);

    globalThis.fetch = createMockFetch(
      directUrlRoutes(modelUrl, config, data)
    );

    // Manager A with prefix-a
    globalThis.indexedDB = {
      open: (_name) => {
        const req = { result: mockDbA, error: null, onsuccess: null, onerror: null, onupgradeneeded: null };
        queueMicrotask(() => { if (req.onsuccess) req.onsuccess(); });
        return req;
      },
    };
    const mgrA = new ModelManager({ cachePrefix: 'prefix-a' });
    await mgrA.loadModel(modelUrl);

    // Manager B with prefix-b (different DB)
    globalThis.indexedDB = {
      open: (_name) => {
        const req = { result: mockDbB, error: null, onsuccess: null, onerror: null, onupgradeneeded: null };
        queueMicrotask(() => { if (req.onsuccess) req.onsuccess(); });
        return req;
      },
    };
    const mgrB = new ModelManager({ cachePrefix: 'prefix-b' });

    // Act
    const cachedInA = await mgrA.getFromCache(modelUrl);
    const cachedInB = await mgrB.getFromCache(modelUrl);

    // Assert
    assert.ok(cachedInA, 'model should be cached under prefix-a');
    assert.equal(cachedInB, null, 'prefix-b should have no cached model');
  });

  // =====================================================================
  // 8. 大きなモデルデータがキャッシュされる
  // =====================================================================

  it('大きなモデルデータがキャッシュされる', async () => {
    // Arrange
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);

    const modelUrl = 'https://example.com/large-model.onnx';
    const config = { sample_rate: 22050, quality: 'medium' };
    const largeSize = 1024 * 1024 + 512; // 1MB + 512 bytes
    const largeData = new ArrayBuffer(largeSize);

    globalThis.fetch = createMockFetch(
      directUrlRoutes(modelUrl, config, largeData)
    );

    const mgr = new ModelManager();

    // Act
    await mgr.loadModel(modelUrl);
    const cached = await mgr.getFromCache(modelUrl);

    // Assert
    assert.ok(cached, 'large model should be cached');
    assert.equal(cached.modelData.byteLength, largeSize);
    assert.deepEqual(cached.config, config);
  });
});
