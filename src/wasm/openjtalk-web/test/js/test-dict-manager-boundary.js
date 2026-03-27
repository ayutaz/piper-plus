/**
 * TDD Tests for DictManager -- 境界値・エラーケース
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 *
 * DictManager の異常系・エッジケースを網羅するテスト群。
 * ネットワークエラー、部分的失敗、IndexedDB不可、同時呼び出し等。
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// ---- Mock: IndexedDB -----------------------------------------------------------

class MockObjectStore {
  constructor(store) { this._store = store; }

  get(key) {
    const result = this._store.get(key) ?? undefined;
    return _fakeRequest(result);
  }

  put(val) {
    this._store.set(val.key, val);
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

let _mockDB;
let _lastOpenedDbName;

function installIndexedDBMock() {
  _mockDB = new MockIDBDatabase();
  _lastOpenedDbName = undefined;
  globalThis.indexedDB = {
    open(name, _version) {
      _lastOpenedDbName = name;
      const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
      Promise.resolve().then(() => {
        if (req.onupgradeneeded) {
          req.onupgradeneeded({ target: { result: _mockDB } });
        }
        req.result = _mockDB;
        if (req.onsuccess) req.onsuccess();
      });
      return req;
    },
  };
}

// ---- Mock: fetch ---------------------------------------------------------------

/** All 8 dict files + 1 voice = 9 total fetches */
const DICT_FILES = [
  'char.bin', 'matrix.bin', 'sys.dic', 'unk.dic',
  'left-id.def', 'right-id.def', 'pos-id.def', 'rewrite.def',
];

/**
 * Install a configurable fetch mock.
 *
 * @param {Object} [opts]
 * @param {boolean} [opts.shouldFail]     - Return 404 for all fetches.
 * @param {boolean} [opts.shouldReject]   - Reject with TypeError.
 * @param {Set<string>} [opts.failFiles]  - Set of filenames that return 404.
 * @param {number} [opts.bodySize]        - Response ArrayBuffer size (default 64).
 * @returns {string[]}
 */
function installFetchMock({ shouldFail = false, shouldReject = false, failFiles = null, bodySize = 64 } = {}) {
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(url);
    if (shouldReject) {
      throw new TypeError('Failed to fetch');
    }
    // Per-file 404 support.
    if (failFiles) {
      const basename = url.split('/').pop();
      if (failFiles.has(basename)) {
        return { ok: false, status: 404, statusText: 'Not Found' };
      }
    }
    if (shouldFail) {
      return { ok: false, status: 404, statusText: 'Not Found' };
    }
    const body = new ArrayBuffer(bodySize);
    return {
      ok: true,
      headers: { get: () => null },
      body: null,
      arrayBuffer: async () => body,
    };
  };
  return fetched;
}

// ---- Import SUT ----------------------------------------------------------------

let DictManager;
try {
  const mod = await import('../../src/dict-manager.js');
  DictManager = mod.DictManager || mod.default;
} catch {
  DictManager = null;
}

const skip = DictManager === null;

// ---- Saved globals for cleanup -------------------------------------------------

let _savedIndexedDB;
let _savedFetch;

// ---- Tests ---------------------------------------------------------------------

