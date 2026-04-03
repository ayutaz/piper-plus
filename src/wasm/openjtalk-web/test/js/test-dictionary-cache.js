/**
 * Tests for ModelManager dictionary cache methods
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 *   - getDictionaryFromCache(key)
 *   - cacheDictionary(key, data)
 *   - fetchAndCacheDictionary(url, key, options)
 *
 * IndexedDB の 'dictionaries' ストアを使用した辞書キャッシュ機能を検証する。
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// --- モック定義 ---

/**
 * In-memory IndexedDB mock with separate stores for 'models' and 'dictionaries'.
 * The real openDatabase() creates both object stores in onupgradeneeded.
 */
function createMockIndexedDB() {
  const stores = {
    models: new Map(),
    dictionaries: new Map(),
  };

  return {
    transaction(storeNames, _mode) {
      return {
        objectStore(name) {
          // Pick the correct backing Map based on the store name.
          const backingStore = stores[name] || stores.models;
          return {
            get(key) {
              return wrapMockResult(backingStore.get(key) ?? undefined);
            },
            put(value, key) {
              backingStore.set(key, value);
              return wrapMockResult(undefined);
            },
            clear() {
              backingStore.clear();
              return wrapMockResult(undefined);
            },
          };
        },
      };
    },
    _stores: stores,
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
 * @returns {{ fetch: Function, calledUrls: string[] }}
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

describe('ModelManager 辞書キャッシュ', { skip }, () => {
  let originalFetch;
  let originalIndexedDB;
  let mockDb;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    originalIndexedDB = globalThis.indexedDB;

    mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.indexedDB = originalIndexedDB;
  });

  // =====================================================================
  // 1. getDictionaryFromCache — キャッシュ未存在時に null を返す
  // =====================================================================

  describe('getDictionaryFromCache()', () => {
    it('キャッシュ未存在時に null を返す', async () => {
      const mgr = new ModelManager();

      const result = await mgr.getDictionaryFromCache('nonexistent-dict');

      assert.equal(result, null);
    });

    it('キャッシュ済み辞書のデータを返す', async () => {
      // Pre-populate the dictionaries store
      const dictData = new ArrayBuffer(512);
      mockDb._stores.dictionaries.set('naist-jdic-v1', {
        data: dictData,
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();

      const result = await mgr.getDictionaryFromCache('naist-jdic-v1');

      assert.ok(result instanceof ArrayBuffer, 'should return an ArrayBuffer');
      assert.equal(result.byteLength, 512);
      assert.equal(result, dictData);
    });

    it('異なるキーは独立している', async () => {
      const dataA = new ArrayBuffer(100);
      const dataB = new ArrayBuffer(200);
      mockDb._stores.dictionaries.set('dict-a', { data: dataA, timestamp: Date.now() });
      mockDb._stores.dictionaries.set('dict-b', { data: dataB, timestamp: Date.now() });

      const mgr = new ModelManager();

      const resultA = await mgr.getDictionaryFromCache('dict-a');
      const resultB = await mgr.getDictionaryFromCache('dict-b');

      assert.equal(resultA.byteLength, 100);
      assert.equal(resultB.byteLength, 200);
    });

    it('存在するキーと存在しないキーを混在で問い合わせできる', async () => {
      mockDb._stores.dictionaries.set('exists', {
        data: new ArrayBuffer(64),
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();

      const found = await mgr.getDictionaryFromCache('exists');
      const missing = await mgr.getDictionaryFromCache('missing');

      assert.ok(found instanceof ArrayBuffer);
      assert.equal(missing, null);
    });
  });

  // =====================================================================
  // 2. cacheDictionary — 正常にデータを保存できる
  // =====================================================================

  describe('cacheDictionary()', () => {
    it('辞書データを保存して取得できる', async () => {
      const mgr = new ModelManager();
      const dictData = new ArrayBuffer(1024);

      await mgr.cacheDictionary('naist-jdic-v1', dictData);

      const result = await mgr.getDictionaryFromCache('naist-jdic-v1');
      assert.ok(result instanceof ArrayBuffer);
      assert.equal(result.byteLength, 1024);
    });

    it('同一キーへの上書き保存ができる', async () => {
      const mgr = new ModelManager();
      const data1 = new ArrayBuffer(100);
      const data2 = new ArrayBuffer(200);

      await mgr.cacheDictionary('dict-key', data1);
      await mgr.cacheDictionary('dict-key', data2);

      const result = await mgr.getDictionaryFromCache('dict-key');
      assert.equal(result.byteLength, 200, 'should return the overwritten data');
    });

    it('複数キーにそれぞれ保存できる', async () => {
      const mgr = new ModelManager();
      const dataA = new ArrayBuffer(64);
      const dataB = new ArrayBuffer(128);

      await mgr.cacheDictionary('dict-a', dataA);
      await mgr.cacheDictionary('dict-b', dataB);

      const resultA = await mgr.getDictionaryFromCache('dict-a');
      const resultB = await mgr.getDictionaryFromCache('dict-b');

      assert.equal(resultA.byteLength, 64);
      assert.equal(resultB.byteLength, 128);
    });

    it('空の ArrayBuffer を保存できる', async () => {
      const mgr = new ModelManager();
      const emptyData = new ArrayBuffer(0);

      await mgr.cacheDictionary('empty-dict', emptyData);

      const result = await mgr.getDictionaryFromCache('empty-dict');
      assert.ok(result instanceof ArrayBuffer);
      assert.equal(result.byteLength, 0);
    });

    it('大きな辞書データを保存できる', async () => {
      const mgr = new ModelManager();
      const largeSize = 2 * 1024 * 1024; // 2 MB
      const largeData = new ArrayBuffer(largeSize);

      await mgr.cacheDictionary('large-dict', largeData);

      const result = await mgr.getDictionaryFromCache('large-dict');
      assert.equal(result.byteLength, largeSize);
    });
  });

  // =====================================================================
  // 3. fetchAndCacheDictionary — キャッシュヒット時は fetch しない
  // =====================================================================

  describe('fetchAndCacheDictionary()', () => {
    it('キャッシュ存在時は fetch せずキャッシュから返す', async () => {
      // Pre-populate the dictionaries store
      const cachedData = new ArrayBuffer(256);
      mockDb._stores.dictionaries.set('cached-dict', {
        data: cachedData,
        timestamp: Date.now(),
      });

      const { fetch: mockFetch, calledUrls } = createMockFetch(new Map([
        ['https://example.com/dict.tar.gz', {
          ok: true,
          arrayBuffer: () => Promise.resolve(new ArrayBuffer(512)),
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      const result = await mgr.fetchAndCacheDictionary(
        'https://example.com/dict.tar.gz',
        'cached-dict',
      );

      assert.ok(result instanceof ArrayBuffer);
      assert.equal(result.byteLength, 256, 'should return the cached data, not fetched data');
      assert.equal(calledUrls.length, 0, 'fetch should not have been called');
    });

    it('キャッシュ未存在時は fetch してキャッシュに保存して返す', async () => {
      const fetchedData = new ArrayBuffer(768);
      const { fetch: mockFetch, calledUrls } = createMockFetch(new Map([
        ['https://example.com/naist-jdic.tar.gz', {
          ok: true,
          arrayBuffer: () => Promise.resolve(fetchedData),
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      const result = await mgr.fetchAndCacheDictionary(
        'https://example.com/naist-jdic.tar.gz',
        'naist-jdic-v1',
      );

      // Verify the data was returned
      assert.ok(result instanceof ArrayBuffer);
      assert.equal(result.byteLength, 768);

      // Verify fetch was called
      assert.equal(calledUrls.length, 1);
      assert.equal(calledUrls[0], 'https://example.com/naist-jdic.tar.gz');

      // Verify data was cached
      const cached = await mgr.getDictionaryFromCache('naist-jdic-v1');
      assert.ok(cached instanceof ArrayBuffer);
      assert.equal(cached.byteLength, 768);
    });

    it('2回目の呼び出しでは fetch が呼ばれない', async () => {
      const fetchedData = new ArrayBuffer(512);
      const { fetch: mockFetch, calledUrls } = createMockFetch(new Map([
        ['https://example.com/dict.bin', {
          ok: true,
          arrayBuffer: () => Promise.resolve(fetchedData),
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      // First call -- fetches from network
      await mgr.fetchAndCacheDictionary('https://example.com/dict.bin', 'dict-key');
      const fetchCountAfterFirst = calledUrls.length;

      // Second call -- should use cache
      const result = await mgr.fetchAndCacheDictionary('https://example.com/dict.bin', 'dict-key');

      assert.equal(result.byteLength, 512);
      assert.equal(
        calledUrls.length,
        fetchCountAfterFirst,
        'no additional fetch calls on second invocation',
      );
    });

    it('fetch 失敗時にエラーがスローされる', async () => {
      const { fetch: mockFetch } = createMockFetch(new Map([
        ['https://example.com/missing-dict.tar.gz', {
          ok: false,
          status: 404,
          statusText: 'Not Found',
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.fetchAndCacheDictionary(
          'https://example.com/missing-dict.tar.gz',
          'missing-dict',
        ),
        (err) => {
          assert.ok(err.message.includes('404') || err.message.includes('Failed'));
          return true;
        },
      );
    });

    it('ネットワークエラー時にエラーがスローされる', async () => {
      globalThis.fetch = async () => {
        throw new TypeError('Failed to fetch');
      };

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.fetchAndCacheDictionary(
          'https://example.com/unreachable.tar.gz',
          'unreachable',
        ),
        (err) => err instanceof TypeError,
      );
    });

    it('fetch 失敗後もキャッシュは汚染されない', async () => {
      const { fetch: mockFetch } = createMockFetch(new Map([
        ['https://example.com/bad-dict.tar.gz', {
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      // Expect the fetch to fail
      try {
        await mgr.fetchAndCacheDictionary(
          'https://example.com/bad-dict.tar.gz',
          'bad-dict',
        );
      } catch {
        // expected
      }

      // Verify cache was not polluted
      const cached = await mgr.getDictionaryFromCache('bad-dict');
      assert.equal(cached, null, 'failed fetch should not populate the cache');
    });

    it('onProgress コールバックが fetchWithProgress に渡される', async () => {
      // Use a body with getReader() to trigger the progress path in fetchWithProgress
      const totalSize = 1024;
      const chunkSize = 256;

      const routes = new Map([
        ['https://example.com/dict-progress.tar.gz', {
          ok: true,
          headers: new Map([['Content-Length', String(totalSize)]]),
          body: {
            getReader() {
              let bytesDelivered = 0;
              return {
                async read() {
                  if (bytesDelivered >= totalSize) {
                    return { done: true, value: undefined };
                  }
                  const chunk = new Uint8Array(chunkSize);
                  bytesDelivered += chunkSize;
                  return { done: false, value: chunk };
                },
              };
            },
          },
          arrayBuffer: () => { throw new Error('should not call arrayBuffer when body exists'); },
        }],
      ]);

      const { fetch: mockFetch } = createMockFetch(routes);
      globalThis.fetch = mockFetch;

      const progressEvents = [];
      const mgr = new ModelManager();

      const result = await mgr.fetchAndCacheDictionary(
        'https://example.com/dict-progress.tar.gz',
        'progress-dict',
        { onProgress: (event) => progressEvents.push({ ...event }) },
      );

      assert.ok(result instanceof ArrayBuffer);
      assert.ok(progressEvents.length > 0, 'onProgress should have been called');

      // Verify progress events are monotonically increasing
      for (let i = 1; i < progressEvents.length; i++) {
        assert.ok(
          progressEvents[i].loaded > progressEvents[i - 1].loaded,
          'loaded bytes should increase',
        );
      }

      const lastEvent = progressEvents[progressEvents.length - 1];
      assert.equal(lastEvent.loaded, totalSize);
      assert.equal(lastEvent.percentage, 100);
    });
  });

  // =====================================================================
  // 4. 辞書キャッシュとモデルキャッシュの独立性
  // =====================================================================

  describe('辞書キャッシュとモデルキャッシュの独立性', () => {
    it('辞書キャッシュとモデルキャッシュは分離されている', async () => {
      // Load a model via the model cache
      const modelUrl = 'https://example.com/model.onnx';
      const { fetch: mockFetch } = createMockFetch(new Map([
        [`${modelUrl}.json`, {
          ok: true,
          json: () => Promise.resolve({ sample_rate: 22050 }),
        }],
        [modelUrl, {
          ok: true,
          arrayBuffer: () => Promise.resolve(new ArrayBuffer(128)),
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      // Store a model
      await mgr.loadModel(modelUrl);

      // Store a dictionary
      await mgr.cacheDictionary('test-dict', new ArrayBuffer(64));

      // Verify both caches are populated
      const model = await mgr.getFromCache(modelUrl);
      const dict = await mgr.getDictionaryFromCache('test-dict');
      assert.ok(model, 'model should be cached');
      assert.ok(dict, 'dictionary should be cached');

      // Verify cross-store queries return null
      const dictAsModel = await mgr.getFromCache('test-dict');
      const modelAsDict = await mgr.getDictionaryFromCache(modelUrl);
      assert.equal(dictAsModel, null, 'dictionary key should not appear in model cache');
      assert.equal(modelAsDict, null, 'model key should not appear in dictionary cache');
    });

    it('clearCache でモデルと辞書の両方がクリアされる', async () => {
      const mgr = new ModelManager();

      // Populate both stores
      mockDb._stores.models.set('model-key', {
        modelData: new ArrayBuffer(32),
        config: { sample_rate: 22050 },
        timestamp: Date.now(),
      });
      mockDb._stores.dictionaries.set('dict-key', {
        data: new ArrayBuffer(64),
        timestamp: Date.now(),
      });

      // Verify both are populated
      const modelBefore = await mgr.getFromCache('model-key');
      const dictBefore = await mgr.getDictionaryFromCache('dict-key');
      assert.ok(modelBefore, 'model should be present before clear');
      assert.ok(dictBefore, 'dictionary should be present before clear');

      // Clear all caches
      await mgr.clearCache();

      // Verify both are cleared
      const modelAfter = await mgr.getFromCache('model-key');
      const dictAfter = await mgr.getDictionaryFromCache('dict-key');
      assert.equal(modelAfter, null, 'model should be cleared');
      assert.equal(dictAfter, null, 'dictionary should be cleared');
    });
  });

  // =====================================================================
  // 5. IndexedDB エラー時のフォールバック
  // =====================================================================

  describe('IndexedDB エラーハンドリング', () => {
    it('IndexedDB open 失敗時に getDictionaryFromCache がエラーをスローする', async () => {
      // Override indexedDB.open to simulate failure
      globalThis.indexedDB = {
        open: (_name, _version) => {
          const req = { result: null, error: new Error('IndexedDB unavailable'), onsuccess: null, onerror: null, onupgradeneeded: null };
          queueMicrotask(() => { if (req.onerror) req.onerror(); });
          return req;
        },
      };

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.getDictionaryFromCache('any-key'),
        (err) => err instanceof Error,
      );
    });

    it('IndexedDB open 失敗時に cacheDictionary がエラーをスローする', async () => {
      globalThis.indexedDB = {
        open: (_name, _version) => {
          const req = { result: null, error: new Error('IndexedDB unavailable'), onsuccess: null, onerror: null, onupgradeneeded: null };
          queueMicrotask(() => { if (req.onerror) req.onerror(); });
          return req;
        },
      };

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.cacheDictionary('any-key', new ArrayBuffer(16)),
        (err) => err instanceof Error,
      );
    });

    it('IndexedDB open 失敗時に fetchAndCacheDictionary がエラーをスローする', async () => {
      globalThis.indexedDB = {
        open: (_name, _version) => {
          const req = { result: null, error: new Error('IndexedDB unavailable'), onsuccess: null, onerror: null, onupgradeneeded: null };
          queueMicrotask(() => { if (req.onerror) req.onerror(); });
          return req;
        },
      };

      // Even though fetch would succeed, IndexedDB failure should propagate
      const { fetch: mockFetch } = createMockFetch(new Map([
        ['https://example.com/dict.tar.gz', {
          ok: true,
          arrayBuffer: () => Promise.resolve(new ArrayBuffer(64)),
        }],
      ]));
      globalThis.fetch = mockFetch;

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.fetchAndCacheDictionary('https://example.com/dict.tar.gz', 'dict-key'),
        (err) => err instanceof Error,
      );
    });
  });
});
