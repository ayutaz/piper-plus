/**
 * TDD Tests for DictManager (辞書動的ダウンロード + IndexedDB キャッシュ)
 *
 * テスト対象: src/wasm/openjtalk-web/src/dict-manager.js
 */

import { strict as assert } from 'assert';
import { describe, it, beforeEach } from 'node:test';

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

function installIndexedDBMock() {
  _mockDB = new MockIDBDatabase();
  globalThis.indexedDB = {
    open(name, version) {
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
 */
function installFetchMock({ shouldFail = false } = {}) {
  const fetched = [];
  globalThis.fetch = async (url) => {
    fetched.push(url);
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

// ---- Tests ---------------------------------------------------------------------

describe('DictManager', { skip }, () => {
  beforeEach(() => {
    installIndexedDBMock();
    installFetchMock();
  });

  // ---------- 1. DictManager 構築 ------------------------------------------------

  describe('構築', () => {
    it('デフォルトオプションで構築可能', () => {
      const dm = new DictManager();
      assert.ok(dm, 'DictManager instance should be truthy');
    });

    it('カスタム cachePrefix を設定可能', () => {
      const dm = new DictManager({ cachePrefix: 'my-custom-prefix' });
      // _dbName is the internal field that stores the prefix.
      assert.equal(dm._dbName, 'my-custom-prefix');
    });

    it('cachePrefix 未指定時はデフォルト値が使用される', () => {
      const dm = new DictManager();
      assert.equal(dm._dbName, 'piper-plus-dict');
    });
  });

  // ---------- 2. 辞書ファイルリスト -----------------------------------------------

  describe('辞書ファイルリスト', () => {
    const EXPECTED_FILES = [
      'char.bin',
      'matrix.bin',
      'sys.dic',
      'unk.dic',
      'left-id.def',
      'right-id.def',
      'pos-id.def',
      'rewrite.def',
    ];

    it('必須の8ファイルが定義されている', async () => {
      const fetched = installFetchMock();
      const dm = new DictManager();
      await dm.loadDictionary();
      // 8 dict files + 1 voice file = 9 fetches total.
      const dictFetches = fetched.filter((u) => !u.includes('voice'));
      assert.equal(dictFetches.length, 8);
    });

    it('char.bin, matrix.bin, sys.dic, unk.dic, left-id.def, right-id.def, pos-id.def, rewrite.def が取得される', async () => {
      const fetched = installFetchMock();
      const dm = new DictManager();
      const { dictFiles } = await dm.loadDictionary();
      for (const name of EXPECTED_FILES) {
        assert.ok(
          dictFiles[name],
          `dictFiles should contain '${name}'`
        );
        const matchingUrl = fetched.find((u) => u.endsWith(`/${name}`));
        assert.ok(matchingUrl, `A fetch URL should end with '/${name}'`);
      }
    });
  });

  // ---------- 3. デフォルト URL ---------------------------------------------------

  describe('デフォルト URL', () => {
    it('dictUrl 未指定時に HuggingFace URL が使用される', async () => {
      const fetched = installFetchMock();
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
      const fetched = installFetchMock();
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
      const fetched = installFetchMock();
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
      const fetched = installFetchMock();
      const dm = new DictManager();
      await dm.loadDictionary({ voiceUrl: 'https://example.com/voice.htsvoice' });
      const voiceUrl = fetched.find((u) => u.includes('example.com'));
      assert.equal(voiceUrl, 'https://example.com/voice.htsvoice');
    });
  });

  // ---------- 4. エラーケース -----------------------------------------------------

  describe('エラーケース', () => {
    it('無効な URL (fetch 404) でエラーがスローされる', async () => {
      installFetchMock({ shouldFail: true });
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
  });
});