describe('DictManager 境界値・エラーケース', { skip }, () => {
  /** @type {string[]} */
  let fetched;

  beforeEach(() => {
    _savedIndexedDB = globalThis.indexedDB;
    _savedFetch = globalThis.fetch;
    installIndexedDBMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    globalThis.indexedDB = _savedIndexedDB;
    globalThis.fetch = _savedFetch;
    fetched = [];
  });

  // ---------- 1. 空 cachePrefix ---------------------------------------------------

  it('空の cachePrefix でデフォルト値が使用される', async () => {
    // Arrange
    const dm = new DictManager({ cachePrefix: '' });

    // Act
    await dm.loadDictionary();

    // Assert -- falsy '' triggers || fallback to 'piper-plus-dict'
    assert.equal(
      _lastOpenedDbName,
      'piper-plus-dict',
      'Empty cachePrefix should fall back to default DB name'
    );
  });

  // ---------- 2. ネットワークエラー (TypeError) ------------------------------------

  it('ネットワークエラーで適切なエラーがスローされる', async () => {
    // Arrange
    fetched = installFetchMock({ shouldReject: true });
    const dm = new DictManager();

    // Act & Assert
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => {
        assert.ok(err instanceof TypeError, 'Error should be a TypeError');
        assert.ok(
          err.message.includes('Failed to fetch'),
          `Error message should contain 'Failed to fetch', got: ${err.message}`
        );
        return true;
      }
    );
  });

  // ---------- 3. 個別ファイル 404 -------------------------------------------------

  it('個別ファイルが 404 の場合にエラー', async () => {
    // Arrange -- only sys.dic fails
    fetched = installFetchMock({ failFiles: new Set(['sys.dic']) });
    const dm = new DictManager();

    // Act & Assert
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => {
        assert.ok(
          err.message.includes('Failed to fetch') || err.message.includes('404'),
          `Error should indicate fetch failure for individual file, got: ${err.message}`
        );
        assert.ok(
          err.message.includes('sys.dic'),
          `Error should reference the failed file, got: ${err.message}`
        );
        return true;
      }
    );
  });

  // ---------- 4. 部分的ダウンロード失敗 -------------------------------------------

  it('部分的なダウンロード失敗でもエラーが発生する', async () => {
    // Arrange -- last dict file fails; others succeed
    fetched = installFetchMock({ failFiles: new Set(['rewrite.def']) });
    const dm = new DictManager();

    // Act & Assert -- even if 7/8 files succeed, one failure causes rejection
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => {
        assert.ok(
          err.message.includes('Failed to fetch') || err.message.includes('404'),
          `Partial failure should still throw, got: ${err.message}`
        );
        return true;
      }
    );

    // Verify that earlier files were actually fetched before the failure
    const fetchedBasenames = fetched.map((u) => u.split('/').pop());
    assert.ok(
      fetchedBasenames.includes('char.bin'),
      'Files before the failing one should have been fetched'
    );
  });

  // ---------- 5. 非常に大きな辞書ファイル ------------------------------------------

  it('非常に大きな辞書ファイルのダウンロード', async () => {
    // Arrange -- 10 MB mock response per file
    const largeSize = 10 * 1024 * 1024;
    fetched = installFetchMock({ bodySize: largeSize });
    const dm = new DictManager();

    // Act
    const { dictFiles, voiceData } = await dm.loadDictionary();

    // Assert -- all files should be present with the large size
    for (const filename of DICT_FILES) {
      assert.ok(dictFiles[filename], `dictFiles should contain '${filename}'`);
      assert.equal(
        dictFiles[filename].byteLength,
        largeSize,
        `${filename} should have ${largeSize} bytes`
      );
    }
    assert.equal(
      voiceData.byteLength,
      largeSize,
      `voiceData should have ${largeSize} bytes`
    );
  });

  // ---------- 6. dictUrl 末尾スラッシュあり ----------------------------------------

  it('dictUrl に末尾スラッシュがある場合の正規化', async () => {
    // Arrange
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({ dictUrl: 'https://example.com/dict/' });

    // Assert -- URL is constructed as `${dictBaseUrl}/${filename}`,
    // so trailing slash produces double-slash: dict//char.bin
    const dictUrls = fetched.filter((u) => !u.includes('voice'));
    for (const url of dictUrls) {
      assert.ok(
        url.startsWith('https://example.com/dict/'),
        `Dict URL should start with the custom base, got: ${url}`
      );
    }

    // Verify file names are still resolvable
    const basenames = dictUrls.map((u) => u.split('/').pop());
    for (const filename of DICT_FILES) {
      assert.ok(
        basenames.includes(filename),
        `Should fetch ${filename} even with trailing slash`
      );
    }
  });

  // ---------- 7. dictUrl 末尾スラッシュなし ----------------------------------------

  it('dictUrl に末尾スラッシュがない場合の正規化', async () => {
    // Arrange
    const dm = new DictManager();

    // Act
    await dm.loadDictionary({ dictUrl: 'https://example.com/dict' });

    // Assert -- URL constructed as 'https://example.com/dict/char.bin'
    const dictUrls = fetched.filter((u) => !u.includes('voice'));
    for (const url of dictUrls) {
      assert.ok(
        url.startsWith('https://example.com/dict/'),
        `Dict URL should use custom base with separator, got: ${url}`
      );
      // Confirm no double slash
      assert.ok(
        !url.includes('dict//'),
        `URL should not contain double-slash, got: ${url}`
      );
    }
  });

  // ---------- 8. indexedDB 利用不可 ------------------------------------------------

  it('indexedDB が利用不可の場合の挙動', async () => {
    // Arrange -- remove indexedDB entirely
    globalThis.indexedDB = undefined;
    const dm = new DictManager();

    // Act & Assert -- _openDB() calls indexedDB.open() which will throw
    await assert.rejects(
      () => dm.loadDictionary(),
      (err) => {
        // TypeError because indexedDB is undefined -> cannot read .open
        assert.ok(
          err instanceof TypeError || err instanceof Error,
          `Should throw when indexedDB unavailable, got: ${err.constructor.name}`
        );
        return true;
      }
    );
  });

  // ---------- 9. 同時呼び出し (race condition) ------------------------------------

  it('同時に loadDictionary を2回呼んだ場合', async () => {
    // Arrange
    const dm = new DictManager();

    // Act -- fire two loads concurrently
    const [result1, result2] = await Promise.all([
      dm.loadDictionary(),
      dm.loadDictionary(),
    ]);

    // Assert -- both should resolve successfully with all expected keys
    const expectedKeys = new Set(DICT_FILES);
    assert.deepEqual(
      new Set(Object.keys(result1.dictFiles)),
      expectedKeys,
      'First concurrent result should have all dict files'
    );
    assert.deepEqual(
      new Set(Object.keys(result2.dictFiles)),
      expectedKeys,
      'Second concurrent result should have all dict files'
    );
    assert.ok(result1.voiceData, 'First result should have voiceData');
    assert.ok(result2.voiceData, 'Second result should have voiceData');

    // Both calls should produce valid ArrayBuffer instances
    for (const filename of DICT_FILES) {
      assert.ok(
        result1.dictFiles[filename] instanceof ArrayBuffer,
        `result1.dictFiles['${filename}'] should be ArrayBuffer`
      );
      assert.ok(
        result2.dictFiles[filename] instanceof ArrayBuffer,
        `result2.dictFiles['${filename}'] should be ArrayBuffer`
      );
    }
  });
});
