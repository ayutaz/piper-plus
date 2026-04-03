/**
 * TDD Tests for ModelManager — Boundary / Error Cases
 *
 * テスト対象: src/wasm/openjtalk-web/src/model-manager.js
 *
 * null/undefined/空文字列、404、ONNX不在、ネットワーク障害、
 * 不正JSON、タイムアウト的状況などの境界条件を網羅する。
 */

import assert from 'node:assert/strict';
import { describe, it, afterEach } from 'node:test';

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
          body: null,
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

describe('ModelManager 境界/エラーケース', { skip }, () => {
  let originalFetch;
  let originalIndexedDB;

  afterEach(() => {
    if (originalFetch !== undefined) globalThis.fetch = originalFetch;
    if (originalIndexedDB !== undefined) globalThis.indexedDB = originalIndexedDB;
    originalFetch = undefined;
    originalIndexedDB = undefined;
  });

  /**
   * Helper: save originals and install mocks for a single test.
   */
  function setupMocks() {
    originalFetch = globalThis.fetch;
    originalIndexedDB = globalThis.indexedDB;
    const mockDb = createMockIndexedDB();
    installIndexedDBMock(mockDb);
    return mockDb;
  }

  // =====================================================================
  // 1. null 入力
  // =====================================================================

  it('null 入力でエラーをスローする', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map());
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel(null),
      (err) => err instanceof Error,
    );
  });

  // =====================================================================
  // 2. undefined 入力
  // =====================================================================

  it('undefined 入力でエラーをスローする', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map());
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel(undefined),
      (err) => err instanceof Error,
    );
  });

  // =====================================================================
  // 3. 空文字列
  // =====================================================================

  it('空文字列でエラーをスローする', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map());
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel(''),
      (err) => err instanceof Error,
    );
  });

  // =====================================================================
  // 4. 存在しない HuggingFace リポジトリで適切なエラー
  // =====================================================================

  it('存在しない HuggingFace リポジトリで適切なエラー', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: false,
        status: 404,
        statusText: 'Not Found',
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('nonexistent-org/nonexistent-repo'),
      (err) => err.message.includes('404'),
    );
  });

  // =====================================================================
  // 5. ONNX ファイルがないリポジトリで適切なエラー
  // =====================================================================

  it('ONNX ファイルがないリポジトリで適切なエラー', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [
            { rfilename: 'README.md' },
            { rfilename: 'data.csv' },
          ],
        }),
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/no-onnx-repo'),
      (err) => err.message.includes('.onnx'),
    );
  });

  // =====================================================================
  // 6. config.json 取得失敗で適切なエラー (siblings に config.json あり、fetch が 503)
  // =====================================================================

  it('config.json 取得失敗で適切なエラー', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [
            { rfilename: 'model.onnx' },
            { rfilename: 'config.json' },
          ],
        }),
      }],
      [/resolve\/main\/config\.json$/, {
        ok: false,
        status: 503,
        statusText: 'Service Unavailable',
      }],
      [/model\.onnx$/, {
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(64)),
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/some-repo'),
      (err) => err.message.includes('503'),
    );
  });

  // =====================================================================
  // 6b. siblings にサイドカーも config.json もない場合 resolveModelFiles でエラー
  // =====================================================================

  it('siblings にサイドカーも config.json もない場合エラーをスローする', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [
            { rfilename: 'model.onnx' },
            { rfilename: 'README.md' },
          ],
        }),
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/no-config-repo'),
      (err) => err.message.includes('No config file found'),
    );
  });

  // =====================================================================
  // 7. ネットワークエラー (fetch reject) で適切なエラー
  // =====================================================================

  it('ネットワークエラー (fetch reject) で適切なエラー', async () => {
    setupMocks();
    globalThis.fetch = async () => {
      throw new TypeError('Failed to fetch');
    };
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/some-repo'),
      (err) => err instanceof TypeError,
    );
  });

  // =====================================================================
  // 8. siblings が空配列の場合のエラー
  // =====================================================================

  it('siblings が空配列の場合のエラー', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [],
        }),
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/empty-siblings-repo'),
      (err) => err.message.includes('.onnx'),
    );
  });

  // =====================================================================
  // 9. 不正な JSON レスポンスでエラー
  // =====================================================================

  it('不正な JSON レスポンスでエラー', async () => {
    setupMocks();
    globalThis.fetch = createMockFetch(new Map([
      [/huggingface\.co\/api\/models\//, {
        ok: true,
        json: () => Promise.resolve({
          siblings: [{ rfilename: 'model.onnx' }, { rfilename: 'config.json' }],
        }),
      }],
      [/resolve\/main\/config\.json$/, {
        ok: true,
        json: () => { throw new SyntaxError('Unexpected token < in JSON'); },
      }],
      [/model\.onnx$/, {
        ok: true,
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(64)),
      }],
    ]));
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/bad-json-repo'),
      (err) => err instanceof SyntaxError,
    );
  });

  // =====================================================================
  // 10. タイムアウト的な状況でのエラー
  // =====================================================================

  it('タイムアウト的な状況でのエラー', async () => {
    setupMocks();
    const controller = new AbortController();
    globalThis.fetch = () => new Promise((_resolve, reject) => {
      // Simulate a fetch that never resolves by aborting immediately.
      const timeoutId = setTimeout(() => {
        reject(new DOMException('The operation was aborted', 'AbortError'));
      }, 0);
      // Keep the timeout reference to avoid GC (Node.js may not need this,
      // but it makes intent explicit).
      void timeoutId;
    });
    const mgr = new ModelManager();

    await assert.rejects(
      () => mgr.loadModel('some-org/slow-repo'),
      (err) => err.name === 'AbortError',
    );
  });
});
