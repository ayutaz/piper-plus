/**
 * TDD Tests for DictManager (辞書動的ダウンロード + IndexedDB キャッシュ)
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 */

import assert from 'node:assert/strict';
import { describe, it, beforeEach, afterEach } from 'node:test';

// ---- Mock: IndexedDB -----------------------------------------------------------

/**
 * Minimal IndexedDB mock for DictManager tests.
 *
 * DictManager uses the global `indexedDB.open()` internally (via openDB()),
 * so we inject a global mock rather than passing a factory.
 */
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
  // Schedule callback on microtask to match real IDB behavior.
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

/** Singleton DB instance shared across a single test to simulate persistence. */
let _mockDB;

/** Track dbName passed to indexedDB.open() for behavior-based assertions. */
let _lastOpenedDbName;

function installIndexedDBMock() {
  _mockDB = new MockIDBDatabase();
  _lastOpenedDbName = undefined;
  globalThis.indexedDB = {
    open(name, version) {
      _lastOpenedDbName = name;
      const req = { result: null, onsuccess: null, onerror: null, onupgradeneeded: null };
      Promise.resolve().then(() => {
        // Fire upgrade on first open (simulates DB creation).
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

/**
 * Install a global fetch mock that returns ArrayBuffers of a given size.
 * Tracks which URLs were requested.
 *
 * @param {Object} [opts]
 * @param {boolean} [opts.shouldFail]     - Return 404 for all fetches.
 * @param {boolean} [opts.shouldReject]   - Reject with TypeError (network error).
 * @returns {string[]} Array that collects fetched URLs.
 */
function installFetchMock({ shouldFail = false, shouldReject = false } = {}) {
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(url);
    if (shouldReject) {
      throw new TypeError('Failed to fetch');
    }
    if (shouldFail) {
      return { ok: false, status: 404, statusText: 'Not Found' };
    }
    const body = new ArrayBuffer(64);
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

// ---- Expected file list --------------------------------------------------------

const EXPECTED_DICT_FILES = [
  'char.bin',
  'matrix.bin',
  'sys.dic',
  'unk.dic',
  'left-id.def',
  'right-id.def',
  'pos-id.def',
  'rewrite.def',
];

// ---- Tests ---------------------------------------------------------------------

describe('DictManager', { skip }, () => {
  /** @type {string[]} URLs fetched during the current test. */
  let fetched;

  beforeEach(() => {
    installIndexedDBMock();
    fetched = installFetchMock();
  });

  afterEach(() => {
    fetched = [];
  });

  // ---------- 1. DictManager 構築 ------------------------------------------------

  describe('構築', () => {
    it('デフォルトオプションで構築可能', () => {
      const dm = new DictManager();
      assert.ok(dm, 'DictManager instance should be truthy');
    });

    it('カスタム cachePrefix を設定すると indexedDB.open に渡される', async () => {
      const dm = new DictManager({ cachePrefix: 'my-custom-prefix' });
      await dm.loadDictionary();
      assert.equal(
        _lastOpenedDbName,
        'my-custom-prefix',
        'indexedDB.open() should receive custom cachePrefix'
      );
    });

    it('cachePrefix 未指定時はデフォルト名で indexedDB.open が呼ばれる', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      assert.equal(
        _lastOpenedDbName,
        'piper-plus-dict',
        'indexedDB.open() should receive default DB name'
      );
    });
  });

  // ---------- 2. 辞書ファイルリスト -----------------------------------------------

  describe('辞書ファイルリスト', () => {
    it('8ファイルが取得される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      // 8 dict files + 1 voice file = 9 fetches total.
      const dictFetches = fetched.filter((u) => !u.includes('voice'));
      assert.equal(dictFetches.length, 8);
    });

    it('返却される dictFiles のキー集合が期待セットと一致する', async () => {
      const dm = new DictManager();
      const { dictFiles } = await dm.loadDictionary();
      const actualKeys = new Set(Object.keys(dictFiles));
      const expectedKeys = new Set(EXPECTED_DICT_FILES);
      assert.deepEqual(actualKeys, expectedKeys);
    });

    // Individual file-presence tests (split from the original 8-file loop).
    for (const filename of EXPECTED_DICT_FILES) {
      it(`dictFiles に ${filename} が含まれる`, async () => {
        const dm = new DictManager();
        const { dictFiles } = await dm.loadDictionary();
        assert.ok(dictFiles[filename], `dictFiles should contain '${filename}'`);
      });
    }

    it('取得 URL 群が全辞書ファイルを網羅する', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const dictFetches = fetched.filter((u) => !u.includes('voice'));
      const fetchedBasenames = new Set(dictFetches.map((u) => u.split('/').pop()));
      const expectedBasenames = new Set(EXPECTED_DICT_FILES);
      assert.deepEqual(fetchedBasenames, expectedBasenames);
    });
  });

  // ---------- 3. デフォルト URL ---------------------------------------------------

  describe('デフォルト URL', () => {
    it('dictUrl 未指定時に HuggingFace URL が使用される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const dictUrls = fetched.filter((u) => !u.includes('voice'));
      for (const url of dictUrls) {
        assert.ok(
          url.startsWith('https://huggingface.co/'),
          `Dict URL should start with HuggingFace origin, got: ${url}`
        );
      }
    });

    it('voiceUrl 未指定時にデフォルト voice URL が使用される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const voiceUrl = fetched.find((u) => u.includes('voice'));
      assert.ok(voiceUrl, 'A voice URL should have been fetched');
      assert.ok(
        voiceUrl.startsWith('https://huggingface.co/'),
        `Voice URL should start with HuggingFace origin, got: ${voiceUrl}`
      );
      assert.ok(
        voiceUrl.includes('mei_normal.htsvoice'),
        `Voice URL should reference mei_normal.htsvoice, got: ${voiceUrl}`
      );
    });

    it('カスタム dictUrl を指定すると使用される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary({ dictUrl: 'https://example.com/dict' });
      const dictUrls = fetched.filter((u) => !u.includes('voice'));
      for (const url of dictUrls) {
        assert.ok(
          url.startsWith('https://example.com/dict/'),
          `Dict URL should use custom base, got: ${url}`
        );
      }
    });

    it('カスタム voiceUrl を指定すると使用される', async () => {
      const dm = new DictManager();
      await dm.loadDictionary({ voiceUrl: 'https://example.com/voice.htsvoice' });
      const voiceUrl = fetched.find((u) => u.includes('example.com'));
      assert.equal(voiceUrl, 'https://example.com/voice.htsvoice');
    });
  });

  // ---------- 4. isCached() -------------------------------------------------------

  describe('isCached()', () => {
    it('loadDictionary 前は false を返す', async () => {
      const dm = new DictManager();
      const cached = await dm.isCached();
      assert.equal(cached, false);
    });

    it('loadDictionary 後は true を返す', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const cached = await dm.isCached();
      assert.equal(cached, true);
    });
  });

  // ---------- 5. clearCache() -----------------------------------------------------

  describe('clearCache()', () => {
    it('clearCache 後は isCached が false を返す', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      // Sanity check: should be cached after load.
      assert.equal(await dm.isCached(), true);

      await dm.clearCache();
      const cached = await dm.isCached();
      assert.equal(cached, false);
    });
  });

  // ---------- 6. キャッシュ後の再取得 -----------------------------------------------

  describe('キャッシュ後の再取得', () => {
    it('2回目の loadDictionary は fetch を呼ばない (キャッシュヒット)', async () => {
      const dm = new DictManager();
      await dm.loadDictionary();
      const firstFetchCount = fetched.length;
      assert.ok(firstFetchCount > 0, 'first load should fetch');

      // Reset tracked URLs, but keep the same IDB / DictManager state.
      fetched.length = 0;
      await dm.loadDictionary();
      assert.equal(fetched.length, 0, 'second load should not fetch (all cached)');
    });
  });

  // ---------- 7. onProgress コールバック ------------------------------------------

  describe('onProgress コールバック', () => {
    it('辞書フェーズで phase, file, overallPercent が通知される', async () => {
      const calls = [];
      const dm = new DictManager();
      await dm.loadDictionary({
        onProgress: (info) => calls.push(info),
      });

      const dictCalls = calls.filter((c) => c.phase === 'dict');
      assert.ok(dictCalls.length > 0, 'should receive at least one dict-phase callback');

      for (const call of dictCalls) {
        assert.equal(call.phase, 'dict');
        assert.equal(typeof call.file, 'string', 'file should be a string');
        assert.equal(typeof call.overallPercent, 'number', 'overallPercent should be a number');
      }
    });

    it('voice フェーズで phase と overallPercent が通知される', async () => {
      const calls = [];
      const dm = new DictManager();
      await dm.loadDictionary({
        onProgress: (info) => calls.push(info),
      });

      const voiceCalls = calls.filter((c) => c.phase === 'voice');
      assert.ok(voiceCalls.length > 0, 'should receive at least one voice-phase callback');
      for (const call of voiceCalls) {
        assert.equal(call.phase, 'voice');
        assert.equal(typeof call.overallPercent, 'number');
      }
    });

    it('最終コールバックの overallPercent が 100 である', async () => {
      const calls = [];
      const dm = new DictManager();
      await dm.loadDictionary({
        onProgress: (info) => calls.push(info),
      });

      assert.ok(calls.length > 0, 'should receive progress callbacks');
      const last = calls[calls.length - 1];
      assert.equal(last.overallPercent, 100, 'last callback should be 100%');
    });

    it('loaded と total がバイト値として含まれる', async () => {
      const calls = [];
      const dm = new DictManager();
      await dm.loadDictionary({
        onProgress: (info) => calls.push(info),
      });

      for (const call of calls) {
        assert.equal(typeof call.loaded, 'number', 'loaded should be a number');
        assert.equal(typeof call.total, 'number', 'total should be a number');
        assert.ok(call.loaded >= 0, 'loaded should be non-negative');
        assert.ok(call.total >= 0, 'total should be non-negative');
      }
    });
  });

  // ---------- 8. エラーケース -----------------------------------------------------

  describe('エラーケース', () => {
    it('HTTP 404 でエラーがスローされる', async () => {
      fetched = installFetchMock({ shouldFail: true });
      const dm = new DictManager();
      await assert.rejects(
        () => dm.loadDictionary({ dictUrl: 'https://invalid.example.com/dict' }),
        (err) => {
          assert.ok(
            err.message.includes('Failed to fetch') || err.message.includes('404'),
            `Error message should indicate fetch failure, got: ${err.message}`
          );
          return true;
        }
      );
    });

    it('ネットワークエラー (TypeError: Failed to fetch) でエラーがスローされる', async () => {
      fetched = installFetchMock({ shouldReject: true });
      const dm = new DictManager();
      await assert.rejects(
        () => dm.loadDictionary({ dictUrl: 'https://unreachable.example.com/dict' }),
        (err) => {
          assert.ok(err instanceof TypeError, 'should be a TypeError');
          assert.ok(
            err.message.includes('Failed to fetch'),
            `Error message should be 'Failed to fetch', got: ${err.message}`
          );
          return true;
        }
      );
    });
  });
});
