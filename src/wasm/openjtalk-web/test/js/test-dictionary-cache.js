/**
 * TDD Tests for DictionaryLoader + CacheManager integration
 * Phase 2: 辞書キャッシュ統合
 *
 * テスト対象: src/wasm/openjtalk-web/src/dictionary-loader.js (CacheManager統合)
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Node.js環境ではIndexedDBが存在しないため、軽量モックを使用
class MockIndexedDB {
  constructor() { this.stores = new Map(); }
  transaction(name, mode) {
    const store = this.stores.get(name) || new Map();
    this.stores.set(name, store);
    return {
      objectStore: (storeName) => ({
        get: (key) => ({ _mock: true, result: store.get(key) }),
        put: (val) => { store.set(val.key, val); return { _mock: true, result: undefined }; },
        delete: (key) => { store.delete(key); return { _mock: true, result: undefined }; },
        count: () => ({ _mock: true, result: store.size }),
        getAll: () => ({ _mock: true, result: [...store.values()] }),
      }),
    };
  }
}

// WASM module FS mock
class MockModule {
  constructor() {
    this.files = new Map();
    this.dirs = new Set();
    this.FS = {
      mkdir: (path) => { this.dirs.add(path); },
      writeFile: (path, data) => { this.files.set(path, data); },
      readdir: (path) => [...this.files.keys()]
        .filter(f => f.startsWith(path + '/'))
        .map(f => f.split('/').pop()),
      stat: (path) => ({ size: this.files.get(path)?.length || 0 }),
    };
  }
}

// Network fetch mock
let fetchCallCount = 0;
const mockFetchData = new Map();
const originalFetch = globalThis.fetch;

function installMockFetch() {
  fetchCallCount = 0;
  mockFetchData.clear();
  globalThis.fetch = async (url) => {
    fetchCallCount++;
    const data = mockFetchData.get(url) || new ArrayBuffer(100);
    return { ok: true, arrayBuffer: async () => data };
  };
}

function restoreFetch() {
  globalThis.fetch = originalFetch;
}

// ---------------------------------------------------------------------------
// Import target modules
// ---------------------------------------------------------------------------

let DictionaryLoader, CacheManager;
try {
  const dictMod = await import('../../src/dictionary-loader.js');
  DictionaryLoader = dictMod.DictionaryLoader;
  const cacheMod = await import('../../src/cache-manager.js');
  CacheManager = cacheMod.CacheManager;
} catch {
  DictionaryLoader = null;
}

const skip = DictionaryLoader === null || CacheManager === null;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DictionaryLoader + CacheManager 統合', { skip }, () => {
  const BASE_URL = 'https://example.com/dict';
  const DICT_FILES = [
    'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
    'left-id.def', 'pos-id.def', 'rewrite.def', 'right-id.def',
  ];

  let mockModule;

  beforeEach(() => {
    mockModule = new MockModule();
    installMockFetch();
    // Prepare mock fetch data for each dict file
    for (const file of DICT_FILES) {
      mockFetchData.set(`${BASE_URL}/${file}`, new ArrayBuffer(64));
    }
  });

  // 1. キャッシュなしの場合、従来通りfetchで取得する
  it('キャッシュなしの場合、従来通りfetchで取得する', async () => {
    const loader = new DictionaryLoader(mockModule);
    await loader.loadIndividualFiles(BASE_URL);

    // Each dict file triggers one fetch
    assert.equal(fetchCallCount, DICT_FILES.length,
      `Expected ${DICT_FILES.length} fetch calls, got ${fetchCallCount}`);

    // All files written to virtual FS
    for (const file of DICT_FILES) {
      assert.ok(mockModule.files.has(`/dict/${file}`),
        `Expected /dict/${file} to be written to FS`);
    }

    restoreFetch();
  });

  // 2. キャッシュあり・初回ロード: fetchしてキャッシュに保存する
  it('キャッシュあり・初回ロード: fetchしてキャッシュに保存する', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
    const loader = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });

    await loader.loadIndividualFiles(BASE_URL);

    // All files fetched on first load
    assert.equal(fetchCallCount, DICT_FILES.length,
      'First load should fetch all files');

    // All files written to virtual FS
    for (const file of DICT_FILES) {
      assert.ok(mockModule.files.has(`/dict/${file}`),
        `Expected /dict/${file} to be written to FS`);
    }

    // All files cached
    for (const file of DICT_FILES) {
      const cached = await cache.get(`dict/${file}`);
      assert.ok(cached, `Expected dict/${file} to be cached`);
      assert.equal(cached.version, 'v1.0');
    }

    restoreFetch();
  });

  // 3. キャッシュあり・2回目ロード: キャッシュから取得しfetchしない
  it('キャッシュあり・2回目ロード: キャッシュから取得しfetchしない', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
    const loader = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });

    // First load — populates cache
    await loader.loadIndividualFiles(BASE_URL);
    const fetchesAfterFirstLoad = fetchCallCount;

    // Reset module FS to verify files get written from cache
    mockModule = new MockModule();
    const loader2 = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });

    // Second load — should use cache, no new fetches
    await loader2.loadIndividualFiles(BASE_URL);
    assert.equal(fetchCallCount, fetchesAfterFirstLoad,
      'Second load should not trigger any additional fetch calls');

    // Files still written to virtual FS
    for (const file of DICT_FILES) {
      assert.ok(mockModule.files.has(`/dict/${file}`),
        `Expected /dict/${file} to be written to FS from cache`);
    }

    restoreFetch();
  });

  // 4. 辞書ファイルはhigh優先度でキャッシュされる
  it('辞書ファイルはhigh優先度でキャッシュされる', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
    const loader = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });

    await loader.loadIndividualFiles(BASE_URL);

    for (const file of DICT_FILES) {
      const cached = await cache.get(`dict/${file}`);
      assert.ok(cached, `Expected dict/${file} to be cached`);
      assert.equal(cached.priority, 'high',
        `Expected dict/${file} to have priority 'high', got '${cached.priority}'`);
    }

    restoreFetch();
  });

  // 5. dictVersionが変わった場合は再fetchする
  it('dictVersionが変わった場合は再fetchする', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });

    // First load with v1.0
    const loader1 = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });
    await loader1.loadIndividualFiles(BASE_URL);
    const fetchesAfterV1 = fetchCallCount;

    // Second load with v2.0 — version change should trigger re-fetch
    mockModule = new MockModule();
    const loader2 = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v2.0',
    });
    await loader2.loadIndividualFiles(BASE_URL);

    assert.equal(fetchCallCount, fetchesAfterV1 + DICT_FILES.length,
      'Version change should re-fetch all files');

    // Cache should now have v2.0
    for (const file of DICT_FILES) {
      const cached = await cache.get(`dict/${file}`);
      assert.equal(cached.version, 'v2.0',
        `Expected dict/${file} cache version to be 'v2.0'`);
    }

    restoreFetch();
  });

  // 6. clearCache()でキャッシュをクリアできる
  it('clearCache()でキャッシュをクリアできる', async () => {
    const cache = new CacheManager({ dbFactory: () => new MockIndexedDB() });
    const loader = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });

    await loader.loadIndividualFiles(BASE_URL);

    // Verify cache is populated
    const keysBefore = await cache.getKeys();
    assert.ok(keysBefore.length > 0, 'Cache should have entries after load');

    // Clear cache
    await cache.clear();

    // Verify cache is empty
    const keysAfter = await cache.getKeys();
    assert.equal(keysAfter.length, 0, 'Cache should be empty after clear()');

    // Re-load should fetch again
    const fetchesBefore = fetchCallCount;
    mockModule = new MockModule();
    const loader2 = new DictionaryLoader(mockModule, {
      cacheManager: cache,
      dictVersion: 'v1.0',
    });
    await loader2.loadIndividualFiles(BASE_URL);

    assert.equal(fetchCallCount, fetchesBefore + DICT_FILES.length,
      'After clear(), loading should fetch all files again');

    restoreFetch();
  });
});
