/**
 * TDD Tests for ModelManager
 * Phase 2: モデル自動ダウンロード
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// --- モック定義 ---

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
  // Fire onsuccess asynchronously, as the real IDB would.
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
 * based on URL matching.
 *
 * @param {Map<string|RegExp, {ok: boolean, status: number, json?: Function, arrayBuffer?: Function, headers?: Map}>} routes
 * @returns {Function}
 */
function createMockFetch(routes) {
  return async (url) => {
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
          body: null, // disable ReadableStream path in fetchWithProgress
        };
      }
    }
    return { ok: false, status: 404, statusText: 'Not Found' };
  };
}

/**
 * Create mock fetch routes for a complete HuggingFace model download flow.
 * Returns routes that handle API metadata, config JSON, and model binary.
 */
function createHuggingFaceRoutes(repoName, onnxFilename, config) {
  return new Map([
    [new RegExp(`huggingface\\.co/api/models/${repoName.replace('/', '\\/')}`), {
      ok: true,
      json: () => Promise.resolve({
        siblings: [
          { rfilename: 'README.md' },
          { rfilename: onnxFilename },
          { rfilename: 'config.json' },
        ],
      }),
    }],
    [new RegExp(`huggingface\\.co/${repoName.replace('/', '\\/')}.*config\\.json`), {
      ok: true,
      json: () => Promise.resolve(config),
    }],
    [new RegExp(`huggingface\\.co/${repoName.replace('/', '\\/')}.*${onnxFilename}$`), {
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(256)),
    }],
  ]);
}

/**
 * Create mock fetch routes for a direct-URL model download flow.
 */
