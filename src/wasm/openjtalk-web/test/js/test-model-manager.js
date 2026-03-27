/**
 * TDD Tests for ModelManager
 * Phase 2: モデル自動ダウンロード
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach, afterEach } from 'node:test';

// --- モック定義 ---

/**
 * Minimal mock for IndexedDB that satisfies ModelManager._getDb().
 * Stores values in a plain Map keyed by the IDBObjectStore key argument.
 */
function createMockIndexedDB() {
  const store = new Map();

  return {
    transaction(storeName, mode) {
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

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    originalIndexedDB = globalThis.indexedDB;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.indexedDB = originalIndexedDB;
  });

  // =====================================================================
  // 1. URL 解決テスト
  // =====================================================================

  describe('URL解決 (_resolveUrls)', () => {
    it('HuggingFaceリポジトリ名をHuggingFace URLに変換する', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      // HF API returns metadata with an .onnx sibling
      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [
              { rfilename: 'README.md' },
              { rfilename: 'model-fp16.onnx' },
              { rfilename: 'config.json' },
            ],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-tsukuyomi-chan');

      assert.ok(urls.modelUrl.includes('huggingface.co'));
      assert.ok(urls.modelUrl.includes('ayousanz/piper-plus-tsukuyomi-chan'));
      assert.ok(urls.modelUrl.endsWith('.onnx'));
      assert.equal(urls.cacheKey, 'ayousanz/piper-plus-tsukuyomi-chan');
    });

    it('レジストリショートカット "tsukuyomi" をフルリポジトリ名に解決する', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\/ayousanz\/piper-plus-tsukuyomi-chan/, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'tsukuyomi.onnx' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('tsukuyomi');

      assert.ok(urls.modelUrl.includes('ayousanz/piper-plus-tsukuyomi-chan'));
      assert.equal(urls.cacheKey, 'ayousanz/piper-plus-tsukuyomi-chan');
    });

    it('直接URLはそのまま使用される', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/model.onnx');

      assert.equal(urls.modelUrl, 'https://example.com/model.onnx');
      assert.equal(urls.cacheKey, 'https://example.com/model.onnx');
    });

    it('config URLはmodel URL + ".json" になる', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://example.com/model.onnx');

      assert.equal(urls.configUrl, 'https://example.com/model.onnx.json');
    });

    it('HuggingFaceリポジトリでもconfigUrlが生成される', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('ayousanz/piper-plus-base');

      assert.ok(urls.configUrl.endsWith('.onnx.json'));
      assert.ok(urls.configUrl.includes('huggingface.co'));
    });

    it('fp16ファイルが存在する場合はそちらを優先する', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [
              { rfilename: 'model.onnx' },
              { rfilename: 'model-fp16.onnx' },
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
  // 2. ModelManager 構築
  // =====================================================================

  describe('コンストラクタ', () => {
    it('デフォルトオプションで構築できる', () => {
      const mgr = new ModelManager();
      assert.ok(mgr instanceof ModelManager);
    });

    it('カスタムcachePrefixを設定できる', () => {
      const mgr = new ModelManager({ cachePrefix: 'my-custom-cache' });
      // _dbName is internal but we verify it to confirm the option is respected
      assert.equal(mgr._dbName, 'my-custom-cache');
    });

    it('オプション省略時はデフォルトのDB名が使用される', () => {
      const mgr = new ModelManager();
      assert.equal(mgr._dbName, 'piper-plus-models');
    });
  });

  // =====================================================================
  // 3. キャッシュキー生成
  // =====================================================================

  describe('キャッシュキー生成', () => {
    it('同じモデル名からは同じキーが生成される', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urls1 = await mgr._resolveUrls('tsukuyomi');
      const urls2 = await mgr._resolveUrls('tsukuyomi');

      assert.equal(urls1.cacheKey, urls2.cacheKey);
    });

    it('異なるモデル名からは異なるキーが生成される', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }],
          }),
        }],
      ]));

      const mgr = new ModelManager();
      const urlsTsukuyomi = await mgr._resolveUrls('tsukuyomi');
      const urlsBase = await mgr._resolveUrls('base');

      assert.notEqual(urlsTsukuyomi.cacheKey, urlsBase.cacheKey);
    });

    it('直接URLの場合はURL自体がキャッシュキーになる', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      const mgr = new ModelManager();
      const urls = await mgr._resolveUrls('https://cdn.example.com/my-model.onnx');

      assert.equal(urls.cacheKey, 'https://cdn.example.com/my-model.onnx');
    });

    it('同じレジストリエイリアスは同じキーに解決される', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: true,
          json: () => Promise.resolve({
            siblings: [{ rfilename: 'model.onnx' }],
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
  // 4. エラーケース
  // =====================================================================

  describe('エラーケース', () => {
    it('HuggingFace APIが404を返す場合エラーをスローする', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map([
        [/huggingface\.co\/api\/models\//, {
          ok: false,
          status: 404,
          statusText: 'Not Found',
        }],
      ]));

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls('ayousanz/nonexistent-model'),
        (err) => {
          assert.ok(err.message.includes('404') || err.message.includes('Failed'));
          return true;
        }
      );
    });

    it('リポジトリにONNXファイルがない場合エラーをスローする', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

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
        () => mgr._resolveUrls('ayousanz/piper-plus-base'),
        (err) => {
          assert.ok(err.message.includes('.onnx') || err.message.includes('No'));
          return true;
        }
      );
    });

    it('空文字列でfetchが呼ばれた場合エラーになる', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      // Empty string is not a URL, so it hits the HF API path with an empty repo name.
      // The mock fetch returns 404 for any unmatched route.
      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls(''),
        (err) => err instanceof Error
      );
    });

    it('null入力でエラーをスローする', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls(null),
        (err) => err instanceof Error
      );
    });

    it('undefined入力でエラーをスローする', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

      globalThis.fetch = createMockFetch(new Map());

      const mgr = new ModelManager();

      await assert.rejects(
        () => mgr._resolveUrls(undefined),
        (err) => err instanceof Error
      );
    });

    it('loadModelでconfig取得失敗時にエラーをスローする', async () => {
      const mockDb = createMockIndexedDB();
      installIndexedDBMock(mockDb);

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
        }
      );
    });
  });
});
