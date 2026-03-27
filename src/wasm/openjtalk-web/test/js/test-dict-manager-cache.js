/**
 * TDD Tests for DictManager cache lifecycle (isCached / clearCache)
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 *
 * キャッシュの初期状態、loadDictionary 後の状態遷移、clearCache による
 * 無効化、再ダウンロード、cachePrefix による独立キャッシュ、データ整合性
 * を検証する。
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// ---- Constants (mirror source for assertions) --------------------------------

const DICT_FILES = [
  'char.bin',
  'matrix.bin',
  'sys.dic',
  'unk.dic',
  'left-id.def',
  'right-id.def',
  'pos-id.def',
  'rewrite.def',
];

const VOICE_KEY = 'voice/mei_normal.htsvoice';

// ---- Mock: IndexedDB (in-memory with working get/put/delete/clear) ----------

/**
 * In-memory object store backed by a Map.
 * Supports get, put, clear, and delete -- all returning IDBRequest-like objects
 * whose onsuccess fires on the next microtick.
 */
class MockObjectStore {
  constructor(store) {
    this._store = store;
  }

  get(key) {
    const result = this._store.get(key) ?? undefined;
    return _fakeRequest(result);
  }

  put(val) {
    this._store.set(val.key, val);
    return _fakeRequest(undefined);
  }

  delete(key) {
    this._store.delete(key);
    return _fakeRequest(undefined);
  }

  clear() {
    this._store.clear();
    return _fakeRequest(undefined);
  }
}

function _fakeRequest(result) {
  const req = { result, onsuccess: null, onerror: null };
  Promise.resolve().then(() => {
    if (req.onsuccess) req.onsuccess();
  });
  return req;
}

class MockIDBDatabase {
  constructor() {
    this._stores = new Map();
    this.objectStoreNames = { contains: (n) => this._stores.has(n) };
  }

  _ensureStore(name) {
    if (!this._stores.has(name)) this._stores.set(name, new Map());
    return this._stores.get(name);
  }

  createObjectStore(name, _opts) {
    this._ensureStore(name);
  }

  transaction(storeName, _mode) {
    const store = this._ensureStore(storeName);
    return { objectStore: () => new MockObjectStore(store) };
  }
}

/**
 * Map of dbName -> MockIDBDatabase.
 * Each unique cachePrefix (dbName) gets its own isolated database instance,
 * which is essential for testing cross-prefix isolation.
 */
let _dbInstances;

function installIndexedDBMock() {
  _dbInstances = new Map();
  globalThis.indexedDB = {
    open(name, _version) {
      if (!_dbInstances.has(name)) {
        _dbInstances.set(name, new MockIDBDatabase());
      }
      const db = _dbInstances.get(name);
      const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
      Promise.resolve().then(() => {
        if (req.onupgradeneeded) {
          req.onupgradeneeded({ target: { result: db } });
        }
        req.result = db;
        if (req.onsuccess) req.onsuccess();
      });
      return req;
    },
  };
}

function teardownIndexedDBMock() {
  _dbInstances = null;
  delete globalThis.indexedDB;
}

// ---- Mock: fetch (returns deterministic dummy data) -------------------------

/** Dummy 64-byte buffer used as dict/voice payload. */
const DUMMY_DATA = new ArrayBuffer(64);
new Uint8Array(DUMMY_DATA).fill(0xAB);

/**
 * Install a global fetch mock that returns copies of DUMMY_DATA.
 * Returns an array that collects all fetched URLs.
 */
function installFetchMock() {
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(url);
    // Return a fresh copy so consumers cannot mutate shared state.
    const copy = DUMMY_DATA.slice(0);
    return {
      ok: true,
      headers: { get: () => null },
      body: null,
      arrayBuffer: async () => copy,
    };
  };
  return fetched;
}

function teardownFetchMock() {
  delete globalThis.fetch;
}

// ---- Import SUT (TDD skip guard) -------------------------------------------

let DictManager;
try {
  const mod = await import('../../src/dict-manager.js');
  DictManager = mod.DictManager || mod.default;
} catch {
  DictManager = null;
}

const skip = DictManager === null;

// ---- Tests ------------------------------------------------------------------