function createDirectUrlRoutes(modelUrl, config) {
  return new Map([
    [`${modelUrl}.json`, {
      ok: true,
      json: () => Promise.resolve(config),
    }],
    [modelUrl, {
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(128)),
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

describe('ModelManager', { skip }, () => {
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
  // 1. コンストラクタ
  // =====================================================================

  describe('コンストラクタ', () => {
    it('デフォルトオプションで構築できる', () => {
      const mgr = new ModelManager();
      assert.ok(mgr instanceof ModelManager);
    });

    it('カスタムcachePrefixを設定できる', () => {
      const mgr = new ModelManager({ cachePrefix: 'my-custom-cache' });
      assert.equal(mgr._dbName, 'my-custom-cache');
    });

    it('オプション省略時はデフォルトのDB名が使用される', () => {
      const mgr = new ModelManager();
      assert.equal(mgr._dbName, 'piper-plus-models');
    });
  });

  // =====================================================================
  // 2. loadModel() 正常系
  // =====================================================================

  describe('loadModel() 正常系', () => {
    it('直接URLからモデルとconfigをダウンロードして返す', async () => {
      const expectedConfig = { sample_rate: 22050, num_speakers: 1 };
      globalThis.fetch = createMockFetch(
        createDirectUrlRoutes('https://example.com/model.onnx', expectedConfig),
      );

      const mgr = new ModelManager();
      const result = await mgr.loadModel('https://example.com/model.onnx');

      assert.ok(result.modelData instanceof ArrayBuffer);
      assert.equal(result.modelData.byteLength, 128);
      assert.deepEqual(result.config, expectedConfig);
    });

    it('HuggingFaceリポジトリ名からモデルをダウンロードして返す', async () => {
      const expectedConfig = { sample_rate: 22050, language: 'ja' };
      globalThis.fetch = createMockFetch(
        createHuggingFaceRoutes(
          'ayousanz/piper-plus-tsukuyomi-chan',
          'model-fp16.onnx',
          expectedConfig,
        ),
      );

      const mgr = new ModelManager();
      const result = await mgr.loadModel('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(result.modelData instanceof ArrayBuffer);
      assert.deepEqual(result.config, expectedConfig);
    });

    it('レジストリショートカットからモデルをダウンロードして返す', async () => {
      const expectedConfig = { sample_rate: 22050 };
      globalThis.fetch = createMockFetch(
        createHuggingFaceRoutes(
          'ayousanz/piper-plus-tsukuyomi-chan',
          'tsukuyomi.onnx',
          expectedConfig,
        ),
      );

      const mgr = new ModelManager();
      const result = await mgr.loadModel('tsukuyomi');

      assert.ok(result.modelData instanceof ArrayBuffer);
      assert.deepEqual(result.config, expectedConfig);
    });

    it('ダウンロード後にキャッシュに保存される', async () => {
      const expectedConfig = { sample_rate: 22050 };
      globalThis.fetch = createMockFetch(
        createDirectUrlRoutes('https://example.com/model.onnx', expectedConfig),
      );

      const mgr = new ModelManager();
      await mgr.loadModel('https://example.com/model.onnx');

      // Verify the cache now has an entry
      const cached = await mgr.getFromCache('https://example.com/model.onnx');
      assert.notEqual(cached, null);
      assert.deepEqual(cached.config, expectedConfig);
    });

    it('キャッシュ済みモデルはfetchなしで返される', async () => {
      const expectedConfig = { sample_rate: 22050 };
      // Pre-populate the cache via the mock DB store
      mockDb._store.set('https://example.com/cached.onnx', {
        modelData: new ArrayBuffer(64),
        config: expectedConfig,
        timestamp: Date.now(),
      });

      // fetch should NOT be called — set it to throw if called
      let fetchCalled = false;
      globalThis.fetch = async () => {
        fetchCalled = true;
        throw new Error('fetch should not be called for cached models');
      };

      const mgr = new ModelManager();
      const result = await mgr.loadModel('https://example.com/cached.onnx');

      assert.equal(fetchCalled, false);
      assert.equal(result.modelData.byteLength, 64);
      assert.deepEqual(result.config, expectedConfig);
    });

    it('onProgressコールバックが呼ばれる（body=nullのフォールバック時はスキップ）', async () => {
      const expectedConfig = { sample_rate: 22050 };
      globalThis.fetch = createMockFetch(
        createDirectUrlRoutes('https://example.com/model.onnx', expectedConfig),
      );

      const mgr = new ModelManager();
      // body=null in mock so fetchWithProgress falls back to arrayBuffer(),
      // but loadModel should still succeed without error
      const result = await mgr.loadModel('https://example.com/model.onnx', {
        onProgress: () => {},
      });

      assert.ok(result.modelData instanceof ArrayBuffer);
    });
  });

  // =====================================================================
  // 3. getFromCache()
  // =====================================================================

  describe('getFromCache()', () => {
    it('キャッシュヒット時にmodelDataとconfigを返す', async () => {
      const expectedConfig = { sample_rate: 22050 };
      const modelData = new ArrayBuffer(32);
      mockDb._store.set('test-key', {
        modelData,
        config: expectedConfig,
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();
      const result = await mgr.getFromCache('test-key');

      assert.notEqual(result, null);
      assert.equal(result.modelData, modelData);
      assert.deepEqual(result.config, expectedConfig);
    });

    it('キャッシュミス時にnullを返す', async () => {
      const mgr = new ModelManager();
      const result = await mgr.getFromCache('nonexistent-key');

      assert.equal(result, null);
    });

    it('異なるキーは独立してキャッシュされる', async () => {
      mockDb._store.set('model-a', {
        modelData: new ArrayBuffer(10),
        config: { name: 'a' },
        timestamp: Date.now(),
      });
      mockDb._store.set('model-b', {
        modelData: new ArrayBuffer(20),
        config: { name: 'b' },
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();

      const resultA = await mgr.getFromCache('model-a');
      const resultB = await mgr.getFromCache('model-b');

      assert.equal(resultA.modelData.byteLength, 10);
      assert.equal(resultB.modelData.byteLength, 20);
    });
  });

  // =====================================================================
  // 4. clearCache()
  // =====================================================================

  describe('clearCache()', () => {
    it('キャッシュ済みモデルがクリアされる', async () => {
      mockDb._store.set('key-1', {
        modelData: new ArrayBuffer(10),
        config: {},
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();
      await mgr.clearCache();

      const result = await mgr.getFromCache('key-1');
      assert.equal(result, null);
    });

    it('複数エントリが全てクリアされる', async () => {
      mockDb._store.set('key-1', {
        modelData: new ArrayBuffer(10),
        config: {},
        timestamp: Date.now(),
      });
      mockDb._store.set('key-2', {
        modelData: new ArrayBuffer(20),
        config: {},
        timestamp: Date.now(),
      });

      const mgr = new ModelManager();
      await mgr.clearCache();

      const result1 = await mgr.getFromCache('key-1');
      const result2 = await mgr.getFromCache('key-2');
      assert.equal(result1, null);
      assert.equal(result2, null);
    });

    it('空キャッシュのクリアはエラーにならない', async () => {
      const mgr = new ModelManager();
      // Should not throw
      await mgr.clearCache();
    });
  });

  // =====================================================================
  // 5. URL解決 (内部実装テスト — _resolveUrls 補足)
  // =====================================================================

  describe('URL解決 (内部実装テスト: _resolveUrls)', () => {
    it('HuggingFaceリポジトリ名のmodelUrlにhuggingface.coが含まれる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model-fp16.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(urls.modelUrl.includes('huggingface.co'));
    });

    it('HuggingFaceリポジトリ名のmodelUrlにリポジトリパスが含まれる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model-fp16.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(urls.modelUrl.includes('ayousanz/piper-plus-tsukuyomi-chan'));
    });

    it('HuggingFaceリポジトリ名のmodelUrlが.onnxで終わる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model-fp16.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(urls.modelUrl.endsWith('.onnx'));
    });

    it('HuggingFaceリポジトリ名のcacheKeyがリポジトリ名になる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model-fp16.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.equal(urls.cacheKey, 'ayousanz/piper-plus-tsukuyomi-chan');
    });

    it('レジストリショートカット "tsukuyomi" をフルリポジトリ名に解決する', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\/ayousanz\/piper-plus-tsukuyomi-chan/, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'tsukuyomi.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('tsukuyomi');

      assert.ok(urls.modelUrl.includes('ayousanz/piper-plus-tsukuyomi-chan'));
      assert.equal(urls.cacheKey, 'ayousanz/piper-plus-tsukuyomi-chan');
    });

    it('直接URLはそのまま使用される', async () => {
      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/model.onnx');

      assert.equal(urls.modelUrl, 'https://example.com/model.onnx');
    });

    it('直接URLのcacheKeyはURL自体になる', async () => {
      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/model.onnx');

      assert.equal(urls.cacheKey, 'https://example.com/model.onnx');
    });

    it('直接URLのconfig URLはmodel URL + ".json" になる', async () => {
      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/model.onnx');

      assert.equal(urls.configUrl, 'https://example.com/model.onnx.json');
    });

    it('HuggingFaceリポジトリのconfigUrlはサイドカー.onnx.jsonを優先する', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [
              { rfilename: 'model.onnx' },
              { rfilename: 'model.onnx.json' },
            ],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-base');

      assert.ok(urls.configUrl.endsWith('.onnx.json'));
    });

    it('サイドカーがない場合はconfig.jsonにフォールバックする', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-base');

      assert.ok(urls.configUrl.endsWith('/config.json'));
    });

    it('直接URLのconfigFallbackUrlはconfig.jsonになる', async () => {
      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/models/model.onnx');

      assert.equal(urls.configFallbackUrl, 'https://example.com/models/config.json');
    });

    it('HuggingFaceリポジトリのconfigFallbackUrlはnullになる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-base');

      assert.equal(urls.configFallbackUrl, null);
    });

    it('HuggingFaceリポジトリのconfigUrlにhuggingface.coが含まれる', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-base');

      assert.ok(urls.configUrl.includes('huggingface.co'));
    });

    it('fp16ファイルが存在する場合はそちらを優先する', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [
              { rfilename: 'model.onnx' },
              { rfilename: 'model-fp16.onnx' },
              { rfilename: 'config.json' },
            ],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(urls.modelUrl.includes('model-fp16.onnx'));
    });
  });

  // =====================================================================
  // 6. キャッシュキー生成
  // =====================================================================

  describe('キャッシュキー生成', () => {
    it('同じモデル名からは同じキーが生成される', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls1 = await mgr._resolveUrls('tsukuyomi');
      const urls2 = await mgr._resolveUrls('tsukuyomi');

      assert.equal(urls1.cacheKey, urls2.cacheKey);
    });

    it('異なるモデル名からは異なるキーが生成される', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urlsTsukuyomi = await mgr._resolveUrls('tsukuyomi');
      const urlsBase = await mgr._resolveUrls('base');

      assert.notEqual(urlsTsukuyomi.cacheKey, urlsBase.cacheKey);
    });

    it('同じレジストリエイリアスは同じキーに解決される', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      // "tsukuyomi" and "tsukuyomi-chan" both map to the same repo
      const urls1 = await mgr._resolveUrls('tsukuyomi');
      const urls2 = await mgr._resolveUrls('tsukuyomi-chan');

      assert.equal(urls1.cacheKey, urls2.cacheKey);
    });
  });

  // =====================================================================
  // 7. エラーケース
  // =====================================================================

  describe('エラーケース', () => {
    it('HuggingFace APIが404を返す場合loadModelがエラーをスローする', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: false,
          status: 404,
          statusText: 'Not Found',
        }],
      ]));

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.loadModel('ayousanz/nonexistent-model'),
        (err) => {
          assert.ok(err.message.includes('404') || err.message.includes('Failed'));
          return true;
        },
      );
    });

    it('リポジトリにONNXファイルがない場合loadModelがエラーをスローする', async () => {
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [
              { rfilename: 'README.md' },
              { rfilename: 'config.json' },
            ],
          }),
        }],
      ]));

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.loadModel('ayousanz/piper-plus-base'),
        (err) => {
          assert.ok(err.message.includes('.onnx') || err.message.includes('No'));
          return true;
        },
      );
    });

    it('loadModelでconfig取得失敗時にエラーをスローする', async () => {
      globalThis.fetch = createMockFetch(new Map([
        ['https://example.com/model.onnx.json', {
          ok: false,
          status: 500,
          statusText: 'Internal Server Error',
        }],
        ['https://example.com/model.onnx', {
          ok: true,
          arrayBuffer: () => Promise.resolve(new ArrayBuffer(100)),
        }],
      ]));

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.loadModel('https://example.com/model.onnx'),
        (err) => {
          assert.ok(err.message.includes('500') || err.message.includes('Failed'));
          return true;
        },
      );
    });

    it('空文字列でloadModelを呼ぶとエラーになる', async () => {
      // Empty string is not a URL, so it hits the HF API path with an empty repo name.
      // The mock fetch returns 404 for any unmatched route.
      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr.loadModel(''),
        (err) => err instanceof Error,
      );
    });

    it('_resolveUrlsにnull入力でエラーをスローする', async () => {
      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls(null),
        (err) => err instanceof Error,
      );
    });

    it('_resolveUrlsにundefined入力でエラーをスローする', async () => {
      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls(undefined),
        (err) => err instanceof Error,
      );
    });
  });
});