describe('DictManager キャッシュライフサイクル', { skip }, () => {
  /** @type {string[]} URLs fetched during the current test. */
  let fetched;

  beforeEach(() => {
    installIndexedDBMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    fetched = [];
    teardownFetchMock();
    teardownIndexedDBMock();
  });

  // ---------- 1. 初期状態 -------------------------------------------------------

  it('初期状態で isCached は false を返す', async () => {
    // Arrange
    const dm = new DictManager();

    // Act
    const cached = await dm.isCached();

    // Assert
    assert.equal(cached, false, 'isCached should be false before any loadDictionary call');
  });

  // ---------- 2. loadDictionary 後 -----------------------------------------------

  it('loadDictionary 後に isCached は true を返す', async () => {
    // Arrange
    const dm = new DictManager();

    // Act
    await dm.loadDictionary();
    const cached = await dm.isCached();

    // Assert
    assert.equal(cached, true, 'isCached should be true after successful loadDictionary');
  });

  // ---------- 3. clearCache 後 ---------------------------------------------------

  it('clearCache 後に isCached は false を返す', async () => {
    // Arrange
    const dm = new DictManager();
    await dm.loadDictionary();
    assert.equal(await dm.isCached(), true, 'precondition: cache should be populated');

    // Act
    await dm.clearCache();
    const cached = await dm.isCached();

    // Assert
    assert.equal(cached, false, 'isCached should be false after clearCache');
  });

  // ---------- 4. clearCache 後の再ダウンロード ------------------------------------

  it('clearCache 後に再度 loadDictionary すると fetch が実行される', async () => {
    // Arrange -- load once, then clear
    const dm = new DictManager();
    await dm.loadDictionary();
    const firstFetchCount = fetched.length;
    assert.ok(firstFetchCount > 0, 'precondition: first load should trigger fetches');

    await dm.clearCache();
    fetched.length = 0;

    // Act -- load again after cache clear
    await dm.loadDictionary();

    // Assert -- all files should be re-fetched (8 dict + 1 voice = 9)
    assert.equal(
      fetched.length,
      DICT_FILES.length + 1,
      'After clearCache, loadDictionary should fetch all files again'
    );
  });

  // ---------- 5. 2回目の loadDictionary はキャッシュを使用する --------------------

  it('2回目の loadDictionary はキャッシュを使用する', async () => {
    // Arrange
    const dm = new DictManager();
    await dm.loadDictionary();
    const firstFetchCount = fetched.length;
    assert.ok(firstFetchCount > 0, 'precondition: first load should fetch');

    // Act -- reset URL tracker and load again
    fetched.length = 0;
    await dm.loadDictionary();

    // Assert -- zero additional fetches means cache was used
    assert.equal(
      fetched.length,
      0,
      'Second loadDictionary should not trigger any fetch (all from cache)'
    );
  });

  // ---------- 6. カスタム cachePrefix で独立したキャッシュが作られる ---------------

  it('カスタム cachePrefix で独立したキャッシュが作られる', async () => {
    // Arrange -- load into prefix-A
    const dmA = new DictManager({ cachePrefix: 'prefix-A' });
    await dmA.loadDictionary();
    assert.equal(await dmA.isCached(), true, 'precondition: prefix-A should be cached');

    // Act -- check prefix-B (never loaded)
    const dmB = new DictManager({ cachePrefix: 'prefix-B' });
    const cachedB = await dmB.isCached();

    // Assert -- prefix-B should be empty despite prefix-A being populated
    assert.equal(
      cachedB,
      false,
      'A different cachePrefix should have its own independent cache'
    );
  });

  // ---------- 7. clearCache が他のキャッシュに影響しない --------------------------

  it('clearCache が他のキャッシュに影響しない', async () => {
    // Arrange -- populate both prefix-A and prefix-B
    const dmA = new DictManager({ cachePrefix: 'prefix-A' });
    const dmB = new DictManager({ cachePrefix: 'prefix-B' });
    await dmA.loadDictionary();
    await dmB.loadDictionary();
    assert.equal(await dmA.isCached(), true, 'precondition: prefix-A cached');
    assert.equal(await dmB.isCached(), true, 'precondition: prefix-B cached');

    // Act -- clear only prefix-A
    await dmA.clearCache();

    // Assert -- prefix-B should be unaffected
    assert.equal(await dmA.isCached(), false, 'prefix-A should be cleared');
    assert.equal(await dmB.isCached(), true, 'prefix-B should remain cached');
  });

  // ---------- 8. キャッシュされた辞書ファイルが正しいデータを返す ------------------

  it('キャッシュされた辞書ファイルが正しいデータを返す', async () => {
    // Arrange -- load once to populate cache
    const dm = new DictManager();
    await dm.loadDictionary();

    // Act -- load again (all from cache)
    const { dictFiles, voiceData } = await dm.loadDictionary();

    // Assert -- dict files
    assert.equal(
      Object.keys(dictFiles).length,
      DICT_FILES.length,
      `dictFiles should contain ${DICT_FILES.length} entries`
    );
    for (const filename of DICT_FILES) {
      const buf = dictFiles[filename];
      assert.ok(buf instanceof ArrayBuffer, `${filename} should be an ArrayBuffer`);
      assert.equal(buf.byteLength, 64, `${filename} should be 64 bytes (matching dummy data)`);

      // Verify data content matches the dummy payload (0xAB fill).
      const bytes = new Uint8Array(buf);
      assert.equal(
        bytes[0],
        0xAB,
        `${filename} first byte should be 0xAB`
      );
      assert.equal(
        bytes[bytes.length - 1],
        0xAB,
        `${filename} last byte should be 0xAB`
      );
    }

    // Assert -- voice data
    assert.ok(voiceData instanceof ArrayBuffer, 'voiceData should be an ArrayBuffer');
    assert.equal(voiceData.byteLength, 64, 'voiceData should be 64 bytes');
  });
});
